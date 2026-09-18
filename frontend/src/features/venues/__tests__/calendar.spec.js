import { describe, expect, it } from "vitest";

import {
  buildMonthGrid,
  buildWeekGrid,
  canGoPrev,
  canGoPrevWeek,
  defaultMonth,
  defaultWeekKey,
  shiftMonth,
  shiftWeekKey,
  layoutWeekSegments,
  singaporeDayKeysCovered,
  startOfWeekKey,
  toCalendarItems,
  toWeekRows,
} from "@/features/venues/calendar";
import { singaporeDayKey } from "@/features/venues/singaporeTime";

// 2026-09-19 12:00 SGT. The seeded blocks and bookings all sit in October, so
// "today" is deliberately in a month with nothing in it.
const TODAY = new Date("2026-09-19T12:00:00+08:00");

const block = (id, startsAt, endsAt, overrides = {}) => ({
  kind: "block",
  id,
  venueId: "b-1",
  venueName: "Heritage Hall",
  startsAt,
  endsAt,
  detail: "renovation",
  ...overrides,
});

describe("singaporeDayKey", () => {
  it("reads the Singapore date, not the UTC one", () => {
    // 16:00Z is already the next day in Singapore.
    expect(singaporeDayKey(new Date("2026-10-09T16:00:00Z"))).toBe("2026-10-10");
  });

  it("gives the same answer however the instant was serialised", () => {
    const asUtc = singaporeDayKey(new Date("2026-10-10T16:00:00Z"));
    const asSgt = singaporeDayKey(new Date("2026-10-11T00:00:00+08:00"));
    expect(asUtc).toBe(asSgt);
  });
});

describe("singaporeDayKeysCovered", () => {
  it("stops before a day the range ends on at midnight", () => {
    // Seeded block: 20–22 Oct. The 22nd is not blocked — the range is
    // half-open, so nothing inside it falls on that day (§6.14, CAL-R2).
    expect(
      singaporeDayKeysCovered("2026-10-20T00:00:00+08:00", "2026-10-22T00:00:00+08:00"),
    ).toEqual(["2026-10-20", "2026-10-21"]);
  });

  it("applies the same rule across a fortnight", () => {
    // Seeded block: 1–15 Oct, so Heritage Hall is free again on the 15th.
    const keys = singaporeDayKeysCovered("2026-10-01T00:00:00+08:00", "2026-10-15T00:00:00+08:00");
    expect(keys).toHaveLength(14);
    expect(keys[0]).toBe("2026-10-01");
    expect(keys.at(-1)).toBe("2026-10-14");
    expect(keys).not.toContain("2026-10-15");
  });

  it("does include the end day when the range reaches even one millisecond into it", () => {
    // Guards the -1ms rule against over-trimming: only an exact midnight end
    // should drop the day.
    expect(
      singaporeDayKeysCovered("2026-10-20T00:00:00+08:00", "2026-10-22T00:00:00.001+08:00"),
    ).toContain("2026-10-22");
  });

  it("keeps a few hours inside one day to one day", () => {
    // Seeded block: air-con servicing, 08:00–12:00 on 10 Oct.
    expect(
      singaporeDayKeysCovered("2026-10-10T08:00:00+08:00", "2026-10-10T12:00:00+08:00"),
    ).toEqual(["2026-10-10"]);
  });

  it("does not split a range that crosses UTC midnight but not Singapore midnight", () => {
    // 20:00–23:00 SGT is 12:00–15:00Z, but a naive UTC reading of the evening
    // hours either side of it would land on two different days.
    expect(
      singaporeDayKeysCovered("2026-10-10T20:00:00+08:00", "2026-10-10T23:00:00+08:00"),
    ).toEqual(["2026-10-10"]);
  });

  it("splits a range that crosses Singapore midnight", () => {
    expect(
      singaporeDayKeysCovered("2026-10-10T23:00:00+08:00", "2026-10-11T01:00:00+08:00"),
    ).toEqual(["2026-10-10", "2026-10-11"]);
  });

  it("clips to the window it is given", () => {
    const keys = singaporeDayKeysCovered("2026-09-29T00:00:00+08:00", "2026-10-03T00:00:00+08:00", {
      fromKey: "2026-10-01",
      toKey: "2026-10-31",
    });
    expect(keys).toEqual(["2026-10-01", "2026-10-02"]);
  });

  it("stays cheap for a range far longer than the window", () => {
    const keys = singaporeDayKeysCovered("2020-01-01T00:00:00+08:00", "2030-01-01T00:00:00+08:00", {
      fromKey: "2026-10-01",
      toKey: "2026-10-31",
    });
    expect(keys).toHaveLength(31);
  });

  it("returns nothing for a range that cannot be ordered", () => {
    expect(singaporeDayKeysCovered("2026-10-10T12:00:00+08:00", "2026-10-10T12:00:00+08:00")).toEqual([]);
    expect(singaporeDayKeysCovered("not a date", "2026-10-10T12:00:00+08:00")).toEqual([]);
  });
});

