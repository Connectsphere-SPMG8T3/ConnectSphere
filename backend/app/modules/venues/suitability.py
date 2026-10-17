"""Venue suitability rules (CR-94; story 18 builds on this module) as pure
functions: does one venue meet one set of requirements?

`check` returns a verdict and the reasons behind it. Capacity and required
facilities are hard rules: missing one makes the venue Unsuitable. Layout and
operating hours only warn. Nothing here touches Supabase.

Left for story 18: an inactive venue (its AC4) and accessibility matching (its
AC5). `events.accessibility_needs` is free text, so there is nothing to match
against the venue's features yet.
"""

from datetime import timedelta, timezone

from app.modules.venues.schemas import (
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


def effective_capacity(venue: VenueSummary, layout: VenueLayout | None) -> int:
    """The capacity rule shared by search (VS-R6), edit-impact checking
    (VC-R2) and suitability: the per-layout figure when the venue records one
    for the requested layout, otherwise the venue-wide capacity."""
    if layout is not None:
        for option in venue.layouts:
            if option.layout == layout and option.capacity_for_layout is not None:
                return option.capacity_for_layout
    return venue.capacity


def _reasons(venue: VenueSummary, req: VenueRequirements) -> list[SuitabilityReason]:
    reasons: list[SuitabilityReason] = []

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
