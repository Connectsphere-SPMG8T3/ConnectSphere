"""Venue module use cases: search the catalogue, read one venue, edit one, request a booking."""

import logging
from collections.abc import Iterable
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.core.exceptions import (
    BookingConflictError,
    BookingDecisionConflictError,
    BookingDecisionTextError,
    BookingNotFoundError,
    EventServiceUnavailableError,
    NotAssignedCoordinatorError,
    VenueAlreadyActiveError,
    VenueAlreadyInactiveError,
    VenueBlockInvalidError,
    VenueConflictError,
    VenueNotFoundError,
)
from app.modules.events import service as events_service
from app.modules.events.schemas import BookingReadiness, EventPlanningContext, SpaceRequirements
from app.modules.venues import impact, repository, search
from app.modules.venues.search import OCCUPYING_STATUSES
from app.modules.venues.schemas import (
    BLOCK_REASON_LABELS,
    INACTIVE_REASON_LABELS,
    AffectedBooking,
    BlockSummary,
    BookingConflict,
    BookingDecision,
    BookingEventRequirements,
    BookingHistoryEntry,
    BookingImpactContext,
    Editor,
    FlaggableBooking,
    HoldExpiry,
    SuitabilitySeverity,
    VenueBooking,
    VenueBookingCreate,
    VenueBookingDetail,
    VenueBookingReject,
    VenueBlockCreate,
    VenueBlockResponse,
    VenueDeactivateRequest,
    VenueDeactivateResponse,
    VenueDetail,
    VenueEditHistoryEntry,
    VenueEditHistoryResponse,
    VenueSearchCriteria,
    VenueSearchResponse,
    VenueStaffDashboard,
    VenueReactivateRequest,
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
        upcoming_blocks=repository.list_upcoming_blocks(venue_id, now),
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
                         period=b.period, status=b.status)
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


def booking_readiness_by_space(event_id: str) -> dict[str, list[BookingReadiness]]:
    """`{event_space_request_id: [BookingReadiness, ...]}` for one event (CR-97
    AC10): each of its event spaces' bookings, with status and open flag, so a
    flagged booking blocks its own space. Spaces with no booking are absent."""
    readiness: dict[str, list[BookingReadiness]] = {}
    for row in repository.list_booking_statuses([event_id]):
        if row.get("event_space_request_id"):
            flags = [row["flag"]] if row.get("flag") else []
            readiness.setdefault(row["event_space_request_id"], []).append(
                BookingReadiness(status=row["status"], flags=flags)
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
        readiness.setdefault(row["event_id"], []).append(BookingReadiness(status=row["status"], flags=flags))
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


def _prepare_replacement(replaces_id: str, event: dict, space_id: str | None) -> None:
    """Refuse before changing anything unless `replaces_id` is this event's (or
    space's) own affected booking that is still held or approved, then return a
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
        or row.get("flag") != "affected"
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
                          accessibility_features=venue.get("accessibility_features") or []))
    return items


def _booking_detail(booking: dict) -> VenueBookingDetail:
    event_id = booking["event_id"]
    context = events_service.planning_context_by_id([event_id]).get(event_id) or EventPlanningContext()
    decision = None
    if booking["status"] == "rejected" and booking.get("decision_reason") and booking.get("decided_at"):
        decision = BookingDecision(reason=booking["decision_reason"], suggestion=booking.get("suggestion_note"),
                                   decided_by_name=booking.get("decided_by_name"), decided_at=booking["decided_at"])
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
        history=[BookingHistoryEntry(**entry) for entry in repository.list_booking_history(booking["id"])],
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
    result = repository.reject_booking(
        booking_id, actor_id, body.reason, body.suggestion,
        # No reason in the notification: the coordinator reads it on the page.
        notify_message=f'Venue staff rejected the booking of {venue_name} for "{event_name}".',
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
        notify_message=f'Venue staff approved the booking of {venue_name} for "{event_name}".',
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
        }
        for row in shown.values()
    ]


MARK_REVISED_REFUSALS = {
    "not_safety_rejected": "This booking isn't flagged Safety rejected.",
    "not_planning": "A booking can be marked revised only while the event is in Planning.",
}


def mark_safety_revision(booking_id: str, actor_id: str) -> VenueBookingDetail:
    """CR-104 AC3/AC4 [Team decision]: assigned coordinator marks revised.

    The RPC checks assignment and Planning under locks before clearing the flag.
    """
    outcome = repository.mark_safety_revision(booking_id, actor_id)
    if outcome == "booking_not_found":
        raise BookingNotFoundError()
    if outcome == "not_assigned":
        raise NotAssignedCoordinatorError()
    if outcome in MARK_REVISED_REFUSALS:
        raise BookingDecisionConflictError(MARK_REVISED_REFUSALS[outcome])
    return _booking_detail(repository.get_booking(booking_id))