describe("buildMonthGrid", () => {
  it("lays October 2026 out as five Monday-first weeks", () => {
    // 1 Oct 2026 is a Thursday, so three leading cells and one trailing.
    const grid = buildMonthGrid(2026, 9, [], { today: TODAY });
    expect(grid.cells).toHaveLength(35);
    expect(grid.cells[0].key).toBe("2026-09-28");
    expect(grid.cells[0].inCurrentMonth).toBe(false);
    expect(grid.cells[3].key).toBe("2026-10-01");
    expect(grid.cells[3].inCurrentMonth).toBe(true);
    expect(grid.cells.at(-1).key).toBe("2026-11-01");
    expect(grid.cells.at(-1).inCurrentMonth).toBe(false);
  });

  it("pads to a fixed row count when asked, so the panel does not resize between months", () => {
    // February 2027 needs 4 rows and October 2026 needs 5; both must render 6.
    for (const [year, month] of [
      [2027, 1],
      [2026, 9],
      [2026, 4],
    ]) {
      expect(buildMonthGrid(year, month, [], { today: TODAY, weeks: 6 }).cells).toHaveLength(42);
    }
  });

  it("never truncates a month that needs more rows than it was asked for", () => {
    const grid = buildMonthGrid(2026, 9, [], { today: TODAY, weeks: 1 });
    const inMonth = grid.cells.filter((cell) => cell.inCurrentMonth);
    expect(inMonth).toHaveLength(31);
  });

  it("keeps placing items correctly in the padded rows", () => {
    // 1 Nov falls in October's sixth row once padded; a block there must show.
    const grid = buildMonthGrid(2026, 9, [block("c-1", "2026-11-01T00:00:00+08:00", "2026-11-02T00:00:00+08:00")], {
      today: TODAY,
      weeks: 6,
    });
    expect(grid.cells.find((c) => c.key === "2026-11-01").hasItems).toBe(true);
  });

  it("has no leading cells when the month starts on a Monday", () => {
    // 1 Jun 2026 is a Monday.
    const grid = buildMonthGrid(2026, 5, [], { today: TODAY });
    expect(grid.cells[0].key).toBe("2026-06-01");
  });

  it("handles a leap February", () => {
    const grid = buildMonthGrid(2028, 1, [], { today: TODAY });
    const inMonth = grid.cells.filter((cell) => cell.inCurrentMonth);
    expect(inMonth).toHaveLength(29);
    expect(inMonth.at(-1).key).toBe("2028-02-29");
  });

  it("marks the days an item covers and no others", () => {
    const grid = buildMonthGrid(2026, 9, [block("c-3", "2026-10-20T00:00:00+08:00", "2026-10-22T00:00:00+08:00")], {
      today: TODAY,
    });
    const marked = grid.cells.filter((cell) => cell.hasItems).map((cell) => cell.key);
    expect(marked).toEqual(["2026-10-20", "2026-10-21"]);
  });

  it("marks an item that straddles a month boundary in both months", () => {
    const straddling = block("c-9", "2026-09-29T00:00:00+08:00", "2026-10-03T00:00:00+08:00");

    const september = buildMonthGrid(2026, 8, [straddling], { today: TODAY });
    const october = buildMonthGrid(2026, 9, [straddling], { today: TODAY });

    expect(september.cells.find((c) => c.key === "2026-09-30").hasItems).toBe(true);
    // Also visible in October's leading cells, so the block reads continuously
    // rather than appearing to stop at the edge of the grid.
    expect(october.cells.find((c) => c.key === "2026-09-30").hasItems).toBe(true);
    expect(october.cells.find((c) => c.key === "2026-10-02").hasItems).toBe(true);
  });

  it("counts each kind on a day and orders the tones by severity", () => {
    const grid = buildMonthGrid(
      2026,
      9,
      [
        { kind: "held", id: "d-1", startsAt: "2026-10-10T13:00:00+08:00", endsAt: "2026-10-10T16:00:00+08:00" },
        block("c-2", "2026-10-10T08:00:00+08:00", "2026-10-10T12:00:00+08:00"),
      ],
      { today: TODAY },
    );

    const cell = grid.cells.find((c) => c.key === "2026-10-10");
    expect(cell.markers).toEqual({ block: 1, held: 1 });
    expect(cell.tones).toEqual(["red", "yellow"]);
    expect(cell.items[0].kind).toBe("block");
  });

  it("flags today", () => {
    const grid = buildMonthGrid(2026, 8, [], { today: TODAY });
    expect(grid.cells.filter((cell) => cell.isToday).map((cell) => cell.key)).toEqual(["2026-09-19"]);
  });
});

