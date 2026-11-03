import { describe, expect, it } from "vitest";

import {
  ALL_VENUE_STATUSES,
  bookingStatusColumns,
  PENDING_BOOKING_STATUS,
  blockReasonLabel,
  bookingStatusLabel,
  filterVenueStatuses,
  bookingStatusFilterOptions,
  expiryInputBounds,
  expiryInputToIso,
  formatEventReference,
  formatHoldExpiry,
  filterBookingRequests,
  sortPendingHoldsSoonestExpiryFirst,
  sortBookingRequests,
  summariseVenueStaffDashboard,
  venueStatusFilterOptions,
  venueStatuses,
  waitingDays,
} from "@/features/venues/dashboard";

const NOW = new Date("2026-09-19T12:00:00+08:00");

const venue = (id, name, overrides = {}) => ({ id, name, location: "Campus", is_active: true, ...overrides });

const blockOn = (venueId, startsAt, endsAt, overrides = {}) => ({
  id: `c-${venueId}-${startsAt}`,
  venue_id: venueId,
  period: { starts_at: startsAt, ends_at: endsAt },
  reason: "maintenance",
  ...overrides,
});

const hold = (id, requestedAt) => ({ id, requested_at: requestedAt, event_id: "e0000000-0000-4000-8000-000000000101" });

const expiring = (id, expiresAt) => ({ ...hold(id, "2026-09-01T09:00:00+08:00"), expires_at: expiresAt });

describe("sortPendingHoldsSoonestExpiryFirst (CR-99)", () => {
  it("puts the hold nearest to expiring first, whatever its age", () => {
    const sorted = sortPendingHoldsSoonestExpiryFirst([
      { ...hold("d-old", "2026-08-01T09:00:00+08:00"), expires_at: "2026-09-25T09:00:00+08:00" },
      { ...hold("d-new", "2026-09-18T09:00:00+08:00"), expires_at: "2026-09-20T09:00:00+08:00" },
      expiring("d-mid", "2026-09-22T09:00:00+08:00"),
    ]);
    expect(sorted.map((h) => h.id)).toEqual(["d-new", "d-mid", "d-old"]);
  });

  it("keeps a stable order for two holds expiring in the same instant", () => {
    const same = "2026-09-22T09:00:00+08:00";
    const sorted = sortPendingHoldsSoonestExpiryFirst([expiring("d-9", same), expiring("d-1", same)]);
    expect(sorted.map((h) => h.id)).toEqual(["d-1", "d-9"]);
  });

  it("does not mutate its input", () => {
    const input = [expiring("d-2", "2026-09-25T09:00:00+08:00"), expiring("d-4", "2026-09-20T09:00:00+08:00")];
    sortPendingHoldsSoonestExpiryFirst(input);
    expect(input.map((h) => h.id)).toEqual(["d-2", "d-4"]);
  });

  it("sorts a missing or unparseable expiry last rather than throwing", () => {
    const sorted = sortPendingHoldsSoonestExpiryFirst([
      expiring("d-bad", "nonsense"),
      hold("d-none", "2026-09-01T09:00:00+08:00"),
      expiring("d-ok", "2026-09-20T09:00:00+08:00"),
    ]);
    expect(sorted.map((h) => h.id)).toEqual(["d-ok", "d-bad", "d-none"]);
  });
});

describe("formatHoldExpiry (CR-99)", () => {
  it("reads the instant in Singapore time, as the notices do", () => {
    expect(formatHoldExpiry("2031-08-05T04:00:00Z")).toBe("5 Aug 2031, 12:00");
  });

  it("crosses midnight by Singapore's clock, not UTC's", () => {
    expect(formatHoldExpiry("2031-08-04T16:30:00Z")).toBe("5 Aug 2031, 00:30");
  });

  it("returns null when there is no usable expiry", () => {
    expect(formatHoldExpiry(null)).toBeNull();
    expect(formatHoldExpiry("nonsense")).toBeNull();
  });
});

describe("expiry input (CR-99 AC2)", () => {
  const pending = {
    ...expiring("d-1", "2026-09-22T09:00:00+08:00"),
    period: { starts_at: "2026-10-10T01:00:00Z", ends_at: "2026-10-10T04:00:00Z" },
  };

  it("bounds the picker from the next minute to the event start, in Singapore time", () => {
    expect(expiryInputBounds(pending, new Date("2026-09-19T04:00:30Z"))).toEqual({
      min: "2026-09-19T12:01",
      max: "2026-10-10T09:00",
      value: "2026-09-22T09:00",
    });
  });

  it("sends what was picked as a Singapore instant", () => {
    expect(expiryInputToIso("2026-09-25T18:30")).toBe("2026-09-25T18:30:00+08:00");
  });

  it("sends nothing for an empty or malformed pick", () => {
    expect(expiryInputToIso("")).toBeNull();
    expect(expiryInputToIso("2026-09-25")).toBeNull();
  });
});

