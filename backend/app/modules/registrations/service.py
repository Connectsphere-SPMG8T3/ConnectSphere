from datetime import datetime, timezone
from fastapi import HTTPException, status

from app.modules.registrations import repository
from app.modules.registrations.schemas import (
    AttendeeRegistration,
    AttendeeRegistrationList,
    PublicEvent,
    PublicVenue,
    RegistrationAvailability,
    RegistrationResult,
    RegisteredEvent,
    WithdrawalResult,
)


def _availability(row: dict, registered: int, capacity: int | None, now: datetime) -> RegistrationAvailability:
    if not row.get("registration_enabled"):
        return RegistrationAvailability.not_open
    opens_at = row.get("registration_opens_at")
    closes_at = row.get("registration_closes_at")
    if opens_at is None or now < _as_utc(opens_at):
        return RegistrationAvailability.not_open
    if closes_at is not None and now >= _as_utc(closes_at):
        return RegistrationAvailability.closed
    if capacity is not None and registered >= capacity:
        return RegistrationAvailability.full
    return RegistrationAvailability.open


def _as_utc(value: datetime | str) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    return parsed.astimezone(timezone.utc)


def registered_count(event_id: str) -> int:
    """How many attendees are registered for the event now (story 37's preview)."""
    return repository.registered_count(event_id)


def public_directory() -> list[PublicEvent]:
    now = datetime.now(timezone.utc)
    return [_to_public_event(row, now) for row in repository.list_public_event_rows()]


def _to_public_event(row: dict, now: datetime) -> PublicEvent:
    venues = _attendee_facing_venues(row.get("event_space_requests"))
    venue_capacity = min((venue.capacity for venue in venues), default=None)
    organiser_capacity = row.get("registration_capacity")
    capacities = [value for value in (organiser_capacity, venue_capacity) if value is not None]
    effective_capacity = min(capacities) if capacities else None
    count = repository.registered_count(row["id"])
    return PublicEvent(
        id=row["id"],
        name=row["name"],
        description=row.get("description"),
        starts_at=row.get("starts_at"),
        ends_at=row.get("ends_at"),
        event_timezone=row["event_timezone"],
        status=row["status"],
        availability=_availability(row, count, effective_capacity, now),
        effective_capacity=effective_capacity,
        registered_count=count,
        waitlist_enabled=row.get("waitlist_enabled", True),
        venues=venues,
    )


def _attendee_facing_venues(spaces: list[dict] | None) -> list[PublicVenue]:
    confirmed_venues = []
    primary_venues = []
    primary_is_set = False
    for space in spaces or []:
        approved = [
            booking["venue"]
            for booking in space.get("venue_bookings") or []
            if booking.get("status") == "approved" and booking.get("venue")
        ]
        confirmed_venues.extend(approved)
        if space.get("is_primary"):
            primary_is_set = True
            primary_venues.extend(approved)
    selected = primary_venues if primary_is_set else confirmed_venues
    return [PublicVenue(**venue) for venue in selected]


def attendee_registrations(attendee_id: str) -> AttendeeRegistrationList:
    rows = repository.list_attendee_registration_rows(attendee_id)
    registrations = []
    for row in rows:
        event_row = row["event"]
        event = RegisteredEvent(
            id=event_row["id"],
            name=event_row["name"],
            description=event_row.get("description"),
            starts_at=event_row["starts_at"],
            ends_at=event_row["ends_at"],
            event_timezone=event_row["event_timezone"],
            status=event_row["status"],
            withdrawal_closes_at=event_row.get("withdrawal_closes_at"),
            venues=_attendee_facing_venues(event_row.get("event_space_requests")),
        )
        registrations.append(
            AttendeeRegistration(
                id=row["id"],
                status=row["status"],
                registered_at=row["registered_at"],
                event=event,
            )
        )
    return AttendeeRegistrationList(registrations=registrations)


def public_event(event_id: str) -> PublicEvent:
    row = repository.get_public_event_row(event_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    return _to_public_event(row, datetime.now(timezone.utc))


def register_attendee(event_id: str, attendee_id: str) -> RegistrationResult:
    result = repository.register_for_event(event_id, attendee_id)
    outcome = result["outcome"]
    if outcome == "unavailable":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    if outcome == "not_open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Registration is not open yet.")
    if outcome == "closed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Registration is closed.")
    if outcome == "full":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Event is full.")
    if outcome == "reregistration_disabled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Re-registration is not allowed for this event.")
    return RegistrationResult(
        registration_id=result.get("registration_id"),
        status="already_registered" if outcome == "already_registered" else "registered",
        registered_at=result.get("registered_at"),
    )


def withdraw_attendee(event_id: str, attendee_id: str) -> WithdrawalResult:
    result = repository.withdraw_registration(event_id, attendee_id)
    outcome = result["outcome"]
    if outcome == "unavailable":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    if outcome == "cutoff_passed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The withdrawal cutoff has passed.")
    if outcome == "event_started":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The event has started.")
    if outcome == "already_withdrawn":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This registration has already been withdrawn.",
        )
    if outcome == "not_registered":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No active registration found.")
    if outcome != "withdrawn":
        raise RuntimeError(f"Unexpected withdrawal outcome: {outcome!r}")
    return WithdrawalResult(registration_id=result["registration_id"], status="withdrawn")