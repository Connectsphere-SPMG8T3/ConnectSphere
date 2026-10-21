/**
 * The coordinator dashboard's Events view (SCRUM-72): one card per assigned
 * event, searchable, filterable and sortable, following the organiser
 * dashboard's pattern (`organiserDashboard.js`). Pure functions, no I/O.
 *
 * They work on the `GET /events/dashboard/coordinator` payload (snake_case,
 * `starts_at` instants), which is why they don't reuse the organiser helpers
 * that expect `stores/events.js`'s form-shaped events.
 */
import {
  ACTION_CATEGORY_KINDS,
  ACTIVE_COORDINATOR_STATUSES,
  mostUrgentActionByEvent,
  outstandingReadiness,
} from "@/features/events/dashboard";
import { getDateString } from "@/features/events/timezones";

function normaliseText(value) {
  return String(value ?? "").trim().toLocaleLowerCase();
}

function instant(value) {
  if (!value) return Number.POSITIVE_INFINITY;
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? Number.POSITIVE_INFINITY : parsed;
}

function statusRank(status) {
  const index = ACTIVE_COORDINATOR_STATUSES.indexOf(status);
  return index === -1 ? ACTIVE_COORDINATOR_STATUSES.length : index;
}

/**
 * One card per active event, carrying the most urgent action waiting on it
 * (ranked as the Overview ranks them) and its outstanding blocking arrangements.
 */
export function coordinatorEventCards(activeEvents = [], actionItems = []) {
  const actionByEvent = mostUrgentActionByEvent(actionItems);

  return activeEvents.map((event) => ({
    id: event.event_id,
    name: event.event_name,
    status: event.status,
    startsAt: event.starts_at,
    flags: event.flags ?? [],
    actionKind: actionByEvent.get(event.event_id) ?? null,
    outstanding: outstandingReadiness(event),
  }));
}

/** Cards for the coordinator's rejected events: closed, so nothing outstanding or waiting. */
export function rejectedEventCards(rejectedEvents = []) {
  return rejectedEvents.map((event) => ({
    id: event.event_id,
    name: event.event_name,
    status: "rejected",
    startsAt: event.starts_at,
    flags: [],
    actionKind: null,
    outstanding: [],
  }));
}

/**
 * `status` is a list (any of them matches); `action` is one of the AC1
 * categories in `ACTION_CATEGORY_KINDS`. An unknown category filters nothing
 * rather than hiding every event behind a bad link.
 */
export function filterCoordinatorEvents(cards = [], { status = [], search = "", action = "" } = {}) {
  const query = normaliseText(search);
  const statuses = Array.isArray(status) ? status : status ? [status] : [];
  const actionKinds = ACTION_CATEGORY_KINDS[action];

  return cards.filter(
    (card) =>
      (!statuses.length || statuses.includes(card.status)) &&
      (!query || normaliseText(card.name).includes(query)) &&
      (!actionKinds || actionKinds.includes(card.actionKind)),
  );
}

function compareCards(left, right, field) {
  if (field === "name") return normaliseText(left.name).localeCompare(normaliseText(right.name));
  if (field === "status") return statusRank(left.status) - statusRank(right.status);
  return instant(left.startsAt) - instant(right.startsAt) || 0;
}

export function sortCoordinatorEvents(cards = [], { field = "date", direction = "asc" } = {}) {
  const multiplier = direction === "desc" ? -1 : 1;
  const undated = (card) => field === "date" && !Number.isFinite(instant(card.startsAt));
  return [...cards].sort(
    (left, right) =>
      // Undated events sort last in either direction.
      Number(undated(left)) - Number(undated(right)) ||
      compareCards(left, right, field) * multiplier ||
      String(left.id).localeCompare(String(right.id)),
  );
}

/** Events with an action waiting on the coordinator, and the rest. */
/**
 * A confirmed event whose date, in Singapore (REQUIREMENTS §4), is before
 * today's, so one on today's date is not yet past however early it started.
 * Undated events never are.
 */
function isPast(card, now) {
  if (card.status !== "confirmed" || !Number.isFinite(instant(card.startsAt))) return false;
  return getDateString(new Date(card.startsAt)) < getDateString(now);
}

/**
 * Past confirmed events first go to `past`, whatever is waiting on them; the
 * rest split by whether anything needs the coordinator.
 */
export function groupCoordinatorEvents(cards = [], now = new Date()) {
  const past = cards.filter((card) => isPast(card, now));
  const current = cards.filter((card) => !isPast(card, now));
  return {
    needsAction: current.filter((card) => card.actionKind),
    inProgress: current.filter((card) => !card.actionKind),
    past,
  };
}
