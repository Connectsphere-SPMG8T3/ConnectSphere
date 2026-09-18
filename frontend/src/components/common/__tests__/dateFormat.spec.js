import { describe, expect, it } from "vitest";

import { formatFriendlyDate, ordinalSuffix } from "@/components/common/dateFormat";

describe("ordinalSuffix", () => {
  it("uses st/nd/rd for 1, 2 and 3", () => {
    expect(ordinalSuffix(1)).toBe("st");
    expect(ordinalSuffix(22)).toBe("nd");
    expect(ordinalSuffix(23)).toBe("rd");
  });

  it("uses th for the 11th to 13th", () => {
    expect(ordinalSuffix(11)).toBe("th");
    expect(ordinalSuffix(12)).toBe("th");
    expect(ordinalSuffix(13)).toBe("th");
  });

  it("uses th for everything else", () => {
    expect(ordinalSuffix(4)).toBe("th");
    expect(ordinalSuffix(30)).toBe("th");
  });
});

describe("formatFriendlyDate", () => {
  it("renders the day, month name and year", () => {
    expect(formatFriendlyDate(new Date(2025, 4, 8))).toBe("8th May 2025");
    expect(formatFriendlyDate(new Date(2026, 0, 1))).toBe("1st January 2026");
  });
});
