"""SCRUM-12: a Lead assigns a coordinator to a submitted event, `POST /events/{id}/assign`."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import CoordinatorNotEligibleError, EventTransitionError
from app.modules.events import lifecycle, repository, service
from app.modules.events.schemas import EventStatus
from app.modules.events.service import EventConflictError, EventNotFoundError

LEAD = "a0000000-0000-4000-8000-0000000000a1"
EVENT = "e0000000-0000-4000-8000-0000000000e1"
NEW = "c0000000-0000-4000-8000-0000000000c2"


def queued_row(**overrides):
    row = {
        "id": EVENT, "name": "Annual Conference", "status": "submitted", "version": 3,
        "coordinator_id": None, "assigned_by": None, "assigned_at": None,
        "coordinator": None, "organiser": {"full_name": "Olivia Tan"},
    }
    row.update(overrides)
    return row


def assigned_row():
    return {
        "id": EVENT, "organiser_id": "o1", "coordinator_id": NEW, "status": "under_review",
        "name": "Annual Conference", "technical_readiness": "not_required", "version": 4,
        "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-13T00:00:00Z",
        "event_timezone": "Asia/Singapore", "registration_enabled": False,
    }


@pytest.fixture()
def data(monkeypatch):
    state = SimpleNamespace(event=queued_row(), target={"id": NEW, "full_name": "Priya Nair"},
                            rpc_result=assigned_row(), rpc_calls=[])
    monkeypatch.setattr(repository, "get_lead_event", lambda event_id: state.event)
    monkeypatch.setattr(repository, "get_coordinator", lambda pid: state.target if pid == NEW else None)

    def assign_event(*args, **kwargs):
        state.rpc_calls.append((args, kwargs))
        return state.rpc_result

    monkeypatch.setattr(repository, "assign_event", assign_event)
    return state


class TestLifecycle:
    def test_submission_waits_in_the_queue(self):
        assert lifecycle.target("submit", "draft") == EventStatus.submitted

    def test_assigning_moves_submitted_to_under_review(self):
        assert lifecycle.target("assign", "submitted") == EventStatus.under_review
        assert lifecycle.allowed_from("assign") == ["submitted"]

    @pytest.mark.parametrize("status", [s.value for s in EventStatus if s is not EventStatus.submitted])
    def test_nothing_else_can_be_assigned(self, status):
        with pytest.raises(Exception) as caught:
            lifecycle.target("assign", status)
        assert caught.value.status_code == 409

    @pytest.mark.parametrize("action", ["approve", "reject", "return"])
    def test_a_queued_event_cannot_be_decided(self, action):
        with pytest.raises(Exception) as caught:
            lifecycle.target(action, "submitted")
        assert caught.value.status_code == 409


class TestService:
    def test_assigns_a_queued_event(self, data):
        result = service.assign(EVENT, LEAD, NEW)
        assert result.coordinator_id == NEW and result.status == EventStatus.under_review
        (args, kwargs), = data.rpc_calls
        assert args == (EVENT, LEAD, NEW)
        assert kwargs["from_statuses"] == ["submitted"] and kwargs["to_status"] == "under_review"

    def test_the_history_reason_and_notices_name_the_people(self, data):
        service.assign(EVENT, LEAD, NEW)
        kwargs = data.rpc_calls[0][1]
        assert "Priya Nair" in kwargs["reason"]
        assert "Annual Conference" in kwargs["notify_assigned"]
        assert "Priya Nair" in kwargs["notify_organiser"]

    @pytest.mark.parametrize("row", [None, queued_row(status="draft")])
    def test_missing_and_draft_events_are_404(self, data, row):
        data.event = row
        with pytest.raises(EventNotFoundError):
            service.assign(EVENT, LEAD, NEW)
        assert data.rpc_calls == []

    @pytest.mark.parametrize("status", ["under_review", "returned", "planning", "safety_review", "confirmed"])
    def test_an_event_that_already_has_a_coordinator_is_rejected(self, data, status):
        data.event = queued_row(status=status, coordinator_id="c1", coordinator={"id": "c1", "full_name": "Marcus Lim"})
        with pytest.raises(EventConflictError) as caught:
            service.assign(EVENT, LEAD, NEW)
        assert caught.value.detail == service.ALREADY_ASSIGNED_MESSAGE
        assert data.rpc_calls == []

    @pytest.mark.parametrize("status", ["rejected", "cancelled", "completed"])
    def test_a_finished_event_is_409(self, data, status):
        data.event = queued_row(status=status)
        with pytest.raises(EventTransitionError) as caught:
            service.assign(EVENT, LEAD, NEW)
        assert caught.value.detail == f"Cannot assign an event that is {status}"
        assert data.rpc_calls == []

    def test_a_target_who_is_not_a_coordinator_is_422(self, data):
        with pytest.raises(CoordinatorNotEligibleError):
            service.assign(EVENT, LEAD, "someone-else")
        assert data.rpc_calls == []

    def test_a_lead_cannot_be_assigned_as_coordinator(self, data):
        with pytest.raises(CoordinatorNotEligibleError):
            service.assign(EVENT, LEAD, LEAD)

    def test_the_second_of_two_simultaneous_assignments_is_rejected(self, data):
        """Both Leads read the event as queued; the database lets only one through."""
        data.rpc_result = None
        with pytest.raises(EventConflictError) as caught:
            service.assign(EVENT, LEAD, NEW)
        assert caught.value.detail == service.ALREADY_ASSIGNED_MESSAGE


class TestEndpoint:
    URL = f"/api/v1/events/{EVENT}/assign"

    def test_a_lead_can_assign(self, authenticate_as, data, client: TestClient):
        authenticate_as("event_coordinator_lead", LEAD)
        response = client.post(self.URL, json={"coordinator_id": NEW}, headers={"Authorization": "Bearer t"})
        assert response.status_code == 200
        assert response.json()["status"] == "under_review"

    def test_the_body_must_carry_a_uuid(self, authenticate_as, data, client: TestClient):
        authenticate_as("event_coordinator_lead", LEAD)
        response = client.post(self.URL, json={"coordinator_id": "nope"}, headers={"Authorization": "Bearer t"})
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "role",
        ["event_organiser", "event_coordinator", "venue_staff", "tech_support", "safety_officer", "attendee"],
    )
    def test_every_other_active_role_gets_403_and_nothing_is_written(
        self, authenticate_as, data, client: TestClient, role
    ):
        authenticate_as(role)
        response = client.post(self.URL, json={"coordinator_id": NEW}, headers={"Authorization": "Bearer t"})
        assert response.status_code == 403
        assert data.rpc_calls == []


class TestLeadIsNotACoordinator:
    """SCRUM-12 AC12: the Lead role is for management only; a Lead acting as Lead gets 403
    on every coordinator action, straight to the API."""

    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("approve", None),
            ("reject", {"reason": "No."}),
            ("return", {"message": "Please amend.", "flagged_fields": []}),
            ("send-for-safety-check", None),
        ],
    )
    def test_a_lead_cannot_act_on_an_event_as_its_coordinator(
        self, authenticate_as, data, client: TestClient, path, body
    ):
        authenticate_as("event_coordinator_lead", LEAD)
        response = client.post(f"/api/v1/events/{EVENT}/{path}", json=body, headers={"Authorization": "Bearer t"})
        assert response.status_code == 403
        assert data.rpc_calls == []
