/**
 * A venue's availability calendar for Venue Staff (SCRUM-57).
 *
 * No I/O and no Vue here, so every rule is unit-testable on its own
 * (REQUIREMENTS §3.3). Grid construction is reused from `calendar.js`; this
 * module adds what a per-venue view needs on top: the five entry types, the
 * setup/event/turnaround bands, the day and week time grid, and the details
 * an entry opens. Every venue is in Singapore and stores no timezone of its
 * own, so the venue's timezone is Asia/Singapore (REQUIREMENTS §9).
 */

import { buildMonthGrid, shiftMonth, shiftWeekKey, startOfWeekKey } from "@/features/venues/calendar";
import { blockReasonLabel, bookingStatusLabel } from "@/features/venues/dashboard";
import { singaporeDayKey, startOfSingaporeDayUtc, toInstant } from "@/features/venues/singaporeTime";
import { formatVenueInstant } from "@/features/venues/venueProfile";

const DAY_MS = 24 * 60 * 60 * 1000;
const VENUE_TIME_ZONE = "Asia/Singapore";

/**
 * The five things an entry can be (AC2, AC8). Each has a label and a pattern
 * as well as a tone, so the types stay apart without colour. Re-review isn't
 * one of AC2's four: those bookings occupy the venue too, so hiding them would
 * show it free (REQUIREMENTS §9).
 */
export const ENTRY_TYPES = [
  {
    key: "confirmed",
    label: "Confirmed",
    tone: "blue",
    pattern: "solid",
    description: "Approved booking",
  },
  {
    key: "tentative",
    label: "Tentative",
    tone: "yellow",
    pattern: "dashed",
    description: "Hold awaiting a decision, until it expires",
  },
  {
    key: "affected",
    label: "Affected",
    tone: "red",
    pattern: "stripes",
    description: "Venue unavailable; still occupies until restored or released",
  },
  {
    key: "re_review",
    label: "Re-review",
    tone: "blue",
    pattern: "dots",
    description: "Approved booking whose event changed, awaiting a new decision",
  },
  {
    key: "blocked",
    label: "Blocked",
    tone: "ink",
    pattern: "crosshatch",
    description: "Venue blocked, with its reason",
  },
];

export const VIEWS = [
  { key: "day", label: "Day" },
  { key: "week", label: "Week" },
  { key: "month", label: "Month" },
];

/** Look up a type's display metadata, tolerating one the SPA doesn't know. */
export function entryTypeMeta(key) {
  return ENTRY_TYPES.find((type) => type.key === key) ?? { key, label: key, tone: "ink", pattern: "solid" };
}

function isExpiredHold(entry, now) {
  return entry.status === "held" && Boolean(entry.expires_at) && toInstant(entry.expires_at) <= now;
}

/**
 * The API's entries in the shape the grids place: by the occupied window, so a
 * booking's setup and turnaround sit on the calendar too (AC5), keeping its own
 * time for the bands. `kind` is the entry type, which is what `calendar.js`
 * groups and orders by.
 *
 * A hold whose expiry passes while the page is open stops occupying the venue
 * at once, not on the next refresh (AC6).
 */
export function toCalendarEntries(entries = [], now = new Date()) {
  return entries
    .filter((entry) => !isExpiredHold(entry, now))
    .map((entry) => ({
      ...entry,
      kind: entry.type,
      source: entry.kind,
      startsAt: entry.occupied_period.starts_at,
      endsAt: entry.occupied_period.ends_at,
      bookedStartsAt: entry.period.starts_at,
      bookedEndsAt: entry.period.ends_at,
      label: entry.kind === "block" ? blockReasonLabel(entry.reason) : (entry.event_name ?? "Unnamed event"),
    }));
}

/**
 * A booking as setup, event and turnaround, each drawn as its own band (AC5).
 * A buffer of zero minutes has no band. A block has no buffer: one band.
 */
export function bookingBands(entry) {
  if (entry.source === "block") {
    return [{ part: "event", label: "Blocked", startsAt: entry.startsAt, endsAt: entry.endsAt }];
  }
  const bands = [
    { part: "setup", label: "Setup", startsAt: entry.startsAt, endsAt: entry.bookedStartsAt },
    { part: "event", label: "Event", startsAt: entry.bookedStartsAt, endsAt: entry.bookedEndsAt },
    { part: "turnaround", label: "Turnaround", startsAt: entry.bookedEndsAt, endsAt: entry.endsAt },
  ];
  return bands.filter((band) => toInstant(band.endsAt) > toInstant(band.startsAt));
}

function dateOfKey(key) {
  return new Date(`${key}T00:00:00Z`);
}

