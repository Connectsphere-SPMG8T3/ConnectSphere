"""Venue suitability rules (CR-94, extended by SCRUM-18) as pure functions:
does one venue meet one set of requirements?

`check` returns a verdict and the reasons behind it. An inactive venue,
capacity and required facilities are hard rules: failing one makes the venue
Unsuitable. Layout, accessibility and operating hours only warn. Nothing here
touches Supabase.

`events.accessibility_needs` is free text, so it is matched to the venue's
accessibility features by keyword (`ACCESSIBILITY_KEYWORDS`) [Team decision,
REQUIREMENTS §6.11].
"""

from datetime import timedelta, timezone

from app.modules.venues.schemas import (
    AccessibilityFeature,
    SuitabilityCode,
    SuitabilityReason,
    SuitabilityResult,
    SuitabilitySeverity,
    SuitabilityVerdict,
    VenueLayout,
    VenueRequirements,
    VenueSummary,
    label,
)

# Venues are Singapore venues (REQUIREMENTS §6.8); operating hours are plain
# local wall-clock values, so a booking's instant is read back in this fixed
# offset (no daylight saving, same as the rest of the venues module).
SGT = timezone(timedelta(hours=8))

# What an event's free-text accessibility needs say, per venue feature. A need
# counts when any keyword appears in the text, ignoring case.
ACCESSIBILITY_KEYWORDS: dict[AccessibilityFeature, tuple[str, ...]] = {
    AccessibilityFeature.wheelchair_access: ("wheelchair", "mobility"),
    AccessibilityFeature.step_free_entry: ("step-free", "step free", "ramp"),
    AccessibilityFeature.accessible_toilet: ("toilet", "restroom", "washroom"),
    AccessibilityFeature.hearing_loop: ("hearing", "deaf"),
    AccessibilityFeature.lift_access: ("lift", "elevator"),
}


def effective_capacity(venue: VenueSummary, layout: VenueLayout | None) -> int:
    """The capacity rule shared by search (VS-R6), edit-impact checking
    (VC-R2) and suitability: the per-layout figure when the venue records one
    for the requested layout, otherwise the venue-wide capacity."""
    if layout is not None:
        for option in venue.layouts:
            if option.layout == layout and option.capacity_for_layout is not None:
                return option.capacity_for_layout
    return venue.capacity


def _accessibility_reason(venue: VenueSummary, needs: str | None) -> SuitabilityReason | None:
    text = (needs or "").strip()
    if not text:
        return None
    lowered = text.lower()
    wanted = {feature for feature, words in ACCESSIBILITY_KEYWORDS.items() if any(w in lowered for w in words)}
    if wanted:
        missing = sorted(label(f) for f in wanted - set(venue.accessibility_features))
        if not missing:
            return None
        message = f"Missing accessibility features this event needs: {', '.join(missing)}."
    else:
        recorded = ", ".join(sorted(label(f) for f in venue.accessibility_features)) or "none"
        message = (
            f"This event lists accessibility needs ({text}) that could not be matched. "
            f"The venue records: {recorded}."
        )
    return SuitabilityReason(
        code=SuitabilityCode.missing_accessibility, severity=SuitabilitySeverity.warning, message=message
    )


def _reasons(venue: VenueSummary, req: VenueRequirements) -> list[SuitabilityReason]:
    reasons: list[SuitabilityReason] = []

    if not venue.is_active:
        reasons.append(
            SuitabilityReason(
                code=SuitabilityCode.inactive,
                severity=SuitabilitySeverity.unsuitable,
                message="This venue is inactive, so it can't be booked.",
            )
        )

    if req.expected_attendance is not None:
        capacity = effective_capacity(venue, req.layout_preference)
        if req.expected_attendance > capacity:
            reasons.append(
                SuitabilityReason(
                    code=SuitabilityCode.capacity,
                    severity=SuitabilitySeverity.unsuitable,
                    message=f"Capacity {capacity} is below the expected attendance of {req.expected_attendance}.",
                )
            )

    missing = sorted(label(f) for f in set(req.facilities_required) - set(venue.facilities))
    if missing:
        reasons.append(
            SuitabilityReason(
                code=SuitabilityCode.missing_facility,
                severity=SuitabilitySeverity.unsuitable,
                message=f"Missing facilities this event needs: {', '.join(missing)}.",
            )
        )

    if req.layout_preference is not None and req.layout_preference not in {o.layout for o in venue.layouts}:
        reasons.append(
            SuitabilityReason(
                code=SuitabilityCode.layout_not_supported,
                severity=SuitabilitySeverity.warning,
                message=f"The {label(req.layout_preference)} layout this event needs is not supported.",
            )
        )

    accessibility = _accessibility_reason(venue, req.accessibility_needs)
    if accessibility is not None:
        reasons.append(accessibility)

    if req.period is not None:
        start_local = req.period.starts_at.astimezone(SGT).time()
        end_local = req.period.ends_at.astimezone(SGT).time()
        if start_local < venue.opens_at or end_local > venue.closes_at:
            reasons.append(
                SuitabilityReason(
                    code=SuitabilityCode.outside_operating_hours,
                    severity=SuitabilitySeverity.warning,
                    message=(
                        "The booking's time falls outside the venue's operating hours "
                        f"({venue.opens_at:%H:%M}–{venue.closes_at:%H:%M})."
                    ),
                )
            )

    return reasons


def _verdict(reasons: list[SuitabilityReason]) -> SuitabilityVerdict:
    if any(r.severity == SuitabilitySeverity.unsuitable for r in reasons):
        return SuitabilityVerdict.unsuitable
    if reasons:
        return SuitabilityVerdict.suitable_with_warnings
    return SuitabilityVerdict.suitable


def check(venue: VenueSummary, req: VenueRequirements) -> SuitabilityResult:
    """Judge one venue against one set of requirements."""
    reasons = _reasons(venue, req)
    return SuitabilityResult(verdict=_verdict(reasons), reasons=reasons)
