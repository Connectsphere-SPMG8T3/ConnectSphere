import { describe, expect, it } from "vitest";

import { formatEventDateRange } from "@/features/registrations/eventDateRange";

describe("event date ranges", () => {
  const event = {
    starts_at: "2026-11-26T10:30:00Z",
    ends_at: "2026-11-26T13:00:00Z",
    event_timezone: "Asia/Singapore",
  };

  it("formats the full weekday and date with a single same-day time range", () => {
    expect(formatEventDateRange(event)).toBe("Thursday 26 November 2026 6:30pm - 9:00pm");
  });

  it("uses a compact date without the weekday when space is limited", () => {
    expect(formatEventDateRange(event, { compact: true })).toBe("26 Nov 2026 6:30pm - 9:00pm");
  });

  it("includes both dates when the event crosses local midnight", () => {
    expect(formatEventDateRange({
      ...event,
      ends_at: "2026-11-26T17:00:00Z",
    })).toBe("Thursday 26 November 2026 6:30pm - Friday 27 November 2026 1:00am");
  });

  it("formats a start date and time when no end time is available", () => {
    expect(formatEventDateRange({
      ...event,
      ends_at: null,
    })).toBe("Thursday 26 November 2026 6:30pm");
  });

  it("reports an event without a start time as to be announced", () => {
    expect(formatEventDateRange({ starts_at: null, event_timezone: "Asia/Singapore" }))
      .toBe("Date to be announced");
  });
});
