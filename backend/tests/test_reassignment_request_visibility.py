"""CR-106 AC2 and AC6: where a reassignment request shows up. The Lead's dashboard
carries the open request (AC2), the assigned coordinator's event read carries it so
they can see it is pending, and the event history records the request and the Lead's
response (AC6). The history is the coordinator's: the request is internal, so the
organiser's history shows none of it [Assumption]."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.modules.events import repository, service
from app.modules.venues import repository as venues_repository

ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
LEAD = "a0000000-0000-4000-8000-0000000000a1"
EVENT_ID = "e0000000-0000-4000-8000-000000001062"
REQUEST_ID = "c0000000-0000-4000-8000-000000001062"
REASON = "I am on leave for the rest of the month"
COORDINATOR = {"id": COORDINATOR_ID, "full_name": "Marcus Lim"}
LEAD_ACTOR = {"id": LEAD, "full_name": "Lena Lead"}


def event_row(status="planning"):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": COORDINATOR_ID,
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


def request_row(**overrides):
    row = {
        "id": REQUEST_ID, "status": "open", "reason": REASON, "requested_at": "2026-10-27T09:00:00+00:00",
        "requested_by": COORDINATOR, "decided_by": None, "decided_at": None, "decision_reason": None,
    }
    row.update(overrides)
    return row


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role="event_coordinator", user_id=COORDINATOR_ID):
        return authenticate_as(role, user_id=user_id)
    return _act_as


@pytest.fixture()
def events(monkeypatch):
    monkeypatch.setattr(repository, "get_event", lambda event_id: deepcopy(event_row()) if event_id == EVENT_ID else None)


class TestCoordinatorEventRead:
    @pytest.fixture()
    def open_request(self, monkeypatch, events):
        monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: None)
        monkeypatch.setattr(venues_repository, "list_booking_statuses", lambda event_ids: [])
        current = {"value": request_row()}
        calls = []

        def get_open_reassignment_request(event_id):
            calls.append(event_id)
            return deepcopy(current["value"])

        monkeypatch.setattr(repository, "get_open_reassignment_request", get_open_reassignment_request, raising=False)
        return SimpleNamespace(current=current, calls=calls)

    def test_the_assigned_coordinator_sees_their_open_request(self, client, auth_headers, act_as, open_request):
        """So they know a request is pending and can't file a second."""
        act_as()

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["open_reassignment_request"] == {
            "id": REQUEST_ID, "kind": "reassignment", "status": "open", "reason": REASON,
            "requested_by": COORDINATOR, "requested_at": "2026-10-27T09:00:00Z",
        }

    def test_no_open_request_reads_as_null(self, client, auth_headers, act_as, open_request):
        open_request.current["value"] = None
        act_as()

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.json()["open_reassignment_request"] is None

    def test_the_organiser_never_sees_it_and_the_table_is_not_read(self, client, auth_headers, act_as, open_request):
        act_as("event_organiser", user_id=ORGANISER_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["open_reassignment_request"] is None
        assert open_request.calls == []


class TestHistoryRecordsTheRequest:
    @pytest.fixture()
    def history(self, monkeypatch, events):
        monkeypatch.setattr(repository, "list_status_history", lambda event_id: [
            {"id": "h2", "from_status": "under_review", "to_status": "planning", "reason": None,
             "at": "2026-10-20T09:00:00+00:00", "actor": LEAD_ACTOR},
        ])
        monkeypatch.setattr(repository, "list_assignment_history", lambda event_id: [])
        requests = [request_row()]
        calls = []

        def list_reassignment_requests(event_id):
            calls.append(event_id)
            return deepcopy(requests)

        monkeypatch.setattr(repository, "list_reassignment_requests", list_reassignment_requests, raising=False)
        return SimpleNamespace(requests=requests, calls=calls)

    def get_history(self, client, auth_headers):
        return client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers)

    def test_the_request_is_an_entry_with_who_why_and_when(self, client, auth_headers, act_as, history):
        """AC6."""
        act_as()

        response = self.get_history(client, auth_headers)

        assert response.status_code == 200
        first, second = response.json()["entries"]
        assert first == {
            "id": REQUEST_ID, "kind": "reassignment_requested", "from_status": None, "to_status": None,
            "from_coordinator": None, "to_coordinator": None, "actor": COORDINATOR,
            "reason": REASON, "at": "2026-10-27T09:00:00Z",
        }
        assert second["id"] == "h2"

    def test_a_declined_request_shows_who_declined_it_and_why(self, client, auth_headers, act_as, history):
        """AC5, AC6: the Lead's response, who acted and when."""
        history.requests[0].update(status="declined", decided_by=LEAD_ACTOR,
                                   decided_at="2026-10-28T09:00:00+00:00", decision_reason="No cover this month")
        act_as()

        declined, requested, _ = self.get_history(client, auth_headers).json()["entries"]

        assert declined == {
            "id": f"{REQUEST_ID}:declined", "kind": "reassignment_declined", "from_status": None,
            "to_status": None, "from_coordinator": None, "to_coordinator": None, "actor": LEAD_ACTOR,
            "reason": "No cover this month", "at": "2026-10-28T09:00:00Z",
        }
        assert requested["kind"] == "reassignment_requested"

    def test_a_reassigned_request_adds_no_second_entry(self, client, auth_headers, act_as, history):
        """The reassignment is already its own history entry (SCRUM-12), with the Lead and both coordinators."""
        history.requests[0].update(status="reassigned", decided_by=LEAD_ACTOR,
                                   decided_at="2026-10-28T09:00:00+00:00")
        act_as()

        kinds = [entry["kind"] for entry in self.get_history(client, auth_headers).json()["entries"]]

        assert kinds == ["reassignment_requested", "status"]

    def test_a_superseded_request_says_when_and_why_it_closed(self, client, auth_headers, act_as, history):
        history.requests[0].update(status="superseded", decided_at="2026-10-28T09:00:00+00:00",
                                   decision_reason="Closed because the event was cancelled.")
        act_as()

        closed = self.get_history(client, auth_headers).json()["entries"][0]

        assert closed["id"] == f"{REQUEST_ID}:closed"
        assert closed["kind"] == "reassignment_request_closed"
        assert closed["actor"] is None
        assert closed["reason"] == "Closed because the event was cancelled."
        assert closed["at"] == "2026-10-28T09:00:00Z"

    def test_the_organiser_history_has_none_of_it_and_the_table_is_not_read(
            self, client, auth_headers, act_as, history):
        act_as("event_organiser", user_id=ORGANISER_ID)

        entries = self.get_history(client, auth_headers).json()["entries"]

        assert [entry["kind"] for entry in entries] == ["status"]
        assert history.calls == []


