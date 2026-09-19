import { describe, expect, it } from "vitest";

import { isEventDateAfterToday } from "@/features/events/dateValidation";

describe("isEventDateAfterToday", () => {
  it("accepts a date after today", () => {
    expect(isEventDateAfterToday("2026-09-20", "2026-09-19")).toBe(true);
  });

  it("rejects today and earlier dates", () => {
    expect(isEventDateAfterToday("2026-09-19", "2026-09-19")).toBe(false);
    expect(isEventDateAfterToday("2026-09-18", "2026-09-19")).toBe(false);
  });
});