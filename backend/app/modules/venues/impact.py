"""Pure rules for REQUIREMENTS VC-R2 (SCRUM-63): does editing a venue put any
of its upcoming bookings at odds with their event's requirements?

`affected_bookings` compares `before` and `after` venue state for each
booking and reports only *newly* broken rules, so a pre-existing mismatch the
edit did not cause never surfaces as a warning about this edit. Nothing here
touches Supabase or the events module directly — the caller (venues.service)
assembles `BookingImpactContext` rows through `events.service`, the same
cross-module pattern `search.py` and `get_venue` already use.
"""

from datetime import timedelta, timezone

from app.modules.venues.schemas import AffectedBooking, BookingImpactContext, VenueSummary
from app.modules.venues.search import effective_capacity

# Venues are Singapore venues (REQUIREMENTS §6.8); operating hours are plain
# local wall-clock values, so a booking's instant is read back in this fixed
# offset (no daylight saving, same as the rest of the venues module).
SGT = timezone(timedelta(hours=8))

CAPACITY = "capacity"
LAYOUT = "layout"
FACILITIES = "facilities"
HOURS = "hours"


def _broken_rules(venue: VenueSummary, booking: BookingImpactContext) -> set[str]:
    broken: set[str] = set()

    if booking.expected_attendance is not None:
        if booking.expected_attendance > effective_capacity(venue, booking.layout_preference):
            broken.add(CAPACITY)

    if booking.layout_preference is not None:
        supported = {option.layout for option in venue.layouts}
        if booking.layout_preference not in supported:
            broken.add(LAYOUT)

    missing = set(booking.facilities_required) - set(venue.facilities)
    if missing:
        broken.add(FACILITIES)

    start_local = booking.period.starts_at.astimezone(SGT).time()
    end_local = booking.period.ends_at.astimezone(SGT).time()
    if start_local < venue.opens_at or end_local > venue.closes_at:
        broken.add(HOURS)

    return broken


def _message(code: str, venue: VenueSummary, booking: BookingImpactContext) -> str:
    if code == CAPACITY:
        return f"Capacity no longer covers this event's expected attendance of {booking.expected_attendance}."
    if code == LAYOUT:
        return f"The {booking.layout_preference.value.replace('_', ' ')} layout this event needs is no longer supported."
    if code == FACILITIES:
        missing = sorted(f.value.replace("_", " ") for f in set(booking.facilities_required) - set(venue.facilities))
        return f"Missing facilities this event needs: {', '.join(missing)}."
    return "This booking's time now falls outside the venue's operating hours."


def affected_bookings(
    before: VenueSummary, after: VenueSummary, bookings: list[BookingImpactContext]
) -> list[AffectedBooking]:
    """Bookings whose event has a problem under `after` that it did not have
    under `before` — the impact of this specific edit, not a general audit."""
    results = []
    for booking in bookings:
        newly_broken = _broken_rules(after, booking) - _broken_rules(before, booking)
        if newly_broken:
            reasons = [_message(code, after, booking) for code in sorted(newly_broken)]
            results.append(
                AffectedBooking(
                    booking_id=booking.booking_id,
                    event_id=booking.event_id,
                    event_name=booking.event_name,
                    period=booking.period,
                    reasons=reasons,
                )
            )
    return results
