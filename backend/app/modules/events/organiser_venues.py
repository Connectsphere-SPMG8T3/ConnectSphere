"""CR-111: what an organiser sees of each venue on their event (QA3-53, CAL-R8).

Pure: no I/O. Takes the booking rows the venues service already returns and keeps only
what is safe for the organiser, so staff notes, flag reasons, replacement links and
re-review reasons are never copied across (AC6).
"""
from datetime import datetime

from app.modules.events.schemas import EventSpaceRequestResponse, OrganiserVenue

# The only wording the organiser gets for a venue. `next_action` for an approved venue
# depends on the event, see `_next_action`.
ORGANISER_VENUE_STATUSES = {
    "awaiting_approval": {
        "label": "Awaiting venue approval",
        "next_action": "Venue staff are reviewing this request. This venue is not confirmed yet.",
    },
    "approved": {
        "label": "Approved",
        "next_action": "Nothing is needed from you.",
    },
    "re_review": {
        "label": "Being re-checked",
        "next_action": "Venue staff are checking this venue again after a change. Your coordinator will update you.",
    },
    # CR-95: the venue became unavailable. Why is the coordinator's to follow up (CAL-R5).
    "affected": {
        "label": "Affected",
        "next_action": "This venue is no longer available. Your coordinator will contact you about the next step.",
    },
}

_APPROVED_BEFORE_CONFIRMED = "Approved by venue staff. Your coordinator will confirm the event once the remaining checks are done."
_BOOKING_STATUS_KEYS = {"held": "awaiting_approval", "approved": "approved", "re_review": "re_review"}


def _status_key(booking: dict) -> str | None:
    # Only `affected` is shown from the coordinator's flags; the others stay internal.
    if booking.get("flag") == "affected" and booking["status"] in _BOOKING_STATUS_KEYS:
        return "affected"
    return _BOOKING_STATUS_KEYS.get(booking["status"])


def _next_action(key: str, event_status: str) -> str:
    if key == "approved" and event_status in ("planning", "safety_review"):
        return _APPROVED_BEFORE_CONFIRMED
    return ORGANISER_VENUE_STATUSES[key]["next_action"]


def _preparation_stage(booking: dict, event_status: str) -> str | None:
    # CR-109 AC4: only the stage is copied, and only once the event is Confirmed (AC1).
    if event_status not in ("confirmed", "preparation"):
        return None
    return (booking.get("preparation") or {}).get("stage") or "not_started"


def organiser_venues(
    event_status: str,
    event_starts_at: datetime | None,
    event_ends_at: datetime | None,
    spaces: list[EventSpaceRequestResponse],
    bookings: list[dict],
) -> list[OrganiserVenue]:
    """One entry per booking, in the order given. Expired and other settled bookings are
    left out. A space without a window of its own inherits the event's (BR-R15)."""
    by_id = {space.id: space for space in spaces}
    venues = []
    for booking in bookings:
        key = _status_key(booking)
        if key is None:
            continue
        space = by_id.get(booking.get("event_space_request_id"))
        venues.append(OrganiserVenue(
            booking_id=booking["id"],
            space_label=space.label if space else None,
            venue_name=booking.get("venue_name"),
            location=booking.get("venue_location"),
            starts_at=(space.starts_at if space and space.starts_at else event_starts_at),
            ends_at=(space.ends_at if space and space.ends_at else event_ends_at),
            is_primary=bool(space and space.is_primary),
            status=key,
            status_label=ORGANISER_VENUE_STATUSES[key]["label"],
            next_action=_next_action(key, event_status),
            preparation_stage=_preparation_stage(booking, event_status),
        ))
    return venues
