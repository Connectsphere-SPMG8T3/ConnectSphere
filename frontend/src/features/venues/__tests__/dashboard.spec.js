import { describe, expect, it } from "vitest";

import {
  blockReasonLabel,
  bookingStatusLabel,
  formatEventReference,
  sortPendingHoldsOldestFirst,
  summariseVenueStaffDashboard,
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

describe("sortPendingHoldsOldestFirst", () => {
  it("puts the longest-waiting request first", () => {
    const sorted = sortPendingHoldsOldestFirst([
      hold("d-2", "2026-09-03T10:30:00+08:00"),
      hold("d-4", "2026-08-28T16:15:00+08:00"),
      hold("d-9", "2026-09-10T11:45:00+08:00"),
    ]);
    expect(sorted.map((h) => h.id)).toEqual(["d-4", "d-2", "d-9"]);
  });

  it("keeps a stable order for two requests made in the same instant", () => {
    const same = "2026-09-03T10:30:00+08:00";
    const sorted = sortPendingHoldsOldestFirst([hold("d-9", same), hold("d-1", same)]);
    expect(sorted.map((h) => h.id)).toEqual(["d-1", "d-9"]);
  });

  it("does not mutate its input", () => {
    const input = [hold("d-2", "2026-09-03T10:30:00+08:00"), hold("d-4", "2026-08-28T16:15:00+08:00")];
    sortPendingHoldsOldestFirst(input);
    expect(input.map((h) => h.id)).toEqual(["d-2", "d-4"]);
  });

  it("sorts an unparseable timestamp last rather than throwing", () => {
    const sorted = sortPendingHoldsOldestFirst([hold("d-bad", "nonsense"), hold("d-ok", "2026-09-03T10:30:00+08:00")]);
    expect(sorted.map((h) => h.id)).toEqual(["d-ok", "d-bad"]);
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
