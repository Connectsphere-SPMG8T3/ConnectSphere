from datetime import datetime
from enum import Enum
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.equipment.schemas import ExitConfirmation
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
    status: str | None = None
    coordinator_id: str | None = None
    expected_attendance: int | None = None
    layout_preference: VenueLayout | None = None
    facilities_required: list[Facility] = []
    # SCRUM-38 AC1: venue staff see it on the booking request.
    accessibility_needs: str | None = None


class SpaceRequirements(BaseModel):
    """What one requested space needs from a venue (CR-94). A null field (or,
    for facilities, an empty list: the column is never null) means the space
    did not say, and the caller falls back to the event's value."""

    expected_pax: int | None = None
    layout_preference: VenueLayout | None = None
    facilities_required: list[Facility] | None = None


def _validate_space_window(starts_at: datetime | None, ends_at: datetime | None) -> None:
    if starts_at is None and ends_at is None:
        return
    if starts_at is None or ends_at is None:
        raise ValueError("starts_at and ends_at must be provided together.")
    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise ValueError("Space schedule values must include a timezone offset.")
    if ends_at <= starts_at:
        raise ValueError("Space end time must be after its start time.")


class EventSpaceRequestFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=150)
    expected_pax: int = Field(ge=1)
    layout_preference: VenueLayout
    facilities_required: list[Facility] = []
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("label", mode="before")
    @classmethod
    def label_is_not_blank(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("A space label is required.")
        return value.strip()

    @model_validator(mode="after")
    def validate_schedule(self):
        _validate_space_window(self.starts_at, self.ends_at)
        return self

class EventSpaceRequestCreate(EventSpaceRequestFields):
    pass


class EventSpaceRequestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=150)
    expected_pax: int | None = Field(default=None, ge=1)
    layout_preference: VenueLayout | None = None
    facilities_required: list[Facility] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    version: int | None = None

    @field_validator("label", mode="before")
    @classmethod
    def optional_label_is_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not isinstance(value, str) or not value.strip():
            raise ValueError("A space label is required.")
        return value.strip()

    @model_validator(mode="after")
    def changed_fields_are_not_null(self):
        for field in ("label", "expected_pax", "layout_preference", "facilities_required"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        schedule_fields = {"starts_at", "ends_at"} & self.model_fields_set
        if schedule_fields and schedule_fields != {"starts_at", "ends_at"}:
            raise ValueError("starts_at and ends_at must be updated together.")
        if schedule_fields:
            _validate_space_window(self.starts_at, self.ends_at)
        return self

class EventSpaceRequest(EventSpaceRequestFields):
    id: str
    event_id: str
    version: int = 1
    is_primary: bool = False


class EventSpaceRequestResponse(BaseModel):
    id: str
    event_id: str
    label: str
    expected_pax: int | None = None
    layout_preference: VenueLayout | None = None
    facilities_required: list[Facility] = []
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    version: int = 1
    is_primary: bool = False  # CR-97 AC9


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


class EventRejectedBooking(BaseModel):
    """A venue booking venue staff rejected, with what they said (SCRUM-38 AC6).
    Coordinator view only: never on the organiser's read (AUTH-R2)."""

    id: str
    venue_id: str
    venue_name: str | None = None
    reason: str | None = None
    suggestion: str | None = None
    decided_at: datetime | None = None


class EventVenueBooking(BaseModel):
    """The venue an event holds or has booked (SCRUM-19). Coordinator view only."""

    id: str
    event_space_request_id: str | None = None
    venue_id: str
    venue_name: str | None = None
    status: str
    # When a hold expires unless approved (CR-99); `expired` once it has.
    expires_at: datetime | None = None
    # CR-95: `affected` when the venue became unavailable, with why, and the
    # booking a replacement stands in for. Coordinator view only.
    flag: str | None = None
    flag_reason: str | None = None
    replaces_booking_id: str | None = None


class EventCoordinator(BaseModel):
    id: str
    full_name: str


class BookingReadiness(BaseModel):
    status: str
    flags: list[str] = []


class SpaceReadiness(BaseModel):
    """One event space and the bookings made for it (CR-97 AC10)."""
    label: str
    bookings: list[BookingReadiness] = []


class SafetyReadiness(BaseModel):
    ready: bool
    missing: list[str]


class SafetyDecisionKind(str, Enum):
    approved = "approved"
    changes_requested = "changes_requested"
    arrangement_rejected = "arrangement_rejected"
    withdrawn = "withdrawn"


class ReturnReason(str, Enum):
    arrangement_flagged = "arrangement_flagged"
    booking_cancelled = "booking_cancelled"
    technical_not_ready = "technical_not_ready"
    approved_details_changed = "approved_details_changed"


class SafetyApproveRequest(BaseModel):
    comment: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("comment", mode="before")
    @classmethod
    def strip_comment(cls, value):
        return value.strip() if isinstance(value, str) else value


class SafetyArrangementIds(BaseModel):
    booking_ids: list[UUID] = []
    equipment_request_ids: list[UUID] = []

    @field_validator("booking_ids", "equipment_request_ids")
    @classmethod
    def unique_ids(cls, value):
        return list(dict.fromkeys(value))


class SafetyChangesRequest(SafetyArrangementIds):
    comment: str = Field(min_length=1, max_length=1000)

    @field_validator("comment", mode="before")
    @classmethod
    def strip_comment(cls, value):
        return value.strip() if isinstance(value, str) else value


class SafetyRejectRequest(BaseModel):
    booking_id: UUID
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def strip_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


class SafetyDecision(BaseModel):
    id: UUID
    decision: SafetyDecisionKind
    comment: str | None = None
    reason_code: ReturnReason | None = None
    affected_booking_ids: list[UUID] = []
    affected_equipment_request_ids: list[UUID] = []
    rejected_venue_ids: list[UUID] = []
    decided_by_name: str | None = None
    decided_at: datetime


class SafetyDecisionSummary(BaseModel):
    decision: SafetyDecisionKind
    reason_label: str
    decided_at: datetime

class EventSpaceVenueBooking(EventVenueBooking):
    pass


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
    spaces: list[EventSpaceRequestResponse] = []

    @field_validator("spaces")
    @classmethod
    def _only_space_is_primary(cls, spaces: list[EventSpaceRequestResponse]) -> list[EventSpaceRequestResponse]:
        # CR-97 Q11: an event's only space is its primary venue without being marked.
        if len(spaces) == 1:
            spaces[0].is_primary = True
        return spaces

    # The open amendment while the event is returned (SCRUM-33); null otherwise
    # and on list responses.
    amendment: AmendmentRequest | None = None
    # The event's held, approved or re-review booking, on the assigned
    # coordinator's single-event read (SCRUM-19), and on the organiser's once
    # the event is confirmed (SCRUM-82 AC8); null otherwise. Before then the
    # organiser doesn't get it: booking state is internal planning detail (AUTH-R2).
    venue_booking: EventVenueBooking | None = None
    # Bookings venue staff rejected, with their reason and suggestion, on the
    # assigned coordinator's single-event read only (SCRUM-38 AC6, AC7).
    rejected_bookings: list[EventRejectedBooking] = []
    safety_readiness: SafetyReadiness | None = None
    latest_safety_decision: SafetyDecision | SafetyDecisionSummary | None = None
    venue_bookings: list[EventSpaceVenueBooking] = []


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

    needs_alternative_venue = "needs_alternative_venue"
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


class LeadCoordinator(BaseModel):
    id: str
    full_name: str
    active_count: int = 0


class LeadEvent(BaseModel):
    event_id: str
    event_name: str
    status: EventStatus
    starts_at: datetime | None = None
    organiser_name: str | None = None
    purpose: str | None = None
    expected_attendance: int | None = None
    coordinator: EventCoordinator | None = None
    assigned_at: datetime | None = None
    # The Lead sends it back on reassign, so a screen that is behind can't overwrite a newer change.
    version: int


class LeadDashboard(BaseModel):
    """CR-101: the Event Coordinator Lead's view. `unassigned` is the shared queue;
    `active_events` are the assigned events in this Lead's scope (AC5)."""

    unassigned: list[LeadEvent] = []
    active_events: list[LeadEvent] = []
    coordinators: list[LeadCoordinator] = []


class EventReassignRequest(BaseModel):
    coordinator_id: UUID
    expected_version: int


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


class SafetyQueueItem(BaseModel):
    event_id: str
    name: str
    organiser_name: str | None = None
    starts_at: datetime | None = None
    expected_attendance: int | None = None
    entered_review_at: datetime


class SafetyQueueResponse(BaseModel):
    items: list[SafetyQueueItem]


class SafetyHistoryItem(BaseModel):
    """One recent decision on the Safety Officer dashboard (CR-103 AC7)."""
    id: UUID
    event_id: str
    event_name: str
    decision: SafetyDecisionKind
    comment: str | None = None
    decided_by_name: str | None = None
    decided_at: datetime


class SafetyHistoryResponse(BaseModel):
    items: list[SafetyHistoryItem]


class SafetyRegistration(BaseModel):
    enabled: bool
    capacity: int | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None


class SafetyReviewEvent(BaseModel):
    id: str
    name: str
    organiser_name: str | None = None
    coordinator_name: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    expected_attendance: int | None = None
    accessibility_needs: str | None = None
    registration: SafetyRegistration


class SafetyReviewVenue(BaseModel):
    booking_id: str
    venue_id: str
    venue_name: str | None = None
    booking_status: str
    capacity: int | None = None
    layouts: list[str] = []
    accessibility_features: list[str] = []
    attendance_to_capacity: float | None = None
    emergency_access: str | None = None
    restrictions: str | None = None


class SafetyEquipmentLine(BaseModel):
    id: str
    equipment_name: str
    quantity: int
    status: str


class SafetyReviewResponse(BaseModel):
    event: SafetyReviewEvent
    venues: list[SafetyReviewVenue]
    equipment_lines: list[SafetyEquipmentLine]
    # SCRUM-24 AC10: who ticked "Equipment does not block exits or walkways", and when.
    exit_confirmation: ExitConfirmation | None = None
    decisions: list[SafetyDecision]
