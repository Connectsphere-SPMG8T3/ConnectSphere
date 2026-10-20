"""SCRUM-18 BR-R3: a booking request is checked for suitability on the server.

An Unsuitable venue is refused and a venue with warnings needs the
coordinator's acknowledgement (`acknowledge_warnings`). Capacity and an
inactive venue are the database function's own refusals (CR-97 AC10, SCRUM-64),
with their own wording, so the check leaves those two to it. The rules are in
test_venue_suitability.py; the repositories are mocked here.
"""

from copy import deepcopy

import pytest

from app.modules.events import repository as events_repository
from app.modules.venues import repository as venues_repository
from app.modules.venues.schemas import AccessibilityFeature, Facility, LayoutOption, VenueLayout
from tests.test_venue_booking_request_api import (
    BOOKING_ID,
    COORDINATOR_ID,
    EVENT_ID,
    SPACE_ID,
    VENUE_ID,
    event_row,
)
from tests.test_venues_api import make_venue_profile

URL = "/api/v1/venue-bookings"
SGT_START = "2031-10-10T10:00:00+08:00"
SGT_END = "2031-10-10T13:00:00+08:00"


def stored_event(**overrides):
    row = event_row()
    row.update(
        starts_at=SGT_START, ends_at=SGT_END, expected_attendance=40, layout_preference="theatre",
        facilities_required=["projector"], accessibility_needs=None, spaces=[],
    )
    row.update(overrides)
    return row


SPACE = {
    "id": SPACE_ID, "event_id": EVENT_ID, "label": "Breakout", "expected_pax": 20, "layout_preference": None,
    "facilities_required": [], "starts_at": None, "ends_at": None, "is_primary": False, "version": 0,
}


@pytest.fixture()
def world(monkeypatch):
    """One planning event for COORDINATOR_ID and a venue that suits it; every
    call that would write a hold is recorded in `calls`."""
    state = {
        "event": stored_event(), "venue": make_venue_profile(VENUE_ID, "Hall A"), "calls": [],
        "outcome": "ok", "statuses": [],
    }

    def hold(*args, **kwargs):
        state["calls"].append(args)
        return {"outcome": state["outcome"], "booking_id": BOOKING_ID if state["outcome"] == "ok" else None}

    monkeypatch.setattr(events_repository, "get_event", lambda event_id: deepcopy(state["event"]))
    monkeypatch.setattr(
        events_repository, "get_space",
        lambda space_id: next((deepcopy(s) for s in state["event"]["spaces"] if s["id"] == space_id), None),
    )
    monkeypatch.setattr(venues_repository, "get_venue", lambda venue_id: state["venue"])
    monkeypatch.setattr(venues_repository, "request_booking", hold)
    monkeypatch.setattr(venues_repository, "request_booking_for_space", hold)
    monkeypatch.setattr(venues_repository, "list_booking_statuses", lambda event_ids: deepcopy(state["statuses"]))
    return state


@pytest.fixture(autouse=True)
def as_coordinator(authenticate_as):
    authenticate_as("event_coordinator", COORDINATOR_ID)


def request(client, auth_headers, **body):
    return client.post(URL, json={"event_id": EVENT_ID, "venue_id": VENUE_ID, **body}, headers=auth_headers)


class TestUnsuitable:
    def test_a_missing_facility_refuses_the_request_and_names_it(self, client, auth_headers, world):
        world["venue"] = make_venue_profile(VENUE_ID, "Hall A", facilities=[Facility.microphone])

        response = request(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "This venue is unsuitable for this event: Missing facilities this event needs: projector."
        )
        assert world["calls"] == []

    def test_every_hard_failure_is_listed(self, client, auth_headers, world):
        world["event"] = stored_event(expected_attendance=500)
        world["venue"] = make_venue_profile(VENUE_ID, "Hall A", facilities=[])

        detail = request(client, auth_headers).json()["detail"]

        assert "Missing facilities this event needs: projector." in detail
        assert world["calls"] == []

    def test_capacity_is_left_to_the_database_functions_own_refusal(self, client, auth_headers, world):
        world["event"] = stored_event(expected_attendance=500)

        response = request(client, auth_headers)

        assert response.status_code == 201
        assert len(world["calls"]) == 1

    def test_an_inactive_venue_is_left_to_the_database_functions_own_refusal(self, client, auth_headers, world):
        world["venue"] = make_venue_profile(
            VENUE_ID, "Hall A", is_active=False, inactive_reason="permanently_closed"
        )

        assert request(client, auth_headers).status_code == 201
        assert len(world["calls"]) == 1

    def test_an_unknown_venue_is_not_found(self, client, auth_headers, world):
        world["venue"] = None

        response = request(client, auth_headers)

        assert response.status_code == 404
        assert world["calls"] == []


