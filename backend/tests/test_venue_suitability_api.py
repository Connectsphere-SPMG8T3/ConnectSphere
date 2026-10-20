"""SCRUM-18 venue suitability on venue search, through the HTTP API with the
repositories mocked. The rules themselves are in test_venue_suitability.py.

A search carries a suitability verdict only when it names an event (and
optionally one of its spaces). The requirements always come from the stored
event or space, never from the client's filters (AC11).
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.events import repository as events_repository
from app.modules.venues import repository
from app.modules.venues.schemas import (
    Facility,
    LayoutOption,
    Occupant,
    Period,
    VenueLayout,
)
from tests.test_venues_api import make_venue

SGT = timezone(timedelta(hours=8))
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_COORDINATOR_ID = "a0000000-0000-4000-8000-000000000009"
EVENT_ID = "e0000000-0000-4000-8000-000000000202"
SPACE_ID = "f0000000-0000-4000-8000-000000000001"
HALL_ID = "b0000000-0000-4000-8000-000000000011"
ROOM_ID = "b0000000-0000-4000-8000-000000000012"
URL = "/api/v1/venues"

EVENT_START = datetime(2026, 10, 10, 14, tzinfo=SGT)


def event_row(**overrides):
    row = {
        "id": EVENT_ID, "coordinator_id": COORDINATOR_ID, "status": "planning", "name": "Partner Summit",
        "starts_at": EVENT_START.isoformat(), "ends_at": (EVENT_START + timedelta(hours=3)).isoformat(),
        "expected_attendance": 500, "layout_preference": "theatre", "facilities_required": ["projector"],
        "accessibility_needs": None,
        "spaces": [
            {"id": SPACE_ID, "event_id": EVENT_ID, "label": "Breakout", "expected_pax": 50,
             "layout_preference": "classroom", "facilities_required": ["whiteboard"],
             "starts_at": None, "ends_at": None, "is_primary": False, "version": 0},
        ],
    }
    row.update(overrides)
    return row


@pytest.fixture()
def world(monkeypatch):
    """A 60-seat classroom with a whiteboard, and a 150-seat hall with a
    projector, plus one stored event whose coordinator is COORDINATOR_ID."""
    state = {"event": event_row(), "occupants": {}}
    state["venues"] = [
        make_venue(
            ROOM_ID, "Room 1", capacity=60, facilities=[Facility.whiteboard],
            layouts=[LayoutOption(layout=VenueLayout.classroom, capacity_for_layout=None)],
        ),
        make_venue(HALL_ID, "Hall 1", capacity=150, facilities=[Facility.projector]),
    ]

    def get_event(event_id):
        return deepcopy(state["event"]) if event_id == EVENT_ID else None

    def get_space(space_id):
        return next((deepcopy(s) for s in state["event"]["spaces"] if s["id"] == space_id), None)

    monkeypatch.setattr(repository, "list_venues", lambda: state["venues"])
    monkeypatch.setattr(repository, "list_occupants", lambda period: state["occupants"])
    monkeypatch.setattr(events_repository, "get_event", get_event)
    monkeypatch.setattr(events_repository, "get_space", get_space)
    return state


def search(client, auth_headers, **params):
    return client.get(URL, params={"include_excluded": "true", **params}, headers=auth_headers)


def by_name(response):
    assert response.status_code == 200, response.text
    return {r["venue"]["name"]: r for r in response.json()["results"]}


class TestWithoutEventContext:
    def test_plain_search_carries_no_suitability(self, client, auth_headers, authenticate_as, world):
        authenticate_as("event_coordinator", COORDINATOR_ID)

        results = by_name(search(client, auth_headers))

        assert all(r["suitability"] is None for r in results.values())


class TestEventRequirements:
    """AC1–AC7 against an event with no spaces: its own pax, layout, facilities."""

    @pytest.fixture(autouse=True)
    def event_without_spaces(self, world):
        world["event"] = event_row(spaces=[], expected_attendance=150, layout_preference="theatre")

    def test_attendance_equal_to_capacity_passes_and_a_missing_facility_is_named(
        self, client, auth_headers, authenticate_as, world
    ):
        authenticate_as("event_coordinator", COORDINATOR_ID)

        results = by_name(search(client, auth_headers, event_id=EVENT_ID))

        assert results["Hall 1"]["suitability"] == {"verdict": "suitable", "reasons": []}
        room = results["Room 1"]["suitability"]
        assert room["verdict"] == "unsuitable"
        assert [r["code"] for r in room["reasons"]] == ["capacity", "missing_facility", "layout_not_supported"]
        assert room["reasons"][1]["message"] == "Missing facilities this event needs: projector."

    def test_the_per_layout_capacity_replaces_the_overall_capacity(
        self, client, auth_headers, authenticate_as, world
    ):
        world["venues"] = [
            make_venue(
                HALL_ID, "Hall 1", capacity=300,
                layouts=[LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=100)],
            )
        ]
        authenticate_as("event_coordinator", COORDINATOR_ID)

        hall = by_name(search(client, auth_headers, event_id=EVENT_ID))["Hall 1"]["suitability"]

        assert hall["reasons"][0]["message"] == "Capacity 100 is below the expected attendance of 150."

    def test_an_inactive_venue_is_unsuitable(self, client, auth_headers, authenticate_as, world):
        world["venues"] = [make_venue(HALL_ID, "Hall 1", is_active=False)]
        authenticate_as("event_coordinator", COORDINATOR_ID)

        hall = by_name(search(client, auth_headers, event_id=EVENT_ID))["Hall 1"]["suitability"]

        assert hall["verdict"] == "unsuitable"
        assert hall["reasons"][0]["code"] == "inactive"

    def test_unsupported_layout_accessibility_and_hours_are_warnings_each_listed(
        self, client, auth_headers, authenticate_as, world
    ):
        world["event"] = event_row(
            spaces=[], expected_attendance=10, layout_preference="banquet", facilities_required=[],
            accessibility_needs="a hearing loop", starts_at=EVENT_START.replace(hour=6).isoformat(),
        )
        authenticate_as("event_coordinator", COORDINATOR_ID)

        hall = by_name(search(client, auth_headers, event_id=EVENT_ID))["Hall 1"]["suitability"]

        assert hall["verdict"] == "suitable_with_warnings"
        assert [r["code"] for r in hall["reasons"]] == [
            "layout_not_supported", "missing_accessibility", "outside_operating_hours",
        ]

    def test_availability_is_reported_separately_from_suitability(self, client, auth_headers, authenticate_as, world):
        world["occupants"] = {
            HALL_ID: [Occupant(
                kind="booking", detail="held",
                period=Period(starts_at=EVENT_START, ends_at=EVENT_START + timedelta(hours=1)),
            )]
        }
        authenticate_as("event_coordinator", COORDINATOR_ID)

        hall = by_name(search(
            client, auth_headers, event_id=EVENT_ID,
            starts_at=EVENT_START.isoformat(), ends_at=(EVENT_START + timedelta(hours=3)).isoformat(),
        ))["Hall 1"]

        assert hall["availability"] == "unavailable"
        assert hall["suitability"]["verdict"] == "suitable"

    def test_the_stored_requirements_win_over_the_clients_filters(self, client, auth_headers, authenticate_as, world):
        authenticate_as("event_coordinator", COORDINATOR_ID)

        results = by_name(search(client, auth_headers, event_id=EVENT_ID, min_capacity=1, layout="classroom"))

        assert results["Hall 1"]["suitability"]["verdict"] == "suitable"


class TestSpaceRequirements:
    """AC11: a space is judged on its own pax, layout and facilities."""

    def test_a_breakout_room_passes_even_though_the_event_is_bigger(
        self, client, auth_headers, authenticate_as, world
    ):
        authenticate_as("event_coordinator", COORDINATOR_ID)

        results = by_name(search(client, auth_headers, space_id=SPACE_ID))

        assert results["Room 1"]["suitability"] == {"verdict": "suitable", "reasons": []}
        hall = results["Hall 1"]["suitability"]
        assert hall["verdict"] == "unsuitable"
        assert [r["code"] for r in hall["reasons"]] == ["missing_facility", "layout_not_supported"]

    def test_the_event_id_may_accompany_its_space(self, client, auth_headers, authenticate_as, world):
        authenticate_as("event_coordinator", COORDINATOR_ID)

        results = by_name(search(client, auth_headers, event_id=EVENT_ID, space_id=SPACE_ID))

        assert results["Room 1"]["suitability"]["verdict"] == "suitable"

    def test_a_space_window_replaces_the_event_window(self, client, auth_headers, authenticate_as, world):
        world["event"]["spaces"][0]["starts_at"] = EVENT_START.replace(hour=6).isoformat()
        world["event"]["spaces"][0]["ends_at"] = EVENT_START.replace(hour=7).isoformat()
        authenticate_as("event_coordinator", COORDINATOR_ID)

        room = by_name(search(client, auth_headers, space_id=SPACE_ID))["Room 1"]["suitability"]

        assert [r["code"] for r in room["reasons"]] == ["outside_operating_hours"]

    def test_a_space_that_says_nothing_falls_back_to_the_event(self, client, auth_headers, authenticate_as, world):
        space = world["event"]["spaces"][0]
        space.update(expected_pax=None, layout_preference=None, facilities_required=[])
        world["event"].update(expected_attendance=100, layout_preference=None, facilities_required=[])
        authenticate_as("event_coordinator", COORDINATOR_ID)

        results = by_name(search(client, auth_headers, space_id=SPACE_ID))

        assert results["Hall 1"]["suitability"]["verdict"] == "suitable"
        assert results["Room 1"]["suitability"]["reasons"][0]["message"] == (
            "Capacity 60 is below the expected attendance of 100."
        )

    def test_a_space_that_is_not_on_the_named_event_is_not_found(self, client, auth_headers, authenticate_as, world):
        authenticate_as("event_coordinator", COORDINATOR_ID)

        response = search(client, auth_headers, event_id="e0000000-0000-4000-8000-0000000000bb", space_id=SPACE_ID)

        assert response.status_code == 404


class TestAccess:
    """AC10: only the event's assigned coordinator, acting as coordinator."""

    @pytest.mark.parametrize("params", [{"event_id": EVENT_ID}, {"space_id": SPACE_ID}])
    @pytest.mark.parametrize(
        "role", ["venue_staff", "event_coordinator_lead", "event_organiser", "attendee", "tech_support"]
    )
    def test_any_other_active_role_is_forbidden(self, client, auth_headers, authenticate_as, world, role, params):
        authenticate_as(role, COORDINATOR_ID)

        assert search(client, auth_headers, **params).status_code == 403

    @pytest.mark.parametrize("params", [{"event_id": EVENT_ID}, {"space_id": SPACE_ID}])
    def test_a_coordinator_who_is_not_assigned_is_forbidden(self, client, auth_headers, authenticate_as, world, params):
        authenticate_as("event_coordinator", OTHER_COORDINATOR_ID)

        assert search(client, auth_headers, **params).status_code == 403

    def test_an_unassigned_event_is_forbidden(self, client, auth_headers, authenticate_as, world):
        world["event"]["coordinator_id"] = None
        authenticate_as("event_coordinator", COORDINATOR_ID)

        assert search(client, auth_headers, event_id=EVENT_ID).status_code == 403

    def test_a_draft_is_not_found(self, client, auth_headers, authenticate_as, world):
        world["event"]["status"] = "draft"
        authenticate_as("event_coordinator", COORDINATOR_ID)

        assert search(client, auth_headers, event_id=EVENT_ID).status_code == 404

    def test_an_unknown_event_or_space_is_not_found(self, client, auth_headers, authenticate_as, world):
        authenticate_as("event_coordinator", COORDINATOR_ID)

        assert search(client, auth_headers, event_id="e0000000-0000-4000-8000-0000000000aa").status_code == 404
        assert search(client, auth_headers, space_id="f0000000-0000-4000-8000-0000000000aa").status_code == 404

    def test_a_plain_search_stays_open_to_venue_staff(self, client, auth_headers, authenticate_as, world):
        authenticate_as("venue_staff")

        assert search(client, auth_headers).status_code == 200

    def test_a_malformed_id_is_rejected(self, client, auth_headers, authenticate_as, world):
        authenticate_as("event_coordinator", COORDINATOR_ID)

        assert search(client, auth_headers, event_id="not-a-uuid").status_code == 422
