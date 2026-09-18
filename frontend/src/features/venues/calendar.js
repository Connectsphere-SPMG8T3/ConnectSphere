/**
 * Month-grid construction for the venue-staff calendar (SCRUM-70).
 *
 * No I/O and no Vue here, so every rule below is unit-testable on its own
 * (REQUIREMENTS §3.3). The component renders what this module returns and
 * decides nothing about which day an item belongs to.
 */

import { singaporeDayKey, startOfSingaporeDayUtc, toInstant } from "@/features/venues/singaporeTime";

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * Monday-first, which is both the ISO ordering and the Singapore working week.
 * It also keeps Saturday and Sunday adjacent, so a weekend-heavy month reads as
 * one block rather than being split across the two ends of the row.
 */
export const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/**
 * How an item is drawn, and which one wins when a day carries several.
 *
 * Order is severity: a blocked venue is a fact about the venue, a hold is a
 * decision waiting on staff, a re-review is a decision waiting on staff that
 * something else already disturbed. The colours are the same ones the stat
 * tiles use for the same things, so colour means one thing across the page.
 */
export const CALENDAR_KINDS = [
  { key: "block", label: "Blocked", tone: "red" },
  { key: "held", label: "Pending hold", tone: "yellow" },
  { key: "re_review", label: "Re-review", tone: "blue" },
];

const KIND_ORDER = CALENDAR_KINDS.map((kind) => kind.key);

/** Look up a kind's display metadata, tolerating one the SPA doesn't know. */
export function calendarKindMeta(key) {
  return CALENDAR_KINDS.find((kind) => kind.key === key) ?? { key, label: key, tone: "blue" };
}

/**
 * The Singapore day keys a half-open `[startsAt, endsAt)` range occupies.
 *
 * The rule that matters: the last instant *inside* the range is `endsAt − ε`,
 * so the last day marked is the day of `endsAt - 1ms`. A range ending exactly
 * at midnight therefore stops on the previous day, with no special case and no
 * branch — which is precisely what §6.14 and CAL-R2 ask for. Two seeded blocks
 * prove it: 1–15 Oct marks through the 14th, and 20–22 Oct marks through the
 * 21st.
 *
 * `fromKey`/`toKey` clip to the visible grid, so a block running for years
 * costs at most 42 iterations instead of thousands.
 */
export function singaporeDayKeysCovered(startsAt, endsAt, { fromKey, toKey } = {}) {
  const start = toInstant(startsAt);
  const end = toInstant(endsAt);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return [];
  // The backend's Period forbids this, but one malformed row should not be
  // able to blank the whole calendar.
  if (end <= start) return [];

  const lastKey = singaporeDayKey(new Date(end.getTime() - 1));
  const firstKey = singaporeDayKey(start);

  // Start iterating at the clip window rather than at the item's own start, so
  // the cost is bounded by the grid and not by how long the item runs.
  const beginKey = fromKey !== undefined && fromKey > firstKey ? fromKey : firstKey;
  if (toKey !== undefined && beginKey > toKey) return [];
  if (beginKey > lastKey) return [];

  const keys = [];
  let cursor = startOfSingaporeDayUtc(beginKey);
  for (;;) {
    const key = singaporeDayKey(cursor);
    if (key > lastKey) break;
    if (toKey !== undefined && key > toKey) break;
    keys.push(key);
    // Every Singapore day is exactly 24h — no daylight saving, ever — so this
    // is exact rather than an approximation that drifts twice a year.
    cursor = new Date(cursor.getTime() + DAY_MS);
  }
  return keys;
}

/**
 * Flatten the dashboard payload into the one shape the calendar understands.
 * Each item keeps enough to render a row in the day panel and to link onward.
 */
export function toCalendarItems({ blocks = [], pendingHolds = [], reReviewBookings = [] } = {}) {
  const fromBooking = (kind) => (booking) => ({
    kind,
    id: booking.id,
    venueId: booking.venue_id,
    venueName: booking.venue_name,
    startsAt: booking.period?.starts_at,
    endsAt: booking.period?.ends_at,
    detail: booking.event_name ?? null,
    eventId: booking.event_id,
  });

  return [
    ...blocks.map((block) => ({
      kind: "block",
      id: block.id,
      venueId: block.venue_id,
      venueName: block.venue_name,
      startsAt: block.period?.starts_at,
      endsAt: block.period?.ends_at,
      detail: block.reason,
      notes: block.notes ?? null,
    })),
    ...pendingHolds.map(fromBooking("held")),
    ...reReviewBookings.map(fromBooking("re_review")),
  ];
}

