"""SCRUM-24 manage equipment reservation, through the HTTP API with the repository mocked.

The database functions decide availability, lock rows and write history and
notices; their behaviour (AC1-AC7, AC10, AC11, AC13) is checked against the real
project by supabase/verification/equipment_reservation_checks.sql, and AC5's race
by verify_live.py. Here: routing, role gates (AC8), outcome-to-status mapping,
the free count on a refusal (AC3), the return to planning when an event stops
being Ready (AC11, CR-104 AC10), what each role's payload carries (AC9, AC12),
and a Supabase outage answering 503.
"""

from copy import deepcopy

import httpx
import pytest

from app.modules.equipment import repository, service
from app.modules.events import service as events_service

TECH_ID = "a0000000-0000-4000-8000-000000000004"
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
EVENT_ID = "e0000000-0000-4000-8000-000000000202"
LINE_ID = "90000000-0000-4000-8000-000000000001"
UNKNOWN_LINE = "90000000-0000-4000-8000-0000000000ff"
PROJECTOR_ID = "b0000000-0000-4000-8000-000000000001"

RESERVE_URL = f"/api/v1/equipment/requests/{LINE_ID}/reserve"
NOT_AVAILABLE_URL = f"/api/v1/equipment/requests/{LINE_ID}/not-available"
NOTES_URL = f"/api/v1/equipment/requests/{LINE_ID}/notes"
EXIT_URL = f"/api/v1/equipment/events/{EVENT_ID}/exit-confirmation"
TECHNICAL_URL = f"/api/v1/equipment/events/{EVENT_ID}/technical"
COORDINATOR_URL = f"/api/v1/equipment/requests/event/{EVENT_ID}"

OTHER_ROLES = ["event_organiser", "event_coordinator", "event_coordinator_lead",
               "venue_staff", "safety_officer", "attendee"]


def line_row(status="pending", notes=None, reason=None):
    return {
        "id": LINE_ID, "submission_id": "50000000-0000-4000-8000-000000000001", "event_id": EVENT_ID,
        "equipment_id": PROJECTOR_ID, "quantity": 3, "technical_requirements": None,
        "status": status, "technical_notes": notes, "not_available_reason": reason,
        "requested_by": COORDINATOR_ID, "created_at": "2026-10-06T02:00:00+00:00",
        "equipment": {"name": "4K Projector"},
        "requester": {"id": COORDINATOR_ID, "full_name": "Marcus Lim"},
        "event": {"name": "Year-End Dinner", "starts_at": "2026-11-20T10:00:00+00:00", "status": "planning"},
    }


def technical_event(status="planning", exit_at=None):
    return {
        "id": EVENT_ID, "name": "Year-End Dinner", "status": status, "coordinator_id": COORDINATOR_ID,
        "starts_at": "2026-11-20T10:00:00+00:00", "ends_at": "2026-11-20T13:00:00+00:00",
        "technical_readiness": "pending", "exit_confirmed_at": exit_at,
        "coordinator": {"full_name": "Marcus Lim"},
        "exit_confirmer": {"full_name": "Tan Wei"} if exit_at else None,
    }


