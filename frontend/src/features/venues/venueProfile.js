import { ACCESSIBILITY_FEATURES, FACILITIES, LAYOUTS } from "@/features/venues/venueSearchStore";
import { blockReasonLabel } from "@/features/venues/dashboard";

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

const LAYOUT_LABELS = Object.fromEntries(LAYOUTS.map((entry) => [entry.value, entry.label]));
const FACILITY_LABELS = Object.fromEntries(FACILITIES.map((entry) => [entry.value, entry.label]));
const ACCESSIBILITY_LABELS = Object.fromEntries(ACCESSIBILITY_FEATURES.map((entry) => [entry.value, entry.label]));

/**
 * The slides in the profile's carousel, in reading order (SCRUM-67).
 *
 * Real photos lead, then one schematic per layout the venue supports. Photos
 * are always absent today (VC-R8), so in practice this is the layout
 * schematics — which are drawn from `venue_layouts`, data we actually hold,
 * rather than being decorative filler.
 *
 * The capacity shown follows VS-R6: the per-layout figure when the venue
 * records one, otherwise the venue-wide capacity. `usesVenueCapacity` says
 * which of the two it is, so the diagram can label the fallback honestly
 * instead of implying the venue was measured in that layout.
 */
export function venueSlides(venue) {
  const photos = (venue?.photos ?? []).map((photo, index) => ({
    key: `photo-${index}`,
    kind: "photo",
    url: photo.url,
    caption: photo.caption ?? null,
  }));

  const layouts = (venue?.layouts ?? []).map((entry) => ({
    key: `layout-${entry.layout}`,
    kind: "layout",
    layout: entry.layout,
    label: LAYOUT_LABELS[entry.layout] ?? String(entry.layout ?? "").replace(/_/g, " "),
    capacity: entry.capacity_for_layout ?? venue?.capacity ?? null,
    usesVenueCapacity: entry.capacity_for_layout == null,
  }));

  return [...photos, ...layouts];
}

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
  // VC-R3 (SCRUM-63): not time-sensitive the way the two tabs above are, so
  // it carries no count, matching the attribute tabs' reasoning.
  { key: "history", label: "History", counted: false },
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
 * The edit form's initial state from a loaded venue (SCRUM-63).
 *
 * Layouts split into `selectedLayouts` (for the checkbox group) and
 * `layoutCapacities` (one optional number per layout), because the API's
 * `layouts` shape — a list of `{layout, capacity_for_layout}` — isn't what a
 * checkbox group plus per-item inputs bind to directly.
 */
export function venueToEditForm(venue) {
  const layouts = venue?.layouts ?? [];
  return {
    name: venue?.name ?? "",
    location: venue?.location ?? "",
    capacity: venue?.capacity != null ? String(venue.capacity) : "",
    selectedLayouts: layouts.map((entry) => entry.layout),
    layoutCapacities: Object.fromEntries(
      layouts.map((entry) => [entry.layout, entry.capacity_for_layout != null ? String(entry.capacity_for_layout) : ""]),
    ),
    facilities: [...(venue?.facilities ?? [])],
    accessibilityFeatures: [...(venue?.accessibility_features ?? [])],
    opensAt: venue?.opens_at ? venue.opens_at.slice(0, 5) : "",
    closesAt: venue?.closes_at ? venue.closes_at.slice(0, 5) : "",
    description: venue?.description ?? "",
    setupMinutes: String(venue?.setup_minutes ?? 0),
    turnaroundMinutes: String(venue?.turnaround_minutes ?? 0),
    emergencyAccess: venue?.emergency_access ?? "",
    restrictions: venue?.restrictions ?? "",
  };
}

/** The edit form's state, as the PATCH body SCRUM-63's endpoint expects. */
export function editFormToPayload(form, { confirm = false } = {}) {
  for (const [label, value] of [["Setup", form.setupMinutes], ["Turnaround", form.turnaroundMinutes]]) {
    // Digits only, up to Postgres `integer`; the customer set no business maximum (VC-R9).
    if (!/^\d+$/.test(String(value ?? "").trim()) || Number(value) > 2147483647) {
      throw new Error(`${label} must be a non-negative whole number of minutes.`);
    }
  }
  return {
    name: form.name.trim(),
    location: form.location.trim(),
    capacity: Number(form.capacity),
    layouts: form.selectedLayouts.map((layout) => ({
      layout,
      capacity_for_layout: form.layoutCapacities[layout] ? Number(form.layoutCapacities[layout]) : null,
    })),
    facilities: [...form.facilities],
    accessibility_features: [...form.accessibilityFeatures],
    opens_at: `${form.opensAt}:00`,
    closes_at: `${form.closesAt}:00`,
    description: form.description.trim() ? form.description.trim() : null,
    setup_minutes: Number(form.setupMinutes),
    turnaround_minutes: Number(form.turnaroundMinutes),
    emergency_access: form.emergencyAccess.trim() || null,
    restrictions: form.restrictions.trim() || null,
    confirm,
  };
}

