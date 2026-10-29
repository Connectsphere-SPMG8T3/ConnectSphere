"""CR-110 record technical preparation progress, through the HTTP API with the repository mocked.

The database function locks the event, refuses statuses other than Confirmed and
Preparation, makes the Confirmed -> Preparation move once, and writes the history
and notices (AC1, AC3, AC5); that is checked against the real project by
supabase/verification/technical_preparation_checks.sql. Here: routing, the role
gate (AC6), request validation (AC2), outcome-to-status mapping, and what each
role's payload carries (AC4).
"""

from copy import deepcopy

import httpx
import pytest

from app.modules.equipment import repository, service

TECH_ID = "a0000000-0000-4000-8000-000000000004"
EVENT_ID = "e0000000-0000-4000-8000-000000000202"
PREPARATION_URL = f"/api/v1/equipment/events/{EVENT_ID}/preparation"

OTHER_ROLES = ["event_organiser", "event_coordinator", "event_coordinator_lead",
               "venue_staff", "safety_officer", "attendee"]

LOCKED = "Technical preparation opens once the Safety Officer has confirmed the event."


@pytest.fixture()
def store(monkeypatch):
    state = {"preparation": {"outcome": "ok", "event_status": "preparation"}, "calls": []}

    def set_technical_preparation(*args):
        state["calls"].append(args)
        return deepcopy(state["preparation"])

    monkeypatch.setattr(repository, "set_technical_preparation", set_technical_preparation)
    return state


@pytest.fixture()
def tech(authenticate_as):
    authenticate_as("tech_support", user_id=TECH_ID)


class TestRecordPreparation:
    """AC1-AC3: Technical Support set the event's stage and internal note."""

    def test_an_update_is_saved_as_the_caller_with_the_note_trimmed(self, client, auth_headers, store, tech):
        response = client.put(PREPARATION_URL, headers=auth_headers,
                              json={"stage": "in_progress", "note": "  Cables run  "})

        assert response.status_code == 200
        assert response.json() == {"stage": "in_progress", "note": "Cables run", "event_status": "preparation"}
        assert store["calls"] == [(EVENT_ID, TECH_ID, "in_progress", "Cables run")]

    @pytest.mark.parametrize("stage", ["not_started", "in_preparation", "in_progress", "completed"])
    def test_every_stage_is_accepted(self, client, auth_headers, store, tech, stage):
        assert client.put(PREPARATION_URL, headers=auth_headers, json={"stage": stage}).status_code == 200

    @pytest.mark.parametrize("body", [{"note": None}, {"note": "   "}, {"note": ""}, {}])
    def test_a_blank_or_missing_note_clears_it(self, client, auth_headers, store, tech, body):
        body = {**body, "stage": "completed"}

        client.put(PREPARATION_URL, headers=auth_headers, json=body)

        assert store["calls"] == [(EVENT_ID, TECH_ID, "completed", None)]

    def test_a_note_of_2000_characters_is_accepted(self, client, auth_headers, store, tech):
        body = {"stage": "completed", "note": "n" * 2000}

        assert client.put(PREPARATION_URL, headers=auth_headers, json=body).status_code == 200

    @pytest.mark.parametrize("body", [
        {}, {"stage": "ready"}, {"stage": None}, {"stage": "Completed"},
        {"stage": "completed", "note": "n" * 2001},
    ])
    def test_an_unknown_stage_or_long_note_is_422(self, client, auth_headers, store, tech, body):
        assert client.put(PREPARATION_URL, headers=auth_headers, json=body).status_code == 422
        assert store["calls"] == []

    def test_an_event_that_is_not_confirmed_is_refused(self, client, auth_headers, store, tech):
        """AC1, including a direct API call; also an event back in Planning (CR-109 AC7)."""
        store["preparation"] = {"outcome": "not_confirmed", "event_status": "planning"}

        response = client.put(PREPARATION_URL, headers=auth_headers, json={"stage": "in_progress"})

        assert response.status_code == 409
        assert response.json() == {"detail": LOCKED}

    def test_an_unknown_or_draft_event_is_404(self, client, auth_headers, store, tech):
        store["preparation"] = {"outcome": "event_not_found", "event_status": None}

        assert client.put(PREPARATION_URL, headers=auth_headers, json={"stage": "in_progress"}).status_code == 404

    def test_an_unexpected_outcome_is_a_server_error(self, store):
        store["preparation"] = {"outcome": "surprise", "event_status": None}

        with pytest.raises(RuntimeError):
            service.set_technical_preparation(EVENT_ID, TECH_ID, "completed", None)

    def test_a_supabase_outage_is_503(self, client, auth_headers, store, tech, monkeypatch):
        def down(*args):
            raise httpx.ConnectError("down")
        monkeypatch.setattr(repository, "set_technical_preparation", down)

        response = client.put(PREPARATION_URL, headers=auth_headers, json={"stage": "completed"})

        assert response.status_code == 503


