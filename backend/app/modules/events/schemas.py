from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator

from app.modules.equipment.schemas import ExitConfirmation, TechnicalPreparation, TechnicalPreparationStage
from app.modules.venues.schemas import Facility, VenueLayout


class EventStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    under_review = "under_review"
    returned = "returned"
    planning = "planning"
    safety_review = "safety_review"
    confirmed = "confirmed"
    preparation = "preparation"
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
    withdrawal_closes_at: datetime | None = None
    re_registration_allowed: bool = True
    waitlist_enabled: bool = True

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
    withdrawal_closes_at: datetime | None = None
    re_registration_allowed: bool | None = None
    waitlist_enabled: bool | None = None

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


class EventDetailsEdit(BaseModel):
    """The assigned coordinator's direct edit of an event's ordinary details (story 112).

    Only the four fields below can be sent. Any other key is kept in `model_extra` so the
    service can refuse it by name: a significant field with the change-request message
    (AC2), anything else as not editable here. Bounds match `EventFields`."""

    model_config = ConfigDict(extra="allow")

    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=3, max_length=150)
    purpose: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    accessibility_needs: str | None = None

    @field_validator("name", "purpose", mode="before")
    @classmethod
    def required_text_is_trimmed(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def required_fields_are_not_blank(self):
        # A submitted request keeps what submission required (_submission_errors).
        for field in ("name", "purpose"):
            if field in self.model_fields_set and not getattr(self, field):
                raise ValueError(f"{field} is required.")
        return self


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
    withdrawal_closes_at = "withdrawal_closes_at"
    re_registration_allowed = "re_registration_allowed"
    waitlist_enabled = "waitlist_enabled"


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
    # Story 37: why an approved change marked it Needs re-review. Absent once sent or never
    # marked, so an unmarked booking keeps the shape it had before.
    needs_re_review_reason: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unmarked(self, handler):
        data = handler(self)
        if self.needs_re_review_reason is None:
            data.pop("needs_re_review_reason", None)
        return data


class EventCoordinator(BaseModel):
    id: str
    full_name: str


class EventOrganiser(BaseModel):
    """SCRUM-49 AC3: who sent the request. Name and organisation only; no contact
    details. `organisation_name` is free text from sign-up (ACC-R5), optional."""
    full_name: str | None = None
    organisation_name: str | None = None


class BookingReadiness(BaseModel):
    status: str
    flags: list[str] = []
    # Story 37: an approved change touched it, and the coordinator hasn't sent it yet.
    needs_re_review: bool = False


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


class SafetyFactor(str, Enum):
    """The six checklist factors of the safety review (CR-108 AC1, QA3-17)."""
    attendance_capacity = "attendance_capacity"
    layout = "layout"
    emergency_access = "emergency_access"
    accessibility = "accessibility"
    equipment_placement = "equipment_placement"
    venue_restrictions = "venue_restrictions"


class SafetyRating(str, Enum):
    satisfactory = "satisfactory"
    concern = "concern"
    not_applicable = "not_applicable"


class SafetyChecklistAnswer(BaseModel):
    """One factor's mark. Venue factors carry the booking they concern; equipment placement has none."""
    factor: SafetyFactor
    booking_id: UUID | None = None
    rating: SafetyRating
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note", mode="before")
    @classmethod
    def strip_note(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class SafetyDecisionText(BaseModel):
    """What every decision carries besides its outcome (CR-108 AC1, AC4).

    `organiser_comment` is shown to the organiser; `private_note` is for the assigned coordinator and
    Safety Officers only and must never reach the organiser, a notification or the organiser's history.
    """
    checklist: list[SafetyChecklistAnswer] = []
    organiser_comment: str | None = Field(default=None, min_length=1, max_length=1000)
    private_note: str | None = Field(default=None, max_length=1000)

    @field_validator("organiser_comment", mode="before")
    @classmethod
    def strip_organiser_comment(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("private_note", mode="before")
    @classmethod
    def strip_private_note(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class SafetyApproveRequest(SafetyDecisionText):
    pass


class SafetyArrangementIds(BaseModel):
    booking_ids: list[UUID] = []
    equipment_request_ids: list[UUID] = []

    @field_validator("booking_ids", "equipment_request_ids")
    @classmethod
    def unique_ids(cls, value):
        return list(dict.fromkeys(value))


class SafetyChangesRequest(SafetyDecisionText, SafetyArrangementIds):
    organiser_comment: str = Field(min_length=1, max_length=1000)


class SafetyRejectRequest(SafetyDecisionText):
    booking_id: UUID
    organiser_comment: str = Field(min_length=1, max_length=1000)


class NamedBooking(BaseModel):
    booking_id: UUID
    venue_name: str | None = None


class NamedEquipmentLine(BaseModel):
    id: UUID
    equipment_name: str | None = None


class NamedVenue(BaseModel):
    venue_id: UUID
    venue_name: str | None = None


class SafetyRevision(BaseModel):
    note: str
    by_name: str | None = None
    at: datetime


class SafetyChecklistItem(BaseModel):
    """One recorded checklist mark, named by venue. Staff only: the organiser never receives these."""
    factor: SafetyFactor
    booking_id: UUID | None = None
    venue_name: str | None = None
    rating: SafetyRating
    note: str | None = None


class SafetyDecision(BaseModel):
    """A decision as the assigned coordinator and the Safety Officers see it (CR-108).

    `private_note` is the decision row's `comment` column. The organiser is given
    `SafetyDecisionSummary` instead, never this model."""
    id: UUID
    decision: SafetyDecisionKind
    organiser_comment: str | None = None
    private_note: str | None = None
    checklist: list[SafetyChecklistItem] = []
    reason_code: ReturnReason | None = None
    affected_booking_ids: list[UUID] = []
    affected_equipment_request_ids: list[UUID] = []
    rejected_venue_ids: list[UUID] = []
    affected_bookings: list[NamedBooking] = []
    affected_equipment: list[NamedEquipmentLine] = []
    rejected_venues: list[NamedVenue] = []
    revision: SafetyRevision | None = None
    decided_by_name: str | None = None
    decided_at: datetime


class SafetyDecisionSummary(BaseModel):
    """What the organiser sees: the outcome and the officer's comment for them (CR-108 AC5)."""
    decision: SafetyDecisionKind
    reason_label: str
    organiser_comment: str | None = None
    decided_at: datetime

class EventSpaceVenueBooking(EventVenueBooking):
    pass


class HistoryActor(BaseModel):
    id: str
    full_name: str


class FieldChange(BaseModel):
    """One proposed field change (story 32, CR-R16). `before` is read from the database,
    never from the client."""

    field: str
    before: object = None
    after: object = None


class SpaceChange(BaseModel):
    space_id: str
    label: str | None = None
    fields: list[FieldChange]


class EventChanges(BaseModel):
    event: list[FieldChange] = []
    spaces: list[SpaceChange] = []


class EventChangeRequest(BaseModel):
    """A change or cancellation request on an event (REQUIREMENTS §6.19). Story 84
    builds the cancellation kind; story 32 adds the change kind, with its proposed
    `changes` and whether any of them is `significant` (§6.7)."""

    id: str
    kind: str
    status: str
    reason: str
    changes: EventChanges | None = None
    significant: bool | None = None
    requested_by: HistoryActor | None = None
    requested_at: datetime

    @model_serializer(mode="wrap")
    def _omit_change_fields_on_cancellations(self, handler):
        # A cancellation request has no proposed changes; keep its shape as story 84 built it.
        data = handler(self)
        if self.kind != "change":
            data.pop("changes", None)
            data.pop("significant", None)
        return data


class EventResponse(EventFields):
    id: str
    organiser_id: str
    coordinator_id: str | None = None
    # Named on the single-event read; null when unassigned and on other responses.
    coordinator: EventCoordinator | None = None
    # Named on the single-event read (SCRUM-49 AC3); null on other responses.
    organiser: EventOrganiser | None = None
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
    # CR-110 AC4 on the single-event read: the assigned coordinator gets the stage
    # and note once the event is Confirmed (and keeps them after a return to
    # Planning); the organiser gets the stage only, while Confirmed or in
    # Preparation. Null otherwise and on list responses.
    technical_preparation: TechnicalPreparation | TechnicalPreparationStage | None = None
    # Bookings venue staff rejected, with their reason and suggestion, on the
    # assigned coordinator's single-event read only (SCRUM-38 AC6, AC7).
    rejected_bookings: list[EventRejectedBooking] = []
    safety_readiness: SafetyReadiness | None = None
    latest_safety_decision: SafetyDecision | SafetyDecisionSummary | None = None
    # Story 84: the open cancellation request, on a single-event read only.
    open_cancellation_request: EventChangeRequest | None = None
    open_change_request: EventChangeRequest | None = None  # story 32
    # CR-106: the assigned coordinator's own open reassignment request, on their read only.
    open_reassignment_request: EventChangeRequest | None = None
    venue_bookings: list[EventSpaceVenueBooking] = []


class EventListResponse(BaseModel):
    events: list[EventResponse]


REJECT_REASON_MAX_LENGTH = 1000  # [Assumption] REQUIREMENTS §9; no customer limit given


class BookingImpact(BaseModel):
    """Story 37 Q1: what approving the open change would do to one venue booking."""

    booking_id: str
    venue_name: str
    space_label: str | None = None
    messages: list[str]


class EquipmentShortfall(BaseModel):
    line_id: str
    label: str | None = None
    needed: int
    free: int


class ChangeImpact(BaseModel):
    """Story 37 Q1, CR-R2: worked out from the event as it is now, never stored."""

    bookings: list[BookingImpact] = []
    equipment: list[EquipmentShortfall] = []
    attendees_notified: int = 0


class ReReviewSendRequest(BaseModel):
    """Story 37 Q20: the coordinator's optional note to staff when sending an arrangement
    for re-review. Trimmed; blank is no note."""

    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note", mode="before")
    @classmethod
    def blank_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class ChangeApproveRequest(BaseModel):
    """Story 37: the event version the coordinator saw when they approved (Q8)."""

    version: int


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


class EventHistoryEntry(BaseModel):
    """One line of an event's history: a status change, or a reassignment (SCRUM-12), which
    is not a status change and so carries the two coordinators instead of statuses, or a
    cancellation request (story 84, `cancellation_requested`), which carries only who asked
    and why, or a change request (story 32, `change_requested`), which also carries the
    proposed `changes`, and its closing (`change_request_closed`) when it was superseded."""

    id: str
    kind: str = "status"
    from_status: EventStatus | None = None
    to_status: EventStatus | None = None
    from_coordinator: HistoryActor | None = None
    to_coordinator: HistoryActor | None = None
    actor: HistoryActor | None = None
    reason: str | None = None
    changes: EventChanges | None = None
    # Story 62: an edit (`edit`) names the field and its old and new value.
    field: str | None = None
    old_value: Any = None
    new_value: Any = None
    # A safety decision (`safety_decision`) names its outcome; its `reason` is the organiser
    # comment and `private_note` the officer's private note, which only staff are given (CR-108).
    decision: str | None = None
    private_note: str | None = None
    # A venue booking's step (`booking`) names what happened and at which venue.
    action: str | None = None
    venue_name: str | None = None
    # A technical update (`technical`) names its action, the equipment line, if any, and its detail.
    line_label: str | None = None
    detail: str | None = None
    at: datetime

    @model_serializer(mode="wrap")
    def _omit_changes_outside_change_requests(self, handler):
        # Only change-request entries and approvals (story 37) have changes, and only
        # edits (story 62) have a field; the others keep their shape.
        data = handler(self)
        if not (self.kind.startswith("change_request") or self.kind == "change_approved"):
            data.pop("changes", None)
        # A venue edit (`venue_edit`) carries the venue's before and after snapshots.
        if self.kind != "edit":
            data.pop("field", None)
        if self.kind not in ("edit", "venue_edit"):
            data.pop("old_value", None)
            data.pop("new_value", None)
        if self.kind != "safety_decision":
            data.pop("decision", None)
        if data.get("private_note") is None:
            data.pop("private_note", None)
        if self.kind not in ("booking", "technical"):
            data.pop("action", None)
        if self.kind not in ("booking", "venue_edit"):
            data.pop("venue_name", None)
        if self.kind != "technical":
            data.pop("line_label", None)
            data.pop("detail", None)
        return data


class EventHistoryResponse(BaseModel):
    entries: list[EventHistoryEntry]


CANCELLATION_REASON_MAX_LENGTH = 1000  # [Assumption] REQUIREMENTS §9; same cap as a rejection reason


class CancellationRequestCreate(BaseModel):
    """Story 84 AC1: the organiser's reason for asking to cancel."""

    reason: str = Field(max_length=CANCELLATION_REASON_MAX_LENGTH)

    @field_validator("reason", mode="before")
    @classmethod
    def reason_is_not_blank(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("A cancellation reason is required.")
        return value.strip()


class EventCancelRequest(CancellationRequestCreate):
    """Story 115 AC3: the coordinator's reason for cancelling without a request."""


REASSIGNMENT_REASON_MAX_LENGTH = CANCELLATION_REASON_MAX_LENGTH  # [Assumption] REQUIREMENTS §9; same cap as the other reasons


class ReassignmentRequestCreate(BaseModel):
    """CR-106 AC1: the coordinator's reason for asking the Lead to reassign the event."""

    reason: str = Field(max_length=REASSIGNMENT_REASON_MAX_LENGTH)

    @field_validator("reason", mode="before")
    @classmethod
    def reason_is_not_blank(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("A reason for the reassignment request is required.")
        return value.strip()


class SpaceChangeProposal(BaseModel):
    """Story 32: proposed values for one of the event's existing spaces. Adding or
    removing a space is out of scope (CR-R16)."""

    id: UUID
    label: str | None = Field(default=None, min_length=1, max_length=150)
    expected_pax: int | None = Field(default=None, ge=1)
    layout_preference: VenueLayout | None = None
    facilities_required: list[Facility] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class ChangeRequestCreate(CancellationRequestCreate):
    """Story 32 AC1: the organiser's proposed values and why. Only the fields sent are
    proposed; `version` is the event version the form was filled in against."""

    version: int
    event: EventUpdateRequest = EventUpdateRequest()
    spaces: list[SpaceChangeProposal] = []

    @field_validator("reason", mode="before")
    @classmethod
    def reason_is_not_blank(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("A reason for the change is required.")
        return value.strip()

    @model_validator(mode="after")
    def withdrawal_cutoff_is_not_changeable(self):
        if "withdrawal_closes_at" in self.event.model_fields_set:
            raise ValueError("Withdrawal cutoff cannot be changed through an event change request.")
        return self


# SCRUM-72: the Event Coordinator dashboard. The SPA's store
# (`frontend/src/features/events/store.js`) fixed this shape first, and it does
# the ranking itself, so action items are returned unordered.


class CoordinatorActionKind(str, Enum):
    """The action kinds the server can produce today. The SPA's `ACTION_KINDS`
    lists more (change requests, booking and equipment decisions, re-review
    outcomes); those arrive with the stories that build their data, and until
    then their widgets stay empty (REQUIREMENTS §6.21)."""

    needs_alternative_venue = "needs_alternative_venue"
    arrangement_issue = "arrangement_issue"
    cancellation_request = "cancellation_request"
    change_request = "change_request"
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


class CoordinatorRejectedEvent(BaseModel):
    """A request the coordinator rejected: closed, so no readiness or actions."""

    event_id: str
    event_name: str
    starts_at: datetime | None = None


class CoordinatorDashboard(BaseModel):
    action_items: list[CoordinatorActionItem] = []
    active_events: list[CoordinatorActiveEvent] = []
    rejected_events: list[CoordinatorRejectedEvent] = []
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
    # Queue entries (SCRUM-12 AC10): when it was submitted, and what it needs from a venue.
    submitted_at: datetime | None = None
    layout_preference: VenueLayout | None = None
    facilities_required: list[Facility] = []
    # The Lead sends it back on reassign, so a screen that is behind can't overwrite a newer change.
    version: int
    # CR-106 AC2: the coordinator's open request that the Lead reassign the event.
    open_reassignment_request: EventChangeRequest | None = None


class LeadDashboard(BaseModel):
    """CR-101: the Event Coordinator Lead's view. `unassigned` is the shared queue;
    `active_events` are the assigned events in this Lead's scope (AC5)."""

    unassigned: list[LeadEvent] = []
    active_events: list[LeadEvent] = []
    coordinators: list[LeadCoordinator] = []


class EventAssignRequest(BaseModel):
    coordinator_id: UUID


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
    organiser_comment: str | None = None
    private_note: str | None = None
    decided_by_name: str | None = None
    decided_at: datetime

    affected_bookings: list[NamedBooking] = []
    affected_equipment: list[NamedEquipmentLine] = []
    rejected_venues: list[NamedVenue] = []
    revision: SafetyRevision | None = None

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
