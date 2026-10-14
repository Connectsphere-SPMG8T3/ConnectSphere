"""CR-101 AC3, AC7: a Lead reassigns an event, `POST /events/{id}/reassign`."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import CoordinatorNotEligibleError, EventNotInLeadScopeError
from app.modules.events import repository, service
from app.modules.events.service import EventConflictError, EventNotFoundError

LEAD = "a0000000-0000-4000-8000-0000000000a1"
OTHER_LEAD = "a0000000-0000-4000-8000-0000000000a2"
EVENT = "e0000000-0000-4000-8000-0000000000e1"
NEW = "c0000000-0000-4000-8000-0000000000c2"
OLD = "c0000000-0000-4000-8000-0000000000c1"


def lead_row(**overrides):
    row = {
        "id": EVENT, "name": "Annual Conference", "status": "under_review", "version": 3,
        "coordinator_id": None, "assigned_by": None, "assigned_at": None,
        "coordinator": None, "organiser": {"full_name": "Olivia Tan"},
    }
    row.update(overrides)
    return row


def updated_row(coordinator_id=NEW):
    return {
        "id": EVENT, "organiser_id": "o1", "coordinator_id": coordinator_id, "status": "under_review",
        "name": "Annual Conference", "technical_readiness": "not_required", "version": 4,
        "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-13T00:00:00Z",
        "event_timezone": "Asia/Singapore", "registration_enabled": False,
    }


@pytest.fixture()
def data(monkeypatch):
    state = SimpleNamespace(event=lead_row(), target={"id": NEW, "full_name": "Priya Nair"},
                            lead_ids={LEAD}, rpc_result=updated_row(), rpc_calls=[])
    monkeypatch.setattr(repository, "get_lead_event", lambda event_id: state.event)
    monkeypatch.setattr(repository, "get_coordinator", lambda pid: state.target if pid == NEW else None)
    monkeypatch.setattr(repository, "list_lead_ids", lambda: state.lead_ids)

    def reassign_event(*args, **kwargs):
        state.rpc_calls.append((args, kwargs))
        return state.rpc_result

    monkeypatch.setattr(repository, "reassign_event", reassign_event)
    return state


def test_assigns_an_unassigned_event_and_passes_the_row_version(data):
    result = service.reassign(EVENT, LEAD, NEW, 3)
    assert result.coordinator_id == NEW
    (args, kwargs), = data.rpc_calls
    assert args == (EVENT, LEAD, NEW, 3)
    assert set(kwargs["active_statuses"]) == {"under_review", "returned", "planning", "safety_review", "confirmed"}
    # A reassignment is not a status change: it must not ask for a status-history row,
    # which would reorder the Safety Officer's queue and show the organiser a fake transition.
    assert "reason" not in kwargs


def test_the_notices_name_the_event_and_the_new_coordinator(data):
    data.event = lead_row(coordinator_id=OLD, coordinator={"id": OLD, "full_name": "Marcus Lim"}, assigned_by=LEAD)
    service.reassign(EVENT, LEAD, NEW, 3)
    kwargs = data.rpc_calls[0][1]
    assert "Annual Conference" in kwargs["notify_assigned"]
    assert "Priya Nair" in kwargs["notify_previous"] and "Priya Nair" in kwargs["notify_organiser"]


def test_missing_event_and_draft_are_404(data):
    data.event = None
    with pytest.raises(EventNotFoundError):
        service.reassign(EVENT, LEAD, NEW, 3)
    data.event = lead_row(status="draft")
    with pytest.raises(EventNotFoundError):
        service.reassign(EVENT, LEAD, NEW, 3)


@pytest.mark.parametrize("status", ["rejected", "cancelled", "completed"])
def test_terminal_events_are_409_and_nothing_is_written(data, status):
    data.event = lead_row(status=status)
    with pytest.raises(EventConflictError) as caught:
        service.reassign(EVENT, LEAD, NEW, 3)
    assert caught.value.status_code == 409
    assert data.rpc_calls == []


def test_an_event_another_current_lead_manages_is_403(data):
    data.lead_ids = {LEAD, OTHER_LEAD}
    data.event = lead_row(coordinator_id=OLD, assigned_by=OTHER_LEAD)
    with pytest.raises(EventNotInLeadScopeError):
        service.reassign(EVENT, LEAD, NEW, 3)
    assert data.rpc_calls == []


def test_a_target_who_is_not_a_coordinator_or_unknown_is_422(data):
    with pytest.raises(CoordinatorNotEligibleError):
        service.reassign(EVENT, LEAD, "not-a-coordinator", 3)
    assert data.rpc_calls == []


def test_reassigning_to_the_current_coordinator_is_409(data):
    data.event = lead_row(coordinator_id=NEW, coordinator={"id": NEW, "full_name": "Priya Nair"})
    with pytest.raises(EventConflictError) as caught:
        service.reassign(EVENT, LEAD, NEW, 3)
    assert "already" in caught.value.detail
    assert data.rpc_calls == []


def test_a_page_that_is_behind_the_event_is_409_reload_and_nothing_is_written(data):
    """The Lead's screen shows version 2, but the event has since moved to 3 (another tab,
    or another Lead's earlier change): the reassign must not silently replace it."""
    with pytest.raises(EventConflictError) as caught:
        service.reassign(EVENT, LEAD, NEW, 2)
    assert caught.value.detail == service.STALE_EVENT_MESSAGE
    assert data.rpc_calls == []


def test_a_lost_race_is_409_reload(data):
    data.rpc_result = None
    with pytest.raises(EventConflictError) as caught:
        service.reassign(EVENT, LEAD, NEW, 3)
    assert caught.value.detail == service.STALE_EVENT_MESSAGE


class TestEndpoint:
    URL = f"/api/v1/events/{EVENT}/reassign"

    def test_a_lead_can_reassign(self, authenticate_as, data, client: TestClient):
        authenticate_as("event_coordinator_lead", LEAD)
        response = client.post(self.URL, json={"coordinator_id": NEW, "expected_version": 3}, headers={"Authorization": "Bearer t"})
        assert response.status_code == 200
        assert response.json()["coordinator_id"] == NEW

    def test_the_body_must_carry_the_version_the_lead_saw(self, authenticate_as, data, client: TestClient):
        authenticate_as("event_coordinator_lead", LEAD)
        response = client.post(self.URL, json={"coordinator_id": NEW}, headers={"Authorization": "Bearer t"})
        assert response.status_code == 422

    def test_the_body_must_carry_a_uuid(self, authenticate_as, data, client: TestClient):
        authenticate_as("event_coordinator_lead", LEAD)
        response = client.post(self.URL, json={"coordinator_id": "nope", "expected_version": 3}, headers={"Authorization": "Bearer t"})
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "role",
        ["event_organiser", "event_coordinator", "venue_staff", "tech_support", "safety_officer", "attendee"],
    )
    def test_every_other_active_role_gets_403_and_nothing_is_written(
        self, authenticate_as, data, client: TestClient, role
    ):
        authenticate_as(role)
        response = client.post(self.URL, json={"coordinator_id": NEW, "expected_version": 3}, headers={"Authorization": "Bearer t"})
        assert response.status_code == 403
        assert data.rpc_calls == []
