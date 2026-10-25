// Story 84. Mirrors the API's CANCELLATION_REASON_MAX_LENGTH ([Assumption], REQUIREMENTS §9).
export const CANCELLATION_REASON_MAX_LENGTH = 1000;

// CR-R4: every status after submission accepts a request except these. The API
// is the enforcement point (lifecycle.py); this only avoids offering a 409.
const REFUSED_STATUSES = new Set(["draft", "rejected", "cancelled", "completed"]);

export function canRequestCancellation(event) {
  return Boolean(event) && !REFUSED_STATUSES.has(event.status) && !event.open_cancellation_request;
}

// Story 115 AC3: the coordinator cancels directly only from these, before the start
// (LC-R5). Like the rule above, it only avoids offering a 409.
const DIRECT_CANCEL_STATUSES = new Set(["planning", "confirmed", "preparation"]);

export function canCancelEvent(event, now = new Date()) {
  return Boolean(event?.starts_at) && DIRECT_CANCEL_STATUSES.has(event.status) && new Date(event.starts_at) > now;
}
