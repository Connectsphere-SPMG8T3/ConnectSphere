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
    VenueStaffBlock,
    VenueStaffBooking,
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


VENUE_STAFF_DASHBOARD = "/api/v1/venues/dashboard/venue-staff"


def make_staff_booking(booking_id: str, status: str, requested_at: datetime, **overrides) -> VenueStaffBooking:
    fields = {
        "id": booking_id,
        "event_id": "e0000000-0000-4000-8000-000000000101",
        "venue_id": HALL_A_ID,
        "venue_name": "Hall A",
        "period": Period(
            starts_at=datetime(2026, 10, 10, 9, tzinfo=SGT),
            ends_at=datetime(2026, 10, 10, 12, tzinfo=SGT),
        ),
        "status": status,
        "requested_at": requested_at,
    }
    fields.update(overrides)
    return VenueStaffBooking(**fields)


@pytest.fixture()
def staff_queue(monkeypatch):
    """Two holds and one re-review across two venues, plus one block.

    The holds are returned newest-first on purpose: the oldest-first ordering
    the dashboard promises (BR-R4) has to be the service's doing, not an
    accident of whatever order the repository happened to hand back.
    """
    venues = [make_venue(HALL_A_ID, "Hall A"), make_venue(HALL_B_ID, "Hall B", is_active=False)]
    newer_hold = make_staff_booking(
        "d0000000-0000-4000-8000-000000000002", "held", datetime(2026, 9, 3, 10, 30, tzinfo=SGT)
    )
    older_hold = make_staff_booking(
        "d0000000-0000-4000-8000-000000000004",
        "held",
        datetime(2026, 8, 28, 16, 15, tzinfo=SGT),
        venue_id=HALL_B_ID,
        venue_name="Hall B",
    )
    re_review = make_staff_booking(
        "d0000000-0000-4000-8000-000000000005", "re_review", datetime(2026, 9, 10, 11, 45, tzinfo=SGT)
    )
    block = VenueStaffBlock(
        id="c0000000-0000-4000-8000-000000000001",
        venue_id=HALL_A_ID,
        venue_name="Hall A",
        period=Period(
            starts_at=datetime(2026, 10, 20, tzinfo=SGT),
            ends_at=datetime(2026, 10, 22, tzinfo=SGT),
        ),
        reason="safety",
        notes="Railing inspection.",
    )
    calls = {"bookings": [], "blocks": []}

    def _bookings(since, statuses):
        calls["bookings"].append((since, set(statuses)))
        return [newer_hold, older_hold, re_review]

    def _blocks(since):
        calls["blocks"].append(since)
        return [block]

    monkeypatch.setattr(repository, "list_venues", lambda: venues)
    monkeypatch.setattr(repository, "list_all_upcoming_bookings", _bookings)
    monkeypatch.setattr(repository, "list_all_upcoming_blocks", _blocks)
    return calls


class TestVenueStaffDashboardAccess:
    def test_venue_staff_can_read_it(self, client, auth_headers, authenticate_as, staff_queue):
        authenticate_as("venue_staff")
        response = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers)
        assert response.status_code == 200

    def test_coordinator_is_forbidden(self, client, auth_headers, authenticate_as, staff_queue):
        """A coordinator may search the catalogue but this is a staff work queue.

        Worth its own test rather than a parametrised case: the coordinator is
        the one denied role that *can* reach every other venues endpoint, so a
        guard copy-pasted from `VenueReader` would pass every other check here.
        """
        authenticate_as("event_coordinator")
        response = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers)
        assert response.status_code == 403

    @pytest.mark.parametrize("role", ["event_organiser", "tech_support", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, authenticate_as, staff_queue, role):
        authenticate_as(role)
        response = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers)
        assert response.status_code == 403

    def test_without_token_is_unauthorised(self, client, staff_queue):
        assert client.get(VENUE_STAFF_DASHBOARD).status_code == 401

    def test_the_path_is_not_captured_by_the_venue_detail_route(self, client, auth_headers, authenticate_as, staff_queue):
        """`/venues/{venue_id}` is typed UUID and would answer 422, not fall through."""
        authenticate_as("venue_staff")
        response = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers)
        assert response.status_code != 422


class TestVenueStaffDashboardPayload:
    def test_it_returns_the_four_lists(self, client, auth_headers, authenticate_as, staff_queue):
        authenticate_as("venue_staff")

        body = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers).json()

        assert set(body) == {"generated_at", "venues", "pending_holds", "re_review_bookings", "blocks"}
        assert [v["name"] for v in body["venues"]] == ["Hall A", "Hall B"]
        assert len(body["pending_holds"]) == 2
        assert len(body["re_review_bookings"]) == 1
        assert body["blocks"][0]["reason"] == "safety"

    def test_pending_holds_are_oldest_first(self, client, auth_headers, authenticate_as, staff_queue):
        authenticate_as("venue_staff")

        body = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers).json()

        assert [h["requested_at"] for h in body["pending_holds"]] == [
            "2026-08-28T16:15:00+08:00",
            "2026-09-03T10:30:00+08:00",
        ]

    def test_only_held_and_re_review_are_requested(self, client, auth_headers, authenticate_as, staff_queue):
        """An approved booking is settled work and belongs on §6.9's calendar."""
        authenticate_as("venue_staff")

        client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers)

        _, statuses = staff_queue["bookings"][0]
        assert statuses == {"held", "re_review"}

    def test_holds_and_re_reviews_do_not_bleed_into_each_other(self, client, auth_headers, authenticate_as, staff_queue):
        authenticate_as("venue_staff")

        body = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers).json()

        assert {h["status"] for h in body["pending_holds"]} == {"held"}
        assert {b["status"] for b in body["re_review_bookings"]} == {"re_review"}

    def test_each_row_names_its_venue(self, client, auth_headers, authenticate_as, staff_queue):
        """The queue spans every venue, so a row without its venue is unusable."""
        authenticate_as("venue_staff")

        body = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers).json()

        assert {h["venue_name"] for h in body["pending_holds"]} == {"Hall A", "Hall B"}
        assert body["blocks"][0]["venue_name"] == "Hall A"

    def test_event_name_is_null_until_the_events_table_lands(self, client, auth_headers, authenticate_as, staff_queue):
        authenticate_as("venue_staff")

        body = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers).json()

        assert all(h["event_name"] is None for h in body["pending_holds"])
        assert all("event_id" in h for h in body["pending_holds"])

    def test_inactive_venues_are_included(self, client, auth_headers, authenticate_as, staff_queue):
        """AC2 asks for each venue's status at a glance, so an inactive one must appear."""
        authenticate_as("venue_staff")

        body = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers).json()

        assert [v["is_active"] for v in body["venues"]] == [True, False]

    def test_both_repository_reads_share_one_cut_off(self, client, auth_headers, authenticate_as, staff_queue):
        authenticate_as("venue_staff")

        client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers)

        (booking_since, _), block_since = staff_queue["bookings"][0], staff_queue["blocks"][0]
        assert booking_since == block_since

    def test_an_empty_queue_is_200_not_404(self, client, auth_headers, authenticate_as, monkeypatch):
        """Nothing to decide is a valid answer, and must not read as an outage."""
        authenticate_as("venue_staff")
        monkeypatch.setattr(repository, "list_venues", list)
        monkeypatch.setattr(repository, "list_all_upcoming_bookings", lambda since, statuses: [])
        monkeypatch.setattr(repository, "list_all_upcoming_blocks", lambda since: [])

        response = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["venues"] == body["pending_holds"] == body["re_review_bookings"] == body["blocks"] == []
