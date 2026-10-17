"""Venue module schemas: controlled lists, search criteria and result shapes.

The enums mirror the Postgres enums created by the SCRUM-39 migration; keep
the two in step (REQUIREMENTS §6.8 lists the values as a [Team decision]).
"""

from datetime import datetime, time
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator


class VenueLayout(str, Enum):
    theatre = "theatre"
    classroom = "classroom"
    boardroom = "boardroom"
    banquet = "banquet"
    u_shape = "u_shape"
    reception = "reception"


class Facility(str, Enum):
    projector = "projector"
    sound_system = "sound_system"
    microphone = "microphone"
    video_conferencing = "video_conferencing"
    whiteboard = "whiteboard"
    stage = "stage"
    wifi = "wifi"
    catering_space = "catering_space"


class AccessibilityFeature(str, Enum):
    wheelchair_access = "wheelchair_access"
    step_free_entry = "step_free_entry"
    accessible_toilet = "accessible_toilet"
    hearing_loop = "hearing_loop"
    lift_access = "lift_access"


class VenueInactiveReason(str, Enum):
    """Why venue staff deactivated a venue (SCRUM-64 AC1). Mirrors
    `public.venue_inactive_reason`."""

    permanently_closed = "permanently_closed"
    long_term_renovation = "long_term_renovation"
    other = "other"


INACTIVE_REASON_LABELS = {
    VenueInactiveReason.permanently_closed: "Permanently closed",
    VenueInactiveReason.long_term_renovation: "Long-term renovation",
    VenueInactiveReason.other: "Other",
}


class Availability(str, Enum):
    available = "available"
    unavailable = "unavailable"
    not_checked = "not_checked"


class ReasonCode(str, Enum):
    inactive = "inactive"
    capacity_below_minimum = "capacity_below_minimum"
    layout_not_supported = "layout_not_supported"
    missing_facility = "missing_facility"
    missing_accessibility_feature = "missing_accessibility_feature"
    location_mismatch = "location_mismatch"
    blocked = "blocked"
    held = "held"
    booked = "booked"


# Setup/turnaround between consecutive bookings, in minutes. The customer set
# it to zero (QA-28, QA-82, QA-103), so back-to-back bookings are allowed and
# no availability check applies a buffer (VS-R1, §6.14). It is a named constant
# served on the venue profile rather than a number the SPA hard-codes, so the
# day the customer asks for a real buffer, this is the one place it changes
# (REQUIREMENTS §8, "a future rule plugs into §6.11 and §6.14").
TURNAROUND_MINUTES = 0


def label(value: str | Enum) -> str:
    """Human wording for an enum value: `sound_system` -> `sound system`."""
    raw = value.value if isinstance(value, Enum) else value
    return raw.replace("_", " ")