@pytest.fixture()
def store(monkeypatch):
    """Canned database answers, and every call the service makes."""
    state = {
        "line": {"id": LINE_ID, "event_id": EVENT_ID, "status": "pending"},
        "lines": [line_row()],
        "event": technical_event(),
        "history": [],
        "reserve": ("ok", 2, False),
        "not_available": ("ok", False),
        "note": "ok",
        "exit": ("ok", False),
        "recheck": ("ok", 0, False),
        "calls": [],
        "returned": [],
    }

    def record(name):
        def _record(*args):
            state["calls"].append((name, *args))
            return state[name]
        return _record

    monkeypatch.setattr(repository, "get_line",
                        lambda line_id: deepcopy(state["line"]) if line_id == LINE_ID and state["line"] else None)
    monkeypatch.setattr(repository, "reserve_line", record("reserve"))
    monkeypatch.setattr(repository, "mark_not_available", record("not_available"))
    monkeypatch.setattr(repository, "set_note", record("note"))
    monkeypatch.setattr(repository, "set_exit_confirmation", record("exit"))
    monkeypatch.setattr(repository, "recheck_event", record("recheck"))
    monkeypatch.setattr(repository, "get_event_technical",
                        lambda event_id: deepcopy(state["event"]) if event_id == EVENT_ID else None)
    monkeypatch.setattr(repository, "list_event_requests", lambda event_id: deepcopy(state["lines"]))
    monkeypatch.setattr(repository, "list_technical_history", lambda event_id: deepcopy(state["history"]))
    monkeypatch.setattr(events_service, "return_to_planning",
                        lambda event_id, **kwargs: state["returned"].append((event_id, kwargs)))
    return state


@pytest.fixture()
def tech(authenticate_as):
    authenticate_as("tech_support", user_id=TECH_ID)


class TestReserve:
    """AC1-AC5: Technical Support reserve a pending line if enough is free."""

    def test_reserving_calls_the_database_as_the_caller(self, client, auth_headers, store, tech):
        response = client.post(RESERVE_URL, headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {"line_id": LINE_ID, "status": "reserved", "free_quantity": 2}
        assert store["calls"] == [("reserve", LINE_ID, TECH_ID)]
        assert store["returned"] == []

    def test_not_enough_is_refused_with_the_free_count(self, client, auth_headers, store, tech):
        store["reserve"] = ("insufficient", 1, False)

        response = client.post(RESERVE_URL, headers=auth_headers)

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Not enough available: 1 free for this event's time. The line stays Pending.",
            "free_quantity": 1,
        }

    def test_none_free_is_still_a_count(self, client, auth_headers, store, tech):
        store["reserve"] = ("insufficient", 0, False)

        assert client.post(RESERVE_URL, headers=auth_headers).json()["free_quantity"] == 0

    def test_a_flagged_line_that_still_does_not_fit_stays_flagged(self, client, auth_headers, store, tech):
        store["line"]["status"] = "re_review"
        store["reserve"] = ("insufficient", 1, False)

        detail = client.post(RESERVE_URL, headers=auth_headers).json()["detail"]

        assert detail.endswith("The line stays Re-review.")

    def test_an_unknown_line_is_404(self, client, auth_headers, store, tech):
        response = client.post(f"/api/v1/equipment/requests/{UNKNOWN_LINE}/reserve", headers=auth_headers)

        assert response.status_code == 404
        assert response.json()["detail"] == "Equipment line not found."
        assert store["calls"] == []

    def test_a_line_deleted_after_the_lookup_is_404(self, client, auth_headers, store, tech):
        store["reserve"] = ("line_not_found", None, False)

        assert client.post(RESERVE_URL, headers=auth_headers).status_code == 404

    @pytest.mark.parametrize(("outcome", "detail"), [
        ("not_reservable", "Only a Pending or Re-review line can be reserved. Reload."),
        ("event_closed", "This event is no longer open for equipment arrangements."),
        ("no_schedule", "This event has no date and time yet, so availability can't be checked."),
    ])
    def test_other_refusals_are_conflicts(self, client, auth_headers, store, tech, outcome, detail):
        store["reserve"] = (outcome, None, False)

        response = client.post(RESERVE_URL, headers=auth_headers)

        assert response.status_code == 409
        assert response.json() == {"detail": detail}

    def test_an_unexpected_outcome_is_a_server_error(self, store, tech):
        store["reserve"] = ("surprise", None, False)

        with pytest.raises(RuntimeError):
            service.reserve_line(LINE_ID, TECH_ID)

    def test_a_supabase_outage_is_503(self, client, auth_headers, store, tech, monkeypatch):
        def down(*args):
            raise httpx.ConnectError("down")
        monkeypatch.setattr(repository, "reserve_line", down)

        response = client.post(RESERVE_URL, headers=auth_headers)

        assert response.status_code == 503
        assert response.json()["detail"] == "The equipment service is temporarily unavailable. Please try again."


