"""CR-95 AC9: venue staff restore an affected booking, through the HTTP API with the repositories mocked.

Whether the venue is free again, and what restoring changes, is decided by
`public.restore_affected_booking` and proven against the real database in
`supabase/verification/venue_restore_checks.sql`. Here the fake answers with each
of the function's outcome codes, and the tests pin down what the API makes of
them and who may call it.
"""

from copy import deepcopy

import pytest

from app.modules.venues import repository as venues_repository
from tests.test_venue_booking_reject_api import (  # noqa: F401  (bookings is the fixture)
    BOOKING_ID,
    COORDINATOR_ID,
    URL,
    VENUE_STAFF_ID,
    bookings,
)

RESTORE_URL = f"{URL}/restore"
AFFECTED = {"status": "approved", "flag": "affected", "flag_reason": "Venue unavailable: maintenance"}


@pytest.fixture()
def restoring(bookings, monkeypatch):  # noqa: F811
    """The booking is affected; `restore_affected_booking` records each call, answers with
    `state["outcome"]` and on `ok` clears the flag the way the database function does."""
    bookings["booking"].update(AFFECTED)
    bookings["restores"] = []

    def restore_affected_booking(booking_id, actor_id):
        bookings["restores"].append((booking_id, actor_id))
        if bookings["outcome"] == "ok":
            bookings["booking"].update(flag=None, flag_reason=None)
        return {"outcome": bookings["outcome"], "cancelled_booking_ids": []}

    monkeypatch.setattr(venues_repository, "restore_affected_booking", restore_affected_booking)
    return bookings


class TestRestore:
    def test_venue_staff_restore_the_booking_and_see_it_unflagged(
        self, client, auth_headers, authenticate_as, restoring
    ):
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        response = client.post(RESTORE_URL, headers=auth_headers)

        assert response.status_code == 200
        assert restoring["restores"] == [(BOOKING_ID, VENUE_STAFF_ID)]
        body = response.json()
        assert (body["status"], body["flag"], body["flag_reason"]) == ("approved", None, None)

    def test_the_booking_page_shows_why_a_booking_is_affected(self, client, auth_headers, authenticate_as, restoring):
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)

        body = client.get(URL, headers=auth_headers).json()

        assert (body["flag"], body["flag_reason"]) == ("affected", "Venue unavailable: maintenance")

    @pytest.mark.parametrize(
        "outcome,message",
        [
            ("not_affected", "isn't waiting"),
            ("replacement_approved", "replacement has already been approved"),
            ("venue_inactive", "inactive"),
            ("still_blocked", "still blocked"),
            ("held_by_other", "taken"),
        ],
    )
    def test_each_refusal_is_a_409_that_says_why_and_changes_nothing(
        self, client, auth_headers, authenticate_as, restoring, outcome, message
    ):
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)
        restoring["outcome"] = outcome

        response = client.post(RESTORE_URL, headers=auth_headers)

        assert response.status_code == 409
        assert message in response.json()["detail"]
        assert restoring["booking"]["flag"] == "affected"

    def test_a_booking_that_does_not_exist_is_a_404(self, client, auth_headers, authenticate_as, restoring):
        authenticate_as("venue_staff", user_id=VENUE_STAFF_ID)
        restoring["outcome"] = "booking_not_found"

        assert client.post(RESTORE_URL, headers=auth_headers).status_code == 404

    @pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "tech_support", "attendee"])
    def test_every_other_role_is_forbidden(self, client, auth_headers, authenticate_as, restoring, role):
        authenticate_as(role, user_id=COORDINATOR_ID)

        assert client.post(RESTORE_URL, headers=auth_headers).status_code == 403
        assert restoring["restores"] == []

    def test_a_venue_staff_holder_acting_as_coordinator_is_forbidden(
        self, client, auth_headers, monkeypatch, restoring
    ):
        from tests.test_event_comments_api import acting_as_another_role

        acting_as_another_role(monkeypatch, COORDINATOR_ID, holds="venue_staff", acts_as="event_coordinator")

        assert client.post(RESTORE_URL, headers=auth_headers).status_code == 403
        assert restoring["restores"] == []

    def test_an_unauthenticated_request_is_refused(self, client, restoring):
        assert client.post(RESTORE_URL).status_code == 401


class TestRestoreRepository:
    def test_it_runs_the_database_function_for_the_booking_and_actor(self, monkeypatch):
        from types import SimpleNamespace

        calls = []

        class Rpc:
            def execute(self):
                return SimpleNamespace(data=[{"outcome": "ok", "cancelled_booking_ids": ["b2"]}])

        class AdminClient:
            def rpc(self, name, params):
                calls.append((name, params))
                return Rpc()

        monkeypatch.setattr(venues_repository, "get_supabase_admin_client", lambda: AdminClient())

        result = venues_repository.restore_affected_booking(BOOKING_ID, VENUE_STAFF_ID)

        assert result == {"outcome": "ok", "cancelled_booking_ids": ["b2"]}
        assert calls == [("restore_affected_booking", {"p_booking_id": BOOKING_ID, "p_actor_id": VENUE_STAFF_ID})]