describe("toCalendarItems", () => {
  it("flattens the payload and tags each item with its kind", () => {
    const items = toCalendarItems({
      blocks: [
        {
          id: "c-1",
          venue_id: "b-7",
          venue_name: "Heritage Hall",
          period: { starts_at: "2026-10-01T00:00:00+08:00", ends_at: "2026-10-15T00:00:00+08:00" },
          reason: "renovation",
          notes: "Floor restoration.",
        },
      ],
      pendingHolds: [
        {
          id: "d-2",
          venue_id: "b-3",
          venue_name: "Seminar Room 1",
          period: { starts_at: "2026-10-10T13:00:00+08:00", ends_at: "2026-10-10T16:00:00+08:00" },
          event_id: "e-102",
          event_name: null,
        },
      ],
      reReviewBookings: [
        {
          id: "d-5",
          venue_id: "b-4",
          venue_name: "Boardroom Orchid",
          period: { starts_at: "2026-10-12T09:00:00+08:00", ends_at: "2026-10-12T12:00:00+08:00" },
          event_id: "e-105",
          event_name: null,
        },
      ],
    });

    expect(items.map((item) => item.kind)).toEqual(["block", "held", "re_review"]);
    expect(items[0].notes).toBe("Floor restoration.");
    expect(items[1].venueName).toBe("Seminar Room 1");
    expect(items[2].startsAt).toBe("2026-10-12T09:00:00+08:00");
  });

  it("copes with an empty payload", () => {
    expect(toCalendarItems()).toEqual([]);
  });
});

describe("month navigation", () => {
  it("rolls the year in both directions", () => {
    expect(shiftMonth({ year: 2026, month: 11 }, 1)).toEqual({ year: 2027, month: 0 });
    expect(shiftMonth({ year: 2026, month: 0 }, -1)).toEqual({ year: 2025, month: 11 });
  });

  it("will not page back past the current month, because the payload is upcoming-only", () => {
    expect(canGoPrev({ year: 2026, month: 8 }, { today: TODAY })).toBe(false);
    expect(canGoPrev({ year: 2026, month: 9 }, { today: TODAY })).toBe(true);
  });
});

describe("defaultMonth", () => {
  it("opens on the current month when it carries something", () => {
    const items = [block("c-1", "2026-09-20T00:00:00+08:00", "2026-09-21T00:00:00+08:00")];
    expect(defaultMonth(items, { today: TODAY })).toEqual({ year: 2026, month: 8 });
  });

  it("opens on the earliest later month when the current one is empty", () => {
    // The seeded state: nothing in September, everything in October.
    const items = [
      block("c-1", "2026-11-02T00:00:00+08:00", "2026-11-03T00:00:00+08:00"),
      block("c-2", "2026-10-20T00:00:00+08:00", "2026-10-22T00:00:00+08:00"),
    ];
    expect(defaultMonth(items, { today: TODAY })).toEqual({ year: 2026, month: 9 });
  });

  it("counts an item already in progress towards the current month", () => {
    const items = [block("c-1", "2026-09-01T00:00:00+08:00", "2026-10-15T00:00:00+08:00")];
    expect(defaultMonth(items, { today: TODAY })).toEqual({ year: 2026, month: 8 });
  });

  it("falls back to the current month when there is nothing at all", () => {
    expect(defaultMonth([], { today: TODAY })).toEqual({ year: 2026, month: 8 });
  });
});

