"""Venue module use cases: search the catalogue, read one venue, edit one, request a booking."""

import logging
import sys
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from httpx import HTTPError
from postgrest.exceptions import APIError

from app.core.exceptions import (
    BookingConflictError,
    BookingDecisionConflictError,
    BookingDecisionTextError,
    BookingNotFoundError,
    EventServiceUnavailableError,
    InsufficientRoleError,
    NotAssignedCoordinatorError,
    VenueAlreadyActiveError,
    VenueAlreadyInactiveError,
    VenueBlockChangeConflictError,
    VenueBlockInvalidError,
    VenueBlockNotFoundError,
    VenueConflictError,
    VenueNotFoundError,
    VenueServiceUnavailableError,
)
from app.modules.events import service as events_service
from app.modules.events.schemas import BookingReadiness, EventPlanningContext, SpaceRequirements
from app.modules.auth.dependencies import CurrentUser
from app.modules.venues import impact, repository, search, suitability
from app.modules.venues.search import OCCUPYING_STATUSES
from app.modules.venues.schemas import (
    ReReviewContext,
    BLOCK_REASON_LABELS,
    INACTIVE_REASON_LABELS,
    AffectedBooking,
    BlockSummary,
    BookingConflict,
    BookingDecision,
    BookingEventRequirements,
    BookingHistoryEntry,
    BookingImpactContext,
    CalendarBooking,
    CalendarEntry,
    CalendarVenue,
    Editor,
    FlaggableBooking,
    HoldExpiry,
    SuitabilitySeverity,
    VenueBooking,
    VenueBookingCreate,
    VenueBookingDetail,
    VenueBookingReject,
    VenueBlock,
    VenueCalendar,
    VenueBlockChange,
    VenueBlockChangeResponse,
    VenueBlockCreate,
    VenueBlockResponse,
    VenueDeactivateRequest,
    VenueDeactivateResponse,
    VenueDetail,
    VenueEditHistoryEntry,
    VenueEditHistoryResponse,
    VenuePreparation,
    VenuePreparationStage,
    VenuePreparationUpdated,
    VenueSearchCriteria,
    VenueSearchResponse,
    VenueStaffDashboard,
    VenueReactivateRequest,
    SuitabilityCode,
    VenueRequirements,
    Period,
    VenueSummary,
    VenueUpdateRequest,
    VenueUpdateResponse,
)

logger = logging.getLogger(__name__)

# What the venue-staff dashboard can discover. The response retains the active
# queue partitions below while also exposing resolved history for reference.
DASHBOARD_BOOKING_STATUSES = frozenset({"held", "re_review", "approved", "rejected", "expired"})

# Events a venue edit no longer affects: their bookings are not re-checked (CR-94 AC7).
FINISHED_EVENT_STATUSES = frozenset({"completed", "cancelled"})


def _suitability_requirements(criteria: VenueSearchCriteria, user: CurrentUser) -> VenueRequirements | None:
    """What a suitability check judges venues against (SCRUM-18), or None for a
    search that names no event.

    The requirements come from the stored event or space, never from the
    client's filters. Only the event's assigned coordinator, acting as
    coordinator, may ask (AC10): 403 for any other active role or a coordinator
    who isn't assigned, 404 for a missing event or space or a draft. A space
    states its own pax, layout, facilities and window (AC11); whatever it leaves
    out falls back to the event's.
    """
    if criteria.event_id is None and criteria.space_id is None:
        return None
    if user.role != "event_coordinator":
        raise InsufficientRoleError(["event_coordinator"])
    space = None
    if criteria.space_id is not None:
        event, space = events_service.assigned_space(str(criteria.space_id), user.id)
        if criteria.event_id is not None and event["id"] != str(criteria.event_id):
            raise events_service.EventNotFoundError()
    else:
        event = events_service.assigned_event(str(criteria.event_id), user.id)
    return _requirements_from(event, space)


def _requirements_from(event: dict, space: dict | None) -> VenueRequirements:
    """What a requested space (else the whole event) needs from a venue: the
    space's own pax, layout, facilities and window, with the event's as the
    fallback for whatever the space leaves out (AC11, QA3-23)."""
    space = space or {}
    starts_at = space.get("starts_at") or event.get("starts_at")
    ends_at = space.get("ends_at") or event.get("ends_at")
    attendance = space.get("expected_pax")
    return VenueRequirements(
        expected_attendance=attendance if attendance is not None else event.get("expected_attendance"),
        layout_preference=space.get("layout_preference") or event.get("layout_preference"),
        facilities_required=space.get("facilities_required") or event.get("facilities_required") or [],
        period=Period(starts_at=starts_at, ends_at=ends_at) if starts_at and ends_at else None,
        accessibility_needs=event.get("accessibility_needs"),
    )


# `public.request_venue_booking*` already refuses these two, atomically and in
# their own words (CR-97 AC10, SCRUM-64 AC2), so the check leaves them to it.
DATABASE_REFUSED_CODES = frozenset({SuitabilityCode.capacity, SuitabilityCode.inactive})


def _database_will_decide(event: dict, space: dict | None, replacing: bool) -> bool:
    """True when `public.request_venue_booking*` will refuse this request for
    its own reason, in its own words: the event isn't in Planning, or the space
    (else the event) already holds a venue. The suitability check then stays out
    of the way, so those refusals read as they always have (TC-BOOK-004, 005).
    A replacement is the exception: it may come from a confirmed event and has
    its own booking in the way, which the database sets aside."""
    if replacing:
        return False
    if event["status"] != "planning":
        return True
    space_id = space["id"] if space else None
    return any(
        row["status"] in OCCUPYING_STATUSES
        and (space_id is None or row.get("event_space_request_id") == space_id)
        for row in repository.list_booking_statuses([event["id"]])
    )


def _require_suitable(venue: VenueSummary, requirements: VenueRequirements, acknowledged: bool) -> None:
    """BR-R3 (SCRUM-18): refuse a request for an Unsuitable venue; one that is
    Suitable with warnings goes through only once the coordinator has
    acknowledged them. Enforced here, on the server, not by the dialog."""
    result = suitability.check(venue, requirements)
    hard = [r for r in result.reasons if r.severity == SuitabilitySeverity.unsuitable]
    if hard:
        ours = [r for r in hard if r.code not in DATABASE_REFUSED_CODES]
        if ours:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This venue is unsuitable for this event: " + " ".join(r.message for r in ours),
            )
        return  # only what the database function refuses itself: let it
    if result.reasons and not acknowledged:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This venue is suitable with warnings: " + " ".join(r.message for r in result.reasons)
            + " Acknowledge the warnings to request it.",
        )


def search_venues(criteria: VenueSearchCriteria, user: CurrentUser) -> VenueSearchResponse:
    """Evaluate every venue against the criteria (and the period, if given).
    When the search names an event or space, each result also carries its
    suitability for it, separate from availability (SCRUM-18)."""
    requirements = _suitability_requirements(criteria, user)
    venues = repository.list_venues()
    period = criteria.period
    # Fetch one envelope wide enough for every venue, then evaluate each venue
    # against its own defaults. Otherwise a setup-only clash is never fetched.
    envelope = search.buffered_period(
        period,
        max((venue.setup_minutes for venue in venues), default=0),
        max((venue.turnaround_minutes for venue in venues), default=0),
    ) if period is not None else None
    occupants = repository.list_occupants(envelope) if envelope is not None else {}

    evaluated = search.search(venues, criteria, occupants)
    if requirements is not None:
        for result in evaluated:
            result.suitability = suitability.check(result.venue, requirements)
    excluded_count = sum(1 for r in evaluated if r.excluded)
    results = evaluated if criteria.include_excluded else [r for r in evaluated if not r.excluded]

    return VenueSearchResponse(
        criteria=criteria,
        results=results,
        included_count=len(evaluated) - excluded_count,
        excluded_count=excluded_count,
    )


