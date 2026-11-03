from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.events.schemas import ReReviewSendRequest
from app.modules.venues import service
from app.modules.venues.schemas import (
    SafetyRevisionRequest,
    HoldExpiry,
    HoldExpiryUpdate,
    VenueBooking,
    VenueBookingCreate,
    VenueBookingDetail,
    VenueBookingReject,
    VenueBlockChange,
    VenueBlockChangeResponse,
    VenueBlockCreate,
    VenueBlockResponse,
    VenueDeactivateRequest,
    VenueDeactivateResponse,
    VenueDetail,
    VenueEditHistoryResponse,
    VenueReactivateRequest,
    VenueSearchCriteria,
    VenueSearchResponse,
    VenueStaffDashboard,
    VenueUpdateRequest,
    VenueUpdateResponse,
)

router = APIRouter(prefix="/venues", tags=["venues"])

# Access matrix (REQUIREMENTS §2): coordinators read and search the catalogue,
# venue staff manage it; organisers, attendees and tech support see nothing.
# A plain search is not tied to an event, so it needs no per-resource check.
# Naming an `event_id` or `space_id` (SCRUM-18) does: `service.search_venues`
# then requires the event's assigned coordinator, acting as coordinator.
VenueReader = Annotated[CurrentUser, Depends(require_roles(["event_coordinator", "venue_staff"]))]

# The dashboard is a venue-staff work queue, so a coordinator is excluded even
# though it may read and search the catalogue above.
#
# There is deliberately no per-resource ownership filter behind this guard.
# The security baseline asks for "the caller's relationship to the resource",
# and here that relationship is *every venue*, by rule: venue staff work as a
# pool and staff-to-venue allocation is not tracked (AUTH-R5, QA-44,
# REQUIREMENTS §6.21). Stated so the absence reads as a decision, not an
# oversight.
VenueStaffOnly = Annotated[CurrentUser, Depends(require_roles(["venue_staff"]))]
# CR-104: only the assigned coordinator marks a Safety-rejected booking revised.
CoordinatorOnly = Annotated[CurrentUser, Depends(require_roles(["event_coordinator"]))]

# Endpoints are plain `def`: supabase-py is synchronous, so FastAPI runs them
# in its threadpool instead of blocking the event loop.


@router.get("", response_model=VenueSearchResponse, status_code=status.HTTP_200_OK)
def search_venues(
    criteria: Annotated[VenueSearchCriteria, Query()],
    current_user: VenueReader,
) -> VenueSearchResponse:
    """Search the venue catalogue.

    With no criteria this lists every active venue. Each criterion given is
    strict; `starts_at`/`ends_at` (ISO 8601 with offset, given together) add
    an availability check against holds, bookings and blocks. Pass
    `include_excluded=true` to also return the venues that were ruled out,
    each with its reasons. Name an `event_id` and/or `space_id` (assigned
    coordinator only, else 403) to add each venue's `suitability` for that
    event or space (SCRUM-18); availability stays a separate answer.
    """
    return service.search_venues(criteria, current_user)


# Declared before `/{venue_id}`. This particular path is safe either way, since
# a two-segment path can't match a one-segment route, but `/{venue_id}` is typed
# `UUID` and FastAPI does not fall through on a validation failure: a future
# single-segment literal like `/venues/export` placed below it would answer 422
# rather than reach its own handler. Keep new literal paths above.
@router.get("/dashboard/venue-staff", response_model=VenueStaffDashboard, status_code=status.HTTP_200_OK)
def read_venue_staff_dashboard(current_user: VenueStaffOnly) -> VenueStaffDashboard:
    """The venue-staff work queue, across every venue.

    Returns pending holds (oldest first), bookings awaiting re-review, active
    and upcoming blocks, and the venue catalogue with each venue's active flag
    (REQUIREMENTS §6.21).
    """
    return service.venue_staff_dashboard()


@router.get("/{venue_id}", response_model=VenueDetail, status_code=status.HTTP_200_OK)
def read_venue(venue_id: UUID, current_user: VenueReader) -> VenueDetail:
    """One venue with its upcoming blocks and occupying bookings. Who set or
    changed a block is shown only to a session acting as Venue Staff (SCRUM-54 AC9)."""
    return service.get_venue(str(venue_id), manages_blocks=current_user.role == "venue_staff")