class TestNotAvailable:
    """AC3, AC9: a line can be marked Not available, with a reason."""

    def test_marking_not_available_sends_the_trimmed_reason(self, client, auth_headers, store, tech):
        response = client.post(NOT_AVAILABLE_URL, headers=auth_headers, json={"reason": "  Only 2 in stock  "})

        assert response.status_code == 200
        assert response.json() == {"line_id": LINE_ID, "status": "rejected", "free_quantity": None}
        assert store["calls"] == [("not_available", LINE_ID, TECH_ID, "Only 2 in stock")]

    @pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 501}, {"reason": None}])
    def test_a_reason_is_required_and_bounded(self, client, auth_headers, store, tech, body):
        assert client.post(NOT_AVAILABLE_URL, headers=auth_headers, json=body).status_code == 422
        assert store["calls"] == []

    def test_a_reason_of_500_characters_is_accepted(self, client, auth_headers, store, tech):
        assert client.post(NOT_AVAILABLE_URL, headers=auth_headers, json={"reason": "x" * 500}).status_code == 200

    def test_a_blank_reason_refused_by_the_database_is_422(self, client, auth_headers, store, tech):
        store["not_available"] = ("reason_required", False)

        assert client.post(NOT_AVAILABLE_URL, headers=auth_headers, json={"reason": "ok"}).status_code == 422

    def test_a_ready_event_that_loses_a_line_returns_to_planning(self, client, auth_headers, store, tech):
        """AC11 with CR-104 AC10: Issue is no longer Ready, so a reviewed event goes back."""
        store["not_available"] = ("ok", True)

        client.post(NOT_AVAILABLE_URL, headers=auth_headers, json={"reason": "Broken"})

        assert store["returned"] == [(EVENT_ID, {"reason_code": "technical_not_ready"})]

    def test_a_released_line_is_a_conflict(self, client, auth_headers, store, tech):
        store["not_available"] = ("not_reservable", False)

        response = client.post(NOT_AVAILABLE_URL, headers=auth_headers, json={"reason": "x"})

        assert response.status_code == 409
        assert response.json()["detail"] == "This line is already Not available or released. Reload."


class TestNotes:
    """AC9, AC12: internal notes on a line."""

    def test_a_note_is_saved_trimmed(self, client, auth_headers, store, tech):
        response = client.put(NOTES_URL, headers=auth_headers, json={"note": "  From store B  "})

        assert response.status_code == 200
        assert store["calls"] == [("note", LINE_ID, TECH_ID, "From store B")]

    @pytest.mark.parametrize("body", [{"note": ""}, {"note": "  "}, {"note": None}])
    def test_a_blank_note_clears_it(self, client, auth_headers, store, tech, body):
        client.put(NOTES_URL, headers=auth_headers, json=body)

        assert store["calls"] == [("note", LINE_ID, TECH_ID, None)]

    def test_a_note_is_capped_at_2000_characters(self, client, auth_headers, store, tech):
        assert client.put(NOTES_URL, headers=auth_headers, json={"note": "x" * 2001}).status_code == 422
        assert client.put(NOTES_URL, headers=auth_headers, json={"note": "x" * 2000}).status_code == 200

    def test_a_closed_event_is_a_conflict(self, client, auth_headers, store, tech):
        store["note"] = "event_closed"

        assert client.put(NOTES_URL, headers=auth_headers, json={"note": "x"}).status_code == 409


