"""CR-106: the assigned coordinator asks the Lead to reassign their event, through the
HTTP API with the repository mocked. The RPC's own guards (one open request, recipients,
notifications) are checked against the real database by
supabase/verification/reassignment_request_checks.sql."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.modules.events import repository
from tests.conftest import make_table_mock  # noqa: F401  (shared fixtures live in conftest)

COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_COORDINATOR_ID = "a0000000-0000-4000-8000-000000000004"
ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
EVENT_ID = "e0000000-0000-4000-8000-000000001060"
MISSING_EVENT_ID = "e0000000-0000-4000-8000-0000000010ff"
REQUEST_ID = "c0000000-0000-4000-8000-000000001060"
REASON = "I am on leave for the rest of the month"


def event_row(status="planning", coordinator_id=COORDINATOR_ID):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": coordinator_id,
        "status": status, "event_timezone": "Asia/Singapore", "name": "Partner Summit",
        "purpose": "Quarterly partner meeting", "description": None,
        "starts_at": "2099-11-12T10:00:00+08:00", "ends_at": "2099-11-12T12:00:00+08:00",
        "expected_attendance": 12, "layout_preference": "boardroom", "facilities_required": [],
        "accessibility_needs": None, "preliminary_equipment_needs": None,
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "technical_readiness": "not_required", "submitted_at": now, "version": 3,
        "created_at": now, "updated_at": now,
    }


@pytest.fixture()
def events(monkeypatch):
    """An in-memory events table plus a fake request_reassignment that answers like the
    RPC: ok with the new request, or an outcome code."""
    store = {EVENT_ID: event_row()}
    calls = []
    reassign_calls = []
    outcome = {"value": "ok"}

    def get_event(event_id):
        return deepcopy(store.get(event_id))

    def request_reassignment(event_id, actor_id, reason, active_statuses, lead_message):
        calls.append({
            "event_id": event_id, "actor_id": actor_id, "reason": reason,
            "active_statuses": active_statuses, "lead_message": lead_message,
        })
        if outcome["value"] != "ok":
            return {"outcome": outcome["value"], "request": None}
        return {"outcome": "ok", "request": {
            "id": REQUEST_ID, "kind": "reassignment", "status": "open", "reason": reason,
            "requested_by": {"id": actor_id, "full_name": "Test event_coordinator"},
            "requested_at": "2026-10-27T09:00:00+00:00",
        }}

    def reassign_event(*args, **kwargs):
        reassign_calls.append((args, kwargs))

    monkeypatch.setattr(repository, "get_event", get_event)
    monkeypatch.setattr(repository, "request_reassignment", request_reassignment, raising=False)
    monkeypatch.setattr(repository, "reassign_event", reassign_event)
    return {"store": store, "calls": calls, "reassign_calls": reassign_calls, "outcome": outcome}


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role="event_coordinator", user_id=COORDINATOR_ID):
        return authenticate_as(role, user_id=user_id)
    return _act_as


def request_reassignment(client, auth_headers, reason=REASON, event_id=EVENT_ID):
    return client.post(f"/api/v1/events/{event_id}/reassignment-request",
                       json={"reason": reason}, headers=auth_headers)


class TestRequestReassignment:
    def test_assigned_coordinator_records_an_open_request(self, client, auth_headers, act_as, events):
        """AC1."""
        act_as()

        response = request_reassignment(client, auth_headers)

        assert response.status_code == 201
        assert response.json() == {
            "id": REQUEST_ID, "kind": "reassignment", "status": "open", "reason": REASON,
            "requested_by": {"id": COORDINATOR_ID, "full_name": "Test event_coordinator"},
            "requested_at": "2026-10-27T09:00:00Z",
        }
        [call] = events["calls"]
        assert call["event_id"] == EVENT_ID
        assert call["actor_id"] == COORDINATOR_ID
        assert call["reason"] == REASON

    @pytest.mark.parametrize("status", ["planning", "preparation"])
    def test_an_active_status_accepts_a_request(self, client, auth_headers, act_as, events, status):
        """AC1: an active event is one the Lead can reassign (CR-101), Preparation included
        (QA3-3, D73). The full list is asserted in test_the_rpc_rechecks_the_active_statuses."""
        events["store"][EVENT_ID]["status"] = status
        act_as()

        assert request_reassignment(client, auth_headers).status_code == 201

    @pytest.mark.parametrize("status", ["submitted", "completed"])
    def test_an_event_that_is_not_active_is_refused(self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as()

        response = request_reassignment(client, auth_headers)

        assert response.status_code == 409
        assert events["calls"] == []

    def test_the_rpc_rechecks_the_active_statuses(self, client, auth_headers, act_as, events):
        act_as()

        request_reassignment(client, auth_headers)

        [call] = events["calls"]
        assert set(call["active_statuses"]) == {
            "under_review", "returned", "planning", "safety_review", "confirmed", "preparation"}

    def test_the_reason_is_trimmed(self, client, auth_headers, act_as, events):
        act_as()

        request_reassignment(client, auth_headers, reason=f"  {REASON}  ")

        assert events["calls"][0]["reason"] == REASON

    @pytest.mark.parametrize("reason", ["", "   ", None])
    def test_a_reason_is_required(self, client, auth_headers, act_as, events, reason):
        """AC1."""
        act_as()

        response = request_reassignment(client, auth_headers, reason=reason)

        assert response.status_code == 422
        assert events["calls"] == []

    def test_an_overlong_reason_is_refused(self, client, auth_headers, act_as, events):
        act_as()

        response = request_reassignment(client, auth_headers, reason="x" * 1001)

        assert response.status_code == 422

    def test_the_lead_message_names_the_event_and_the_coordinator(self, client, auth_headers, act_as, events):
        """AC2: the RPC picks the recipients; the API supplies the wording."""
        act_as()

        request_reassignment(client, auth_headers)

        message = events["calls"][0]["lead_message"]
        assert "Partner Summit" in message
        assert "Test event_coordinator" in message
        assert REASON in message

    def test_the_request_changes_nothing_on_its_own(self, client, auth_headers, act_as, events):
        """AC3: the coordinator stays assigned and nobody is reassigned."""
        act_as()
        before = deepcopy(events["store"])

        request_reassignment(client, auth_headers)

        assert events["store"] == before
        assert events["reassign_calls"] == []

    def test_a_second_request_is_refused_while_one_is_open(self, client, auth_headers, act_as, events):
        """AC5."""
        events["outcome"]["value"] = "already_open"
        act_as()

        response = request_reassignment(client, auth_headers)

        assert response.status_code == 409
        assert "already" in response.json()["detail"].lower()

    def test_an_event_that_moved_on_is_a_conflict(self, client, auth_headers, act_as, events):
        events["outcome"]["value"] = "status_changed"
        act_as()

        assert request_reassignment(client, auth_headers).status_code == 409

    @pytest.mark.parametrize("outcome, expected", [("not_found", 404), ("not_assigned", 403)])
    def test_the_rpc_rechecks_who_is_assigned(self, client, auth_headers, act_as, events, outcome, expected):
        events["outcome"]["value"] = outcome
        act_as()

        assert request_reassignment(client, auth_headers).status_code == expected


class TestWhoMayRequest:
    def test_another_coordinator_is_forbidden(self, client, auth_headers, act_as, events):
        """AC7."""
        act_as(user_id=OTHER_COORDINATOR_ID)

        response = request_reassignment(client, auth_headers)

        assert response.status_code == 403
        assert events["calls"] == []

    @pytest.mark.parametrize("role", ["event_organiser", "event_coordinator_lead"])
    def test_other_active_roles_are_forbidden(self, client, auth_headers, act_as, events, role):
        """AC4, AC7: the active role decides, even for the assigned user. A Lead who is also
        this event's coordinator, acting as Lead, gets 403."""
        act_as(role=role)

        response = request_reassignment(client, auth_headers)

        assert response.status_code == 403
        assert events["calls"] == []

    def test_a_draft_is_not_found(self, client, auth_headers, act_as, events):
        events["store"][EVENT_ID]["status"] = "draft"
        act_as()

        assert request_reassignment(client, auth_headers).status_code == 404

    def test_an_unknown_event_is_not_found(self, client, auth_headers, act_as, events):
        act_as()

        assert request_reassignment(client, auth_headers, event_id=MISSING_EVENT_ID).status_code == 404

    def test_an_unassigned_event_is_forbidden(self, client, auth_headers, act_as, events):
        events["store"][EVENT_ID]["coordinator_id"] = None
        act_as()

        assert request_reassignment(client, auth_headers).status_code == 403

    def test_a_missing_token_is_refused(self, client, events):
        response = client.post(f"/api/v1/events/{EVENT_ID}/reassignment-request", json={"reason": REASON})

        assert response.status_code in (401, 403)
        assert events["calls"] == []


class TestNoDirectHandover:
    """AC4: a coordinator can't reassign or hand over directly, even with a raw request."""

    def test_the_coordinator_cannot_reassign(self, client, auth_headers, act_as, events):
        act_as()

        response = client.post(f"/api/v1/events/{EVENT_ID}/reassign", headers=auth_headers, json={
            "coordinator_id": OTHER_COORDINATOR_ID, "expected_version": 3})

        assert response.status_code == 403
        assert events["reassign_calls"] == []

    def test_the_coordinator_cannot_assign(self, client, auth_headers, act_as, events):
        act_as()

        response = client.post(f"/api/v1/events/{EVENT_ID}/assign", headers=auth_headers, json={
            "coordinator_id": OTHER_COORDINATOR_ID})

        assert response.status_code == 403
