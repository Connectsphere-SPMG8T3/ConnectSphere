"""Story 62 change history, through the HTTP API with the repository mocked."""

import pytest

from app.modules.equipment import service as equipment_service
from app.modules.events import repository
from app.modules.venues import repository as venues_repository
from app.modules.venues import service as venues_service
from tests.test_event_amendment_api import (  # noqa: F401 (pytest fixtures)
    EVENT_ID,
    ORGANISER_ID,
    act_as,
    acting_as_another_role,
    events,
    resubmit_request,
    returned,
)


# Captured before conftest's offline default replaces it, so the window rule runs for real.
ORIGINAL_EVENT_VENUE_EDITS = getattr(venues_service, "event_venue_edits", None)


class TestEditsAreRecorded:
    """AC1: an edit to a returned request is saved through edit_event, which records it."""

    def test_an_edit_to_a_returned_request_is_recorded_as_the_organiser(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        response = client.patch(f"/api/v1/events/{EVENT_ID}", json={"description": "Now with a keynote"},
                                headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["description"] == "Now with a keynote"
        assert events["edits"] == [{"actor_id": ORGANISER_ID, "values": {"description": "Now with a keynote"},
                                    "from_statuses": ["returned"]}]

    def test_edits_sent_with_a_resubmission_are_recorded(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers, expected_attendance=40)

        assert response.status_code == 200
        assert events["edits"] == [{"actor_id": ORGANISER_ID, "values": {"expected_attendance": 40},
                                    "from_statuses": ["returned"]}]

    def test_an_edit_to_a_draft_is_not_recorded(self, client, auth_headers, act_as, events):
        events["store"][EVENT_ID]["status"] = "draft"
        act_as("event_organiser", ORGANISER_ID)

        response = client.patch(f"/api/v1/events/{EVENT_ID}", json={"description": "Draft text"},
                                headers=auth_headers)

        assert response.status_code == 200
        assert events["edits"] == []
        assert events["updates"] == [{"description": "Draft text"}]

    def test_a_stale_edit_to_a_returned_request_is_refused(self, client, auth_headers, act_as, events,
                                                           monkeypatch):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)
        monkeypatch.setattr(repository, "edit_event", lambda *args: None)

        response = client.patch(f"/api/v1/events/{EVENT_ID}", json={"description": "Too late"},
                                headers=auth_headers)

        assert response.status_code == 409
        assert events["updates"] == []


COORDINATOR = {"id": "a0000000-0000-4000-8000-000000000002", "full_name": "Marcus Lim"}
ORGANISER = {"id": ORGANISER_ID, "full_name": "Olivia Tan"}
EDIT_ROWS = [
    {"id": "e2", "field": "description", "old_value": None, "new_value": "Now with a keynote",
     "at": "2026-10-30T03:00:00+00:00", "actor": ORGANISER},
    {"id": "e1", "field": "expected_attendance", "old_value": 12, "new_value": 40,
     "at": "2026-10-30T02:00:00+00:00", "actor": ORGANISER},
]
STATUS_ROWS = [
    {"id": "h1", "from_status": "returned", "to_status": "under_review", "reason": "Attendance is now 40",
     "at": "2026-10-30T02:30:00+00:00", "actor": ORGANISER},
]


@pytest.fixture()
def history(monkeypatch, events):
    monkeypatch.setattr(repository, "list_status_history", lambda event_id: [dict(row) for row in STATUS_ROWS])
    monkeypatch.setattr(repository, "list_assignment_history", lambda event_id: [])
    monkeypatch.setattr(repository, "list_edit_history", lambda event_id: [dict(row) for row in EDIT_ROWS])
    return events


def read_history(client, auth_headers):
    response = client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers)
    assert response.status_code == 200
    return response.json()["entries"]


