"""Venue module schemas: controlled lists, search criteria and result shapes.

The enums mirror the Postgres enums created by the SCRUM-39 migration; keep
the two in step (REQUIREMENTS §6.8 lists the values as a [Team decision]).
"""

from datetime import datetime, time
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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


class Occupant(BaseModel):
    """Something that occupies a venue for a period: an occupying booking
    (`detail` = its status) or a block (`detail` = its reason)."""

    kind: Literal["booking", "block"]
    period: Period
    detail: str


class BlockSummary(BaseModel):
    id: str
    period: Period
    reason: str
    notes: str | None = None


class BookingSummary(BaseModel):
    id: str
    event_id: str
    period: Period
    status: str
    # Resolved through `events.service.names_by_id`, because `venue_bookings`
    # has no foreign key to `events` and so cannot embed the name in one query.
    # Null when the event row has gone: a booking with no name is still a
    # booking staff must plan around, so it is shown with a short id rather
    # than dropped.
    event_name: str | None = None


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
    # venue_bookings.created_at. Holds never expire (BR-R4), so how long one has
    # been waiting is the only nudge the system gives, and the dashboard sorts
    # on it (§6.21). That makes it part of the contract, not a display detail.
    requested_at: datetime
    # `event_name` is inherited from `BookingSummary`. The dashboard does not
    # resolve it yet, so it stays null here and the SPA falls back to a short
    # id; `venues.service.get_venue` shows how to fill it (SCRUM-67).


class VenueStaffDashboard(BaseModel):
    """Everything the venue-staff work queue needs, in one round trip (§6.21).

    There is deliberately no `counts` field. Each list below is complete —
    nothing paginates — so a server-side count would be a second source of
    truth that could disagree with the list rendered beside it. The SPA derives
    its tiles from the lists.
    """

    generated_at: datetime
    venues: list[VenueSummary] = []
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


class AffectedBooking(BaseModel):
    """A booking whose event has a new problem because of this edit (VC-R2)."""

    booking_id: str
    event_id: str
    event_name: str | None = None
    period: Period
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
