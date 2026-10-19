import { describe, expect, it } from "vitest";

import {
  BLOCK_DETAIL_MAX_LENGTH,
  BLOCK_REASONS,
  emptyBlockForm,
  toBlockPayload,
  validateBlockForm,
} from "@/features/venues/blockForm";

// 1 May 2031, 10:00 Singapore time.
const NOW = new Date("2031-05-01T02:00:00Z");
const VALID = { startsAt: "2031-05-20T09:00", endsAt: "2031-05-20T17:00", reason: "maintenance", detail: "" };

describe("block form rules (SCRUM-51 AC1)", () => {
  it("lists the six categories in the order the story names them", () => {
    expect(BLOCK_REASONS.map((r) => r.value)).toEqual([
      "maintenance", "equipment_failure", "renovation", "safety", "internal_activity", "other",
    ]);
    expect(BLOCK_REASONS[1].label).toBe("Equipment failure");
  });

  it("starts empty", () => {
    expect(emptyBlockForm()).toEqual({ startsAt: "", endsAt: "", reason: "", detail: "" });
  });

  it("accepts a valid block", () => {
    expect(validateBlockForm(VALID, NOW)).toEqual({});
  });

  it("accepts a start in the past for an emergency block", () => {
    expect(validateBlockForm({ ...VALID, startsAt: "2031-04-30T09:00", endsAt: "2031-05-01T12:00" }, NOW)).toEqual({});
  });

  it("names a missing start, end and reason", () => {
    expect(validateBlockForm(emptyBlockForm(), NOW)).toEqual({
      startsAt: "Choose a start date and time.",
      endsAt: "Choose an end date and time.",
      reason: "Choose a reason.",
    });
  });

  it("refuses an end before or equal to the start", () => {
    expect(validateBlockForm({ ...VALID, endsAt: "2031-05-20T08:00" }, NOW).endsAt).toBe("End must be after start.");
    expect(validateBlockForm({ ...VALID, endsAt: VALID.startsAt }, NOW).endsAt).toBe("End must be after start.");
  });

  it("refuses an end that has already passed", () => {
    const errors = validateBlockForm({ ...VALID, startsAt: "2031-04-30T08:00", endsAt: "2031-05-01T10:00" }, NOW);
    expect(errors.endsAt).toBe("End must be in the future.");
  });

  it("requires a detail for Other, ignoring spaces", () => {
    expect(validateBlockForm({ ...VALID, reason: "other", detail: "   " }, NOW).detail)
      .toBe("A detail is required when the reason is Other.");
    expect(validateBlockForm({ ...VALID, reason: "other", detail: "Film shoot" }, NOW)).toEqual({});
  });

  it("caps the detail at 1000 characters", () => {
    expect(BLOCK_DETAIL_MAX_LENGTH).toBe(1000);
    expect(validateBlockForm({ ...VALID, detail: "x".repeat(1000) }, NOW)).toEqual({});
    expect(validateBlockForm({ ...VALID, detail: "x".repeat(1001) }, NOW).detail)
      .toBe("The detail can be at most 1000 characters.");
  });

  it("builds the payload in Singapore time with a trimmed detail", () => {
    expect(toBlockPayload({ ...VALID, detail: "  Aircon  " }, { confirm: true })).toEqual({
      starts_at: "2031-05-20T09:00:00+08:00",
      ends_at: "2031-05-20T17:00:00+08:00",
      reason: "maintenance",
      detail: "Aircon",
      confirm: true,
    });
    expect(toBlockPayload(VALID)).toMatchObject({ detail: null, confirm: false });
  });
});
