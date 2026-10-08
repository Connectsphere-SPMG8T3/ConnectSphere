"""SCRUM-72: the Event Coordinator dashboard endpoint, `GET /events/dashboard/coordinator`.

The SPA's store (`frontend/src/features/events/store.js`) already fixes the
response shape and does the ranking, so these tests pin what the server
derives: which action items exist, each event's readiness, and that nothing
outside the caller's own assignments leaks in. Unassigned events belong to the
Event Coordinator Lead's queue, so a coordinator's dashboard says nothing about them.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.equipment import service as equipment_service
from app.modules.events import repository, service
from app.modules.events.service import ACTIVE_COORDINATOR_STATUSES
from app.modules.venues import service as venues_service

COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
DASHBOARD_URL = "/api/v1/events/dashboard/coordinator"


def event_row(event_id: str, status: str, **overrides) -> dict:
    row = {
        "id": event_id,
        "name": f"Event {event_id[-3:]}",
        "status": status,
        "starts_at": "2026-11-12T10:00:00+08:00",
        "submitted_at": "2026-09-20T09:00:00+08:00",
        "technical_readiness": "not_required",
        "preliminary_equipment_needs": None,
        "organiser": {"full_name": "Olivia Tan"},
    }
    row.update(overrides)
    return row


@pytest.fixture()
def data(monkeypatch):
    """Every read the dashboard makes, replaced by an in-memory answer."""
    state = SimpleNamespace(
        events=[],
        resubmissions={},
        bookings={},
        reserved=set(),
        calls={},
    )

    def list_coordinator_events(coordinator_id, statuses):
        state.calls["events"] = (coordinator_id, set(statuses))
        return state.events

    monkeypatch.setattr(repository, "list_coordinator_events", list_coordinator_events)
    monkeypatch.setattr(repository, "list_latest_resubmissions", lambda ids: state.resubmissions)
    monkeypatch.setattr(venues_service, "booking_statuses_by_event", lambda ids: state.bookings)
    monkeypatch.setattr(equipment_service, "reserved_event_ids", lambda ids: state.reserved)
    return state


def items_by_kind(dashboard) -> dict[str, list[str]]:
    kinds: dict[str, list[str]] = {}
    for item in dashboard.action_items:
        kinds.setdefault(item.kind.value, []).append(item.event_id)
    return kinds


class TestScope:
    def test_reads_only_the_callers_events_in_active_statuses(self, data):
        service.coordinator_dashboard(COORDINATOR_ID)

        coordinator_id, statuses = data.calls["events"]
        assert coordinator_id == COORDINATOR_ID
        assert statuses == {"under_review", "returned", "planning", "safety_review", "confirmed"}
        # Drafts are private to their organiser (DR-R2); terminal statuses aren't active.
        assert "draft" not in ACTIVE_COORDINATOR_STATUSES

    def test_nothing_assigned_is_an_empty_dashboard_not_an_error(self, data):
        dashboard = service.coordinator_dashboard(COORDINATOR_ID)

        assert dashboard.action_items == []
        assert dashboard.active_events == []


class TestActionItems:
    def test_under_review_without_a_resubmission_awaits_first_review(self, data):
        data.events = [event_row("e-001", "under_review")]

        dashboard = service.coordinator_dashboard(COORDINATOR_ID)

        [item] = dashboard.action_items
        assert item.kind.value == "awaiting_review"
        assert item.event_id == "e-001"
        assert item.event_name == "Event 001"
        assert item.organiser_name == "Olivia Tan"
        assert item.occurred_at.isoformat() == "2026-09-20T09:00:00+08:00"

    def test_a_resubmitted_request_is_a_clarification_response_not_a_first_review(self, data):
        data.events = [event_row("e-002", "under_review")]
        data.resubmissions = {"e-002": "2026-09-25T15:30:00+08:00"}

        dashboard = service.coordinator_dashboard(COORDINATOR_ID)

        assert items_by_kind(dashboard) == {"resubmitted": ["e-002"]}
        assert dashboard.action_items[0].occurred_at.isoformat() == "2026-09-25T15:30:00+08:00"

    def test_a_returned_request_is_waiting_on_the_organiser_so_needs_no_action(self, data):
        data.events = [event_row("e-003", "returned")]
        # A closed amendment from an earlier round must not make it look resubmitted.
        data.resubmissions = {"e-003": "2026-09-21T10:00:00+08:00"}

        dashboard = service.coordinator_dashboard(COORDINATOR_ID)

        assert dashboard.action_items == []
        assert [e.status.value for e in dashboard.active_events] == ["returned"]

    def test_a_technical_issue_on_a_planned_event_is_an_arrangement_issue(self, data):
        data.events = [
            event_row("e-004", "planning", technical_readiness="issue"),
            event_row("e-005", "confirmed", technical_readiness="issue"),
            event_row("e-006", "planning", technical_readiness="pending"),
        ]

        dashboard = service.coordinator_dashboard(COORDINATOR_ID)

        assert items_by_kind(dashboard) == {"arrangement_issue": ["e-004", "e-005"]}
        flags = {e.event_id: e.flags for e in dashboard.active_events}
        assert flags == {"e-004": ["technical_issue"], "e-005": ["technical_issue"], "e-006": []}

    def test_planning_and_confirmed_events_without_issues_need_no_action(self, data):
        data.events = [event_row("e-007", "planning"), event_row("e-008", "confirmed")]

        assert service.coordinator_dashboard(COORDINATOR_ID).action_items == []

    def test_an_event_without_an_organiser_row_still_appears(self, data):
        data.events = [event_row("e-009", "under_review", organiser=None)]

        [item] = service.coordinator_dashboard(COORDINATOR_ID).action_items
        assert item.organiser_name is None


class TestReadiness:
    def readiness(self, data, row):
        data.events = [row]
        [event] = service.coordinator_dashboard(COORDINATOR_ID).active_events
        return event.readiness

    def test_venue_is_ready_only_with_an_approved_booking(self, data):
        data.bookings = {"e-010": ["released", "approved"], "e-011": ["held"]}

        assert self.readiness(data, event_row("e-010", "planning")).venue.value == "ready"
        assert self.readiness(data, event_row("e-011", "planning")).venue.value == "pending"
        assert self.readiness(data, event_row("e-012", "planning")).venue.value == "pending"

    def test_equipment_not_required_when_the_event_asked_for_none(self, data):
        for needs in (None, "", "   "):
            row = event_row("e-013", "planning", preliminary_equipment_needs=needs)
            assert self.readiness(data, row).equipment.value == "not_required"

    def test_equipment_ready_once_reserved_and_pending_until_then(self, data):
        data.reserved = {"e-014"}

        ready = event_row("e-014", "planning", preliminary_equipment_needs="2 projectors")
        waiting = event_row("e-015", "planning", preliminary_equipment_needs="2 projectors")
        assert self.readiness(data, ready).equipment.value == "ready"
        assert self.readiness(data, waiting).equipment.value == "pending"

    def test_technical_readiness_is_passed_through(self, data):
        for value in ("not_required", "pending", "ready", "issue"):
            row = event_row("e-016", "planning", technical_readiness=value)
            assert self.readiness(data, row).technical.value == value


class TestUnassignedEvents:
    """Unassigned events are the Event Coordinator Lead's queue (customer
    clarification, REQUIREMENTS §6.5), not something a coordinator acts on."""

    def test_the_dashboard_carries_no_unassigned_figure(self, data):
        dashboard = service.coordinator_dashboard(COORDINATOR_ID)

        assert "unassigned_count" not in dashboard.model_dump()

    def test_no_query_counts_other_coordinators_or_unassigned_events(self):
        assert not hasattr(repository, "count_unassigned")


def chainable_query(rows, count=None) -> MagicMock:
    query = MagicMock()
    for method in ("select", "eq", "in_", "is_", "not_", "order"):
        getattr(query, method).return_value = query
    query.not_ = query
    query.execute.return_value = SimpleNamespace(data=rows, count=count)
    return query


class TestRepositoryQueries:
    """The query each read builds: mocked tests can't reach PostgREST, so pin the shape."""

    def test_coordinator_events_filter_by_caller_and_status_and_name_the_organiser_fk(self, monkeypatch):
        query = chainable_query([event_row("e-020", "planning")])
        admin = MagicMock()
        admin.table.return_value = query
        monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: admin)

        rows = repository.list_coordinator_events(COORDINATOR_ID, ["planning", "under_review"])

        admin.table.assert_called_once_with("events")
        assert "profiles!events_organiser_id_fkey(full_name)" in query.select.call_args.args[0]
        query.eq.assert_called_once_with("coordinator_id", COORDINATOR_ID)
        query.in_.assert_called_once_with("status", ["planning", "under_review"])
        assert [row["id"] for row in rows] == ["e-020"]

    def test_latest_resubmission_per_event(self, monkeypatch):
        query = chainable_query([
            {"event_id": "e-021", "resubmitted_at": "2026-09-25T10:00:00+00:00"},
            {"event_id": "e-021", "resubmitted_at": "2026-09-22T10:00:00+00:00"},
            {"event_id": "e-022", "resubmitted_at": "2026-09-23T10:00:00+00:00"},
        ])
        admin = MagicMock()
        admin.table.return_value = query
        monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: admin)

        latest = repository.list_latest_resubmissions(["e-021", "e-022"])

        admin.table.assert_called_once_with("amendment_requests")
        query.in_.assert_called_once_with("event_id", ["e-021", "e-022"])
        query.order.assert_called_once_with("resubmitted_at", desc=True)
        assert latest == {"e-021": "2026-09-25T10:00:00+00:00", "e-022": "2026-09-23T10:00:00+00:00"}

    def test_latest_resubmission_skips_the_query_with_no_events(self, monkeypatch):
        admin = MagicMock()
        monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: admin)

        assert repository.list_latest_resubmissions([]) == {}
        admin.table.assert_not_called()


