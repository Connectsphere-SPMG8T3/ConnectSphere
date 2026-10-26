import { describe, expect, it } from "vitest";

import * as publicEvents from "@/features/registrations/publicEvents";

describe("public event presentation", () => {
  it("formats public event dates in the event timezone", () => {
    expect(publicEvents.formatPublicEventDate).toBeTypeOf("function");
    if (!publicEvents.formatPublicEventDate) return;

    expect(publicEvents.formatPublicEventDate({
      starts_at: "2026-11-03T11:00:00Z",
      ends_at: "2026-11-03T13:00:00Z",
      event_timezone: "Asia/Singapore",
    })).toBe("3 Nov 2026 7:00pm - 9:00pm");
  });

  it("labels public registration availability", () => {
    expect(publicEvents.publicEventAvailabilityLabel).toBeTypeOf("function");
    if (!publicEvents.publicEventAvailabilityLabel) return;

    expect(publicEvents.publicEventAvailabilityLabel("open")).toBe("Registration open");
    expect(publicEvents.publicEventAvailabilityLabel("full")).toBe("Full");
    expect(publicEvents.publicEventAvailabilityLabel("unknown")).toBe("Registration unavailable");
  });

  it("filters public events by name and sorts them by date or name in either direction", () => {
    expect(publicEvents.filterAndSortPublicEvents).toBeTypeOf("function");
    if (!publicEvents.filterAndSortPublicEvents) return;

    const events = [
      { id: "b", name: "Blue Evening", starts_at: "2026-11-03T11:00:00Z" },
      { id: "a", name: "Amber Gathering", starts_at: "2026-11-02T11:00:00Z" },
      { id: "c", name: "Amber Supper", starts_at: "2026-11-04T11:00:00Z" },
    ];

    expect(publicEvents.filterAndSortPublicEvents(events, { search: "AMBER", sortBy: "name" }).map(({ id }) => id))
      .toEqual(["a", "c"]);
    expect(publicEvents.filterAndSortPublicEvents(events, { sortBy: "date", direction: "desc" }).map(({ id }) => id))
      .toEqual(["c", "b", "a"]);
    expect(publicEvents.filterAndSortPublicEvents(events, { sortBy: "name", direction: "desc" }).map(({ id }) => id))
      .toEqual(["b", "c", "a"]);
  });
});
