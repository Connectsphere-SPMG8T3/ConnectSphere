from collections.abc import Iterable
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status

from app.core.exceptions import NotAssignedCoordinatorError
# Module imports, not names: `venues.service` imports this module too, and a
# module reference resolves at call time, so the cycle is harmless.
from app.modules.equipment import service as equipment_service
from app.modules.events import lifecycle, repository
from app.modules.venues import service as venues_service
from app.modules.events.schemas import (
    AmendmentRequest,
    CoordinatorActionItem,
    CoordinatorActionKind,
    CoordinatorActiveEvent,
    CoordinatorDashboard,
    EventCreateRequest,
    EventHistoryEntry,
    EventHistoryResponse,
    EventResponse,
    EventResubmitRequest,
    EventReturnRequest,
    EventStatus,
    EventUpdateRequest,
    Readiness,
    ReadinessState,
)

DEFAULT_EVENT_TIMEZONE = "Asia/Singapore"

# The statuses an assigned coordinator still has work in (SCRUM-72 AC2). Drafts
# are private to their organiser (DR-R2) and terminal statuses aren't active.
ACTIVE_COORDINATOR_STATUSES = ("under_review", "returned", "planning", "confirmed")

# [Assumption] REQUIREMENTS §6.21.1: the awaiting-assignment alert (AS-R5) counts
# every non-draft, non-terminal event with no coordinator. AS-R5 names only
# `submitted`, but until SCRUM-12 assigns on submission, unassigned events sit in
# `under_review` or later.
UNASSIGNED_STATUSES = ("submitted", *ACTIVE_COORDINATOR_STATUSES)


class EventNotFoundError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")


class EventConflictError(HTTPException):
    def __init__(self, detail: str = "The event was changed by another request.") -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


def names_by_id(event_ids: Iterable[str]) -> dict[str, str]:
    """`{event_id: name}` for the ids given — the events module's answer to
    "what is this event called?" for modules that only hold an `event_id`.

    No ownership check: the callers are already behind their own role and
    relationship guards, and an event's name is the least of what they are
    cleared to see. `venue_bookings.event_id` has no foreign key to `events`
    (BUILD_LOG §4.9), so a PostgREST embed is not available and a caller that
    needs names asks here rather than reading another module's table.
    """
    return repository.list_event_names(event_ids)


def _to_response(row: dict) -> EventResponse:
    return EventResponse(**row)


def _with_amendment(row: dict) -> EventResponse:
    """A single event, carrying its open amendment while it is returned (SCRUM-33)."""
    response = _to_response(row)
    if response.status == EventStatus.returned:
        amendment = repository.get_open_amendment(row["id"])
        if amendment:
            response.amendment = AmendmentRequest(**amendment)
    return response


def _owned_event(event_id: str, organiser_id: str) -> dict:
    row = repository.get_event(event_id)
    if not row or row.get("organiser_id") != organiser_id:
        raise EventNotFoundError()
    return row


STALE_EVENT_MESSAGE = "This event was updated by someone else. Reload."


def _assigned_event(event_id: str, coordinator_id: str) -> dict:
    """The event, if the caller is its assigned coordinator. Unlike `_owned_event`,
    a coordinator who isn't assigned gets 403, not 404: coordinators may already
    search every non-draft event (QA-87), so the 403 confirms nothing new, and
    SCRUM-34/52 name the case Forbidden. A draft answers 404 to every coordinator,
    assigned or not: drafts are private to their organiser (DR-R2)."""
    row = repository.get_event(event_id)
    if not row or row.get("status") == "draft":
        raise EventNotFoundError()
    if row.get("coordinator_id") != coordinator_id:
        raise NotAssignedCoordinatorError()
    return row


