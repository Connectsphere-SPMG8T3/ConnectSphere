"""Story 115: the assigned coordinator approves or rejects a cancellation request, or
cancels the event directly, through the HTTP API with the repository mocked. The RPCs'
own guards and releases are checked against the real database by
supabase/verification/event_cancellation_decision_checks.sql."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.events import repository

ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
EVENT_ID = "e0000000-0000-4000-8000-000000001151"
REQUEST_ID = "c0000000-0000-4000-8000-000000001151"
REQUEST_REASON = "Our keynote speaker has withdrawn"
FUTURE_START = "2026-11-12T10:00:00+08:00"


def event_row(status="confirmed", starts_at=FUTURE_START):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": COORDINATOR_ID,
        "status": status, "event_timezone": "Asia/Singapore", "name": "Partner Summit",
        "purpose": "Quarterly partner meeting", "description": None,
        "starts_at": starts_at, "ends_at": "2026-11-12T12:00:00+08:00",
        "expected_attendance": 12, "layout_preference": "boardroom", "facilities_required": [],
        "accessibility_needs": None, "preliminary_equipment_needs": None,
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "technical_readiness": "not_required", "submitted_at": now, "version": 3,
        "created_at": now, "updated_at": now,
    }


OPEN_REQUEST = {
    "id": REQUEST_ID, "kind": "cancellation", "status": "open", "reason": REQUEST_REASON,
    "requested_by": {"id": ORGANISER_ID, "full_name": "Olivia Organiser"},
    "requested_at": "2026-10-23T09:00:00+00:00",
}


@pytest.fixture()
def events(monkeypatch):
    """An in-memory event, its open request, and a fake `cancel_event` that answers like
    the RPC: ok with the cancelled event, or an outcome code."""
    store = {EVENT_ID: event_row()}
    request = {"value": deepcopy(OPEN_REQUEST)}
    calls = []
    outcome = {"value": "ok"}

    def cancel_event(event_id, actor_id, expected_version, from_statuses, reason,
                     require_open_request, organiser_message, staff_message, attendee_message,
                     safety_message):
        calls.append({
            "event_id": event_id, "actor_id": actor_id, "expected_version": expected_version,
            "from_statuses": from_statuses, "reason": reason,
            "require_open_request": require_open_request, "organiser_message": organiser_message,
            "staff_message": staff_message, "attendee_message": attendee_message,
            "safety_message": safety_message,
        })
        if outcome["value"] != "ok":
            return {"outcome": outcome["value"], "event": None}
        cancelled = {**store[event_id], "status": "cancelled", "version": expected_version + 1}
        return {"outcome": "ok", "event": cancelled}

    monkeypatch.setattr(repository, "get_event", lambda event_id: deepcopy(store.get(event_id)))
    monkeypatch.setattr(repository, "get_open_cancellation_request",
                        lambda event_id: deepcopy(request["value"]))
    monkeypatch.setattr(repository, "cancel_event", cancel_event)
    return {"store": store, "request": request, "calls": calls, "outcome": outcome}


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role="event_coordinator", user_id=COORDINATOR_ID):
        return authenticate_as(role, user_id=user_id)
    return _act_as


def approve(client, auth_headers):
    return client.post(f"/api/v1/events/{EVENT_ID}/cancellation-request/approve", headers=auth_headers)


class TestApproveCancellationRequest:
    def test_approving_cancels_the_event_in_one_call(self, client, auth_headers, act_as, events):
        act_as()

        response = approve(client, auth_headers)

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        [call] = events["calls"]
        assert call["event_id"] == EVENT_ID
        assert call["actor_id"] == COORDINATOR_ID
        assert call["expected_version"] == 3
        assert call["require_open_request"] is True

    def test_the_history_reason_is_the_organisers_reason(self, client, auth_headers, act_as, events):
        act_as()

        approve(client, auth_headers)

        assert events["calls"][0]["reason"] == f"Cancellation approved. Organiser's reason: {REQUEST_REASON}"

    def test_everyone_involved_is_told(self, client, auth_headers, act_as, events):
        act_as()

        approve(client, auth_headers)

        call = events["calls"][0]
        assert call["organiser_message"] == 'Your request to cancel "Partner Summit" was approved. The event is cancelled.'
        assert call["staff_message"] == (
            '"Partner Summit" was cancelled. Its venue bookings and equipment reservations are released.')
        assert call["attendee_message"] == '"Partner Summit" has been cancelled. Your registration is cancelled.'
        assert call["safety_message"] == '"Partner Summit" was cancelled and no longer needs its safety check.'

    @pytest.mark.parametrize("status", ["under_review", "returned", "planning", "safety_review",
                                        "confirmed", "preparation"])
    def test_every_status_that_takes_a_request_can_be_approved(self, client, auth_headers, act_as,
                                                               events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as()

        response = approve(client, auth_headers)

        assert response.status_code == 200
        call = events["calls"][0]
        assert {"under_review", "returned", "planning", "safety_review", "confirmed",
                "preparation"} <= set(call["from_statuses"])
        assert {"draft", "rejected", "cancelled", "completed"}.isdisjoint(call["from_statuses"])
