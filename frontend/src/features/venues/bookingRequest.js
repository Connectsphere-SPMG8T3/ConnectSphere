/**
 * Venue booking request helpers (SCRUM-19): what the coordinator's event page
 * offers, and how a search opened from an event is pre-filled.
 */
import { BLOCK_REASON_LABELS } from "@/features/venues/dashboard";
import { emptyCriteria } from "@/features/venues/venueSearchStore";
import { SINGAPORE_OFFSET_MS, singaporeDayKey, toInstant } from "@/features/venues/singaporeTime";

// How each occupying booking status reads to the coordinator (§6.12–6.14).
export const BOOKING_STATUS_LABELS = {
  held: "Tentative hold",
  approved: "Approved",
  re_review: "Under re-review",
  expired: "Expired",
};

function singaporeTime(value) {
  return new Date(toInstant(value).getTime() + SINGAPORE_OFFSET_MS).toISOString().slice(11, 16);
}

/**
 * Search criteria for finding a venue for this event. The search reads times
 * as Singapore time, which is where every venue is, so the event's instants
 * are converted to Singapore wall-clock rather than the event's own zone. An
 * event that crosses midnight in Singapore can't be expressed as one date and
 * two times, so its timing is left for the coordinator to enter.
 */
export function criteriaFromEvent(event) {
  const criteria = emptyCriteria();
  if (event.starts_at && event.ends_at && singaporeDayKey(event.starts_at) === singaporeDayKey(event.ends_at)) {
    criteria.date = singaporeDayKey(event.starts_at);
    criteria.startTime = singaporeTime(event.starts_at);
    criteria.endTime = singaporeTime(event.ends_at);
  }
  if (event.expected_attendance) criteria.minCapacity = event.expected_attendance;
  if (event.layout_preference) criteria.layout = event.layout_preference;
  criteria.facilities = [...(event.facilities_required ?? [])];
  return criteria;
}

export function criteriaFromSpace(space, event) {
  const criteria = criteriaFromEvent({
    ...(event ?? {}),
    starts_at: space?.starts_at ?? event?.starts_at,
    ends_at: space?.ends_at ?? event?.ends_at,
  });
  if (space?.expected_pax) criteria.minCapacity = space.expected_pax;
  if (space?.layout_preference) criteria.layout = space.layout_preference;
  if (space?.facilities_required) criteria.facilities = [...space.facilities_required];
  return criteria;
}

/**
 * What the event page's Venue panel shows. The API is the enforcement point;
 * this only avoids offering a request that would answer 409.
 */
// The venue changes that mean a coordinator may still arrange a replacement:
// the event is in planning, or has gone on and will be returned to it (CR-95 AC7).
const REPLACEABLE_EVENT_STATUSES = ["planning", "safety_review", "confirmed"];
const LIVE_BOOKING_STATUSES = ["held", "approved"];

/**
 * An affected booking (the venue became unavailable, CR-95 AC1) and, if one has
 * been asked for, the replacement standing beside it. A booking that is no
 * longer held or approved needs neither.
 */
function affectedPanelState(event, space) {
  const bookings = (event.venue_bookings ?? []).filter(
    (item) => !space || item.event_space_request_id === space.id,
  );
  const affected = bookings.find((item) => item.flag === "affected" && LIVE_BOOKING_STATUSES.includes(item.status));
  if (!affected) return null;
  const replacement = bookings.find(
    (item) => item.replaces_booking_id === affected.id && [...LIVE_BOOKING_STATUSES, "re_review"].includes(item.status),
  );
  if (replacement) return { kind: "replacing", booking: affected, replacement };
  return {
    kind: "affected",
    booking: affected,
    reason: affected.flag_reason,
    canReplace: REPLACEABLE_EVENT_STATUSES.includes(event.status),
  };
}

/** Venue search for this event (or space), asking to replace `booking` (CR-95 AC4). */
export function replacementSearchRoute(event, space, booking) {
  const query = { event: event.id };
  if (space) query.space = space.id;
  query.replaces = booking.id;
  return { name: "venue-search", query };
}

function safetyRejectedPanelState(event, space) {
  const bookings = event.venue_bookings ?? (event.venue_booking ? [event.venue_booking] : []);
  const booking = bookings.find((item) => (!space || item.event_space_request_id === space.id)
    && item.flag === "safety_rejected" && LIVE_BOOKING_STATUSES.includes(item.status));
  if (!booking) return null;
  const replacement = bookings.find((item) => item.replaces_booking_id === booking.id
    && ["held", "approved", "re_review"].includes(item.status));
  const canAct = !replacement && event.status === "planning";
  return {
    kind: "safety-rejected", booking, reason: booking.flag_reason,
    canMarkRevised: canAct, canReplace: canAct,
    ...(replacement ? { replacement } : {}),
  };
}

export function venuePanelState(event, space = null) {
  if (!event) return { kind: "none" };
  const rejected = safetyRejectedPanelState(event, space);
  if (rejected) return rejected;
  const affected = affectedPanelState(event, space);
  if (affected) return affected;
  // CR-99 AC7: the hold ran out. Say so, and offer the venue again when a
  // request is possible at all.
  const booking = space
    ? (event.venue_bookings ?? []).find((item) => item.event_space_request_id === space.id)
      ?? (event.venue_booking?.event_space_request_id === space.id ? event.venue_booking : null)
    : event.venue_booking;
  if (booking?.status === "expired") {
    return { kind: "expired", booking, canRequest: event.status === "planning" };
  }
  if (booking) return { kind: "booked", booking };
  if (event.status === "planning") return { kind: "can-request" };
  if (event.status === "returned") return { kind: "unavailable", reason: "Requirements are still being amended." };
  if (event.status === "under_review") {
    return { kind: "unavailable", reason: "A venue can be requested once the request is approved for planning." };
  }
  return { kind: "none" };
}

/**
 * What refused a venue request, as one line under the refusal (SCRUM-21 AC2):
 * the other event's name and the window it occupies, setup to turnaround, or
 * a block and its reason. Times are in the event's own timezone, like the
 * request's period above it. Empty when the API named nothing.
 */
export function describeConflict(conflict, timeZone) {
  if (!conflict) return "";
  const dateTime = new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeStyle: "short", timeZone });
  const timeOnly = new Intl.DateTimeFormat("en-SG", { timeStyle: "short", timeZone });
  const dayOnly = new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeZone });
  const starts = new Date(conflict.starts_at);
  const ends = new Date(conflict.ends_at);
  const end = dayOnly.format(starts) === dayOnly.format(ends) ? timeOnly.format(ends) : dateTime.format(ends);
  const window = starts.getUTCFullYear() === 1 || ends.getUTCFullYear() === 9999
    ? "beyond supported dates" : `${dateTime.format(starts)} – ${end}`;
  if (conflict.kind === "block") {
    const reason = (BLOCK_REASON_LABELS[conflict.block_reason] ?? conflict.block_reason).toLowerCase();
    return `Blocked for ${reason} ${window}.`;
  }
  return `"${conflict.event_name}" occupies it ${window}, including setup and turnaround.`;
}
