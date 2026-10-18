/**
 * Venue staff's decision on a booking request (SCRUM-38 reject, SCRUM-36
 * approve): what may be offered, what a rejection must contain, and how the
 * booking's time reads. No I/O.
 */

// Mirrors the API's BOOKING_NOTE_MAX_LENGTH (AC2, AC3).
export const REJECTION_TEXT_MAX_LENGTH = 1000;

/** Per-field messages for a rejection, empty when it can be sent. Lengths count after trimming, as the API does. */
export function rejectionErrors({ reason = "", suggestion = "" } = {}) {
  const errors = {};
  const trimmedReason = (reason ?? "").trim();
  if (!trimmedReason) errors.reason = "Give a reason for rejecting this request.";
  else if (trimmedReason.length > REJECTION_TEXT_MAX_LENGTH) errors.reason = "Keep the reason to 1000 characters.";
  if ((suggestion ?? "").trim().length > REJECTION_TEXT_MAX_LENGTH) {
    errors.suggestion = "Keep the suggestion to 1000 characters.";
  }
  return errors;
}

/** The body for `POST /venue-bookings/{id}/reject`: trimmed, with no suggestion rather than a blank one. */
export function rejectionPayload({ reason = "", suggestion = "" } = {}) {
  return { reason: (reason ?? "").trim(), suggestion: (suggestion ?? "").trim() || null };
}

/** Only a held booking can be rejected (AC9), and only by a session acting as venue staff (AC11). UX only: the API decides. */
export function canRejectBooking(booking, role) {
  return role === "venue_staff" && booking?.status === "held";
}

/** The same rule for approval (SCRUM-36 AC6, AC8). UX only: the API decides, including blocks and inactive venues. */
export function canApproveBooking(booking, role) {
  return role === "venue_staff" && booking?.status === "held";
}

/** Only a live booking flagged Affected can be restored (CR-95 AC9), and only by a session acting as venue staff. UX only: the API decides. */
export function canRestoreBooking(booking, role) {
  return (
    role === "venue_staff" && booking?.flag === "affected" && ["held", "approved"].includes(booking?.status)
  );
}

// Venues are in Singapore, so times are shown there (REQUIREMENTS §4).
const dayFormatter = new Intl.DateTimeFormat("en-SG", {
  timeZone: "Asia/Singapore", weekday: "short", day: "numeric", month: "short", year: "numeric",
});
const timeFormatter = new Intl.DateTimeFormat("en-SG", {
  timeZone: "Asia/Singapore", hour: "2-digit", minute: "2-digit", hour12: false,
});

/** "Mon, 10 Mar 2031, 14:00–17:00", naming both days when the booking crosses midnight. */
export function formatBookingPeriod(period) {
  if (!period?.starts_at || !period?.ends_at) return "Timing to be confirmed";
  const start = new Date(period.starts_at);
  const end = new Date(period.ends_at);
  const startDay = dayFormatter.format(start);
  const endDay = dayFormatter.format(end);
  if (startDay === endDay) return `${startDay}, ${timeFormatter.format(start)}–${timeFormatter.format(end)}`;
  return `${startDay}, ${timeFormatter.format(start)} – ${endDay}, ${timeFormatter.format(end)}`;
}

const decisionFormatter = new Intl.DateTimeFormat("en-SG", {
  timeZone: "Asia/Singapore", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  hour12: false,
});

/** "1 Mar 2031, 10:00": when a request was made or decided. */
export function formatDecisionTime(value) {
  return value ? decisionFormatter.format(new Date(value)) : "time not recorded";
}

// CR-99's `venue_booking_history.action` values, plus this story's rejection.
const HISTORY_ACTION_LABELS = {
  safety_rejected: "Safety rejected",
  safety_revised: "Marked revised",
  rejected: "Rejected",
  approved: "Approved",
  expired: "Expired",
  expiry_changed: "Expiry changed",
};

/** One history row's action as a person reads it; an unknown one is spelled out rather than hidden. */
export function historyActionLabel(action) {
  if (!action) return "Changed";
  if (HISTORY_ACTION_LABELS[action]) return HISTORY_ACTION_LABELS[action];
  const words = String(action).replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
