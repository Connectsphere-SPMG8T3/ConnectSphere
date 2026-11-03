import { describe, expect, it } from "vitest";

import {
  ENTRY_TYPES,
  bandLayout,
  entryBadge,
  holdExpiry,
  bookingBands,
  entryDetails,
  entryTypeMeta,
  formatWindow,
  layoutDay,
  periodLabel,
  shiftAnchor,
  toCalendarEntries,
  viewDayKeys,
  viewRange,
} from "@/features/venues/availabilityCalendar";
import { formatVenueInstant } from "@/features/venues/venueProfile";

// SCRUM-57: a venue's availability calendar for Venue Staff.

const NOW = new Date("2031-03-10T02:00:00Z"); // Mon 10 Mar 2031, 10:00 SGT

function booking(overrides = {}) {
  return {
    id: "d1",
    kind: "booking",
    type: "confirmed",
    status: "approved",
    event_id: "e1",
    event_name: "Gala",
    // 10:00–12:00 SGT, occupying 09:30–12:45 SGT.
    period: { starts_at: "2031-03-11T02:00:00Z", ends_at: "2031-03-11T04:00:00Z" },
    occupied_period: { starts_at: "2031-03-11T01:30:00Z", ends_at: "2031-03-11T04:45:00Z" },
    setup_minutes: 30,
    turnaround_minutes: 45,
    expires_at: null,
    flag: null,
    flag_reason: null,
    reason: null,
    notes: null,
    created_by: null,
    created_at: null,
    ...overrides,
  };
}

function block(overrides = {}) {
  const period = { starts_at: "2031-03-11T00:00:00Z", ends_at: "2031-03-11T06:00:00Z" };
  return {
    ...booking(),
    id: "b1",
    kind: "block",
    type: "blocked",
    status: null,
    event_id: null,
    event_name: null,
    period,
    occupied_period: period,
    setup_minutes: 0,
    turnaround_minutes: 0,
    reason: "maintenance",
    notes: "Aircon",
    created_by: { id: "a1", full_name: "Vera Staff" },
    created_at: "2031-03-01T01:00:00Z",
    ...overrides,
  };
}

describe("ENTRY_TYPES (AC2, AC8)", () => {
  it("names the five types, each with its own label and pattern, not colour alone", () => {
    expect(ENTRY_TYPES.map((type) => type.key)).toEqual(["confirmed", "tentative", "affected", "re_review", "blocked"]);
    expect(ENTRY_TYPES.map((type) => type.label)).toEqual([
      "Confirmed",
      "Tentative",
      "Affected",
      "Re-review",
      "Blocked",
    ]);
    const patterns = ENTRY_TYPES.map((type) => type.pattern);
    expect(new Set(patterns).size).toBe(ENTRY_TYPES.length);
  });

  it("falls back for a type the SPA doesn't know", () => {
    expect(entryTypeMeta("mystery")).toMatchObject({ key: "mystery", label: "mystery" });
  });
});

describe("toCalendarEntries (AC3, AC6)", () => {
  it("places each entry by its occupied window and keeps its booked time", () => {
    const [entry] = toCalendarEntries([booking()], NOW);
    expect(entry).toMatchObject({
      id: "d1",
      kind: "confirmed",
      source: "booking",
      startsAt: "2031-03-11T01:30:00Z",
      endsAt: "2031-03-11T04:45:00Z",
      bookedStartsAt: "2031-03-11T02:00:00Z",
      bookedEndsAt: "2031-03-11T04:00:00Z",
      label: "Gala",
    });
  });

  it("labels a block with its reason, and an unnamed event as such", () => {
    const entries = toCalendarEntries([block(), booking({ event_name: null })], NOW);
    expect(entries.map((entry) => entry.label)).toEqual(["Maintenance", "Unnamed event"]);
  });

  it("drops a hold whose expiry has passed while the page was open", () => {
    const entries = toCalendarEntries(
      [
        booking({ id: "gone", type: "tentative", status: "held", expires_at: "2031-03-10T02:00:00Z" }),
        booking({ id: "kept", type: "tentative", status: "held", expires_at: "2031-03-10T02:00:01Z" }),
        booking({ id: "affected-hold", type: "affected", status: "held", expires_at: "2031-03-10T01:00:00Z" }),
      ],
      NOW,
    );
    expect(entries.map((entry) => entry.id)).toEqual(["kept"]);
  });

  it("keeps an approved Affected booking, which occupies the venue until restored or released", () => {
    expect(toCalendarEntries([booking({ type: "affected", flag: "affected" })], NOW)).toHaveLength(1);
  });

  it("is empty without entries", () => {
    expect(toCalendarEntries(undefined, NOW)).toEqual([]);
  });
});

