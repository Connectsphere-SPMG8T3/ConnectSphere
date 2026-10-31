import { describe, expect, it } from "vitest";

import {
  defaultInventoryWindow,
  describeInventoryWindow,
  inventoryWindowError,
} from "@/features/equipment/inventoryWindow";

describe("tech support's inventory window (D46)", () => {
  it("defaults to today, 9 am to 5 pm, as datetime-local values", () => {
    expect(defaultInventoryWindow(new Date("2026-10-19T22:30:00+08:00"))).toEqual({
      startAt: "2026-10-19T09:00",
      endAt: "2026-10-19T17:00",
    });
    expect(defaultInventoryWindow(new Date("2026-01-05T08:00:00+08:00"))).toEqual({
      startAt: "2026-01-05T09:00",
      endAt: "2026-01-05T17:00",
    });
  });

  it("needs both ends, with the end after the start", () => {
    expect(inventoryWindowError("2026-10-19T09:00", "2026-10-19T17:00")).toBeNull();
    expect(inventoryWindowError("", "2026-10-19T17:00")).toBe("Choose a start and an end for the inventory window.");
    expect(inventoryWindowError("2026-10-19T09:00", null)).toBe("Choose a start and an end for the inventory window.");
    expect(inventoryWindowError("2026-10-19T17:00", "2026-10-19T17:00")).toBe("End time must be later than the start time.");
    expect(inventoryWindowError("2026-10-19T17:00", "2026-10-19T09:00")).toBe("End time must be later than the start time.");
  });

  it("describes the window as entered, naming the date once when it is one day", () => {
    expect(describeInventoryWindow("2026-10-19T09:00", "2026-10-19T17:00")).toBe("19 Oct 2026, 9:00 am – 5:00 pm");
    expect(describeInventoryWindow("2031-09-01T00:00", "2031-09-01T12:30")).toBe("1 Sep 2031, 12:00 am – 12:30 pm");
    expect(describeInventoryWindow("2026-12-31T21:15", "2027-01-02T13:05")).toBe("31 Dec 2026, 9:15 pm – 2 Jan 2027, 1:05 pm");
  });

  it("describes nothing it can't read", () => {
    expect(describeInventoryWindow("", "2026-10-19T17:00")).toBe("");
    expect(describeInventoryWindow("not a date", "2026-10-19T17:00")).toBe("");
  });
});
