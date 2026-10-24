"""Story 84: the organiser requests cancellation of their event, through the HTTP API
with the repository mocked. The RPC's own guards are checked against the real
database by supabase/verification/event_cancellation_request_checks.sql."""

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.modules.equipment import service as equipment_service
from app.modules.events import repository
from app.modules.venues import repository as venues_repository
from app.modules.venues import service as venues_service
from tests.conftest import make_table_mock

ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_ORGANISER_ID = "a0000000-0000-4000-8000-000000000003"
EVENT_ID = "e0000000-0000-4000-8000-000000000841"
OTHER_EVENT_ID = "e0000000-0000-4000-8000-000000000842"
MISSING_EVENT_ID = "e0000000-0000-4000-8000-0000000008ff"
REQUEST_ID = "c0000000-0000-4000-8000-000000000841"
REASON = "Our keynote speaker has withdrawn"


def event_row(status="planning", coordinator_id=COORDINATOR_ID):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": coordinator_id,
        "status": status, "event_timezone": "Asia/Singapore", "name": "Partner Summit",
        "purpose": "Quarterly partner meeting", "description": None,
        "starts_at": "2026-11-12T10:00:00+08:00", "ends_at": "2026-11-12T12:00:00+08:00",
        "expected_attendance": 12, "layout_preference": "boardroom", "facilities_required": [],
        "accessibility_needs": None, "preliminary_equipment_needs": None,
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "technical_readiness": "not_required", "submitted_at": now, "version": 3,
        "created_at": now, "updated_at": now,
    }


@pytest.fixture()
def events(monkeypatch):
    """An in-memory events table plus a fake request_event_cancellation that answers
    like the RPC: ok with the new request, or an outcome code."""
    store = {EVENT_ID: event_row()}
    calls = []
    outcome = {"value": "ok"}

    def get_event(event_id):
        return deepcopy(store.get(event_id))

    def request_event_cancellation(event_id, actor_id, reason, from_statuses,
                                   coordinator_message, lead_message):
        calls.append({
            "event_id": event_id, "actor_id": actor_id, "reason": reason,
            "from_statuses": from_statuses, "coordinator_message": coordinator_message,
            "lead_message": lead_message,
        })
        if outcome["value"] != "ok":
            return {"outcome": outcome["value"], "request": None}
        return {"outcome": "ok", "request": {
            "id": REQUEST_ID, "kind": "cancellation", "status": "open", "reason": reason,
            "requested_by": {"id": actor_id, "full_name": "Test event_organiser"},
            "requested_at": "2026-10-23T09:00:00+00:00",
        }}

    monkeypatch.setattr(repository, "get_event", get_event)
    monkeypatch.setattr(repository, "request_event_cancellation", request_event_cancellation)
    return {"store": store, "calls": calls, "outcome": outcome}


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role="event_organiser", user_id=ORGANISER_ID):
        return authenticate_as(role, user_id=user_id)
    return _act_as


def request_cancellation(client, auth_headers, reason=REASON, event_id=EVENT_ID):
    return client.post(f"/api/v1/events/{event_id}/cancellation-request",
                       json={"reason": reason}, headers=auth_headers)


