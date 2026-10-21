import { describe, expect, it } from "vitest";

import { formatNotificationTime } from "@/features/notifications/format";

const NOW = new Date("2026-10-20T12:00:00Z");

describe("formatNotificationTime", () => {
  it.each([
    ["2026-10-20T12:00:00Z", "just now"],
    ["2026-10-20T11:59:31Z", "just now"],
    ["2026-10-20T11:55:00Z", "5 min ago"],
    ["2026-10-20T11:01:00Z", "59 min ago"],
    ["2026-10-20T09:00:00Z", "3 h ago"],
    ["2026-10-19T12:30:00Z", "23 h ago"],
    ["2026-10-18T12:00:00Z", "18 Oct"],
    ["2026-01-05T08:00:00Z", "5 Jan"],
  ])("%s reads %s", (iso, expected) => {
    expect(formatNotificationTime(iso, NOW)).toBe(expected);
  });

  it("treats a time slightly in the future (clock skew) as just now", () => {
    expect(formatNotificationTime("2026-10-20T12:00:30Z", NOW)).toBe("just now");
  });

  it("returns an empty string for a missing or invalid time", () => {
    expect(formatNotificationTime(null, NOW)).toBe("");
    expect(formatNotificationTime("not a date", NOW)).toBe("");
  });
});
