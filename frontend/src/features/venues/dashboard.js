/**
 * Pure presentation logic for the Venue Staff dashboard (SCRUM-70).
 *
 * No I/O lives here, so every rule is unit-testable on its own
 * (REQUIREMENTS §3.3). The view and the store both read from this module
 * rather than re-deriving counts, ordering or status wording themselves.
 */
import { SINGAPORE_OFFSET_MS, toInstant, toSingaporeIso } from "@/features/venues/singaporeTime";

/** Block reasons, labelled in one place (REQUIREMENTS §6.8 controlled list). */
export const BLOCK_REASON_LABELS = {
  maintenance: "Maintenance",
  renovation: "Renovation",
  safety: "Safety",
  internal_activity: "Internal activity",
  other: "Other",
};

/** Booking statuses as venue staff read them, not as the enum spells them. */
export const BOOKING_STATUS_LABELS = {
  held: "Pending hold",
  re_review: "Re-review",
  approved: "Approved",
  rejected: "Rejected",
  cancelled: "Cancelled",
  released: "Released",
};

export const blockReasonLabel = (reason) => BLOCK_REASON_LABELS[reason] ?? String(reason ?? "").replace(/_/g, " ");
export const bookingStatusLabel = (status) => BOOKING_STATUS_LABELS[status] ?? String(status ?? "").replace(/_/g, " ");

function timestamp(value) {
  if (!value) return Number.POSITIVE_INFINITY;
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? Number.POSITIVE_INFINITY : parsed;
}

/**
 * Pending holds, soonest expiry first (CR-99, W7 CR-04).
 *
 * A hold expires unless venue staff approve it in time, so the one nearest to
 * expiring is the one that most needs a decision. A hold without a usable
 * expiry sorts last. Ties break on id so two holds expiring in the same
 * instant keep a stable order between loads. Returns a new array.
 */