class TestExitConfirmation:
    """AC10: tick "Equipment does not block exits or walkways"."""

    @pytest.mark.parametrize("confirmed", [True, False])
    def test_ticking_and_unticking(self, client, auth_headers, store, tech, confirmed):
        response = client.put(EXIT_URL, headers=auth_headers, json={"confirmed": confirmed})

        assert response.status_code == 204
        assert store["calls"] == [("exit", EVENT_ID, TECH_ID, confirmed)]

    @pytest.mark.parametrize("body", [{}, {"confirmed": "yes"}, {"confirmed": 1}, {"confirmed": None}])
    def test_confirmed_must_be_a_boolean(self, client, auth_headers, store, tech, body):
        assert client.put(EXIT_URL, headers=auth_headers, json=body).status_code == 422

    def test_unticking_a_ready_event_returns_it_to_planning(self, client, auth_headers, store, tech):
        store["exit"] = ("ok", True)

        client.put(EXIT_URL, headers=auth_headers, json={"confirmed": False})

        assert store["returned"] == [(EVENT_ID, {"reason_code": "technical_not_ready"})]

    def test_an_event_without_equipment_has_nothing_to_tick(self, client, auth_headers, store, tech):
        store["exit"] = ("no_equipment", False)

        response = client.put(EXIT_URL, headers=auth_headers, json={"confirmed": True})

        assert response.status_code == 409
        assert response.json()["detail"] == "This event has no equipment lines, so there is nothing to confirm."

    def test_an_unknown_event_is_404(self, client, auth_headers, store, tech):
        store["exit"] = ("event_not_found", False)

        assert client.put(EXIT_URL, headers=auth_headers, json={"confirmed": True}).status_code == 404


class TestTechnicalView:
    """AC9-AC13: Technical Support's view of one event's equipment."""

    def test_the_view_carries_lines_notes_tick_status_and_history(self, client, auth_headers, store, tech):
        store["event"] = technical_event(exit_at="2026-10-19T03:00:00+00:00")
        store["lines"] = [line_row("rejected", notes="Ask vendor", reason="Only 2 in stock")]
        store["history"] = [{
            "id": "h1", "request_id": LINE_ID, "action": "not_available", "from_status": "pending",
            "to_status": "rejected", "detail": "Only 2 in stock", "created_at": "2026-10-19T03:00:00+00:00",
            "actor": {"full_name": "Tan Wei"},
            "line": {"quantity": 3, "equipment": {"name": "4K Projector"}},
        }]

        body = client.get(TECHNICAL_URL, headers=auth_headers).json()

        assert body["event"]["name"] == "Year-End Dinner"
        assert body["event"]["coordinator_name"] == "Marcus Lim"
        assert body["technical_status"] == "pending"
        assert body["exit_confirmation"] == {"confirmed_by_name": "Tan Wei", "confirmed_at": "2026-10-19T03:00:00Z"}
        assert body["lines"][0]["technical_notes"] == "Ask vendor"
        assert body["lines"][0]["not_available_reason"] == "Only 2 in stock"
        assert body["history"] == [{
            "action": "not_available", "line_label": "3 × 4K Projector", "from_status": "pending",
            "to_status": "rejected", "detail": "Only 2 in stock", "actor_name": "Tan Wei",
            "created_at": "2026-10-19T03:00:00Z",
        }]

    def test_an_unticked_event_has_no_exit_confirmation_and_system_history_has_no_actor(
        self, client, auth_headers, store, tech
    ):
        store["history"] = [{"id": "h2", "request_id": None, "action": "exit_cleared", "from_status": None,
                             "to_status": None, "detail": "An equipment line was added.",
                             "created_at": "2026-10-19T03:00:00+00:00", "actor": None, "line": None}]

        body = client.get(TECHNICAL_URL, headers=auth_headers).json()

        assert body["exit_confirmation"] is None
        assert body["history"][0]["actor_name"] is None
        assert body["history"][0]["line_label"] is None

    @pytest.mark.parametrize("status", ["draft"])
    def test_a_draft_is_not_found(self, client, auth_headers, store, tech, status):
        store["event"] = technical_event(status=status)

        assert client.get(TECHNICAL_URL, headers=auth_headers).status_code == 404

    def test_an_unknown_event_is_not_found(self, client, auth_headers, store, tech):
        url = "/api/v1/equipment/events/e0000000-0000-4000-8000-0000000000ff/technical"

        assert client.get(url, headers=auth_headers).status_code == 404


