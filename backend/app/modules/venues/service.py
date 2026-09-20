"""Venue module use cases: search the catalogue, read one venue."""

from datetime import datetime, timezone

from app.core.exceptions import VenueNotFoundError
from app.modules.events import service as events_service
from app.modules.venues import repository, search
from app.modules.venues.schemas import (
    VenueDetail,
    VenueSearchCriteria,
    VenueSearchResponse,
    VenueStaffDashboard,
)

# What the venue-staff dashboard tracks. `approved` is deliberately absent:
# a settled booking is not work, and it belongs on the per-venue availability
# calendar of §6.9 (SCRUM-16) rather than in a queue of things to decide.
# The remaining occupying status, `held`, plus `re_review`, are exactly the two
# that are waiting on a venue-staff decision (§6.12, §6.19).
DASHBOARD_BOOKING_STATUSES = frozenset({"held", "re_review"})


def search_venues(criteria: VenueSearchCriteria) -> VenueSearchResponse:
    """Evaluate every venue against the criteria (and the period, if given)."""
    venues = repository.list_venues()
    period = criteria.period
    occupants = repository.list_occupants(period) if period is not None else {}

    evaluated = search.search(venues, criteria, occupants)
    excluded_count = sum(1 for r in evaluated if r.excluded)
    results = evaluated if criteria.include_excluded else [r for r in evaluated if not r.excluded]

    return VenueSearchResponse(
        criteria=criteria,
        results=results,
        included_count=len(evaluated) - excluded_count,
        excluded_count=excluded_count,
    )


def get_venue(venue_id: str) -> VenueDetail:
    """The full venue profile: attributes, who last touched them, and what is
    already booked (SCRUM-67).

    One response, because the profile is read to plan around the venue and a
    page that fetched its bookings separately could show attributes and
    occupancy from two different instants.
    """
    venue = repository.get_venue(venue_id)
    if venue is None:
        raise VenueNotFoundError()
    now = datetime.now(timezone.utc)
    bookings = repository.list_upcoming_bookings(venue_id, now)
    # One lookup for the whole list, not one per booking. Skipped entirely when
    # the venue is free, so a quiet venue costs no second round trip.
    names = events_service.names_by_id(b.event_id for b in bookings) if bookings else {}
    for booking in bookings:
        booking.event_name = names.get(booking.event_id)
    return VenueDetail(
        **venue.model_dump(),
        upcoming_blocks=repository.list_upcoming_blocks(venue_id, now),
        upcoming_bookings=bookings,
    )


def venue_staff_dashboard(now: datetime | None = None) -> VenueStaffDashboard:
    """Everything the venue-staff work queue needs, across ALL venues (§6.21).

    The scope is every venue, not a subset. Venue staff operate as a pool and
    the allocation of staff to venues is not tracked anywhere in the system
    (AUTH-R5, QA-44), so "the venues I'm in charge of" resolves to all of them.

    `now` is injectable so the ordering and the "still relevant" cut-off can be
    tested without freezing the clock.
    """
    now = now or datetime.now(timezone.utc)

    # One query for both statuses, partitioned here: they come from the same
    # table with the same filter, so two round trips would buy nothing.
    bookings = repository.list_all_upcoming_bookings(now, DASHBOARD_BOOKING_STATUSES)

    return VenueStaffDashboard(
        generated_at=now,
        venues=repository.list_venues(),
        # Oldest first (BR-R4): a hold never expires, so its age is the only
        # nudge the system gives. Tie-broken on id for a stable order.
        pending_holds=sorted(
            (b for b in bookings if b.status == "held"),
            key=lambda b: (b.requested_at, b.id),
        ),
        re_review_bookings=[b for b in bookings if b.status == "re_review"],
        blocks=repository.list_all_upcoming_blocks(now),
    )
