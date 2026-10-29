// SCRUM-24 equipment reservation (REQUIREMENTS §6.15–6.17). The API and the
// database functions decide everything; these only choose which actions to
// offer and how statuses, the exit tick and history read on screen.

// Mirror the API's NOT_AVAILABLE_REASON_MAX_LENGTH and TECHNICAL_NOTES_MAX_LENGTH.
export const NOT_AVAILABLE_REASON_MAX_LENGTH = 500;
export const TECHNICAL_NOTES_MAX_LENGTH = 2000;

// AC11: the event's derived technical status.
export const TECHNICAL_STATUS_LABELS = {
  not_required: "Not required",
  pending: "Pending",
  ready: "Ready",
  issue: "Issue",
};

// Static class names: Tailwind can't see built ones.
export const TECHNICAL_STATUS_BADGE_CLASSES = {
  not_required: "bg-canvas text-ink",
  pending: "bg-bauhaus-yellow text-ink",
  ready: "bg-bauhaus-blue text-canvas",
  issue: "bg-bauhaus-red text-canvas",
};

// AC13: how each history entry reads.
export const HISTORY_ACTION_LABELS = {
  reserved: "Reserved",
  refused: "Reserve refused",
  not_available: "Marked not available",
  note_updated: "Notes updated",
  released: "Released",
  re_review: "Flagged for re-review",
  needs_re_review: "Needs re-review after an approved change",
  sent_for_re_review: "Sent for re-review",
  exit_ticked: "Exit check ticked",
  exit_unticked: "Exit check unticked",
  exit_cleared: "Exit check cleared",
  technical_status: "Technical status changed",
};

const STATUS_WORDS = {
  ...TECHNICAL_STATUS_LABELS,
  reserved: "Reserved",
  rejected: "Not available",
  re_review: "Re-review",
  released: "Released",
};

const OPEN_EVENT_STATUSES = new Set(["planning", "safety_review", "confirmed"]);

const formatter = new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore" });

export function formatTechnicalTime(value) {
  return value ? formatter.format(new Date(value)) : "Date not set";
}

// Arrangements are made while the event is in planning, safety review or confirmed.
export function isOpenForArrangements(eventStatus) {
  return OPEN_EVENT_STATUSES.has(eventStatus);
}

// AC1 and D8: a pending line, or one flagged for re-review, can be reserved.
export function canReserve(lineStatus) {
  return lineStatus === "pending" || lineStatus === "re_review";
}

// AC3, AC9: any line still in play can be marked Not available.
export function canMarkNotAvailable(lineStatus) {
  return lineStatus === "pending" || lineStatus === "reserved" || lineStatus === "re_review";
}

// AC10: the tick only applies to an event that has equipment.
export function hasLiveLines(lines) {
  return lines.some((line) => line.status !== "released");
}

export function reasonError(reason) {
  const text = String(reason ?? "").trim();
  if (!text) return "Give a reason the line is not available.";
  if (text.length > NOT_AVAILABLE_REASON_MAX_LENGTH) return `Keep the reason to ${NOT_AVAILABLE_REASON_MAX_LENGTH} characters.`;
  return null;
}

export function notesError(notes) {
  return String(notes ?? "").trim().length > TECHNICAL_NOTES_MAX_LENGTH
    ? `Keep the notes to ${TECHNICAL_NOTES_MAX_LENGTH} characters.`
    : null;
}

// AC10, shown to the Safety Officer (CR-103) and the coordinator.
export function exitConfirmationText(exit) {
  if (!exit) return "Not recorded";
  return `Confirmed by ${exit.confirmed_by_name ?? "a former staff member"} · ${formatTechnicalTime(exit.confirmed_at)}`;
}

export function historyEntryText(entry) {
  const action = HISTORY_ACTION_LABELS[entry.action] ?? entry.action;
  const subject = entry.line_label ? ` · ${entry.line_label}` : "";
  const change = entry.from_status && entry.to_status && entry.from_status !== entry.to_status
    ? ` · ${STATUS_WORDS[entry.from_status] ?? entry.from_status} → ${STATUS_WORDS[entry.to_status] ?? entry.to_status}`
    : "";
  return `${action}${subject}${change}`;
}

export function historyActor(entry) {
  return entry.actor_name ?? "System";
}