# SCRUM-54 AC1, AC9: who set or changed a block, and why, are Venue Staff's.
_BLOCK_MANAGEMENT_FIELDS = {
    "created_by": None, "created_at": None, "original_period": None,
    "changed_by": None, "changed_at": None, "change_note": None,
}


def get_venue(venue_id: str, *, manages_blocks: bool = True) -> VenueDetail:
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
        # Read as `VenueBlock` (SCRUM-54); a plain summary takes its defaults.
        # Anyone else reading the profile sees each block's period and reason only.
        upcoming_blocks=[
            VenueBlock.model_validate({**b.model_dump(), **({} if manages_blocks else _BLOCK_MANAGEMENT_FIELDS)})
            for b in repository.list_upcoming_blocks(venue_id, now)
        ],
        upcoming_bookings=bookings,
    )


def _to_impact_context(
    booking, contexts: dict[str, EventPlanningContext], spaces: dict[str, SpaceRequirements]
) -> BookingImpactContext:
    """A booking judged on its own space's requirements, each field falling
    back to the event's when the space leaves it empty (CR-94). A space's
    facility list is never null (the space a booking request creates
    automatically stores `{}`), so an empty list also means "didn't say"."""
    context = contexts.get(booking.event_id) or EventPlanningContext()
    space = spaces.get(booking.event_space_request_id) or SpaceRequirements()
    return BookingImpactContext(
        booking_id=booking.id,
        event_id=booking.event_id,
        period=booking.period,
        event_name=context.name,
        coordinator_id=context.coordinator_id,
        expected_attendance=space.expected_pax if space.expected_pax is not None else context.expected_attendance,
        layout_preference=space.layout_preference or context.layout_preference,
        facilities_required=space.facilities_required or context.facilities_required,
        accessibility_needs=context.accessibility_needs,
    )


def _snapshot(venue: VenueSummary) -> dict:
    """A JSON-safe dict of every editable field, for both the impact check's
    "after" state and the `venue_edit_history` row (VC-R3)."""
    return {
        "name": venue.name,
        "location": venue.location,
        "capacity": venue.capacity,
        "layouts": [{"layout": o.layout.value, "capacity_for_layout": o.capacity_for_layout} for o in venue.layouts],
        "facilities": [f.value for f in venue.facilities],
        "accessibility_features": [a.value for a in venue.accessibility_features],
        "opens_at": venue.opens_at.isoformat(),
        "closes_at": venue.closes_at.isoformat(),
        "description": venue.description,
        "setup_minutes": venue.setup_minutes,
        "turnaround_minutes": venue.turnaround_minutes,
        "emergency_access": venue.emergency_access,
        "restrictions": venue.restrictions,
        "is_active": venue.is_active,
        "inactive_reason": venue.inactive_reason.value if venue.inactive_reason else None,
        "inactive_note": venue.inactive_note,
    }


def _venue_staff_notifications(venue_name: str, actor_id: str, warnings: list[AffectedBooking]) -> list[dict]:
    """One notification per affected event for every venue staff member but
    the editor, who has just seen the warning (CR-94 AC5). Staff work as a
    pool (AUTH-R5), so all of them hear about it."""
    by_event: dict[str, list[AffectedBooking]] = {}
    for w in warnings:
        by_event.setdefault(w.event_id, []).append(w)
    messages = {}
    for event_id, affected in by_event.items():
        unsuitable = any(w.outcome == "unsuitable" for w in affected)
        reasons = list(dict.fromkeys(r for w in affected for r in w.reasons))
        state = "is now Unsuitable" if unsuitable else "needs a check"
        messages[event_id] = (
            f'Venue "{venue_name}" was edited and "{affected[0].event_name or "an event"}" {state}: ' + " ".join(reasons)
        )
    recipients = sorted(repository.list_venue_staff_ids() - {actor_id})
    return [
        {"recipient_id": recipient, "event_id": event_id, "message": message}
        for event_id, message in messages.items()
        for recipient in recipients
    ]


def _coordinator_message(venue_name: str, warning: AffectedBooking) -> str:
    return (f'Venue "{venue_name}" changed in a way that may affect '
            f'"{warning.event_name or "your event"}": ' + " ".join(warning.reasons))


def _unsuitable_flag(venue_name: str, warning: AffectedBooking, contexts: dict[str, EventPlanningContext]) -> dict:
    """What `update_venue` needs to flag one Unsuitable booking (CR-94 AC3,
    AC5). The reason names only the hard rules that make it Unsuitable; the
    coordinator's message names everything the edit broke. A booking that
    can't take the flag (already flagged, first flag wins, or in re-review)
    gets `unflagged_message`, the part-1 notification, instead."""
    hard = [d.message for d in warning.details if d.severity == SuitabilitySeverity.unsuitable]
    context = contexts.get(warning.event_id) or EventPlanningContext()
    return {
        "booking_id": warning.booking_id,
        "event_id": warning.event_id,
        "coordinator_id": context.coordinator_id,
        "reason": f'Venue "{venue_name}" was edited: ' + " ".join(hard),
        "message": (f'Venue "{venue_name}" was edited and your booking for '
                    f'"{warning.event_name or "your event"}" is flagged Unsuitable: ' + " ".join(warning.reasons)),
        "unflagged_message": _coordinator_message(venue_name, warning),
    }


