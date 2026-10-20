import { describe, expect, it } from "vitest";

import {
  LEAD_STATUS_OPTIONS,
  coordinatorFilterOptions,
  coordinatorOptions,
  filterLeadEvents,
  queueVenueNeeds,
  sortLeadEvents,
} from "@/features/events/leadDashboard";

const EVENTS = [
  { event_id: "e1", event_name: "Annual Conference", status: "planning", starts_at: "2026-11-02T02:00:00Z", coordinator: { id: "c1", full_name: "Marcus Lim" } },
  { event_id: "e2", event_name: "Product Launch", status: "confirmed", starts_at: "2026-11-01T02:00:00Z", coordinator: { id: "c2", full_name: "Priya Nair" } },
  { event_id: "e3", event_name: "Alumni Night", status: "planning", starts_at: null, coordinator: { id: "c1", full_name: "Marcus Lim" } },
];
const COORDINATORS = [
  { id: "c1", full_name: "Marcus Lim", active_count: 2 },
  { id: "c2", full_name: "Priya Nair", active_count: 1 },
  { id: "c3", full_name: "Idle Person", active_count: 0 },
];

describe("filterLeadEvents", () => {
  it("returns everything with no filters", () => {
    expect(filterLeadEvents(EVENTS, {})).toHaveLength(3);
  });
  it("filters by coordinator", () => {
    expect(filterLeadEvents(EVENTS, { coordinator: "c1" }).map((e) => e.event_id)).toEqual(["e1", "e3"]);
  });
  it("filters by one or more statuses", () => {
    expect(filterLeadEvents(EVENTS, { status: ["confirmed"] }).map((e) => e.event_id)).toEqual(["e2"]);
    expect(filterLeadEvents(EVENTS, { status: ["confirmed", "planning"] })).toHaveLength(3);
  });
  it("combines filters and a case-insensitive name search", () => {
    expect(
      filterLeadEvents(EVENTS, { coordinator: "c1", status: ["planning"], search: "ALUMNI" }).map((e) => e.event_id),
    ).toEqual(["e3"]);
  });
  it("returns nothing when nothing matches", () => {
    expect(filterLeadEvents(EVENTS, { coordinator: "c2", status: ["planning"] })).toEqual([]);
  });
  it("copes with no events at all", () => {
    expect(filterLeadEvents(undefined, { coordinator: "c1" })).toEqual([]);
  });
});

describe("sortLeadEvents", () => {
  it("puts the soonest first and undated events last, without mutating", () => {
    const before = [...EVENTS];
    expect(sortLeadEvents(EVENTS).map((e) => e.event_id)).toEqual(["e2", "e1", "e3"]);
    expect(EVENTS).toEqual(before);
  });
  it("orders undated events by name", () => {
    const undated = [
      { event_id: "b", event_name: "Beta", starts_at: null },
      { event_id: "a", event_name: "Alpha", starts_at: "not a date" },
    ];
    expect(sortLeadEvents(undated).map((e) => e.event_id)).toEqual(["a", "b"]);
  });
});

describe("coordinator options", () => {
  it("labels the filter with each coordinator's active count, including zero", () => {
    expect(coordinatorFilterOptions(COORDINATORS)).toEqual([
      { value: "c1", label: "Marcus Lim (2)" },
      { value: "c2", label: "Priya Nair (1)" },
      { value: "c3", label: "Idle Person (0)" },
    ]);
  });
  it("offers every coordinator except the current one when reassigning", () => {
    expect(coordinatorOptions(COORDINATORS, "c1").map((o) => o.value)).toEqual(["c2", "c3"]);
    expect(coordinatorOptions(COORDINATORS, null)).toHaveLength(3);
  });
});

describe("LEAD_STATUS_OPTIONS", () => {
  it("lists only active statuses with their labels", () => {
    expect(LEAD_STATUS_OPTIONS.map((o) => o.value)).toEqual([
      "under_review",
      "returned",
      "planning",
      "safety_review",
      "confirmed",
    ]);
    expect(LEAD_STATUS_OPTIONS.every((o) => o.label)).toBe(true);
  });
});

describe("queueVenueNeeds (SCRUM-12 AC10)", () => {
  it("names the layout and facilities an event asks of a venue", () => {
    expect(queueVenueNeeds({ layout_preference: "u_shape", facilities_required: ["projector", "video_conferencing"] })).toBe(
      "U-shape · Projector, Video conferencing",
    );
  });

  it("copes with only a layout, only facilities, or neither", () => {
    expect(queueVenueNeeds({ layout_preference: "theatre", facilities_required: [] })).toBe("Theatre");
    expect(queueVenueNeeds({ layout_preference: null, facilities_required: ["wifi"] })).toBe("Wi-Fi");
    expect(queueVenueNeeds({})).toBe("No venue needs given");
  });
});