class TestCoordinatorSeesStatusAndNotes:
    """AC9: the assigned coordinator sees each line's status, reason and notes,
    and the event's technical status and exit tick."""

    def test_the_coordinator_list_carries_notes_reason_status_and_tick(
        self, client, auth_headers, store, authenticate_as, monkeypatch
    ):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
        monkeypatch.setattr(events_service, "assigned_event",
                            lambda event_id, coordinator_id: {"id": EVENT_ID, "technical_readiness": "issue"})
        store["event"] = technical_event(exit_at="2026-10-19T03:00:00+00:00")
        store["lines"] = [line_row("rejected", notes="Ask vendor", reason="Only 2 in stock")]

        body = client.get(COORDINATOR_URL, headers=auth_headers).json()

        assert body["technical_status"] == "issue"
        assert body["exit_confirmation"]["confirmed_by_name"] == "Tan Wei"
        assert body["lines"][0]["status"] == "rejected"
        assert body["lines"][0]["technical_notes"] == "Ask vendor"
        assert body["lines"][0]["not_available_reason"] == "Only 2 in stock"


class TestOnlyTechnicalSupport:
    """AC8: every other active role gets 403, and nothing reaches the database."""

    @pytest.mark.parametrize("role", OTHER_ROLES)
    @pytest.mark.parametrize(("method", "url", "body"), [
        ("post", RESERVE_URL, None),
        ("post", NOT_AVAILABLE_URL, {"reason": "x"}),
        ("put", NOTES_URL, {"note": "x"}),
        ("put", EXIT_URL, {"confirmed": True}),
        ("get", TECHNICAL_URL, None),
    ])
    def test_other_roles_are_forbidden(self, client, auth_headers, store, authenticate_as, role, method, url, body):
        authenticate_as(role)

        response = client.request(method.upper(), url, headers=auth_headers, json=body)

        assert response.status_code == 403
        assert store["calls"] == []

    @pytest.mark.parametrize(("method", "url"), [("post", RESERVE_URL), ("get", TECHNICAL_URL)])
    def test_no_token_is_401(self, client, store, method, url):
        assert client.request(method.upper(), url).status_code == 401


class TestRecheck:
    """AC7: story 37 calls `recheck_event` after a date or time change."""

    def test_recheck_reports_how_many_lines_were_flagged(self, store):
        store["recheck"] = ("ok", 2, False)

        assert service.recheck_event(EVENT_ID) == 2
        assert store["calls"] == [("recheck", EVENT_ID, None)]
        assert store["returned"] == []

    def test_a_ready_event_that_is_flagged_returns_to_planning(self, store):
        store["recheck"] = ("ok", 1, True)

        service.recheck_event(EVENT_ID, actor_id=COORDINATOR_ID)

        assert store["calls"] == [("recheck", EVENT_ID, COORDINATOR_ID)]
        assert store["returned"] == [(EVENT_ID, {"reason_code": "technical_not_ready"})]

    @pytest.mark.parametrize("outcome", ["event_not_found", "no_schedule"])
    def test_nothing_to_recheck_flags_nothing(self, store, outcome):
        store["recheck"] = (outcome, 0, False)

        assert service.recheck_event(EVENT_ID) == 0


class TestNotesNeverReachOrganisers:
    """AC12: no organiser- or attendee-facing model carries technical notes."""

    def test_event_response_has_no_equipment_notes(self):
        from app.modules.events.schemas import EventResponse

        assert not {"technical_notes", "not_available_reason"} & set(EventResponse.model_fields)
