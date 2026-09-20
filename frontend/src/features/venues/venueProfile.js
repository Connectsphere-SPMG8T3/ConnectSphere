/**
 * Pure presentation logic for the venue profile page (SCRUM-67).
 *
 * The API returns one flat list of the bookings that occupy a venue, each with
 * its status, and deliberately no server-side counts (`VenueDetail` in
 * `backend/app/modules/venues/schemas.py` says why). Grouping and counting that
 * complete list is this module's job, so the view stays markup and the rules
 * are unit-testable without mounting anything — the same split as
 * `features/venues/dashboard.js`.
 */

/**
 * How the profile groups the bookings that occupy a venue (§6.14).
 *
 * The wording follows `CONTEXT.md`: an approved booking is the confirmed one,
 * a hold is the tentative one. `re_review` is neither — it is a settled
 * booking reopened after a significant change (§6.19) — so it gets its own
 * group rather than being counted as confirmed, which would overstate what is
 * actually agreed, or as tentative, which would understate it.
 *
 * Every group still occupies the venue, so all three constrain planning.
 */
export const BOOKING_GROUPS = [
  {
    key: "confirmed",
    statuses: ["approved"],
    label: "Confirmed",
    detail: "Approved by venue staff.",
    tone: "blue",
  },
  {
    key: "tentative",
    statuses: ["held"],
    label: "Tentative",
    detail: "Held while venue staff decide. A hold occupies the venue exactly like an approved booking.",
    tone: "yellow",
  },
  {
    key: "reReview",
    statuses: ["re_review"],
    label: "Under re-review",
    detail: "Previously approved; a significant change reopened the arrangement.",
    tone: "red",
  },
];

const KNOWN_STATUSES = new Set(BOOKING_GROUPS.flatMap((group) => group.statuses));

const startsAt = (booking) => {
  const parsed = new Date(booking?.period?.starts_at ?? NaN).getTime();
  return Number.isNaN(parsed) ? Number.POSITIVE_INFINITY : parsed;
};

const soonestFirst = (bookings) => [...bookings].sort((a, b) => startsAt(a) - startsAt(b));

/**
 * The venue's upcoming bookings, split into the groups above (AC3).
 *
 * Every group comes back even when empty, so the profile can state "none"
 * instead of hiding the question. A status this module does not recognise —
 * a new enum value that shipped ahead of this list — is collected into a
 * trailing group rather than dropped: a booking nobody can see is the one way
 * this screen could actively mislead someone planning around the venue.
 */
export function groupUpcomingBookings(bookings = []) {
  const list = Array.isArray(bookings) ? bookings : [];
  const groups = BOOKING_GROUPS.map((group) => ({
    ...group,
    bookings: soonestFirst(list.filter((booking) => group.statuses.includes(booking?.status))),
  }));

  const unrecognised = list.filter((booking) => !KNOWN_STATUSES.has(booking?.status));
  if (unrecognised.length > 0) {
    groups.push({
      key: "other",
      statuses: [],
      label: "Other",
      detail: "Occupies the venue; status not recognised by this page.",
      tone: "plain",
      bookings: soonestFirst(unrecognised),
    });
  }
  return groups;
}

/**
 * The setup/turnaround time between consecutive bookings, in words (AC1).
 *
 * The customer set it to zero (QA-28), which is why the zero case reads as a
 * statement about back-to-back bookings rather than "0 min" — the figure on
 * its own invites the reader to assume it was never filled in.
 */
export function formatTurnaround(minutes) {
  if (!Number.isFinite(minutes)) return "Not recorded";
  if (minutes === 0) return "None — bookings may run back to back";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const parts = [];
  if (hours > 0) parts.push(`${hours} h`);
  if (rest > 0) parts.push(`${rest} min`);
  return `${parts.join(" ")} between bookings`;
}

/**
 * Who last edited the profile (AC2).
 *
 * `updated_by` is null for every venue edited before the column existed, and
 * for an editor whose account has been removed; `full_name` is nullable in
 * `profiles`. Each case says so rather than showing a plausible-looking name,
 * the same reasoning as `formatEventReference` in `features/venues/dashboard.js`.
 */
export function lastEditorName(editor) {
  if (!editor) return "Not recorded";
  if (editor.full_name) return editor.full_name;
  const id = String(editor.id ?? "");
  return id ? `Account ${id.slice(0, 8).toUpperCase()}` : "Not recorded";
}

/**
 * The profile's tabs, in a fixed reading order (SCRUM-67).
 *
 * The attributes come first because they answer "is this the right venue?",
 * and the two time-based sections follow because they answer "can I have it?".
 */
export const VENUE_PROFILE_TABS = [
  { key: "capacity", label: "Capacity & hours", counted: false },
  { key: "facilities", label: "Facilities & access", counted: false },
  { key: "bookings", label: "Upcoming bookings", counted: true },
  { key: "blocks", label: "Blocks", counted: true },
];

/**
 * The tabs with a count on the two that hide something time-sensitive.
 *
 * Tabs hide content by design, which is a real cost for AC3: the bookings
 * summary is the thing staff are planning around, and a closed tab could
 * imply there is nothing behind it. The count on the tab itself is what keeps
 * that honest — "Upcoming bookings 2" is visible without opening anything.
 *
 * The attribute tabs get `null`, not `0`. Every venue has capacity and hours,
 * so a zero there would be read as "none recorded", which is a different and
 * false claim.
 */
export function venueProfileTabs(venue) {
  const counts = {
    bookings: venue?.upcoming_bookings?.length ?? 0,
    blocks: venue?.upcoming_blocks?.length ?? 0,
  };
  return VENUE_PROFILE_TABS.map((tab) => ({
    ...tab,
    count: tab.counted ? counts[tab.key] : null,
  }));
}

/**
 * Move `delta` places through `length` items, wrapping at both ends.
 *
 * Wrapping rather than clamping, so the carousel never dead-ends on the first
 * or last photo with a control that silently does nothing. Guards `length <= 0`
 * because the modulo would otherwise produce `NaN` and leave the carousel
 * stuck on an index that renders nothing.
 */
export function stepIndex(current, length, delta) {
  if (!length || length <= 0) return 0;
  return (((current + delta) % length) + length) % length;
}

/**
 * Which booking group the Upcoming bookings tab should open on.
 *
 * The first group that actually has something, rather than always `confirmed`.
 * A venue whose only commitment is a hold would otherwise open on an empty
 * "Confirmed" panel, which reads as "nothing booked" — the precise misreading
 * the counts on the tabs exist to prevent. Falls back to the first group when
 * every one is empty, so the tab row still has a selection.
 */
export function defaultBookingGroupKey(groups) {
  const list = Array.isArray(groups) ? groups : [];
  const occupied = list.find((group) => group.bookings?.length > 0);
  return occupied?.key ?? list[0]?.key ?? BOOKING_GROUPS[0].key;
}