function addDays(key, delta) {
  const date = dateOfKey(key);
  date.setUTCDate(date.getUTCDate() + delta);
  return date.toISOString().slice(0, 10);
}

/** The Singapore days a view shows: one, Monday to Sunday, or a six-week month grid. */
export function viewDayKeys(view, anchorKey) {
  if (view === "day") return [anchorKey];
  if (view === "week") {
    const monday = startOfWeekKey(anchorKey);
    return Array.from({ length: 7 }, (_, i) => addDays(monday, i));
  }
  const [year, month] = anchorKey.split("-").map(Number);
  return buildMonthGrid(year, month - 1, [], { weeks: 6 }).cells.map((cell) => cell.key);
}

/** The `[startsAt, endsAt)` instants a view asks the API about. */
export function viewRange(view, anchorKey) {
  const keys = viewDayKeys(view, anchorKey);
  const startsAt = startOfSingaporeDayUtc(keys[0]);
  const endsAt = new Date(startOfSingaporeDayUtc(keys[keys.length - 1]).getTime() + DAY_MS);
  return { startsAt, endsAt };
}

/** Step a view's anchor by a day, a week or a month; a month lands on its 1st. */
export function shiftAnchor(view, anchorKey, delta) {
  if (view === "day") return addDays(anchorKey, delta);
  if (view === "week") return shiftWeekKey(anchorKey, delta);
  const [year, month] = anchorKey.split("-").map(Number);
  const next = shiftMonth({ year, month: month - 1 }, delta);
  return `${next.year}-${String(next.month + 1).padStart(2, "0")}-01`;
}

const dayTitleFormatter = new Intl.DateTimeFormat("en-SG", { dateStyle: "full", timeZone: "UTC" });
const rangeFormatter = new Intl.DateTimeFormat("en-SG", { day: "numeric", month: "short", timeZone: "UTC" });
const monthFormatter = new Intl.DateTimeFormat("en-SG", { month: "long", year: "numeric", timeZone: "UTC" });

/** What the header names: a day, a week's date range, or a month. */
export function periodLabel(view, anchorKey) {
  if (view === "day") return dayTitleFormatter.format(dateOfKey(anchorKey));
  if (view === "week") {
    const keys = viewDayKeys("week", anchorKey);
    const last = keys[6];
    return `${rangeFormatter.format(dateOfKey(keys[0]))} – ${rangeFormatter.format(dateOfKey(last))} ${last.slice(0, 4)}`;
  }
  return monthFormatter.format(dateOfKey(anchorKey));
}

/**
 * Where each entry sits in one day's column of the time grid, as percentages
 * of the day. An entry running past midnight is clipped to the day, and says
 * so, so it doesn't look as if it starts or stops there. A half-open window
 * ending at the day's first instant doesn't touch it (CAL-R2).
 *
 * Entries that overlap share the column side by side: each cluster of
 * overlapping entries is split into the fewest lanes (greedy interval
 * colouring, as `layoutWeekSegments` does for the month bars), and an entry
 * on its own keeps the full width.
 */
export function layoutDay(dayKey, entries) {
  const dayStart = startOfSingaporeDayUtc(dayKey).getTime();
  const dayEnd = dayStart + DAY_MS;
  const touching = entries
    .map((entry) => ({ entry, start: toInstant(entry.startsAt).getTime(), end: toInstant(entry.endsAt).getTime() }))
    .filter(({ start, end }) => start < dayEnd && end > dayStart)
    .sort((a, b) => a.start - b.start || b.end - a.end);

  const placed = [];
  let cluster = [];
  let clusterEnd = -Infinity;
  const closeCluster = () => {
    const lanes = cluster.reduce((count, item) => Math.max(count, item.lane + 1), 0);
    for (const item of cluster) item.lanes = lanes;
    cluster = [];
  };

  for (const { entry, start, end } of touching) {
    if (start >= clusterEnd) {
      closeCluster();
      clusterEnd = -Infinity;
    }
    const busy = new Set(cluster.filter((item) => item.end > start).map((item) => item.lane));
    let lane = 0;
    while (busy.has(lane)) lane += 1;
    const clippedStart = Math.max(start, dayStart);
    const clippedEnd = Math.min(end, dayEnd);
    const item = {
      entry,
      end,
      lane,
      lanes: 1,
      top: ((clippedStart - dayStart) / DAY_MS) * 100,
      height: ((clippedEnd - clippedStart) / DAY_MS) * 100,
      continuesBefore: start < dayStart,
      continuesAfter: end > dayEnd,
    };
    cluster.push(item);
    placed.push(item);
    clusterEnd = Math.max(clusterEnd, end);
  }
  closeCluster();

  return placed.map(({ end, ...item }) => item);
}