describe("week view", () => {
  it("anchors a week on its Monday, whichever day it is given", () => {
    // 10 Oct 2026 is a Saturday; its week starts Monday the 5th.
    expect(startOfWeekKey("2026-10-10")).toBe("2026-10-05");
    expect(startOfWeekKey("2026-10-05")).toBe("2026-10-05");
    expect(startOfWeekKey("2026-10-11")).toBe("2026-10-05");
    // Sunday belongs to the week that began the previous Monday.
    expect(startOfWeekKey("2026-10-04")).toBe("2026-09-28");
  });

  it("accepts an instant as well as a day key, reading it in Singapore time", () => {
    expect(startOfWeekKey(new Date("2026-10-09T16:00:00Z"))).toBe("2026-10-05");
  });

  it("builds seven Monday-first cells", () => {
    const grid = buildWeekGrid("2026-10-08", [], { today: TODAY });
    expect(grid.startKey).toBe("2026-10-05");
    expect(grid.endKey).toBe("2026-10-11");
    expect(grid.cells.map((c) => c.key)).toEqual([
      "2026-10-05",
      "2026-10-06",
      "2026-10-07",
      "2026-10-08",
      "2026-10-09",
      "2026-10-10",
      "2026-10-11",
    ]);
  });

  it("places items on the right days, with the same half-open rule as the month grid", () => {
    // 20-22 Oct covers the 20th and 21st, not the 22nd.
    const grid = buildWeekGrid("2026-10-20", [block("c-3", "2026-10-20T00:00:00+08:00", "2026-10-22T00:00:00+08:00")], {
      today: TODAY,
    });
    const marked = grid.cells.filter((c) => c.hasItems).map((c) => c.key);
    expect(marked).toEqual(["2026-10-20", "2026-10-21"]);
  });

  it("crosses a month boundary within one week", () => {
    const grid = buildWeekGrid("2026-10-01", [], { today: TODAY });
    expect(grid.cells.map((c) => c.key)).toContain("2026-09-28");
    expect(grid.cells.map((c) => c.key)).toContain("2026-10-04");
    // Nothing is greyed out in a week view: every day shown is in view.
    expect(grid.cells.every((c) => c.inCurrentMonth)).toBe(true);
  });

  it("flags today", () => {
    const grid = buildWeekGrid("2026-09-19", [], { today: TODAY });
    expect(grid.cells.filter((c) => c.isToday).map((c) => c.key)).toEqual(["2026-09-19"]);
  });

  it("steps by whole weeks and rolls across months and years", () => {
    expect(shiftWeekKey("2026-10-05", 1)).toBe("2026-10-12");
    expect(shiftWeekKey("2026-10-05", -1)).toBe("2026-09-28");
    expect(shiftWeekKey("2026-12-28", 1)).toBe("2027-01-04");
  });

  it("will not page back before the current week", () => {
    expect(canGoPrevWeek("2026-09-14", { today: TODAY })).toBe(false);
    expect(canGoPrevWeek("2026-09-21", { today: TODAY })).toBe(true);
  });

  it("opens on the current week when it carries something", () => {
    const items = [block("c-1", "2026-09-17T00:00:00+08:00", "2026-09-18T00:00:00+08:00")];
    expect(defaultWeekKey(items, { today: TODAY })).toBe("2026-09-14");
  });

  it("opens on the earliest later week when the current one is empty", () => {
    const items = [
      block("c-1", "2026-11-02T00:00:00+08:00", "2026-11-03T00:00:00+08:00"),
      block("c-2", "2026-10-20T00:00:00+08:00", "2026-10-22T00:00:00+08:00"),
    ];
    expect(defaultWeekKey(items, { today: TODAY })).toBe("2026-10-19");
  });

  it("counts a long item that merely spans the current week", () => {
    // Starts before and ends after, so neither end lands in this week.
    const items = [block("c-1", "2026-09-01T00:00:00+08:00", "2026-10-15T00:00:00+08:00")];
    expect(defaultWeekKey(items, { today: TODAY })).toBe("2026-09-14");
  });

  it("falls back to the current week when there is nothing at all", () => {
    expect(defaultWeekKey([], { today: TODAY })).toBe("2026-09-14");
  });
});

