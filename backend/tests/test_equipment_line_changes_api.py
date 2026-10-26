"""SCRUM-44 modify or remove equipment request lines, through the HTTP API with the repository mocked.

The database functions lock the event and the line, re-check the event's status,
the assignment and the line's status, and write the line, its reservation, the
exit tick, history and Technical Support's notices; that is checked against the
real project by supabase/verification/equipment_line_change_checks.sql and
verify_live.py. Here: routing, validation (AC2), the Planning-only refusal
(AC4), the stale-line refusal that settles a race with a reservation (AC6), who
may act (AC7), outcome-to-status mapping, the history the coordinator now sees
(AC8) and a Supabase outage answering 503.
"""

from copy import deepcopy

import httpx
import pytest

from app.modules.equipment import repository
from app.modules.events import service as events_service
from tests.test_equipment_reservation_api import (
    COORDINATOR_ID,
    EVENT_ID,
    LINE_ID,
    PROJECTOR_ID,
    UNKNOWN_LINE,
    line_row,
)

OTHER_COORDINATOR_ID = "a0000000-0000-4000-8000-000000000009"
MIC_ID = "b0000000-0000-4000-8000-000000000002"

LINE_URL = f"/api/v1/equipment/requests/{LINE_ID}"
HISTORY_URL = f"/api/v1/equipment/requests/event/{EVENT_ID}/history"
PLANNING_ONLY = "Equipment can only be changed while the event is in Planning."
STALE = "This line changed while you were editing it. Reload to see its current status."

OTHER_ROLES = ["event_organiser", "event_coordinator_lead", "venue_staff", "tech_support",
               "safety_officer", "attendee"]


def event_row(status="planning", coordinator_id=COORDINATOR_ID):
    return {"id": EVENT_ID, "status": status, "coordinator_id": coordinator_id, "technical_readiness": "pending"}


def change(**overrides):
    body = {"equipment_id": PROJECTOR_ID, "quantity": 4, "technical_requirements": "HDMI", "expected_status": "pending"}
    body.update(overrides)
    return body


@pytest.fixture()
def store(monkeypatch):
    """Canned database answers, and every call the service makes."""
    state = {
        "line": {"id": LINE_ID, "event_id": EVENT_ID, "status": "pending"},
        "event": event_row(),
        "catalogue": [{"id": PROJECTOR_ID, "name": "4K Projector"}, {"id": MIC_ID, "name": "Wireless Mic"}],
        "lines": [line_row()],
        "history": [],
        "update": ("ok", "pending"),
        "remove": "ok",
        "calls": [],
    }

    def record(name):
        def _record(*args):
            state["calls"].append((name, *args))
            return state[name]
        return _record

    def assigned_event(event_id, coordinator_id):
        # The real rule (events.service._assigned_event) against the canned row.
        row = state["event"]
        if event_id != EVENT_ID or row["status"] == "draft":
            raise events_service.EventNotFoundError()
        if row["coordinator_id"] != coordinator_id:
            from app.core.exceptions import NotAssignedCoordinatorError
            raise NotAssignedCoordinatorError()
        return deepcopy(row)

    monkeypatch.setattr(repository, "get_line",
                        lambda line_id: deepcopy(state["line"]) if line_id == LINE_ID and state["line"] else None)
    monkeypatch.setattr(repository, "list_catalogue",
                        lambda ids=None: [row for row in state["catalogue"] if ids is None or row["id"] in set(ids)])
    monkeypatch.setattr(repository, "update_line", record("update"))
    monkeypatch.setattr(repository, "remove_line", record("remove"))
    monkeypatch.setattr(repository, "list_event_requests", lambda event_id: deepcopy(state["lines"]))
    monkeypatch.setattr(repository, "list_technical_history", lambda event_id: deepcopy(state["history"]))
    monkeypatch.setattr(repository, "get_event_technical", lambda event_id: None)
    monkeypatch.setattr(events_service, "assigned_event", assigned_event)
    return state


@pytest.fixture()
def coordinator(authenticate_as):
    authenticate_as("event_coordinator", user_id=COORDINATOR_ID)


def patch(client, headers, body):
    return client.patch(LINE_URL, headers=headers, json=body)