const dateFormatter = new Intl.DateTimeFormat("en-SG", {
  timeZone: VENUE_TIME_ZONE,
  weekday: "short",
  day: "numeric",
  month: "short",
  year: "numeric",
});
const timeFormatter = new Intl.DateTimeFormat("en-SG", {
  timeZone: VENUE_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

function formatDate(value) {
  const parts = Object.fromEntries(dateFormatter.formatToParts(toInstant(value)).map((p) => [p.type, p.value]));
  return `${parts.weekday} ${parts.day} ${parts.month} ${parts.year}`;
}

/** A clock time in the venue's timezone, e.g. "09:30" (AC10). */
export function formatTime(value) {
  return timeFormatter.format(toInstant(value));
}

function formatInstant(value) {
  return `${formatDate(value)}, ${formatTime(value)}`;
}

/**
 * A window in the venue's timezone (AC10): its day once when it ends the same
 * day (a window ending at midnight counts as that day), both days otherwise.
 */
export function formatWindow(startsAt, endsAt) {
  const lastInstant = new Date(toInstant(endsAt).getTime() - 1);
  if (singaporeDayKey(startsAt) === singaporeDayKey(lastInstant)) {
    return `${formatDate(startsAt)}, ${formatTime(startsAt)}–${formatTime(endsAt)}`;
  }
  return `${formatInstant(startsAt)} – ${formatInstant(endsAt)}`;
}

function bufferText(entry) {
  if (!entry.setup_minutes && !entry.turnaround_minutes) return "None";
  const before = entry.setup_minutes ? `${entry.setup_minutes} min before` : "None before";
  const after = entry.turnaround_minutes ? `${entry.turnaround_minutes} min after` : "none after";
  return `${before}, ${after}`;
}

/** What selecting an entry shows (AC9), as label/value rows. */
export function entryDetails(entry) {
  const type = entryTypeMeta(entry.kind).label;
  const occupied = formatWindow(entry.startsAt, entry.endsAt);
  if (entry.source === "block") {
    const who = entry.created_by?.full_name ?? "Unknown user";
    return [
      { label: "Type", value: type },
      { label: "Reason", value: blockReasonLabel(entry.reason) },
      ...(entry.notes ? [{ label: "Details", value: entry.notes }] : []),
      { label: "Occupied window", value: occupied },
      { label: "Set by", value: entry.created_at ? `${who} · ${formatVenueInstant(entry.created_at)}` : who },
    ];
  }
  return [
    { label: "Event", value: entry.label },
    { label: "Type", value: type },
    { label: "Status", value: bookingStatusLabel(entry.status) },
    { label: "Occupied window", value: occupied },
    { label: "Event time", value: formatWindow(entry.bookedStartsAt, entry.bookedEndsAt) },
    { label: "Setup and turnaround", value: bufferText(entry) },
    ...(entry.status === "held" && entry.expires_at
      ? [{ label: "Hold expires", value: formatInstant(entry.expires_at) }]
      : []),
    ...(entry.flag === "affected" && entry.flag_reason ? [{ label: "Affected because", value: entry.flag_reason }] : []),
  ];
}

/**
 * Where each band of an entry sits inside the entry's box on one day, as
 * percentages of that box, which `layoutDay` has already clipped to the day.
 * A band that falls wholly on another day is left out.
 */
export function bandLayout(entry, dayKey) {
  const dayStart = startOfSingaporeDayUtc(dayKey).getTime();
  const dayEnd = dayStart + DAY_MS;
  const boxStart = Math.max(toInstant(entry.startsAt).getTime(), dayStart);
  const boxEnd = Math.min(toInstant(entry.endsAt).getTime(), dayEnd);
  const span = boxEnd - boxStart;
  return bookingBands(entry)
    .map((band) => {
      const start = Math.max(toInstant(band.startsAt).getTime(), boxStart);
      const end = Math.min(toInstant(band.endsAt).getTime(), boxEnd);
      return {
        ...band,
        top: ((start - boxStart) / span) * 100,
        height: ((end - start) / span) * 100,
        minutes: (end - start) / 60_000,
      };
    })
    .filter((band) => band.height > 0);
}

/** A tentative hold's expiry, as the grid shows it under the type (AC6); null otherwise. */
export function holdExpiry(entry) {
  return entry.kind === "tentative" && entry.expires_at ? `Expires ${formatInstant(entry.expires_at)}` : null;
}

/** The type an entry shows on the grid, with a tentative hold's expiry (AC2, AC6). */
export function entryBadge(entry) {
  const label = entryTypeMeta(entry.kind).label;
  return entry.kind === "tentative" && entry.expires_at ? `${label} · expires ${formatInstant(entry.expires_at)}` : label;
}
