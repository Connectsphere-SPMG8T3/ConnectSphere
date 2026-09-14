"""HTTP contract of the venues module (SCRUM-39): role gate, validation, response shape.

The repository is patched, so the tests run offline; the rules themselves are
covered in test_venue_search.py.
"""

from datetime import datetime, time, timedelta, timezone

import pytest

from app.modules.venues import repository
from app.modules.venues.schemas import (
    AccessibilityFeature,
    BlockSummary,
    BookingSummary,
    Facility,
    LayoutOption,
    Occupant,
    Period,
    VenueLayout,
    VenueSummary,
)

SGT = timezone(timedelta(hours=8))
HALL_A_ID = "b0000000-0000-4000-8000-000000000001"
HALL_B_ID = "b0000000-0000-4000-8000-000000000002"
SEARCH_PERIOD = {"starts_at": "2026-10-10T14:00:00+08:00", "ends_at": "2026-10-10T17:00:00+08:00"}


def make_venue(venue_id: str, name: str, **overrides) -> VenueSummary:
    fields = {
        "id": venue_id,
        "name": name,
        "location": "Bukit Timah Campus",
        "capacity": 150,
        "layouts": [LayoutOption(layout=VenueLayout.theatre, capacity_for_layout=None)],
        "facilities": [Facility.projector],
        "accessibility_features": [AccessibilityFeature.wheelchair_access],
        "opens_at": time(8, 0),
        "closes_at": time(22, 0),
        "is_active": True,
        "description": None,
    }
    fields.update(overrides)
    return VenueSummary(**fields)


@pytest.fixture()
def catalogue(monkeypatch):
    """Two venues; Hall B is held 13:00–16:00 on 10 Oct by another event."""
    venues = [make_venue(HALL_A_ID, "Hall A"), make_venue(HALL_B_ID, "Hall B", capacity=100)]
    hold = Occupant(
        kind="booking",
        period=Period(starts_at=datetime(2026, 10, 10, 13, tzinfo=SGT), ends_at=datetime(2026, 10, 10, 16, tzinfo=SGT)),
        detail="held",
    )
    calls = {"list_occupants": []}

    def _list_occupants(period):
        calls["list_occupants"].append(period)
        return {HALL_B_ID: [hold]}

    monkeypatch.setattr(repository, "list_venues", lambda: venues)
    monkeypatch.setattr(repository, "list_occupants", _list_occupants)
    monkeypatch.setattr(repository, "get_venue", lambda venue_id: next((v for v in venues if v.id == str(venue_id)), None))
    monkeypatch.setattr(
        repository,
        "list_upcoming_blocks",
        lambda venue_id, since: [
            BlockSummary(id="c0000000-0000-4000-8000-000000000001", period=hold.period, reason="maintenance", notes=None)
        ],
    )
    monkeypatch.setattr(
        repository,
        "list_upcoming_bookings",
        lambda venue_id, since: [
            BookingSummary(
                id="d0000000-0000-4000-8000-000000000001",
                event_id="e0000000-0000-4000-8000-000000000101",
                period=hold.period,
                status="held",
            )
        ],
    )
    return calls


