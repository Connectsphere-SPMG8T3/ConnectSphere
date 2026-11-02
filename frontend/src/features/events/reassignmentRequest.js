import { ACTIVE_COORDINATOR_STATUSES } from "@/features/events/dashboard";

// CR-106. Mirrors the API's REASSIGNMENT_REASON_MAX_LENGTH ([Assumption], REQUIREMENTS §9).
export const REASSIGNMENT_REASON_MAX_LENGTH = 1000;

// AC1, AC5: the assigned coordinator may ask while a Lead could reassign the event, which is
// every status a coordinator still works in (CR-101, QA3-3, D73), and while no request is open.
// The API is the enforcement point; this only avoids offering a request that would answer 409.
export function canRequestReassignment(event) {
  return Boolean(event) && ACTIVE_COORDINATOR_STATUSES.includes(event.status) && !event.open_reassignment_request;
}
