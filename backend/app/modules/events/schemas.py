from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from app.modules.venues.schemas import Facility, VenueLayout


class EventStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    under_review = "under_review"
    returned = "returned"
    planning = "planning"
    confirmed = "confirmed"
    rejected = "rejected"
    cancelled = "cancelled"
    completed = "completed"


class TechnicalReadiness(str, Enum):
    not_required = "not_required"
    pending = "pending"
    ready = "ready"
    issue = "issue"


class EventFields(BaseModel):
    name: str = Field(min_length=3, max_length=150)
    event_timezone: str = "Asia/Singapore"
    purpose: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    expected_attendance: int | None = Field(default=None, ge=1)
    layout_preference: VenueLayout | None = None
    facilities_required: list[Facility] = []
    accessibility_needs: str | None = None
    preliminary_equipment_needs: str | None = None
    registration_enabled: bool = False
    registration_capacity: int | None = Field(default=None, ge=1)
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None

    @field_validator("event_timezone")
    @classmethod
    def validate_event_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("event_timezone must be a valid IANA timezone.")
        return value


class EventCreateRequest(EventFields):
    pass


class EventUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=150)
    event_timezone: str | None = None
    purpose: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    expected_attendance: int | None = Field(default=None, ge=1)
    layout_preference: VenueLayout | None = None
    facilities_required: list[Facility] | None = None
    accessibility_needs: str | None = None
    preliminary_equipment_needs: str | None = None
    registration_enabled: bool | None = None
    registration_capacity: int | None = Field(default=None, ge=1)
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None

    @field_validator("event_timezone")
    @classmethod
    def validate_event_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("event_timezone must be a valid IANA timezone.")
        return value


class EventResponse(EventFields):
    id: str
    organiser_id: str
    coordinator_id: str | None = None
    status: EventStatus
    technical_readiness: TechnicalReadiness
    submitted_at: datetime | None = None
    version: int
    created_at: datetime
    updated_at: datetime


class EventListResponse(BaseModel):
    events: list[EventResponse]


REJECT_REASON_MAX_LENGTH = 1000  # [Assumption] REQUIREMENTS §9; no customer limit given


class EventRejectRequest(BaseModel):
    reason: str = Field(max_length=REJECT_REASON_MAX_LENGTH)

    @field_validator("reason")
    @classmethod
    def reason_is_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("A rejection reason is required.")
        return stripped