@router.patch("/{venue_id}", response_model=VenueUpdateResponse, status_code=status.HTTP_200_OK)
def update_venue(venue_id: UUID, body: VenueUpdateRequest, current_user: VenueStaffOnly) -> VenueUpdateResponse:
    """Edit a venue's details (SCRUM-63; QA-101: venue staff manage the catalogue).

    `saved` is `false` without `confirm: true` when the edit would newly
    affect an upcoming booking (VC-R2) — nothing is written in that case, so
    the SPA can show the warning and let staff decide. `409` means the
    venue's `version` had already moved on (DB-5); reload and retry.
    """
    return service.update_venue(str(venue_id), current_user.id, body)


@router.post("/{venue_id}/deactivate", response_model=VenueDeactivateResponse, status_code=status.HTTP_200_OK)
def deactivate_venue(
    venue_id: UUID, body: VenueDeactivateRequest, current_user: VenueStaffOnly
) -> VenueDeactivateResponse:
    """Mark a venue inactive with a reason (SCRUM-64 AC1, AC3).

    `saved` is `false` without `confirm: true` when the venue has future held
    or approved bookings: `affected` lists the ones that would be flagged
    Affected, and nothing is written. `409` means the venue is already
    inactive or its `version` had moved on.
    """
    return service.deactivate_venue(str(venue_id), current_user.id, body)


@router.post("/{venue_id}/blocks", response_model=VenueBlockResponse, status_code=status.HTTP_200_OK)
def create_block(venue_id: UUID, body: VenueBlockCreate, current_user: VenueStaffOnly) -> VenueBlockResponse:
    """Block a venue for a period with a reason (SCRUM-51 AC1). Any user
    acting as Venue Staff may block any venue (AUTH-R5).

    `saved` is `false` without `confirm: true` when the block overlaps held or
    approved bookings: `affected` lists them and nothing is written. Once
    saved, `affected` lists the bookings flagged and recorded against the
    block (AC5, AC6). `422` names the problem with the period or reason.
    """
    return service.create_block(str(venue_id), current_user.id, body)


@router.post("/{venue_id}/blocks/{block_id}/change", response_model=VenueBlockChangeResponse,
             status_code=status.HTTP_200_OK)
def change_block(venue_id: UUID, block_id: UUID, body: VenueBlockChange,
                 current_user: VenueStaffOnly) -> VenueBlockChangeResponse:
    """End a block now, shorten it, or remove one that hasn't started
    (SCRUM-54 AC2), with an optional note. The block is kept, with its original
    period in the venue's history (AC4). `restorable` lists the bookings it had
    flagged that no block covers any more, for venue staff to restore (AC5).
    `409` means the block has ended, was removed, or has (or hasn't) started;
    `422` names the problem with the new end or the note."""
    return service.change_block(str(venue_id), str(block_id), current_user.id, body)


@router.post("/{venue_id}/reactivate", response_model=VenueDetail, status_code=status.HTTP_200_OK)
def reactivate_venue(venue_id: UUID, body: VenueReactivateRequest, current_user: VenueStaffOnly) -> VenueDetail:
    """Make an inactive venue bookable again (SCRUM-64 AC4). Bookings flagged
    when it was deactivated stay flagged. `409` means the venue is already
    active or its `version` had moved on."""
    return service.reactivate_venue(str(venue_id), current_user.id, body)


@router.get("/{venue_id}/history", response_model=VenueEditHistoryResponse, status_code=status.HTTP_200_OK)
def read_venue_history(venue_id: UUID, current_user: VenueReader) -> VenueEditHistoryResponse:
    """Every saved edit to this venue, newest first (VC-R3)."""
    return service.venue_history(str(venue_id))


# Booking requests sit in the venues module, which owns `venue_bookings`, under
# their own path so SCRUM-20 can add `/venue-bookings/{id}/approve` beside them.
bookings_router = APIRouter(prefix="/venue-bookings", tags=["venue bookings"])

# Only a coordinator requests a venue (REQUIREMENTS §2), gated on the session's
# active role; the service then checks it is *this event's* coordinator.
BookingRequester = Annotated[CurrentUser, Depends(require_roles(["event_coordinator"]))]


@bookings_router.post("", response_model=VenueBooking, status_code=status.HTTP_201_CREATED)
def request_venue_booking(body: VenueBookingCreate, current_user: BookingRequester) -> VenueBooking:
    """Request a venue for a planning event: a tentative hold over the event's
    own period, and venue staff are notified. Refused with 409 when the venue
    is held, booked or blocked for that time, the event already has a venue,
    or the event isn't in planning."""
    return service.request_booking(body, current_user.id)