def update_venue(venue_id: str, actor_id: str, body: VenueUpdateRequest) -> VenueUpdateResponse:
    """Save a venue edit (SCRUM-63).

    Compares the current attributes with the submitted ones against every
    upcoming occupying booking (VC-R2). If that newly breaks something a
    booking's event relies on and the caller has not yet set `confirm: true`,
    nothing is written — the warning comes back instead, so the SPA can show
    it before the staff member commits. Saving never un-books anything;
    resolution stays manual (VC-R2).
    """
    current = repository.get_venue(venue_id)
    if current is None:
        raise VenueNotFoundError()

    before = VenueSummary(
        id=current.id,
        name=current.name,
        location=current.location,
        capacity=current.capacity,
        layouts=current.layouts,
        facilities=current.facilities,
        accessibility_features=current.accessibility_features,
        opens_at=current.opens_at,
        closes_at=current.closes_at,
        is_active=current.is_active,
        description=current.description,
        setup_minutes=current.setup_minutes,
        turnaround_minutes=current.turnaround_minutes,
        emergency_access=current.emergency_access,
        restrictions=current.restrictions,
        inactive_reason=current.inactive_reason,
        inactive_note=current.inactive_note,
    )
    after = VenueSummary(
        id=current.id,
        name=body.name,
        location=body.location,
        capacity=body.capacity,
        layouts=body.layouts,
        facilities=body.facilities,
        accessibility_features=body.accessibility_features,
        opens_at=body.opens_at,
        closes_at=body.closes_at,
        is_active=current.is_active,
        description=body.description,
        setup_minutes=body.setup_minutes,
        turnaround_minutes=body.turnaround_minutes,
        emergency_access=body.emergency_access,
        restrictions=body.restrictions,
        inactive_reason=current.inactive_reason,
        inactive_note=current.inactive_note,
    )

    now = datetime.now(timezone.utc)
    bookings = repository.list_upcoming_bookings(venue_id, now)
    contexts_by_event = events_service.planning_context_by_id(b.event_id for b in bookings) if bookings else {}
    live = [
        b for b in bookings
        if (contexts_by_event.get(b.event_id) or EventPlanningContext()).status not in FINISHED_EVENT_STATUSES
    ]
    space_ids = {b.event_space_request_id for b in live if b.event_space_request_id}
    spaces = events_service.space_requirements_by_id(space_ids) if space_ids else {}
    impact_contexts = [_to_impact_context(b, contexts_by_event, spaces) for b in live]
    warnings = impact.affected_bookings(before, after, impact_contexts)

    if warnings and not body.confirm:
        return VenueUpdateResponse(saved=False, venue=None, warnings=warnings)

    flags = [_unsuitable_flag(after.name, w, contexts_by_event) for w in warnings if w.outcome == "unsuitable"]
    notifications = [
        {
            "recipient_id": contexts_by_event[w.event_id].coordinator_id,
            "event_id": w.event_id,
            "message": _coordinator_message(after.name, w),
        }
        for w in warnings
        if w.outcome != "unsuitable"
        and w.event_id in contexts_by_event and contexts_by_event[w.event_id].coordinator_id
    ]
    notifications += _venue_staff_notifications(after.name, actor_id, warnings) if warnings else []

    after_snapshot = _snapshot(after)
    updated = repository.update_venue(
        venue_id,
        actor_id,
        current.version,
        name=after.name,
        location=after.location,
        capacity=after.capacity,
        opens_at=after.opens_at,
        closes_at=after.closes_at,
        description=after.description,
        accessibility_features=after_snapshot["accessibility_features"],
        layouts=after_snapshot["layouts"],
        facilities=after_snapshot["facilities"],
        before=_snapshot(before),
        after=after_snapshot,
        notifications=notifications,
        flags=flags,
    )
    if updated is None:
        raise VenueConflictError()
    updated, flagged_event_ids = updated

    # The edit and its flags have committed together. A failed return leaves
    # that event where it is, but its booking is flagged, so the Safety
    # Officer cannot approve it: report the save, not a failure (as SCRUM-64).
    for event_id in flagged_event_ids:
        try:
            events_service.return_to_planning(event_id, reason_code="arrangement_flagged")
        except EventServiceUnavailableError:
            logger.warning("Venue %s edited, but event %s could not be returned to planning", venue_id, event_id)

    for booking in bookings:
        booking.event_name = (contexts_by_event.get(booking.event_id) or EventPlanningContext()).name
    venue = VenueDetail(
        **updated.model_dump(),
        # Read as `VenueBlock` (SCRUM-54); a plain summary takes its defaults.
        # Anyone else reading the profile sees each block's period and reason only.
        upcoming_blocks=[
            VenueBlock.model_validate({**b.model_dump(), **({} if manages_blocks else _BLOCK_MANAGEMENT_FIELDS)})
            for b in repository.list_upcoming_blocks(venue_id, now)
        ],
        upcoming_bookings=bookings,
    )
    return VenueUpdateResponse(saved=True, venue=venue, warnings=warnings)


def _summary(venue: VenueSummary, **changes) -> VenueSummary:
    """The catalogue fields of `venue` (a profile is also a summary), with
    `changes` applied: the before/after pair a history row records."""
    return VenueSummary(**{**VenueSummary.model_validate(venue.model_dump()).model_dump(), **changes})


def deactivate_venue(venue_id: str, actor_id: str, body: VenueDeactivateRequest) -> VenueDeactivateResponse:
    """Deactivate a venue (SCRUM-64 AC1, AC3).

    Without `confirm`, a venue with future held or approved bookings returns
    them instead of saving, so staff see who is affected first (the SCRUM-63
    pattern). Saving flags those bookings Affected and notifies their
    coordinators and organisers in one transaction; then any flagged event
    already in Safety review or Confirmed goes back to Planning (CR-104 AC10,
    CR-95 AC7).
    """
    current = repository.get_venue(venue_id)
    if current is None:
        raise VenueNotFoundError()
    if not current.is_active:
        raise VenueAlreadyInactiveError()
    if body.version != current.version:
        raise VenueConflictError()

    bookings = repository.list_flaggable_bookings(venue_id, datetime.now(timezone.utc))
    names = events_service.names_by_id(b.event_id for b in bookings) if bookings else {}
    affected = [
        FlaggableBooking(booking_id=b.id, event_id=b.event_id, event_name=names.get(b.event_id),
                         period=b.period, status=b.status, flag=b.flag)
        for b in bookings
    ]
    if affected and not body.confirm:
        return VenueDeactivateResponse(saved=False, affected=affected)

    label = INACTIVE_REASON_LABELS[body.reason]
    flag_reason = f"Venue deactivated: {label.lower()}" + (f" — {body.note}" if body.note else "")
    message = (f'Venue "{current.name}" has been deactivated ({label}). '
               "Your booking is flagged Affected and needs a replacement venue.")
    before = _summary(current)
    after = _summary(current, is_active=False, inactive_reason=body.reason, inactive_note=body.note)
    result = repository.deactivate_venue(
        venue_id, actor_id, current.version,
        reason=body.reason.value, note=body.note,
        before=_snapshot(before), after=_snapshot(after),
        flag_reason=flag_reason, message=message,
    )
    outcome = result["outcome"]
    if outcome == "venue_not_found":
        raise VenueNotFoundError()
    if outcome == "already_inactive":
        raise VenueAlreadyInactiveError()
    if outcome == "stale":
        raise VenueConflictError()

    # The deactivation has committed. A failed return leaves that event where
    # it is, but its booking is flagged, so the Safety Officer cannot approve
    # it and its coordinator has been told: report the save, not a failure.
    for event_id in result["event_ids"]:
        try:
            events_service.return_to_planning(event_id, reason_code="arrangement_flagged")
        except EventServiceUnavailableError:
            logger.warning("Venue %s deactivated, but event %s could not be returned to planning", venue_id, event_id)

    return VenueDeactivateResponse(saved=True, venue=get_venue(venue_id), affected=affected)


_BLOCK_REFUSALS = {
    "invalid_period": "End must be after start.",
    "ended": "End must be in the future.",
    "detail_too_long": "The detail can be at most 1000 characters.",
    "invalid_detail": "A detail is required when the reason is Other.",
}


def create_block(venue_id: str, actor_id: str, body: VenueBlockCreate) -> VenueBlockResponse:
    """Block a venue for a period (SCRUM-51 AC1, AC5, AC6, AC9).

    Without `confirm`, a block that overlaps held or approved bookings returns
    them instead of saving (CAL-R1, the deactivation pattern). Both lists come
    from the shared conflict check, never an overlap query of our own (AC7).
    Saving writes the block and its history row; the database trigger then
    flags the bookings Affected, records the block against each, and notifies
    the coordinators and organisers (CR-95, AC5, AC10-AC13). The events'
    statuses are left alone (CR-95 AC7), so nothing is returned to planning.
    """
    if repository.get_venue(venue_id) is None:
        raise VenueNotFoundError()

    period = Period(starts_at=body.starts_at, ends_at=body.ends_at)
    label = BLOCK_REASON_LABELS[body.reason]
    affected = repository.list_block_conflicts(venue_id, period)
    if affected and not body.confirm:
        return VenueBlockResponse(saved=False, affected=_name_affected(affected, label))

    result = repository.create_venue_block(
        venue_id, actor_id,
        period=period, reason=body.reason.value, notes=body.detail,
        history_after={"block": {"starts_at": body.starts_at.isoformat(), "ends_at": body.ends_at.isoformat(),
                                 "reason": body.reason.value, "notes": body.detail}},
    )
    outcome = result["outcome"]
    if outcome == "venue_not_found":
        raise VenueNotFoundError()
    if outcome in _BLOCK_REFUSALS:
        raise VenueBlockInvalidError(_BLOCK_REFUSALS[outcome])

    block = BlockSummary(id=result["block_id"], period=period, reason=body.reason.value, notes=body.detail)
    linked = repository.list_block_bookings(result["block_id"])
    return VenueBlockResponse(saved=True, block=block, affected=_name_affected(linked, label))


