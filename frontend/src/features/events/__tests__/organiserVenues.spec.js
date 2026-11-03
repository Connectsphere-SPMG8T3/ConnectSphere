import { describe, expect, it } from "vitest";

import { coordinatorLabel, venueWindowLabel } from "@/features/events/organiserVenues";

describe("coordinatorLabel (CR-111 AC1, QA3-42)", () => {
  it("reads Unassigned until a coordinator is assigned", () => {
    expect(coordinatorLabel({ coordinator: null, coordinator_id: null })).toBe("Unassigned");
    expect(coordinatorLabel({})).toBe("Unassigned");
  });

  it("shows the coordinator's name once assigned, and the new name after a reassignment", () => {
    expect(coordinatorLabel({ coordinator: { full_name: "Marcus Lim" } })).toBe("Marcus Lim");
    expect(coordinatorLabel({ coordinator: { full_name: "Priya Nair" } })).toBe("Priya Nair");
  });

  it("falls back to Assigned when only the ID is known", () => {
    expect(coordinatorLabel({ coordinator: null, coordinator_id: "c1" })).toBe("Assigned");
  });
});

describe("venueWindowLabel (CR-111 AC2)", () => {
  it("shows the window in the event's timezone", () => {
    const label = venueWindowLabel("2026-11-12T02:00:00Z", "2026-11-12T04:30:00Z", "Asia/Singapore");

    expect(label).toContain("12 Nov 2026");
    expect(label).toContain("10:00");
    expect(label).toContain("12:30");
  });

  it("says so when the time is not known", () => {
    expect(venueWindowLabel(null, null, "Asia/Singapore")).toBe("Time not provided");
  });
});
