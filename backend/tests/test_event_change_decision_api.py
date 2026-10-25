"""Story 37: the assigned coordinator approves or rejects the organiser's open change
request, through the HTTP API with the repository mocked. The RPCs' own guards, moves
and markers are checked against the real database by
supabase/verification/change_request_decision_checks.sql."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.modules.events import repository
from tests.conftest import make_table_mock

ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_COORDINATOR_ID = "a0000000-0000-4000-8000-000000000009"
EVENT_ID = "e0000000-0000-4000-8000-000000000371"
REQUEST_ID = "c0000000-0000-4000-8000-000000000371"
REQUEST_REASON = "More guests confirmed"
REJECTION_REASON = "The venue can't take more people"
FUTURE_START = "2026-11-12T10:00:00+08:00"


def event_row(status="confirmed", starts_at=FUTURE_START):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": COORDINATOR_ID,
        "status": status, "event_timezone": "Asia/Singapore", "name": "Partner Summit",
        "purpose": "Quarterly partner meeting", "description": None,
        "starts_at": starts_at, "ends_at": "2026-11-12T12:00:00+08:00",
        "expected_attendance": 80, "layout_preference": "theatre", "facilities_required": [],
        "accessibility_needs": None, "preliminary_equipment_needs": None,
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "technical_readiness": "not_required", "submitted_at": now, "version": 3,
        "created_at": now, "updated_at": now,
    }


OPEN_REQUEST = {
    "id": REQUEST_ID, "kind": "change", "status": "open", "reason": REQUEST_REASON,
    "changes": {"event": [{"field": "expected_attendance", "before": 80, "after": 120}], "spaces": []},
    "significant": True,
    "requested_by": {"id": ORGANISER_ID, "full_name": "Olivia Organiser"},
    "requested_at": "2026-10-24T09:00:00+00:00",
}


@pytest.fixture()
def events(monkeypatch):
    """An in-memory event with its open change request."""
    store = {EVENT_ID: event_row()}
    request = {"value": deepcopy(OPEN_REQUEST)}
    monkeypatch.setattr(repository, "get_event", lambda event_id: deepcopy(store.get(event_id)))
    monkeypatch.setattr(repository, "get_open_change_request", lambda event_id: deepcopy(request["value"]))
    return {"store": store, "request": request}


@pytest.fixture()
def rejections(monkeypatch, events):
    """A fake `reject_event_change` that answers like the RPC."""
    calls = []
    outcome = {"value": "ok"}

    def reject_event_change(event_id, actor_id, reason, from_statuses, organiser_message):
        calls.append({"event_id": event_id, "actor_id": actor_id, "reason": reason,
                      "from_statuses": from_statuses, "organiser_message": organiser_message})
        return {"outcome": outcome["value"]}

    monkeypatch.setattr(repository, "reject_event_change", reject_event_change)
    return {"calls": calls, "outcome": outcome}


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role="event_coordinator", user_id=COORDINATOR_ID):
        return authenticate_as(role, user_id=user_id)
    return _act_as


def reject(client, auth_headers, reason=REJECTION_REASON):
    return client.post(f"/api/v1/events/{EVENT_ID}/change-request/reject",
                       json={"reason": reason}, headers=auth_headers)


class TestRejectChangeRequest:
    def test_rejecting_keeps_the_event_as_it_was(self, client, auth_headers, act_as, events, rejections):
        act_as()

        response = reject(client, auth_headers)

        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
        assert response.json()["expected_attendance"] == 80
        [call] = rejections["calls"]
        assert call["event_id"] == EVENT_ID
        assert call["actor_id"] == COORDINATOR_ID
        assert call["reason"] == REJECTION_REASON

    def test_the_rpc_rechecks_the_decidable_statuses(self, client, auth_headers, act_as, events, rejections):
        """AC8: the RPC refuses under the lock if the event moved to a closed status."""
        act_as()

        reject(client, auth_headers)

        assert rejections["calls"][0]["from_statuses"] == [
            "confirmed", "planning", "preparation", "safety_review", "submitted", "under_review"]

    def test_the_organiser_is_told_why(self, client, auth_headers, act_as, events, rejections):
        """AC4, CR-R3."""
        act_as()

        reject(client, auth_headers)

        assert rejections["calls"][0]["organiser_message"] == (
            f'Your requested changes to "Partner Summit" were rejected: {REJECTION_REASON}')

    def test_the_reason_is_trimmed(self, client, auth_headers, act_as, events, rejections):
        act_as()

        reject(client, auth_headers, reason=f"  {REJECTION_REASON}  ")

        assert rejections["calls"][0]["reason"] == REJECTION_REASON

    @pytest.mark.parametrize("reason", ["", "   ", "x" * 1001, None])
    def test_a_missing_blank_or_overlong_reason_is_rejected(self, client, auth_headers, act_as, events,
                                                            rejections, reason):
        """CR-R3."""
        act_as()

        response = reject(client, auth_headers, reason=reason)

        assert response.status_code == 422
        assert rejections["calls"] == []

    def test_without_an_open_request_there_is_nothing_to_reject(self, client, auth_headers, act_as, events,
                                                                rejections):
        events["request"]["value"] = None
        act_as()

        response = reject(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "There is no open change request for this event."
        assert rejections["calls"] == []

    @pytest.mark.parametrize("status", ["completed", "cancelled", "rejected"])
    def test_a_closed_event_takes_no_decision(self, client, auth_headers, act_as, events, rejections, status):
        """AC8: the event and the request stay as they were."""
        events["store"][EVENT_ID]["status"] = status
        act_as()

        response = reject(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"A change request can't be decided on an event that is {status}."
        assert rejections["calls"] == []

    def test_a_started_event_takes_no_decision(self, client, auth_headers, act_as, events, rejections):
        """Q5, as CR-R10."""
        events["store"][EVENT_ID]["starts_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        act_as()

        response = reject(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "This event has already started, so its change request can't be decided."
        assert rejections["calls"] == []

    @pytest.mark.parametrize(("outcome", "status_code", "detail"), [
        ("no_open_request", 409, "There is no open change request for this event."),
        ("not_assigned", 403, None),
        ("not_found", 404, None),
        ("started", 409, "This event has already started, so its change request can't be decided."),
        ("status_changed", 409, "This event was updated by someone else. Reload."),
    ])
    def test_the_rpc_recheck_under_the_lock_decides(self, client, auth_headers, act_as, events, rejections,
                                                    outcome, status_code, detail):
        rejections["outcome"]["value"] = outcome
        act_as()

        response = reject(client, auth_headers)

        assert response.status_code == status_code
        if detail:
            assert response.json()["detail"] == detail


class TestHistoryRecordsTheDecision:
    """Q18: the organiser sees the outcome in the history, with the reason when rejected."""

    @pytest.fixture()
    def history(self, monkeypatch, events):
        monkeypatch.setattr(repository, "list_status_history", lambda event_id: [])
        monkeypatch.setattr(repository, "list_assignment_history", lambda event_id: [])
        monkeypatch.setattr(repository, "list_cancellation_requests", lambda event_id: [])
        monkeypatch.setattr(repository, "list_change_requests", lambda event_id: [
            {**OPEN_REQUEST, "status": "rejected", "decision_reason": REJECTION_REASON,
             "decided_at": "2026-10-25T10:00:00+00:00",
             "decided_by": {"id": COORDINATOR_ID, "full_name": "Cora Coordinator"}},
        ])

    @pytest.mark.parametrize(("role", "user_id"), [("event_organiser", ORGANISER_ID),
                                                    ("event_coordinator", COORDINATOR_ID)])
    def test_a_rejected_change_shows_who_rejected_it_and_why(self, client, auth_headers, act_as, history,
                                                            role, user_id):
        act_as(role, user_id=user_id)

        response = client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers)

        assert response.status_code == 200
        rejected, requested = response.json()["entries"]
        assert rejected == {
            "id": f"{REQUEST_ID}:rejected", "kind": "change_rejected",
            "from_status": None, "to_status": None, "from_coordinator": None, "to_coordinator": None,
            "actor": {"id": COORDINATOR_ID, "full_name": "Cora Coordinator"},
            "reason": REJECTION_REASON, "at": "2026-10-25T10:00:00Z",
        }
        assert requested["kind"] == "change_requested"


DECISIONS = [
    ("reject", reject),
]


class TestOnlyTheAssignedCoordinatorDecides:
    """Q4, SCRUM-76: every decision is the assigned coordinator's, acting as coordinator."""

    @pytest.mark.parametrize(("name", "decide"), DECISIONS)
    def test_another_coordinator_is_forbidden(self, client, auth_headers, act_as, events, rejections,
                                              name, decide):
        act_as(user_id=OTHER_COORDINATOR_ID)

        response = decide(client, auth_headers)

        assert response.status_code == 403
        assert rejections["calls"] == []

    @pytest.mark.parametrize(("name", "decide"), DECISIONS)
    @pytest.mark.parametrize("role", ["event_organiser", "event_coordinator_lead", "venue_staff",
                                      "tech_support", "safety_officer", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, events, rejections,
                                       role, name, decide):
        act_as(role, user_id=COORDINATOR_ID)

        response = decide(client, auth_headers)

        assert response.status_code == 403
        assert rejections["calls"] == []

    @pytest.mark.parametrize(("name", "decide"), DECISIONS)
    def test_a_draft_is_not_found(self, client, auth_headers, act_as, events, rejections, name, decide):
        events["store"][EVENT_ID]["status"] = "draft"
        act_as()

        response = decide(client, auth_headers)

        assert response.status_code == 404
        assert rejections["calls"] == []

    @pytest.mark.parametrize(("name", "decide"), DECISIONS)
    def test_the_coordinator_acting_as_another_role_is_forbidden(self, client, auth_headers, monkeypatch,
                                                                 events, rejections, name, decide):
        """The assigned coordinator's account also holds organiser and is acting as it."""
        profile = {"id": COORDINATOR_ID, "email": "multi@connectsphere.dev", "full_name": "Multi Role",
                   "role": "event_coordinator", "organisation_name": None, "department": None,
                   "phone_number": None}
        anon = MagicMock()
        anon.auth.get_claims.return_value = {"claims": {
            "sub": COORDINATOR_ID, "aud": "authenticated", "email": profile["email"],
            "session_id": "33333333-3333-3333-3333-333333333333"}}
        monkeypatch.setattr("app.core.security.get_supabase_anon_client", lambda: anon)
        monkeypatch.setattr("app.core.security.get_supabase_admin_client",
                            lambda: make_table_mock(profile, session_active_role={"role": "event_organiser"}))

        response = decide(client, auth_headers)

        assert response.status_code == 403
        assert rejections["calls"] == []