class TestEditEntries:
    """AC1, AC2: each edit shows what changed, from what to what, who and when, newest first."""

    @pytest.mark.parametrize("role, user_id", [("event_organiser", ORGANISER_ID),
                                               ("event_coordinator", COORDINATOR["id"])])
    def test_edits_join_the_history_in_time_order(self, client, auth_headers, act_as, history, role, user_id):
        act_as(role, user_id)

        entries = read_history(client, auth_headers)

        assert [entry["id"] for entry in entries] == ["e2", "h1", "e1"]
        edit = entries[0]
        assert edit["kind"] == "edit"
        assert edit["field"] == "description"
        assert edit["old_value"] is None
        assert edit["new_value"] == "Now with a keynote"
        assert edit["actor"] == ORGANISER
        assert entries[2]["old_value"] == 12 and entries[2]["new_value"] == 40

    def test_other_entries_keep_their_shape(self, client, auth_headers, act_as, history):
        act_as("event_organiser", ORGANISER_ID)

        status_entry = read_history(client, auth_headers)[1]

        assert {"field", "old_value", "new_value"}.isdisjoint(status_entry)


SAFETY_ROWS = [
    {"id": "s1", "event_id": EVENT_ID, "decision": "changes_requested", "comment": "Officer's own working note",
     "organiser_comment": "Move the stage back from the exit",
     "reason_code": None, "affected_booking_ids": [], "affected_equipment_request_ids": [], "rejected_venue_ids": [],
     "decided_by": "a0000000-0000-4000-8000-000000000006", "decided_at": "2026-10-30T04:00:00+00:00",
     "decided_by_name": "Hafiz Ismail"},
]


@pytest.fixture()
def safety_history(monkeypatch, history):
    monkeypatch.setattr(repository, "list_safety_decisions", lambda event_id: [dict(row) for row in SAFETY_ROWS])
    return history


class TestSafetyDecisionEntries:
    """AC5, AC6 (CR-108): safety decisions feed the history. The organiser sees the outcome, who,
    when and the organiser comment; the private note is the coordinator's and the officers' only."""

    def test_the_coordinator_sees_the_organiser_comment_and_the_private_note(self, client, auth_headers, act_as, safety_history):
        act_as("event_coordinator", COORDINATOR["id"])

        decision = read_history(client, auth_headers)[0]

        assert decision["id"] == "s1"
        assert decision["kind"] == "safety_decision"
        assert decision["decision"] == "changes_requested"
        assert decision["reason"] == "Move the stage back from the exit"
        assert decision["private_note"] == "Officer's own working note"
        assert decision["actor"] == {"id": "a0000000-0000-4000-8000-000000000006", "full_name": "Hafiz Ismail"}

    def test_the_organiser_sees_the_outcome_and_the_organiser_comment_never_the_private_note(
            self, client, auth_headers, act_as, safety_history):
        act_as("event_organiser", ORGANISER_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers)

        decision = response.json()["entries"][0]
        assert decision["kind"] == "safety_decision"
        assert decision["decision"] == "changes_requested"
        assert decision["reason"] == "Move the stage back from the exit"
        assert "private_note" not in decision
        assert "Officer's own working note" not in response.text

    def test_a_decision_recorded_before_organiser_comments_has_no_reason(self, client, auth_headers, act_as, monkeypatch, history):
        legacy = {k: v for k, v in SAFETY_ROWS[0].items() if k != "organiser_comment"}
        monkeypatch.setattr(repository, "list_safety_decisions", lambda event_id: [dict(legacy)])
        act_as("event_organiser", ORGANISER_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers)

        assert response.json()["entries"][0]["reason"] is None
        assert "Officer's own working note" not in response.text


BOOKING_ROWS = [
    {"id": "b1", "action": "approved", "venue_name": "Hall A", "reason": None,
     "actor": {"id": "a0000000-0000-4000-8000-000000000003", "full_name": "Priya Nair"},
     "at": "2026-10-30T05:00:00+00:00"},
]


@pytest.fixture()
def booking_history(monkeypatch, history):
    monkeypatch.setattr(venues_service, "event_booking_history", lambda event_id: [dict(row) for row in BOOKING_ROWS])
    return history


