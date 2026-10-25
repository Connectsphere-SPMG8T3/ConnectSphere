"""Story 37: the assigned coordinator approves or rejects the organiser's open change
request, through the HTTP API with the repository mocked. The RPCs' own guards, moves
and markers are checked against the real database by
supabase/verification/change_request_decision_checks.sql."""

from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.modules.events import repository
from app.modules.venues import repository as venues_repository
from app.modules.venues.schemas import LayoutOption, VenueLayout, VenueSummary
from tests.conftest import make_table_mock

ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_COORDINATOR_ID = "a0000000-0000-4000-8000-000000000009"
EVENT_ID = "e0000000-0000-4000-8000-000000000371"
REQUEST_ID = "c0000000-0000-4000-8000-000000000371"
SPACE_ID = "f0000000-0000-4000-8000-000000000371"
BOOKING_ID = "d0000000-0000-4000-8000-000000000371"
VENUE_ID = "b0000000-0000-4000-8000-000000000001"
REQUEST_REASON = "More guests confirmed"
REJECTION_REASON = "The venue can't take more people"
FUTURE_START = "2026-11-12T10:00:00+08:00"


def event_row(status="confirmed", starts_at=FUTURE_START):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": COORDINATOR_ID,
        "status": status, "event_timezone": "Asia/Singapore", "name": "Partner Summit",
        "purpose": "Quarterly partner meeting", "description": None,
        "starts_at": starts_at, "ends_at": "2026-11-12T12:00:00+08:00",
        "expected_attendance": 80, "layout_preference": "theatre", "facilities_required": [],
        "accessibility_needs": None, "preliminary_equipment_needs": None,
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "technical_readiness": "not_required", "submitted_at": now, "version": 3,
        "created_at": now, "updated_at": now,
        "spaces": [{"id": SPACE_ID, "event_id": EVENT_ID, "label": "Main hall", "expected_pax": 80,
                    "layout_preference": "theatre", "facilities_required": [], "starts_at": None,
                    "ends_at": None, "version": 1, "is_primary": True}],
    }


OPEN_REQUEST = {
    "id": REQUEST_ID, "kind": "change", "status": "open", "reason": REQUEST_REASON,
    "changes": {"event": [{"field": "expected_attendance", "before": 80, "after": 120}], "spaces": []},
    "significant": True,
    "requested_by": {"id": ORGANISER_ID, "full_name": "Olivia Organiser"},
    "requested_at": "2026-10-24T09:00:00+00:00",
}


@pytest.fixture()
def events(monkeypatch):
    """An in-memory event with its open change request."""
    store = {EVENT_ID: event_row()}
    request = {"value": deepcopy(OPEN_REQUEST)}
    monkeypatch.setattr(repository, "get_event", lambda event_id: deepcopy(store.get(event_id)))
    monkeypatch.setattr(repository, "get_open_change_request", lambda event_id: deepcopy(request["value"]))
    return {"store": store, "request": request}


@pytest.fixture()
def rejections(monkeypatch, events):
    """A fake `reject_event_change` that answers like the RPC."""
    calls = []
    outcome = {"value": "ok"}

    def reject_event_change(event_id, actor_id, reason, from_statuses, organiser_message):
        calls.append({"event_id": event_id, "actor_id": actor_id, "reason": reason,
                      "from_statuses": from_statuses, "organiser_message": organiser_message})
        return {"outcome": outcome["value"]}

    monkeypatch.setattr(repository, "reject_event_change", reject_event_change)
    return {"calls": calls, "outcome": outcome}


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role="event_coordinator", user_id=COORDINATOR_ID):
        return authenticate_as(role, user_id=user_id)
    return _act_as


def reject(client, auth_headers, reason=REJECTION_REASON):
    return client.post(f"/api/v1/events/{EVENT_ID}/change-request/reject",
                       json={"reason": reason}, headers=auth_headers)


