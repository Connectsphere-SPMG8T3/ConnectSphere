"""SCRUM-81 AC4: the Event Coordinator Lead reads an event's reassignment history,
`GET /events/{id}/reassignment-history`. Reassignments only, never the event's full
history [Assumption, REQUIREMENTS §9 item 110]. Scope is the Lead's (LA-R2)."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import EventNotInLeadScopeError
from app.modules.events import repository, service
from app.modules.events.service import EventNotFoundError

LEAD = "a0000000-0000-4000-8000-0000000000a1"
OTHER_LEAD = "a0000000-0000-4000-8000-0000000000a2"
EVENT = "e0000000-0000-4000-8000-0000000000e1"
OLD = "c0000000-0000-4000-8000-0000000000c1"
NEW = "c0000000-0000-4000-8000-0000000000c2"

ENTRY = {
    "id": "h1", "at": "2026-11-02T09:00:00+00:00",
    "actor": {"id": LEAD, "full_name": "Lena Lead"},
    "from_coordinator": {"id": OLD, "full_name": "Marcus Lim"},
    "to_coordinator": {"id": NEW, "full_name": "Priya Nair"},
}


@pytest.fixture()
def data(monkeypatch):
    state = SimpleNamespace(
        event={"id": EVENT, "status": "under_review", "coordinator_id": OLD, "assigned_by": LEAD, "version": 3},
        lead_ids={LEAD}, history=[ENTRY], status_history_reads=[],
    )
    monkeypatch.setattr(repository, "get_lead_event", lambda event_id: state.event)
    monkeypatch.setattr(repository, "list_lead_ids", lambda: state.lead_ids)
    monkeypatch.setattr(repository, "list_assignment_history", lambda event_id: state.history)
    monkeypatch.setattr(repository, "list_status_history",
                        lambda event_id: state.status_history_reads.append(event_id) or [])
    return state


def test_returns_each_reassignment_with_from_to_by_and_when(data):
    response = service.reassignment_history(EVENT, LEAD)

    (entry,) = response.entries
    assert entry.kind == "reassignment"
    assert entry.from_coordinator.full_name == "Marcus Lim"
    assert entry.to_coordinator.full_name == "Priya Nair"
    assert entry.actor.full_name == "Lena Lead"
    assert entry.at.isoformat() == "2026-11-02T09:00:00+00:00"


def test_an_event_never_reassigned_has_an_empty_history(data):
    data.history = []
    assert service.reassignment_history(EVENT, LEAD).entries == []


def test_the_scope_check_reads_the_requested_event(data, monkeypatch):
    reads = []
    monkeypatch.setattr(repository, "get_lead_event", lambda event_id: reads.append(event_id) or data.event)

    service.reassignment_history(EVENT, LEAD)

    assert reads == [EVENT]


def test_reads_reassignments_only_not_the_status_or_other_history(data):
    service.reassignment_history(EVENT, LEAD)
    assert data.status_history_reads == []


def test_missing_event_and_draft_are_404(data):
    data.event = None
    with pytest.raises(EventNotFoundError):
        service.reassignment_history(EVENT, LEAD)
    data.event = {**ENTRY, "id": EVENT, "status": "draft", "coordinator_id": None}
    with pytest.raises(EventNotFoundError):
        service.reassignment_history(EVENT, LEAD)


def test_an_event_another_current_lead_manages_is_403(data):
    data.lead_ids = {LEAD, OTHER_LEAD}
    data.event = {**data.event, "assigned_by": OTHER_LEAD}
    with pytest.raises(EventNotInLeadScopeError):
        service.reassignment_history(EVENT, LEAD)


def test_an_event_assigned_before_the_lead_role_existed_is_in_every_leads_scope(data):
    """AC13: `assigned_by` is null for events auto-assigned before Week 7."""
    data.event = {**data.event, "assigned_by": None}
    assert len(service.reassignment_history(EVENT, LEAD).entries) == 1


class TestEndpoint:
    URL = f"/api/v1/events/{EVENT}/reassignment-history"

    def test_a_lead_reads_the_history(self, authenticate_as, data, client: TestClient):
        authenticate_as("event_coordinator_lead", LEAD)
        response = client.get(self.URL, headers={"Authorization": "Bearer t"})
        assert response.status_code == 200
        (entry,) = response.json()["entries"]
        assert entry["kind"] == "reassignment"
        assert entry["to_coordinator"]["full_name"] == "Priya Nair"

    def test_an_event_in_another_leads_scope_is_403(self, authenticate_as, data, client: TestClient):
        data.lead_ids = {LEAD, OTHER_LEAD}
        data.event = {**data.event, "assigned_by": OTHER_LEAD}
        authenticate_as("event_coordinator_lead", LEAD)
        response = client.get(self.URL, headers={"Authorization": "Bearer t"})
        assert response.status_code == 403

    def test_the_event_id_must_be_a_uuid(self, authenticate_as, data, client: TestClient):
        authenticate_as("event_coordinator_lead", LEAD)
        response = client.get("/api/v1/events/nope/reassignment-history", headers={"Authorization": "Bearer t"})
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "role",
        ["event_organiser", "event_coordinator", "venue_staff", "tech_support", "safety_officer", "attendee"],
    )
    def test_every_other_active_role_gets_403_and_reads_nothing(self, authenticate_as, data, client: TestClient, role):
        """Gated on the session's active role: even a coordinator who also holds Lead is
        refused while acting as a coordinator (raw request, no UI)."""
        authenticate_as(role)
        response = client.get(self.URL, headers={"Authorization": "Bearer t"})
        assert response.status_code == 403
        assert data.status_history_reads == []

    def test_no_token_is_401(self, data, client: TestClient):
        assert client.get(self.URL).status_code in (401, 403)