function sortItems(a, b) {
  return (
    KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind) ||
    String(a.startsAt).localeCompare(String(b.startsAt)) ||
    String(a.venueName).localeCompare(String(b.venueName)) ||
    String(a.id).localeCompare(String(b.id))
  );
}

/**
 * Place `items` onto a list of day cells and finish them off.
 *
 * Shared by the month and week grids so both agree on what a cell means:
 * which items fall on it, how many of each kind, which tones to draw, and
 * whether it is today.
 */
function decorateCells(cells, items, today) {
  const byKey = new Map(cells.map((cell) => [cell.key, cell]));
  const fromKey = cells[0].key;
  const toKey = cells[cells.length - 1].key;

  for (const item of items) {
    for (const key of singaporeDayKeysCovered(item.startsAt, item.endsAt, { fromKey, toKey })) {
      const cell = byKey.get(key);
      if (!cell) continue;
      cell.items.push(item);
      cell.markers[item.kind] = (cell.markers[item.kind] ?? 0) + 1;
    }
  }

  const todayKey = singaporeDayKey(today);
  for (const cell of cells) {
    cell.isToday = cell.key === todayKey;
    cell.items.sort(sortItems);
    cell.hasItems = cell.items.length > 0;
    cell.tones = KIND_ORDER.filter((kind) => cell.markers[kind]).map((kind) => calendarKindMeta(kind).tone);
  }

  return cells;
}

function blankCell(date, inCurrentMonth) {
  return {
    key: date.toISOString().slice(0, 10),
    day: date.getUTCDate(),
    inCurrentMonth,
    isToday: false,
    markers: {},
    tones: [],
    items: [],
    hasItems: false,
  };
}

/** A `"YYYY-MM-DD"` key as a UTC-midnight Date, for pure calendar arithmetic. */
function dateOfKey(key) {
  return new Date(`${key}T00:00:00Z`);
}

/**
 * Build one month's grid.
 *
 * `monthIndex` is 0-based, matching JS `Date`. The grid is a *calendar*
 * construction rather than a set of instants, so its weekday and length are
 * computed from UTC fields: no timezone enters until an item is placed, and
 * placement goes through `singaporeDayKeysCovered`.
 *
 * `weeks` forces a row count. Left unset, the grid is only as tall as the
 * month needs (4, 5 or 6 rows). The dashboard passes 6, because a panel that
 * changed height as you stepped through months would shift everything beside
 * it; a consistently present trailing row reads as a calendar, whereas one
 * that appears and disappears reads as a bug.
 */
export function buildMonthGrid(year, monthIndex, items = [], { today = new Date(), weeks } = {}) {
  const firstOfMonth = new Date(Date.UTC(year, monthIndex, 1));
  // getUTCDay() is 0=Sunday; shift so Monday is 0.
  const leading = (firstOfMonth.getUTCDay() + 6) % 7;
  // Day 0 of the next month is the last day of this one.
  const daysInMonth = new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
  const needed = Math.ceil((leading + daysInMonth) / 7);
  // Never truncate: a forced row count below what the month needs would drop
  // real days off the end.
  const cellCount = Math.max(weeks ?? needed, needed) * 7;

  const month = ((monthIndex % 12) + 12) % 12;
  const cells = [];
  for (let i = 0; i < cellCount; i += 1) {
    const date = new Date(Date.UTC(year, monthIndex, 1 - leading + i));
    cells.push(blankCell(date, date.getUTCMonth() === month));
  }

  decorateCells(cells, items, today);
  return { year, month: monthIndex, cells, weekdays: WEEKDAY_LABELS };
}

/** The Monday of the week containing `value` (a day key or an instant). */
export function startOfWeekKey(value) {
  const key = typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : singaporeDayKey(value);
  const date = dateOfKey(key);
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
  return date.toISOString().slice(0, 10);
}