describe("waitingDays", () => {
  it("counts whole days since the request", () => {
    expect(waitingDays(hold("d-1", "2026-09-03T10:30:00+08:00"), NOW)).toBe(16);
  });

  it("is zero, never negative, for a request dated in the future", () => {
    expect(waitingDays(hold("d-1", "2026-10-01T00:00:00+08:00"), NOW)).toBe(0);
  });

  it("is null when there is no usable timestamp", () => {
    expect(waitingDays({}, NOW)).toBeNull();
  });
});

describe("booking request history", () => {
  const requests = [
    { id: "d-1", status: "approved", venue_id: "b-1", period: { starts_at: "2026-10-20T01:00:00Z" }, requested_at: "2026-09-01T00:00:00Z" },
    { id: "d-2", status: "held", venue_id: "b-2", period: { starts_at: "2026-10-10T01:00:00Z" }, requested_at: "2026-09-10T00:00:00Z" },
    { id: "d-3", status: "rejected", venue_id: "b-1", period: { starts_at: "2026-10-15T01:00:00Z" }, requested_at: "2026-09-05T00:00:00Z" },
  ];

  it("filters by status and venue together", () => {
    expect(filterBookingRequests(requests, { status: "approved", venueId: "b-1" }).map((row) => row.id)).toEqual(["d-1"]);
  });

  it("returns select-compatible values for each status option", () => {
    expect(bookingStatusFilterOptions(requests).map((option) => option.value)).toEqual([
      "pending",
      "all",
      "approved",
      "rejected",
    ]);
  });

  it("treats held requests as the default pending view", () => {
    expect(filterBookingRequests([...requests, { id: "d-4", status: "re_review", venue_id: "b-1", period: {} }], { status: PENDING_BOOKING_STATUS }).map((row) => row.id)).toEqual(["d-2"]);
  });

  it("shows every request when the status select is set to Any", () => {
    expect(filterBookingRequests(requests, { status: "" }).map((row) => row.id)).toEqual(["d-1", "d-2", "d-3"]);
  });

  it("filters by an inclusive event date range", () => {
    expect(
      filterBookingRequests(requests, { startDate: "2026-10-15", endDate: "2026-10-15" }).map((row) => row.id),
    ).toEqual(["d-3"]);
  });

  it("sorts by event date and pending wait time", () => {
    expect(sortBookingRequests(requests, "event_soonest").map((row) => row.id)).toEqual(["d-2", "d-3", "d-1"]);
    expect(sortBookingRequests(requests, "waiting_longest", new Date("2026-09-20T00:00:00Z")).map((row) => row.id)).toEqual([
      "d-1",
      "d-3",
      "d-2",
    ]);
  });
});

describe("formatEventReference", () => {
  it("uses the event name once the backend sends one", () => {
    expect(formatEventReference({ event_name: "Annual Symposium", event_id: "e-1" })).toBe("Annual Symposium");
  });

  it("falls back to a short id rather than inventing a name", () => {
    expect(formatEventReference({ event_name: null, event_id: "e0000000-0000-4000-8000-000000000101" })).toBe(
      "Event E0000000",
    );
  });

  it("says so plainly when there is nothing to go on", () => {
    expect(formatEventReference({})).toBe("Unidentified event");
  });
});

describe("summariseVenueStaffDashboard", () => {
  it("counts each queue and splits venues by their active flag", () => {
    const summary = summariseVenueStaffDashboard({
      venues: [venue("b-1", "Grand Ballroom"), venue("b-8", "Old Lecture Theatre", { is_active: false })],
      pendingHolds: [hold("d-2", "2026-09-03T10:30:00+08:00"), hold("d-4", "2026-08-28T16:15:00+08:00")],
      reReviewBookings: [hold("d-5", "2026-09-10T11:45:00+08:00")],
      blocks: [blockOn("b-1", "2026-10-01T00:00:00+08:00", "2026-10-15T00:00:00+08:00")],
    });

    expect(summary).toEqual({
      pendingHolds: 2,
      reReview: 1,
      blocks: 1,
      venuesTotal: 2,
      venuesActive: 1,
      venuesInactive: 1,
    });
  });

  it("returns zeroes for an empty payload", () => {
    expect(summariseVenueStaffDashboard()).toMatchObject({ pendingHolds: 0, venuesTotal: 0 });
  });
});