class TestBookingEntries:
    """AC5: venue booking history feeds the event's history. AC3: it is staff-only."""

    def test_the_coordinator_sees_what_happened_to_each_booking(self, client, auth_headers, act_as, booking_history):
        act_as("event_coordinator", COORDINATOR["id"])

        booking = read_history(client, auth_headers)[0]

        assert booking["id"] == "b1"
        assert booking["kind"] == "booking"
        assert booking["action"] == "approved"
        assert booking["venue_name"] == "Hall A"
        assert booking["actor"]["full_name"] == "Priya Nair"
        assert "old_preparation_stage" not in booking and "new_preparation_stage" not in booking

    def test_a_preparation_update_names_the_stage_it_moved_from_and_to(
        self, client, auth_headers, act_as, monkeypatch, history
    ):
        """CR-109 AC5: the coordinator reads the stage change, not just that one happened."""
        row = {"id": "b2", "action": "preparation", "venue_name": "Hall A", "reason": None,
               "old_preparation_stage": "not_started", "new_preparation_stage": "in_progress",
               "actor": {"id": "a0000000-0000-4000-8000-000000000003", "full_name": "Priya Nair"},
               "at": "2026-10-30T05:00:00+00:00"}
        monkeypatch.setattr(venues_service, "event_booking_history", lambda event_id: [dict(row)])
        act_as("event_coordinator", COORDINATOR["id"])

        booking = read_history(client, auth_headers)[0]

        assert booking["action"] == "preparation"
        assert booking["old_preparation_stage"] == "not_started"
        assert booking["new_preparation_stage"] == "in_progress"

    def test_the_organiser_never_gets_booking_entries(self, client, auth_headers, act_as, booking_history):
        act_as("event_organiser", ORGANISER_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers)

        assert "booking" not in [entry["kind"] for entry in response.json()["entries"]]
        assert "Hall A" not in response.text


TECHNICAL_ROWS = [
    {"id": "t1", "action": "preparation", "line_label": None, "detail": None,
     "actor": {"id": "a0000000-0000-4000-8000-000000000004", "full_name": "Daniel Wong"},
     "at": "2026-10-30T06:00:00+00:00"},
]


@pytest.fixture()
def technical_history(monkeypatch, history):
    monkeypatch.setattr(equipment_service, "event_technical_history",
                        lambda event_id: [dict(row) for row in TECHNICAL_ROWS])
    return history


class TestTechnicalEntries:
    """AC1, AC5: equipment and technical preparation updates feed the history. AC3: staff-only."""

    def test_the_coordinator_sees_technical_updates(self, client, auth_headers, act_as, technical_history):
        act_as("event_coordinator", COORDINATOR["id"])

        update = read_history(client, auth_headers)[0]

        assert update["id"] == "t1"
        assert update["kind"] == "technical"
        assert update["action"] == "preparation"
        assert update["actor"]["full_name"] == "Daniel Wong"

    def test_the_organiser_never_gets_technical_entries(self, client, auth_headers, act_as, technical_history):
        act_as("event_organiser", ORGANISER_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers)

        assert "technical" not in [entry["kind"] for entry in response.json()["entries"]]
        assert "Daniel Wong" not in response.text


