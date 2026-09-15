"""Venue module use cases: search the catalogue, read one venue."""

from datetime import datetime, timezone

from app.core.exceptions import VenueNotFoundError
from app.modules.venues import repository, search
from app.modules.venues.schemas import VenueDetail, VenueSearchCriteria, VenueSearchResponse


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
    venue = repository.get_venue(venue_id)
    if venue is None:
        raise VenueNotFoundError()
    now = datetime.now(timezone.utc)
    return VenueDetail(
        **venue.model_dump(),
        upcoming_blocks=repository.list_upcoming_blocks(venue_id, now),
        upcoming_bookings=repository.list_upcoming_bookings(venue_id, now),
    )