describe("bookingBands (AC5)", () => {
  it("splits a booking into setup, event and turnaround", () => {
    const [entry] = toCalendarEntries([booking()], NOW);
    expect(bookingBands(entry)).toEqual([
      { part: "setup", label: "Setup", startsAt: "2031-03-11T01:30:00Z", endsAt: "2031-03-11T02:00:00Z" },
      { part: "event", label: "Event", startsAt: "2031-03-11T02:00:00Z", endsAt: "2031-03-11T04:00:00Z" },
      { part: "turnaround", label: "Turnaround", startsAt: "2031-03-11T04:00:00Z", endsAt: "2031-03-11T04:45:00Z" },
    ]);
  });

  it("leaves out a buffer of zero minutes", () => {
    const [entry] = toCalendarEntries(
      [
        booking({
          setup_minutes: 0,
          occupied_period: { starts_at: "2031-03-11T02:00:00Z", ends_at: "2031-03-11T04:45:00Z" },
        }),
      ],
      NOW,
    );
    expect(bookingBands(entry).map((band) => band.part)).toEqual(["event", "turnaround"]);
  });

  it("gives a block a single band with no buffer", () => {
    const [entry] = toCalendarEntries([block()], NOW);
    expect(bookingBands(entry)).toEqual([
      { part: "event", label: "Blocked", startsAt: "2031-03-11T00:00:00Z", endsAt: "2031-03-11T06:00:00Z" },
    ]);
  });
});

describe("views (AC1)", () => {
  it("a day view covers one Singapore day", () => {
    expect(viewDayKeys("day", "2031-03-12")).toEqual(["2031-03-12"]);
    const range = viewRange("day", "2031-03-12");
    expect(range.startsAt.toISOString()).toBe("2031-03-11T16:00:00.000Z");
    expect(range.endsAt.toISOString()).toBe("2031-03-12T16:00:00.000Z");
  });

  it("a week view covers Monday to Sunday around the anchor", () => {
    expect(viewDayKeys("week", "2031-03-12")).toEqual([
      "2031-03-10",
      "2031-03-11",
      "2031-03-12",
      "2031-03-13",
      "2031-03-14",
      "2031-03-15",
      "2031-03-16",
    ]);
    const range = viewRange("week", "2031-03-12");
    expect(range.startsAt.toISOString()).toBe("2031-03-09T16:00:00.000Z");
    expect(range.endsAt.toISOString()).toBe("2031-03-16T16:00:00.000Z");
  });

  it("a month view covers its six-week grid, at most 42 days", () => {
    const keys = viewDayKeys("month", "2031-03-12");
    expect(keys).toHaveLength(42);
    expect(keys[0]).toBe("2031-02-24");
    const range = viewRange("month", "2031-03-12");
    expect((range.endsAt - range.startsAt) / 86_400_000).toBe(42);
  });

  it("steps by a day, a week or a month, landing a month on its first day", () => {
    expect(shiftAnchor("day", "2031-03-31", 1)).toBe("2031-04-01");
    expect(shiftAnchor("week", "2031-03-12", -1)).toBe("2031-03-03");
    expect(shiftAnchor("month", "2031-01-31", 1)).toBe("2031-02-01");
    expect(shiftAnchor("month", "2031-01-15", -1)).toBe("2030-12-01");
  });

  it("names the period shown", () => {
    expect(periodLabel("day", "2031-03-12")).toBe("Wednesday, 12 March 2031");
    expect(periodLabel("week", "2031-03-12")).toBe("10 Mar – 16 Mar 2031");
    expect(periodLabel("month", "2031-03-12")).toBe("March 2031");
  });
});