class TestRejectChangeRequest:
    def test_rejecting_keeps_the_event_as_it_was(self, client, auth_headers, act_as, events, rejections):
        act_as()

        response = reject(client, auth_headers)

        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
        assert response.json()["expected_attendance"] == 80
        [call] = rejections["calls"]
        assert call["event_id"] == EVENT_ID
        assert call["actor_id"] == COORDINATOR_ID
        assert call["reason"] == REJECTION_REASON

    def test_the_rpc_rechecks_the_decidable_statuses(self, client, auth_headers, act_as, events, rejections):
        """AC8: the RPC refuses under the lock if the event moved to a closed status."""
        act_as()

        reject(client, auth_headers)

        assert rejections["calls"][0]["from_statuses"] == [
            "confirmed", "planning", "preparation", "safety_review", "submitted", "under_review"]

    def test_the_organiser_is_told_why(self, client, auth_headers, act_as, events, rejections):
        """AC4, CR-R3."""
        act_as()

        reject(client, auth_headers)

        assert rejections["calls"][0]["organiser_message"] == (
            f'Your requested changes to "Partner Summit" were rejected: {REJECTION_REASON}')

    def test_the_reason_is_trimmed(self, client, auth_headers, act_as, events, rejections):
        act_as()

        reject(client, auth_headers, reason=f"  {REJECTION_REASON}  ")

        assert rejections["calls"][0]["reason"] == REJECTION_REASON

    @pytest.mark.parametrize("reason", ["", "   ", "x" * 1001, None])
    def test_a_missing_blank_or_overlong_reason_is_rejected(self, client, auth_headers, act_as, events,
                                                            rejections, reason):
        """CR-R3."""
        act_as()

        response = reject(client, auth_headers, reason=reason)

        assert response.status_code == 422
        assert rejections["calls"] == []

    def test_without_an_open_request_there_is_nothing_to_reject(self, client, auth_headers, act_as, events,
                                                                rejections):
        events["request"]["value"] = None
        act_as()

        response = reject(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "There is no open change request for this event."
        assert rejections["calls"] == []

    @pytest.mark.parametrize("status", ["completed", "cancelled", "rejected"])
    def test_a_closed_event_takes_no_decision(self, client, auth_headers, act_as, events, rejections, status):
        """AC8: the event and the request stay as they were."""
        events["store"][EVENT_ID]["status"] = status
        act_as()

        response = reject(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"A change request can't be decided on an event that is {status}."
        assert rejections["calls"] == []

    def test_a_started_event_takes_no_decision(self, client, auth_headers, act_as, events, rejections):
        """Q5, as CR-R10."""
        events["store"][EVENT_ID]["starts_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        act_as()

        response = reject(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "This event has already started, so its change request can't be decided."
        assert rejections["calls"] == []

    @pytest.mark.parametrize(("outcome", "status_code", "detail"), [
        ("no_open_request", 409, "There is no open change request for this event."),
        ("not_assigned", 403, None),
        ("not_found", 404, None),
        ("started", 409, "This event has already started, so its change request can't be decided."),
        ("status_changed", 409, "This event was updated by someone else. Reload."),
    ])
    def test_the_rpc_recheck_under_the_lock_decides(self, client, auth_headers, act_as, events, rejections,
                                                    outcome, status_code, detail):
        rejections["outcome"]["value"] = outcome
        act_as()

        response = reject(client, auth_headers)

        assert response.status_code == status_code
        if detail:
            assert response.json()["detail"] == detail


ORDINARY_REQUEST = {
    **OPEN_REQUEST, "significant": False,
    "changes": {"event": [{"field": "name", "before": "Partner Summit", "after": "Partner Forum"}],
                "spaces": [{"space_id": SPACE_ID, "label": "Main hall",
                            "fields": [{"field": "label", "before": "Main hall", "after": "Great hall"}]}]},
}


def venue(capacity=200, banquet=None):
    layouts = [LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=None)]
    if banquet:
        layouts.append(LayoutOption(layout=VenueLayout.banquet, capacity_for_layout=banquet))
    return VenueSummary(id=VENUE_ID, name="Grand Ballroom", location="Marina", capacity=capacity, layouts=layouts,
                        facilities=[], accessibility_features=[], opens_at=time(8), closes_at=time(22),
                        is_active=True, description=None)


@pytest.fixture()
def bookings(monkeypatch):
    """The event's occupying bookings and the venues they are at, as the venues
    repository reads them."""
    rows = {"value": [{"id": BOOKING_ID, "event_space_request_id": SPACE_ID, "status": "approved",
                       "venue_id": VENUE_ID, "flag": None, "flag_reason": None}]}
    venues = {"value": [venue()]}
    monkeypatch.setattr(venues_repository, "list_change_bookings", lambda event_id: deepcopy(rows["value"]))
    monkeypatch.setattr(venues_repository, "list_venues", lambda: venues["value"])
    return {"rows": rows, "venues": venues}


@pytest.fixture()
def approvals(monkeypatch, events, bookings):
    """A fake `approve_event_change` that answers like the RPC: ok with the changed
    event, or an outcome code."""
    calls = []
    outcome = {"value": "ok"}

    def approve_event_change(event_id, actor_id, expected_version, from_statuses, event_values,
                             space_values, organiser_message, history_reason, officer_message,
                             attendee_message, booking_plans):
        calls.append({"event_id": event_id, "actor_id": actor_id, "expected_version": expected_version,
                      "from_statuses": from_statuses, "event_values": event_values,
                      "space_values": space_values, "organiser_message": organiser_message,
                      "history_reason": history_reason, "officer_message": officer_message,
                      "attendee_message": attendee_message, "booking_plans": booking_plans})
        if outcome["value"] != "ok":
            return {"outcome": outcome["value"], "event": None}
        changed = {**events["store"][event_id], **event_values, "version": expected_version + 1}
        changed.pop("spaces", None)
        return {"outcome": "ok", "event": changed}

    events["request"]["value"] = deepcopy(ORDINARY_REQUEST)
    monkeypatch.setattr(repository, "approve_event_change", approve_event_change)
    return {"calls": calls, "outcome": outcome}


def approve(client, auth_headers, version=3):
    return client.post(f"/api/v1/events/{EVENT_ID}/change-request/approve",
                       json={"version": version}, headers=auth_headers)


class TestApproveOrdinaryChange:
    def test_approving_applies_the_proposed_values_in_one_call(self, client, auth_headers, act_as, events,
                                                               approvals):
        act_as()

        response = approve(client, auth_headers)

        assert response.status_code == 200
        assert response.json()["name"] == "Partner Forum"
        assert response.json()["status"] == "confirmed"
        [call] = approvals["calls"]
        assert call["event_id"] == EVENT_ID
        assert call["actor_id"] == COORDINATOR_ID
        assert call["expected_version"] == 3
        assert call["event_values"] == {"name": "Partner Forum"}
        assert call["space_values"] == {SPACE_ID: {"label": "Great hall"}}

    def test_the_organiser_is_told(self, client, auth_headers, act_as, events, approvals):
        """AC4."""
        act_as()

        approve(client, auth_headers)

        assert approvals["calls"][0]["organiser_message"] == 'Your requested changes to "Partner Summit" were approved.'

    def test_a_value_changed_since_the_request_refuses_approval(self, client, auth_headers, act_as, events,
                                                                approvals):
        """Q8: applying `after` over a value nobody reviewed would overwrite someone's edit."""
        events["store"][EVENT_ID]["name"] = "Partner Summit 2026"
        act_as()

        response = approve(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "This event has changed since the request was made; reject it and ask for a new one.")
        assert approvals["calls"] == []

    def test_a_space_value_changed_since_the_request_refuses_approval(self, client, auth_headers, act_as,
                                                                      events, approvals):
        events["store"][EVENT_ID]["spaces"][0]["label"] = "Ballroom"
        act_as()

        response = approve(client, auth_headers)

        assert response.status_code == 409
        assert approvals["calls"] == []

    def test_an_older_version_than_the_coordinator_saw_refuses(self, client, auth_headers, act_as, events,
                                                              approvals):
        act_as()

        response = approve(client, auth_headers, version=2)

        assert response.status_code == 409
        assert response.json()["detail"] == "This event was updated by someone else. Reload."
        assert approvals["calls"] == []

    def test_a_change_that_now_breaks_a_submission_rule_is_refused(self, client, auth_headers, act_as, events,
                                                                    approvals):
        """CR-R19 re-run at approval: the proposed date was tomorrow when requested, and is today now."""
        today = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        events["request"]["value"]["changes"] = {
            "event": [{"field": "starts_at", "before": FUTURE_START, "after": today}], "spaces": []}
        act_as()

        response = approve(client, auth_headers)

        assert response.status_code == 422
        assert approvals["calls"] == []

    def test_without_an_open_request_there_is_nothing_to_approve(self, client, auth_headers, act_as, events,
                                                                 approvals):
        events["request"]["value"] = None
        act_as()

        response = approve(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "There is no open change request for this event."

    @pytest.mark.parametrize("status", ["completed", "cancelled", "rejected"])
    def test_a_closed_event_takes_no_decision(self, client, auth_headers, act_as, events, approvals, status):
        """AC8."""
        events["store"][EVENT_ID]["status"] = status
        act_as()

        response = approve(client, auth_headers)

        assert response.status_code == 409
        assert approvals["calls"] == []

    @pytest.mark.parametrize(("outcome", "status_code"), [
        ("no_open_request", 409), ("not_assigned", 403), ("not_found", 404), ("started", 409),
        ("stale", 409), ("status_changed", 409),
    ])
    def test_the_rpc_recheck_under_the_lock_decides(self, client, auth_headers, act_as, events, approvals,
                                                    outcome, status_code):
        approvals["outcome"]["value"] = outcome
        act_as()

        response = approve(client, auth_headers)

        assert response.status_code == status_code


class TestApproveSignificantChange:
    """AC7, Q6, Q9: the database moves the event; the API words what it records and tells."""

    def test_the_history_says_what_the_change_was(self, client, auth_headers, act_as, events, approvals):
        events["request"]["value"] = deepcopy(OPEN_REQUEST)
        act_as()

        approve(client, auth_headers)

        assert approvals["calls"][0]["history_reason"] == "Change approved: expected attendance"

    def test_the_safety_officers_are_told_why_it_left_their_queue(self, client, auth_headers, act_as, events,
                                                                 approvals):
        events["request"]["value"] = deepcopy(OPEN_REQUEST)
        act_as()

        approve(client, auth_headers)

        assert approvals["calls"][0]["officer_message"] == (
            '"Partner Summit" returned to planning. Approved event details changed.')

    def test_attendees_are_not_told_of_an_attendance_change(self, client, auth_headers, act_as, events,
                                                           approvals):
        events["request"]["value"] = deepcopy(OPEN_REQUEST)
        act_as()

        approve(client, auth_headers)

        assert approvals["calls"][0]["attendee_message"] is None

    @pytest.mark.parametrize(("field", "after"), [
        ("starts_at", "2026-11-12T11:00:00+08:00"),
        ("ends_at", "2026-11-12T13:00:00+08:00"),
        ("event_timezone", "Asia/Tokyo"),
    ])
    def test_attendees_are_told_of_a_new_date_or_time(self, client, auth_headers, act_as, events, approvals,
                                                     field, after):
        """RG-R4, Q9."""
        before = events["store"][EVENT_ID][field]
        events["request"]["value"]["changes"] = {
            "event": [{"field": field, "before": before, "after": after}], "spaces": []}
        act_as()

        approve(client, auth_headers)

        assert approvals["calls"][0]["attendee_message"] == (
            'The date or time of "Partner Summit" has changed. Check the event page for the new time.')


class TestApprovalPlansTheBookings:
    """AC3, AC5: the API tells the database what the change does to each booking."""

    def test_an_ordinary_change_touches_no_booking(self, client, auth_headers, act_as, events, approvals):
        act_as()

        approve(client, auth_headers)

        assert approvals["calls"][0]["booking_plans"] == []

    def test_a_new_time_moves_and_marks_the_booking(self, client, auth_headers, act_as, events, approvals):
        events["request"]["value"]["changes"] = {"event": [
            {"field": "starts_at", "before": FUTURE_START, "after": "2026-11-12T14:00:00+08:00"},
            {"field": "ends_at", "before": "2026-11-12T12:00:00+08:00", "after": "2026-11-12T16:00:00+08:00"},
        ], "spaces": []}
        act_as()

        approve(client, auth_headers)

        assert approvals["calls"][0]["booking_plans"] == [{
            "booking_id": BOOKING_ID, "period": ["2026-11-12T14:00:00+08:00", "2026-11-12T16:00:00+08:00"],
            "mark": "Date or time changed.", "unsuitable": None, "clear_unsuitable": False,
        }]

    def test_attendance_above_the_layouts_capacity_flags_the_booking(self, client, auth_headers, act_as, events,
                                                                     bookings, approvals):
        """Q17, via the shared capacity rule: banquet seats fewer than the hall."""
        bookings["venues"]["value"] = [venue(capacity=200, banquet=100)]
        events["request"]["value"]["changes"] = {"event": [], "spaces": [{
            "space_id": SPACE_ID, "label": "Main hall",
            "fields": [{"field": "layout_preference", "before": "theatre", "after": "banquet"}]}]}
        events["store"][EVENT_ID]["spaces"][0]["expected_pax"] = 150
        act_as()

        approve(client, auth_headers)

        [plan] = approvals["calls"][0]["booking_plans"]
        assert plan["mark"] == "Layout changed."
        assert plan["unsuitable"] == "After an approved change: Main hall needs 150 people; Grand Ballroom seats 100."

    def test_a_booking_at_an_unknown_venue_is_left_to_the_database(self, client, auth_headers, act_as, events,
                                                                    bookings, approvals):
        """A venue missing from the catalogue read can't be judged on capacity here."""
        bookings["venues"]["value"] = []
        events["request"]["value"]["changes"] = {"event": [
            {"field": "expected_attendance", "before": 80, "after": 900}], "spaces": []}
        events["store"][EVENT_ID]["spaces"][0]["expected_pax"] = None
        act_as()

        approve(client, auth_headers)

        assert approvals["calls"][0]["booking_plans"] == []


class TestHistoryRecordsTheDecision:
    """Q18: the organiser sees the outcome in the history, with the reason when rejected."""

    @pytest.fixture()
    def history(self, monkeypatch, events):
        monkeypatch.setattr(repository, "list_status_history", lambda event_id: [])
        monkeypatch.setattr(repository, "list_assignment_history", lambda event_id: [])
        monkeypatch.setattr(repository, "list_cancellation_requests", lambda event_id: [])
        monkeypatch.setattr(repository, "list_change_requests", lambda event_id: [
            {**OPEN_REQUEST, "status": "rejected", "decision_reason": REJECTION_REASON,
             "decided_at": "2026-10-25T10:00:00+00:00",
             "decided_by": {"id": COORDINATOR_ID, "full_name": "Cora Coordinator"}},
        ])

    @pytest.mark.parametrize(("role", "user_id"), [("event_organiser", ORGANISER_ID),
                                                    ("event_coordinator", COORDINATOR_ID)])
    def test_a_rejected_change_shows_who_rejected_it_and_why(self, client, auth_headers, act_as, history,
                                                            role, user_id):
        act_as(role, user_id=user_id)

        response = client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers)

        assert response.status_code == 200
        rejected, requested = response.json()["entries"]
        assert rejected == {
            "id": f"{REQUEST_ID}:rejected", "kind": "change_rejected",
            "from_status": None, "to_status": None, "from_coordinator": None, "to_coordinator": None,
            "actor": {"id": COORDINATOR_ID, "full_name": "Cora Coordinator"},
            "reason": REJECTION_REASON, "at": "2026-10-25T10:00:00Z",
        }
        assert requested["kind"] == "change_requested"


class TestHistoryRecordsTheApproval:
    @pytest.fixture()
    def history(self, monkeypatch, events):
        monkeypatch.setattr(repository, "list_status_history", lambda event_id: [])
        monkeypatch.setattr(repository, "list_assignment_history", lambda event_id: [])
        monkeypatch.setattr(repository, "list_cancellation_requests", lambda event_id: [])
        monkeypatch.setattr(repository, "list_change_requests", lambda event_id: [
            {**ORDINARY_REQUEST, "status": "approved", "decision_reason": None,
             "decided_at": "2026-10-25T10:00:00+00:00",
             "decided_by": {"id": COORDINATOR_ID, "full_name": "Cora Coordinator"}},
        ])

    def test_an_approved_change_shows_who_approved_it_and_what_changed(self, client, auth_headers, act_as,
                                                                      history):
        act_as("event_organiser", user_id=ORGANISER_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers)

        approved, requested = response.json()["entries"]
        assert approved["id"] == f"{REQUEST_ID}:approved"
        assert approved["kind"] == "change_approved"
        assert approved["actor"] == {"id": COORDINATOR_ID, "full_name": "Cora Coordinator"}
        assert approved["reason"] is None
        assert approved["changes"] == ORDINARY_REQUEST["changes"]
        assert approved["at"] == "2026-10-25T10:00:00Z"
        assert requested["kind"] == "change_requested"


class TestImpactPreview:
    """Q1, CR-R2: what approving would do, worked out from the event as it is now."""

    TIME_CHANGE = {"event": [
        {"field": "starts_at", "before": FUTURE_START, "after": "2026-11-12T14:00:00+08:00"},
        {"field": "ends_at", "before": "2026-11-12T12:00:00+08:00", "after": "2026-11-12T16:00:00+08:00"},
    ], "spaces": []}

    @pytest.fixture()
    def impact(self, monkeypatch, events, bookings):
        from app.modules.equipment import repository as equipment_repository
        from app.modules.registrations import repository as registrations_repository

        state = {"conflict": None, "free": 5, "registered": 3, "conflict_calls": []}

        def first_conflict(period, venue_id, exclude_booking_id):
            state["conflict_calls"].append((period, venue_id, exclude_booking_id))
            return state["conflict"]

        events["request"]["value"]["changes"] = deepcopy(self.TIME_CHANGE)
        bookings["rows"]["value"][0].update(setup_minutes=30, turnaround_minutes=0)
        monkeypatch.setattr(venues_repository, "first_conflict", first_conflict)
        monkeypatch.setattr(equipment_repository, "list_event_requests", lambda event_id: [
            {"id": "l1", "equipment_id": "p1", "quantity": 8, "status": "reserved",
             "needs_re_review_since": None, "equipment": {"name": "PA Systems"}},
            {"id": "l2", "equipment_id": "m1", "quantity": 2, "status": "pending",
             "needs_re_review_since": None, "equipment": {"name": "Wireless Mics"}},
        ])
        monkeypatch.setattr(equipment_repository, "line_free_quantity",
                            lambda line_id, equipment_id, starts_at, ends_at: state["free"])
        monkeypatch.setattr(registrations_repository, "registered_count", lambda event_id: state["registered"])
        return state

    def preview(self, client, auth_headers):
        return client.get(f"/api/v1/events/{EVENT_ID}/change-request/impact", headers=auth_headers)

    def test_a_clear_move_needs_re_review_and_attendees_are_counted(self, client, auth_headers, act_as, impact):
        act_as()

        response = self.preview(client, auth_headers)

        assert response.status_code == 200
        assert response.json() == {
            "bookings": [{"booking_id": BOOKING_ID, "venue_name": "Grand Ballroom", "space_label": "Main hall",
                          "messages": ["Moves to the new time.",
                                       "Needs re-review by venue staff: Date or time changed."]}],
            "equipment": [{"line_id": "l1", "label": "8 × PA Systems", "needed": 8, "free": 5}],
            "attendees_notified": 3,
        }

    def test_the_conflict_check_uses_the_occupied_window_and_leaves_the_booking_out(
        self, client, auth_headers, act_as, impact
    ):
        act_as()

        self.preview(client, auth_headers)

        [(period, venue_id, excluded)] = impact["conflict_calls"]
        assert (period.starts_at.isoformat(), period.ends_at.isoformat()) == (
            "2026-11-12T13:30:00+08:00", "2026-11-12T16:00:00+08:00")
        assert (venue_id, excluded) == (VENUE_ID, BOOKING_ID)

    @pytest.mark.parametrize(("conflict", "message"), [
        ({"kind": "booking", "event_name": "Product Launch", "block_reason": None},
         'Clashes with "Product Launch": it keeps its time and is flagged Conflict.'),
        ({"kind": "block", "event_name": None, "block_reason": "maintenance"},
         "Clashes with a venue block (Maintenance): it keeps its time and is flagged Conflict."),
    ])
    def test_a_clash_is_named(self, client, auth_headers, act_as, impact, conflict, message):
        impact["conflict"] = conflict
        act_as()

        [booking] = self.preview(client, auth_headers).json()["bookings"]

        assert booking["messages"] == [message]

    def test_attendance_over_capacity_says_a_replacement_is_needed(self, client, auth_headers, act_as, events,
                                                                   impact):
        """The §6.19 example."""
        events["request"]["value"]["changes"] = {"event": [
            {"field": "expected_attendance", "before": 80, "after": 250}], "spaces": []}
        events["store"][EVENT_ID]["spaces"][0]["expected_pax"] = None
        act_as()

        body = self.preview(client, auth_headers).json()

        assert body["bookings"][0]["messages"] == [
            "After an approved change: Main hall needs 250 people; Grand Ballroom seats 200. "
            "A replacement venue is needed."]
        assert body["equipment"] == [] and body["attendees_notified"] == 0

    def test_lines_still_in_stock_are_not_listed(self, client, auth_headers, act_as, impact):
        impact["free"] = 8
        act_as()

        assert self.preview(client, auth_headers).json()["equipment"] == []

    def test_without_an_open_request_there_is_nothing_to_preview(self, client, auth_headers, act_as, events,
                                                                 impact):
        events["request"]["value"] = None
        act_as()

        response = self.preview(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "There is no open change request for this event."

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "event_coordinator_lead"])
    def test_only_the_coordinator_previews(self, client, auth_headers, act_as, impact, role):
        act_as(role, user_id=COORDINATOR_ID)

        assert self.preview(client, auth_headers).status_code == 403

    def test_another_coordinator_is_forbidden(self, client, auth_headers, act_as, impact):
        act_as(user_id=OTHER_COORDINATOR_ID)

        assert self.preview(client, auth_headers).status_code == 403


DECISIONS = [
    ("reject", reject),
    ("approve", approve),
]


class TestOnlyTheAssignedCoordinatorDecides:
    """Q4, SCRUM-76: every decision is the assigned coordinator's, acting as coordinator."""

    @pytest.mark.parametrize(("name", "decide"), DECISIONS)
    def test_another_coordinator_is_forbidden(self, client, auth_headers, act_as, events, rejections,
                                              approvals, name, decide):
        act_as(user_id=OTHER_COORDINATOR_ID)

        response = decide(client, auth_headers)

        assert response.status_code == 403
        assert rejections["calls"] == [] and approvals["calls"] == []

    @pytest.mark.parametrize(("name", "decide"), DECISIONS)
    @pytest.mark.parametrize("role", ["event_organiser", "event_coordinator_lead", "venue_staff",
                                      "tech_support", "safety_officer", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, events, rejections,
                                       approvals, role, name, decide):
        act_as(role, user_id=COORDINATOR_ID)

        response = decide(client, auth_headers)

        assert response.status_code == 403
        assert rejections["calls"] == [] and approvals["calls"] == []

    @pytest.mark.parametrize(("name", "decide"), DECISIONS)
    def test_a_draft_is_not_found(self, client, auth_headers, act_as, events, rejections, approvals,
                                  name, decide):
        events["store"][EVENT_ID]["status"] = "draft"
        act_as()

        response = decide(client, auth_headers)

        assert response.status_code == 404
        assert rejections["calls"] == [] and approvals["calls"] == []

    @pytest.mark.parametrize(("name", "decide"), DECISIONS)
    def test_the_coordinator_acting_as_another_role_is_forbidden(self, client, auth_headers, monkeypatch,
                                                                 events, rejections, approvals, name,
                                                                 decide):
        """The assigned coordinator's account also holds organiser and is acting as it."""
        profile = {"id": COORDINATOR_ID, "email": "multi@connectsphere.dev", "full_name": "Multi Role",
                   "role": "event_coordinator", "organisation_name": None, "department": None,
                   "phone_number": None}
        anon = MagicMock()
        anon.auth.get_claims.return_value = {"claims": {
            "sub": COORDINATOR_ID, "aud": "authenticated", "email": profile["email"],
            "session_id": "33333333-3333-3333-3333-333333333333"}}
        monkeypatch.setattr("app.core.security.get_supabase_anon_client", lambda: anon)
        monkeypatch.setattr("app.core.security.get_supabase_admin_client",
                            lambda: make_table_mock(profile, session_active_role={"role": "event_organiser"}))

        response = decide(client, auth_headers)

        assert response.status_code == 403
        assert rejections["calls"] == [] and approvals["calls"] == []
