"""SCRUM-81: what a reassignment does to the event, through the HTTP API with the
repository mocked. A stateful in-memory events table stands in for `reassign_event`,
`transition_event` and `resubmit_event`, each mirroring its RPC's guards. The RPCs' own
behaviour (locking, history, notices, the coordinator kept on resubmit) is checked against
the real database by supabase/verification/reassignment_effects_checks.sql.

AC1 (the current assignee is refused), AC3 (the previous coordinator loses access at once),
AC7 (the new one has it at once), AC9 (status unchanged), AC12 (a returned request, once
resubmitted, stays with the coordinator assigned at that time), AC13 (events assigned
before the Lead role existed)."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.events import repository
from app.modules.venues import repository as venues_repository

LEAD = "a0000000-0000-4000-8000-0000000000a1"
OTHER_LEAD = "a0000000-0000-4000-8000-0000000000a2"
ORGANISER = "a0000000-0000-4000-8000-000000000001"
OLD = "a0000000-0000-4000-8000-000000000002"
NEW = "a0000000-0000-4000-8000-000000000003"
EVENT = "e0000000-0000-4000-8000-000000000081"
ACTIVE = ["under_review", "returned", "planning", "safety_review", "confirmed", "preparation"]
OPEN_AMENDMENT = {"id": "a1", "message": "Please confirm the attendance",
                  "flagged_fields": ["expected_attendance"], "returned_at": "2026-11-02T03:00:00+00:00"}


def event_row(status="under_review", coordinator_id=OLD, assigned_by=LEAD):
    now = datetime.now(timezone.utc).isoformat()
    starts = datetime.now(timezone.utc) + timedelta(days=30)
    return {
        "id": EVENT, "organiser_id": ORGANISER, "coordinator_id": coordinator_id, "assigned_by": assigned_by,
        "status": status, "event_timezone": "Asia/Singapore", "name": "Partner Summit",
        "purpose": "Quarterly partner meeting", "description": None,
        "starts_at": starts.isoformat(), "ends_at": (starts + timedelta(hours=2)).isoformat(),
        "expected_attendance": 12, "layout_preference": "boardroom", "facilities_required": [],
        "accessibility_needs": None, "preliminary_equipment_needs": None,
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "technical_readiness": "not_required", "submitted_at": now, "version": 3,
        "created_at": now, "updated_at": now,
    }


@pytest.fixture()
def events(monkeypatch):
    state = {"store": {EVENT: event_row()}, "lead_ids": {LEAD}, "transitions": [], "reassigns": [],
             "resubmit_notified": [], "amendment": None}

    def get_event(event_id):
        return deepcopy(state["store"].get(event_id))

    def reassign_event(event_id, lead_id, coordinator_id, expected_version, **kwargs):
        state["reassigns"].append({"lead_id": lead_id, "coordinator_id": coordinator_id, **kwargs})
        row = state["store"].get(event_id)
        if row is None or row["version"] != expected_version or row["status"] not in kwargs["active_statuses"]:
            return None
        row.update(coordinator_id=coordinator_id, assigned_by=lead_id, version=row["version"] + 1)
        return deepcopy(row)

    def transition_event(event_id, actor_id, from_statuses, to_status, expected_version, **kwargs):
        state["transitions"].append({"actor_id": actor_id, "to_status": to_status})
        row = state["store"].get(event_id)
        if row is None or row["version"] != expected_version or row["status"] not in from_statuses:
            return None
        row.update(status=to_status, version=row["version"] + 1)
        return deepcopy(row)

    def resubmit_event(event_id, actor_id, from_statuses, to_status, expected_version, *, note, notify_message):
        row = state["store"].get(event_id)
        if row is None or row["version"] != expected_version or row["status"] not in from_statuses:
            return None
        row.update(status=to_status, version=row["version"] + 1)
        state["amendment"] = None
        # The RPC notifies the coordinator on the row at that moment, and never changes it.
        state["resubmit_notified"].append(row["coordinator_id"])
        return deepcopy(row)

    monkeypatch.setattr(repository, "get_event", get_event)
    monkeypatch.setattr(repository, "get_lead_event", get_event)
    monkeypatch.setattr(repository, "list_lead_ids", lambda: state["lead_ids"])
    monkeypatch.setattr(repository, "get_coordinator",
                        lambda pid: {"id": pid, "full_name": "Priya Nair"} if pid in (OLD, NEW) else None)
    monkeypatch.setattr(repository, "reassign_event", reassign_event)
    monkeypatch.setattr(repository, "transition_event", transition_event)
    monkeypatch.setattr(repository, "resubmit_event", resubmit_event)
    monkeypatch.setattr(repository, "get_open_amendment", lambda event_id: deepcopy(state["amendment"]))
    monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: None)
    monkeypatch.setattr(venues_repository, "list_booking_statuses", lambda event_ids: [])
    return state


def reassign(client, auth_headers, authenticate_as, coordinator_id=NEW, version=3, lead=LEAD):
    authenticate_as("event_coordinator_lead", lead)
    return client.post(f"/api/v1/events/{EVENT}/reassign",
                       json={"coordinator_id": coordinator_id, "expected_version": version}, headers=auth_headers)


class TestOnlyTheLeadReassigns:
    """AC1: every other role is refused, the current assignee included."""

    def test_the_current_assignee_is_refused_and_nothing_changes(self, client, auth_headers, authenticate_as, events):
        authenticate_as("event_coordinator", OLD)
        response = client.post(f"/api/v1/events/{EVENT}/reassign",
                               json={"coordinator_id": NEW, "expected_version": 3}, headers=auth_headers)
        assert response.status_code == 403
        assert events["reassigns"] == []
        assert events["store"][EVENT]["coordinator_id"] == OLD

    def test_the_organiser_is_refused(self, client, auth_headers, authenticate_as, events):
        authenticate_as("event_organiser", ORGANISER)
        response = client.post(f"/api/v1/events/{EVENT}/reassign",
                               json={"coordinator_id": NEW, "expected_version": 3}, headers=auth_headers)
        assert response.status_code == 403
        assert events["reassigns"] == []


class TestThePreviousCoordinatorLosesAccessAtOnce:
    """AC3: a write after the reassignment is refused, as from a page that was open before it."""

    WRITES = [
        ("approve", "/approve", None),
        ("reject", "/reject", {"reason": "Venue unavailable on that date"}),
        ("return", "/return", {"message": "Please confirm", "flagged_fields": ["expected_attendance"]}),
        ("send for safety check", "/send-for-safety-check", None),
        ("request reassignment", "/reassignment-request", {"reason": "I am on leave"}),
    ]

    @pytest.mark.parametrize("name,path,body", WRITES, ids=[w[0] for w in WRITES])
    def test_a_write_by_the_previous_coordinator_is_403_and_changes_nothing(
        self, client, auth_headers, authenticate_as, events, name, path, body
    ):
        assert reassign(client, auth_headers, authenticate_as).status_code == 200
        authenticate_as("event_coordinator", OLD)

        response = client.post(f"/api/v1/events/{EVENT}{path}", json=body, headers=auth_headers)

        assert response.status_code == 403
        assert events["transitions"] == []
        assert events["store"][EVENT]["status"] == "under_review"

    def test_the_previous_coordinator_can_no_longer_read_the_event(self, client, auth_headers, authenticate_as, events):
        reassign(client, auth_headers, authenticate_as)
        authenticate_as("event_coordinator", OLD)
        assert client.get(f"/api/v1/events/{EVENT}", headers=auth_headers).status_code == 403


class TestTheNewCoordinatorHasAccessAtOnce:
    """AC7."""

    def test_the_new_coordinator_reads_and_decides_straight_away(self, client, auth_headers, authenticate_as, events):
        reassign(client, auth_headers, authenticate_as)
        authenticate_as("event_coordinator", NEW)

        assert client.get(f"/api/v1/events/{EVENT}", headers=auth_headers).status_code == 200
        approved = client.post(f"/api/v1/events/{EVENT}/approve", headers=auth_headers)

        assert approved.status_code == 200
        assert events["transitions"] == [{"actor_id": NEW, "to_status": "planning"}]


class TestReassignmentLeavesTheStatusAlone:
    """AC9: the status is unchanged, and the call asks for no status change or history row."""

    @pytest.mark.parametrize("status", ACTIVE)
    def test_status_is_unchanged_in_every_active_status(self, client, auth_headers, authenticate_as, events, status):
        events["store"][EVENT]["status"] = status

        response = reassign(client, auth_headers, authenticate_as)

        assert response.status_code == 200
        assert response.json()["status"] == status
        assert events["store"][EVENT]["status"] == status
        [call] = events["reassigns"]
        assert "to_status" not in call and "reason" not in call


class TestAReturnedRequestStaysWithItsCoordinator:
    """AC12 (QA3-15, LA-R9): reassigned while returned, then resubmitted, it goes to the
    coordinator assigned at that time, not back to the queue."""

    def returned(self, events):
        events["store"][EVENT]["status"] = "returned"
        events["amendment"] = deepcopy(OPEN_AMENDMENT)

    def test_a_returned_request_can_be_reassigned_and_stays_returned(self, client, auth_headers, authenticate_as, events):
        self.returned(events)
        response = reassign(client, auth_headers, authenticate_as)
        assert response.status_code == 200
        assert response.json()["status"] == "returned"
        assert response.json()["coordinator_id"] == NEW

    def test_resubmitting_goes_to_the_new_coordinator_who_can_then_decide(
        self, client, auth_headers, authenticate_as, events
    ):
        self.returned(events)
        reassign(client, auth_headers, authenticate_as)

        authenticate_as("event_organiser", ORGANISER)
        resubmitted = client.post(f"/api/v1/events/{EVENT}/resubmit",
                                  json={"resubmission_note": "Attendance is now 40"}, headers=auth_headers)

        assert resubmitted.status_code == 200
        body = resubmitted.json()
        assert body["status"] == "under_review"
        assert body["coordinator_id"] == NEW
        assert events["resubmit_notified"] == [NEW]

        authenticate_as("event_coordinator", NEW)
        assert client.post(f"/api/v1/events/{EVENT}/approve", headers=auth_headers).status_code == 200
        authenticate_as("event_coordinator", OLD)
        assert client.post(f"/api/v1/events/{EVENT}/approve", headers=auth_headers).status_code == 403

    def test_without_a_reassignment_it_returns_to_the_same_coordinator(self, client, auth_headers, authenticate_as, events):
        self.returned(events)
        authenticate_as("event_organiser", ORGANISER)
        body = client.post(f"/api/v1/events/{EVENT}/resubmit",
                           json={"resubmission_note": "Attendance is now 40"}, headers=auth_headers).json()
        assert body["status"] == "under_review" and body["coordinator_id"] == OLD


class TestEventsAssignedBeforeTheLeadRoleExisted:
    """AC13 (QA3-38): `assigned_by` is null; any Lead can reassign, and then owns the scope."""

    @pytest.mark.parametrize("lead", [LEAD, OTHER_LEAD])
    def test_any_lead_can_reassign_and_becomes_the_assigning_lead(
        self, client, auth_headers, authenticate_as, events, lead
    ):
        events["lead_ids"] = {LEAD, OTHER_LEAD}
        events["store"][EVENT]["assigned_by"] = None

        response = reassign(client, auth_headers, authenticate_as, lead=lead)

        assert response.status_code == 200
        assert response.json()["coordinator_id"] == NEW
        assert events["store"][EVENT]["assigned_by"] == lead

    def test_once_reassigned_the_other_lead_is_out_of_scope(self, client, auth_headers, authenticate_as, events):
        events["lead_ids"] = {LEAD, OTHER_LEAD}
        events["store"][EVENT]["assigned_by"] = None
        reassign(client, auth_headers, authenticate_as, lead=LEAD)

        again = reassign(client, auth_headers, authenticate_as, coordinator_id=OLD, version=4, lead=OTHER_LEAD)

        assert again.status_code == 403
