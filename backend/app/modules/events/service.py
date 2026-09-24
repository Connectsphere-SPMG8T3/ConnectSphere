from collections.abc import Iterable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status

from app.core.exceptions import NotAssignedCoordinatorError
from app.modules.events import lifecycle, repository
from app.modules.events.schemas import (
    EventCreateRequest,
    EventHistoryEntry,
    EventHistoryResponse,
    EventResponse,
    EventUpdateRequest,
)

DEFAULT_EVENT_TIMEZONE = "Asia/Singapore"


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
    (SCENARIO §4.9), so a PostgREST embed is not available and a caller that
    needs names asks here rather than reading another module's table.
    """
    return repository.list_event_names(event_ids)


def _to_response(row: dict) -> EventResponse:
    return EventResponse(**row)


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
    SCRUM-34/52 name the case Forbidden."""
    row = repository.get_event(event_id)
    if not row:
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
        row = repository.get_event(event_id)
        if not row or row.get("status") == "draft":
            raise EventNotFoundError()
        if row.get("coordinator_id") != user_id:
            raise NotAssignedCoordinatorError()
        return row
    return _owned_event(event_id, user_id)


def read(event_id: str, user_id: str, role: str = "event_organiser") -> EventResponse:
    return _to_response(_visible_event(event_id, user_id, role))


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
    return _to_response(updated)


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
    updated = repository.submit_event(event_id, row["version"], datetime.now(timezone.utc))
    if not updated:
        raise EventConflictError()
    return _to_response(updated)