def _transition(row: dict, actor_id: str, action: str, *, reason: str | None,
                notify_type: str, notify_message: str) -> EventResponse:
    to_status = lifecycle.target(action, row["status"])
    updated = repository.transition_event(
        row["id"], actor_id, lifecycle.allowed_from(action), to_status.value, row["version"],
        reason=reason, notify_type=notify_type, notify_message=notify_message,
    )
    if not updated:
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return _to_response(updated)


def approve(event_id: str, coordinator_id: str) -> EventResponse:
    row = _assigned_event(event_id, coordinator_id)
    return _transition(
        row, coordinator_id, "approve", reason=None, notify_type="event_approved",
        notify_message=f'Your event "{row["name"]}" passed its initial review and is now in planning.',
    )


def reject(event_id: str, coordinator_id: str, reason: str) -> EventResponse:
    row = _assigned_event(event_id, coordinator_id)
    return _transition(
        row, coordinator_id, "reject", reason=reason, notify_type="event_rejected",
        notify_message=f'Your event "{row["name"]}" was rejected: {reason}',
    )


def return_for_amendment(event_id: str, coordinator_id: str, body: EventReturnRequest) -> EventResponse:
    row = _assigned_event(event_id, coordinator_id)
    to_status = lifecycle.target("return", row["status"])
    updated = repository.return_event(
        row["id"], coordinator_id, lifecycle.allowed_from("return"), to_status.value, row["version"],
        message=body.message,
        flagged_fields=[field.value for field in body.flagged_fields],
        notify_message=f'Your event "{row["name"]}" was returned for amendment: {body.message}',
    )
    if not updated:
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return _with_amendment(updated)


def resubmit(event_id: str, organiser_id: str, body: EventResubmitRequest) -> EventResponse:
    """Like `submit`: apply the form's edits, check the request is still complete, then
    move it back to its coordinator. Edits that land before a lost race stay saved; the
    event stays returned and the organiser is told to reload."""
    row = _owned_event(event_id, organiser_id)
    to_status = lifecycle.target("resubmit", row["status"])
    values = body.model_dump(mode="json", exclude_unset=True, exclude={"resubmission_note"})
    _validate_submission({**row, **values})
    if values:
        updated = repository.update_event(event_id, values, row["version"])
        if not updated:
            raise EventConflictError(STALE_EVENT_MESSAGE)
        row = updated
    updated = repository.resubmit_event(
        event_id, organiser_id, lifecycle.allowed_from("resubmit"), to_status.value, row["version"],
        note=body.resubmission_note,
        notify_message=f'"{row["name"]}" was amended and resubmitted: {body.resubmission_note}',
    )
    if not updated:
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return _to_response(updated)


def _validate_submission(row: dict) -> None:
    errors = []
    required_fields = ("purpose", "starts_at", "ends_at", "expected_attendance", "layout_preference")
    for field in required_fields:
        if row.get(field) in (None, ""):
            errors.append({"loc": ["body", field], "msg": "Field required", "type": "missing"})

    starts_at = row.get("starts_at")
    ends_at = row.get("ends_at")
    event_timezone = ZoneInfo(row.get("event_timezone") or DEFAULT_EVENT_TIMEZONE)
    event_ends_at = None
    if starts_at and ends_at:
        starts_at = _parse_datetime(starts_at)
        ends_at = _parse_datetime(ends_at)
        event_ends_at = ends_at
        if ends_at <= starts_at:
            errors.append({"loc": ["body", "ends_at"], "msg": "End time must be after start time.", "type": "value_error"})
        if starts_at.astimezone(event_timezone).date() <= datetime.now(event_timezone).date():
            errors.append({"loc": ["body", "starts_at"], "msg": "Event date must be after today.", "type": "value_error"})

    if row.get("registration_enabled"):
        if not row.get("registration_capacity"):
            errors.append({"loc": ["body", "registration_capacity"], "msg": "Registration capacity is required when registration is enabled.", "type": "value_error"})
        if row.get("registration_opens_at") is None:
            errors.append({"loc": ["body", "registration_opens_at"], "msg": "Registration opening time is required when registration is enabled.", "type": "value_error"})
        if row.get("registration_closes_at") is None:
            errors.append({"loc": ["body", "registration_closes_at"], "msg": "Registration closing time is required when registration is enabled.", "type": "value_error"})
        registration_opens_at = row.get("registration_opens_at")
        registration_closes_at = row.get("registration_closes_at")
        if registration_opens_at and registration_closes_at:
            registration_opens_at = _parse_datetime(registration_opens_at)
            registration_closes_at = _parse_datetime(registration_closes_at)
            if registration_opens_at.astimezone(event_timezone).date() <= datetime.now(event_timezone).date():
                errors.append({"loc": ["body", "registration_opens_at"], "msg": "Registration opening date must be after today.", "type": "value_error"})
            if registration_closes_at <= registration_opens_at:
                errors.append({"loc": ["body", "registration_closes_at"], "msg": "Registration closing time must be after opening time.", "type": "value_error"})
            if registration_closes_at.astimezone(event_timezone).date() <= datetime.now(event_timezone).date():
                errors.append({"loc": ["body", "registration_closes_at"], "msg": "Registration closing date must be after today.", "type": "value_error"})
            if event_ends_at and registration_closes_at > event_ends_at:
                errors.append({"loc": ["body", "registration_closes_at"], "msg": "Registration closing time cannot be after the event end time.", "type": "value_error"})

    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)