class TestOnlyTechnicalSupport:
    """AC6: every other active role gets 403 and nothing reaches the database. An
    account acting as another role while holding tech_support is covered by the
    route matrix in test_active_role_access.py (SCRUM-76)."""

    @pytest.mark.parametrize("role", OTHER_ROLES)
    def test_other_roles_are_forbidden(self, client, auth_headers, store, authenticate_as, role):
        authenticate_as(role)

        response = client.put(PREPARATION_URL, headers=auth_headers, json={"stage": "completed"})

        assert response.status_code == 403
        assert store["calls"] == []

    def test_no_token_is_401(self, client, store):
        assert client.put(PREPARATION_URL, json={"stage": "completed"}).status_code == 401


TECHNICAL_URL = f"/api/v1/equipment/events/{EVENT_ID}/technical"
RECORDED = {"preparation_record": {
    "stage": "in_progress", "note": "Cables run", "updated_at": "2026-10-26T03:00:00+00:00",
    "updater": {"full_name": "Tan Wei"},
}}


@pytest.fixture()
def technical(monkeypatch):
    """Technical Support's view of a Confirmed event with no equipment lines."""
    state = {"event": {
        "id": EVENT_ID, "name": "Year-End Dinner", "status": "confirmed", "coordinator_id": None,
        "starts_at": "2026-11-20T10:00:00+00:00", "ends_at": "2026-11-20T13:00:00+00:00",
        "technical_readiness": "not_required", "exit_confirmed_at": None,
        "coordinator": None, "exit_confirmer": None,
    }, "history": []}
    monkeypatch.setattr(repository, "get_event_technical", lambda event_id: deepcopy(state["event"]))
    monkeypatch.setattr(repository, "list_event_requests", lambda event_id: [])
    monkeypatch.setattr(repository, "list_technical_history", lambda event_id: deepcopy(state["history"]))
    return state


class TestTechnicalView:
    """AC2, AC5: Technical Support see the stage, the note and the updates."""

    def test_the_view_carries_the_recorded_stage_note_and_who_set_it(self, client, auth_headers, technical, tech):
        technical["event"].update(RECORDED)

        body = client.get(TECHNICAL_URL, headers=auth_headers).json()

        assert body["technical_preparation"] == {
            "stage": "in_progress", "note": "Cables run",
            "updated_at": "2026-10-26T03:00:00Z", "updated_by_name": "Tan Wei",
        }

    def test_a_confirmed_event_with_no_update_is_not_started(self, client, auth_headers, technical, tech):
        """Q16: no stored row is needed for Not started."""
        body = client.get(TECHNICAL_URL, headers=auth_headers).json()

        assert body["technical_preparation"] == {
            "stage": "not_started", "note": None, "updated_at": None, "updated_by_name": None,
        }

    def test_stage_changes_are_listed_in_the_history(self, client, auth_headers, technical, tech):
        technical["history"] = [{
            "id": "h1", "request_id": None, "action": "preparation", "from_status": "not_started",
            "to_status": "in_progress", "detail": None, "created_at": "2026-10-26T03:00:00+00:00",
            "actor": {"full_name": "Tan Wei"}, "line": None,
        }]

        [entry] = client.get(TECHNICAL_URL, headers=auth_headers).json()["history"]

        assert entry["action"] == "preparation"
        assert (entry["from_status"], entry["to_status"], entry["actor_name"]) == ("not_started", "in_progress", "Tan Wei")


