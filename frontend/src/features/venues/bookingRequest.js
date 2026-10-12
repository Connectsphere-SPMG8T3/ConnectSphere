/**
 * Venue booking request helpers (SCRUM-19): what the coordinator's event page
 * offers, and how a search opened from an event is pre-filled.
 */
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

/**
 * What the event page's Venue panel shows. The API is the enforcement point;
 * this only avoids offering a request that would answer 409.
 */
export function venuePanelState(event) {
  if (!event) return { kind: "none" };
  // CR-99 AC7: the hold ran out. Say so, and offer the venue again when a
  // request is possible at all.
  if (event.venue_booking?.status === "expired") {
    return { kind: "expired", booking: event.venue_booking, canRequest: event.status === "planning" };
  }
  if (event.venue_booking) return { kind: "booked", booking: event.venue_booking };
  if (event.status === "planning") return { kind: "can-request" };
  if (event.status === "returned") return { kind: "unavailable", reason: "Requirements are still being amended." };
  if (event.status === "under_review") {
    return { kind: "unavailable", reason: "A venue can be requested once the request is approved for planning." };
  }
  return { kind: "none" };
}