describe("layoutDay (AC5, AC7)", () => {
  it("places an entry by minutes from the start of the Singapore day", () => {
    const entries = toCalendarEntries([booking()], NOW);
    const [placed] = layoutDay("2031-03-11", entries);
    // 09:30 to 12:45 SGT.
    expect(placed.top).toBeCloseTo((9.5 * 60 * 100) / 1440);
    expect(placed.height).toBeCloseTo((3.25 * 60 * 100) / 1440);
    expect(placed).toMatchObject({ lane: 0, lanes: 1, continuesBefore: false, continuesAfter: false });
  });

  it("clips an entry running over midnight to the day shown", () => {
    const entries = toCalendarEntries(
      [block({ occupied_period: { starts_at: "2031-03-10T12:00:00Z", ends_at: "2031-03-11T18:00:00Z" } })],
      NOW,
    );
    const [placed] = layoutDay("2031-03-11", entries);
    expect(placed).toMatchObject({ top: 0, height: 100, continuesBefore: true, continuesAfter: true });
  });

  it("leaves out an entry that doesn't touch the day, including one ending at its midnight", () => {
    const entries = toCalendarEntries(
      [block({ occupied_period: { starts_at: "2031-03-10T10:00:00Z", ends_at: "2031-03-10T16:00:00Z" } })],
      NOW,
    );
    expect(layoutDay("2031-03-11", entries)).toEqual([]);
  });

  it("puts overlapping entries side by side and the rest full width", () => {
    const entries = toCalendarEntries(
      [
        block(),
        booking(),
        booking({
          id: "d2",
          occupied_period: { starts_at: "2031-03-11T08:00:00Z", ends_at: "2031-03-11T09:00:00Z" },
          period: { starts_at: "2031-03-11T08:00:00Z", ends_at: "2031-03-11T09:00:00Z" },
        }),
      ],
      NOW,
    );
    const placed = layoutDay("2031-03-11", entries);
    expect(placed.map((p) => [p.entry.id, p.lane, p.lanes])).toEqual([
      ["b1", 0, 2],
      ["d1", 1, 2],
      ["d2", 0, 1],
    ]);
  });
});

describe("formatWindow (AC10)", () => {
  it("shows a same-day window once, in Singapore time", () => {
    expect(formatWindow("2031-03-11T01:30:00Z", "2031-03-11T04:45:00Z")).toBe("Tue 11 Mar 2031, 09:30–12:45");
  });

  it("names both days when a window spans midnight", () => {
    expect(formatWindow("2031-03-10T12:00:00Z", "2031-03-11T18:00:00Z")).toBe(
      "Mon 10 Mar 2031, 20:00 – Wed 12 Mar 2031, 02:00",
    );
  });
});