def read_event(client, auth_headers, authenticate_as, monkeypatch, row, role, user_id):
    from app.modules.events import repository as events_repository
    from app.modules.venues import repository as venues_repository

    monkeypatch.setattr(events_repository, "get_event", lambda event_id: deepcopy(row))
    monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: None)
    authenticate_as(role, user_id=user_id)
    return client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers).json()


class TestWhoSeesTheStage:
    """AC4: the assigned coordinator sees the stage and the note; the organiser
    sees the stage only, once the event is Confirmed (AUTH-R2, RD-R2)."""

    @pytest.fixture()
    def row(self):
        from tests.test_event_review_api import event_row

        return {**event_row("preparation"), **RECORDED}

    def as_coordinator(self, client, auth_headers, authenticate_as, monkeypatch, row):
        from tests.test_event_review_api import COORDINATOR_ID

        return read_event(client, auth_headers, authenticate_as, monkeypatch, row, "event_coordinator", COORDINATOR_ID)

    def as_organiser(self, client, auth_headers, authenticate_as, monkeypatch, row):
        from tests.test_event_review_api import ORGANISER_ID

        return read_event(client, auth_headers, authenticate_as, monkeypatch, row, "event_organiser", ORGANISER_ID)

    def test_the_coordinator_sees_the_stage_and_the_note(self, client, auth_headers, authenticate_as, monkeypatch, row):
        body = self.as_coordinator(client, auth_headers, authenticate_as, monkeypatch, row)

        assert body["technical_preparation"] == {
            "stage": "in_progress", "note": "Cables run",
            "updated_at": "2026-10-26T03:00:00Z", "updated_by_name": "Tan Wei",
        }

    def test_the_coordinator_still_sees_a_kept_stage_after_a_return_to_planning(
        self, client, auth_headers, authenticate_as, monkeypatch, row
    ):
        """Q9: the stage and note are kept, only updating is locked."""
        row["status"] = "planning"
        monkeypatch.setattr("app.modules.venues.service.booking_readiness_by_event", lambda event_ids: {})

        body = self.as_coordinator(client, auth_headers, authenticate_as, monkeypatch, row)

        assert body["technical_preparation"]["stage"] == "in_progress"

    @pytest.mark.parametrize("status", ["confirmed", "preparation"])
    def test_the_organiser_sees_the_stage_without_the_note(
        self, client, auth_headers, authenticate_as, monkeypatch, row, status
    ):
        row["status"] = status

        body = self.as_organiser(client, auth_headers, authenticate_as, monkeypatch, row)

        assert body["technical_preparation"] == {"stage": "in_progress", "updated_at": "2026-10-26T03:00:00Z"}

    def test_the_organiser_sees_not_started_before_the_first_update(
        self, client, auth_headers, authenticate_as, monkeypatch, row
    ):
        row.update(status="confirmed", preparation_record=None)

        body = self.as_organiser(client, auth_headers, authenticate_as, monkeypatch, row)

        assert body["technical_preparation"] == {"stage": "not_started", "updated_at": None}

    @pytest.mark.parametrize("status", ["planning", "safety_review", "cancelled"])
    def test_the_organiser_sees_no_stage_outside_confirmed_and_preparation(
        self, client, auth_headers, authenticate_as, monkeypatch, row, status
    ):
        row["status"] = status

        body = self.as_organiser(client, auth_headers, authenticate_as, monkeypatch, row)

        assert body["technical_preparation"] is None

    def test_the_organiser_keeps_the_arrangements_once_in_preparation(
        self, client, auth_headers, authenticate_as, monkeypatch, row
    ):
        """Q10: moving to Preparation must not hide the confirmed venue booking."""
        seen = []
        monkeypatch.setattr("app.modules.venues.service.active_booking_for_event",
                            lambda event_id: seen.append(event_id))

        self.as_organiser(client, auth_headers, authenticate_as, monkeypatch, row)

        assert seen == [EVENT_ID]