class TestWarnings:
    @pytest.fixture(autouse=True)
    def a_layout_the_venue_lacks(self, world):
        world["event"] = stored_event(layout_preference="banquet")

    def test_a_venue_with_warnings_needs_the_coordinators_acknowledgement(self, client, auth_headers, world):
        response = request(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "This venue is suitable with warnings: The banquet layout this event needs is not supported. "
            "Acknowledge the warnings to request it."
        )
        assert world["calls"] == []

    def test_acknowledging_the_warnings_lets_the_request_through(self, client, auth_headers, world):
        response = request(client, auth_headers, acknowledge_warnings=True)

        assert response.status_code == 201
        assert len(world["calls"]) == 1

    def test_acknowledging_does_not_excuse_a_hard_failure(self, client, auth_headers, world):
        world["venue"] = make_venue_profile(VENUE_ID, "Hall A", facilities=[])

        response = request(client, auth_headers, acknowledge_warnings=True)

        assert response.status_code == 409
        assert response.json()["detail"].startswith("This venue is unsuitable for this event:")
        assert world["calls"] == []

    def test_every_warning_is_listed(self, client, auth_headers, world):
        world["event"] = stored_event(layout_preference="banquet", accessibility_needs="a hearing loop")

        detail = request(client, auth_headers).json()["detail"]

        assert "The banquet layout this event needs is not supported." in detail
        assert "Missing accessibility features this event needs: hearing loop." in detail

    def test_the_acknowledgement_must_be_a_boolean(self, client, auth_headers, world):
        assert request(client, auth_headers, acknowledge_warnings="yes please").status_code == 422


class TestSuitable:
    def test_a_suitable_venue_needs_no_acknowledgement(self, client, auth_headers, world):
        response = request(client, auth_headers)

        assert response.status_code == 201
        assert len(world["calls"]) == 1

    def test_the_acknowledgement_defaults_to_off(self, client, auth_headers, world):
        world["event"] = stored_event(layout_preference="banquet")

        assert request(client, auth_headers, acknowledge_warnings=False).status_code == 409


class TestPerSpace:
    """AC11: the check is made against the space the request is for."""

    @pytest.fixture(autouse=True)
    def an_event_with_a_space(self, world):
        space = {**SPACE, "facilities_required": ["whiteboard"]}
        world["event"] = stored_event(expected_attendance=500, spaces=[space])

    def test_a_space_request_is_judged_on_the_spaces_own_facilities(self, client, auth_headers, world):
        response = client.post(
            URL, json={"event_space_request_id": SPACE_ID, "venue_id": VENUE_ID}, headers=auth_headers
        )

        assert response.status_code == 409
        assert "Missing facilities this event needs: whiteboard." in response.json()["detail"]
        assert world["calls"] == []

    def test_a_space_the_venue_suits_goes_through_even_though_the_event_is_bigger(
        self, client, auth_headers, world
    ):
        world["venue"] = make_venue_profile(
            VENUE_ID, "Hall A", capacity=60, facilities=[Facility.whiteboard],
            layouts=[LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=None)],
            accessibility_features=[AccessibilityFeature.wheelchair_access],
        )

        response = client.post(
            URL, json={"event_space_request_id": SPACE_ID, "venue_id": VENUE_ID}, headers=auth_headers
        )

        assert response.status_code == 201
        assert len(world["calls"]) == 1

    def test_an_event_only_request_is_judged_on_the_first_space(self, client, auth_headers, world):
        response = request(client, auth_headers)

        assert response.status_code == 409
        assert "Missing facilities this event needs: whiteboard." in response.json()["detail"]


class TestTheDatabasesRefusalsComeFirst:
    """TC-BOOK-004, TC-BOOK-005: when the database function would refuse the
    request anyway, its own wording stands; the suitability check only decides
    a request that would otherwise go through."""

    @pytest.fixture(autouse=True)
    def an_unsuitable_venue(self, world):
        world["venue"] = make_venue_profile(VENUE_ID, "Hall A", facilities=[])

    @pytest.mark.parametrize("status", ["under_review", "returned", "rejected"])
    def test_an_event_outside_planning_is_refused_for_its_status(self, client, auth_headers, world, status):
        world["event"] = stored_event(status=status)
        world["outcome"] = "not_planning" if status != "returned" else "returned"

        response = request(client, auth_headers)

        assert response.status_code == 409
        assert "unsuitable" not in response.json()["detail"]
        assert len(world["calls"]) == 1

    @pytest.mark.parametrize("held", ["held", "approved", "re_review"])
    def test_an_event_that_already_holds_a_venue_is_refused_for_that(self, client, auth_headers, world, held):
        world["statuses"] = [{"event_id": EVENT_ID, "event_space_request_id": None, "status": held, "flag": None}]
        world["outcome"] = "already_booked"

        response = request(client, auth_headers)

        assert response.json()["detail"] == "This event already has a venue booking."
        assert len(world["calls"]) == 1

    def test_a_released_booking_does_not_hide_an_unsuitable_venue(self, client, auth_headers, world):
        world["statuses"] = [{"event_id": EVENT_ID, "event_space_request_id": None, "status": "released", "flag": None}]

        response = request(client, auth_headers)

        assert response.json()["detail"].startswith("This venue is unsuitable for this event:")
        assert world["calls"] == []

    def test_another_spaces_booking_does_not_hide_an_unsuitable_venue(self, client, auth_headers, world):
        world["event"] = stored_event(spaces=[{**SPACE, "facilities_required": ["whiteboard"]}])
        world["statuses"] = [
            {"event_id": EVENT_ID, "event_space_request_id": "f0000000-0000-4000-8000-0000000000ff",
             "status": "held", "flag": None}
        ]

        response = client.post(
            URL, json={"event_space_request_id": SPACE_ID, "venue_id": VENUE_ID}, headers=auth_headers
        )

        assert response.json()["detail"].startswith("This venue is unsuitable for this event:")
        assert world["calls"] == []
