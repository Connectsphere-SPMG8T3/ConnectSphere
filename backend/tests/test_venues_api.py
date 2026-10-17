"""HTTP contract of the venues module (SCRUM-39): role gate, validation, response shape.

The repository is patched, so the tests run offline; the rules themselves are
covered in test_venue_search.py.
"""

from datetime import datetime, time, timedelta, timezone

import pytest

from app.core.exceptions import EventServiceUnavailableError
from app.modules.events import repository as events_repository
from app.modules.events import service as events_service
from app.modules.venues import repository
from app.modules.venues.schemas import (
    AccessibilityFeature,
    BlockSummary,
    BookingSummary,
    Editor,
    Facility,
    LayoutOption,
    Occupant,
    Period,
    VenueLayout,
    VenueProfile,
    VenueStaffBlock,
    VenueStaffBooking,
    VenueSummary,
)

VALID_EDIT_PAYLOAD = {
    "name": "Hall A",
    "location": "Bukit Timah Campus",
    "capacity": 150,
    "layouts": [{"layout": "theatre", "capacity_for_layout": None}],
    "facilities": ["projector"],
    "accessibility_features": ["wheelchair_access"],
    "opens_at": "08:00:00",
    "closes_at": "22:00:00",
    "description": None,
}

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


VENUE_STAFF_ID = "a0000000-0000-4000-8000-000000000003"
SEED_EVENT_ID = "e0000000-0000-4000-8000-000000000101"


def make_venue_profile(venue_id: str, name: str, **overrides) -> VenueProfile:
    """A venue as its own profile page reads it: catalogue fields plus the
    audit stamp SCRUM-67 shows and the version SCRUM-63 edits against.

    `overrides` may name either a base catalogue field (e.g. `capacity`) or a
    profile-only field (`updated_at`, `updated_by`, `version`) — each goes to
    whichever `VenueProfile(...)` call it belongs to, so a test never has to
    care which layer a field lives on.
    """
    base = make_venue(venue_id, name).model_dump()
    fields = {
        "updated_at": datetime(2026, 9, 18, 10, 30, tzinfo=SGT),
        "updated_by": Editor(id=VENUE_STAFF_ID, full_name="Val Staff"),
        "version": 0,
    }
    for key, value in overrides.items():
        (base if key in base else fields)[key] = value
    return VenueProfile(**base, **fields)


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
    profiles = {v.id: make_venue_profile(v.id, v.name, **({} if v.id == HALL_A_ID else {"updated_by": None})) for v in venues}
    monkeypatch.setattr(repository, "get_venue", lambda venue_id: profiles.get(str(venue_id)))
    monkeypatch.setattr(
        events_repository,
        "list_event_names",
        lambda event_ids: {SEED_EVENT_ID: "Seed Auditorium Event"} if SEED_EVENT_ID in event_ids else {},
    )
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
        [period] = catalogue["list_occupants"]
        assert period.starts_at == datetime(2026, 10, 10, 14, tzinfo=SGT)

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

    def test_bookings_and_blocks_are_read_for_this_venue_from_now(
        self, client, auth_headers, authenticate_as, catalogue, monkeypatch
    ):
        reads = []
        monkeypatch.setattr(repository, "list_upcoming_bookings", lambda venue_id, since: reads.append((venue_id, since)) or [])
        monkeypatch.setattr(repository, "list_upcoming_blocks", lambda venue_id, since: reads.append((venue_id, since)) or [])
        authenticate_as("venue_staff")

        client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers)

        assert [venue_id for venue_id, _ in reads] == [HALL_A_ID, HALL_A_ID]
        assert all(abs(since - datetime.now(timezone.utc)) < timedelta(minutes=1) for _, since in reads)

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