@bookings_router.patch("/{booking_id}/expiry", response_model=HoldExpiry, status_code=status.HTTP_200_OK)
def change_hold_expiry(booking_id: UUID, body: HoldExpiryUpdate, current_user: VenueStaffOnly) -> HoldExpiry:
    """Change or extend a tentative hold's expiry (CR-99 AC2). It must be in the
    future and no later than the event start; 409 once the hold has expired or
    is no longer a hold."""
    return service.change_hold_expiry(str(booking_id), current_user.id, body.expires_at)

# A booking request is read by the venue staff who decide it and by the
# coordinator whose event it is (the service checks the assignment). Deciding
# it is venue staff's alone (SCRUM-38 AC11), on the session's active role.
BookingViewer = Annotated[CurrentUser, Depends(require_roles(["venue_staff", "event_coordinator"]))]


@bookings_router.get("/{booking_id}", response_model=VenueBookingDetail, status_code=status.HTTP_200_OK)
def read_venue_booking(booking_id: UUID, current_user: BookingViewer) -> VenueBookingDetail:
    """One booking request with its event's requirements, venue staff's decision
    if there is one, and the booking's history (SCRUM-38 AC1, AC6, AC12)."""
    return service.booking_detail(str(booking_id), current_user.id, current_user.role)


@bookings_router.post("/{booking_id}/mark-revised", response_model=VenueBookingDetail, status_code=status.HTTP_200_OK)
def mark_venue_booking_revised(booking_id: UUID, body: SafetyRevisionRequest, current_user: CoordinatorOnly) -> VenueBookingDetail:
    """CR-104 AC3/AC4 [Team decision]: the assigned coordinator marks revised."""
    return service.mark_safety_revision(str(booking_id), current_user.id, body.note)


@bookings_router.post("/{booking_id}/send-for-re-review", status_code=status.HTTP_204_NO_CONTENT)
def send_venue_booking_for_re_review(booking_id: UUID, body: ReReviewSendRequest,
                                     current_user: CoordinatorOnly) -> Response:
    """Story 37 AC6: send a booking an approved change marked Needs re-review to venue
    staff, with an optional note. It keeps its hold until they decide."""
    service.send_booking_for_re_review(str(booking_id), current_user.id, body.note)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@bookings_router.post("/{booking_id}/restore", response_model=VenueBookingDetail, status_code=status.HTTP_200_OK)
def restore_venue_booking(booking_id: UUID, current_user: VenueStaffOnly) -> VenueBookingDetail:
    """Restore an affected booking once its venue is free for the full occupied
    window (CR-95 AC9): clears the Affected flag and cancels a pending replacement.
    Refused with 409 while a block or deactivation remains or once a replacement
    is approved."""
    return service.restore_booking(str(booking_id), current_user.id)


@bookings_router.post("/{booking_id}/reject", response_model=VenueBookingDetail, status_code=status.HTTP_200_OK)
def reject_venue_booking(booking_id: UUID, body: VenueBookingReject, current_user: VenueStaffOnly) -> VenueBookingDetail:
    """Reject a held booking with a reason and an optional suggestion (SCRUM-38).
    The hold is released and the assigned coordinator is notified. Refused with
    409 when the booking is no longer held, including a hold that has expired."""
    return service.reject_booking(str(booking_id), current_user.id, body)


@bookings_router.post("/{booking_id}/approve", response_model=VenueBookingDetail, status_code=status.HTTP_200_OK)
def approve_venue_booking(booking_id: UUID, current_user: VenueStaffOnly) -> VenueBookingDetail:
    """Approve a held booking (SCRUM-36). The assigned coordinator is notified.
    Refused with 409 when the booking is no longer held (including an expired
    hold), a venue block now overlaps it, or the venue has been deactivated."""
    return service.approve_booking(str(booking_id), current_user.id)


@bookings_router.post("/{booking_id}/cancel", response_model=VenueBookingDetail, status_code=status.HTTP_200_OK)
def cancel_venue_booking(booking_id: UUID, current_user: CoordinatorOnly) -> VenueBookingDetail:
    """The assigned coordinator, acting as coordinator, cancels a held, approved or
    re-review booking (SCRUM-85). Its slot is freed, venue staff are told, and an
    event in Safety review, Confirmed or Preparation returns to Planning. 409 when
    the booking is already finished or the event has started, ended or been
    cancelled; 403 for anyone else, the Coordinator Lead included."""
    return service.cancel_booking(str(booking_id), current_user.id)