describe("venueStatuses", () => {
  it("marks a venue blocked while a block is in progress", () => {
    const [row] = venueStatuses(
      [venue("b-1", "Grand Ballroom")],
      [blockOn("b-1", "2026-09-18T00:00:00+08:00", "2026-09-25T00:00:00+08:00")],
      NOW,
    );
    expect(row.status).toBe("blocked");
    expect(row.blockedUntil).toBe("2026-09-25T00:00:00+08:00");
  });

  it("does not call a venue blocked by a block that ends exactly now", () => {
    // Half-open again: the block's end is exclusive, so the venue is free.
    const [row] = venueStatuses(
      [venue("b-1", "Grand Ballroom")],
      [blockOn("b-1", "2026-09-18T00:00:00+08:00", "2026-09-19T12:00:00+08:00")],
      NOW,
    );
    expect(row.status).toBe("active");
  });

  it("is blocked from the instant a block starts", () => {
    const [row] = venueStatuses(
      [venue("b-1", "Grand Ballroom")],
      [blockOn("b-1", "2026-09-19T12:00:00+08:00", "2026-09-20T00:00:00+08:00")],
      NOW,
    );
    expect(row.status).toBe("blocked");
  });

  it("flags a block that has not started yet without calling the venue blocked", () => {
    const [row] = venueStatuses(
      [venue("b-5", "Rooftop Terrace")],
      [blockOn("b-5", "2026-10-20T00:00:00+08:00", "2026-10-22T00:00:00+08:00")],
      NOW,
    );
    expect(row.status).toBe("block_scheduled");
    expect(row.nextBlockStartsAt).toBe("2026-10-20T00:00:00+08:00");
  });

  it("reports an inactive venue as inactive even while a block sits on it", () => {
    // Out of service entirely outranks "blocked until Thursday", which would
    // understate the problem.
    const [row] = venueStatuses(
      [venue("b-8", "Old Lecture Theatre", { is_active: false })],
      [blockOn("b-8", "2026-09-18T00:00:00+08:00", "2026-09-25T00:00:00+08:00")],
      NOW,
    );
    expect(row.status).toBe("inactive");
  });

  it("ignores blocks belonging to other venues", () => {
    const [row] = venueStatuses(
      [venue("b-1", "Grand Ballroom")],
      [blockOn("b-7", "2026-09-18T00:00:00+08:00", "2026-09-25T00:00:00+08:00")],
      NOW,
    );
    expect(row.status).toBe("active");
  });

  it("puts what needs attention first, then sorts alphabetically", () => {
    const rows = venueStatuses(
      [
        venue("b-9", "Zed Room"),
        venue("b-8", "Old Lecture Theatre", { is_active: false }),
        venue("b-1", "Alpha Hall"),
        venue("b-5", "Rooftop Terrace"),
      ],
      [
        blockOn("b-5", "2026-09-18T00:00:00+08:00", "2026-09-25T00:00:00+08:00"),
        blockOn("b-9", "2026-10-20T00:00:00+08:00", "2026-10-22T00:00:00+08:00"),
      ],
      NOW,
    );
    expect(rows.map((r) => [r.venue.name, r.status])).toEqual([
      ["Rooftop Terrace", "blocked"],
      ["Zed Room", "block_scheduled"],
      ["Alpha Hall", "active"],
      ["Old Lecture Theatre", "inactive"],
    ]);
  });

  it("picks the soonest of several upcoming blocks", () => {
    const [row] = venueStatuses(
      [venue("b-5", "Rooftop Terrace")],
      [
        blockOn("b-5", "2026-11-01T00:00:00+08:00", "2026-11-02T00:00:00+08:00"),
        blockOn("b-5", "2026-10-20T00:00:00+08:00", "2026-10-22T00:00:00+08:00"),
      ],
      NOW,
    );
    expect(row.nextBlockStartsAt).toBe("2026-10-20T00:00:00+08:00");
  });
});

describe("labels", () => {
  it("spells out the controlled lists", () => {
    expect(blockReasonLabel("internal_activity")).toBe("Internal activity");
    expect(bookingStatusLabel("re_review")).toBe("Re-review");
  });

  it("degrades readably for a value the SPA does not know", () => {
    expect(blockReasonLabel("act_of_god")).toBe("act of god");
    expect(bookingStatusLabel(undefined)).toBe("");
  });
});

