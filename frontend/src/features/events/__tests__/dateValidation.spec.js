import { afterEach, describe, expect, it, vi } from "vitest";

import { getEarliestEventDate, getRegistrationClosingError, getRegistrationOpeningError } from "@/features/events/dateValidation";

const base = {
  opensAt: "2026-10-09T09:00",
  eventDate: "2026-10-10",
  eventEndTime: "17:00",
};

afterEach(() => {
  vi.useRealTimers();
});

describe("registration closing validation", () => {
  it("rejects an opening date that is today or earlier", () => {
    expect(getRegistrationOpeningError("2026-09-19T09:00", "2026-09-19")).toBe(
      "Registration opening date must be after today.",
    );
  });

  it("requires closing after opening", () => {
    expect(getRegistrationClosingError({ ...base, closesAt: "2026-10-09T08:00" }, "2026-09-19")).toBe(
      "Registration closing time must be after opening time.",
    );
  });

  it("requires a closing date after today", () => {
    expect(getRegistrationClosingError({ ...base, opensAt: "2026-09-20T09:00", closesAt: "2026-09-19T18:00" }, "2026-09-19")).toBe(
      "Registration closing date must be after today.",
    );
  });

  it("keeps closing at or before the event end", () => {
    expect(getRegistrationClosingError({ ...base, closesAt: "2026-10-10T17:01" }, "2026-09-19")).toBe(
      "Registration closing time cannot be after the event end time.",
    );
  });
});import { describe, expect, it } from "vitest";

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

describe("event date minimum", () => {
  it("requires a proposed event date after today's Singapore date", () => {
    const today = new Date("2026-09-19T23:30:00+08:00");
    const expectedTomorrow = "2026-09-20";
    vi.useFakeTimers();
    vi.setSystemTime(today);

    expect(getEarliestEventDate()).toBe(expectedTomorrow);
  });
});
describe("timezones.getEarliestEventDate", () => {
  // Timezones behind UTC are wrong today: DEFECTS D91.
  it("is the day after today in a timezone ahead of UTC", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2031-05-01T20:00:00Z"));
    const { getEarliestEventDate: earliest } = await import("@/features/events/timezones");

    expect(earliest("Asia/Singapore")).toBe("2031-05-03");
    expect(earliest("Pacific/Kiritimati")).toBe("2031-05-03");
    vi.useRealTimers();
  });
});
