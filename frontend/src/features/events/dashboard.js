/**
 * Pure presentation logic for the Event Coordinator dashboard (SCRUM-72).
 *
 * No I/O lives here, so every rule below is unit-testable on its own
 * (REQUIREMENTS §3.3). The dashboard component and its Pinia store both read
 * from this module rather than re-deriving ordering or labels themselves.
 */

/**
 * Event statuses, labelled in one place so renaming a status is a one-line
 * change (REQUIREMENTS §5, LC-R3). The plain-language descriptions are what
 * REQUIREMENTS §6.6 asks the UI to show next to a status badge.
 *
 * "Approved" appears on no status except confirmed: the customer uses
 * "Confirmed/Approved" for one final status (QA-18, QA2-8), so calling planning
 * "approved" would tell an organiser their event is settled before it is.
 */
export const STATUS_LABELS = {
  draft: "Draft",
  submitted: "Awaiting assignment",
  under_review: "Under review",
  returned: "Returned for amendment",
  planning: "Planning",
  confirmed: "Confirmed",
  rejected: "Rejected",
  cancelled: "Cancelled",
  completed: "Completed",
};

export const STATUS_DESCRIPTIONS = {
  under_review: "Waiting on your approval or rejection.",
  returned: "With the organiser for amendment.",
  planning: "Passed initial review — venue and equipment being arranged.",
  confirmed: "All blocking arrangements are in place.",
};

/**
 * The statuses an assigned coordinator still has work in, in lifecycle order
 * (REQUIREMENTS §5). `draft` is deliberately absent: drafts are visible only to
 * their owner and never appear in a staff queue, search, or count (DR-R2).
 * `submitted` is absent too — an event only reaches a coordinator once
 * assignment has moved it to `under_review` (§6.5); unassigned events surface
 * through the separate awaiting-assignment alert (AS-R5).
 */
export const ACTIVE_COORDINATOR_STATUSES = ["under_review", "returned", "planning", "confirmed"];

/**
 * How the dashboard ranks the things a coordinator could act on, most urgent
 * first. Order is the rank, so re-prioritising is a matter of moving a line
 * (NFR-M1). Each entry cites the rule that puts it where it is.
 *
 * There is deliberately no time-based escalation: the customer ruled out SLA
 * timers and review deadlines entirely (LC-R4, QA-55, QA-68). Urgency here
 * comes from what the item blocks, not from how long it has sat.
 */
export const ACTION_KINDS = [
  {
    key: "arrangement_issue",
    label: "Arrangement issue",
    tone: "red",
    // §7 NFR-R1: a flag stays on the event until someone resolves it, and a
    // confirmed event with a broken arrangement is the worst inconsistency the
    // system can show.
    description: "A venue block, venue change, or equipment shortfall affects this event.",
  },
  {
    key: "re_review_rejected",
    label: "Re-review rejected",
    tone: "red",
    // §6.19: the event lost its venue or equipment after a change and cannot be
    // re-confirmed until the coordinator finds an alternative.
    description: "Staff rejected an arrangement on re-review. An alternative is needed.",
  },
  {
    key: "cancellation_request",
    label: "Cancellation requested",
    tone: "red",
    // QA-12: arrangements stay held until the coordinator decides.
    description: "The organiser asked to cancel. Arrangements stay held until you decide.",
  },
  {
    key: "change_request",
    label: "Change requested",
    tone: "yellow",
    // QA-12, §6.19.
    description: "The organiser proposed changes. Review the impact before deciding.",
  },
  {
    key: "resubmitted",
    label: "Amended and resubmitted",
    tone: "yellow",
    // QA-22, QA-77: the organiser has answered; the coordinator is now the only
    // thing standing between the request and planning.
    description: "The organiser answered your amendment request.",
  },
  {
    key: "awaiting_review",
    label: "Awaiting first review",
    tone: "blue",
    // §6.4: the initial approve/reject decision.
    description: "Newly assigned. Needs an initial approval or rejection.",
  },
  {
    key: "booking_decision",
    label: "Venue booking decided",
    tone: "blue",
    // §6.13.
    description: "Venue staff approved or rejected the booking request.",
  },
  {
    key: "equipment_decision",
    label: "Equipment decided",
    tone: "blue",
    // §6.17.
    description: "Tech support reserved or rejected an equipment line.",
  },
];

const ACTION_KINDS_BY_KEY = new Map(ACTION_KINDS.map((kind) => [kind.key, kind]));

const UNKNOWN_ACTION_KIND = {
  key: "unknown",
  label: "Needs attention",
  tone: "blue",
  description: "This item needs your attention.",
};

/** Look up a kind's display metadata, falling back for a kind the SPA doesn't know. */
export function actionKindMeta(key) {
  return ACTION_KINDS_BY_KEY.get(key) ?? { ...UNKNOWN_ACTION_KIND, key };
}