class Period(BaseModel):
    """A half-open interval [starts_at, ends_at); both ends timezone-aware."""

    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def _check_bounds(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("starts_at and ends_at must include a timezone offset")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self

    def overlaps(self, other: "Period") -> bool:
        # Half-open ranges: touching at the boundary is not an overlap (§6.14).
        return self.starts_at < other.ends_at and other.starts_at < self.ends_at


class LayoutOption(BaseModel):
    layout: VenueLayout
    capacity_for_layout: int | None = None


class VenueSummary(BaseModel):
    id: str
    name: str
    location: str
    capacity: int
    layouts: list[LayoutOption] = []
    facilities: list[Facility] = []
    accessibility_features: list[AccessibilityFeature] = []
    opens_at: time
    closes_at: time
    is_active: bool
    description: str | None = None
    # Set exactly when the venue is inactive (SCRUM-64 AC1).
    inactive_reason: VenueInactiveReason | None = None
    inactive_note: str | None = None


class Occupant(BaseModel):
    """Something that occupies a venue for a period: an occupying booking
    (`detail` = its status) or a block (`detail` = its reason)."""

    kind: Literal["booking", "block"]
    period: Period
    detail: str


class BookingConflict(BaseModel):
    """What refused a booking request (SCRUM-21 AC2): another event's booking,
    named by the event only, or a block with its reason. The window is the one
    it occupies, setup to turnaround."""

    kind: Literal["booking", "block"]
    event_name: str | None = None
    block_reason: str | None = None
    starts_at: AwareDatetime
    ends_at: AwareDatetime


class BlockSummary(BaseModel):
    id: str
    period: Period
    reason: str
    notes: str | None = None


class BookingSummary(BaseModel):
    id: str
    event_id: str
    event_space_request_id: str | None = None
    period: Period
    status: str
    event_name: str | None = None
    coordinator_name: str | None = None
    requested_by_name: str | None = None
    decision_reason: str | None = None
    suggestion: str | None = None
    decided_at: datetime | None = None


class Editor(BaseModel):
    """Whoever last edited a venue profile (SCRUM-67 AC2).

    `full_name` may be null: `profiles` allows it, and the caller is shown the
    fact rather than a fabricated name.
    """

    id: str
    full_name: str | None = None


class VenueProfile(VenueSummary):
    """A venue read for its own profile page: the catalogue fields plus the
    audit stamp (SCRUM-67 AC2).

    Kept off `VenueSummary` on purpose. That shape is also a search result and
    a venue-staff dashboard row, where "who last edited this" is noise, and
    reading it there would cost a `profiles` embed on every venue in the
    catalogue for something no one looks at.
    """

    updated_at: datetime
    # Null until the venue is edited through a path that records the editor
    # (SCRUM-63/64), or when that account has since been removed.
    updated_by: Editor | None = None
    # Optimistic concurrency (DB-5), same pattern as `events.version`: an edit
    # reads this, then writes conditioned on it being unchanged (SCRUM-63).
    version: int = 0


class VenuePhoto(BaseModel):
    """One image in the venue profile's carousel.

    Declared now, populated by nothing. There is no `venue_photos` table and
    no storage bucket on the project, so `VenueDetail.photos` is always empty
    and the SPA renders an empty state. The field exists so the carousel is
    built against the real shape and starts working the day photos are added,
    without another SPA change — the same contract-first move `event_name`
    made for the venue-staff dashboard. Stock imagery is deliberately not used:
    this page's job is letting staff verify *current* information.
    """

    url: str
    caption: str | None = None


class VenueDetail(VenueProfile):
    # Stated on the profile so venue staff can see the rule they are planning
    # against, instead of inferring it from bookings that sit back-to-back.
    turnaround_minutes: int = TURNAROUND_MINUTES
    photos: list[VenuePhoto] = []
    upcoming_blocks: list[BlockSummary] = []
    # Every booking that occupies the venue (§6.14): `approved` (confirmed),
    # `held` (tentative) and `re_review`. Deliberately one list with a status
    # on each row, not three server-side buckets — the same reasoning as
    # `VenueStaffDashboard` below, where grouping and counting a complete list
    # belongs to the reader, not to a second source of truth.
    upcoming_bookings: list[BookingSummary] = []


class VenueStaffBlock(BlockSummary):
    """A block seen from the venue-staff queue, which spans every venue.

    `BlockSummary` is always read in the context of one venue, so it has no
    need to name it; here the venue is the first thing staff read off the row.
    """

    venue_id: str
    venue_name: str


class VenueStaffBooking(BookingSummary):
    venue_id: str
    venue_name: str
    # venue_bookings.created_at: how long the request has been waiting.
    requested_at: datetime
    # When a hold expires unless approved (CR-99). The dashboard sorts pending
    # holds on it, soonest first. Null on a booking that was never held.
    expires_at: datetime | None = None
    # `event_name`, `coordinator_name` and decision metadata are resolved by
    # the complete dashboard history query; the SPA only falls back to an id
    # when an event row is genuinely unavailable.


class VenueStaffDashboard(BaseModel):
    """Everything the venue-staff work queue needs, in one round trip (§6.21).

    There is deliberately no `counts` field. Each list below is complete —
    nothing paginates — so a server-side count would be a second source of
    truth that could disagree with the list rendered beside it. The SPA derives
    its tiles from the lists.
    """

    generated_at: datetime
    venues: list[VenueSummary] = []
    booking_requests: list[VenueStaffBooking] = []
    pending_holds: list[VenueStaffBooking] = []
    re_review_bookings: list[VenueStaffBooking] = []
    blocks: list[VenueStaffBlock] = []


class VenueSearchCriteria(BaseModel):
    """What the coordinator is searching for. Every criterion set is strict:
    a venue that misses it is excluded, with the reason recorded (§6.10)."""

    starts_at: datetime | None = None
    ends_at: datetime | None = None
    min_capacity: int | None = Field(default=None, ge=1)
    location: str | None = Field(default=None, max_length=255)
    layout: VenueLayout | None = None
    facilities: list[Facility] = []
    accessibility: list[AccessibilityFeature] = []
    include_excluded: bool = False

    @model_validator(mode="after")
    def _check_period(self):
        if (self.starts_at is None) != (self.ends_at is None):
            raise ValueError("starts_at and ends_at must be given together")
        if self.starts_at is not None:
            # Period's own validator enforces timezone-aware, ends > starts.
            Period(starts_at=self.starts_at, ends_at=self.ends_at)
        if self.location is not None and not self.location.strip():
            self.location = None
        return self

    @property
    def period(self) -> Period | None:
        if self.starts_at is None:
            return None
        return Period(starts_at=self.starts_at, ends_at=self.ends_at)


class Reason(BaseModel):
    code: ReasonCode
    message: str


class VenueRequirements(BaseModel):
    """What one event (or one of its spaces) needs from a venue, as
    `suitability.check` judges it. Every field is optional: a requirement the
    event did not state is never held against a venue."""

    expected_attendance: int | None = None
    layout_preference: VenueLayout | None = None
    facilities_required: list[Facility] = []
    period: Period | None = None


class SuitabilityVerdict(str, Enum):
    suitable = "suitable"
    suitable_with_warnings = "suitable_with_warnings"
    unsuitable = "unsuitable"


class SuitabilitySeverity(str, Enum):
    unsuitable = "unsuitable"
    warning = "warning"


class SuitabilityCode(str, Enum):
    capacity = "capacity"
    missing_facility = "missing_facility"
    layout_not_supported = "layout_not_supported"
    outside_operating_hours = "outside_operating_hours"
    # Edit-only (CR-94): set by `venues.impact`, never by `suitability.check`.
    accessibility_changed = "accessibility_changed"


class SuitabilityReason(BaseModel):
    code: SuitabilityCode
    severity: SuitabilitySeverity
    message: str


class SuitabilityResult(BaseModel):
    verdict: SuitabilityVerdict
    reasons: list[SuitabilityReason] = []


class BookingImpactContext(BaseModel):
    """One occupying booking plus the event fields needed to judge whether an
    edit to the venue (VC-R2) newly breaks something that booking relies on.

    Assembled by `venues.service` from its own `BookingSummary` plus
    `events.service.planning_context_by_id` — the cross-module lookup, never
    a direct read of the events table (REQUIREMENTS §3.3 module rules).
    """

    booking_id: str
    event_id: str
    event_name: str | None = None
    coordinator_id: str | None = None
    period: Period
    expected_attendance: int | None = None
    layout_preference: VenueLayout | None = None
    facilities_required: list[Facility] = []
    accessibility_needs: str | None = None


class AffectedBooking(BaseModel):
    """A booking whose event has a new problem because of this edit (VC-R2).

    `outcome` is `unsuitable` when any newly broken rule is a hard one
    (capacity, a required facility), otherwise `warning` (CR-94). `reasons`
    repeats the `details` messages for callers that only show text.
    """

    booking_id: str
    event_id: str
    event_name: str | None = None
    period: Period
    outcome: Literal["unsuitable", "warning"]
    details: list[SuitabilityReason] = []
    reasons: list[str]


class VenueUpdateRequest(BaseModel):
    """The full venue-edit form (SCRUM-63), not a partial patch: venue staff
    see every field pre-filled and submit the whole record, so this mirrors
    the table's own constraints directly rather than merging deltas onto a
    freshly-read row. `is_active` is excluded — SCRUM-64 (deactivate/
    reactivate) owns that switch.
    """

    name: str = Field(min_length=1, max_length=150)
    location: str = Field(min_length=1, max_length=255)
    capacity: int = Field(gt=0)
    layouts: list[LayoutOption] = []
    facilities: list[Facility] = []
    accessibility_features: list[AccessibilityFeature] = []
    opens_at: time
    closes_at: time
    description: str | None = None
    # Set once the caller has seen the warnings below and still wants to save
    # (VC-R2: "resolution is manual" — a warning never blocks the edit).
    confirm: bool = False

    @model_validator(mode="after")
    def _check_hours(self):
        if self.closes_at <= self.opens_at:
            raise ValueError("closes_at must be after opens_at")
        return self


class VenueUpdateResponse(BaseModel):
    """`saved=False` means nothing was written: `warnings` named at least one
    newly-affected booking and the caller had not yet set `confirm=true`."""

    saved: bool
    venue: VenueDetail | None = None
    warnings: list[AffectedBooking] = []


class VenueEditHistoryEntry(BaseModel):
    """One saved edit (VC-R3): the whole before/after snapshot of whatever
    fields changed, who changed it, and when."""

    id: str
    actor: Editor | None = None
    before: dict
    after: dict
    at: datetime


class VenueEditHistoryResponse(BaseModel):
    entries: list[VenueEditHistoryEntry] = []


class VenueSearchResult(BaseModel):
    venue: VenueSummary
    availability: Availability
    excluded: bool
    reasons: list[Reason] = []


class VenueSearchResponse(BaseModel):
    criteria: VenueSearchCriteria
    results: list[VenueSearchResult]
    included_count: int
    excluded_count: int


BOOKING_NOTE_MAX_LENGTH = 1000  # [Assumption] REQUIREMENTS §9; same cap as the other free-text fields


class VenueBookingCreate(BaseModel):
    """A coordinator's booking request.

    `event_id` remains accepted for the legacy single-space flow while new
    callers identify the organiser's requested space explicitly.
    """

    event_id: UUID | None = None
    event_space_request_id: UUID | None = None
    venue_id: UUID
    note: str | None = Field(default=None, max_length=BOOKING_NOTE_MAX_LENGTH)
    # CR-95 AC4: the affected booking this request replaces.
    replaces_booking_id: UUID | None = None

    @field_validator("note", mode="before")
    @classmethod
    def _blank_note_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def _has_event_or_space(self):
        if self.event_id is None and self.event_space_request_id is None:
            raise ValueError("event_id or event_space_request_id is required")
        return self


class VenueBooking(BaseModel):
    id: str
    event_id: str
    event_space_request_id: str | None = None
    venue_id: str
    status: str
    note: str | None = None


class HoldExpiryUpdate(BaseModel):
    """Venue staff's new expiry for a hold (CR-99 AC2). Must carry its offset:
    a bare local time would be read in the server's zone, not Singapore's."""

    expires_at: AwareDatetime


class HoldExpiry(BaseModel):
    id: str
    status: str
    expires_at: datetime

class VenueBookingReject(BaseModel):
    """Venue staff's rejection of a held booking (SCRUM-38 AC2, AC3). Both
    texts are trimmed first, so the limits count what is stored."""

    reason: str = Field(min_length=1, max_length=BOOKING_NOTE_MAX_LENGTH)
    suggestion: str | None = Field(default=None, max_length=BOOKING_NOTE_MAX_LENGTH)

    @field_validator("reason", mode="before")
    @classmethod
    def _trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("suggestion", mode="before")
    @classmethod
    def _blank_suggestion_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class BookingEventRequirements(BaseModel):
    """What the booking's event needs from a venue (SCRUM-38 AC1)."""

    id: str
    name: str | None = None
    status: str | None = None
    expected_attendance: int | None = None
    layout_preference: VenueLayout | None = None
    facilities_required: list[Facility] = []
    accessibility_needs: str | None = None


class BookingDecision(BaseModel):
    """Venue staff's latest decision on a booking. Internal: shown to venue
    staff and the assigned coordinator only (AC6, AUTH-R2)."""

    reason: str
    suggestion: str | None = None
    decided_by_name: str | None = None
    decided_at: datetime


class BookingHistoryEntry(BaseModel):
    """One change to a booking, from CR-99's `venue_booking_history` (AC12)."""

    action: str
    from_status: str | None = None
    to_status: str | None = None
    actor_name: str | None = None
    reason: str | None = None
    suggestion: str | None = None
    at: datetime


class VenueBookingDetail(BaseModel):
    """One booking request as venue staff decide on it (SCRUM-38 AC1; SCRUM-36's
    approval reads the same page)."""

    id: str
    status: str
    venue_id: str
    venue_name: str | None = None
    period: Period
    request_note: str | None = None
    requested_at: datetime
    requested_by_name: str | None = None
    event: BookingEventRequirements
    decision: BookingDecision | None = None
    history: list[BookingHistoryEntry] = []


class VenueDeactivateRequest(BaseModel):
    """Deactivate a venue (SCRUM-64 AC1). `version` is the one the page
    loaded, so staff never deactivate a venue someone else just changed."""

    reason: VenueInactiveReason
    note: str | None = Field(default=None, max_length=500)
    version: int
    confirm: bool = False

    @model_validator(mode="after")
    def _note_rules(self):
        self.note = (self.note or "").strip() or None
        if self.reason is VenueInactiveReason.other and self.note is None:
            raise ValueError("A note is required when the reason is Other.")
        return self


class FlaggableBooking(BaseModel):
    """A future booking that deactivating the venue would flag Affected (AC3)."""

    booking_id: str
    event_id: str
    event_name: str | None = None
    period: Period
    status: Literal["held", "approved"]


class VenueDeactivateResponse(BaseModel):
    """`saved=False` means nothing was written: `affected` lists the bookings
    that would be flagged and the caller had not yet set `confirm=true`."""

    saved: bool
    venue: VenueDetail | None = None
    affected: list[FlaggableBooking] = []


class VenueReactivateRequest(BaseModel):
    version: int