class TestCrossModuleReads:
    def test_booking_statuses_are_grouped_by_event(self, monkeypatch):
        from app.modules.venues import repository as venues_repository

        monkeypatch.setattr(
            venues_repository,
            "list_booking_statuses",
            lambda ids: [
                {"event_id": "e-030", "status": "released"},
                {"event_id": "e-030", "status": "approved"},
                {"event_id": "e-031", "status": "held"},
            ],
        )

        assert venues_service.booking_statuses_by_event(["e-030", "e-031"]) == {
            "e-030": ["released", "approved"],
            "e-031": ["held"],
        }

    def test_reserved_event_ids_are_those_with_a_live_or_finished_reservation(self, monkeypatch):
        from app.modules.equipment import repository as equipment_repository

        seen = {}

        def list_reserved_event_ids(ids, statuses):
            seen["args"] = (list(ids), set(statuses))
            return ["e-040"]

        monkeypatch.setattr(equipment_repository, "list_reserved_event_ids", list_reserved_event_ids)

        assert equipment_service.reserved_event_ids(["e-040", "e-041"]) == {"e-040"}
        assert seen["args"] == (["e-040", "e-041"], {"confirmed", "completed"})


class TestApi:
    def test_coordinator_gets_the_dashboard(self, client, auth_headers, authenticate_as, data):
        authenticate_as("event_coordinator", COORDINATOR_ID)
        data.events = [event_row("e-050", "under_review")]

        response = client.get(DASHBOARD_URL, headers=auth_headers)

        # 200, not 422: the route is declared above `/{event_id}`, which is typed UUID.
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"action_items", "active_events"}
        assert body["action_items"] == [{
            "event_id": "e-050",
            "event_name": "Event 050",
            "kind": "awaiting_review",
            "starts_at": "2026-11-12T10:00:00+08:00",
            "occurred_at": "2026-09-20T09:00:00+08:00",
            "organiser_name": "Olivia Tan",
        }]
        assert body["active_events"] == [{
            "event_id": "e-050",
            "event_name": "Event 050",
            "status": "under_review",
            "starts_at": "2026-11-12T10:00:00+08:00",
            "flags": [],
            "readiness": {"venue": "pending", "equipment": "not_required", "technical": "not_required"},
        }]
        assert data.calls["events"][0] == COORDINATOR_ID

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee"])
    def test_every_other_active_role_is_forbidden(self, client, auth_headers, authenticate_as, data, role):
        authenticate_as(role)

        response = client.get(DASHBOARD_URL, headers=auth_headers)

        assert response.status_code == 403
        assert "events" not in data.calls

    def test_no_token_is_401(self, client, data):
        assert client.get(DASHBOARD_URL).status_code == 401


def test_safety_review_remains_active_and_reports_technical_issues(data):
    """SCRUM-82: sending does not remove the coordinator's event."""
    data.events = [event_row("e-safe", "safety_review", technical_readiness="issue")]
    dashboard = service.coordinator_dashboard(COORDINATOR_ID)
    assert dashboard.active_events[0].status.value == "safety_review"
    assert items_by_kind(dashboard) == {"arrangement_issue": ["e-safe"]}
