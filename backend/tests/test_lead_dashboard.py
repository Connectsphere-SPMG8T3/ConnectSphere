"""CR-101: the Event Coordinator Lead dashboard, `GET /events/dashboard/lead`."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.modules.events import repository, service
from app.modules.events.service import ACTIVE_COORDINATOR_STATUSES

LEAD = "a0000000-0000-4000-8000-0000000000a1"
OTHER_LEAD = "a0000000-0000-4000-8000-0000000000a2"
URL = "/api/v1/events/dashboard/lead"


def event(event_id, status, coordinator=None, assigned_by=None, **extra):
    row = {
        "id": event_id,
        "name": f"Event {event_id}",
        "status": status,
        "starts_at": "2026-11-12T10:00:00+08:00",
        "version": 5,
        "purpose": "Conference",
        "expected_attendance": 80,
        "coordinator_id": coordinator["id"] if coordinator else None,
        "coordinator": coordinator,
        "assigned_by": assigned_by,
        "assigned_at": "2026-10-10T09:00:00+08:00" if coordinator else None,
        "organiser": {"full_name": "Olivia Tan"},
    }
    row.update(extra)
    return row


C1 = {"id": "c1", "full_name": "Marcus Lim"}
C2 = {"id": "c2", "full_name": "Priya Nair"}


@pytest.fixture()
def data(monkeypatch):
    state = SimpleNamespace(events=[], lead_ids={LEAD}, coordinators=[C1, C2], statuses=None)

    def list_lead_events(statuses):
        state.statuses = set(statuses)
        return state.events

    monkeypatch.setattr(repository, "list_lead_events", list_lead_events)
    monkeypatch.setattr(repository, "list_lead_ids", lambda: state.lead_ids)
    monkeypatch.setattr(repository, "list_coordinators", lambda: state.coordinators)
    return state


class TestScopeAndStatuses:
    def test_reads_only_active_statuses(self, data):
        service.lead_dashboard(LEAD)
        assert data.statuses == set(ACTIVE_COORDINATOR_STATUSES)
        assert not data.statuses & {"draft", "rejected", "cancelled", "completed"}

    def test_empty_system_is_an_empty_dashboard(self, data):
        data.coordinators = []
        dashboard = service.lead_dashboard(LEAD)
        assert dashboard.unassigned == [] and dashboard.active_events == [] and dashboard.coordinators == []

    def test_unassigned_queue_and_assigned_events_are_separated_with_coordinator_and_status(self, data):
        data.events = [event("e1", "under_review"), event("e2", "planning", C1, LEAD)]
        dashboard = service.lead_dashboard(LEAD)
        assert [e.event_id for e in dashboard.unassigned] == ["e1"]
        [assigned] = dashboard.active_events
        assert (assigned.event_id, assigned.status.value, assigned.coordinator.full_name) == ("e2", "planning", "Marcus Lim")
        assert assigned.organiser_name == "Olivia Tan"
        assert assigned.version == 5  # the Lead sends it back so a stale screen can't overwrite a newer change

    def test_every_lead_sees_the_queue_but_only_their_own_assigned_events(self, data):
        data.lead_ids = {LEAD, OTHER_LEAD}
        data.events = [
            event("q", "under_review"),
            event("mine", "planning", C1, LEAD),
            event("theirs", "planning", C1, OTHER_LEAD),
            event("legacy", "planning", C2, None),
        ]
        dashboard = service.lead_dashboard(LEAD)
        assert [e.event_id for e in dashboard.unassigned] == ["q"]
        assert sorted(e.event_id for e in dashboard.active_events) == ["legacy", "mine"]

    def test_a_single_lead_sees_all_events(self, data):
        data.events = [event("a", "planning", C1, LEAD), event("b", "planning", C2, "former-lead")]
        assert len(service.lead_dashboard(LEAD).active_events) == 2

    def test_coordinator_counts_cover_the_leads_scope_and_include_idle_coordinators(self, data):
        data.lead_ids = {LEAD, OTHER_LEAD}
        data.events = [
            event("a", "planning", C1, LEAD),
            event("b", "confirmed", C1, None),
            event("c", "planning", C1, OTHER_LEAD),  # out of scope: not counted
        ]
        counts = {c.id: c.active_count for c in service.lead_dashboard(LEAD).coordinators}
        assert counts == {"c1": 2, "c2": 0}


class TestEndpointAccess:
    def test_a_lead_gets_the_dashboard(self, authenticate_as, data, client: TestClient):
        authenticate_as("event_coordinator_lead", LEAD)
        response = client.get(URL, headers={"Authorization": "Bearer t"})
        assert response.status_code == 200
        assert set(response.json()) == {"unassigned", "active_events", "coordinators"}

    @pytest.mark.parametrize(
        "role",
        ["event_organiser", "event_coordinator", "venue_staff", "tech_support", "safety_officer", "attendee"],
    )
    def test_every_other_active_role_gets_403(self, authenticate_as, data, client: TestClient, role):
        authenticate_as(role)
        assert client.get(URL, headers={"Authorization": "Bearer t"}).status_code == 403

    def test_no_token_is_rejected(self, client: TestClient):
        assert client.get(URL).status_code in (401, 403)
