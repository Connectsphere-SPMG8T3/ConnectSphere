import { describe, expect, it } from "vitest";

import {
  BOOKING_GROUPS,
  VENUE_PROFILE_TABS,
  formatTurnaround,
  groupUpcomingBookings,
  lastEditorName,
  stepIndex,
  venueProfileTabs,
} from "@/features/venues/venueProfile";

const booking = (id, status, startHour) => ({
  id,
  event_id: `e${id}`,
  status,
  period: {
    starts_at: `2026-10-10T0${startHour}:00:00Z`,
    ends_at: `2026-10-10T0${startHour + 1}:00:00Z`,
  },
});

describe("groupUpcomingBookings (SCRUM-67 AC3)", () => {
  it("splits occupying bookings into confirmed, tentative and re-review", () => {
    const groups = groupUpcomingBookings([
      booking("1", "held", 1),
      booking("2", "approved", 2),
      booking("3", "re_review", 3),
      booking("4", "approved", 4),
    ]);

    expect(groups.map((g) => [g.key, g.bookings.map((b) => b.id)])).toEqual([
      ["confirmed", ["2", "4"]],
      ["tentative", ["1"]],
      ["reReview", ["3"]],
    ]);
  });

  it("orders each group soonest first, whatever order the API sent", () => {
    const groups = groupUpcomingBookings([booking("late", "approved", 8), booking("early", "approved", 2)]);

    expect(groups[0].bookings.map((b) => b.id)).toEqual(["early", "late"]);
  });

  it("returns every group even when empty, so the profile can say 'none'", () => {
    const groups = groupUpcomingBookings([]);

    expect(groups).toHaveLength(BOOKING_GROUPS.length);
    expect(groups.every((g) => g.bookings.length === 0)).toBe(true);
  });

  it("tolerates a missing list", () => {
    expect(groupUpcomingBookings().every((g) => g.bookings.length === 0)).toBe(true);
  });

  it("never silently drops a booking whose status it does not recognise", () => {
    const groups = groupUpcomingBookings([booking("1", "approved", 1), booking("9", "invented", 2)]);
    const shown = groups.flatMap((g) => g.bookings.map((b) => b.id));

    expect(shown).toContain("9");
  });
});

describe("formatTurnaround (QA-28)", () => {
  it("says back-to-back is allowed when the buffer is zero", () => {
    expect(formatTurnaround(0)).toBe("None — bookings may run back to back");
  });

  it("words a real buffer in hours and minutes", () => {
    expect(formatTurnaround(30)).toBe("30 min between bookings");
    expect(formatTurnaround(60)).toBe("1 h between bookings");
    expect(formatTurnaround(90)).toBe("1 h 30 min between bookings");
  });

  it("says nothing rather than guessing when the figure is missing", () => {
    expect(formatTurnaround(null)).toBe("Not recorded");
    expect(formatTurnaround(undefined)).toBe("Not recorded");
  });
});

describe("lastEditorName (SCRUM-67 AC2)", () => {
  it("names the editor", () => {
    expect(lastEditorName({ id: "a1", full_name: "Val Staff" })).toBe("Val Staff");
  });

  it("falls back to a short id when the account has no name", () => {
    expect(lastEditorName({ id: "a0000000-1111-4000-8000-000000000003" })).toBe("Account A0000000");
  });

  it("reports that nothing was recorded rather than inventing an editor", () => {
    expect(lastEditorName(null)).toBe("Not recorded");
    expect(lastEditorName(undefined)).toBe("Not recorded");
  });
});

describe("venueProfileTabs", () => {
  const venue = {
    upcoming_bookings: [booking("1", "approved", 1), booking("2", "held", 2)],
    upcoming_blocks: [{ id: "c1" }],
  };

  it("returns the four profile tabs in a fixed order", () => {
    expect(venueProfileTabs(venue).map((t) => t.key)).toEqual(VENUE_PROFILE_TABS.map((t) => t.key));
    expect(venueProfileTabs(venue).map((t) => t.key)).toEqual(["capacity", "facilities", "bookings", "blocks"]);
  });

  it("counts what is behind the time-based tabs, so a closed tab still shows there is something in it", () => {
    const byKey = Object.fromEntries(venueProfileTabs(venue).map((t) => [t.key, t.count]));

    expect(byKey.bookings).toBe(2);
    expect(byKey.blocks).toBe(1);
  });

  it("gives the attribute tabs no count, rather than a misleading zero", () => {
    const byKey = Object.fromEntries(venueProfileTabs(venue).map((t) => [t.key, t.count]));

    expect(byKey.capacity).toBeNull();
    expect(byKey.facilities).toBeNull();
  });

  it("counts zero for an empty venue, and tolerates a missing venue", () => {
    expect(venueProfileTabs({}).find((t) => t.key === "bookings").count).toBe(0);
    expect(venueProfileTabs().find((t) => t.key === "blocks").count).toBe(0);
  });
});

describe("stepIndex (photo carousel)", () => {
  it("moves forward and backward", () => {
    expect(stepIndex(0, 3, 1)).toBe(1);
    expect(stepIndex(2, 3, -1)).toBe(1);
  });

  it("wraps at both ends, so the carousel never dead-ends", () => {
    expect(stepIndex(2, 3, 1)).toBe(0);
    expect(stepIndex(0, 3, -1)).toBe(2);
  });

  it("stays at zero when there is nothing to show", () => {
    expect(stepIndex(0, 0, 1)).toBe(0);
    expect(stepIndex(0, 0, -1)).toBe(0);
  });

  it("handles a single photo without moving", () => {
    expect(stepIndex(0, 1, 1)).toBe(0);
  });
});