const sgtFormatter = new Intl.DateTimeFormat("en-SG", {
  timeZone: "Asia/Singapore",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** One instant in Singapore time, as the venue page shows it ("30 Apr 2031, 10:30"). */
export function formatVenueInstant(value) {
  return sgtFormatter.format(new Date(value));
}

/** A booking or block period in Singapore time, as the venue page shows it. */
export function formatVenuePeriod(period) {
  return `${sgtFormatter.format(new Date(period.starts_at))} – ${sgtFormatter.format(new Date(period.ends_at))}`;
}

/** "Confirmed" / "Tentative" / "Under re-review" for a booking status (VC-R6). */
export function bookingStatusLabel(status) {
  return BOOKING_GROUPS.find((group) => group.statuses.includes(status))?.label ?? status;
}

// "1 booking", "2 bookings": the count the block and deactivate dialogs open
// their affected-bookings notices with.
export function countBookings(n) {
  return `${n} ${n === 1 ? "booking" : "bookings"}`;
}

// SCRUM-64 AC1: why a venue is inactive. Mirrors `public.venue_inactive_reason`.
export const INACTIVE_REASONS = [
  { value: "permanently_closed", label: "Permanently closed" },
  { value: "long_term_renovation", label: "Long-term renovation" },
  { value: "other", label: "Other" },
];

export function inactiveReasonLabel(value) {
  return INACTIVE_REASONS.find((reason) => reason.value === value)?.label ?? value;
}

const EDIT_HISTORY_FIELD_LABELS = {
  name: "Name",
  location: "Location",
  capacity: "Capacity",
  layouts: "Layouts",
  facilities: "Facilities",
  accessibility_features: "Accessibility",
  opens_at: "Opens",
  closes_at: "Closes",
  description: "Description",
  setup_minutes: "Default setup (minutes)",
  turnaround_minutes: "Default turnaround (minutes)",
  emergency_access: "Emergency access",
  restrictions: "Restrictions",
  is_active: "Status",
  inactive_reason: "Inactive reason",
  inactive_note: "Inactive note",
  block: "Block added",
};

function formatHistoryValue(field, value) {
  // SCRUM-51 AC9: a block's row records only what was added. SCRUM-54 AC4: a
  // change records the block before and after, with its status and note.
  if (field === "block") {
    if (!value) return "None";
    const note = value.note ? `Note: ${value.note}` : null;
    if (value.status === "removed") return ["Removed", note].filter(Boolean).join(" · ");
    return [formatVenuePeriod(value), blockReasonLabel(value.reason), value.notes, note].filter(Boolean).join(" · ");
  }
  if (field === "is_active" && typeof value === "boolean") return value ? "Active" : "Inactive";
  if (value == null || value === "") return "None recorded";
  if (field === "inactive_reason") return inactiveReasonLabel(value);
  if (field === "layouts") {
    const list = Array.isArray(value) ? value : [];
    if (!list.length) return "None";
    return list
      .map((entry) => `${LAYOUT_LABELS[entry.layout] ?? entry.layout}${entry.capacity_for_layout ? ` (${entry.capacity_for_layout})` : ""}`)
      .join(", ");
  }
  if (field === "facilities") {
    const list = Array.isArray(value) ? value : [];
    return list.length ? list.map((f) => FACILITY_LABELS[f] ?? f).join(", ") : "None";
  }
  if (field === "accessibility_features") {
    const list = Array.isArray(value) ? value : [];
    return list.length ? list.map((a) => ACCESSIBILITY_LABELS[a] ?? a).join(", ") : "None";
  }
  if (field === "opens_at" || field === "closes_at") return String(value).slice(0, 5);
  return String(value);
}

/**
 * One `venue_edit_history` row (VC-R3), reduced to only the fields that
 * actually changed — a field identical in `before` and `after` is noise a
 * reader has to filter out themselves, so this module filters it instead.
 */
// SCRUM-54 AC4: a block's row says whether it was added, ended early or removed.
function blockHistoryLabel(block) {
  if (block?.status === "ended_early") return "Block ended early";
  if (block?.status === "removed") return "Block removed";
  return EDIT_HISTORY_FIELD_LABELS.block;
}

export function summariseEditHistoryEntry(entry) {
  const before = entry?.before ?? {};
  const after = entry?.after ?? {};
  return Object.keys(EDIT_HISTORY_FIELD_LABELS)
    .filter((field) => JSON.stringify(before[field] ?? null) !== JSON.stringify(after[field] ?? null))
    .map((field) => ({
      field,
      label: field === "block" ? blockHistoryLabel(after.block) : EDIT_HISTORY_FIELD_LABELS[field],
      before: formatHistoryValue(field, before[field]),
      after: formatHistoryValue(field, after[field]),
    }));
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
