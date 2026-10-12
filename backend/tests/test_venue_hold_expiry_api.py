"""CR-99 hold expiry, through the HTTP API with the repositories mocked.

What the expiry functions decide (the bounds, the history, the job, the race
with approval) is proven against the real database in
`supabase/verification/hold_expiry_checks.sql`. Here the fake returns each of
the function's outcome codes, and the tests pin down what the API makes of them.
"""

import pytest

from app.modules.venues import repository as venues_repository

STAFF_ID = "a0000000-0000-4000-8000-000000000003"
BOOKING_ID = "d0000000-0000-4000-8000-000000000999"
URL = f"/api/v1/venue-bookings/{BOOKING_ID}/expiry"
NEW_EXPIRY = "2031-08-05T12:00:00+08:00"


@pytest.fixture()
def expiry(monkeypatch):
    """`set_hold_expiry` records each call and answers with `state["outcome"]`,
    the way `public.set_venue_hold_expiry` answers."""
    state = {"outcome": "ok", "calls": []}

    def set_hold_expiry(booking_id, actor_id, expires_at):
        state["calls"].append({"booking_id": booking_id, "actor_id": actor_id, "expires_at": expires_at})
        return {"outcome": state["outcome"], "expires_at": "2031-08-05T04:00:00+00:00"}

    monkeypatch.setattr(venues_repository, "set_hold_expiry", set_hold_expiry)
    return state


def patch(client, auth_headers, expires_at=NEW_EXPIRY):
    return client.patch(URL, json={"expires_at": expires_at}, headers=auth_headers)


class TestChangeExpiry:
    def test_venue_staff_change_a_holds_expiry(self, client, auth_headers, authenticate_as, expiry):
        authenticate_as("venue_staff", user_id=STAFF_ID)

        response = patch(client, auth_headers)

        assert response.status_code == 200
        assert response.json() == {"id": BOOKING_ID, "status": "held", "expires_at": "2031-08-05T04:00:00Z"}
        [sent] = expiry["calls"]
        assert sent["booking_id"] == BOOKING_ID
        assert sent["actor_id"] == STAFF_ID
        assert sent["expires_at"].isoformat() == "2031-08-05T12:00:00+08:00"

    @pytest.mark.parametrize(
        ("outcome", "status_code", "detail"),
        [
            ("booking_not_found", 404, "Booking not found."),
            # AC2 "before it passes", AC5.
            ("hold_expired", 409, "This hold has already expired."),
            # AC4: an approved booking no longer expires.
            ("not_held", 409, "Only a held booking has an expiry to change."),
            # AC1: in the future and before the event starts.
            ("not_in_future", 422, "The new expiry must be in the future."),
            ("after_event_start", 422, "The new expiry can't be after the event starts."),
        ],
    )
    def test_a_refusal_from_the_database_is_answered_with_its_message(
        self, client, auth_headers, authenticate_as, expiry, outcome, status_code, detail
    ):
        expiry["outcome"] = outcome
        authenticate_as("venue_staff", user_id=STAFF_ID)

        response = patch(client, auth_headers)

        assert response.status_code == status_code
        assert response.json()["detail"] == detail

    @pytest.mark.parametrize("expires_at", ["2031-08-05T12:00:00", "", None, "next week"])
    def test_an_expiry_without_a_timezone_or_not_a_time_is_rejected_unsent(
        self, client, auth_headers, authenticate_as, expiry, expires_at
    ):
        authenticate_as("venue_staff", user_id=STAFF_ID)

        response = patch(client, auth_headers, expires_at=expires_at)

        assert response.status_code == 422
        assert expiry["calls"] == []

    @pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "attendee", "tech_support"])
    def test_only_venue_staff_change_an_expiry(self, client, auth_headers, authenticate_as, expiry, role):
        # The seeded coordinator also holds venue_staff; acting as coordinator
        # it is refused all the same (SCRUM-76: the active role decides).
        authenticate_as(role, user_id=STAFF_ID)

        response = patch(client, auth_headers)

        assert response.status_code == 403
        assert expiry["calls"] == []


class FakeBookingsTable:
    """Answers the event-booking read with `rows`, recording the filters, the
    order asked of Postgres, and the columns selected."""

    def __init__(self, rows):
        self.rows, self.calls = rows, {}

    def table(self, name):
        self.calls["table"] = name
        return self

    def select(self, columns):
        self.calls["select"] = columns
        return self

    def eq(self, column, value):
        self.calls["eq"] = (column, value)
        return self

    def in_(self, column, values):
        self.calls["in_"] = (column, sorted(values))
        return self

    def order(self, column, desc=False):
        self.calls["order"] = (column, desc)
        return self

    def execute(self):
        return type("Response", (), {"data": self.rows})()


class TestEventBookingRead:
    """`get_active_booking` feeds the coordinator's event page (SCRUM-19)."""

    def read(self, monkeypatch, rows):
        fake = FakeBookingsTable(rows)
        monkeypatch.setattr(venues_repository, "get_supabase_admin_client", lambda: fake)
        return venues_repository.get_active_booking("e-1"), fake.calls

    def test_an_active_booking_wins_over_a_newer_expired_hold(self, monkeypatch):
        # Newest first, as ordered by Postgres.
        rows = [{"id": "expired-new", "status": "expired"}, {"id": "held-old", "status": "held"}]

        row, calls = self.read(monkeypatch, rows)

        assert row["id"] == "held-old"
        assert calls["order"] == ("created_at", True)
        assert calls["in_"] == ("status", ["approved", "expired", "held", "re_review"])
        assert "expires_at" in calls["select"]

    def test_with_nothing_active_the_latest_expired_hold_is_returned(self, monkeypatch):
        # CR-99 AC7.
        rows = [{"id": "expired-new", "status": "expired"}, {"id": "expired-old", "status": "expired"}]

        row, _ = self.read(monkeypatch, rows)

        assert row["id"] == "expired-new"

    def test_no_booking_at_all_is_none(self, monkeypatch):
        row, _ = self.read(monkeypatch, [])

        assert row is None


class TestSetHoldExpiryCall:
    def test_the_rpc_gets_the_expiry_as_an_iso_instant_with_its_offset(self, monkeypatch):
        from datetime import datetime, timedelta, timezone

        sent = {}

        class Client:
            def rpc(self, name, params):
                sent.update(name=name, params=params)
                return self

            def execute(self):
                return type("Response", (), {"data": [{"outcome": "ok", "expires_at": "2031-08-05T04:00:00+00:00"}]})()

        monkeypatch.setattr(venues_repository, "get_supabase_admin_client", Client)

        result = venues_repository.set_hold_expiry(
            BOOKING_ID, STAFF_ID, datetime(2031, 8, 5, 12, tzinfo=timezone(timedelta(hours=8))))

        assert sent == {"name": "set_venue_hold_expiry", "params": {
            "p_booking_id": BOOKING_ID, "p_actor_id": STAFF_ID, "p_expires_at": "2031-08-05T12:00:00+08:00"}}
        assert result["outcome"] == "ok"