# SCRUM-54 AC2: a refusal about the block's state is a 409 (reload and look
# again); one about the new end or the note is a 422 (fix the input).
_BLOCK_CHANGE_CONFLICTS = {
    "ended": "This block has already ended, so it can't be changed.",
    "removed": "This block was removed, so it can't be changed.",
    "not_started": "This block hasn't started yet. Remove it instead.",
    "already_started": "Only a block that hasn't started can be removed. End it now instead.",
}
_BLOCK_CHANGE_INVALID = {
    "end_not_before_current": "The new end must be earlier than the current end. To block for longer, add a new block.",
    "end_not_after_start": "The new end must be after the block's start.",
    "end_in_past": "The new end must be in the future. To end the block now, choose End now.",
    "note_too_long": "The note can be at most 1000 characters.",
}


def change_block(venue_id: str, block_id: str, actor_id: str, body: VenueBlockChange) -> VenueBlockChangeResponse:
    """End a block now, shorten it, or remove one that hasn't started (SCRUM-54 AC2).

    `public.change_venue_block` decides under the venue lock, so a change can't
    race a booking request or approval (AC3). It keeps the row and records the
    original period, the new end, who, when and the note in the venue's history
    (AC4); it never clears a flag or touches a replacement (AC5, AC7). It does
    tell the coordinator of each freed booking that has a pending replacement.

    Then the bookings this block flagged that no block covers any more are
    listed for venue staff to restore (AC5, AC6), through CR-95's restore.
    Venue staff work as a pool (AUTH-R5), so any of them may change any block.
    """
    outcome = repository.change_venue_block(
        venue_id, block_id, actor_id, action=body.action.value, ends_at=body.ends_at, note=body.note,
    )["outcome"]
    if outcome == "venue_not_found":
        raise VenueNotFoundError()
    if outcome == "block_not_found":
        raise VenueBlockNotFoundError()
    if outcome in _BLOCK_CHANGE_CONFLICTS:
        raise VenueBlockChangeConflictError(_BLOCK_CHANGE_CONFLICTS[outcome])
    if outcome in _BLOCK_CHANGE_INVALID:
        raise VenueBlockInvalidError(_BLOCK_CHANGE_INVALID[outcome])

    block = repository.get_block(block_id)
    if block is None:
        raise VenueBlockNotFoundError()
    label = BLOCK_REASON_LABELS.get(block.reason, block.reason.replace("_", " "))
    restorable = repository.list_restorable_block_bookings(block_id)
    return VenueBlockChangeResponse(block=block, restorable=_name_affected(restorable, label))


def _name_affected(bookings, label: str):
    names = events_service.names_by_id(b.event_id for b in bookings) if bookings else {}
    return [b.model_copy(update={"event_name": names.get(b.event_id), "block_reason": label}) for b in bookings]


def reactivate_venue(venue_id: str, actor_id: str, body: VenueReactivateRequest) -> VenueDetail:
    """Make an inactive venue bookable again (SCRUM-64 AC4).

    Only the venue changes. Bookings flagged when it was deactivated stay
    flagged: their coordinators may already be arranging a replacement, and
    resolving a flag is theirs (CR-95), as with VC-R2.
    """
    current = repository.get_venue(venue_id)
    if current is None:
        raise VenueNotFoundError()
    if current.is_active:
        raise VenueAlreadyActiveError()
    if body.version != current.version:
        raise VenueConflictError()

    before = _summary(current)
    after = _summary(current, is_active=True, inactive_reason=None, inactive_note=None)
    outcome = repository.reactivate_venue(
        venue_id, actor_id, current.version, before=_snapshot(before), after=_snapshot(after)
    )
    if outcome == "venue_not_found":
        raise VenueNotFoundError()
    if outcome == "already_active":
        raise VenueAlreadyActiveError()
    if outcome == "stale":
        raise VenueConflictError()
    return get_venue(venue_id)


def _history_actor(row: dict) -> Editor | None:
    actor = row.get("actor")
    if isinstance(actor, list):
        actor = actor[0] if actor else None
    if not actor:
        return None
    return Editor(id=actor["id"], full_name=actor.get("full_name"))


def venue_history(venue_id: str) -> VenueEditHistoryResponse:
    """VC-R3: every saved edit, newest first, with its before/after snapshot
    and who made it."""
    if repository.get_venue(venue_id) is None:
        raise VenueNotFoundError()
    entries = [
        VenueEditHistoryEntry(
            id=row["id"],
            actor=_history_actor(row),
            before=row["before"],
            after=row["after"],
            at=row["created_at"],
        )
        for row in repository.list_edit_history(venue_id)
    ]
    return VenueEditHistoryResponse(entries=entries)


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
        booking_requests=sorted(bookings, key=lambda b: (b.period.starts_at, b.id)),
        # Soonest expiry first (CR-99): the hold nearest to expiring most needs
        # a decision. One already past its expiry is left out even before the
        # minute job marks it expired (AC5). Tie-broken on id for a stable order.
        pending_holds=sorted(
            (b for b in bookings if b.status == "held" and (b.expires_at is None or b.expires_at > now)),
            key=lambda b: (b.expires_at or b.period.starts_at, b.id),
        ),
        re_review_bookings=[b for b in bookings if b.status == "re_review"],
        # Soonest event first. One that has ended has nothing left to restore.
        affected_bookings=sorted(
            (
                b for b in bookings
                if b.flag == "affected" and b.status in ("held", "approved") and b.period.ends_at > now
            ),
            key=lambda b: (b.period.starts_at, b.id),
        ),
        blocks=repository.list_all_upcoming_blocks(now),
    )


# How a booking reads on the calendar (SCRUM-57 AC2). An Affected flag outranks
# the status: the booking still occupies the venue (AC8) but must not read as
# settled. Re-review is its own type, as on the profile (VC-R6).
_CALENDAR_BOOKING_TYPES = {"approved": "confirmed", "held": "tentative", "re_review": "re_review"}


def _calendar_booking(booking: CalendarBooking, event_name: str | None) -> CalendarEntry:
    return CalendarEntry(
        **booking.model_dump(),
        kind="booking",
        type="affected" if booking.flag == "affected" else _CALENDAR_BOOKING_TYPES[booking.status],
        event_name=event_name,
    )


def _calendar_block(block: VenueBlock) -> CalendarEntry:
    # A block has no setup or turnaround: it occupies exactly its period (AC5).
    return CalendarEntry(id=block.id, kind="block", type="blocked", period=block.period,
                         occupied_period=block.period, reason=block.reason, notes=block.notes,
                         created_by=block.created_by, created_at=block.created_at)


def venue_calendar(venue_id: str, period: Period, now: datetime | None = None) -> VenueCalendar:
    """What occupies one venue during `period`, typed for its calendar (SCRUM-57).

    Only what is current or upcoming is shown (AC3), so the period is asked
    about from `now` on: a view reaching into the past shows nothing that has
    ended. A hold past its expiry no longer occupies the venue, even before the
    minute job marks it expired (AC6). Every venue is offered to switch to,
    since venue staff are one pool (AUTH-R5, QA-44).
    """
    venue = repository.get_venue(venue_id)
    if venue is None:
        raise VenueNotFoundError()
    now = now or datetime.now(timezone.utc)
    entries: list[CalendarEntry] = []
    if period.ends_at > now:
        bookings, blocks = repository.list_calendar_occupants(
            venue_id, Period(starts_at=max(period.starts_at, now), ends_at=period.ends_at))
        bookings = [b for b in bookings if not (b.status == "held" and b.expires_at and b.expires_at <= now)]
        names = events_service.names_by_id(b.event_id for b in bookings) if bookings else {}
        entries = [_calendar_booking(b, names.get(b.event_id)) for b in bookings]
        entries += [_calendar_block(b) for b in blocks]
    return VenueCalendar(
        venue=CalendarVenue(id=venue.id, name=venue.name, is_active=venue.is_active),
        period=Period(starts_at=period.starts_at, ends_at=period.ends_at),
        entries=sorted(entries, key=lambda e: (e.occupied_period.starts_at, e.id)),
        venues=[CalendarVenue(id=v.id, name=v.name, is_active=v.is_active) for v in repository.list_venues()],
    )


