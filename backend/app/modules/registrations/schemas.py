from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class RegistrationAvailability(str, Enum):
    not_open = "not_open"
    closed = "closed"
    full = "full"
    open = "open"


class PublicVenue(BaseModel):
    id: str
    name: str
    location: str
    capacity: int


class PublicEvent(BaseModel):
    id: str
    name: str
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    event_timezone: str
    status: str
    availability: RegistrationAvailability
    effective_capacity: int | None = None
    registered_count: int
    waitlist_enabled: bool
    venues: list[PublicVenue]


class PublicEventDirectory(BaseModel):
    events: list[PublicEvent]


class RegisteredEvent(BaseModel):
    id: str
    name: str
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    event_timezone: str
    status: str
    withdrawal_closes_at: datetime | None = None
    venues: list[PublicVenue]


class AttendeeRegistration(BaseModel):
    id: str
    status: str
    registered_at: datetime
    invitation_expires_at: datetime | None = None
    event: RegisteredEvent


class AttendeeRegistrationList(BaseModel):
    registrations: list[AttendeeRegistration]


class ManagedRegistration(BaseModel):
    id: str
    full_name: str
    status: str
    email: str | None = None
    phone_number: str | None = None


class ManagedRegistrationReport(BaseModel):
    event_id: str
    effective_capacity: int | None = None
    registered_count: int
    remaining_places: int | None = None
    waitlist_count: int
    registrations: list[ManagedRegistration]


class RegistrationResult(BaseModel):
    registration_id: str | None = None
    status: str
    registered_at: datetime | None = None
    invitation_expires_at: datetime | None = None


class WithdrawalResult(BaseModel):
    registration_id: str
    status: str