class TestSearchAccess:
    def test_coordinator_can_search(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("event_coordinator")
        response = client.get("/api/v1/venues", headers=auth_headers)
        assert response.status_code == 200

    def test_venue_staff_can_search(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("venue_staff")
        response = client.get("/api/v1/venues", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.parametrize("role", ["event_organiser", "attendee", "tech_support"])
    def test_other_roles_are_forbidden(self, client, auth_headers, authenticate_as, catalogue, role):
        authenticate_as(role)
        response = client.get("/api/v1/venues", headers=auth_headers)
        assert response.status_code == 403

    def test_without_token_is_unauthorised(self, client, catalogue):
        response = client.get("/api/v1/venues")
        assert response.status_code == 401


class TestSearchValidation:
    def test_end_before_or_equal_to_start_is_rejected(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("event_coordinator")
        response = client.get(
            "/api/v1/venues",
            params={"starts_at": "2026-10-10T17:00:00+08:00", "ends_at": "2026-10-10T14:00:00+08:00"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_a_lone_start_or_end_is_rejected(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("event_coordinator")
        response = client.get("/api/v1/venues", params={"starts_at": SEARCH_PERIOD["starts_at"]}, headers=auth_headers)
        assert response.status_code == 422

    def test_unknown_facility_is_rejected(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("event_coordinator")
        response = client.get("/api/v1/venues", params={"facilities": ["jacuzzi"]}, headers=auth_headers)
        assert response.status_code == 422

    def test_min_capacity_must_be_positive(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("event_coordinator")
        response = client.get("/api/v1/venues", params={"min_capacity": 0}, headers=auth_headers)
        assert response.status_code == 422


class TestSearchResults:
    def test_matching_venues_come_back_with_availability(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("event_coordinator")

        response = client.get("/api/v1/venues", params=SEARCH_PERIOD, headers=auth_headers)

        body = response.json()
        assert body["included_count"] == 1
        assert body["excluded_count"] == 1
        assert [r["venue"]["name"] for r in body["results"]] == ["Hall A"]
        assert body["results"][0]["availability"] == "available"
        assert body["results"][0]["venue"]["facilities"] == ["projector"]
        assert body["results"][0]["venue"]["layouts"] == [{"layout": "theatre", "capacity_for_layout": None}]
        assert body["results"][0]["venue"]["opens_at"] == "08:00:00"
        assert len(catalogue["list_occupants"]) == 1

    def test_show_excluded_reveals_reasons(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("event_coordinator")

        response = client.get(
            "/api/v1/venues", params={**SEARCH_PERIOD, "min_capacity": 120, "include_excluded": "true"}, headers=auth_headers
        )

        results = response.json()["results"]
        assert [(r["venue"]["name"], r["excluded"]) for r in results] == [("Hall A", False), ("Hall B", True)]
        hall_b = results[1]
        assert hall_b["availability"] == "unavailable"
        assert hall_b["reasons"] == [
            {"code": "capacity_below_minimum", "message": "Capacity 100 is below the required 120"},
            {"code": "held", "message": "Held by another event 10 Oct 13:00–16:00"},
        ]

    def test_without_a_period_availability_is_not_checked(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("event_coordinator")

        response = client.get("/api/v1/venues", headers=auth_headers)

        body = response.json()
        assert [r["availability"] for r in body["results"]] == ["not_checked", "not_checked"]
        assert catalogue["list_occupants"] == []

    def test_repeated_facility_params_are_all_applied(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("event_coordinator")

        response = client.get(
            "/api/v1/venues",
            params={"facilities": ["projector", "stage"], "include_excluded": "true"},
            headers=auth_headers,
        )

        results = response.json()["results"]
        assert all(r["excluded"] for r in results)
        assert results[0]["reasons"][0]["message"] == "Missing facilities: stage"

    def test_echoes_the_criteria_it_applied(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("event_coordinator")

        response = client.get("/api/v1/venues", params={**SEARCH_PERIOD, "layout": "theatre"}, headers=auth_headers)

        criteria = response.json()["criteria"]
        assert criteria["layout"] == "theatre"
        assert criteria["starts_at"] == "2026-10-10T14:00:00+08:00"


class TestVenueDetail:
    def test_detail_includes_upcoming_blocks_and_bookings(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("event_coordinator")

        response = client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Hall A"
        assert body["upcoming_blocks"][0]["reason"] == "maintenance"
        assert body["upcoming_blocks"][0]["period"]["starts_at"] == "2026-10-10T13:00:00+08:00"
        assert body["upcoming_bookings"][0]["status"] == "held"

    def test_unknown_venue_is_404(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("venue_staff")
        response = client.get("/api/v1/venues/b0000000-0000-4000-8000-0000000000ff", headers=auth_headers)
        assert response.status_code == 404

    def test_malformed_id_is_422(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("venue_staff")
        response = client.get("/api/v1/venues/not-a-uuid", headers=auth_headers)
        assert response.status_code == 422

    def test_organiser_cannot_read_detail(self, client, auth_headers, authenticate_as, catalogue):
        authenticate_as("event_organiser")
        response = client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers)
        assert response.status_code == 403
