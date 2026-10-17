"""SCRUM-36 venue staff approve a held booking, through the HTTP API with the repositories mocked.

Whether a booking can still be approved is decided by `public.approve_venue_booking`
under CR-99's lock on the booking row, and proven against the real database in
`supabase/verification/venue_booking_approve_checks.sql`. Here the fake answers
with each of the function's outcome codes, and the tests pin down what the API
makes of them and who may call it.
"""

from copy import deepcopy

import pytest

from app.modules.events import repository as events_repository
from app.modules.venues import repository as venues_repository
from tests.test_venue_booking_reject_api import (
    BOOKING_ID,
    COORDINATOR_ID,
    DECIDED_AT,
    EVENT_ID,
    URL,
    VENUE_STAFF_ID,
    booking_row,
    event_row,
)

APPROVE_URL = f"{URL}/approve"


@pytest.fixture()
def bookings(monkeypatch):
    """An in-memory held booking and its event. `approve_booking` records each
    call, answers with `state["outcome"]`, and on `ok` changes the booking the
    way the database function does."""
    state = {"event": event_row(), "booking": booking_row(), "outcome": "ok", "calls": [], "history": []}

    def get_booking(booking_id):
        return deepcopy(state["booking"]) if booking_id == BOOKING_ID and state["booking"] else None

    def approve_booking(booking_id, actor_id, *, notify_message):
        state["calls"].append({"booking_id": booking_id, "actor_id": actor_id, "notify_message": notify_message})
        if state["outcome"] == "ok":
            state["booking"].update(status="approved", decided_by_name="Venue Staff", decided_at=DECIDED_AT)
            state["history"].append({"action": "approved", "from_status": "held", "to_status": "approved",
                                     "actor_name": "Venue Staff", "reason": None, "suggestion": None,
                                     "at": DECIDED_AT})
            return {"outcome": "ok", "event_id": EVENT_ID, "from_status": "held"}
        return {"outcome": state["outcome"], "event_id": EVENT_ID, "from_status": state["booking"]["status"]}

    monkeypatch.setattr(venues_repository, "get_booking", get_booking)
    monkeypatch.setattr(venues_repository, "approve_booking", approve_booking)
    monkeypatch.setattr(venues_repository, "list_booking_history", lambda booking_id: deepcopy(state["history"]))
    monkeypatch.setattr(events_repository, "list_planning_context",
                        lambda event_ids: [deepcopy(state["event"])] if EVENT_ID in event_ids else [])
    monkeypatch.setattr(events_repository, "list_event_names",
                        lambda event_ids: {EVENT_ID: state["event"]["name"]} if EVENT_ID in event_ids else {})
    return state


def approve(client, auth_headers):
    return client.post(APPROVE_URL, headers=auth_headers)