class TestVenueProfile:
    """SCRUM-67 — the venue profile venue staff read before planning around a venue.

    AC1 (the attributes themselves) is exercised by `TestVenueDetail` and the
    search tests; what follows covers what SCRUM-67 adds on top: the audit
    stamp, the turnaround figure, and the upcoming-bookings summary.
    """

    @pytest.fixture()
    def occupied(self, monkeypatch, catalogue):
        """Hall A with one booking per occupying status (§6.14)."""

        def _period(hour: int) -> Period:
            return Period(
                starts_at=datetime(2026, 10, 10, hour, tzinfo=SGT),
                ends_at=datetime(2026, 10, 10, hour + 2, tzinfo=SGT),
            )

        bookings = [
            BookingSummary(id="d1", event_id=SEED_EVENT_ID, period=_period(9), status="approved"),
            BookingSummary(id="d2", event_id="e0000000-0000-4000-8000-000000000102", period=_period(13), status="held"),
            BookingSummary(id="d3", event_id="e0000000-0000-4000-8000-000000000103", period=_period(17), status="re_review"),
        ]
        monkeypatch.setattr(repository, "list_upcoming_bookings", lambda venue_id, since: bookings)
        return bookings

    def test_every_attribute_arrives_in_one_response(self, client, auth_headers, authenticate_as, catalogue):
        """AC1: one request answers location, capacity, facilities, accessibility,
        layouts and operating hours — no second call to assemble the profile."""
        authenticate_as("venue_staff")

        body = client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers).json()

        assert body["location"] == "Bukit Timah Campus"
        assert body["capacity"] == 150
        assert body["facilities"] == ["projector"]
        assert body["accessibility_features"] == ["wheelchair_access"]
        assert body["layouts"] == [{"layout": "theatre", "capacity_for_layout": None}]
        assert (body["opens_at"], body["closes_at"]) == ("08:00:00", "22:00:00")

    def test_it_reports_when_the_profile_was_last_updated_and_by_whom(
        self, client, auth_headers, authenticate_as, catalogue
    ):
        """AC2."""
        authenticate_as("venue_staff")

        body = client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers).json()

        assert body["updated_at"] == "2026-09-18T10:30:00+08:00"
        assert body["updated_by"] == {"id": VENUE_STAFF_ID, "full_name": "Val Staff"}

    def test_an_unattributed_edit_reports_no_editor_rather_than_guessing(
        self, client, auth_headers, authenticate_as, catalogue
    ):
        """AC2 boundary: `venues.updated_by` is null for every edit made before
        the column existed, and for an editor whose account has been removed."""
        authenticate_as("venue_staff")

        body = client.get(f"/api/v1/venues/{HALL_B_ID}", headers=auth_headers).json()

        assert body["updated_at"] is not None
        assert body["updated_by"] is None

    def test_turnaround_is_reported_as_zero(self, client, auth_headers, authenticate_as, catalogue):
        """AC1: the profile states the setup/turnaround time. The customer set it
        to zero (QA-28), so the SPA reads the figure off the contract instead of
        hard-coding a business rule."""
        authenticate_as("venue_staff")

        body = client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers).json()

        assert body["turnaround_minutes"] == 0

    def test_confirmed_tentative_and_re_review_bookings_are_all_listed(
        self, client, auth_headers, authenticate_as, occupied
    ):
        """AC3: every booking that occupies the venue is on the profile, soonest
        first, each carrying the status the SPA groups on."""
        authenticate_as("venue_staff")

        body = client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers).json()

        assert [b["status"] for b in body["upcoming_bookings"]] == ["approved", "held", "re_review"]

    def test_upcoming_bookings_name_their_event(self, client, auth_headers, authenticate_as, occupied):
        """AC3: "plan around it" needs to say which event holds the slot, so the
        venue module resolves the names through the events module's service."""
        authenticate_as("venue_staff")

        body = client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers).json()

        assert body["upcoming_bookings"][0]["event_name"] == "Seed Auditorium Event"

    def test_a_booking_whose_event_row_is_missing_keeps_a_null_name(
        self, client, auth_headers, authenticate_as, occupied
    ):
        authenticate_as("venue_staff")

        body = client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers).json()

        assert [b["event_name"] for b in body["upcoming_bookings"][1:]] == [None, None]

    def test_a_free_venue_asks_the_events_module_for_nothing(
        self, client, auth_headers, authenticate_as, catalogue, monkeypatch
    ):
        """No bookings means no event ids, and so no second round trip."""
        authenticate_as("venue_staff")
        calls = []
        monkeypatch.setattr(repository, "list_upcoming_bookings", lambda venue_id, since: [])
        monkeypatch.setattr(events_repository, "list_event_names", lambda ids: calls.append(list(ids)) or {})

        body = client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers).json()

        assert body["upcoming_bookings"] == []
        assert calls == []

    def test_the_profile_declares_a_photos_field_that_is_empty(self, client, auth_headers, authenticate_as, catalogue):
        """The profile page leads with a photo carousel, so `photos` is part of
        the contract from the start. Nothing populates it yet — there is no
        `venue_photos` table and no storage bucket — so it is always `[]` and
        the SPA shows an empty state rather than stock imagery."""
        authenticate_as("venue_staff")

        body = client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers).json()

        assert body["photos"] == []

    def test_a_coordinator_reads_the_same_profile(self, client, auth_headers, authenticate_as, catalogue):
        """SCRUM-67 is a venue-staff story, but the endpoint is the catalogue
        read that coordinators already hold (§2); it is not narrowed here."""
        authenticate_as("event_coordinator")

        response = client.get(f"/api/v1/venues/{HALL_A_ID}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["updated_by"]["full_name"] == "Val Staff"

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

    The hold that expires later is returned first on purpose: the
    soonest-expiry ordering the dashboard promises (CR-99) has to be the
    service's doing, not an accident of the repository's order. The newer
    request expires sooner, so ordering by age would get it wrong.
    """
    venues = [make_venue(HALL_A_ID, "Hall A"), make_venue(HALL_B_ID, "Hall B", is_active=False)]
    newer_hold = make_staff_booking(
        "d0000000-0000-4000-8000-000000000002", "held", datetime(2026, 9, 3, 10, 30, tzinfo=SGT),
        expires_at=datetime(2031, 1, 1, 9, tzinfo=SGT),
    )
    older_hold = make_staff_booking(
        "d0000000-0000-4000-8000-000000000004",
        "held",
        datetime(2026, 8, 28, 16, 15, tzinfo=SGT),
        expires_at=datetime(2031, 2, 1, 9, tzinfo=SGT),
        venue_id=HALL_B_ID,
        venue_name="Hall B",
    )
    re_review = make_staff_booking(
        "d0000000-0000-4000-8000-000000000005", "re_review", datetime(2026, 9, 10, 11, 45, tzinfo=SGT)
    )
    approved = make_staff_booking(
        "d0000000-0000-4000-8000-000000000006", "approved", datetime(2026, 9, 11, 11, 45, tzinfo=SGT)
    )
    rejected = make_staff_booking(
        "d0000000-0000-4000-8000-000000000007", "rejected", datetime(2026, 9, 12, 11, 45, tzinfo=SGT)
    )
    expired = make_staff_booking(
        "d0000000-0000-4000-8000-000000000008", "expired", datetime(2026, 9, 13, 11, 45, tzinfo=SGT)
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
        return [older_hold, newer_hold, re_review, approved, rejected, expired]

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
    def test_it_returns_the_dashboard_lists(self, client, auth_headers, authenticate_as, staff_queue):
        authenticate_as("venue_staff")

        body = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers).json()

        assert set(body) == {"generated_at", "venues", "booking_requests", "pending_holds", "re_review_bookings", "blocks"}
        assert [v["name"] for v in body["venues"]] == ["Hall A", "Hall B"]
        assert len(body["pending_holds"]) == 2
        assert len(body["re_review_bookings"]) == 1
        assert body["blocks"][0]["reason"] == "safety"

    def test_pending_holds_are_soonest_expiry_first(self, client, auth_headers, authenticate_as, staff_queue):
        authenticate_as("venue_staff")

        body = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers).json()

        assert [h["expires_at"] for h in body["pending_holds"]] == [
            "2031-01-01T09:00:00+08:00",
            "2031-02-01T09:00:00+08:00",
        ]

    def test_a_hold_without_an_expiry_is_ordered_by_its_start(
        self, client, auth_headers, authenticate_as, staff_queue, monkeypatch
    ):
        no_expiry = make_staff_booking(
            "d0000000-0000-4000-8000-000000000009", "held", datetime(2026, 9, 1, tzinfo=SGT),
            period=Period(starts_at=datetime(2030, 6, 1, 9, tzinfo=SGT), ends_at=datetime(2030, 6, 1, 12, tzinfo=SGT)),
        )
        others = repository.list_all_upcoming_bookings(None, set())
        monkeypatch.setattr(repository, "list_all_upcoming_bookings", lambda since, statuses: [*others, no_expiry])
        authenticate_as("venue_staff")

        body = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers).json()

        assert [h["id"] for h in body["pending_holds"]] == [
            "d0000000-0000-4000-8000-000000000009",
            "d0000000-0000-4000-8000-000000000002",
            "d0000000-0000-4000-8000-000000000004",
        ]

    def test_all_dashboard_statuses_are_requested(self, client, auth_headers, authenticate_as, staff_queue):
        authenticate_as("venue_staff")

        client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers)

        _, statuses = staff_queue["bookings"][0]
        assert statuses == {"held", "re_review", "approved", "rejected", "expired"}

    def test_holds_and_re_reviews_do_not_bleed_into_each_other(self, client, auth_headers, authenticate_as, staff_queue):
        authenticate_as("venue_staff")

        body = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers).json()

        assert {h["status"] for h in body["pending_holds"]} == {"held"}
        assert {b["status"] for b in body["re_review_bookings"]} == {"re_review"}

    def test_request_list_includes_pending_and_resolved_statuses(self, client, auth_headers, authenticate_as, staff_queue):
        authenticate_as("venue_staff")

        body = client.get(VENUE_STAFF_DASHBOARD, headers=auth_headers).json()

        assert {request["status"] for request in body["booking_requests"]} == {
            "held",
            "re_review",
            "approved",
            "rejected",
            "expired",
        }

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


COORDINATOR_ID = "a0000000-0000-4000-8000-000000000099"
EVENT_ID = "e0000000-0000-4000-8000-000000000201"


class TestVenueEdit:
    """SCRUM-63: edit a venue's details, with a VC-R2 warning before saving
    anything that would newly affect an upcoming booking, and a VC-R3 history
    row once the edit is saved."""

    @pytest.fixture()
    def profile(self, monkeypatch):
        current = make_venue_profile(HALL_A_ID, "Hall A", version=3)
        monkeypatch.setattr(repository, "get_venue", lambda venue_id: current if venue_id == HALL_A_ID else None)
        monkeypatch.setattr(repository, "list_upcoming_bookings", lambda venue_id, since: [])
        monkeypatch.setattr(repository, "list_upcoming_blocks", lambda venue_id, since: [])
        monkeypatch.setattr(events_repository, "list_planning_context", lambda ids: [])
        monkeypatch.setattr(repository, "list_venue_staff_ids", lambda: set())
        # `flagged_event_ids` is what the RPC reports it flagged (CR-94).
        calls = {"update_venue": [], "flagged_event_ids": []}

        def _update_venue(venue_id, actor_id, expected_version, **kwargs):
            calls["update_venue"].append({"venue_id": venue_id, "actor_id": actor_id, "version": expected_version, **kwargs})
            saved = make_venue_profile(
                venue_id,
                kwargs["name"],
                version=expected_version + 1,
                capacity=kwargs["capacity"],
                updated_by=Editor(id=actor_id),
            )
            return saved, calls["flagged_event_ids"]

        monkeypatch.setattr(repository, "update_venue", _update_venue)
        return calls

    def test_venue_staff_can_save_an_edit_with_no_affected_bookings(self, client, auth_headers, authenticate_as, profile):
        actor = authenticate_as("venue_staff")

        response = client.patch(f"/api/v1/venues/{HALL_A_ID}", json=VALID_EDIT_PAYLOAD, headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["saved"] is True
        assert body["warnings"] == []
        assert body["venue"]["capacity"] == 150
        assert len(profile["update_venue"]) == 1
        assert profile["update_venue"][0]["actor_id"] == actor["id"]
        assert profile["update_venue"][0]["version"] == 3

    def test_every_submitted_field_is_saved_with_a_before_and_after_snapshot(
        self, client, auth_headers, authenticate_as, profile, monkeypatch
    ):
        """VC-R3: the history row records each editable field before and after."""
        current = make_venue_profile(HALL_A_ID, "Hall A", version=3, description="Main hall.")
        monkeypatch.setattr(repository, "get_venue", lambda venue_id: current)
        authenticate_as("venue_staff")
        edit = {
            "name": "Hall A2",
            "location": "City Campus",
            "capacity": 90,
            "layouts": [{"layout": "boardroom", "capacity_for_layout": 20}],
            "facilities": ["stage"],
            "accessibility_features": ["hearing_loop"],
            "opens_at": "09:30:00",
            "closes_at": "21:00:00",
            "description": "Renovated in 2026.",
        }

        client.patch(f"/api/v1/venues/{HALL_A_ID}", json=edit, headers=auth_headers)

        call = profile["update_venue"][0]
        assert {k: call[k] for k in ("name", "location", "capacity", "description")} == {
            "name": "Hall A2", "location": "City Campus", "capacity": 90, "description": "Renovated in 2026.",
        }
        assert (call["opens_at"], call["closes_at"]) == (time(9, 30), time(21, 0))
        assert call["layouts"] == edit["layouts"]
        assert call["facilities"] == ["stage"]
        assert call["accessibility_features"] == ["hearing_loop"]
        assert call["after"] == {**edit, "is_active": True, "inactive_reason": None, "inactive_note": None}
        assert call["before"] == {
            "name": "Hall A",
            "location": "Bukit Timah Campus",
            "capacity": 150,
            "layouts": [{"layout": "theatre", "capacity_for_layout": None}],
            "facilities": ["projector"],
            "accessibility_features": ["wheelchair_access"],
            "opens_at": "08:00:00",
            "closes_at": "22:00:00",
            "description": "Main hall.",
            "is_active": True,
            "inactive_reason": None,
            "inactive_note": None,
        }

    def test_bookings_and_blocks_are_read_for_this_venue_from_now(
        self, client, auth_headers, authenticate_as, profile, monkeypatch
    ):
        reads = []
        monkeypatch.setattr(repository, "list_upcoming_bookings", lambda venue_id, since: reads.append((venue_id, since)) or [])
        monkeypatch.setattr(repository, "list_upcoming_blocks", lambda venue_id, since: reads.append((venue_id, since)) or [])
        authenticate_as("venue_staff")

        client.patch(f"/api/v1/venues/{HALL_A_ID}", json=VALID_EDIT_PAYLOAD, headers=auth_headers)

        assert [venue_id for venue_id, _ in reads] == [HALL_A_ID, HALL_A_ID]
        assert all(abs(since - datetime.now(timezone.utc)) < timedelta(minutes=1) for _, since in reads)

    def test_editing_an_inactive_venue_keeps_its_reason_in_the_history_snapshots(
        self, client, auth_headers, authenticate_as, profile, monkeypatch
    ):
        # SCRUM-64: the snapshot records the inactive fields, so they must be the venue's real ones.
        inactive = make_venue_profile(HALL_A_ID, "Hall A", version=3, is_active=False,
                                      inactive_reason="permanently_closed", inactive_note="Lease ended")
        monkeypatch.setattr(repository, "get_venue", lambda venue_id: inactive)
        authenticate_as("venue_staff")

        client.patch(f"/api/v1/venues/{HALL_A_ID}", json=VALID_EDIT_PAYLOAD, headers=auth_headers)

        [call] = profile["update_venue"]
        for side in (call["before"], call["after"]):
            assert (side["is_active"], side["inactive_reason"], side["inactive_note"]) == (
                False, "permanently_closed", "Lease ended")

    def test_coordinator_cannot_edit(self, client, auth_headers, authenticate_as, profile):
        authenticate_as("event_coordinator")

        response = client.patch(f"/api/v1/venues/{HALL_A_ID}", json=VALID_EDIT_PAYLOAD, headers=auth_headers)

        assert response.status_code == 403
        assert profile["update_venue"] == []

    def test_unknown_venue_is_404(self, client, auth_headers, authenticate_as, profile):
        authenticate_as("venue_staff")
        response = client.patch(
            "/api/v1/venues/b0000000-0000-4000-8000-0000000000ff", json=VALID_EDIT_PAYLOAD, headers=auth_headers
        )
        assert response.status_code == 404

    def test_closes_at_before_opens_at_is_422(self, client, auth_headers, authenticate_as, profile):
        authenticate_as("venue_staff")
        response = client.patch(
            f"/api/v1/venues/{HALL_A_ID}",
            json={**VALID_EDIT_PAYLOAD, "opens_at": "22:00:00", "closes_at": "08:00:00"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_a_lost_concurrency_race_is_409(self, client, auth_headers, authenticate_as, profile, monkeypatch):
        authenticate_as("venue_staff")
        monkeypatch.setattr(repository, "update_venue", lambda *a, **k: None)

        response = client.patch(f"/api/v1/venues/{HALL_A_ID}", json=VALID_EDIT_PAYLOAD, headers=auth_headers)

        assert response.status_code == 409

    class TestWarnings:
        @pytest.fixture()
        def booking_at_risk(self, monkeypatch, profile):
            """Hall A holds one approved booking for an event expecting 120 pax."""
            booking = BookingSummary(
                id="d0000000-0000-4000-8000-000000000050",
                event_id=EVENT_ID,
                period=Period(starts_at=datetime(2026, 10, 10, 9, tzinfo=SGT), ends_at=datetime(2026, 10, 10, 12, tzinfo=SGT)),
                status="approved",
            )
            monkeypatch.setattr(repository, "list_upcoming_bookings", lambda venue_id, since: [booking])
            monkeypatch.setattr(events_repository, "list_event_names", lambda ids: {EVENT_ID: "Annual Gala"})
            monkeypatch.setattr(
                events_repository,
                "list_planning_context",
                lambda ids: [
                    {
                        "id": EVENT_ID,
                        "name": "Annual Gala",
                        "coordinator_id": COORDINATOR_ID,
                        "expected_attendance": 120,
                        "layout_preference": "theatre",
                        "facilities_required": ["projector"],
                    }
                ]
                if EVENT_ID in ids
                else [],
            )
            return profile

        def test_reducing_capacity_below_attendance_warns_without_saving(
            self, client, auth_headers, authenticate_as, booking_at_risk
        ):
            authenticate_as("venue_staff")

            response = client.patch(
                f"/api/v1/venues/{HALL_A_ID}", json={**VALID_EDIT_PAYLOAD, "capacity": 100}, headers=auth_headers
            )

            assert response.status_code == 200
            body = response.json()
            assert body["saved"] is False
            assert body["venue"] is None
            assert len(body["warnings"]) == 1
            assert body["warnings"][0]["event_name"] == "Annual Gala"
            assert "120" in body["warnings"][0]["reasons"][0]
            assert booking_at_risk["update_venue"] == []

        def test_confirming_saves_and_notifies_the_coordinator(
            self, client, auth_headers, authenticate_as, booking_at_risk
        ):
            authenticate_as("venue_staff")

            response = client.patch(
                f"/api/v1/venues/{HALL_A_ID}",
                json={**VALID_EDIT_PAYLOAD, "capacity": 100, "confirm": True},
                headers=auth_headers,
            )

            assert response.status_code == 200
            body = response.json()
            assert body["saved"] is True
            assert body["venue"]["capacity"] == 100
            assert body["venue"]["upcoming_bookings"][0]["event_name"] == "Annual Gala"
            assert len(body["warnings"]) == 1

            # An Unsuitable booking's coordinator hears through its flag (CR-94).
            call = booking_at_risk["update_venue"][0]
            assert call["notifications"] == []
            [flag] = call["flags"]
            assert (flag["coordinator_id"], flag["event_id"]) == (COORDINATOR_ID, EVENT_ID)
            assert flag["reason"] == 'Venue "Hall A" was edited: Capacity 100 is below the expected attendance of 120.'
            assert flag["message"] == (
                'Venue "Hall A" was edited and your booking for "Annual Gala" is flagged Unsuitable: '
                "Capacity 100 is below the expected attendance of 120."
            )
            assert flag["unflagged_message"] == (
                'Venue "Hall A" changed in a way that may affect "Annual Gala": '
                "Capacity 100 is below the expected attendance of 120."
            )

        def test_a_booking_whose_event_has_no_planning_context_is_still_checked(
            self, client, auth_headers, authenticate_as, booking_at_risk, monkeypatch
        ):
            """An event row the events module can't return has no coordinator to
            notify, but the time-based check still applies and venue staff hear
            about it under a generic name."""
            monkeypatch.setattr(events_repository, "list_planning_context", lambda ids: [])
            other = "a0000000-0000-4000-8000-000000000031"
            monkeypatch.setattr(repository, "list_venue_staff_ids", lambda: {other})
            authenticate_as("venue_staff")

            response = client.patch(
                f"/api/v1/venues/{HALL_A_ID}",
                json={**VALID_EDIT_PAYLOAD, "opens_at": "10:00:00", "confirm": True},
                headers=auth_headers,
            )

            assert response.status_code == 200
            assert response.json()["saved"] is True
            [notification] = booking_at_risk["update_venue"][0]["notifications"]
            assert notification["recipient_id"] == other
            assert notification["message"].startswith('Venue "Hall A" was edited and "an event" needs a check: ')

        def test_a_reduction_that_still_covers_attendance_does_not_warn(
            self, client, auth_headers, authenticate_as, booking_at_risk
        ):
            authenticate_as("venue_staff")

            response = client.patch(
                f"/api/v1/venues/{HALL_A_ID}", json={**VALID_EDIT_PAYLOAD, "capacity": 130}, headers=auth_headers
            )

            body = response.json()
            assert body["saved"] is True
            assert body["warnings"] == []

        @pytest.mark.parametrize("event_status", ["completed", "cancelled"])
        def test_a_completed_or_cancelled_event_is_not_rechecked(
            self, client, auth_headers, authenticate_as, booking_at_risk, monkeypatch, event_status
        ):
            """CR-94 AC7: only bookings whose event can still happen are re-checked."""
            monkeypatch.setattr(
                events_repository,
                "list_planning_context",
                lambda ids: [
                    {"id": EVENT_ID, "name": "Annual Gala", "status": event_status, "coordinator_id": COORDINATOR_ID,
                     "expected_attendance": 120}
                ],
            )
            authenticate_as("venue_staff")

            response = client.patch(
                f"/api/v1/venues/{HALL_A_ID}", json={**VALID_EDIT_PAYLOAD, "capacity": 100}, headers=auth_headers
            )

            body = response.json()
            assert body["saved"] is True
            assert body["warnings"] == []
            assert booking_at_risk["update_venue"][0]["notifications"] == []


        def test_confirming_also_notifies_every_other_venue_staff_member(
            self, client, auth_headers, authenticate_as, booking_at_risk, monkeypatch
        ):
            """CR-94 AC5: the rest of the venue staff pool hears about it too;
            the editor already saw the warning, so is not notified."""
            actor = authenticate_as("venue_staff")
            others = ["a0000000-0000-4000-8000-000000000031", "a0000000-0000-4000-8000-000000000032"]
            monkeypatch.setattr(repository, "list_venue_staff_ids", lambda: {actor["id"], *others})

            client.patch(
                f"/api/v1/venues/{HALL_A_ID}",
                json={**VALID_EDIT_PAYLOAD, "capacity": 100, "confirm": True},
                headers=auth_headers,
            )

            notifications = booking_at_risk["update_venue"][0]["notifications"]
            staff = sorted((n for n in notifications if n["recipient_id"] != COORDINATOR_ID), key=lambda n: n["recipient_id"])
            assert [n["recipient_id"] for n in staff] == others
            assert all(n["event_id"] == EVENT_ID for n in staff)
            assert staff[0]["message"] == (
                'Venue "Hall A" was edited and "Annual Gala" is now Unsuitable: '
                "Capacity 100 is below the expected attendance of 120."
            )

        def test_venue_staff_get_one_notification_per_event_not_per_booking(
            self, client, auth_headers, authenticate_as, booking_at_risk, monkeypatch
        ):
            authenticate_as("venue_staff")
            other = "a0000000-0000-4000-8000-000000000031"
            monkeypatch.setattr(repository, "list_venue_staff_ids", lambda: {other})
            period = Period(starts_at=datetime(2026, 10, 11, 9, tzinfo=SGT), ends_at=datetime(2026, 10, 11, 12, tzinfo=SGT))
            monkeypatch.setattr(
                repository,
                "list_upcoming_bookings",
                lambda venue_id, since: [
                    BookingSummary(id=f"d0000000-0000-4000-8000-00000000007{i}", event_id=EVENT_ID, period=period,
                                   status="held")
                    for i in range(2)
                ],
            )

            client.patch(
                f"/api/v1/venues/{HALL_A_ID}",
                json={**VALID_EDIT_PAYLOAD, "capacity": 100, "confirm": True},
                headers=auth_headers,
            )

            notifications = booking_at_risk["update_venue"][0]["notifications"]
            [staff] = [n for n in notifications if n["recipient_id"] == other]
            # Both bookings fail for the same reason; the message says it once.
            assert staff["message"] == (
                'Venue "Hall A" was edited and "Annual Gala" is now Unsuitable: '
                "Capacity 100 is below the expected attendance of 120."
            )

        def test_a_warning_only_edit_tells_venue_staff_it_needs_a_check(
            self, client, auth_headers, authenticate_as, booking_at_risk, monkeypatch
        ):
            authenticate_as("venue_staff")
            other = "a0000000-0000-4000-8000-000000000031"
            monkeypatch.setattr(repository, "list_venue_staff_ids", lambda: {other})

            client.patch(
                f"/api/v1/venues/{HALL_A_ID}",
                json={**VALID_EDIT_PAYLOAD, "layouts": [{"layout": "boardroom", "capacity_for_layout": None}],
                      "confirm": True},
                headers=auth_headers,
            )

            notifications = booking_at_risk["update_venue"][0]["notifications"]
            message = next(n["message"] for n in notifications if n["recipient_id"] == other)
            assert message == (
                'Venue "Hall A" was edited and "Annual Gala" needs a check: '
                "The theatre layout this event needs is not supported."
            )

        def test_without_confirming_no_one_is_notified(
            self, client, auth_headers, authenticate_as, booking_at_risk, monkeypatch
        ):
            authenticate_as("venue_staff")
            monkeypatch.setattr(repository, "list_venue_staff_ids", lambda: {"a0000000-0000-4000-8000-000000000031"})

            client.patch(f"/api/v1/venues/{HALL_A_ID}", json={**VALID_EDIT_PAYLOAD, "capacity": 100}, headers=auth_headers)

            assert booking_at_risk["update_venue"] == []

    class TestFlagging:
        """CR-94 part 2: saving past the warning flags each Unsuitable booking
        through SCRUM-64's `flag_venue_bookings`, inside `update_venue`'s
        transaction, and returns flagged events to Planning."""

        BOOKING_ID = "d0000000-0000-4000-8000-000000000050"

        @pytest.fixture()
        def booking_at_risk(self, monkeypatch, profile):
            booking = BookingSummary(
                id=self.BOOKING_ID,
                event_id=EVENT_ID,
                period=Period(starts_at=datetime(2026, 10, 10, 9, tzinfo=SGT), ends_at=datetime(2026, 10, 10, 12, tzinfo=SGT)),
                status="approved",
            )
            monkeypatch.setattr(repository, "list_upcoming_bookings", lambda venue_id, since: [booking])
            monkeypatch.setattr(
                events_repository,
                "list_planning_context",
                lambda ids: [
                    {
                        "id": EVENT_ID,
                        "name": "Annual Gala",
                        "coordinator_id": COORDINATOR_ID,
                        "expected_attendance": 120,
                        "layout_preference": "theatre",
                        "facilities_required": ["projector"],
                    }
                ],
            )
            returned = []
            monkeypatch.setattr(events_service, "return_to_planning",
                                lambda event_id, *, reason_code, **kw: returned.append((event_id, reason_code)))
            profile["returned"] = returned
            return profile

        def _save(self, client, auth_headers, **changes):
            return client.patch(
                f"/api/v1/venues/{HALL_A_ID}",
                json={**VALID_EDIT_PAYLOAD, **changes, "confirm": True},
                headers=auth_headers,
            )

        def test_an_unsuitable_booking_is_flagged_with_its_reason(
            self, client, auth_headers, authenticate_as, booking_at_risk
        ):
            authenticate_as("venue_staff")

            self._save(client, auth_headers, capacity=100, layouts=[{"layout": "boardroom", "capacity_for_layout": None}])

            [flag] = booking_at_risk["update_venue"][0]["flags"]
            assert flag == {
                "booking_id": self.BOOKING_ID,
                "event_id": EVENT_ID,
                "coordinator_id": COORDINATOR_ID,
                # AC5: the flag's reason names only the hard rules that make it Unsuitable.
                "reason": 'Venue "Hall A" was edited: Capacity 100 is below the expected attendance of 120.',
                "message": (
                    'Venue "Hall A" was edited and your booking for "Annual Gala" is flagged Unsuitable: '
                    "Capacity 100 is below the expected attendance of 120. "
                    "The theatre layout this event needs is not supported."
                ),
                # Sent instead when the booking can't take the flag (already flagged, or re-review).
                "unflagged_message": (
                    'Venue "Hall A" changed in a way that may affect "Annual Gala": '
                    "Capacity 100 is below the expected attendance of 120. "
                    "The theatre layout this event needs is not supported."
                ),
            }

        def test_a_removed_required_facility_is_flagged(self, client, auth_headers, authenticate_as, booking_at_risk):
            authenticate_as("venue_staff")

            self._save(client, auth_headers, facilities=[])

            [flag] = booking_at_risk["update_venue"][0]["flags"]
            assert flag["reason"].startswith('Venue "Hall A" was edited: Missing facilities this event needs:')

        def test_a_warning_only_change_flags_nothing_and_notifies_the_coordinator(
            self, client, auth_headers, authenticate_as, booking_at_risk
        ):
            """AC4: layout, accessibility and operating hours only warn."""
            authenticate_as("venue_staff")

            self._save(client, auth_headers, layouts=[{"layout": "boardroom", "capacity_for_layout": None}])

            call = booking_at_risk["update_venue"][0]
            assert call["flags"] == []
            assert [(n["recipient_id"], n["event_id"]) for n in call["notifications"]] == [(COORDINATOR_ID, EVENT_ID)]
            assert booking_at_risk["returned"] == []

        def test_an_edit_affecting_nothing_flags_nothing(self, client, auth_headers, authenticate_as, booking_at_risk):
            authenticate_as("venue_staff")

            self._save(client, auth_headers, capacity=130)

            assert booking_at_risk["update_venue"][0]["flags"] == []

        def test_without_confirming_nothing_is_flagged(self, client, auth_headers, authenticate_as, booking_at_risk):
            authenticate_as("venue_staff")

            client.patch(f"/api/v1/venues/{HALL_A_ID}", json={**VALID_EDIT_PAYLOAD, "capacity": 100}, headers=auth_headers)

            assert booking_at_risk["update_venue"] == []
            assert booking_at_risk["returned"] == []

        def test_an_event_without_a_coordinator_is_still_flagged(
            self, client, auth_headers, authenticate_as, booking_at_risk, monkeypatch
        ):
            monkeypatch.setattr(
                events_repository, "list_planning_context",
                lambda ids: [{"id": EVENT_ID, "name": "Annual Gala", "expected_attendance": 120}],
            )
            authenticate_as("venue_staff")

            self._save(client, auth_headers, capacity=100)

            [flag] = booking_at_risk["update_venue"][0]["flags"]
            assert flag["coordinator_id"] is None

        def test_each_flagged_event_returns_to_planning(self, client, auth_headers, authenticate_as, booking_at_risk):
            """CR-104 AC10: a flagged event in Safety review or Confirmed goes back to Planning."""
            authenticate_as("venue_staff")
            booking_at_risk["flagged_event_ids"] = [EVENT_ID]

            response = self._save(client, auth_headers, capacity=100)

            assert response.status_code == 200
            assert booking_at_risk["returned"] == [(EVENT_ID, "arrangement_flagged")]

        def test_an_event_not_newly_flagged_is_not_returned(self, client, auth_headers, authenticate_as, booking_at_risk):
            """An already-flagged booking keeps its first flag, so nothing new happened to its event."""
            authenticate_as("venue_staff")

            self._save(client, auth_headers, capacity=100)

            assert booking_at_risk["returned"] == []

        def test_a_failed_return_still_reports_the_save(
            self, client, auth_headers, authenticate_as, booking_at_risk, monkeypatch, caplog
        ):
            authenticate_as("venue_staff")
            booking_at_risk["flagged_event_ids"] = [EVENT_ID]

            def _down(event_id, **kw):
                raise EventServiceUnavailableError()

            monkeypatch.setattr(events_service, "return_to_planning", _down)

            response = self._save(client, auth_headers, capacity=100)

            assert response.status_code == 200
            assert response.json()["saved"] is True
            assert EVENT_ID in caplog.text

    class TestSpaceRequirements:
        """CR-94: a booking for one of the event's spaces is judged on that
        space's requirements, falling back to the event's per field."""

        SPACE_ID = "f0000000-0000-4000-8000-000000000301"

        @pytest.fixture()
        def space_booking(self, monkeypatch, profile):
            booking = BookingSummary(
                id="d0000000-0000-4000-8000-000000000060",
                event_id=EVENT_ID,
                event_space_request_id=self.SPACE_ID,
                period=Period(starts_at=datetime(2026, 10, 10, 9, tzinfo=SGT), ends_at=datetime(2026, 10, 10, 12, tzinfo=SGT)),
                status="held",
            )
            monkeypatch.setattr(repository, "list_upcoming_bookings", lambda venue_id, since: [booking])
            monkeypatch.setattr(
                events_repository,
                "list_planning_context",
                lambda ids: [
                    {"id": EVENT_ID, "name": "Annual Gala", "status": "planning", "coordinator_id": COORDINATOR_ID,
                     "expected_attendance": 120, "facilities_required": ["projector"]}
                ],
            )
            return profile

        def _spaces(self, monkeypatch, **space):
            calls = []

            def _list(ids):
                calls.append(sorted(ids))
                return [{"id": self.SPACE_ID, "expected_pax": None, "layout_preference": None,
                         "facilities_required": None, **space}]

            monkeypatch.setattr(events_repository, "list_spaces_by_ids", _list)
            return calls

        def test_the_space_attendance_is_used_instead_of_the_event_total(
            self, client, auth_headers, authenticate_as, space_booking, monkeypatch
        ):
            calls = self._spaces(monkeypatch, expected_pax=140)
            authenticate_as("venue_staff")

            response = client.patch(
                f"/api/v1/venues/{HALL_A_ID}", json={**VALID_EDIT_PAYLOAD, "capacity": 130}, headers=auth_headers
            )

            warnings = response.json()["warnings"]
            assert len(warnings) == 1
            assert warnings[0]["outcome"] == "unsuitable"
            assert "140" in warnings[0]["reasons"][0]
            assert calls == [[self.SPACE_ID]]

        def test_a_field_the_space_leaves_empty_falls_back_to_the_event(
            self, client, auth_headers, authenticate_as, space_booking, monkeypatch
        ):
            """The space states no attendance and no facilities, so the event's
            120 pax and projector apply: dropping the projector is Unsuitable,
            cutting capacity to 130 is not."""
            self._spaces(monkeypatch, layout_preference="theatre")
            authenticate_as("venue_staff")

            response = client.patch(
                f"/api/v1/venues/{HALL_A_ID}",
                json={**VALID_EDIT_PAYLOAD, "capacity": 130, "facilities": []},
                headers=auth_headers,
            )

            warnings = response.json()["warnings"]
            assert [d["code"] for d in warnings[0]["details"]] == ["missing_facility"]

        def test_the_space_layout_is_used_instead_of_the_event_layout(
            self, client, auth_headers, authenticate_as, space_booking, monkeypatch
        ):
            """The event prefers theatre but this space wants boardroom, so
            dropping boardroom affects the booking and dropping theatre doesn't."""
            monkeypatch.setattr(
                events_repository,
                "list_planning_context",
                lambda ids: [{"id": EVENT_ID, "name": "Annual Gala", "status": "planning",
                              "coordinator_id": COORDINATOR_ID, "layout_preference": "theatre"}],
            )
            self._spaces(monkeypatch, layout_preference="boardroom")
            authenticate_as("venue_staff")
            both = [{"layout": "theatre", "capacity_for_layout": None}, {"layout": "boardroom", "capacity_for_layout": None}]
            monkeypatch.setattr(
                repository, "get_venue",
                lambda venue_id: make_venue_profile(HALL_A_ID, "Hall A", version=3, layouts=[
                    LayoutOption(layout=VenueLayout.theatre), LayoutOption(layout=VenueLayout.boardroom)]),
            )

            drop_boardroom = client.patch(
                f"/api/v1/venues/{HALL_A_ID}", json={**VALID_EDIT_PAYLOAD, "layouts": both[:1]}, headers=auth_headers
            ).json()
            drop_theatre = client.patch(
                f"/api/v1/venues/{HALL_A_ID}", json={**VALID_EDIT_PAYLOAD, "layouts": both[1:]}, headers=auth_headers
            ).json()

            assert [d["code"] for d in drop_boardroom["warnings"][0]["details"]] == ["layout_not_supported"]
            assert drop_theatre["warnings"] == []

        def test_the_space_facilities_are_used_instead_of_the_event_facilities(
            self, client, auth_headers, authenticate_as, space_booking, monkeypatch
        ):
            """The event needs a projector but this space needs a microphone, so
            removing the projector doesn't affect the booking; removing the
            microphone does."""
            self._spaces(monkeypatch, facilities_required=["microphone"])
            authenticate_as("venue_staff")
            monkeypatch.setattr(
                repository, "get_venue",
                lambda venue_id: make_venue_profile(HALL_A_ID, "Hall A", version=3,
                                                    facilities=[Facility.projector, Facility.microphone]),
            )

            drop_projector = client.patch(
                f"/api/v1/venues/{HALL_A_ID}", json={**VALID_EDIT_PAYLOAD, "facilities": ["microphone"]}, headers=auth_headers
            ).json()
            drop_microphone = client.patch(
                f"/api/v1/venues/{HALL_A_ID}", json={**VALID_EDIT_PAYLOAD, "facilities": ["projector"]}, headers=auth_headers
            ).json()

            assert drop_projector["warnings"] == []
            assert drop_microphone["warnings"][0]["reasons"] == ["Missing facilities this event needs: microphone."]

        def test_an_empty_space_facility_list_falls_back_to_the_event(
            self, client, auth_headers, authenticate_as, space_booking, monkeypatch
        ):
            """`event_space_requests.facilities_required` is never null: the
            space a booking request creates automatically stores `{}`. An empty
            list therefore means the space didn't say, not "needs nothing"."""
            self._spaces(monkeypatch, facilities_required=[])
            authenticate_as("venue_staff")

            response = client.patch(
                f"/api/v1/venues/{HALL_A_ID}", json={**VALID_EDIT_PAYLOAD, "facilities": []}, headers=auth_headers
            )

            warnings = response.json()["warnings"]
            assert [d["code"] for d in warnings[0]["details"]] == ["missing_facility"]

        def test_the_event_accessibility_needs_reach_the_check(
            self, client, auth_headers, authenticate_as, space_booking, monkeypatch
        ):
            self._spaces(monkeypatch)
            monkeypatch.setattr(
                events_repository,
                "list_planning_context",
                lambda ids: [{"id": EVENT_ID, "name": "Annual Gala", "status": "planning",
                              "coordinator_id": COORDINATOR_ID, "accessibility_needs": "Two wheelchair users"}],
            )
            authenticate_as("venue_staff")

            response = client.patch(
                f"/api/v1/venues/{HALL_A_ID}",
                json={**VALID_EDIT_PAYLOAD, "accessibility_features": []},
                headers=auth_headers,
            )

            warnings = response.json()["warnings"]
            assert warnings[0]["outcome"] == "warning"
            assert [d["code"] for d in warnings[0]["details"]] == ["accessibility_changed"]


class TestVenueEditHistory:
    @pytest.fixture()
    def history(self, monkeypatch):
        monkeypatch.setattr(
            repository, "get_venue", lambda venue_id: make_venue_profile(HALL_A_ID, "Hall A") if venue_id == HALL_A_ID else None
        )
        entries = [
            {
                "id": "h0000000-0000-4000-8000-000000000001",
                "before": {"capacity": 150},
                "after": {"capacity": 100},
                "created_at": "2026-10-06T10:00:00+08:00",
                "actor": {"id": "a0000000-0000-4000-8000-000000000003", "full_name": "Val Staff"},
            }
        ]
        monkeypatch.setattr(repository, "list_edit_history", lambda venue_id: entries if venue_id == HALL_A_ID else [])
        return entries

    def test_an_unknown_venue_is_404(self, client, auth_headers, authenticate_as, history):
        authenticate_as("venue_staff")

        assert client.get(f"/api/v1/venues/{HALL_B_ID}/history", headers=auth_headers).status_code == 404

    @pytest.mark.parametrize(
        ("actor", "expected"),
        [
            # PostgREST may embed the to-one actor as a one-element list.
            ([{"id": VENUE_STAFF_ID, "full_name": "Val Staff"}], {"id": VENUE_STAFF_ID, "full_name": "Val Staff"}),
            ([], None),
        ],
    )
    def test_an_actor_embedded_as_a_list_is_unwrapped(
        self, client, auth_headers, authenticate_as, history, actor, expected
    ):
        history[0]["actor"] = actor
        authenticate_as("venue_staff")

        body = client.get(f"/api/v1/venues/{HALL_A_ID}/history", headers=auth_headers).json()

        assert body["entries"][0]["actor"] == expected

    def test_venue_staff_can_read_it(self, client, auth_headers, authenticate_as, history):
        authenticate_as("venue_staff")
        response = client.get(f"/api/v1/venues/{HALL_A_ID}/history", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["entries"][0]["before"] == {"capacity": 150}
        assert body["entries"][0]["after"] == {"capacity": 100}
        assert body["entries"][0]["actor"]["full_name"] == "Val Staff"

    def test_coordinator_can_read_it_too(self, client, auth_headers, authenticate_as, history):
        authenticate_as("event_coordinator")
        response = client.get(f"/api/v1/venues/{HALL_A_ID}/history", headers=auth_headers)
        assert response.status_code == 200

    def test_organiser_cannot_read_it(self, client, auth_headers, authenticate_as, history):
        authenticate_as("event_organiser")
        response = client.get(f"/api/v1/venues/{HALL_A_ID}/history", headers=auth_headers)
        assert response.status_code == 403