describe("laying a week out as bars", () => {
  // Monday 5 Oct to Sunday 11 Oct 2026.
  const week = (items) => buildWeekGrid("2026-10-05", items, { today: TODAY }).cells;

  it("draws a multi-day item as one bar spanning its days", () => {
    // A fortnight's renovation should read as one thing, not fourteen chips.
    const { segments } = layoutWeekSegments(week([block("c-1", "2026-10-06T00:00:00+08:00", "2026-10-09T00:00:00+08:00")]));

    expect(segments).toHaveLength(1);
    expect(segments[0]).toMatchObject({ startIndex: 1, span: 3, lane: 0 });
  });

  it("clips a bar to the week and flags that it carries on", () => {
    const { segments } = layoutWeekSegments(week([block("c-1", "2026-10-01T00:00:00+08:00", "2026-10-15T00:00:00+08:00")]));

    expect(segments[0]).toMatchObject({
      startIndex: 0,
      span: 7,
      continuesBefore: true,
      continuesAfter: true,
    });
  });

  it("does not flag continuation for an item that starts and ends inside the week", () => {
    const { segments } = layoutWeekSegments(week([block("c-1", "2026-10-06T09:00:00+08:00", "2026-10-06T12:00:00+08:00")]));
    expect(segments[0]).toMatchObject({ continuesBefore: false, continuesAfter: false, span: 1 });
  });

  it("stacks overlapping items into separate lanes", () => {
    const { segments, laneCount } = layoutWeekSegments(
      week([
        block("c-1", "2026-10-05T00:00:00+08:00", "2026-10-08T00:00:00+08:00"),
        block("c-2", "2026-10-06T00:00:00+08:00", "2026-10-10T00:00:00+08:00"),
      ]),
    );

    expect(segments.map((s) => s.lane)).toEqual([0, 1]);
    expect(laneCount).toBe(2);
  });

  it("reuses a lane once it is free again", () => {
    // Mon-Tue then Fri-Sat: no overlap, so both sit on the top lane.
    const { segments, laneCount } = layoutWeekSegments(
      week([
        block("c-1", "2026-10-05T00:00:00+08:00", "2026-10-07T00:00:00+08:00"),
        block("c-2", "2026-10-09T00:00:00+08:00", "2026-10-11T00:00:00+08:00"),
      ]),
    );

    expect(segments.map((s) => s.lane)).toEqual([0, 0]);
    expect(laneCount).toBe(1);
  });

  it("puts the more serious kind on the top lane", () => {
    // A block outranks a hold, whichever order they arrive in.
    const cells = week([
      { kind: "held", id: "d-1", startsAt: "2026-10-06T09:00:00+08:00", endsAt: "2026-10-06T12:00:00+08:00" },
      block("c-1", "2026-10-06T00:00:00+08:00", "2026-10-07T00:00:00+08:00"),
    ]);
    const { segments } = layoutWeekSegments(cells);

    expect(segments.find((s) => s.lane === 0).item.kind).toBe("block");
  });

  it("counts what it had to hide, per day, rather than dropping it", () => {
    const { segments, overflow, hiddenCount } = layoutWeekSegments(
      week([
        block("c-1", "2026-10-06T00:00:00+08:00", "2026-10-07T00:00:00+08:00"),
        block("c-2", "2026-10-06T00:00:00+08:00", "2026-10-07T00:00:00+08:00"),
        block("c-3", "2026-10-06T00:00:00+08:00", "2026-10-07T00:00:00+08:00"),
      ]),
      { maxLanes: 2 },
    );

    expect(segments).toHaveLength(2);
    expect(hiddenCount).toBe(1);
    // Tuesday the 6th only; all three end before Wednesday.
    expect(overflow).toEqual([0, 1, 0, 0, 0, 0, 0]);
  });

  it("splits a month grid into one laid-out row per week", () => {
    const grid = buildMonthGrid(2026, 9, [block("c-1", "2026-10-20T00:00:00+08:00", "2026-10-22T00:00:00+08:00")], {
      today: TODAY,
      weeks: 6,
    });
    const rows = toWeekRows(grid, { maxLanes: 2 });

    expect(rows).toHaveLength(6);
    expect(rows.every((row) => row.cells.length === 7)).toBe(true);
    // 20 Oct is a Tuesday; the bar covers Tuesday and Wednesday.
    const withBar = rows.filter((row) => row.segments.length);
    expect(withBar).toHaveLength(1);
    expect(withBar[0].segments[0]).toMatchObject({ startIndex: 1, span: 2 });
  });

  it("carries one item across two week rows as two bars", () => {
    const grid = buildMonthGrid(2026, 9, [block("c-1", "2026-10-01T00:00:00+08:00", "2026-10-15T00:00:00+08:00")], {
      today: TODAY,
      weeks: 6,
    });
    const rows = toWeekRows(grid, { maxLanes: 3 });
    const bars = rows.flatMap((row) => row.segments);

    // 1-14 Oct spans parts of three calendar weeks.
    expect(bars).toHaveLength(3);
    expect(bars[0].continuesAfter).toBe(true);
    expect(bars.at(-1).continuesBefore).toBe(true);
    expect(bars.at(-1).continuesAfter).toBe(false);
  });
});