// An unrecognised kind sorts after every known one instead of disappearing:
// the backend may publish a new kind before the SPA is redeployed, and silently
// dropping a coordinator's action item would be worse than showing it unstyled.
function rankOf(kind) {
  const index = ACTION_KINDS.findIndex((entry) => entry.key === kind);
  return index === -1 ? ACTION_KINDS.length : index;
}

// Missing or unparseable dates sort last rather than throwing, so one bad row
// can't blank the whole queue.
function timestamp(value) {
  if (!value) return Number.POSITIVE_INFINITY;
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? Number.POSITIVE_INFINITY : parsed;
}

/**
 * Order the coordinator's outstanding actions (SCRUM-72 AC1).
 *
 * Rank first, then the soonest event date, then the longest wait — so two
 * equally urgent items are settled by which event happens first, and two items
 * on the same day by which has been waiting longer. Returns a new array.
 */
export function prioritiseActionItems(items = []) {
  return [...items].sort(
    (a, b) =>
      rankOf(a.kind) - rankOf(b.kind) ||
      timestamp(a.starts_at) - timestamp(b.starts_at) ||
      timestamp(a.occurred_at) - timestamp(b.occurred_at) ||
      String(a.event_id).localeCompare(String(b.event_id)),
  );
}

/**
 * The three categories SCRUM-72 AC1 names, mapped onto action kinds.
 *
 * "Client clarification responses" is the return-for-amendment model the
 * customer confirmed (QA-22, QA-77): the coordinator returns a request with a
 * message, the organiser edits the same request and resubmits. A resubmission
 * *is* the clarification response. See REQUIREMENTS §6.4 — this replaced the
 * older "clarification thread" reading of SCRUM-33 (PROJECT_REVIEW B2a).
 */
const IMMEDIATE_ACTION_KINDS = [
  "arrangement_issue",
  "re_review_rejected",
  "cancellation_request",
  "change_request",
];

export function summariseActionItems(items = []) {
  const count = (predicate) => items.filter(predicate).length;
  return {
    immediate: count((item) => IMMEDIATE_ACTION_KINDS.includes(item.kind)),
    awaitingApproval: count((item) => item.kind === "awaiting_review"),
    clarificationResponses: count((item) => item.kind === "resubmitted"),
    total: items.length,
  };
}

function byEventDate(a, b) {
  return timestamp(a.starts_at) - timestamp(b.starts_at) || String(a.event_id).localeCompare(String(b.event_id));
}

/**
 * Bucket the coordinator's events under each active status (SCRUM-72 AC2).
 *
 * Every active status is returned even when it holds nothing, so the dashboard
 * shows a complete picture of the pipeline rather than hiding stages that
 * happen to be empty.
 */
export function groupActiveEventsByStatus(events = []) {
  return ACTIVE_COORDINATOR_STATUSES.map((status) => ({
    status,
    label: STATUS_LABELS[status],
    description: STATUS_DESCRIPTIONS[status],
    events: events.filter((event) => event.status === status).sort(byEventDate),
  }));
}

/** Count events per active status; statuses with no events are omitted. */
export function countByStatus(events = []) {
  return events.reduce((counts, event) => {
    if (!ACTIVE_COORDINATOR_STATUSES.includes(event.status)) return counts;
    counts[event.status] = (counts[event.status] ?? 0) + 1;
    return counts;
  }, {});
}

/**
 * The blocking arrangements an event is still missing (REQUIREMENTS §6.6).
 * `not_required` counts as ready — an event with no equipment needs is not
 * waiting on tech support. Programme and registration setup are shown for
 * information only and never block, so they are not listed here (QA-17, QA-133).
 */
const READINESS_ITEMS = [
  { key: "venue", label: "Venue" },
  { key: "equipment", label: "Equipment" },
  { key: "technical", label: "Technical readiness" },
];

const READY_STATES = ["ready", "not_required"];

export function outstandingReadiness(event) {
  const readiness = event?.readiness ?? {};
  return READINESS_ITEMS.filter((item) => !READY_STATES.includes(readiness[item.key])).map(
    (item) => item.label,
  );
}

/**
 * Events starting within `days` that still have a blocking gap — the schedule
 * overview from REQUIREMENTS §6.21. Events that have already started are
 * excluded; the window boundary is inclusive.
 */
export function readinessGaps(events = [], { now = new Date(), days = 14 } = {}) {
  const from = now.getTime();
  const until = from + days * 24 * 60 * 60 * 1000;

  return events
    .filter((event) => ["planning", "confirmed"].includes(event.status))
    .filter((event) => {
      const startsAt = timestamp(event.starts_at);
      return startsAt >= from && startsAt <= until;
    })
    .filter((event) => outstandingReadiness(event).length > 0)
    .sort(byEventDate);
}
