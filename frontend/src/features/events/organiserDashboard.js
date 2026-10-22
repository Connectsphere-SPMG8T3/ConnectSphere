import { STATUS_LABELS } from "@/features/events/dashboard";
import { getDateString } from "@/features/events/timezones";

const STATUS_ORDER = [
  "draft",
  "submitted",
  "under_review",
  "returned",
  "planning",
  "confirmed",
  "rejected",
  "cancelled",
  "completed",
];

function normaliseText(value) {
  return String(value ?? "").trim().toLocaleLowerCase();
}

function dateValue(event) {
  if (!event?.date) return Number.POSITIVE_INFINITY;
  const value = new Date(`${event.date}T${event.startTime || "00:00"}`).getTime();
  return Number.isNaN(value) ? Number.POSITIVE_INFINITY : value;
}

function statusValue(status) {
  const index = STATUS_ORDER.indexOf(status);
  return index === -1 ? STATUS_ORDER.length : index;
}

function compareText(left, right) {
  return normaliseText(left).localeCompare(normaliseText(right));
}

function compareEvents(left, right, field) {
  if (field === "date") return dateValue(left) - dateValue(right);
  if (field === "name") return compareText(left.name, right.name);
  if (field === "status") return statusValue(left.status) - statusValue(right.status);
  return 0;
}

export function filterOrganiserEvents(events = [], { status = "", search = "" } = {}) {
  const query = normaliseText(search);
  const selectedStatuses = Array.isArray(status) ? status : status ? [status] : [];

  return events.filter((event) => {
    const matchesStatus =
      !selectedStatuses.length || selectedStatuses.some((selectedStatus) =>
        selectedStatus === "under_review" ? ["submitted", "under_review"].includes(event.status) : event.status === selectedStatus,
      );
    const matchesSearch = !query || normaliseText(event.name).includes(query);
    return matchesStatus && matchesSearch;
  });
}

export function sortOrganiserEvents(events = [], { field = "date", direction = "asc" } = {}) {
  const multiplier = direction === "desc" ? -1 : 1;

  return [...events].sort((left, right) => {
    const primary = compareEvents(left, right, field) * multiplier;
    return primary || String(left.id).localeCompare(String(right.id));
  });
}

export function groupOrganiserEvents(events = []) {
  return {
    drafts: events.filter((event) => event.status === "draft"),
    requests: events.filter((event) => event.status !== "draft"),
  };
}

export function groupOrganiserActiveEvents(events = [], now = new Date()) {
  // Single-status labels come from STATUS_LABELS (LC-R3). "Under review" is its
  // own label because it also holds `submitted`. Descriptions stay here: they
  // are written for the organiser, while STATUS_DESCRIPTIONS speaks to coordinators.
  const groups = [
    { status: "draft", label: STATUS_LABELS.draft, description: "Only you can see these. Finish and submit them." },
    { status: "under_review", label: "Under review", description: "Requests awaiting review or clarification." },
    { status: "returned", label: STATUS_LABELS.returned, description: "Requests sent back to you to amend and resubmit." },
    { status: "planning", label: STATUS_LABELS.planning, description: "Events being arranged with ConnectSphere." },
    { status: "safety_review", label: STATUS_LABELS.safety_review, description: "Events being checked by the Safety Officer." },
    { status: "confirmed", label: STATUS_LABELS.confirmed, description: "Events with confirmed arrangements." },
  ];
  // Past events have their own section (groupOrganiserClosedEvents).
  const current = events.filter((event) => !isPastEvent(event, now));

  return groups.map((group) => {
    const groupEvents = current.filter((event) =>
      group.status === "under_review"
        ? ["submitted", "under_review"].includes(event.status)
        : event.status === group.status,
    );
    // Returned is the only column on the board the organiser has to act on.
    return { ...group, events: groupEvents, needsAttention: group.status === "returned" && groupEvents.length > 0 };
  });
}

// A confirmed event whose date, in its own timezone, is before today has
// happened even though nobody has marked it completed yet (as on the
// coordinator dashboard). An event without a date is never past.
function isPastEvent(event, now) {
  if (event.status === "completed") return true;
  if (event.status !== "confirmed" || !event.date) return false;
  return event.date < getDateString(now, event.eventTimezone || undefined);
}

/** The closed events listed below the board: past ones and rejected requests. */
export function groupOrganiserClosedEvents(events = [], now = new Date()) {
  return {
    past: events.filter((event) => isPastEvent(event, now)),
    rejected: events.filter((event) => event.status === "rejected"),
  };
}

const ORGANISER_WAITING_STATUSES = ["submitted", "under_review", "planning", "safety_review"];

/**
 * How an organiser's status-board card is highlighted, in the coordinator
 * board's tones (`BOARD_CARD_TONE_CLASSES`): red when the organiser must act,
 * blue for a draft it can still edit, grey while ConnectSphere works on it, green once confirmed or completed,
 * greyed out once rejected.
 */
export function organiserBoardTone(event) {
  if (event.status === "returned") return "attention";
  if (event.status === "draft") return "editable";
  if (ORGANISER_WAITING_STATUSES.includes(event.status)) return "waiting";
  if (event.status === "confirmed" || event.status === "completed") return "done";
  if (event.status === "rejected") return "rejected";
  return "plain";
}

export function needsOrganiserAttention(event) {
  if (!event) return false;
  if (event.status === "draft" || event.status === "returned") return true;
  return event.status === "submitted" && !event.coordinatorId;
}

export function getOrganiserAction(event) {
  if (event?.status === "draft") return { kind: "continue_draft", label: "Edit draft" };
  if (event?.status === "returned") return { kind: "amend", label: "Amend and resubmit" };
  return { kind: "view", label: "View event" };
}

export { STATUS_ORDER };