def delete(client, headers, expected_status="pending", url=LINE_URL):
    return client.delete(url, headers=headers, params={"expected_status": expected_status})


class TestChangeLine:
    """AC2, AC3: the assigned coordinator changes a line's item, quantity or
    requirements; the database decides the line's next status."""

    def test_a_change_is_sent_as_the_caller_and_answers_the_new_status(self, client, auth_headers, store, coordinator):
        response = patch(client, auth_headers, change())

        assert response.status_code == 200
        assert response.json() == {"line_id": LINE_ID, "status": "pending", "free_quantity": None}
        assert store["calls"] == [("update", LINE_ID, COORDINATOR_ID, PROJECTOR_ID, 4, "HDMI", "pending")]

    def test_a_reserved_line_comes_back_for_re_review(self, client, auth_headers, store, coordinator):
        store["line"]["status"] = "reserved"
        store["update"] = ("ok", "re_review")

        response = patch(client, auth_headers, change(expected_status="reserved"))

        assert response.json()["status"] == "re_review"
        assert store["calls"][0][-1] == "reserved"

    def test_a_not_available_line_returns_to_pending(self, client, auth_headers, store, coordinator):
        store["line"]["status"] = "rejected"
        store["update"] = ("ok", "pending")

        assert patch(client, auth_headers, change(expected_status="rejected")).json()["status"] == "pending"

    def test_nothing_changed_still_answers_the_line_status(self, client, auth_headers, store, coordinator):
        store["update"] = ("unchanged", "pending")

        response = patch(client, auth_headers, change())

        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    def test_blank_requirements_are_sent_as_none(self, client, auth_headers, store, coordinator):
        patch(client, auth_headers, change(technical_requirements="   "))

        assert store["calls"][0][5] is None

    def test_requirements_are_trimmed(self, client, auth_headers, store, coordinator):
        patch(client, auth_headers, change(technical_requirements="  HDMI cable  "))

        assert store["calls"][0][5] == "HDMI cable"

    def test_a_different_item_from_the_catalogue_is_accepted(self, client, auth_headers, store, coordinator):
        response = patch(client, auth_headers, change(equipment_id=MIC_ID))

        assert response.status_code == 200
        assert store["calls"][0][3] == MIC_ID

    def test_a_quantity_above_total_inventory_is_accepted(self, client, auth_headers, store, coordinator):
        # AC2 with 45 AC2 (EQ-R1): the warning is the screen's; the API accepts it.
        assert patch(client, auth_headers, change(quantity=500)).status_code == 200

    def test_an_item_not_in_the_catalogue_is_422_without_calling_the_database(
        self, client, auth_headers, store, coordinator
    ):
        store["catalogue"] = [{"id": PROJECTOR_ID, "name": "4K Projector"}]

        response = patch(client, auth_headers, change(equipment_id=MIC_ID))

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "equipment_id"]
        assert store["calls"] == []

    def test_an_item_retired_while_editing_is_422(self, client, auth_headers, store, coordinator):
        store["update"] = ("unknown_equipment", None)

        response = patch(client, auth_headers, change())

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "equipment_id"]

    @pytest.mark.parametrize("quantity", [0, -1, 1.5, "2", True, None, 2_147_483_648])
    def test_quantity_must_be_a_whole_number_of_at_least_1(self, client, auth_headers, store, coordinator, quantity):
        response = patch(client, auth_headers, change(quantity=quantity))

        assert response.status_code == 422
        assert store["calls"] == []

    def test_requirements_over_1000_characters_are_422(self, client, auth_headers, store, coordinator):
        assert patch(client, auth_headers, change(technical_requirements="x" * 1001)).status_code == 422

    def test_requirements_of_exactly_1000_characters_are_accepted(self, client, auth_headers, store, coordinator):
        assert patch(client, auth_headers, change(technical_requirements="x" * 1000)).status_code == 200

    @pytest.mark.parametrize("expected_status", ["released", "", "approved", None])
    def test_the_expected_status_must_be_a_live_line_status(
        self, client, auth_headers, store, coordinator, expected_status
    ):
        assert patch(client, auth_headers, change(expected_status=expected_status)).status_code == 422

    def test_a_missing_field_is_422(self, client, auth_headers, store, coordinator):
        body = change()
        del body["equipment_id"]

        assert patch(client, auth_headers, body).status_code == 422