/** Move a week anchor by `delta` weeks. Always returns a Monday. */
export function shiftWeekKey(anchorKey, delta) {
  const date = dateOfKey(startOfWeekKey(anchorKey));
  date.setUTCDate(date.getUTCDate() + delta * 7);
  return date.toISOString().slice(0, 10);
}

/**
 * Build one week's grid: seven cells, Monday first.
 *
 * Same cell shape as the month grid, so the component renders either from one
 * set of rules. `inCurrentMonth` is always true here — every day in a week
 * view is in view, so there is nothing to grey out.
 */
export function buildWeekGrid(anchorKey, items = [], { today = new Date() } = {}) {
  const startKey = startOfWeekKey(anchorKey);
  const start = dateOfKey(startKey);

  const cells = [];
  for (let i = 0; i < 7; i += 1) {
    const date = new Date(start.getTime());
    date.setUTCDate(date.getUTCDate() + i);
    cells.push(blankCell(date, true));
  }

  decorateCells(cells, items, today);
  return { startKey, endKey: cells[6].key, cells, weekdays: WEEKDAY_LABELS };
}

/**
 * Which week to open on — the week-view twin of `defaultMonth`.
 *
 * The current week if it carries anything, otherwise the earliest later week
 * that does, otherwise the current week.
 */
export function defaultWeekKey(items = [], { today = new Date() } = {}) {
  const currentKey = startOfWeekKey(today);

  let earliest = null;
  for (const item of items) {
    const keys = singaporeDayKeysCovered(item.startsAt, item.endsAt);
    if (!keys.length) continue;
    for (const key of [keys[0], keys[keys.length - 1]]) {
      const weekKey = startOfWeekKey(key);
      if (weekKey === currentKey) return currentKey;
      if (weekKey > currentKey && (earliest === null || weekKey < earliest)) earliest = weekKey;
    }
  }

  // An item spanning the current week without starting or ending in it still
  // belongs to it.
  for (const item of items) {
    const keys = singaporeDayKeysCovered(item.startsAt, item.endsAt);
    if (keys.some((key) => startOfWeekKey(key) === currentKey)) return currentKey;
  }

  return earliest ?? currentKey;
}

/** As `canGoPrev`, for the week view: the payload holds nothing earlier. */
export function canGoPrevWeek(anchorKey, { today = new Date() } = {}) {
  return startOfWeekKey(anchorKey) > startOfWeekKey(today);
}

export function singaporeMonthOf(value) {
  const [year, month] = singaporeDayKey(value).split("-");
  return { year: Number(year), month: Number(month) - 1 };
}

function monthOrdinal({ year, month }) {
  return year * 12 + month;
}

export function sameMonth(a, b) {
  return a.year === b.year && a.month === b.month;
}

/** Move a month by `delta`, rolling the year in both directions. */
export function shiftMonth({ year, month }, delta) {
  const ordinal = monthOrdinal({ year, month }) + delta;
  return { year: Math.floor(ordinal / 12), month: ((ordinal % 12) + 12) % 12 };
}

/**
 * Which month to open on.
 *
 * The current month if it carries anything, otherwise the earliest later month
 * that does, otherwise the current month. Opening on an empty September while
 * every block sits in October would look like a dashboard with nothing on it,
 * but jumping the user forward silently would be just as bad — so the panel
 * also says which month it chose and why.
 */
export function defaultMonth(items = [], { today = new Date() } = {}) {
  const current = singaporeMonthOf(today);
  const currentOrdinal = monthOrdinal(current);

  let earliest = null;
  for (const item of items) {
    const keys = singaporeDayKeysCovered(item.startsAt, item.endsAt);
    if (!keys.length) continue;
    // An item already in progress counts towards the current month even though
    // it started earlier, so use the later of its start and today.
    for (const key of [keys[0], keys[keys.length - 1]]) {
      const month = singaporeMonthOf(startOfSingaporeDayUtc(key));
      const ordinal = monthOrdinal(month);
      if (ordinal === currentOrdinal) return current;
      if (ordinal > currentOrdinal && (earliest === null || ordinal < earliest)) earliest = ordinal;
    }
  }

  if (earliest === null) return current;
  return { year: Math.floor(earliest / 12), month: ((earliest % 12) + 12) % 12 };
}

