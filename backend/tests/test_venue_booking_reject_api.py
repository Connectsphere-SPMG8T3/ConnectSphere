"""SCRUM-38 venue staff reject a booking request, through the HTTP API with the repositories mocked.

Whether a booking can still be rejected is decided by `public.reject_venue_booking`
under a lock on the booking row, and proven against the real database in
`supabase/verification/venue_booking_reject_checks.sql`. Here the fake answers
with each of the function's outcome codes, and the tests pin down what the API
makes of them, who may call it, and who sees the reason afterwards.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.events import repository as events_repository
from app.modules.venues import repository as venues_repository
from app.modules.venues.schemas import Period

COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_COORDINATOR_ID = "a0000000-0000-4000-8000-000000000009"
ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
VENUE_STAFF_ID = "a0000000-0000-4000-8000-000000000003"
EVENT_ID = "e0000000-0000-4000-8000-000000000202"
VENUE_ID = "b0000000-0000-4000-8000-000000000006"
BOOKING_ID = "d0000000-0000-4000-8000-000000000999"
URL = f"/api/v1/venue-bookings/{BOOKING_ID}"
REJECT_URL = f"{URL}/reject"
STARTS = datetime(2031, 3, 10, 6, 0, tzinfo=timezone.utc)
DECIDED_AT = datetime(2031, 3, 1, 2, 0, tzinfo=timezone.utc)


def event_row(status="planning", coordinator_id=COORDINATOR_ID):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": coordinator_id,
        "status": status, "event_timezone": "Asia/Singapore", "name": "Partner Summit",
        "purpose": "Quarterly partner meeting", "description": None,
        "starts_at": STARTS.isoformat(), "ends_at": (STARTS + timedelta(hours=3)).isoformat(),
        "expected_attendance": 40, "layout_preference": "classroom", "facilities_required": ["projector"],
        "accessibility_needs": "Step-free access", "preliminary_equipment_needs": None,
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "technical_readiness": "not_required", "submitted_at": now, "version": 4,
        "created_at": now, "updated_at": now,
    }


def booking_row(status="held"):
    """What `venues.repository.get_booking` returns: one booking, already shaped."""
    rejected = status == "rejected"
    return {
        "id": BOOKING_ID, "event_id": EVENT_ID, "venue_id": VENUE_ID, "venue_name": "Innovation Lab",
        "period": Period(starts_at=STARTS, ends_at=STARTS + timedelta(hours=3)),
        "status": status, "request_note": "Need early access at 13:00",
        "requested_at": datetime(2031, 2, 1, tzinfo=timezone.utc), "requested_by_name": "Marcus Lim",
        "decision_reason": "Capacity exceeded" if rejected else None,
        "suggestion_note": "Try Heritage Hall" if rejected else None,
        "decided_by_name": "Venue Staff" if rejected else None,
        "decided_at": DECIDED_AT if rejected else None,
    }


@pytest.fixture()
def bookings(monkeypatch):
    """An in-memory booking and its event. `reject_booking` records each call,
    answers with `state["outcome"]`, and on `ok` changes the booking the way the
    database function does, so the response shows the stored decision."""
    state = {"event": event_row(), "booking": booking_row(), "outcome": "ok", "calls": [], "history": []}

    def get_booking(booking_id):
        return deepcopy(state["booking"]) if booking_id == BOOKING_ID and state["booking"] else None

    def reject_booking(booking_id, actor_id, reason, suggestion, *, notify_message):
        state["calls"].append({"booking_id": booking_id, "actor_id": actor_id, "reason": reason,
                               "suggestion": suggestion, "notify_message": notify_message})
        if state["outcome"] == "ok":
            state["booking"].update(status="rejected", decision_reason=reason, suggestion_note=suggestion,
                                    decided_by_name="Venue Staff", decided_at=DECIDED_AT)
            state["history"].append({"action": "rejected", "from_status": "held", "to_status": "rejected",
                                     "actor_name": "Venue Staff",
                                     "reason": reason, "suggestion": suggestion, "at": DECIDED_AT})
            return {"outcome": "ok", "event_id": EVENT_ID, "from_status": "held"}
        return {"outcome": state["outcome"], "event_id": EVENT_ID, "from_status": state["booking"]["status"]}

    monkeypatch.setattr(venues_repository, "get_booking", get_booking)
    monkeypatch.setattr(venues_repository, "reject_booking", reject_booking)
    monkeypatch.setattr(venues_repository, "list_booking_history",
                        lambda booking_id: deepcopy(state["history"]) if booking_id == BOOKING_ID else [])
    monkeypatch.setattr(events_repository, "get_event",
                        lambda event_id: deepcopy(state["event"]) if event_id == EVENT_ID else None)
    monkeypatch.setattr(events_repository, "list_planning_context",
                        lambda event_ids: [deepcopy(state["event"])] if EVENT_ID in event_ids else [])
    monkeypatch.setattr(events_repository, "list_event_names",
                        lambda event_ids: {EVENT_ID: state["event"]["name"]} if EVENT_ID in event_ids else {})
    return state


def reject(client, auth_headers, **body):
    payload = {"reason": "Capacity exceeded", **body}
    return client.post(REJECT_URL, json=payload, headers=auth_headers)


class TestViewRequest:
    def test_venue_staff_see_the_request_with_the_events_requirements(
        self, client, auth_headers, authenticate_as, bookings
    ):
        # AC1: date, time, capacity, layout and the other requirements.
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = client.get(URL, headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == BOOKING_ID
        assert body["status"] == "held"
        assert body["venue_name"] == "Innovation Lab"
        assert body["period"] == {"starts_at": "2031-03-10T06:00:00Z", "ends_at": "2031-03-10T09:00:00Z"}
        assert body["request_note"] == "Need early access at 13:00"
        assert body["requested_by_name"] == "Marcus Lim"
        assert body["event"] == {
            "id": EVENT_ID, "name": "Partner Summit", "status": "planning", "expected_attendance": 40,
            "layout_preference": "classroom", "facilities_required": ["projector"],
            "accessibility_needs": "Step-free access",
        }
        assert body["decision"] is None
        assert body["history"] == []

    @pytest.mark.parametrize(
        "booking",
        [
            # An approval stamps decided_at but is not a rejection.
            {"status": "approved", "decided_at": DECIDED_AT},
            # A rejection with no stored reason has nothing to show.
            {"status": "rejected", "decision_reason": None, "decided_at": DECIDED_AT},
        ],
    )
    def test_only_a_rejection_with_its_reason_shows_a_decision(
        self, client, auth_headers, authenticate_as, bookings, booking
    ):
        bookings["booking"].update(booking)
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = client.get(URL, headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["decision"] is None

    def test_a_missing_booking_is_not_found(self, client, auth_headers, authenticate_as, bookings):
        bookings["booking"] = None
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = client.get(URL, headers=auth_headers)

        assert response.status_code == 404
        assert response.json()["detail"] == "Booking not found."

    def test_the_assigned_coordinator_can_read_it(self, client, auth_headers, authenticate_as, bookings):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        assert client.get(URL, headers=auth_headers).status_code == 200

    def test_a_coordinator_who_is_not_assigned_is_forbidden(self, client, auth_headers, authenticate_as, bookings):
        bookings["event"]["coordinator_id"] = OTHER_COORDINATOR_ID
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        assert client.get(URL, headers=auth_headers).status_code == 403

    @pytest.mark.parametrize("role", ["event_organiser", "tech_support", "safety_officer",
                                      "event_coordinator_lead", "attendee"])
    def test_every_other_role_is_forbidden(self, client, auth_headers, authenticate_as, bookings, role):
        # AC6: the organiser and attendees never see the request or its reason.
        authenticate_as(role, user_id=ORGANISER_ID)

        assert client.get(URL, headers=auth_headers).status_code == 403

    def test_an_unauthenticated_request_is_refused(self, client, bookings):
        assert client.get(URL).status_code == 401


class TestReject:
    def test_venue_staff_reject_a_held_booking_with_a_reason_and_suggestion(
        self, client, auth_headers, authenticate_as, bookings
    ):
        # AC2, AC3, AC4, AC12.
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = reject(client, auth_headers, reason="  Capacity exceeded  ", suggestion="  Try Heritage Hall  ")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "rejected"
        assert body["decision"] == {
            "reason": "Capacity exceeded", "suggestion": "Try Heritage Hall",
            "decided_by_name": "Venue Staff", "decided_at": "2031-03-01T02:00:00Z",
        }
        assert body["history"] == [{
            "action": "rejected", "from_status": "held", "to_status": "rejected", "actor_name": "Venue Staff",
            "reason": "Capacity exceeded", "suggestion": "Try Heritage Hall", "at": "2031-03-01T02:00:00Z",
        }]
        [sent] = bookings["calls"]
        assert sent == {
            "booking_id": BOOKING_ID, "actor_id": VENUE_STAFF_ID, "reason": "Capacity exceeded",
            "suggestion": "Try Heritage Hall",
            "notify_message": 'Venue staff rejected the booking of Innovation Lab for "Partner Summit".',
        }

    def test_the_notification_does_not_carry_the_reason(self, client, auth_headers, authenticate_as, bookings):
        # [Assumption] §9: the coordinator reads the reason on the event or booking page.
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        reject(client, auth_headers, reason="Double-booked for maintenance", suggestion="Heritage Hall")

        message = bookings["calls"][0]["notify_message"]
        assert "maintenance" not in message
        assert "Heritage" not in message

    def test_the_notification_reads_naturally_without_a_venue_or_event_name(
        self, client, auth_headers, authenticate_as, bookings, monkeypatch
    ):
        bookings["booking"]["venue_name"] = None
        monkeypatch.setattr(events_repository, "list_event_names", lambda event_ids: {})
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        reject(client, auth_headers)

        assert bookings["calls"][0]["notify_message"] == 'Venue staff rejected the booking of the venue for "your event".'

    def test_the_suggestion_is_optional_and_a_blank_one_is_none(self, client, auth_headers, authenticate_as, bookings):
        # AC3.
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        assert reject(client, auth_headers).status_code == 200
        assert reject(client, auth_headers, suggestion="   ").status_code == 200
        assert reject(client, auth_headers, suggestion=None).status_code == 200
        assert [call["suggestion"] for call in bookings["calls"]] == [None, None, None]

    @pytest.mark.parametrize("reason", ["", "   ", None])
    def test_a_missing_or_blank_reason_is_refused(self, client, auth_headers, authenticate_as, bookings, reason):
        # AC2: the reason can't be blank.
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = client.post(REJECT_URL, json={"reason": reason}, headers=auth_headers)

        assert response.status_code == 422
        assert bookings["calls"] == []

    def test_a_body_without_a_reason_is_refused(self, client, auth_headers, authenticate_as, bookings):
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        assert client.post(REJECT_URL, json={}, headers=auth_headers).status_code == 422
        assert bookings["calls"] == []

    def test_the_reason_and_suggestion_are_capped_at_1000_characters(
        self, client, auth_headers, authenticate_as, bookings
    ):
        # AC2, AC3: at most 1000 characters each, counted after trimming.
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        assert reject(client, auth_headers, reason="x" * 1001).status_code == 422
        assert reject(client, auth_headers, suggestion="x" * 1001).status_code == 422
        assert bookings["calls"] == []
        assert reject(client, auth_headers, reason=f" {'x' * 1000} ", suggestion="y" * 1000).status_code == 200

    @pytest.mark.parametrize(
        ("status", "detail"),
        [
            ("approved", "Only a held booking can be rejected. This one is approved."),
            ("rejected", "Only a held booking can be rejected. This one is already rejected."),
            ("cancelled", "Only a held booking can be rejected. This one is cancelled."),
            ("released", "Only a held booking can be rejected. This one is released."),
            ("re_review", "Only a held booking can be rejected. This one is under re-review."),
            # No label of its own: the status reads as itself.
            ("expired", "Only a held booking can be rejected. This one is expired."),
        ],
    )
    def test_a_booking_that_is_no_longer_held_is_refused(
        self, client, auth_headers, authenticate_as, bookings, status, detail
    ):
        # AC9, AC10: the database decides under the row lock, so a booking that
        # changed after the page loaded is refused, not overwritten.
        bookings["booking"]["status"] = status
        bookings["outcome"] = "not_held"
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = reject(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == detail

    def test_a_missing_booking_is_not_found(self, client, auth_headers, authenticate_as, bookings):
        bookings["booking"] = None
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        assert reject(client, auth_headers).status_code == 404
        assert bookings["calls"] == []

    def test_a_booking_removed_after_the_api_read_it_is_not_found(
        self, client, auth_headers, authenticate_as, bookings
    ):
        bookings["outcome"] = "booking_not_found"
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        assert reject(client, auth_headers).status_code == 404

    @pytest.mark.parametrize(("outcome", "field"), [("invalid_reason", "reason"), ("invalid_suggestion", "suggestion")])
    def test_text_the_database_refuses_is_still_unprocessable(
        self, client, auth_headers, authenticate_as, bookings, outcome, field
    ):
        # Defence in depth: the function re-checks the text it is given.
        bookings["outcome"] = outcome
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = reject(client, auth_headers)

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", field]

    def test_a_hold_past_its_expiry_is_refused_as_expired(self, client, auth_headers, authenticate_as, bookings):
        # AC9, AC10 (CR-99): the function expires a hold past its expiry instead
        # of rejecting it, so only the expiry is saved.
        bookings["outcome"] = "hold_expired"
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = reject(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "This hold has expired, so it can't be rejected."


class TestWhoMayReject:
    @pytest.mark.parametrize("role", ["event_organiser", "event_coordinator", "event_coordinator_lead",
                                      "tech_support", "safety_officer", "attendee"])
    def test_every_other_role_is_forbidden(self, client, auth_headers, authenticate_as, bookings, role):
        # AC11.
        authenticate_as(role, user_id=COORDINATOR_ID)

        assert reject(client, auth_headers).status_code == 403
        assert bookings["calls"] == []

    def test_a_venue_staff_holder_acting_as_coordinator_is_forbidden(
        self, client, auth_headers, monkeypatch, bookings
    ):
        # AC11, SCRUM-76: the seeded coordinator also holds venue_staff; acting
        # as coordinator they can't reject, even though they hold the role.
        from tests.test_event_comments_api import acting_as_another_role

        acting_as_another_role(monkeypatch, COORDINATOR_ID, holds="venue_staff", acts_as="event_coordinator")

        assert reject(client, auth_headers).status_code == 403
        assert bookings["calls"] == []

    def test_an_unauthenticated_request_is_refused(self, client, bookings):
        assert client.post(REJECT_URL, json={"reason": "No"}).status_code == 401


class TestEventShowsRejections:
    """AC6, AC7: the coordinator sees why on the event page and can try another
    venue; the organiser never sees the reason."""

    REJECTED = {"id": BOOKING_ID, "venue_id": VENUE_ID, "venue_name": "Innovation Lab",
                "reason": "Capacity exceeded", "suggestion": "Try Heritage Hall", "decided_at": DECIDED_AT}

    @pytest.fixture()
    def rejected(self, monkeypatch, bookings):
        monkeypatch.setattr(venues_repository, "list_rejected_bookings",
                            lambda event_id: [deepcopy(self.REJECTED)] if event_id == EVENT_ID else [])
        monkeypatch.setattr(venues_repository, "get_active_booking", lambda event_id: None)
        monkeypatch.setattr(venues_repository, "list_booking_statuses",
                            lambda event_ids: [{"event_id": EVENT_ID, "status": "rejected"}])
        return bookings

    def test_the_assigned_coordinator_sees_the_reason_and_suggestion(
        self, client, auth_headers, authenticate_as, rejected
    ):
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["rejected_bookings"] == [{
            "id": BOOKING_ID, "venue_id": VENUE_ID, "venue_name": "Innovation Lab",
            "reason": "Capacity exceeded", "suggestion": "Try Heritage Hall", "decided_at": "2031-03-01T02:00:00Z",
        }]
        # AC7: no venue is held any more, so the event is free to request another.
        assert body["status"] == "planning"
        assert body["venue_booking"] is None

    @pytest.mark.parametrize("status", ["planning", "confirmed"])
    def test_the_organiser_never_sees_a_rejection(self, client, auth_headers, authenticate_as, rejected, status):
        rejected["event"]["status"] = status
        authenticate_as("event_organiser", user_id=ORGANISER_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["rejected_bookings"] == []
        assert "Capacity exceeded" not in response.text
        assert "Heritage" not in response.text
