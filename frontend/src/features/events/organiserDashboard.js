import { STATUS_LABELS } from "@/features/events/dashboard";

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

export function summariseOrganiserEvents(events = []) {
  const counts = (statuses) => events.filter((event) => statuses.includes(event.status)).length;
  const drafts = counts(["draft"]);
  const returned = counts(["returned"]);
  const rejected = counts(["rejected"]);
  const underReview = counts(["submitted", "under_review"]);
  const planning = counts(["planning"]);
  const confirmed = counts(["confirmed"]);
  const completed = counts(["completed"]);

  return {
    needsAction: { drafts, returned, rejected, total: drafts + returned + rejected },
    myEvents: { underReview, planning, confirmed, completed, total: underReview + planning + confirmed + completed },
  };
}

export function groupOrganiserActiveEvents(events = []) {
  // Single-status labels come from STATUS_LABELS (LC-R3). "Under review" is its
  // own label because it also holds `submitted`. Descriptions stay here: they
  // are written for the organiser, while STATUS_DESCRIPTIONS speaks to coordinators.
  const groups = [
    { status: "under_review", label: "Under review", description: "Requests awaiting review or clarification." },
    { status: "planning", label: STATUS_LABELS.planning, description: "Events being arranged with ConnectSphere." },
    { status: "confirmed", label: STATUS_LABELS.confirmed, description: "Events with confirmed arrangements." },
    { status: "completed", label: STATUS_LABELS.completed, description: "Events that have finished." },
  ];

  return groups.map((group) => ({
    ...group,
    events: events.filter((event) =>
      group.status === "under_review"
        ? ["submitted", "under_review"].includes(event.status)
        : event.status === group.status,
    ),
  }));
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
