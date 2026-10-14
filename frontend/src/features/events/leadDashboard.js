/**
 * The Event Coordinator Lead dashboard's pure logic (CR-101): filtering by
 * coordinator and status, ordering, and the coordinator option lists. Works on
 * the `GET /events/dashboard/lead` payload. No I/O.
 */
import { ACTIVE_COORDINATOR_STATUSES, STATUS_LABELS } from "@/features/events/dashboard";

export const LEAD_STATUS_OPTIONS = ACTIVE_COORDINATOR_STATUSES.map((value) => ({
  value,
  label: STATUS_LABELS[value],
}));

function normaliseText(value) {
  return String(value ?? "").trim().toLocaleLowerCase();
}

function instant(value) {
  if (!value) return Number.POSITIVE_INFINITY;
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? Number.POSITIVE_INFINITY : parsed;
}

export function filterLeadEvents(events = [], { coordinator = "", status = [], search = "" } = {}) {
  const needle = normaliseText(search);
  return events.filter((event) => {
    if (coordinator && event.coordinator?.id !== coordinator) return false;
    if (status.length && !status.includes(event.status)) return false;
    if (needle && !normaliseText(event.event_name).includes(needle)) return false;
    return true;
  });
}

export function sortLeadEvents(events = []) {
  return [...events].sort((a, b) => {
    const byDate = instant(a.starts_at) - instant(b.starts_at);
    // Two undated events are Infinity - Infinity = NaN: fall through to the name.
    if (byDate) return Number.isNaN(byDate) ? String(a.event_name).localeCompare(String(b.event_name)) : byDate;
    return String(a.event_name).localeCompare(String(b.event_name));
  });
}

export function coordinatorFilterOptions(coordinators = []) {
  return coordinators.map((c) => ({ value: c.id, label: `${c.full_name} (${c.active_count})` }));
}

export function coordinatorOptions(coordinators = [], currentId = null) {
  return coordinators.filter((c) => c.id !== currentId).map((c) => ({ value: c.id, label: c.full_name }));
}
