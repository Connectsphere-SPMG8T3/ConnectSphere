"""SCRUM-57: a venue's availability calendar for Venue Staff (AC1–AC3, AC5–AC11).

Which bookings and blocks occupy a venue is decided by `public.venue_conflicts`,
the one conflict check (SCRUM-21), and proven against the real database by the
live checks (TC-VCAL). Here the fakes answer as that check would, and the tests
pin down how the API types each entry, which period it asks about and who may
call it.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.events import service as events_service
from app.modules.venues import repository
from app.modules.venues.schemas import CalendarBooking, Editor, Period, VenueBlock
from tests.test_venues_api import HALL_A_ID, HALL_B_ID, make_venue

URL = f"/api/v1/venues/{HALL_A_ID}/calendar"
STAFF_ID = "a0000000-0000-4000-8000-000000000003"
EVENT_ID = "e0000000-0000-4000-8000-000000000571"
NOW = datetime.now(timezone.utc)
FROM = NOW + timedelta(days=1)
TO = FROM + timedelta(days=7)


def _booking(booking_id: str, status: str, *, flag=None, expires_at=None, setup=30, turnaround=45) -> CalendarBooking:
    starts = FROM + timedelta(hours=10)
    ends = starts + timedelta(hours=2)
    return CalendarBooking(
        id=booking_id, event_id=EVENT_ID, status=status,
        period=Period(starts_at=starts, ends_at=ends),
        occupied_period=Period(starts_at=starts - timedelta(minutes=setup), ends_at=ends + timedelta(minutes=turnaround)),
        setup_minutes=setup, turnaround_minutes=turnaround, expires_at=expires_at, flag=flag,
        flag_reason="Venue unavailable: maintenance" if flag == "affected" else None,
    )


def _block(**changes) -> VenueBlock:
    fields = {"id": "f0000000-0000-4000-8000-000000000571", "reason": "maintenance", "notes": "Aircon",
              "period": Period(starts_at=FROM, ends_at=FROM + timedelta(hours=4)), "status": "active",
              "created_by": Editor(id=STAFF_ID, full_name="Vera Staff"), "created_at": NOW - timedelta(days=1)}
    return VenueBlock(**{**fields, **changes})


@pytest.fixture()
def calendar(monkeypatch):
    state = {"bookings": [], "blocks": [], "calls": [], "venue": make_venue(HALL_A_ID, "Hall A")}
    monkeypatch.setattr(repository, "get_venue", lambda venue_id: state["venue"] if venue_id == HALL_A_ID else None)
    monkeypatch.setattr(repository, "list_venues", lambda: [
        make_venue(HALL_A_ID, "Hall A"), make_venue(HALL_B_ID, "Hall B", is_active=False)])
    monkeypatch.setattr(events_service, "names_by_id", lambda ids: {EVENT_ID: "Gala"})

    def _occupants(venue_id, period):
        state["calls"].append((venue_id, period))
        return state["bookings"], state["blocks"]

    monkeypatch.setattr(repository, "list_calendar_occupants", _occupants)
    return state


def _params(starts=FROM, ends=TO) -> dict:
    return {"starts_at": starts.isoformat(), "ends_at": ends.isoformat()}


def _get(client, auth_headers, **kwargs):
    return client.get(URL, params=_params(**kwargs), headers=auth_headers)


class TestEntryTypes:
    """AC2, AC3, AC8: each occupant is typed; an Affected flag outranks the status."""

    @pytest.mark.parametrize(("status", "flag", "expected"), [
        ("approved", None, "confirmed"),
        ("held", None, "tentative"),
        ("re_review", None, "re_review"),
        ("approved", "affected", "affected"),
        ("held", "affected", "affected"),
        ("approved", "unsuitable", "confirmed"),
    ])
    def test_a_booking_is_typed_by_status_and_flag(self, client, auth_headers, authenticate_as, calendar,
                                                    status, flag, expected):
        authenticate_as("venue_staff")
        expires = NOW + timedelta(days=1) if status == "held" else None
        calendar["bookings"] = [_booking("d1", status, flag=flag, expires_at=expires)]
        entry = _get(client, auth_headers).json()["entries"][0]
        assert entry["kind"] == "booking" and entry["type"] == expected
        assert entry["status"] == status and entry["flag"] == flag

    def test_a_block_is_blocked_with_its_reason_and_who_set_it(self, client, auth_headers, authenticate_as,
                                                               calendar):
        authenticate_as("venue_staff")
        calendar["blocks"] = [_block()]
        entry = _get(client, auth_headers).json()["entries"][0]
        assert entry["kind"] == "block" and entry["type"] == "blocked"
        assert entry["reason"] == "maintenance" and entry["notes"] == "Aircon"
        assert entry["created_by"] == {"id": STAFF_ID, "full_name": "Vera Staff"}
        assert entry["status"] is None and entry["event_name"] is None

    def test_a_shortened_block_shows_only_its_remaining_period(self, client, auth_headers, authenticate_as,
                                                               calendar):
        authenticate_as("venue_staff")
        remaining = Period(starts_at=FROM, ends_at=FROM + timedelta(hours=1))
        calendar["blocks"] = [_block(status="ended_early", period=remaining,
                                     original_period=Period(starts_at=FROM, ends_at=FROM + timedelta(hours=4)))]
        entry = _get(client, auth_headers).json()["entries"][0]
        assert entry["period"]["ends_at"] == remaining.ends_at.isoformat().replace("+00:00", "Z")
        assert entry["occupied_period"] == entry["period"]

    def test_a_hold_already_past_its_expiry_is_left_out(self, client, auth_headers, authenticate_as, calendar):
        """AC6: before the minute job marks it expired, it already stops occupying."""
        authenticate_as("venue_staff")
        calendar["bookings"] = [_booking("d1", "held", expires_at=NOW - timedelta(seconds=1)),
                                _booking("d2", "held", expires_at=NOW + timedelta(hours=1))]
        entries = _get(client, auth_headers).json()["entries"]
        assert [e["id"] for e in entries] == ["d2"]
        assert entries[0]["expires_at"] is not None


class TestBookingDetails:
    """AC5, AC7, AC9: a booking carries its event, booked time and its own buffers."""

    def test_a_booking_has_its_event_name_window_and_buffers(self, client, auth_headers, authenticate_as,
                                                             calendar):
        authenticate_as("venue_staff")
        calendar["bookings"] = [_booking("d1", "approved", setup=30, turnaround=45)]
        entry = _get(client, auth_headers).json()["entries"][0]
        assert entry["event_id"] == EVENT_ID and entry["event_name"] == "Gala"
        assert entry["setup_minutes"] == 30 and entry["turnaround_minutes"] == 45
        assert entry["period"] != entry["occupied_period"]

    def test_an_unreadable_event_name_is_null(self, client, auth_headers, authenticate_as, calendar, monkeypatch):
        authenticate_as("venue_staff")
        monkeypatch.setattr(events_service, "names_by_id", lambda ids: {})
        calendar["bookings"] = [_booking("d1", "approved")]
        assert _get(client, auth_headers).json()["entries"][0]["event_name"] is None

    def test_entries_are_ordered_by_occupied_start_then_id(self, client, auth_headers, authenticate_as, calendar):
        authenticate_as("venue_staff")
        calendar["bookings"] = [_booking("d2", "approved"), _booking("d1", "approved")]
        calendar["blocks"] = [_block()]
        ids = [e["id"] for e in _get(client, auth_headers).json()["entries"]]
        assert ids == [_block().id, "d1", "d2"]

    def test_no_occupants_is_an_empty_list_without_naming_events(self, client, auth_headers, authenticate_as,
                                                                 calendar, monkeypatch):
        authenticate_as("venue_staff")
        monkeypatch.setattr(events_service, "names_by_id", lambda ids: pytest.fail("named nothing"))
        assert _get(client, auth_headers).json()["entries"] == []


class TestVenueAndPeriod:
    """AC1, AC3, AC10: the venue, every venue to switch to, the timezone and the period asked about."""

    def test_the_response_names_the_venue_timezone_and_every_venue(self, client, auth_headers, authenticate_as,
                                                                   calendar):
        authenticate_as("venue_staff")
        body = _get(client, auth_headers).json()
        assert body["venue"] == {"id": HALL_A_ID, "name": "Hall A", "is_active": True}
        assert body["timezone"] == "Asia/Singapore"
        assert body["venues"] == [{"id": HALL_A_ID, "name": "Hall A", "is_active": True},
                                  {"id": HALL_B_ID, "name": "Hall B", "is_active": False}]

    def test_a_future_period_is_asked_about_as_given(self, client, auth_headers, authenticate_as, calendar):
        authenticate_as("venue_staff")
        _get(client, auth_headers)
        venue_id, period = calendar["calls"][0]
        assert venue_id == HALL_A_ID and period == Period(starts_at=FROM, ends_at=TO)

    def test_a_period_already_under_way_is_asked_about_from_now(self, client, auth_headers, authenticate_as,
                                                                 calendar):
        """AC3: current or upcoming only, so nothing that has ended is sent."""
        authenticate_as("venue_staff")
        body = _get(client, auth_headers, starts=NOW - timedelta(days=3), ends=NOW + timedelta(days=3)).json()
        _, period = calendar["calls"][0]
        assert NOW <= period.starts_at <= datetime.now(timezone.utc)
        assert body["period"]["starts_at"] == (NOW - timedelta(days=3)).isoformat().replace("+00:00", "Z")

    def test_a_period_wholly_past_asks_nothing(self, client, auth_headers, authenticate_as, calendar):
        authenticate_as("venue_staff")
        body = _get(client, auth_headers, starts=NOW - timedelta(days=9), ends=NOW - timedelta(days=2)).json()
        assert body["entries"] == [] and calendar["calls"] == []

    def test_an_unknown_venue_is_404(self, client, auth_headers, authenticate_as, calendar):
        authenticate_as("venue_staff")
        response = client.get(f"/api/v1/venues/{HALL_B_ID}/calendar", params=_params(), headers=auth_headers)
        assert response.status_code == 404 and calendar["calls"] == []

    @pytest.mark.parametrize("params", [
        {"starts_at": TO.isoformat(), "ends_at": FROM.isoformat()},
        {"starts_at": FROM.isoformat(), "ends_at": FROM.isoformat()},
        {"starts_at": "2031-01-01T00:00:00", "ends_at": "2031-01-08T00:00:00"},
        {"starts_at": FROM.isoformat()},
        {},
        {"starts_at": FROM.isoformat(), "ends_at": (FROM + timedelta(days=42, seconds=1)).isoformat()},
    ])
    def test_a_bad_period_is_422(self, client, auth_headers, authenticate_as, calendar, params):
        authenticate_as("venue_staff")
        assert client.get(URL, params=params, headers=auth_headers).status_code == 422
        assert calendar["calls"] == []

    def test_a_six_week_month_grid_is_accepted(self, client, auth_headers, authenticate_as, calendar):
        authenticate_as("venue_staff")
        assert _get(client, auth_headers, ends=FROM + timedelta(days=42)).status_code == 200


class TestAccess:
    """AC11: only a session acting as Venue Staff may read a venue's calendar."""

    @pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "event_coordinator_lead",
                                      "tech_support", "safety_officer", "attendee"])
    def test_every_other_role_is_forbidden(self, client, auth_headers, authenticate_as, calendar, role):
        authenticate_as(role)
        assert _get(client, auth_headers).status_code == 403
        assert calendar["calls"] == []

    def test_a_venue_staff_holder_acting_as_coordinator_is_forbidden(self, client, auth_headers, monkeypatch,
                                                                      calendar):
        from tests.test_event_comments_api import acting_as_another_role

        acting_as_another_role(monkeypatch, STAFF_ID, holds="venue_staff", acts_as="event_coordinator")
        assert _get(client, auth_headers).status_code == 403
        assert calendar["calls"] == []

    def test_an_unauthenticated_request_is_refused(self, client, calendar):
        assert client.get(URL, params=_params()).status_code == 401