export function sortPendingHoldsSoonestExpiryFirst(holds = []) {
  return [...holds].sort(
    (a, b) => timestamp(a.expires_at) - timestamp(b.expires_at) || String(a.id).localeCompare(String(b.id)),
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "YYYY-MM-DDTHH:MM" on Singapore's clock: what a datetime-local input holds.
function singaporeLocal(value) {
  return new Date(toInstant(value).getTime() + SINGAPORE_OFFSET_MS).toISOString().slice(0, 16);
}

/** A hold's expiry as "5 Aug 2031, 12:00" in Singapore time, the wording the
 * coordinator's notices use; null when there is none. */
export function formatHoldExpiry(value) {
  if (!Number.isFinite(timestamp(value))) return null;
  const [date, time] = singaporeLocal(value).split("T");
  const [year, month, day] = date.split("-");
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}, ${time}`;
}

/**
 * What the Change expiry picker allows (CR-99 AC1, AC2): from the next whole
 * minute to the event start, opening on the current expiry. The server checks
 * the same bounds; these only keep the picker from offering a refusal.
 */
export function expiryInputBounds(hold, now = new Date()) {
  const nextMinute = new Date(Math.floor(now.getTime() / 60000) * 60000 + 60000);
  return {
    min: singaporeLocal(nextMinute),
    max: singaporeLocal(hold.period.starts_at),
    value: singaporeLocal(hold.expires_at),
  };
}

/** A datetime-local pick, read as Singapore time, as an ISO instant; null if
 * it isn't a full date and time. */
export function expiryInputToIso(value) {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})$/.exec(value ?? "");
  return match ? toSingaporeIso(match[1], match[2]) : null;
}

/** Whole days a request has been waiting. Never negative. */
export function waitingDays(booking, now = new Date()) {
  const requested = timestamp(booking?.requested_at);
  if (!Number.isFinite(requested)) return null;
  const days = Math.floor((now.getTime() - requested) / (24 * 60 * 60 * 1000));
  return Math.max(days, 0);
}

/**
 * How to refer to the event behind a booking.
 *
 * There is no `events` table yet, so `event_name` is always null and the only
 * honest handle is a short form of the id. Inventing a name would be worse
 * than a terse one, and this falls through to the real name the moment
 * SCRUM-8/19 start sending it.
 */
export function formatEventReference(booking) {
  if (booking?.event_name) return booking.event_name;
  const id = String(booking?.event_id ?? "");
  return id ? `Event ${id.slice(0, 8).toUpperCase()}` : "Unidentified event";
}

/** The four figures the stat tiles show (REQUIREMENTS §6.21, in priority order). */
export function summariseVenueStaffDashboard({
  venues = [],
  pendingHolds = [],
  reReviewBookings = [],
  blocks = [],
} = {}) {
  const active = venues.filter((venue) => venue.is_active).length;
  return {
    pendingHolds: pendingHolds.length,
    reReview: reReviewBookings.length,
    blocks: blocks.length,
    venuesTotal: venues.length,
    venuesActive: active,
    venuesInactive: venues.length - active,
  };
}

/**
 * Venue statuses, worst first (SCRUM-70 AC2: status at a glance).
 *
 * Precedence is inactive → blocked → block scheduled → active. An inactive
 * venue cannot be booked at all, so that outranks a block sitting on it:
 * showing "blocked until Thursday" for a venue that is out of service
 * entirely would understate the problem.
 *
 * `venue_blocks` has no active flag, so "blocked now" is derived —
 * `starts_at <= now < ends_at`, half-open like everything else, so a block
 * ending exactly now has already ended (§6.14, CAL-R2).
 */
export const VENUE_STATUS_ORDER = ["blocked", "block_scheduled", "active", "inactive"];

const STATUS_META = {
  blocked: { label: "Blocked now", tone: "red" },
  block_scheduled: { label: "Block scheduled", tone: "yellow" },
  active: { label: "Active", tone: "green" },
  inactive: { label: "Inactive", tone: "muted" },
};

export const venueStatusMeta = (status) => STATUS_META[status] ?? STATUS_META.active;

/** The filter row's "no filter" key, kept out of the status vocabulary. */
export const ALL_VENUE_STATUSES = "all";

/**
 * The status filters to offer for a set of venue rows (SCRUM-70 AC2).
 *
 * Only statuses some venue actually has are offered: a control that can only
 * ever produce an empty list is a dead control, and it would also invite the
 * reading that the dashboard is hiding something. Each option carries its own
 * count, so the row doubles as the at-a-glance breakdown AC2 asks for.
 *
 * "All" leads, so the unfiltered list is always one click away, and the rest
 * follow `VENUE_STATUS_ORDER` — worst first, matching the list beneath them.
 */
export function venueStatusFilterOptions(rows = []) {
  const counts = new Map();
  for (const row of rows) counts.set(row.status, (counts.get(row.status) ?? 0) + 1);

  return [
    { key: ALL_VENUE_STATUSES, label: "All", count: rows.length },
    ...VENUE_STATUS_ORDER.filter((status) => counts.has(status)).map((status) => ({
      key: status,
      label: venueStatusMeta(status).label,
      count: counts.get(status),
    })),
  ];
}

/**
 * Narrow venue rows to one status, preserving their order.
 *
 * A key outside the vocabulary falls back to every row rather than to none:
 * an empty venue list reads as "you have no venues", which would be a lie.
 * Showing too much is recoverable at a glance; showing nothing is not.
 */
export function filterVenueStatuses(rows = [], status = ALL_VENUE_STATUSES) {
  if (status === ALL_VENUE_STATUSES || !VENUE_STATUS_ORDER.includes(status)) return [...rows];
  return rows.filter((row) => row.status === status);
}

export function venueStatuses(venues = [], blocks = [], now = new Date()) {
  const at = now.getTime();

  return venues
    .map((venue) => {
      const mine = blocks
        .filter((block) => block.venue_id === venue.id)
        .sort((a, b) => timestamp(a.period?.starts_at) - timestamp(b.period?.starts_at));

      const current = mine.find(
        (block) => timestamp(block.period?.starts_at) <= at && at < timestamp(block.period?.ends_at),
      );
      const next = mine.find((block) => timestamp(block.period?.starts_at) > at);

      let status = "active";
      if (!venue.is_active) status = "inactive";
      else if (current) status = "blocked";
      else if (next) status = "block_scheduled";

      return {
        venue,
        status,
        blockedUntil: current?.period?.ends_at ?? null,
        nextBlockStartsAt: next?.period?.starts_at ?? null,
        reason: current?.reason ?? next?.reason ?? null,
      };
    })
    .sort(
      (a, b) =>
        VENUE_STATUS_ORDER.indexOf(a.status) - VENUE_STATUS_ORDER.indexOf(b.status) ||
        String(a.venue.name).localeCompare(String(b.venue.name)),
    );
}
