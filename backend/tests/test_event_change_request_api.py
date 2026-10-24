"""Story 32: the organiser requests changes to their event, through the HTTP API with
the repository mocked. The RPC's own guards are checked against the real database by
supabase/verification/event_change_request_checks.sql."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.modules.events import repository

ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
EVENT_ID = "e0000000-0000-4000-8000-000000000321"
SPACE_ID = "f0000000-0000-4000-8000-000000000321"
REQUEST_ID = "c0000000-0000-4000-8000-000000000321"
REASON = "Our sponsor wants a longer programme"


def space_row():
    return {
        "id": SPACE_ID, "event_id": EVENT_ID, "label": "Main hall", "expected_pax": 80,
        "layout_preference": "theatre", "facilities_required": ["projector"],
        "starts_at": None, "ends_at": None, "version": 1, "is_primary": True,
    }


def event_row(status="planning", coordinator_id=COORDINATOR_ID):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": coordinator_id,
        "status": status, "event_timezone": "Asia/Singapore", "name": "Partner Summit",
        "purpose": "Quarterly partner meeting", "description": None,
        "starts_at": "2026-11-12T10:00:00+08:00", "ends_at": "2026-11-12T12:00:00+08:00",
        "expected_attendance": 80, "layout_preference": "theatre", "facilities_required": ["projector"],
        "accessibility_needs": None, "preliminary_equipment_needs": None,
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "re_registration_allowed": True, "waitlist_enabled": True,
        "technical_readiness": "not_required", "submitted_at": now, "version": 3,
        "created_at": now, "updated_at": now, "spaces": [space_row()],
    }


@pytest.fixture()
def events(monkeypatch):
    """An in-memory events table plus a fake request_event_change that answers like
    the RPC: ok with the new request, or an outcome code."""
    store = {EVENT_ID: event_row()}
    calls = []
    outcome = {"value": "ok"}

    def get_event(event_id):
        return deepcopy(store.get(event_id))

    def request_event_change(event_id, actor_id, reason, changes, significant, from_statuses,
                             expected_version, coordinator_message, lead_message):
        calls.append({
            "event_id": event_id, "actor_id": actor_id, "reason": reason, "changes": changes,
            "significant": significant, "from_statuses": from_statuses,
            "expected_version": expected_version, "coordinator_message": coordinator_message,
            "lead_message": lead_message,
        })
        if outcome["value"] != "ok":
            return {"outcome": outcome["value"], "request": None}
        return {"outcome": "ok", "request": {
            "id": REQUEST_ID, "kind": "change", "status": "open", "reason": reason,
            "changes": changes, "significant": significant,
            "requested_by": {"id": actor_id, "full_name": "Test event_organiser"},
            "requested_at": "2026-10-24T09:00:00+00:00",
        }}

    monkeypatch.setattr(repository, "get_event", get_event)
    monkeypatch.setattr(repository, "request_event_change", request_event_change)
    return {"store": store, "calls": calls, "outcome": outcome}


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role="event_organiser", user_id=ORGANISER_ID):
        return authenticate_as(role, user_id=user_id)
    return _act_as


def request_change(client, auth_headers, *, event=None, spaces=None, reason=REASON, version=3,
                   event_id=EVENT_ID):
    body = {"reason": reason, "version": version, "event": event or {}, "spaces": spaces or []}
    return client.post(f"/api/v1/events/{event_id}/change-request", json=body, headers=auth_headers)


class TestRequestChange:
    def test_owner_records_an_open_change_request_with_the_before_and_after(
            self, client, auth_headers, act_as, events):
        act_as()

        response = request_change(client, auth_headers, event={"description": "Two keynotes and a panel"})

        assert response.status_code == 201
        assert response.json() == {
            "id": REQUEST_ID, "kind": "change", "status": "open", "reason": REASON,
            "changes": {
                "event": [{"field": "description", "before": None, "after": "Two keynotes and a panel"}],
                "spaces": [],
            },
            "significant": False,
            "requested_by": {"id": ORGANISER_ID, "full_name": "Test event_organiser"},
            "requested_at": "2026-10-24T09:00:00Z",
        }
        [call] = events["calls"]
        assert call["event_id"] == EVENT_ID
        assert call["actor_id"] == ORGANISER_ID
        assert call["expected_version"] == 3
