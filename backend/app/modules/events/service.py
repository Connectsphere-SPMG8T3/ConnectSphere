from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.modules.events import repository
from app.modules.events.schemas import EventCreateRequest, EventResponse, EventUpdateRequest

SINGAPORE_TZ = timezone(timedelta(hours=8))


class EventNotFoundError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")


class EventConflictError(HTTPException):
    def __init__(self, detail: str = "The event was changed by another request.") -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _to_response(row: dict) -> EventResponse:
    return EventResponse(**row)


def _owned_event(event_id: str, organiser_id: str) -> dict:
    row = repository.get_event(event_id)
    if not row or row.get("organiser_id") != organiser_id:
        raise EventNotFoundError()
    return row


def _validate_submission(row: dict) -> None:
    errors = []
    required_fields = ("purpose", "starts_at", "ends_at", "expected_attendance", "layout_preference")
    for field in required_fields:
        if row.get(field) in (None, ""):
            errors.append({"loc": ["body", field], "msg": "Field required", "type": "missing"})

    starts_at = row.get("starts_at")
    ends_at = row.get("ends_at")
    event_ends_at = None
    if starts_at and ends_at:
        starts_at = _parse_datetime(starts_at)
        ends_at = _parse_datetime(ends_at)
        event_ends_at = ends_at
        if ends_at <= starts_at:
            errors.append({"loc": ["body", "ends_at"], "msg": "End time must be after start time.", "type": "value_error"})
        if starts_at.astimezone(SINGAPORE_TZ).date() <= datetime.now(SINGAPORE_TZ).date():
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
            if registration_opens_at.astimezone(SINGAPORE_TZ).date() <= datetime.now(SINGAPORE_TZ).date():
                errors.append({"loc": ["body", "registration_opens_at"], "msg": "Registration opening date must be after today.", "type": "value_error"})
            if registration_closes_at <= registration_opens_at:
                errors.append({"loc": ["body", "registration_closes_at"], "msg": "Registration closing time must be after opening time.", "type": "value_error"})
            if registration_closes_at.astimezone(SINGAPORE_TZ).date() <= datetime.now(SINGAPORE_TZ).date():
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


def read(event_id: str, organiser_id: str) -> EventResponse:
    return _to_response(_owned_event(event_id, organiser_id))


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