def _parse_datetime(value: datetime | str) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise HTTPException(status_code=422, detail="Date and time values must include a timezone offset.")
    return parsed


def create(organiser_id: str, body: EventCreateRequest) -> EventResponse:
    values = body.model_dump(mode="json", exclude_unset=True)
    return _to_response(repository.create_event(organiser_id, values))


def list_owned(organiser_id: str) -> list[EventResponse]:
    return [_to_response(row) for row in repository.list_events(organiser_id)]


def _visible_event(event_id: str, user_id: str, role: str) -> dict:
    """Organisers see their own events (404 otherwise); coordinators see the non-draft
    events assigned to them (403 if unassigned, 404 if draft or missing). The router's
    role gate admits no one else."""
    if role == "event_coordinator":
        return _assigned_event(event_id, user_id)
    return _owned_event(event_id, user_id)


def read(event_id: str, user_id: str, role: str = "event_organiser") -> EventResponse:
    return _with_amendment(_visible_event(event_id, user_id, role))


def history(event_id: str, user_id: str, role: str) -> EventHistoryResponse:
    _visible_event(event_id, user_id, role)
    return EventHistoryResponse(
        entries=[EventHistoryEntry(**row) for row in repository.list_status_history(event_id)]
    )


def update(event_id: str, organiser_id: str, body: EventUpdateRequest) -> EventResponse:
    row = _owned_event(event_id, organiser_id)
    if row.get("status") not in ("draft", "returned"):
        raise EventConflictError("Only draft or returned events can be edited.")
    values = body.model_dump(mode="json", exclude_unset=True)
    updated = repository.update_event(event_id, values, row["version"])
    if not updated:
        raise EventConflictError()
    return _with_amendment(updated)


def discard(event_id: str, organiser_id: str) -> None:
    row = _owned_event(event_id, organiser_id)
    if row.get("status") != "draft":
        raise EventConflictError("Only draft events can be discarded.")
    repository.delete_event(event_id)


def submit(event_id: str, organiser_id: str, body: EventUpdateRequest | None = None) -> EventResponse:
    row = _owned_event(event_id, organiser_id)
    if row.get("status") != "draft":
        raise EventConflictError("Only draft events can be submitted.")
    values = body.model_dump(mode="json", exclude_unset=True) if body is not None else {}
    candidate = {**row, **values}
    _validate_submission(candidate)
    if values:
        updated = repository.update_event(event_id, values, row["version"])
        if not updated:
            raise EventConflictError()
        row = updated
    updated = repository.transition_event(
        event_id, organiser_id, lifecycle.allowed_from("submit"),
        lifecycle.target("submit", row["status"]).value, row["version"],
    )
    if not updated:
        raise EventConflictError()
    return _to_response(updated)


