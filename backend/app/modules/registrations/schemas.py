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


class RegistrationResult(BaseModel):
    registration_id: str | None = None
    status: str
    registered_at: datetime | None = None