def booking_statuses_by_event(event_ids: Iterable[str]) -> dict[str, list[str]]:
    """`{event_id: [booking status, ...]}` — the venues module's answer to "has this
    event's venue been settled?" (REQUIREMENTS §6.6: ready once a booking is
    `approved`). Events with no booking are absent. Used by the coordinator
    dashboard (SCRUM-72); the event arrangements panel (SCRUM-13) needs the same.
    """
    statuses: dict[str, list[str]] = {}
    for row in repository.list_booking_statuses(event_ids):
        statuses.setdefault(row["event_id"], []).append(row["status"])
    return statuses


def affected_event_ids(event_ids: Iterable[str]) -> set[str]:
    """The events with a held or approved booking flagged Affected (CR-95 AC3): the
    ones whose coordinator has to find an alternative venue. A released or
    cancelled booking no longer needs one, whatever flag it kept."""
    return {
        row["event_id"]
        for row in repository.list_booking_statuses(event_ids)
        if row.get("flag") == "affected" and row["status"] in ("held", "approved")
    }


def change_bookings(event_id: str) -> list[dict]:
    """Story 37: the event's occupying bookings, each with its venue's name and a
    `capacity_for(layout)` through the shared capacity rule, for the events module to
    plan an approved change with. A venue the catalogue doesn't return has no
    capacity to judge here, so nothing is flagged for it."""
    venues = {venue.id: venue for venue in repository.list_venues()}
    bookings = []
    for row in repository.list_change_bookings(event_id):
        venue = venues.get(row["venue_id"])
        bookings.append({
            "id": row["id"], "space_id": row.get("event_space_request_id"), "status": row["status"],
            "flag": row.get("flag"), "flag_reason": row.get("flag_reason"), "venue_id": row["venue_id"],
            "setup_minutes": row.get("setup_minutes") or 0, "turnaround_minutes": row.get("turnaround_minutes") or 0,
            "venue_name": venue.name if venue else "",
            "capacity_for": ((lambda layout, venue=venue: suitability.effective_capacity(venue, layout)) if venue
                             else (lambda layout: sys.maxsize)),
        })
    return bookings


def move_clash(booking_id: str, venue_id: str, setup_minutes: int, turnaround_minutes: int,
               starts_at: datetime, ends_at: datetime) -> str | None:
    """Story 37 preview: what a booking moved to `[starts_at, ends_at)` would clash with,
    in words, judged on its occupied window (setup and turnaround) at its venue and
    leaving the booking itself out (SCRUM-21 AC4). None when the window is free."""
    occupied = Period(starts_at=starts_at - timedelta(minutes=setup_minutes),
                      ends_at=ends_at + timedelta(minutes=turnaround_minutes))
    clash = repository.first_conflict(occupied, venue_id, booking_id)
    if clash is None:
        return None
    if clash["kind"] == "block":
        label = BLOCK_REASON_LABELS.get(clash.get("block_reason"), str(clash.get("block_reason")))
        return f"a venue block ({label})"
    return f'"{clash.get("event_name") or "another event"}"'


def booking_readiness_by_space(event_id: str) -> dict[str, list[BookingReadiness]]:
    """`{event_space_request_id: [BookingReadiness, ...]}` for one event (CR-97
    AC10): each of its event spaces' bookings, with status and open flag, so a
    flagged booking blocks its own space. Spaces with no booking are absent."""
    readiness: dict[str, list[BookingReadiness]] = {}
    for row in repository.list_booking_statuses([event_id]):
        if row.get("event_space_request_id"):
            flags = [row["flag"]] if row.get("flag") else []
            readiness.setdefault(row["event_space_request_id"], []).append(
                BookingReadiness(status=row["status"], flags=flags,
                                 needs_re_review=bool(row.get("needs_re_review_since")))
            )
    return readiness


def booking_readiness_by_event_space(event_ids: Iterable[str]) -> dict[str, dict[str, list[BookingReadiness]]]:
    """`{event_id: {event_space_request_id: [BookingReadiness, ...]}}`: what
    `booking_readiness_by_space` gives for one event, for many in one query
    (the coordinator dashboard, D35). Bookings without a space are left out."""
    readiness: dict[str, dict[str, list[BookingReadiness]]] = {}
    for row in repository.list_booking_statuses(event_ids):
        if row.get("event_space_request_id"):
            flags = [row["flag"]] if row.get("flag") else []
            readiness.setdefault(row["event_id"], {}).setdefault(row["event_space_request_id"], []).append(
                BookingReadiness(status=row["status"], flags=flags,
                                 needs_re_review=bool(row.get("needs_re_review_since")))
            )
    return readiness


def booking_readiness_by_event(event_ids: Iterable[str]) -> dict[str, list[BookingReadiness]]:
    """`{event_id: [BookingReadiness, ...]}`: each booking's status and its
    open flag, for the safety readiness check (82 AC10). A flagged booking
    (SCRUM-64, CR-95, CR-94) is not ready whatever its status. Events with no
    booking are absent."""
    readiness: dict[str, list[BookingReadiness]] = {}
    for row in repository.list_booking_statuses(event_ids):
        flags = [row["flag"]] if row.get("flag") else []
        readiness.setdefault(row["event_id"], []).append(BookingReadiness(
            status=row["status"], flags=flags, needs_re_review=bool(row.get("needs_re_review_since"))))
    return readiness


# What `public.request_venue_booking` refuses with, as the coordinator reads it
# (REQUIREMENTS §6.12, §6.14, §6.4). Wording of the first and fourth is the spec's.
BOOKING_REFUSALS = {
    "held_by_other": "Venue already held for this time by another event.",
    "blocked": "Venue blocked for this time.",
    "already_booked": "This event already has a venue booking.",
    "returned": "Requirements are still being amended.",
    "no_period": "This event has no start and end time to hold a venue for.",
    # SCRUM-64 AC2: a deactivated venue takes no new requests.
    "venue_inactive": "This venue is inactive.",
    # CR-95 AC4: only the event's own affected booking can be replaced.
    "replaced_booking_invalid": "That booking is not waiting for a replacement.",
}


# CR-95 AC4 / D52: both follow-up flags permit requesting another venue.
# Story 37 Q16, Q17: a clash with an approved change's new time, or attendance over capacity.
REPLACEABLE_FLAGS = ("affected", "safety_rejected", "conflict", "unsuitable")