def _venue_readiness(booking_statuses: list[str]) -> ReadinessState:
    # REQUIREMENTS §6.6: the venue is ready once a booking is approved.
    return ReadinessState.ready if "approved" in booking_statuses else ReadinessState.pending


def _equipment_readiness(row: dict, reserved: set[str]) -> ReadinessState:
    # [Assumption] REQUIREMENTS §6.21.1: no equipment asked for means nothing to
    # wait on; otherwise ready once tech support has reserved some.
    if not (row.get("preliminary_equipment_needs") or "").strip():
        return ReadinessState.not_required
    return ReadinessState.ready if row["id"] in reserved else ReadinessState.pending


def _action_kind(row: dict, resubmitted_at: str | None) -> CoordinatorActionKind | None:
    status = row["status"]
    if status == "under_review":
        # A resubmission is the organiser's answer to a return (QA-22, QA-77):
        # SCRUM-72's "clarification response", not a first review.
        return CoordinatorActionKind.resubmitted if resubmitted_at else CoordinatorActionKind.awaiting_review
    # [Assumption] REQUIREMENTS §6.21.1: tech support marking technical readiness
    # as `issue` is the one arrangement problem the system records today.
    if status in ("planning", "confirmed") and row.get("technical_readiness") == "issue":
        return CoordinatorActionKind.arrangement_issue
    # `returned` is waiting on the organiser, not the coordinator.
    return None


def coordinator_dashboard(coordinator_id: str) -> CoordinatorDashboard:
    """Everything the Event Coordinator dashboard shows, in one round trip (SCRUM-72).

    Only events assigned to the caller, never drafts (DR-R2). Action kinds whose
    data doesn't exist yet (change and cancellation requests, booking and
    equipment decisions, re-review outcomes) are not produced, so their widgets
    stay empty rather than invent anything (REQUIREMENTS §6.21). The SPA ranks
    the items, so they are returned unordered.
    """
    rows = repository.list_coordinator_events(coordinator_id, ACTIVE_COORDINATOR_STATUSES)
    event_ids = [row["id"] for row in rows]
    under_review_ids = [row["id"] for row in rows if row["status"] == "under_review"]

    resubmissions = repository.list_latest_resubmissions(under_review_ids)
    bookings = venues_service.booking_statuses_by_event(event_ids) if event_ids else {}
    reserved = equipment_service.reserved_event_ids(event_ids) if event_ids else set()

    action_items: list[CoordinatorActionItem] = []
    active_events: list[CoordinatorActiveEvent] = []
    for row in rows:
        resubmitted_at = resubmissions.get(row["id"])
        kind = _action_kind(row, resubmitted_at)
        if kind is not None:
            action_items.append(
                CoordinatorActionItem(
                    event_id=row["id"],
                    event_name=row["name"],
                    kind=kind,
                    starts_at=row.get("starts_at"),
                    occurred_at=resubmitted_at or row.get("submitted_at"),
                    organiser_name=(row.get("organiser") or {}).get("full_name"),
                )
            )

        technical = ReadinessState(row["technical_readiness"])
        active_events.append(
            CoordinatorActiveEvent(
                event_id=row["id"],
                event_name=row["name"],
                status=row["status"],
                starts_at=row.get("starts_at"),
                flags=["technical_issue"] if technical is ReadinessState.issue else [],
                readiness=Readiness(
                    venue=_venue_readiness(bookings.get(row["id"], [])),
                    equipment=_equipment_readiness(row, reserved),
                    technical=technical,
                ),
            )
        )

    return CoordinatorDashboard(
        action_items=action_items,
        active_events=active_events,
        unassigned_count=repository.count_unassigned(UNASSIGNED_STATUSES),
    )
