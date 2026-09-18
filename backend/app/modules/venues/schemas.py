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


class VenueDetail(VenueSummary):
    upcoming_blocks: list[BlockSummary] = []
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
    # There is no `events` table yet, so `event_id` is a bare uuid with nothing
    # to join to. The field is declared now and left None so SCRUM-8/19 can fill
    # it in without an SPA change — the same contract-first move the coordinator
    # dashboard made. The SPA falls back to a short id and never invents a name.
    event_name: str | None = None


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