def _prepare_replacement(replaces_id: str, event: dict, space_id: str | None) -> None:
    """Refuse before changing anything unless `replaces_id` is this event's (or
    space's) own flagged booking (Affected, Safety rejected, Conflict or Unsuitable) that is still
    held or approved, then return a
    Confirmed or Safety-review event to planning, which the booking functions
    require (CR-95 AC4, AC7). The coordinator has decided to replace the venue
    by asking, so the event stays in planning even if the venue they pick is
    taken; if the return fails, nothing has been requested."""
    row = repository.get_replaceable_booking(replaces_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
    if (
        row["event_id"] != event["id"]
        or row.get("event_space_request_id") != space_id
        or row.get("flag") not in REPLACEABLE_FLAGS
        or row["status"] not in ("held", "approved")
    ):
        raise BookingConflictError(BOOKING_REFUSALS["replaced_booking_invalid"], None)
    if event["status"] in ("safety_review", "confirmed"):
        events_service.return_to_planning(event["id"], reason_code="arrangement_flagged")


def request_booking(body: VenueBookingCreate, coordinator_id: str) -> VenueBooking:
    """Hold a venue for a planning event (SCRUM-19, REQUIREMENTS §6.12).

    The relationship check runs here (404 / 403); everything that depends on
    the state of other bookings is decided by the database function under its
    locks, so two coordinators racing for one slot can't both win (QA2-23).
    """
    venue_id = str(body.venue_id)
    if body.event_space_request_id:
        event, space = events_service.assigned_space(str(body.event_space_request_id), coordinator_id)
    else:
        event = events_service.assigned_event(str(body.event_id), coordinator_id)
        # CR-97: an event-only request books the event's first space.
        space = event["spaces"][0] if event.get("spaces") else None
    event_id = event["id"]
    space_id = space["id"] if space else None
    if not _database_will_decide(event, space, bool(body.replaces_booking_id)):
        venue = repository.get_venue(venue_id)
        if venue is None:
            raise VenueNotFoundError()
        _require_suitable(venue, _requirements_from(event, space), body.acknowledge_warnings)
    notify_message = f'A venue booking was requested for "{event["name"]}".'
    replaces_id = str(body.replaces_booking_id) if body.replaces_booking_id else None
    extra = {"replaces_booking_id": replaces_id} if replaces_id else {}
    if replaces_id:
        _prepare_replacement(replaces_id, event, space_id)
    if space_id:
        result = repository.request_booking_for_space(
            space_id, venue_id, coordinator_id, body.note, notify_message=notify_message, **extra,
        )
    else:
        result = repository.request_booking(
            event_id, venue_id, coordinator_id, body.note, notify_message=notify_message, **extra,
        )
    outcome = result["outcome"]
    if outcome == "over_capacity":
        # CR-97 AC10: the function refused on the space's expected pax; say by how much.
        venue = repository.get_venue(venue_id)
        seats = search.effective_capacity(venue, space.get("layout_preference"))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{venue.name} seats {seats}; this space needs {space['expected_pax']}.",
        )
    if outcome in BOOKING_REFUSALS:
        # SCRUM-21 AC2: an overlap or a block comes with what is in the way.
        conflict = result.get("conflict")
        raise BookingConflictError(
            BOOKING_REFUSALS[outcome],
            BookingConflict.model_validate(conflict).model_dump(mode="json") if conflict else None,
        )
    if outcome == "not_planning":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot request a venue for an event that is {event['status'].replace('_', ' ')}.",
        )
    if outcome == "venue_not_found":
        raise VenueNotFoundError()
    if outcome == "not_assigned":
        raise NotAssignedCoordinatorError()
    if outcome == "event_not_found":
        raise events_service.EventNotFoundError()
    return VenueBooking(
        id=result["booking_id"],
        event_id=event_id,
        event_space_request_id=space_id,
        venue_id=venue_id,
        status="held",
        note=body.note,
    )


# What `public.set_venue_hold_expiry` refuses with (CR-99 AC1, AC2, AC4).
HOLD_EXPIRY_REFUSALS = {
    "hold_expired": (status.HTTP_409_CONFLICT, "This hold has already expired."),
    "not_held": (status.HTTP_409_CONFLICT, "Only a held booking has an expiry to change."),
    "not_in_future": (status.HTTP_422_UNPROCESSABLE_ENTITY, "The new expiry must be in the future."),
    "after_event_start": (status.HTTP_422_UNPROCESSABLE_ENTITY, "The new expiry can't be after the event starts."),
}


def change_hold_expiry(booking_id: str, actor_id: str, expires_at: datetime) -> HoldExpiry:
    """Change or extend a hold's expiry (CR-99 AC2). Venue staff work as a pool
    (AUTH-R5), so any of them may change any hold; the bounds, the history row
    and the reset of the 24-hour warning are the database function's."""
    result = repository.set_hold_expiry(booking_id, actor_id, expires_at)
    outcome = result["outcome"]
    if outcome == "booking_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
    if outcome in HOLD_EXPIRY_REFUSALS:
        code, detail = HOLD_EXPIRY_REFUSALS[outcome]
        raise HTTPException(status_code=code, detail=detail)
    return HoldExpiry(id=booking_id, status="held", expires_at=result["expires_at"])


def _flag_fields(row: dict) -> dict:
    """What marks a booking as affected, or as the replacement for one (CR-95)."""
    return {
        "flag": row.get("flag"),
        "flag_reason": row.get("flag_reason"),
        "replaces_booking_id": row.get("replaces_booking_id"),
    }


def active_booking_for_event(event_id: str) -> dict | None:
    """`{id, venue_id, venue_name, status, expires_at}` for the venue the event
    holds or has booked, or else its latest expired hold (CR-99 AC7), or None
    (SCRUM-19). The event page reads it to show the hold."""
    row = repository.get_active_booking(event_id)
    if row is None:
        return None
    return {
        "id": row["id"],
        "event_space_request_id": row.get("event_space_request_id"),
        "venue_id": row["venue_id"],
        "venue_name": (row.get("venues") or {}).get("name"),
        "status": row["status"],
        "expires_at": row.get("expires_at"),
        "preparation": row.get("preparation"),
        **_flag_fields(row),
    }


def event_booking_ids(event_id: str) -> set[str]:
    """Every booking id, including released bookings, for officer validation."""
    return {row["id"] for row in repository.list_event_booking_ids(event_id)}


def event_bookings_with_venues(event_id: str) -> list[dict]:
    """Active arrangements and venue facts for the safety review."""
    items = []
    for row in repository.list_event_bookings_with_venues(event_id):
        venue = row.get("venues") or {}
        items.append(dict(booking_id=row["id"], venue_id=row["venue_id"], booking_status=row["status"],
                          venue_name=venue.get("name"), capacity=venue.get("capacity"),
                          layouts=[layout["layout"] for layout in venue.get("venue_layouts") or []],
                          accessibility_features=venue.get("accessibility_features") or [],
                          emergency_access=venue.get("emergency_access"), restrictions=venue.get("restrictions")))
    return items


def _booking_detail(booking: dict) -> VenueBookingDetail:
    event_id = booking["event_id"]
    context = events_service.planning_context_by_id([event_id]).get(event_id) or EventPlanningContext()
    decision = None
    if booking["status"] == "rejected" and booking.get("decision_reason") and booking.get("decided_at"):
        decision = BookingDecision(reason=booking["decision_reason"], suggestion=booking.get("suggestion_note"),
                                   decided_by_name=booking.get("decided_by_name"), decided_at=booking["decided_at"])
    history = repository.list_booking_history(booking["id"])
    return VenueBookingDetail(
        id=booking["id"], status=booking["status"], venue_id=booking["venue_id"],
        venue_name=booking.get("venue_name"), period=booking["period"], request_note=booking.get("request_note"),
        requested_at=booking["requested_at"], requested_by_name=booking.get("requested_by_name"),
        flag=booking.get("flag"), flag_reason=booking.get("flag_reason"),
        event=BookingEventRequirements(
            id=event_id, name=context.name, status=context.status,
            expected_attendance=context.expected_attendance, layout_preference=context.layout_preference,
            facilities_required=context.facilities_required, accessibility_needs=context.accessibility_needs,
        ),
        decision=decision,
        preparation=booking_preparation(booking, internal=True) if booking.get("preparation") else None,
        history=[BookingHistoryEntry(**entry) for entry in history],
        re_review=_re_review_context(booking, history) if booking["status"] == "re_review" else None,
    )


def _re_review_context(booking: dict, history: list[dict]) -> ReReviewContext:
    """Story 37 Q21: the latest approved change, the latest move, and the note the
    coordinator sent it with (the latest send's reason)."""
    sends = [entry for entry in history if entry["action"] == "sent_for_re_review"]
    move = repository.get_last_move(booking["id"]) or {}
    return ReReviewContext(
        changes=events_service.latest_approved_change(booking["event_id"]),
        note=sends[-1]["reason"] if sends else None,
        moved_from=move.get("old_period"), moved_to=move.get("new_period"),
    )