/**
 * Whether the calendar may page back from `shown`.
 *
 * The dashboard payload only carries what is still upcoming, so every month
 * before the current one is guaranteed to be empty. Offering them would render
 * an empty grid that looks like an answer but is really a gap in the data.
 */
export function canGoPrev(shown, { today = new Date() } = {}) {
  return monthOrdinal(shown) > monthOrdinal(singaporeMonthOf(today));
}

/**
 * The first and last Singapore day an item occupies.
 *
 * Same `endsAt − 1ms` rule as `singaporeDayKeysCovered`, without walking the
 * days in between — a block running for a year only needs its two ends.
 */
export function itemDayRange(item) {
  const start = toInstant(item.startsAt);
  const end = toInstant(item.endsAt);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start) return null;
  return { firstKey: singaporeDayKey(start), lastKey: singaporeDayKey(new Date(end.getTime() - 1)) };
}

/**
 * Lay one week's items out as horizontal bars.
 *
 * A booking or block occupies a continuous run of days, so it is drawn as one
 * bar spanning those columns rather than repeated in each cell — a fortnight's
 * renovation should read as one thing, not as fourteen identical chips.
 *
 * Bars are packed into lanes: each takes the first lane where nothing already
 * overlaps its columns, which is the standard greedy interval-graph colouring
 * and uses the fewest lanes possible for the row. Items are placed in the
 * cells' existing order (kind severity, then start time), so the most serious
 * thing in a week sits on the top lane.
 *
 * `maxLanes` caps how many are drawn. Anything beyond it is reported per day
 * in `overflow`, so a cell can say "+2" rather than silently dropping items.
 */
export function layoutWeekSegments(cells, { maxLanes = Infinity } = {}) {
  const firstIndexOf = new Map();
  const lastIndexOf = new Map();
  const itemOf = new Map();
  const order = [];

  cells.forEach((cell, index) => {
    for (const item of cell.items) {
      const id = `${item.kind}-${item.id}`;
      if (!firstIndexOf.has(id)) {
        firstIndexOf.set(id, index);
        itemOf.set(id, item);
        order.push(id);
      }
      lastIndexOf.set(id, index);
    }
  });

  // `lanes[n]` is the last column lane n is occupied up to, so a candidate
  // fits when its start clears that.
  const lanes = [];
  const segments = order.map((id) => {
    const startIndex = firstIndexOf.get(id);
    const endIndex = lastIndexOf.get(id);
    let lane = lanes.findIndex((until) => until < startIndex);
    if (lane === -1) lane = lanes.push(-1) - 1;
    lanes[lane] = endIndex;

    const item = itemOf.get(id);
    const range = itemDayRange(item);
    return {
      id,
      item,
      startIndex,
      span: endIndex - startIndex + 1,
      lane,
      // Drawn as a flat edge rather than a bar end, so a run that carries on
      // into the next week does not look like it stops on Sunday.
      continuesBefore: range ? range.firstKey < cells[0].key : false,
      continuesAfter: range ? range.lastKey > cells[cells.length - 1].key : false,
    };
  });

  const visible = segments.filter((segment) => segment.lane < maxLanes);
  const hidden = segments.filter((segment) => segment.lane >= maxLanes);

  const overflow = cells.map((_, index) =>
    hidden.filter((segment) => index >= segment.startIndex && index < segment.startIndex + segment.span).length,
  );

  return {
    segments: visible,
    laneCount: Math.min(lanes.length, maxLanes),
    overflow,
    hiddenCount: hidden.length,
  };
}

/** Split a grid's cells into weeks, each laid out as bars. */
export function toWeekRows(grid, { maxLanes = Infinity } = {}) {
  const rows = [];
  for (let i = 0; i < grid.cells.length; i += 7) {
    const cells = grid.cells.slice(i, i + 7);
    rows.push({ key: cells[0].key, cells, ...layoutWeekSegments(cells, { maxLanes }) });
  }
  return rows;
}