class TestRequestCancellation:
    def test_owner_records_an_open_cancellation_request(self, client, auth_headers, act_as, events):
        act_as()

        response = request_cancellation(client, auth_headers)

        assert response.status_code == 201
        assert response.json() == {
            "id": REQUEST_ID, "kind": "cancellation", "status": "open", "reason": REASON,
            "requested_by": {"id": ORGANISER_ID, "full_name": "Test event_organiser"},
            "requested_at": "2026-10-23T09:00:00Z",
        }
        [call] = events["calls"]
        assert call["event_id"] == EVENT_ID
        assert call["actor_id"] == ORGANISER_ID
        assert call["reason"] == REASON

    @pytest.mark.parametrize("status", ["submitted", "under_review", "returned", "planning",
                                        "safety_review", "confirmed", "preparation"])
    def test_every_status_after_submission_accepts_a_request(self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as()

        response = request_cancellation(client, auth_headers)

        assert response.status_code == 201

    def test_the_rpc_rechecks_every_status_but_the_refused_ones(self, client, auth_headers, act_as, events):
        act_as()

        request_cancellation(client, auth_headers)

        [call] = events["calls"]
        assert "draft" not in call["from_statuses"]
        assert {"rejected", "cancelled", "completed"}.isdisjoint(call["from_statuses"])
        assert {"submitted", "under_review", "returned", "planning", "safety_review",
                "confirmed", "preparation"} <= set(call["from_statuses"])

    def test_the_reason_is_trimmed(self, client, auth_headers, act_as, events):
        act_as()

        request_cancellation(client, auth_headers, reason=f"  {REASON}  ")

        assert events["calls"][0]["reason"] == REASON

    def test_the_coordinator_is_told_who_asked_and_why(self, client, auth_headers, act_as, events):
        act_as()

        request_cancellation(client, auth_headers)

        call = events["calls"][0]
        assert call["coordinator_message"] == (
            f'Test event_organiser requested to cancel "Partner Summit". Reason: {REASON}')
        assert call["lead_message"] == 'Cancellation requested for unassigned event "Partner Summit".'


class TestRefusedRequests:
    @pytest.mark.parametrize("status", ["rejected", "cancelled", "completed"])
    def test_a_closed_event_cannot_have_a_request(self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as()

        response = request_cancellation(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Cancellation can't be requested for an event that is {status}."
        assert events["calls"] == []

    def test_a_draft_is_discarded_instead(self, client, auth_headers, act_as, events):
        events["store"][EVENT_ID]["status"] = "draft"
        act_as()

        response = request_cancellation(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "A draft can't be cancelled. Discard the draft instead."
        assert events["calls"] == []

    def test_a_second_open_request_is_refused(self, client, auth_headers, act_as, events):
        events["outcome"]["value"] = "already_open"
        act_as()

        response = request_cancellation(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "A cancellation request is already open for this event."

    def test_an_event_that_moved_on_under_the_lock_is_a_conflict(self, client, auth_headers, act_as, events):
        events["outcome"]["value"] = "status_changed"
        act_as()

        response = request_cancellation(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "This event was updated by someone else. Reload."

    @pytest.mark.parametrize("outcome", ["not_found", "not_owner"])
    def test_an_event_gone_or_changed_hands_under_the_lock_is_not_found(self, client, auth_headers, act_as,
                                                                       events, outcome):
        events["outcome"]["value"] = outcome
        act_as()

        response = request_cancellation(client, auth_headers)

        assert response.status_code == 404

    @pytest.mark.parametrize("reason", ["", "   ", "x" * 1001, None])
    def test_a_missing_blank_or_overlong_reason_is_rejected(self, client, auth_headers, act_as, events, reason):
        act_as()

        response = request_cancellation(client, auth_headers, reason=reason)

        assert response.status_code == 422
        assert events["calls"] == []


class TestWhoCanRequest:
    def test_another_organiser_gets_not_found(self, client, auth_headers, act_as, events):
        act_as(user_id=OTHER_ORGANISER_ID)

        response = request_cancellation(client, auth_headers)

        assert response.status_code == 404
        assert events["calls"] == []

    def test_a_missing_event_is_not_found(self, client, auth_headers, act_as, events):
        act_as()

        response = request_cancellation(client, auth_headers, event_id=MISSING_EVENT_ID)

        assert response.status_code == 404

    @pytest.mark.parametrize("role", ["event_coordinator", "event_coordinator_lead", "venue_staff",
                                      "tech_support", "safety_officer", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, events, role):
        act_as(role, user_id=COORDINATOR_ID)

        response = request_cancellation(client, auth_headers)

        assert response.status_code == 403
        assert events["calls"] == []

    def test_the_owner_acting_as_another_role_is_forbidden(self, client, auth_headers, monkeypatch, events):
        """SCRUM-76: the owner's account also holds coordinator and is acting as it."""
        profile = {"id": ORGANISER_ID, "email": "multi@connectsphere.dev", "full_name": "Multi Role",
                   "role": "event_organiser", "organisation_name": None, "department": None,
                   "phone_number": None}
        anon = MagicMock()
        anon.auth.get_claims.return_value = {"claims": {
            "sub": ORGANISER_ID, "aud": "authenticated", "email": profile["email"],
            "session_id": "22222222-2222-2222-2222-222222222222"}}
        monkeypatch.setattr("app.core.security.get_supabase_anon_client", lambda: anon)
        monkeypatch.setattr("app.core.security.get_supabase_admin_client",
                            lambda: make_table_mock(profile, session_active_role={"role": "event_coordinator"}))

        response = request_cancellation(client, auth_headers)

        assert response.status_code == 403
        assert events["calls"] == []


OPEN_REQUEST = {
    "id": REQUEST_ID, "kind": "cancellation", "status": "open", "reason": REASON,
    "requested_by": {"id": ORGANISER_ID, "full_name": "Olivia Organiser"},
    "requested_at": "2026-10-23T09:00:00+00:00",
}


@pytest.fixture()
def open_request(monkeypatch, events):
    """The event's open cancellation request as the repository returns it (None: no request)."""
    current = {"value": deepcopy(OPEN_REQUEST)}
    monkeypatch.setattr(repository, "get_open_cancellation_request", lambda event_id: deepcopy(current["value"]))
    return current


class TestEventDetailShowsTheOpenRequest:
    def test_the_owner_sees_their_open_request(self, client, auth_headers, act_as, open_request):
        act_as()

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["open_cancellation_request"] == {
            **OPEN_REQUEST, "requested_at": "2026-10-23T09:00:00Z"}

    def test_the_assigned_coordinator_sees_it_too(self, client, auth_headers, act_as, open_request, monkeypatch):
        monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: None)
        monkeypatch.setattr(venues_repository, "list_booking_statuses", lambda event_ids: [])
        act_as("event_coordinator", user_id=COORDINATOR_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["open_cancellation_request"]["reason"] == REASON

    def test_no_open_request_reads_as_null(self, client, auth_headers, act_as, open_request):
        open_request["value"] = None
        act_as()

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.json()["open_cancellation_request"] is None


class TestHistoryRecordsTheRequest:
    @pytest.fixture()
    def history(self, monkeypatch, events):
        monkeypatch.setattr(repository, "list_status_history", lambda event_id: [
            {"id": "h2", "from_status": "under_review", "to_status": "planning", "reason": None,
             "at": "2026-10-20T09:00:00+00:00", "actor": {"id": COORDINATOR_ID, "full_name": "Cora Coordinator"}},
        ])
        monkeypatch.setattr(repository, "list_assignment_history", lambda event_id: [])
        monkeypatch.setattr(repository, "list_cancellation_requests", lambda event_id: [
            {"id": REQUEST_ID, "reason": REASON, "requested_at": "2026-10-23T09:00:00+00:00",
             "requested_by": {"id": ORGANISER_ID, "full_name": "Olivia Organiser"}},
        ])

    @pytest.mark.parametrize(("role", "user_id"), [("event_organiser", ORGANISER_ID),
                                                    ("event_coordinator", COORDINATOR_ID)])
    def test_the_request_is_the_newest_entry_with_who_why_and_when(self, client, auth_headers, act_as,
                                                                   history, role, user_id):
        act_as(role, user_id=user_id)

        response = client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers)

        assert response.status_code == 200
        first, second = response.json()["entries"]
        assert first == {
            "id": REQUEST_ID, "kind": "cancellation_requested", "from_status": None, "to_status": None,
            "from_coordinator": None, "to_coordinator": None,
            "actor": {"id": ORGANISER_ID, "full_name": "Olivia Organiser"},
            "reason": REASON, "at": "2026-10-23T09:00:00Z",
        }
        assert second["id"] == "h2"


class TestCoordinatorDashboardListsTheRequest:
    @pytest.fixture()
    def dashboard_data(self, monkeypatch):
        rows = [
            {"id": EVENT_ID, "name": "Partner Summit", "status": "confirmed",
             "starts_at": "2026-11-12T10:00:00+08:00", "submitted_at": "2026-09-20T09:00:00+08:00",
             "technical_readiness": "not_required", "preliminary_equipment_needs": None,
             "organiser": {"full_name": "Olivia Organiser"}},
            {"id": OTHER_EVENT_ID, "name": "Year-End Dinner", "status": "planning",
             "starts_at": "2026-12-12T19:00:00+08:00", "submitted_at": "2026-09-21T09:00:00+08:00",
             "technical_readiness": "not_required", "preliminary_equipment_needs": None,
             "organiser": {"full_name": "Olivia Organiser"}},
        ]
        asked = {}

        def open_requests(event_ids):
            asked["ids"] = list(event_ids)
            return {EVENT_ID: "2026-10-23T09:00:00+00:00"}

        monkeypatch.setattr(repository, "list_coordinator_events", lambda coordinator_id, statuses: rows)
        monkeypatch.setattr(repository, "list_latest_resubmissions", lambda ids: {})
        monkeypatch.setattr(repository, "list_open_cancellation_requests", open_requests)
        monkeypatch.setattr(venues_service, "booking_statuses_by_event", lambda ids: {})
        monkeypatch.setattr(venues_service, "affected_event_ids", lambda ids: set())
        monkeypatch.setattr(equipment_service, "equipment_readiness_by_event", lambda ids: {})
        return asked

    def test_an_open_request_is_an_action_item_dated_when_it_was_asked(self, client, auth_headers, act_as,
                                                                        dashboard_data):
        act_as("event_coordinator", user_id=COORDINATOR_ID)

        response = client.get("/api/v1/events/dashboard/coordinator", headers=auth_headers)

        assert response.status_code == 200
        items = [item for item in response.json()["action_items"] if item["kind"] == "cancellation_request"]
        assert items == [{
            "event_id": EVENT_ID, "event_name": "Partner Summit", "kind": "cancellation_request",
            "starts_at": "2026-11-12T10:00:00+08:00", "occurred_at": "2026-10-23T09:00:00Z",
            "organiser_name": "Olivia Organiser",
        }]
        assert set(dashboard_data["ids"]) == {EVENT_ID, OTHER_EVENT_ID}