class TestActiveRole:
    """SCRUM-76: the history follows the session's active role, never every role held.
    Here one account both owns the event and is its assigned coordinator."""

    @pytest.fixture()
    def own_and_assigned(self, monkeypatch, safety_history, booking_history, technical_history):
        safety_history["store"][EVENT_ID]["organiser_id"] = COORDINATOR["id"]
        return safety_history

    def test_acting_as_organiser_gets_only_the_organiser_view(self, client, auth_headers, monkeypatch,
                                                              own_and_assigned):
        acting_as_another_role(monkeypatch, COORDINATOR["id"], holds="event_coordinator", acts_as="event_organiser")

        response = client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers)

        assert response.status_code == 200
        kinds = {entry["kind"] for entry in response.json()["entries"]}
        assert kinds.isdisjoint({"booking", "technical"})
        assert "Officer's own working note" not in response.text

    def test_acting_as_coordinator_gets_every_entry(self, client, auth_headers, monkeypatch, own_and_assigned):
        acting_as_another_role(monkeypatch, COORDINATOR["id"], holds="event_organiser", acts_as="event_coordinator")

        kinds = {entry["kind"] for entry in read_history(client, auth_headers)}

        assert {"booking", "technical", "safety_decision", "edit", "status"} <= kinds

    def test_acting_as_venue_staff_is_forbidden(self, client, auth_headers, monkeypatch, own_and_assigned):
        acting_as_another_role(monkeypatch, COORDINATOR["id"], holds="event_coordinator", acts_as="venue_staff")

        assert client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers).status_code == 403


BOOKINGS = [
    # Booked 1 Oct, released 20 Oct.
    {"venue_id": "v1", "venue_name": "Hall A", "status": "released",
     "created_at": "2026-10-01T00:00:00+00:00", "updated_at": "2026-10-20T00:00:00+00:00"},
    # Held since 25 Oct.
    {"venue_id": "v2", "venue_name": "Hall B", "status": "held",
     "created_at": "2026-10-25T00:00:00+00:00", "updated_at": "2026-10-25T00:00:00+00:00"},
]
VENUE_EDITS = {
    "v1": [
        {"id": "ve-after", "before": {"capacity": 100}, "after": {"capacity": 80},
         "created_at": "2026-10-21T00:00:00+00:00", "actor": {"id": "vs", "full_name": "Priya Nair"}},
        {"id": "ve-during", "before": {"capacity": 120}, "after": {"capacity": 100},
         "created_at": "2026-10-10T00:00:00+00:00", "actor": {"id": "vs", "full_name": "Priya Nair"}},
        {"id": "ve-before", "before": {"capacity": 150}, "after": {"capacity": 120},
         "created_at": "2026-09-01T00:00:00+00:00", "actor": {"id": "vs", "full_name": "Priya Nair"}},
    ],
    "v2": [
        {"id": "ve-held", "before": {"restrictions": None}, "after": {"restrictions": "No food"},
         "created_at": "2026-10-28T00:00:00+00:00", "actor": None},
    ],
}


@pytest.fixture()
def venue_edits(monkeypatch, history):
    monkeypatch.setattr(venues_repository, "list_event_bookings_for_history", lambda event_id: [dict(b) for b in BOOKINGS])
    monkeypatch.setattr(venues_repository, "list_edit_history", lambda venue_id: [dict(e) for e in VENUE_EDITS[venue_id]])
    monkeypatch.setattr(venues_service, "event_venue_edits", ORIGINAL_EVENT_VENUE_EDITS)
    return history


class TestVenueEditEntries:
    """AC5, REQUIREMENTS §9 item 113 [Assumption]: a venue edit joins the event's history
    only if the event held or had booked that venue at the time, and only for the coordinator."""

    def test_the_coordinator_sees_edits_made_while_the_event_held_the_venue(self, client, auth_headers, act_as,
                                                                           venue_edits):
        act_as("event_coordinator", COORDINATOR["id"])

        edits = [entry for entry in read_history(client, auth_headers) if entry["kind"] == "venue_edit"]

        assert [edit["id"] for edit in edits] == ["ve-held", "ve-during"]
        during = edits[1]
        assert during["venue_name"] == "Hall A"
        assert during["old_value"] == {"capacity": 120}
        assert during["new_value"] == {"capacity": 100}
        assert during["actor"]["full_name"] == "Priya Nair"

    def test_the_organiser_never_gets_venue_edits(self, client, auth_headers, act_as, venue_edits):
        act_as("event_organiser", ORGANISER_ID)

        kinds = [entry["kind"] for entry in read_history(client, auth_headers)]

        assert "venue_edit" not in kinds
