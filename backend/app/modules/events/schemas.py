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
    safety_review = "safety_review"
    confirmed = "confirmed"
    rejected = "rejected"
    cancelled = "cancelled"
    completed = "completed"


class EventPlanningContext(BaseModel):
    """What another module needs to judge an event's requirements without
    reading the `events` table itself (SCRUM-63; `venues.impact` uses this to
    decide whether a venue edit newly breaks a booking's event).
    """

    name: str | None = None
    coordinator_id: str | None = None
    expected_attendance: int | None = None
    layout_preference: VenueLayout | None = None
    facilities_required: list[Facility] = []


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


class EventVenueBooking(BaseModel):
    """The venue an event holds or has booked (SCRUM-19). Coordinator view only."""

    id: str
    venue_id: str
    venue_name: str | None = None
    status: str


class EventCoordinator(BaseModel):
    id: str
    full_name: str


class BookingReadiness(BaseModel):
    status: str
    flags: list[str] = []


class SafetyReadiness(BaseModel):
    ready: bool
    missing: list[str]


class EventResponse(EventFields):
    id: str
    organiser_id: str
    coordinator_id: str | None = None
    # Named on the single-event read; null when unassigned and on other responses.
    coordinator: EventCoordinator | None = None
    status: EventStatus
    technical_readiness: TechnicalReadiness
    submitted_at: datetime | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    # The open amendment while the event is returned (SCRUM-33); null otherwise
    # and on list responses.
    amendment: AmendmentRequest | None = None
    # The event's held, approved or re-review booking, on the assigned
    # coordinator's single-event read (SCRUM-19), and on the organiser's once
    # the event is confirmed (SCRUM-82 AC8); null otherwise. Before then the
    # organiser doesn't get it: booking state is internal planning detail (AUTH-R2).
    venue_booking: EventVenueBooking | None = None
    safety_readiness: SafetyReadiness | None = None


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


# SCRUM-72: the Event Coordinator dashboard. The SPA's store
# (`frontend/src/features/events/store.js`) fixed this shape first, and it does
# the ranking itself, so action items are returned unordered.


class CoordinatorActionKind(str, Enum):
    """The action kinds the server can produce today. The SPA's `ACTION_KINDS`
    lists more (change and cancellation requests, booking and equipment
    decisions, re-review outcomes); those arrive with the stories that build
    their data, and until then their widgets stay empty (REQUIREMENTS §6.21)."""

    arrangement_issue = "arrangement_issue"
    resubmitted = "resubmitted"
    awaiting_review = "awaiting_review"


class ReadinessState(str, Enum):
    not_required = "not_required"
    pending = "pending"
    ready = "ready"
    issue = "issue"


class CoordinatorActionItem(BaseModel):
    event_id: str
    event_name: str
    kind: CoordinatorActionKind
    starts_at: datetime | None = None
    occurred_at: datetime | None = None
    organiser_name: str | None = None


class Readiness(BaseModel):
    """The blocking arrangements of REQUIREMENTS §6.6."""

    venue: ReadinessState
    equipment: ReadinessState
    technical: ReadinessState


class CoordinatorActiveEvent(BaseModel):
    event_id: str
    event_name: str
    status: EventStatus
    starts_at: datetime | None = None
    flags: list[str] = []
    readiness: Readiness


class CoordinatorDashboard(BaseModel):
    action_items: list[CoordinatorActionItem] = []
    active_events: list[CoordinatorActiveEvent] = []
    # No unassigned figure: unassigned events are the Event Coordinator Lead's
    # queue, not a coordinator's (customer clarification, REQUIREMENTS §6.5).


COMMENT_MAX_LENGTH = 1000  # [Assumption] REQUIREMENTS §9; same cap as a rejection reason

# Statuses whose thread accepts new comments (SCRUM-61). Drafts have no thread yet;
# rejected, cancelled and completed events keep theirs read-only. Mirrored in
# public.add_event_comment and in the SPA's features/events/comments.js.
COMMENTABLE_STATUSES = frozenset({
    EventStatus.submitted, EventStatus.under_review, EventStatus.returned,
    EventStatus.planning, EventStatus.safety_review, EventStatus.confirmed,
})


class EventCommentCreate(BaseModel):
    body: str = Field(max_length=COMMENT_MAX_LENGTH)

    @field_validator("body", mode="before")
    @classmethod
    def body_is_not_blank(cls, value):
        return _required_text(value, "A comment can't be empty.")


class EventCommentAuthor(BaseModel):
    id: str
    full_name: str
    role: str | None = None  # the role they hold on this event, not their profile role


class EventComment(BaseModel):
    id: str
    body: str
    created_at: datetime
    author: EventCommentAuthor | None = None


class EventCommentsResponse(BaseModel):
    comments: list[EventComment]
