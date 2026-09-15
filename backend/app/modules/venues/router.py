from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.venues import service
from app.modules.venues.schemas import VenueDetail, VenueSearchCriteria, VenueSearchResponse

router = APIRouter(prefix="/venues", tags=["venues"])

# Access matrix (REQUIREMENTS §2): coordinators read and search the catalogue,
# venue staff manage it; organisers, attendees and tech support see nothing.
# No per-resource relationship check is needed yet: search is not tied to an
# event. When an `event_id` criterion is added, the "this event's coordinator"
# check comes with it.
VenueReader = Annotated[CurrentUser, Depends(require_roles(["event_coordinator", "venue_staff"]))]

# Endpoints are plain `def`: supabase-py is synchronous, so FastAPI runs them
# in its threadpool instead of blocking the event loop.


@router.get("", response_model=VenueSearchResponse, status_code=status.HTTP_200_OK)
def search_venues(
    criteria: Annotated[VenueSearchCriteria, Query()],
    current_user: VenueReader,
) -> VenueSearchResponse:
    """Search the venue catalogue.

    With no criteria this lists every active venue. Each criterion given is
    strict; `starts_at`/`ends_at` (ISO 8601 with offset, given together) add
    an availability check against holds, bookings and blocks. Pass
    `include_excluded=true` to also return the venues that were ruled out,
    each with its reasons.
    """
    return service.search_venues(criteria)


@router.get("/{venue_id}", response_model=VenueDetail, status_code=status.HTTP_200_OK)
def read_venue(venue_id: UUID, current_user: VenueReader) -> VenueDetail:
    """One venue with its upcoming blocks and occupying bookings."""
    return service.get_venue(str(venue_id))