class TestApprove:
    def test_venue_staff_approve_a_held_booking(self, client, auth_headers, authenticate_as, bookings):
        # AC2, AC10: approved, and the history records who and when.
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = approve(client, auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "approved"
        # A decision panel is for a rejection's reason; an approval has none.
        assert body["decision"] is None
        assert body["history"] == [{
            "action": "approved", "from_status": "held", "to_status": "approved", "actor_name": "Venue Staff",
            "reason": None, "suggestion": None, "at": "2031-03-01T02:00:00Z",
        }]

    def test_the_coordinator_is_told_which_venue_and_event(self, client, auth_headers, authenticate_as, bookings):
        # AC2: the function sends it to the assigned coordinator, never the actor.
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        approve(client, auth_headers)

        assert bookings["calls"] == [{
            "booking_id": BOOKING_ID, "actor_id": VENUE_STAFF_ID,
            "notify_message": 'Venue staff approved the booking of Innovation Lab for "Partner Summit".',
        }]

    def test_the_actor_is_taken_from_the_session_not_the_body(self, client, auth_headers, authenticate_as, bookings):
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        client.post(APPROVE_URL, json={"actor_id": COORDINATOR_ID}, headers=auth_headers)

        assert bookings["calls"][0]["actor_id"] == VENUE_STAFF_ID

    def test_an_unnamed_venue_and_event_still_read_in_the_notification(
        self, client, auth_headers, authenticate_as, bookings, monkeypatch
    ):
        bookings["booking"]["venue_name"] = None
        monkeypatch.setattr(events_repository, "list_event_names", lambda event_ids: {})
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        approve(client, auth_headers)

        assert bookings["calls"][0]["notify_message"] == 'Venue staff approved the booking of the venue for "your event".'

    def test_a_venue_block_over_the_booking_refuses_it(self, client, auth_headers, authenticate_as, bookings):
        # AC3.
        bookings["outcome"] = "venue_blocked"
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = approve(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "Venue blocked for this time."

    def test_a_deactivated_venue_refuses_it(self, client, auth_headers, authenticate_as, bookings):
        # AC4.
        bookings["outcome"] = "venue_inactive"
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = approve(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "This venue is inactive, so the booking can't be approved."

    @pytest.mark.parametrize("status", ["held", "expired"])
    def test_an_expired_hold_is_refused_as_expired(self, client, auth_headers, authenticate_as, bookings, status):
        # AC6 (CR-99): `lock_hold_for_approval` answers `hold_expired` both for
        # a hold already expired and for one past its expiry the job hasn't
        # reached yet, which it expires instead of letting the approval through.
        bookings["booking"]["status"] = status
        bookings["outcome"] = "hold_expired"
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = approve(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "This hold has expired, so it can't be approved."

    @pytest.mark.parametrize(
        ("status", "detail"),
        [
            ("approved", "Only a held booking can be approved. This one is approved."),
            ("rejected", "Only a held booking can be approved. This one is already rejected."),
            ("cancelled", "Only a held booking can be approved. This one is cancelled."),
            ("released", "Only a held booking can be approved. This one is released."),
            ("re_review", "Only a held booking can be approved. This one is under re-review."),
        ],
    )
    def test_a_booking_that_is_no_longer_held_is_refused(
        self, client, auth_headers, authenticate_as, bookings, status, detail
    ):
        # AC6, AC9: decided under the row lock, so a booking rejected or expired
        # after the page loaded is refused, not overwritten.
        bookings["booking"]["status"] = status
        bookings["outcome"] = "not_held"
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = approve(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == detail

    def test_a_missing_booking_is_not_found(self, client, auth_headers, authenticate_as, bookings):
        bookings["booking"] = None
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = approve(client, auth_headers)

        assert response.status_code == 404
        assert response.json()["detail"] == "Booking not found."
        assert bookings["calls"] == []

    def test_a_booking_removed_after_the_api_read_it_is_not_found(
        self, client, auth_headers, authenticate_as, bookings
    ):
        bookings["outcome"] = "booking_not_found"
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        assert approve(client, auth_headers).status_code == 404


class TestWhoMayApprove:
    @pytest.mark.parametrize("role", ["event_organiser", "event_coordinator", "event_coordinator_lead",
                                      "tech_support", "safety_officer", "attendee"])
    def test_every_other_role_is_forbidden(self, client, auth_headers, authenticate_as, bookings, role):
        # AC8.
        authenticate_as(role, user_id=COORDINATOR_ID)

        assert approve(client, auth_headers).status_code == 403
        assert bookings["calls"] == []

    def test_a_venue_staff_holder_acting_as_coordinator_is_forbidden(
        self, client, auth_headers, monkeypatch, bookings
    ):
        # AC8, SCRUM-76: the seeded coordinator also holds venue_staff; acting
        # as coordinator they can't approve, even though they hold the role.
        from tests.test_event_comments_api import acting_as_another_role

        acting_as_another_role(monkeypatch, COORDINATOR_ID, holds="venue_staff", acts_as="event_coordinator")

        assert approve(client, auth_headers).status_code == 403
        assert bookings["calls"] == []

    def test_an_unauthenticated_request_is_refused(self, client, bookings):
        assert client.post(APPROVE_URL).status_code == 401
