"""Venue search rules (REQUIREMENTS §6.10, §6.14) as pure functions.

`evaluate` decides, for one venue, whether it meets every criterion the
coordinator set and whether it is free for the requested period; `search`
runs it over the catalogue and orders the results. Nothing here touches
Supabase, so the boundaries are unit-testable (tests/test_venue_search.py).

Deliberately absent: setup/turnaround buffers (zero, QA-28) and the
operating-hours / suitability warnings, which belong to SCRUM-18.
"""

from datetime import tzinfo

from app.modules.venues.schemas import (
    Availability,
    Occupant,
    Period,
    Reason,
    ReasonCode,
    VenueLayout,
    VenueSearchCriteria,
    VenueSearchResult,
    VenueSummary,
    label,
)

# Booking statuses that occupy the venue (§6.14); anything else is ignored.
OCCUPYING_STATUSES = frozenset({"held", "approved", "re_review"})


def effective_capacity(venue: VenueSummary, layout: VenueLayout | None) -> int:
    """The capacity rule shared by search (VS-R6) and edit-impact checking
    (VC-R2): the per-layout figure when the venue records one for the
    requested layout, otherwise the venue-wide capacity."""
    if layout is not None:
        for option in venue.layouts:
            if option.layout == layout and option.capacity_for_layout is not None:
                return option.capacity_for_layout
    return venue.capacity


def _format_period(period: Period, tz: tzinfo) -> str:
    start = period.starts_at.astimezone(tz)
    end = period.ends_at.astimezone(tz)
    if start.date() == end.date():
        return f"{start.day} {start:%b %H:%M}–{end:%H:%M}"
    return f"{start.day} {start:%b %H:%M} – {end.day} {end:%b %H:%M}"


def _criteria_reasons(venue: VenueSummary, criteria: VenueSearchCriteria) -> list[Reason]:
    reasons: list[Reason] = []

    if not venue.is_active:
        reasons.append(Reason(code=ReasonCode.inactive, message="Venue is inactive"))

    layouts = {option.layout: option.capacity_for_layout for option in venue.layouts}

    if criteria.min_capacity is not None:
        # Per-layout capacity wins when the coordinator asked for that layout
        # and the venue records a figure for it (§6.11 capacity rule).
        capacity = effective_capacity(venue, criteria.layout)
        subject = f"{label(criteria.layout).capitalize()} capacity" if criteria.layout in layouts and layouts.get(criteria.layout) is not None else "Capacity"
        if capacity < criteria.min_capacity:
            reasons.append(
                Reason(
                    code=ReasonCode.capacity_below_minimum,
                    message=f"{subject} {capacity} is below the required {criteria.min_capacity}",
                )
            )

    if criteria.layout is not None and criteria.layout not in layouts:
        reasons.append(
            Reason(
                code=ReasonCode.layout_not_supported,
                message=f"{label(criteria.layout).capitalize()} layout is not supported",
            )
        )

    missing_facilities = sorted(label(f) for f in set(criteria.facilities) - set(venue.facilities))
    if missing_facilities:
        reasons.append(
            Reason(code=ReasonCode.missing_facility, message=f"Missing facilities: {', '.join(missing_facilities)}")
        )

    missing_access = sorted(label(a) for a in set(criteria.accessibility) - set(venue.accessibility_features))
    if missing_access:
        reasons.append(
            Reason(
                code=ReasonCode.missing_accessibility_feature,
                message=f"Missing accessibility features: {', '.join(missing_access)}",
            )
        )

    if criteria.location is not None:
        needle = criteria.location.strip().lower()
        if needle and needle not in venue.location.lower():
            reasons.append(
                Reason(code=ReasonCode.location_mismatch, message=f"Location does not match '{criteria.location.strip()}'")
            )

    return reasons


def _availability_reasons(period: Period, occupants: list[Occupant]) -> list[Reason]:
    reasons: list[Reason] = []
    tz = period.starts_at.tzinfo
    for occupant in sorted(occupants, key=lambda o: o.period.starts_at):
        if not occupant.period.overlaps(period):
            continue
        when = _format_period(occupant.period, tz)
        if occupant.kind == "block":
            reasons.append(Reason(code=ReasonCode.blocked, message=f"Blocked: {label(occupant.detail)} {when}"))
        elif occupant.detail == "held":
            reasons.append(Reason(code=ReasonCode.held, message=f"Held by another event {when}"))
        elif occupant.detail in OCCUPYING_STATUSES:
            reasons.append(Reason(code=ReasonCode.booked, message=f"Booked by another event {when}"))
    return reasons


def evaluate(venue: VenueSummary, criteria: VenueSearchCriteria, occupants: list[Occupant]) -> VenueSearchResult:
    """Apply every criterion and the availability check to one venue."""
    reasons = _criteria_reasons(venue, criteria)

    period = criteria.period
    if period is None:
        availability = Availability.not_checked
    else:
        conflicts = _availability_reasons(period, occupants)
        reasons.extend(conflicts)
        availability = Availability.unavailable if conflicts else Availability.available

    return VenueSearchResult(venue=venue, availability=availability, excluded=bool(reasons), reasons=reasons)


def search(
    venues: list[VenueSummary],
    criteria: VenueSearchCriteria,
    occupants_by_venue: dict[str, list[Occupant]],
) -> list[VenueSearchResult]:
    """Evaluate the whole catalogue: included venues first, then the excluded
    ones, each group ordered by name. The caller decides whether to show the
    excluded group (`criteria.include_excluded`)."""
    results = [evaluate(venue, criteria, occupants_by_venue.get(venue.id, [])) for venue in venues]
    results.sort(key=lambda r: (r.excluded, r.venue.name.lower()))
    return results