def booking_detail(booking_id: str, user_id: str, role: str) -> VenueBookingDetail:
    """One booking request with its event's requirements (SCRUM-38 AC1).

    Venue staff read every booking: they work as a pool and staff-to-venue
    allocation is not tracked (AUTH-R5). A coordinator reads only bookings on
    events assigned to them (404 / 403 from the events module), so they see
    the reason for a rejection on the booking as well as on the event (AC6).
    """
    booking = repository.get_booking(booking_id)
    if booking is None:
        raise BookingNotFoundError()
    if role == "event_coordinator":
        events_service.assigned_event(booking["event_id"], user_id)
    return _booking_detail(booking)


# How a booking that is no longer held reads to venue staff (AC9).
_NOT_HELD_LABELS = {
    "approved": "approved",
    "rejected": "already rejected",
    "cancelled": "cancelled",
    "released": "released",
    "re_review": "under re-review",
}


# What `public.restore_affected_booking` refuses with, as venue staff read it (CR-95 AC9).
RESTORE_REFUSALS = {
    "not_affected": "This booking isn't waiting on an unavailable venue.",
    "replacement_approved": "A replacement has already been approved, so the original can't be restored.",
    "venue_inactive": "This venue is inactive, so the booking can't be restored.",
    "still_blocked": "The venue is still blocked for part of this booking's time.",
    "held_by_other": "The venue is taken for part of this booking's time.",
    "hold_expired": "This hold has expired, so it can't be restored.",
}


def restore_booking(booking_id: str, actor_id: str) -> VenueBookingDetail:
    """Venue staff confirm an affected booking is restored (CR-95 AC9, QA3-9).

    Whether the venue is free for the booking's full occupied window, and what
    restoring changes (flag cleared, pending replacement cancelled, history,
    notices), is the database function's, under a lock on the booking row.
    Venue staff work as a pool (AUTH-R5), so any of them may restore any booking.
    """
    outcome = repository.restore_affected_booking(booking_id, actor_id)["outcome"]
    if outcome == "booking_not_found":
        raise BookingNotFoundError()
    if outcome in RESTORE_REFUSALS:
        raise BookingDecisionConflictError(RESTORE_REFUSALS[outcome])
    return _booking_detail(repository.get_booking(booking_id))


def reject_booking(booking_id: str, actor_id: str, body: VenueBookingReject) -> VenueBookingDetail:
    """Venue staff reject a held booking (SCRUM-38, REQUIREMENTS §6.13).

    Whether it is still held is decided by `public.reject_venue_booking` under
    a lock on the booking row, so a rejection racing an approval (SCRUM-36) or
    the expiry job (CR-99) is refused, never overwritten (AC10). The event stays
    in planning and its other bookings are untouched (AC7, AC8, BA-R4).
    """
    booking = repository.get_booking(booking_id)
    if booking is None:
        raise BookingNotFoundError()
    event_name = events_service.names_by_id([booking["event_id"]]).get(booking["event_id"], "your event")
    venue_name = booking.get("venue_name") or "the venue"
    # Story 37: after a re-review the coordinator needs another venue, so the notice says so.
    message = (f'Venue staff rejected {venue_name} for "{event_name}" after its change. Find another venue.'
               if booking["status"] == "re_review"
               else f'Venue staff rejected the booking of {venue_name} for "{event_name}".')
    result = repository.reject_booking(
        booking_id, actor_id, body.reason, body.suggestion,
        # No reason in the notification: the coordinator reads it on the page.
        notify_message=message,
    )
    outcome = result["outcome"]
    if outcome == "booking_not_found":
        raise BookingNotFoundError()
    if outcome == "hold_expired":
        raise BookingDecisionConflictError("This hold has expired, so it can't be rejected.")
    if outcome == "not_held":
        label = _NOT_HELD_LABELS.get(result["from_status"], str(result["from_status"]).replace("_", " "))
        raise BookingDecisionConflictError(f"Only a held booking can be rejected. This one is {label}.")
    if outcome == "invalid_reason":
        raise BookingDecisionTextError("reason")
    if outcome == "invalid_suggestion":
        raise BookingDecisionTextError("suggestion")
    return _booking_detail(repository.get_booking(booking_id))


def approve_booking(booking_id: str, actor_id: str) -> VenueBookingDetail:
    """Venue staff approve a held booking (SCRUM-36, REQUIREMENTS §6.13).

    `public.approve_venue_booking` decides under the same lock on the booking
    row as rejection and the expiry job, so only one of them wins (AC9). It
    also refuses a hold that a venue block now overlaps (AC3) or whose venue
    has been deactivated (AC4). Only this booking changes (AC7).
    """
    booking = repository.get_booking(booking_id)
    if booking is None:
        raise BookingNotFoundError()
    event_name = events_service.names_by_id([booking["event_id"]]).get(booking["event_id"], "your event")
    venue_name = booking.get("venue_name") or "the venue"
    result = repository.approve_booking(
        booking_id, actor_id,
        notify_message=(f'Venue staff re-approved {venue_name} for "{event_name}" after its change.'
                        if booking["status"] == "re_review"
                        else f'Venue staff approved the booking of {venue_name} for "{event_name}".'),
    )
    outcome = result["outcome"]
    if outcome == "booking_not_found":
        raise BookingNotFoundError()
    if outcome == "hold_expired":
        raise BookingDecisionConflictError("This hold has expired, so it can't be approved.")
    if outcome == "not_held":
        label = _NOT_HELD_LABELS.get(result["from_status"], str(result["from_status"]).replace("_", " "))
        raise BookingDecisionConflictError(f"Only a held booking can be approved. This one is {label}.")
    if outcome == "venue_blocked":
        raise BookingDecisionConflictError("Venue blocked for this time.")
    if outcome == "venue_inactive":
        raise BookingDecisionConflictError("This venue is inactive, so the booking can't be approved.")
    return _booking_detail(repository.get_booking(booking_id))


# What `public.cancel_venue_booking` refuses with, as the coordinator reads it (SCRUM-85).
CANCEL_REFUSALS = {
    "not_cancellable": "Only a Held or Approved booking can be cancelled.",
    "hold_expired": "This hold has expired, so it can't be cancelled.",
    "event_closed": "A booking can't be cancelled once its event has started, ended or been cancelled.",
}


def cancel_booking(booking_id: str, coordinator_id: str) -> VenueBookingDetail:
    """The assigned coordinator cancels one of their event's bookings (SCRUM-85, BR-R5).

    `public.cancel_venue_booking` decides under the event's and the booking's locks,
    so a cancel racing an approval, restore or expiry, or a second cancel, saves
    one outcome (AC9). In the same transaction it frees the slot (AC1), records
    who and when (AC6), tells every venue staff account (AC1) and returns a Safety
    review, Confirmed or Preparation event to Planning (AC4, AC8). The event's
    other bookings are untouched (AC7).
    """
    booking = repository.get_booking(booking_id)
    if booking is None:
        raise BookingNotFoundError()
    event_name = events_service.names_by_id([booking["event_id"]]).get(booking["event_id"], "your event")
    venue_name = booking.get("venue_name") or "the venue"
    try:
        result = repository.cancel_booking(
            booking_id, coordinator_id,
            staff_message=(f'The coordinator cancelled the booking of {venue_name} for "{event_name}". '
                           "The venue is free for that time again."),
            return_message=events_service.return_to_planning_message(event_name, "booking_cancelled"),
        )
    except (HTTPError, APIError) as exc:
        raise VenueServiceUnavailableError() from exc
    outcome = result["outcome"]
    if outcome == "booking_not_found":
        raise BookingNotFoundError()
    if outcome == "not_assigned":
        raise NotAssignedCoordinatorError()
    if outcome in CANCEL_REFUSALS:
        raise BookingDecisionConflictError(CANCEL_REFUSALS[outcome])
    return _booking_detail(repository.get_booking(booking_id))


