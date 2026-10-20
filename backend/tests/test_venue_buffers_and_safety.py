"""CR-100: defaults, safety facts, history and active-role authorisation."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.events.schemas import SafetyReviewVenue
from app.modules.auth.dependencies import CurrentUser
from app.modules.venues import repository, service
from app.modules.venues.schemas import VenueProfile
from tests.test_event_comments_api import acting_as_another_role
from tests.test_venues_api import HALL_A_ID, VALID_EDIT_PAYLOAD, make_venue_profile

COORDINATOR = CurrentUser(id="a0000000-0000-4000-8000-000000000002", email="c@connectsphere.dev",
                          full_name="Coordinator", role="event_coordinator", session_id="s", access_token="t")

URL = f"/api/v1/venues/{HALL_A_ID}"
FACTS = dict(setup_minutes=30, turnaround_minutes=45,
             emergency_access="East exit\nEvacuate to courtyard", restrictions="No open flames")


@pytest.fixture()
def venue_state(monkeypatch):
    state = {"venue": make_venue_profile(HALL_A_ID, "Hall A"), "writes": []}
    monkeypatch.setattr(repository, "get_venue", lambda _: state["venue"])
    monkeypatch.setattr(repository, "list_upcoming_bookings", lambda *a: [])
    monkeypatch.setattr(repository, "list_upcoming_blocks", lambda *a: [])

    def save(venue_id, actor_id, expected_version, **values):
        state["writes"].append(values)
        state["venue"] = VenueProfile(**{
            **state["venue"].model_dump(), **values["after"], "version": expected_version + 1,
            "updated_by": {"id": actor_id},
        })
        return state["venue"], []

    monkeypatch.setattr(repository, "update_venue", save)
    return state


def test_default_zero_and_unrecorded_safety_details(client, authenticate_as, auth_headers, venue_state):
    authenticate_as("venue_staff")
    data = client.get(URL, headers=auth_headers).json()
    assert {key: data[key] for key in FACTS} == dict(
        setup_minutes=0, turnaround_minutes=0, emergency_access=None, restrictions=None)


@pytest.mark.parametrize("minutes", [0, 30, 1000000, 2147483647])
def test_save_read_and_history(client, authenticate_as, auth_headers, venue_state, minutes):
    actor = authenticate_as("venue_staff")
    facts = {**FACTS, "setup_minutes": minutes}
    response = client.patch(URL, headers=auth_headers, json={**VALID_EDIT_PAYLOAD, **facts})
    assert response.status_code == 200
    assert response.json()["warnings"] == []
    assert {key: response.json()["venue"][key] for key in facts} == facts
    read = client.get(URL, headers=auth_headers).json()
    assert {key: read[key] for key in facts} == facts
    assert read["updated_by"]["id"] == actor["id"]
    [write] = venue_state["writes"]
    assert {key: write["before"][key] for key in facts} == dict(
        setup_minutes=0, turnaround_minutes=0, emergency_access=None, restrictions=None)
    assert {key: write["after"][key] for key in facts} == facts
    assert write["flags"] == write["notifications"] == []


@pytest.mark.parametrize("field", ["setup_minutes", "turnaround_minutes"])
@pytest.mark.parametrize("value", [-1, 2147483648, "abc", "", "   ", None, True, 1.5])
def test_invalid_buffer_rejected_before_write(client, authenticate_as, auth_headers, venue_state, field, value):
    authenticate_as("venue_staff")
    response = client.patch(URL, headers=auth_headers, json={**VALID_EDIT_PAYLOAD, **FACTS, field: value})
    assert response.status_code == 422
    assert venue_state["writes"] == []


def test_safety_text_can_be_cleared(client, authenticate_as, auth_headers, venue_state):
    authenticate_as("venue_staff")
    venue_state["venue"] = make_venue_profile(HALL_A_ID, "Hall A", **FACTS)
    response = client.patch(URL, headers=auth_headers, json={
        **VALID_EDIT_PAYLOAD, **FACTS, "emergency_access": " \n ", "restrictions": None})
    assert response.status_code == 200
    assert response.json()["venue"]["emergency_access"] is None
    assert response.json()["venue"]["restrictions"] is None
    [write] = venue_state["writes"]
    assert write["before"]["emergency_access"] == FACTS["emergency_access"]
    assert write["after"]["emergency_access"] is None


@pytest.mark.parametrize("role", ["event_organiser", "event_coordinator", "event_coordinator_lead",
                                  "safety_officer", "tech_support", "attendee"])
def test_only_active_venue_staff_may_edit(client, authenticate_as, auth_headers, venue_state, role):
    authenticate_as(role)
    assert client.patch(URL, headers=auth_headers, json={**VALID_EDIT_PAYLOAD, **FACTS}).status_code == 403
    assert venue_state["writes"] == []


def test_venue_staff_holder_acting_as_coordinator_is_denied(client, auth_headers, venue_state, monkeypatch):
    acting_as_another_role(monkeypatch, "a0000000-0000-4000-8000-000000000002",
                          "venue_staff", "event_coordinator")
    assert client.patch(URL, headers=auth_headers, json={**VALID_EDIT_PAYLOAD, **FACTS}).status_code == 403
    assert venue_state["writes"] == []


def test_repository_profile_maps_real_columns(monkeypatch):
    row = {**VALID_EDIT_PAYLOAD, **FACTS, "id": HALL_A_ID, "is_active": True,
           "updated_at": "2026-10-18T01:00:00Z", "version": 1}
    query = MagicMock()
    query.select.return_value = query.eq.return_value = query.maybe_single.return_value = query
    query.execute.return_value = SimpleNamespace(data=row)
    admin = MagicMock()
    admin.table.return_value = query
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: admin)
    venue = repository.get_venue(HALL_A_ID)
    assert {key: venue.model_dump()[key] for key in FACTS} == FACTS
    selected = query.select.call_args.args[0]
    assert all(key in selected for key in FACTS)


def test_safety_review_receives_real_venue_facts(monkeypatch):
    monkeypatch.setattr(repository, "list_event_bookings_with_venues", lambda _: [{
        "id": "booking", "venue_id": HALL_A_ID, "status": "approved",
        "venues": {"name": "Hall A", "capacity": 150, **FACTS},
    }])
    [item] = service.event_bookings_with_venues("event")
    parsed = SafetyReviewVenue(**item).model_dump()
    assert parsed["emergency_access"] == FACTS["emergency_access"]
    assert parsed["restrictions"] == FACTS["restrictions"]


@pytest.mark.parametrize("start,end,unavailable", [
    ("2031-05-20T09:00:00Z", "2031-05-20T09:30:00Z", False),
    ("2031-05-20T09:00:00Z", "2031-05-20T09:31:00Z", True),
    ("2031-05-20T12:44:00Z", "2031-05-20T13:00:00Z", True),
    ("2031-05-20T12:45:00Z", "2031-05-20T13:00:00Z", False),
])
def test_search_includes_candidate_buffers_and_touching_boundaries(monkeypatch, start, end, unavailable):
    from app.modules.venues.schemas import VenueSearchCriteria, Occupant, Period

    venue = make_venue_profile(HALL_A_ID, "Hall A", **FACTS)
    reads = []
    monkeypatch.setattr(repository, "list_venues", lambda: [venue])

    def occupants(period):
        reads.append(period.model_dump(mode="json"))
        return {HALL_A_ID: [Occupant(kind="block", detail="maintenance",
                                   period=Period(starts_at=start, ends_at=end))]}

    monkeypatch.setattr(repository, "list_occupants", occupants)
    result = service.search_venues(VenueSearchCriteria(
        starts_at="2031-05-20T10:00:00Z", ends_at="2031-05-20T12:00:00Z", include_excluded=True), COORDINATOR)
    assert result.results[0].excluded is unavailable
    assert reads == [{"starts_at": "2031-05-20T09:30:00Z", "ends_at": "2031-05-20T12:45:00Z"}]


@pytest.mark.parametrize("starts,ends,setup,turnaround,first_year,last_year", [
    ("2031-05-20T10:00:00Z", "2031-05-20T12:00:00Z", 2147483647, 0, 1, 2031),
    ("9998-05-20T10:00:00Z", "9998-05-20T12:00:00Z", 0, 2147483647, 9998, 9999),
])
def test_large_valid_defaults_do_not_crash_dated_search(monkeypatch, starts, ends, setup, turnaround, first_year, last_year):
    from app.modules.venues.schemas import VenueSearchCriteria

    venues = [make_venue_profile(HALL_A_ID, "Hall A", setup_minutes=setup, turnaround_minutes=turnaround),
              make_venue_profile("b0000000-0000-4000-8000-000000000002", "Hall B")]
    reads = []
    monkeypatch.setattr(repository, "list_venues", lambda: venues)
    monkeypatch.setattr(repository, "list_occupants", lambda period: reads.append(period) or {})
    result = service.search_venues(VenueSearchCriteria(starts_at=starts, ends_at=ends), COORDINATOR)
    assert result.included_count == 2
    assert reads[0].starts_at.year == first_year
    assert reads[0].ends_at.year == last_year
    assert venues[0].setup_minutes == setup
    assert venues[0].turnaround_minutes == turnaround


@pytest.mark.parametrize("method", ["get_booking", "list_upcoming_bookings", "list_flaggable_bookings", "list_all_upcoming_bookings"])
def test_booking_reads_display_booked_window_not_buffered_occupation(monkeypatch, method):
    from datetime import datetime, timezone

    query = MagicMock()
    for name in ("select", "eq", "in_", "is_", "overlaps", "limit"):
        getattr(query, name).return_value = query
    query.execute.return_value.data = [{"id": "booking", "event_id": "event", "venue_id": HALL_A_ID,
        "status": "held", "created_at": "2030-01-01T00:00:00Z",
        "booked_period": '["2031-05-20 10:00:00+00","2031-05-20 12:00:00+00")',
        "occupied_period": '["2031-05-20 09:30:00+00","2031-05-20 12:45:00+00")'}]
    admin = MagicMock(); admin.table.return_value = query
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: admin)
    since = datetime(2030, 1, 1, tzinfo=timezone.utc)
    if method == "get_booking":
        period = repository.get_booking("booking")["period"]
    elif method == "list_all_upcoming_bookings":
        [booking] = repository.list_all_upcoming_bookings(since, {"held"})
        period = booking.period
    else:
        [booking] = getattr(repository, method)(HALL_A_ID, since)
        period = booking.period
    assert period.starts_at.isoformat() == "2031-05-20T10:00:00+00:00"
    assert period.ends_at.isoformat() == "2031-05-20T12:00:00+00:00"


def test_occupied_dates_outside_python_range_remain_comparable_and_are_labelled(monkeypatch):
    from app.modules.venues.schemas import Period, VenueSearchCriteria, BookingConflict
    from app.modules.venues import search

    query = MagicMock()
    query.execute.return_value.data = [{"kind": "booking", "venue_id": HALL_A_ID, "booking_status": "approved",
        "occupied_period": '["2053-06-12 07:52:00+00 BC","12001-05-20 12:00:00+00")'}]
    admin = MagicMock(); admin.rpc.return_value = query
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: admin)
    period = Period(starts_at="2031-05-20T10:00:00Z", ends_at="2031-05-20T12:00:00Z")
    occupants = repository.list_occupants(period)
    result = search.evaluate(make_venue_profile(HALL_A_ID, "Hall A"), VenueSearchCriteria(
        starts_at=period.starts_at, ends_at=period.ends_at), occupants[HALL_A_ID])
    assert result.excluded is True
    assert "beyond supported dates" in result.reasons[0].message
    conflict = BookingConflict(kind="booking", event_name="Long setup", starts_at="2053-06-12T07:52:00+00:00 BC",
                               ends_at="12001-05-20T12:00:00+00:00")
    assert conflict.starts_at.year == 1 and conflict.ends_at.year == 9999


def test_conflict_contract_also_accepts_already_parsed_datetimes():
    from datetime import datetime, timezone
    from app.modules.venues.schemas import BookingConflict

    starts = datetime(2031, 5, 20, 10, tzinfo=timezone.utc)
    ends = datetime(2031, 5, 20, 12, tzinfo=timezone.utc)
    conflict = BookingConflict(kind="booking", starts_at=starts, ends_at=ends)
    assert conflict.starts_at == starts and conflict.ends_at == ends


def test_upcoming_bookings_keep_a_booking_still_in_its_turnaround(monkeypatch):
    from datetime import datetime, timezone

    query = MagicMock()
    for name in ("select", "eq", "in_"):
        getattr(query, name).return_value = query
    query.execute.return_value.data = [{"id": "booking", "event_id": "event", "status": "approved",
        "booked_period": '["2031-05-20 10:00:00+00","2031-05-20 12:00:00+00")',
        "occupied_period": '["2031-05-20 09:30:00+00","2031-05-20 12:45:00+00")'}]
    admin = MagicMock(); admin.table.return_value = query
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: admin)
    # 12:30: the event has ended but its turnaround still occupies the venue.
    [booking] = repository.list_upcoming_bookings(HALL_A_ID, datetime(2031, 5, 20, 12, 30, tzinfo=timezone.utc))
    assert booking.period.ends_at.isoformat() == "2031-05-20T12:00:00+00:00"
    [booking_after] = repository.list_upcoming_bookings(HALL_A_ID, datetime(2031, 5, 20, 12, 44, tzinfo=timezone.utc))
    assert booking_after.id == "booking"
    assert repository.list_upcoming_bookings(HALL_A_ID, datetime(2031, 5, 20, 12, 45, tzinfo=timezone.utc)) == []