describe("entryDetails (AC9)", () => {
  const rows = (entry) => Object.fromEntries(entryDetails(entry).map((row) => [row.label, row.value]));

  it("gives a booking's event, type, status, occupied window, own time and buffers", () => {
    const [entry] = toCalendarEntries([booking()], NOW);
    expect(rows(entry)).toEqual({
      Event: "Gala",
      Type: "Confirmed",
      Status: "Approved",
      "Occupied window": "Tue 11 Mar 2031, 09:30–12:45",
      "Event time": "Tue 11 Mar 2031, 10:00–12:00",
      "Setup and turnaround": "30 min before, 45 min after",
    });
  });

  it("adds a hold's expiry and an Affected booking's reason", () => {
    const [entry] = toCalendarEntries(
      [
        booking({
          type: "affected",
          status: "held",
          flag: "affected",
          flag_reason: "Venue unavailable: maintenance",
          expires_at: "2031-03-10T10:00:00Z",
        }),
      ],
      NOW,
    );
    expect(rows(entry)).toMatchObject({
      Type: "Affected",
      Status: "Pending hold",
      "Hold expires": "Mon 10 Mar 2031, 18:00",
      "Affected because": "Venue unavailable: maintenance",
    });
  });

  it("says when a booking has no setup or turnaround", () => {
    const [entry] = toCalendarEntries(
      [booking({ setup_minutes: 0, turnaround_minutes: 0, occupied_period: booking().period })],
      NOW,
    );
    expect(rows(entry)["Setup and turnaround"]).toBe("None");
  });

  it("gives a block's type, reason, notes, window and who set it", () => {
    const [entry] = toCalendarEntries([block()], NOW);
    expect(rows(entry)).toEqual({
      Type: "Blocked",
      Reason: "Maintenance",
      Details: "Aircon",
      "Occupied window": "Tue 11 Mar 2031, 08:00–14:00",
      "Set by": `Vera Staff · ${formatVenueInstant("2031-03-01T01:00:00Z")}`,
    });
  });

  it("names an unknown setter and leaves out absent notes", () => {
    const [entry] = toCalendarEntries([block({ notes: null, created_by: null, created_at: null })], NOW);
    expect(rows(entry)).toMatchObject({ "Set by": "Unknown user" });
    expect(rows(entry)).not.toHaveProperty("Details");
  });
});

describe("bandLayout (AC5)", () => {
  it("places each band within the entry's box on that day", () => {
    const [entry] = toCalendarEntries([booking()], NOW);
    const bands = bandLayout(entry, "2031-03-11");
    // 195 occupied minutes: 30 setup, 120 event, 45 turnaround.
    expect(bands.map((band) => band.part)).toEqual(["setup", "event", "turnaround"]);
    expect(bands[0].top).toBe(0);
    expect(bands[0].height).toBeCloseTo((30 / 195) * 100);
    expect(bands[1].top).toBeCloseTo((30 / 195) * 100);
    expect(bands[2].top + bands[2].height).toBeCloseTo(100);
    expect(bands.map((band) => band.minutes)).toEqual([30, 120, 45]);
  });

  it("leaves out a band on another day when a booking runs past midnight", () => {
    const [entry] = toCalendarEntries(
      [
        booking({
          // Event 23:00–01:00 SGT with an hour of setup before it.
          period: { starts_at: "2031-03-11T15:00:00Z", ends_at: "2031-03-11T17:00:00Z" },
          occupied_period: { starts_at: "2031-03-11T14:00:00Z", ends_at: "2031-03-11T17:00:00Z" },
          setup_minutes: 60,
          turnaround_minutes: 0,
        }),
      ],
      NOW,
    );
    expect(bandLayout(entry, "2031-03-11").map((band) => [band.part, Math.round(band.height)])).toEqual([
      ["setup", 50],
      ["event", 50],
    ]);
    expect(bandLayout(entry, "2031-03-12").map((band) => [band.part, band.top, band.height])).toEqual([
      ["event", 0, 100],
    ]);
  });
});

describe("entryBadge (AC2, AC6)", () => {
  it("names the type, and a tentative hold's expiry", () => {
    const entries = toCalendarEntries(
      [
        booking(),
        booking({ id: "h", type: "tentative", status: "held", expires_at: "2031-03-10T10:00:00Z" }),
        booking({ id: "h2", type: "tentative", status: "held", expires_at: null }),
        block(),
      ],
      NOW,
    );
    expect(entries.map(entryBadge)).toEqual([
      "Confirmed",
      "Tentative · expires Mon 10 Mar 2031, 18:00",
      "Tentative",
      "Blocked",
    ]);
    expect(entries.map(holdExpiry)).toEqual([null, "Expires Mon 10 Mar 2031, 18:00", null, null]);
  });
});
