"""Pure rules for REQUIREMENTS VC-R2 (SCRUM-63, CR-94): does editing a venue
put any of its upcoming bookings at odds with their event's requirements?

`affected_bookings` runs `suitability.check` on each booking's requirements
against the `before` and `after` venue and reports only *newly* broken rules,
so a pre-existing mismatch the edit did not cause never surfaces as a warning
about this edit. A booking whose new problems include a hard rule (capacity or
a required facility) is `unsuitable`; any other is a `warning` (CR-94).

One rule exists only here: `accessibility_changed`, raised when the venue's
accessibility features change and the event lists accessibility needs.
`events.accessibility_needs` is free text, so whether the new features still
meet it is for a person to judge.

Nothing here touches Supabase or the events module directly — the caller
(venues.service) assembles `BookingImpactContext` rows through
`events.service`, the same cross-module pattern `search.py` and `get_venue`
already use.
"""

from app.modules.venues import suitability
from app.modules.venues.schemas import (
    AffectedBooking,
    BookingImpactContext,
    SuitabilityCode,
    SuitabilityReason,
    SuitabilitySeverity,
    VenueRequirements,
    VenueSummary,
    label,
)


def _requirements(booking: BookingImpactContext) -> VenueRequirements:
    return VenueRequirements(
        expected_attendance=booking.expected_attendance,
        layout_preference=booking.layout_preference,
        facilities_required=booking.facilities_required,
        period=booking.period,
    )


def _accessibility_changed(
    before: VenueSummary, after: VenueSummary, booking: BookingImpactContext
) -> SuitabilityReason | None:
    needs = (booking.accessibility_needs or "").strip()
    if not needs or set(before.accessibility_features) == set(after.accessibility_features):
        return None
    now = ", ".join(sorted(label(a) for a in after.accessibility_features)) or "none"
    return SuitabilityReason(
        code=SuitabilityCode.accessibility_changed,
        severity=SuitabilitySeverity.warning,
        message=(
            f"The venue's accessibility features changed (now: {now}). "
            f"Check they still meet this event's needs: {needs}."
        ),
    )


def _newly_broken(
    before: VenueSummary, after: VenueSummary, booking: BookingImpactContext
) -> list[SuitabilityReason]:
    req = _requirements(booking)
    already = {reason.code for reason in suitability.check(before, req).reasons}
    details = [reason for reason in suitability.check(after, req).reasons if reason.code not in already]
    accessibility = _accessibility_changed(before, after, booking)
    if accessibility is not None:
        details.append(accessibility)
    return details


def affected_bookings(
    before: VenueSummary, after: VenueSummary, bookings: list[BookingImpactContext]
) -> list[AffectedBooking]:
    """Bookings whose event has a problem under `after` that it did not have
    under `before` — the impact of this specific edit, not a general audit."""
    results = []
    for booking in bookings:
        details = _newly_broken(before, after, booking)
        if not details:
            continue
        unsuitable = any(d.severity == SuitabilitySeverity.unsuitable for d in details)
        results.append(
            AffectedBooking(
                booking_id=booking.booking_id,
                event_id=booking.event_id,
                event_name=booking.event_name,
                period=booking.period,
                outcome="unsuitable" if unsuitable else "warning",
                details=details,
                reasons=[d.message for d in details],
            )
        )
    return results
