// Tech support's equipment request list (SCRUM-24), shaped like venue staff's
// booking requests (features/venues/dashboard.js): filter by status, item and
// the event's date; sort by event date, event name, equipment type (§6.15) or
// how long a line has waited.
import { REQUEST_STATUS_LABELS } from "@/features/equipment/equipmentRequest";
import { singaporeDayKey } from "@/features/venues/singaporeTime";

export const WAITING = "waiting";
export const ALL_STATUSES = "all";
export const ALL_ITEMS = "all";

// The lines that need a decision from tech support (AC1, AC7).
const WAITING_STATUSES = new Set(["pending", "re_review"]);
const STATUS_ORDER = ["pending", "re_review", "reserved", "rejected", "released"];
const DAY_MS = 24 * 60 * 60 * 1000;

export const REQUEST_SORT_OPTIONS = [
  { value: "event_soonest", label: "Event date: soonest" },
  { value: "event_latest", label: "Event date: latest" },
  { value: "event_name", label: "Event name: A–Z" },
  { value: "equipment_type", label: "Equipment type: A–Z" },
  { value: "waiting_longest", label: "Waiting: longest" },
  { value: "waiting_shortest", label: "Waiting: shortest" },
];

export function isWaiting(line) {
  return WAITING_STATUSES.has(line.status);
}

export function waitingCount(lines = []) {
  return lines.filter(isWaiting).length;
}

export function waitingDays(line, now = new Date()) {
  const created = Date.parse(line?.created_at ?? "");
  if (!Number.isFinite(created)) return null;
  return Math.max(Math.floor((now.getTime() - created) / DAY_MS), 0);
}

export function requestStatusFilterOptions(lines = []) {
  const counts = new Map();
  for (const line of lines) counts.set(line.status, (counts.get(line.status) ?? 0) + 1);
  return [
    { value: WAITING, label: `Waiting on you (${waitingCount(lines)})` },
    { value: ALL_STATUSES, label: `All statuses (${lines.length})` },
    ...STATUS_ORDER.filter((status) => counts.has(status)).map((status) => ({
      value: status,
      label: `${REQUEST_STATUS_LABELS[status]} (${counts.get(status)})`,
    })),
  ];
}

export function equipmentFilterOptions(lines = []) {
  const names = new Map();
  for (const line of lines) if (!names.has(line.equipment_id)) names.set(line.equipment_id, line.equipment_name);
  return [
    { value: ALL_ITEMS, label: "All equipment" },
    ...[...names].sort((a, b) => a[1].localeCompare(b[1])).map(([value, label]) => ({ value, label })),
  ];
}

export function filterRequests(lines = [], { status = ALL_STATUSES, equipmentId = ALL_ITEMS, startDate = "", endDate = "" } = {}) {
  return lines.filter((line) => {
    const day = line.event_starts_at ? singaporeDayKey(line.event_starts_at) : null;
    const statusMatches = status === ALL_STATUSES || (status === WAITING ? isWaiting(line) : line.status === status);
    return (
      statusMatches &&
      (equipmentId === ALL_ITEMS || line.equipment_id === equipmentId) &&
      (!startDate || (day !== null && day >= startDate)) &&
      (!endDate || (day !== null && day <= endDate))
    );
  });
}

// Undated events and untyped items sort last whichever way the list runs.
function byEventDate(direction) {
  return (a, b) => {
    const left = Date.parse(a.event_starts_at ?? "");
    const right = Date.parse(b.event_starts_at ?? "");
    if (!Number.isFinite(left) || !Number.isFinite(right)) return Number.isFinite(left) ? -1 : Number.isFinite(right) ? 1 : 0;
    return direction * (left - right);
  };
}

function byText(field) {
  return (a, b) => {
    if (!a[field] || !b[field]) return a[field] ? -1 : b[field] ? 1 : 0;
    return a[field].localeCompare(b[field]);
  };
}

export function sortRequests(lines = [], sort = "event_soonest", now = new Date()) {
  const soonest = byEventDate(1);
  const comparators = {
    event_soonest: soonest,
    event_latest: byEventDate(-1),
    event_name: byText("event_name"),
    equipment_type: byText("equipment_type"),
    waiting_longest: (a, b) => (waitingDays(b, now) ?? -1) - (waitingDays(a, now) ?? -1),
    waiting_shortest: (a, b) => (waitingDays(a, now) ?? Infinity) - (waitingDays(b, now) ?? Infinity),
  };
  const compare = comparators[sort] ?? soonest;
  return [...lines].sort((a, b) => compare(a, b) || soonest(a, b) || String(a.id).localeCompare(String(b.id)));
}