class TestRemoveLine:
    """AC1: the assigned coordinator removes a line of any live status."""

    @pytest.mark.parametrize("line_status", ["pending", "reserved", "re_review", "rejected"])
    def test_removing_a_line_releases_it(self, client, auth_headers, store, coordinator, line_status):
        store["line"]["status"] = line_status

        response = delete(client, auth_headers, line_status)

        assert response.status_code == 200
        assert response.json() == {"line_id": LINE_ID, "status": "released", "free_quantity": None}
        assert store["calls"] == [("remove", LINE_ID, COORDINATOR_ID, line_status)]

    def test_the_expected_status_is_required(self, client, auth_headers, store, coordinator):
        assert client.delete(LINE_URL, headers=auth_headers).status_code == 422
        assert store["calls"] == []

    def test_an_already_removed_line_cannot_be_named_as_expected(self, client, auth_headers, store, coordinator):
        assert delete(client, auth_headers, "released").status_code == 422


class TestPlanningOnly:
    """AC4: refused unless the event is in Planning, whichever way the event left it."""

    @pytest.mark.parametrize("event_status", [
        "submitted", "under_review", "returned", "safety_review", "confirmed", "preparation",
        "completed", "rejected", "cancelled",
    ])
    def test_a_change_outside_planning_is_refused(self, client, auth_headers, store, coordinator, event_status):
        store["event"]["status"] = event_status

        response = patch(client, auth_headers, change())

        assert response.status_code == 409
        assert response.json()["detail"] == PLANNING_ONLY
        assert store["calls"] == []

    @pytest.mark.parametrize("event_status", ["safety_review", "confirmed", "returned"])
    def test_a_removal_outside_planning_is_refused(self, client, auth_headers, store, coordinator, event_status):
        store["event"]["status"] = event_status

        response = delete(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == PLANNING_ONLY
        assert store["calls"] == []

    def test_an_event_that_left_planning_after_the_check_is_refused(self, client, auth_headers, store, coordinator):
        store["update"] = ("not_planning", None)
        store["remove"] = "not_planning"

        assert patch(client, auth_headers, change()).json()["detail"] == PLANNING_ONLY
        assert delete(client, auth_headers).json()["detail"] == PLANNING_ONLY


class TestRace:
    """AC6: a reservation and an edit or removal of the same line can't both
    land. Each names the status it saw; the database refuses a stale one."""

    def test_a_line_reserved_meanwhile_refuses_the_change(self, client, auth_headers, store, coordinator):
        store["update"] = ("stale", None)

        response = patch(client, auth_headers, change())

        assert response.status_code == 409
        assert response.json()["detail"] == STALE

    def test_a_line_reserved_meanwhile_refuses_the_removal(self, client, auth_headers, store, coordinator):
        store["remove"] = "stale"

        response = delete(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == STALE

    def test_a_removed_line_cannot_be_changed(self, client, auth_headers, store, coordinator):
        store["line"]["status"] = "released"

        response = patch(client, auth_headers, change())

        assert response.status_code == 409
        assert response.json()["detail"] == STALE
        assert store["calls"] == []

    def test_a_removed_line_cannot_be_removed_again(self, client, auth_headers, store, coordinator):
        store["line"]["status"] = "released"

        assert delete(client, auth_headers).status_code == 409
        assert store["calls"] == []


class TestWhoMayChange:
    """AC7, SCRUM-76: only the assigned coordinator, acting as coordinator."""

    @pytest.mark.parametrize("role", OTHER_ROLES)
    def test_other_active_roles_are_forbidden(self, client, auth_headers, store, authenticate_as, role):
        authenticate_as(role, user_id=COORDINATOR_ID)

        assert patch(client, auth_headers, change()).status_code == 403
        assert delete(client, auth_headers).status_code == 403
        assert store["calls"] == []

    def test_a_coordinator_holder_acting_as_another_role_is_forbidden(
        self, client, auth_headers, store, monkeypatch
    ):
        # The assigned coordinator also holds tech_support; acting as tech
        # support they can't edit, even though they hold the coordinator role.
        from tests.test_event_comments_api import acting_as_another_role

        acting_as_another_role(monkeypatch, COORDINATOR_ID, holds="event_coordinator", acts_as="tech_support")

        assert patch(client, auth_headers, change()).status_code == 403
        assert delete(client, auth_headers).status_code == 403
        assert store["calls"] == []

    def test_a_coordinator_not_assigned_to_the_event_is_forbidden(
        self, client, auth_headers, store, authenticate_as
    ):
        authenticate_as("event_coordinator", user_id=OTHER_COORDINATOR_ID)

        assert patch(client, auth_headers, change()).status_code == 403
        assert delete(client, auth_headers).status_code == 403
        assert store["calls"] == []

    def test_a_reassignment_after_the_check_is_forbidden(self, client, auth_headers, store, coordinator):
        store["update"] = ("not_assigned", None)
        store["remove"] = "not_assigned"

        assert patch(client, auth_headers, change()).status_code == 403
        assert delete(client, auth_headers).status_code == 403

    def test_an_unknown_line_is_404(self, client, auth_headers, store, coordinator):
        url = f"/api/v1/equipment/requests/{UNKNOWN_LINE}"

        assert client.patch(url, headers=auth_headers, json=change()).status_code == 404
        assert delete(client, auth_headers, url=url).status_code == 404

    def test_a_line_gone_by_the_time_the_database_looks_is_404(self, client, auth_headers, store, coordinator):
        store["update"] = ("line_not_found", None)
        store["remove"] = "line_not_found"

        assert patch(client, auth_headers, change()).status_code == 404
        assert delete(client, auth_headers).status_code == 404

    def test_a_line_on_a_draft_is_404(self, client, auth_headers, store, coordinator):
        store["event"]["status"] = "draft"

        assert patch(client, auth_headers, change()).status_code == 404

    def test_no_token_is_401(self, client, store):
        assert client.patch(LINE_URL, json=change()).status_code == 401
        assert client.delete(LINE_URL, params={"expected_status": "pending"}).status_code == 401


class TestOutage:
    @pytest.mark.parametrize("name", ["update_line", "remove_line"])
    def test_a_supabase_outage_is_503(self, client, auth_headers, store, coordinator, monkeypatch, name):
        def down(*args):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(repository, name, down)

        response = patch(client, auth_headers, change()) if name == "update_line" else delete(client, auth_headers)

        assert response.status_code == 503

    def test_an_unexpected_outcome_is_not_reported_as_success(self, client, auth_headers, store, coordinator):
        store["remove"] = "surprise"

        with pytest.raises(RuntimeError):
            delete(client, auth_headers)


class TestCoordinatorSeesHistory:
    """AC8: the assigned coordinator reads the event's equipment history, where a
    removed line stays visible."""

    def test_the_history_names_the_removed_line_who_and_when(self, client, auth_headers, store, coordinator):
        store["history"] = [{
            "action": "removed", "from_status": "reserved", "to_status": "released",
            "detail": "Removed 3 × 4K Projector.", "created_at": "2026-10-26T02:00:00+00:00",
            "actor": {"full_name": "Marcus Lim"},
            "line": {"quantity": 3, "equipment": {"name": "4K Projector"}},
        }]

        response = client.get(HISTORY_URL, headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {"history": [{
            "action": "removed", "line_label": "3 × 4K Projector", "from_status": "reserved",
            "to_status": "released", "detail": "Removed 3 × 4K Projector.", "actor_name": "Marcus Lim",
            "created_at": "2026-10-26T02:00:00Z",
        }]}

    def test_another_coordinator_is_forbidden(self, client, auth_headers, store, authenticate_as):
        authenticate_as("event_coordinator", user_id=OTHER_COORDINATOR_ID)

        assert client.get(HISTORY_URL, headers=auth_headers).status_code == 403

    @pytest.mark.parametrize("role", OTHER_ROLES)
    def test_other_active_roles_are_forbidden(self, client, auth_headers, store, authenticate_as, role):
        authenticate_as(role, user_id=COORDINATOR_ID)

        assert client.get(HISTORY_URL, headers=auth_headers).status_code == 403

    def test_a_draft_is_404(self, client, auth_headers, store, coordinator):
        store["event"]["status"] = "draft"

        assert client.get(HISTORY_URL, headers=auth_headers).status_code == 404
