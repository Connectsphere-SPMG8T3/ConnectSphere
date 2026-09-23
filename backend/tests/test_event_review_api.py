"""SCRUM-34 approve and SCRUM-52 reject, through the HTTP API with the repository mocked."""

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.modules.events import repository
from tests.conftest import make_table_mock

ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_COORDINATOR_ID = "a0000000-0000-4000-8000-000000000009"
EVENT_ID = "e0000000-0000-4000-8000-000000000201"
MISSING_EVENT_ID = "e0000000-0000-4000-8000-0000000009ff"
ALL_STATUSES = ["draft", "submitted", "under_review", "returned", "planning",
                "confirmed", "rejected", "cancelled", "completed"]


def event_row(status="under_review", coordinator_id=COORDINATOR_ID):
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
    """An in-memory events table plus a fake transition_event with the RPC's guards."""
    store = {EVENT_ID: event_row()}
    calls = []

    def get_event(event_id):
        return deepcopy(store.get(event_id))

    def transition_event(event_id, actor_id, from_statuses, to_status, expected_version,
                         reason=None, notify_type=None, notify_message=None):
        calls.append({
            "event_id": event_id, "actor_id": actor_id, "from_statuses": from_statuses,
            "to_status": to_status, "expected_version": expected_version, "reason": reason,
            "notify_type": notify_type, "notify_message": notify_message,
        })
        row = store.get(event_id)
        if row is None or row["version"] != expected_version or row["status"] not in from_statuses:
            return None
        row.update(status=to_status, version=row["version"] + 1)
        return deepcopy(row)

    monkeypatch.setattr(repository, "get_event", get_event)
    monkeypatch.setattr(repository, "transition_event", transition_event)
    return {"store": store, "calls": calls}


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role, user_id=COORDINATOR_ID):
        return authenticate_as(role, user_id=user_id)
    return _act_as


def approve(client, auth_headers, event_id=EVENT_ID):
    return client.post(f"/api/v1/events/{event_id}/approve", headers=auth_headers)


def reject(client, auth_headers, reason="Venue unavailable on that date", event_id=EVENT_ID):
    return client.post(f"/api/v1/events/{event_id}/reject", json={"reason": reason}, headers=auth_headers)


class TestApprove:
    def test_assigned_coordinator_moves_under_review_event_to_planning(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        response = approve(client, auth_headers)

        assert response.status_code == 200
        assert response.json()["status"] == "planning"
        [call] = events["calls"]
        assert call["actor_id"] == COORDINATOR_ID
        assert call["from_statuses"] == ["under_review"]
        assert call["to_status"] == "planning"
        assert call["expected_version"] == 3
        assert call["reason"] is None

    def test_approval_notifies_the_organiser(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        approve(client, auth_headers)

        [call] = events["calls"]
        assert call["notify_type"] == "event_approved"
        assert call["notify_message"] == 'Your event "Partner Summit" passed its initial review and is now in planning.'

    @pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s != "under_review"])
    def test_approve_is_blocked_unless_under_review(self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as("event_coordinator")

        response = approve(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Cannot approve an event that is {status.replace('_', ' ')}"
        assert events["calls"] == []

    def test_a_coordinator_who_is_not_assigned_is_forbidden(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", user_id=OTHER_COORDINATOR_ID)

        response = approve(client, auth_headers)

        assert response.status_code == 403
        assert events["calls"] == []

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, events, role):
        act_as(role)

        assert approve(client, auth_headers).status_code == 403
        assert events["calls"] == []

    def test_unknown_event_is_not_found(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        assert approve(client, auth_headers, event_id=MISSING_EVENT_ID).status_code == 404

    def test_a_lost_race_is_a_conflict(self, client, auth_headers, act_as, events, monkeypatch):
        monkeypatch.setattr(repository, "transition_event", lambda *args, **kwargs: None)
        act_as("event_coordinator")

        response = approve(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "This event was updated by someone else. Reload."


class TestReject:
    @pytest.mark.parametrize("status", ["under_review", "planning"])
    def test_assigned_coordinator_rejects_before_confirmation(self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as("event_coordinator")

        response = reject(client, auth_headers, reason="  Venue unavailable on that date  ")

        assert response.status_code == 200
        assert response.json()["status"] == "rejected"
        [call] = events["calls"]
        assert call["from_statuses"] == ["planning", "under_review"]
        assert call["to_status"] == "rejected"
        assert call["reason"] == "Venue unavailable on that date"
        assert call["notify_type"] == "event_rejected"
        assert call["notify_message"] == 'Your event "Partner Summit" was rejected: Venue unavailable on that date'

    @pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s not in ("under_review", "planning")])
    def test_reject_is_blocked_outside_under_review_and_planning(self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as("event_coordinator")

        response = reject(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Cannot reject an event that is {status.replace('_', ' ')}"
        assert events["calls"] == []

    @pytest.mark.parametrize("reason", ["", "   ", "\n\t "])
    def test_a_blank_reason_is_rejected(self, client, auth_headers, act_as, events, reason):
        act_as("event_coordinator")

        assert reject(client, auth_headers, reason=reason).status_code == 422
        assert events["calls"] == []

    def test_a_missing_reason_is_rejected(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        response = client.post(f"/api/v1/events/{EVENT_ID}/reject", json={}, headers=auth_headers)

        assert response.status_code == 422
        assert events["calls"] == []

    def test_a_reason_over_1000_characters_is_rejected(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        assert reject(client, auth_headers, reason="x" * 1001).status_code == 422
        assert reject(client, auth_headers, reason="x" * 1000).status_code == 200

    def test_a_coordinator_who_is_not_assigned_is_forbidden(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", user_id=OTHER_COORDINATOR_ID)

        assert reject(client, auth_headers).status_code == 403
        assert events["calls"] == []

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, events, role):
        act_as(role)

        assert reject(client, auth_headers).status_code == 403
        assert events["calls"] == []


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_a_coordinator_acting_as_venue_staff_is_forbidden(client, auth_headers, monkeypatch, events, action):
    """SCRUM-76: holding the coordinator role is not enough; the session must be acting as it."""
    profile = {
        "id": COORDINATOR_ID, "email": "coordinator@connectsphere.dev", "full_name": "Marcus Lim",
        "role": "event_coordinator", "organisation_name": None, "department": None, "phone_number": None,
    }
    anon_client = MagicMock()
    anon_client.auth.get_claims.return_value = {"claims": {
        "sub": COORDINATOR_ID, "aud": "authenticated", "email": profile["email"],
        "session_id": "22222222-2222-2222-2222-222222222222",
    }}
    monkeypatch.setattr("app.core.security.get_supabase_anon_client", lambda: anon_client)
    monkeypatch.setattr(
        "app.core.security.get_supabase_admin_client",
        lambda: make_table_mock(profile, session_active_role={"role": "venue_staff"}),
    )

    response = client.post(f"/api/v1/events/{EVENT_ID}/{action}", json={"reason": "No venue"}, headers=auth_headers)

    assert response.status_code == 403
    assert events["calls"] == []
