import { afterEach, describe, expect, it, vi } from "vitest";
import * as singaporeTime from "@/features/venues/singaporeTime";

describe("formatSingaporeDateTime (D61)", () => {
  afterEach(() => vi.unstubAllEnvs());

  it.each([
    ["2026-10-24T16:00:00Z", "25 Oct 2026, 12:00 am"],
    ["2031-12-10T01:00:00Z", "10 Dec 2031, 9:00 am"],
    ["2031-12-10T17:15:00+08:00", "10 Dec 2031, 5:15 pm"],
  ])("formats %s with the Singapore date and time", (iso, expected) => {
    vi.stubEnv("TZ", "UTC");
    expect(singaporeTime.formatSingaporeDateTime(iso)).toBe(expected);
  });
});
