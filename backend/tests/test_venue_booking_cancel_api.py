"""SCRUM-85: the assigned coordinator cancels a venue booking, through the HTTP API
with the repositories mocked.

Whether a booking can still be cancelled, and what cancelling changes (the freed
slot, history, venue staff's notices, the event's return to Planning), is decided
by `public.cancel_venue_booking` under the event's and the booking's locks, and
proven against the real database in `supabase/verification/venue_booking_cancel_checks.sql`.
Here the fake answers with each of the function's outcome codes, and the tests pin
down what the API makes of them, the messages it hands the function, and who may
call it.
"""

import pytest
from postgrest.exceptions import APIError

from app.modules.venues import repository as venues_repository
from tests.test_venue_booking_reject_api import (  # noqa: F401  (bookings is the fixture)
    BOOKING_ID,
    COORDINATOR_ID,
    OTHER_COORDINATOR_ID,
    URL,
    bookings,
)

CANCEL_URL = f"{URL}/cancel"


@pytest.fixture()
def cancelling(bookings, monkeypatch):  # noqa: F811
    """`cancel_venue_booking` records each call, answers with `state["outcome"]`, and
    on `ok` cancels the booking the way the database function does."""
    bookings["cancels"] = []

    def cancel_booking(booking_id, actor_id, *, staff_message, return_message):
        bookings["cancels"].append({"booking_id": booking_id, "actor_id": actor_id,
                                    "staff_message": staff_message, "return_message": return_message})
        if bookings["outcome"] == "ok":
            from_status = bookings["booking"]["status"]
            bookings["booking"].update(status="cancelled")
            bookings["history"].append({"action": "cancelled", "from_status": from_status, "to_status": "cancelled",
                                        "actor_name": "Marcus Lim", "reason": None, "suggestion": None,
                                        "at": "2031-03-01T02:00:00+00:00"})
            return {"outcome": "ok", "event_id": bookings["event"]["id"], "from_status": from_status}
        return {"outcome": bookings["outcome"], "event_id": bookings["event"]["id"],
                "from_status": bookings["booking"]["status"]}

    monkeypatch.setattr(venues_repository, "cancel_booking", cancel_booking)
    return bookings


def cancel(client, auth_headers):
    return client.post(CANCEL_URL, headers=auth_headers)


class TestCancel:
    @pytest.mark.parametrize("status", ["held", "approved", "re_review"])
    def test_the_assigned_coordinator_cancels_the_booking(
        self, client, auth_headers, authenticate_as, cancelling, status
    ):
        # AC1, [Assumption] §9: held, approved and re-review bookings.
        cancelling["booking"]["status"] = status
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = cancel(client, auth_headers)

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        assert [call["booking_id"] for call in cancelling["cancels"]] == [BOOKING_ID]
        assert cancelling["cancels"][0]["actor_id"] == COORDINATOR_ID

    def test_venue_staff_and_a_returned_event_are_told_what_happened(
        self, client, auth_headers, authenticate_as, cancelling
    ):
        # AC1 (venue staff), AC4 (the coordinator, and the officers from Safety review).
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        cancel(client, auth_headers)

        call = cancelling["cancels"][0]
        assert call["staff_message"] == (
            'The coordinator cancelled the booking of Innovation Lab for "Partner Summit". '
            "The venue is free for that time again."
        )
        assert call["return_message"] == '"Partner Summit" returned to planning. A venue booking was cancelled.'

    def test_the_cancellation_shows_in_the_bookings_history(self, client, auth_headers, authenticate_as, cancelling):
        # AC6: who and when.
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        history = cancel(client, auth_headers).json()["history"]

        assert [(row["action"], row["actor_name"]) for row in history] == [("cancelled", "Marcus Lim")]

    def test_a_booking_that_does_not_exist_is_a_404_and_nothing_runs(
        self, client, auth_headers, authenticate_as, cancelling
    ):
        cancelling["booking"] = None
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        assert cancel(client, auth_headers).status_code == 404
        assert cancelling["cancels"] == []

    def test_a_booking_gone_by_the_time_the_function_runs_is_a_404(
        self, client, auth_headers, authenticate_as, cancelling
    ):
        cancelling["outcome"] = "booking_not_found"
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        assert cancel(client, auth_headers).status_code == 404


