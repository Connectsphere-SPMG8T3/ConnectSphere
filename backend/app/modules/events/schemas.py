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


class EventField(str, Enum):
    """The request fields a coordinator can flag when returning it (SCRUM-33).
    Exactly the fields `EventUpdateRequest` lets the organiser edit."""

    name = "name"
    event_timezone = "event_timezone"
    purpose = "purpose"
    description = "description"
    starts_at = "starts_at"
    ends_at = "ends_at"
    expected_attendance = "expected_attendance"
    layout_preference = "layout_preference"
    facilities_required = "facilities_required"
    accessibility_needs = "accessibility_needs"
    preliminary_equipment_needs = "preliminary_equipment_needs"
    registration_enabled = "registration_enabled"
    registration_capacity = "registration_capacity"
    registration_opens_at = "registration_opens_at"
    registration_closes_at = "registration_closes_at"


class AmendmentRequest(BaseModel):
    id: str
    message: str
    # Plain strings on the way out: EventReturnRequest validates names on the way
    # in, and a stored name that later leaves EventField must not break reads.
    flagged_fields: list[str]
    returned_at: datetime


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
    # The open amendment while the event is returned (SCRUM-33); null otherwise
    # and on list responses.
    amendment: AmendmentRequest | None = None


class EventListResponse(BaseModel):
    events: list[EventResponse]


REJECT_REASON_MAX_LENGTH = 1000  # [Assumption] REQUIREMENTS §9; no customer limit given


class EventRejectRequest(BaseModel):
    reason: str = Field(max_length=REJECT_REASON_MAX_LENGTH)

    @field_validator("reason", mode="before")
    @classmethod
    def reason_is_not_blank(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("A rejection reason is required.")
        stripped = value.strip()
        if not stripped:
            raise ValueError("A rejection reason is required.")
        return stripped


AMENDMENT_TEXT_MAX_LENGTH = 1000  # [Assumption] REQUIREMENTS §9; same cap as a rejection reason


def _required_text(value, message: str) -> str:
    if not isinstance(value, str):
        raise ValueError(message)
    stripped = value.strip()
    if not stripped:
        raise ValueError(message)
    return stripped


class EventReturnRequest(BaseModel):
    message: str = Field(max_length=AMENDMENT_TEXT_MAX_LENGTH)
    flagged_fields: list[EventField] = []

    @field_validator("message", mode="before")
    @classmethod
    def message_is_not_blank(cls, value):
        return _required_text(value, "A message for the organiser is required.")

    @field_validator("flagged_fields")
    @classmethod
    def flag_each_field_once(cls, value: list[EventField]) -> list[EventField]:
        return list(dict.fromkeys(value))


class EventResubmitRequest(EventUpdateRequest):
    resubmission_note: str = Field(max_length=AMENDMENT_TEXT_MAX_LENGTH)

    @field_validator("resubmission_note", mode="before")
    @classmethod
    def note_is_not_blank(cls, value):
        return _required_text(value, "A resubmission note is required.")


class HistoryActor(BaseModel):
    id: str
    full_name: str


class EventHistoryEntry(BaseModel):
    id: str
    from_status: EventStatus | None = None
    to_status: EventStatus
    actor: HistoryActor | None = None
    reason: str | None = None
    at: datetime


class EventHistoryResponse(BaseModel):
    entries: list[EventHistoryEntry]