class TestLeadDashboardCarriesTheRequest:
    @pytest.fixture()
    def data(self, monkeypatch):
        state = SimpleNamespace(events=[], open_requests={}, asked_for=None)
        monkeypatch.setattr(repository, "list_lead_events", lambda statuses: state.events)
        monkeypatch.setattr(repository, "list_lead_ids", lambda: {LEAD})
        monkeypatch.setattr(repository, "list_coordinators", lambda: [COORDINATOR])

        def list_open_reassignment_requests(event_ids):
            state.asked_for = list(event_ids)
            return deepcopy(state.open_requests)

        monkeypatch.setattr(repository, "list_open_reassignment_requests", list_open_reassignment_requests,
                            raising=False)
        return state

    @staticmethod
    def lead_event(event_id, status, coordinator=None):
        return {
            "id": event_id, "name": f"Event {event_id}", "status": status, "version": 5,
            "starts_at": "2099-11-12T10:00:00+08:00", "purpose": "Conference", "expected_attendance": 80,
            "coordinator_id": coordinator["id"] if coordinator else None, "coordinator": coordinator,
            "assigned_by": LEAD if coordinator else None,
            "assigned_at": "2026-10-10T09:00:00+08:00" if coordinator else None,
            "organiser": {"full_name": "Olivia Tan"},
        }

    def test_an_assigned_event_with_an_open_request_carries_it(self, data):
        """AC2: the request appears in the Lead's view."""
        data.events = [self.lead_event("e1", "planning", COORDINATOR), self.lead_event("e2", "planning", COORDINATOR)]
        data.open_requests = {"e1": request_row()}

        dashboard = service.lead_dashboard(LEAD)

        with_request, without = dashboard.active_events
        assert with_request.open_reassignment_request.reason == REASON
        assert with_request.open_reassignment_request.requested_by.full_name == "Marcus Lim"
        assert with_request.open_reassignment_request.kind == "reassignment"
        assert without.open_reassignment_request is None

    def test_only_assigned_events_are_looked_up(self, data):
        data.events = [self.lead_event("e1", "submitted"), self.lead_event("e2", "planning", COORDINATOR)]

        dashboard = service.lead_dashboard(LEAD)

        assert data.asked_for == ["e2"]
        assert dashboard.unassigned[0].open_reassignment_request is None

    def test_an_empty_dashboard_asks_for_nothing(self, data):
        service.lead_dashboard(LEAD)

        assert data.asked_for == []