def rejected_bookings_for_event(event_id: str) -> list[dict]:
    """The event's rejected bookings with venue staff's reason and suggestion
    (SCRUM-38 AC6). Callers must already have checked the reader is the
    assigned coordinator: the organiser never sees these (AUTH-R2)."""
    return repository.list_rejected_bookings(event_id)


def active_bookings_for_event(event_id: str) -> list[dict]:
    """Each space's booking for the event page (CR-97 AC5): its occupying booking,
    or else its latest expired hold so the page can say it ran out (CR-99 AC7)."""
    shown: dict[str, dict] = {}
    for row in repository.list_active_bookings(event_id):  # oldest first
        # An affected booking and the replacement asked for beside it (CR-95)
        # are both shown: the coordinator works from the one and tracks the other.
        own_row = row.get("flag") or row.get("replaces_booking_id")
        key = row["id"] if own_row else row.get("event_space_request_id") or row["id"]
        current = shown.get(key)
        if current is None or current["status"] == "expired" or row["status"] in OCCUPYING_STATUSES:
            shown[key] = row
    return [
        {
            "id": row["id"],
            "event_id": row.get("event_id"),
            "event_space_request_id": row.get("event_space_request_id"),
            "venue_id": row["venue_id"],
            "venue_name": (row.get("venues") or {}).get("name"),
            "status": row["status"],
            "expires_at": row.get("expires_at"),
            **_flag_fields(row),
            # CR-111: where the venue is, for the organiser's list; absent when it has none recorded.
            **({"venue_location": row["venues"]["location"]} if (row.get("venues") or {}).get("location") else {}),
            # Story 37 Q20: why an approved change marked it, so it can be sent for re-review.
            **({"needs_re_review_reason": row["needs_re_review_reason"]} if row.get("needs_re_review_reason") else {}),
            # CR-109 AC4: each venue's progress; the events module strips the note for the organiser.
            **({"preparation": row["preparation"]} if row.get("preparation") else {}),
        }
        for row in shown.values()
    ]


MARK_REVISED_REFUSALS = {
    "replacement_pending": "A replacement venue has been requested for this booking.",
    "not_safety_rejected": "This booking isn't flagged Safety rejected.",
    "not_planning": "A booking can be marked revised only while the event is in Planning.",
}


def mark_safety_revision(booking_id: str, actor_id: str, note: str) -> VenueBookingDetail:
    """CR-104 AC3/AC4 [Team decision]: assigned coordinator marks revised.

    The RPC checks assignment and Planning under locks before clearing the flag.
    """
    outcome = repository.mark_safety_revision(booking_id, actor_id, note)
    if outcome == "note_required":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A note is required.")
    if outcome == "booking_not_found":
        raise BookingNotFoundError()
    if outcome == "not_assigned":
        raise NotAssignedCoordinatorError()
    if outcome in MARK_REVISED_REFUSALS:
        raise BookingDecisionConflictError(MARK_REVISED_REFUSALS[outcome])
    return _booking_detail(repository.get_booking(booking_id))


NOT_PLANNING_MESSAGE = "Arrangements can be sent for re-review only while the event is in Planning."


def send_booking_for_re_review(booking_id: str, coordinator_id: str, note: str | None) -> None:
    """Story 37 AC6, Q20: the assigned coordinator sends a booking an approved change
    marked Needs re-review to venue staff. The RPC checks assignment, Planning and the
    marker under the event's lock; the booking keeps its hold."""
    booking = repository.get_booking(booking_id)
    if booking is None:
        raise BookingNotFoundError()
    name = events_service.names_by_id([booking["event_id"]]).get(booking["event_id"], "An event")
    message = f'"{name}" changed: {booking["venue_name"]} needs re-review.'
    if note:
        message += f" Note: {note}"
    outcome = repository.send_booking_for_re_review(booking_id, coordinator_id, note, message)["outcome"]
    if outcome == "not_found":
        raise BookingNotFoundError()
    if outcome == "not_assigned":
        raise NotAssignedCoordinatorError()
    if outcome == "status_changed":
        raise BookingDecisionConflictError(NOT_PLANNING_MESSAGE)
    if outcome != "ok":
        raise BookingDecisionConflictError("This booking doesn't need re-review.")


def event_booking_history(event_id: str) -> list[dict]:
    """Story 62 AC5: every booking's history on the event, for its change history."""
    return repository.list_event_booking_history(event_id)


def booking_preparation(row: dict, *, internal: bool) -> VenuePreparation | VenuePreparationStage:
    """CR-109 AC4: a booking's recorded progress; the note and who made it only when `internal`."""
    recorded = row.get("preparation") or {}
    stage = recorded.get("stage") or "not_started"
    updated_at = recorded.get("updated_at")
    if not internal:
        return VenuePreparationStage(stage=stage, updated_at=updated_at)
    updater = recorded.get("updater") or {}
    if isinstance(updater, list):
        updater = updater[0] if updater else {}
    return VenuePreparation(
        stage=stage,
        updated_at=updated_at,
        note=recorded.get("note"),
        updated_by_name=updater.get("full_name"),
    )


def set_venue_preparation(
    booking_id: str, actor_id: str, stage: str, note: str | None
) -> VenuePreparationUpdated:
    """CR-109 AC1-AC3, AC5: update one booking through the atomic RPC."""
    row = repository.set_venue_preparation(booking_id, actor_id, stage, note)
    outcome = row.get("outcome")
    if outcome == "booking_not_found" or outcome == "event_not_found":
        raise BookingNotFoundError()
    if outcome == "not_confirmed":
        raise BookingDecisionConflictError(
            "Venue preparation opens once the Safety Officer has confirmed the event."
        )
    if outcome == "booking_not_active":
        raise BookingDecisionConflictError("Only an approved booking can record venue preparation.")
    if outcome != "ok":
        raise RuntimeError(f"venue preparation function returned {outcome!r}")
    return VenuePreparationUpdated(
        stage=row["stage"],
        note=row.get("note"),
        updated_at=row.get("updated_at"),
        updated_by_name=row.get("updated_by_name"),
        event_status=row["event_status"],
    )


# A booking in one of these still holds or has booked its venue.
_ACTIVE_BOOKING_STATUSES = {"held", "approved", "re_review"}


def event_venue_edits(event_id: str) -> list[dict]:
    """Story 62 AC5, REQUIREMENTS §9 item 113 [Assumption]: the edits to each venue the
    event held or booked, made while it did: from the booking's creation until it ended
    (its last change, for a booking no longer active), or until now."""
    edits = {}
    for booking in repository.list_event_bookings_for_history(event_id):
        start = datetime.fromisoformat(booking["created_at"])
        end = (None if booking["status"] in _ACTIVE_BOOKING_STATUSES
               else datetime.fromisoformat(booking["updated_at"]))
        for row in repository.list_edit_history(booking["venue_id"]):
            at = datetime.fromisoformat(row["created_at"])
            if at >= start and (end is None or at <= end):
                # Two bookings of the same venue can share an edit; it appears once.
                edits[row["id"]] = {"id": row["id"], "venue_name": booking["venue_name"],
                                    "old_value": row["before"], "new_value": row["after"],
                                    "actor": row.get("actor"), "at": row["created_at"]}
    return list(edits.values())


def booking_venue_names(booking_ids: list[str]) -> dict[str, str | None]:
    return repository.booking_venue_names(booking_ids)


def venue_names(venue_ids: list[str]) -> dict[str, str | None]:
    return repository.venue_names(venue_ids)


def safety_revisions(booking_ids: list[str]) -> list[dict]:
    return repository.safety_revisions(booking_ids)