describe("venueStatusFilterOptions", () => {
  // The rows a loaded dashboard would hold: one of each status.
  const rows = [
    { venue: venue("b-1", "Grand Ballroom"), status: "blocked" },
    { venue: venue("b-5", "Rooftop Terrace"), status: "block_scheduled" },
    { venue: venue("b-7", "Heritage Hall"), status: "block_scheduled" },
    { venue: venue("b-2", "Auditorium A"), status: "active" },
    { venue: venue("b-8", "Old Lecture Theatre"), status: "inactive" },
  ];

  it("leads with All, counting every venue", () => {
    const [first] = venueStatusFilterOptions(rows);
    expect(first).toEqual({ key: ALL_VENUE_STATUSES, label: "All", count: 5 });
  });

  it("offers each status that is actually present, worst first, with its count", () => {
    expect(venueStatusFilterOptions(rows).slice(1)).toEqual([
      { key: "blocked", label: "Blocked now", count: 1 },
      { key: "block_scheduled", label: "Block scheduled", count: 2 },
      { key: "active", label: "Active", count: 1 },
      { key: "inactive", label: "Inactive", count: 1 },
    ]);
  });

  it("omits a status no venue has, so no control can produce an empty list", () => {
    const keys = venueStatusFilterOptions(rows.filter((row) => row.status !== "inactive")).map((o) => o.key);
    expect(keys).not.toContain("inactive");
  });

  it("offers only All when there are no venues at all", () => {
    expect(venueStatusFilterOptions([])).toEqual([{ key: ALL_VENUE_STATUSES, label: "All", count: 0 }]);
  });
});

describe("filterVenueStatuses", () => {
  const rows = [
    { venue: venue("b-1", "Grand Ballroom"), status: "blocked" },
    { venue: venue("b-5", "Rooftop Terrace"), status: "block_scheduled" },
    { venue: venue("b-8", "Old Lecture Theatre"), status: "inactive" },
  ];

  it("keeps every row, in order, when nothing is filtered", () => {
    expect(filterVenueStatuses(rows, ALL_VENUE_STATUSES).map((r) => r.venue.id)).toEqual(["b-1", "b-5", "b-8"]);
  });

  it("narrows to one status", () => {
    expect(filterVenueStatuses(rows, "inactive").map((r) => r.venue.id)).toEqual(["b-8"]);
  });

  it("falls back to everything for a status it does not know, rather than to nothing", () => {
    // An empty list reads as "no venues", which would be a lie. Showing too
    // much is recoverable; showing nothing is not.
    expect(filterVenueStatuses(rows, "decommissioned")).toHaveLength(3);
  });

  it("does not mutate its input", () => {
    const copy = [...rows];
    filterVenueStatuses(rows, "blocked");
    expect(rows).toEqual(copy);
  });
});

describe("bookingStatusColumns", () => {
  const at = (day) => ({ starts_at: `2031-05-${day}T10:00:00Z`, ends_at: `2031-05-${day}T12:00:00Z` });
  const hold = (id, expires) => ({ id, status: "held", expires_at: expires, period: at("10") });
  const state = {
    pendingHolds: [hold("h2", "2031-05-09T10:00:00Z"), hold("h1", "2031-05-08T10:00:00Z")],
    affectedBookings: [
      { id: "f2", status: "approved", flag: "affected", period: at("18") },
      { id: "f1", status: "held", flag: "affected", period: at("14") },
    ],
    bookingRequests: [
      hold("h1", "2031-05-08T10:00:00Z"),
      { id: "a2", status: "approved", period: at("20") },
      { id: "x1", status: "rejected", period: at("21") },
      { id: "a1", status: "approved", period: at("15") },
    ],
  };

  it("has Flagged bookings, Pending requests (in the middle) and Approved columns", () => {
    expect(bookingStatusColumns(state).map((column) => [column.status, column.label])).toEqual([
      ["flagged", "Flagged bookings"],
      ["pending", "Pending requests"],
      ["approved", "Approved"],
    ]);
  });

  it("puts flagged and approved bookings soonest first and the holds nearest their expiry first, leaving rejected ones out", () => {
    const [flagged, pending, approved] = bookingStatusColumns(state);

    expect(flagged.events.map((booking) => booking.id)).toEqual(["f1", "f2"]);
    expect(pending.events.map((booking) => booking.id)).toEqual(["h1", "h2"]);
    expect(approved.events.map((booking) => booking.id)).toEqual(["a1", "a2"]);
  });

  it("flags a column as needing action only while it holds a booking that needs a decision", () => {
    const [flagged, pending, approved] = bookingStatusColumns(state);
    expect([flagged.needsAttention, pending.needsAttention, approved.needsAttention]).toEqual([true, true, false]);

    const [emptyFlagged, emptyPending] = bookingStatusColumns({});
    expect([emptyFlagged.needsAttention, emptyPending.needsAttention]).toEqual([false, false]);
  });

  it("returns three empty columns for no data", () => {
    expect(bookingStatusColumns().map((column) => column.events)).toEqual([[], [], []]);
  });
});