class TestRefusals:
    @pytest.mark.parametrize("status", ["rejected", "cancelled", "released", "expired"])
    def test_a_finished_booking_cant_be_cancelled_again(
        self, client, auth_headers, authenticate_as, cancelling, status
    ):
        # AC3, AC9: a double-click's second cancel lands here.
        cancelling["booking"]["status"] = status
        cancelling["outcome"] = "not_cancellable"
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = cancel(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "Only a Held or Approved booking can be cancelled."
        assert cancelling["booking"]["status"] == status

    def test_a_hold_that_expires_as_it_is_cancelled_says_so(self, client, auth_headers, authenticate_as, cancelling):
        # AC9, CR-99: the expiry won.
        cancelling["outcome"] = "hold_expired"
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = cancel(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "This hold has expired, so it can't be cancelled."

    def test_a_started_ended_or_cancelled_event_is_refused(self, client, auth_headers, authenticate_as, cancelling):
        # AC10.
        cancelling["outcome"] = "event_closed"
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        response = cancel(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "A booking can't be cancelled once its event has started, ended or been cancelled.")

    def test_a_database_outage_is_a_503(self, client, auth_headers, authenticate_as, cancelling, monkeypatch):
        def unavailable(*args, **kwargs):
            raise APIError({"message": "connection refused", "code": "08006"})

        monkeypatch.setattr(venues_repository, "cancel_booking", unavailable)
        authenticate_as("event_coordinator", user_id=COORDINATOR_ID)

        assert cancel(client, auth_headers).status_code == 503


class TestAccess:
    def test_a_coordinator_not_assigned_to_the_event_is_forbidden(
        self, client, auth_headers, authenticate_as, cancelling
    ):
        # AC5: the function re-checks the assignment under the event's lock.
        cancelling["outcome"] = "not_assigned"
        authenticate_as("event_coordinator", user_id=OTHER_COORDINATOR_ID)

        response = cancel(client, auth_headers)

        assert response.status_code == 403
        assert cancelling["booking"]["status"] == "held"

    @pytest.mark.parametrize("role", ["event_coordinator_lead", "venue_staff", "event_organiser",
                                      "safety_officer", "tech_support", "attendee"])
    def test_every_other_role_is_forbidden(self, client, auth_headers, authenticate_as, cancelling, role):
        # AC5: the Coordinator Lead included.
        authenticate_as(role, user_id=COORDINATOR_ID)

        assert cancel(client, auth_headers).status_code == 403
        assert cancelling["cancels"] == []

    def test_a_coordinator_acting_as_venue_staff_is_forbidden(self, client, auth_headers, monkeypatch, cancelling):
        # AC5, SCRUM-76: the seeded coordinator also holds venue_staff; acting as
        # venue staff they can't cancel, even though they hold the coordinator role.
        from tests.test_event_comments_api import acting_as_another_role

        acting_as_another_role(monkeypatch, COORDINATOR_ID, holds="event_coordinator", acts_as="venue_staff")

        assert cancel(client, auth_headers).status_code == 403
        assert cancelling["cancels"] == []

    def test_an_unauthenticated_request_is_refused(self, client, cancelling):
        assert client.post(CANCEL_URL).status_code == 401


class TestCancelRepository:
    def test_it_runs_the_database_function_with_the_messages(self, monkeypatch):
        from types import SimpleNamespace

        calls = []

        class Rpc:
            def execute(self):
                return SimpleNamespace(data=[{"outcome": "ok", "event_id": "e1", "from_status": "held"}])

        class AdminClient:
            def rpc(self, name, params):
                calls.append((name, params))
                return Rpc()

        monkeypatch.setattr(venues_repository, "get_supabase_admin_client", lambda: AdminClient())

        result = venues_repository.cancel_booking(BOOKING_ID, COORDINATOR_ID, staff_message="s", return_message="r")

        assert result == {"outcome": "ok", "event_id": "e1", "from_status": "held"}
        assert calls == [("cancel_venue_booking", {
            "p_booking_id": BOOKING_ID, "p_actor_id": COORDINATOR_ID,
            "p_staff_message": "s", "p_return_message": "r",
        })]
