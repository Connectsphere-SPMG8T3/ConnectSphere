import { describe, expect, it } from "vitest";

import {
  BLOCK_CHANGE_NOTE_MAX_LENGTH,
  blockActions,
  blockSetBy,
  blockStatusLabel,
  emptyBlockChange,
  toBlockChangePayload,
  validateBlockChange,
} from "@/features/venues/blockChange";

// 1 May 2031, 10:00 Singapore time.
const NOW = new Date("2031-05-01T02:00:00Z");
// 20 May 2031, 09:00–17:00 Singapore time: hasn't started.
const UPCOMING = { id: "b1", status: "active", period: { starts_at: "2031-05-20T01:00:00Z", ends_at: "2031-05-20T09:00:00Z" } };
// Started an hour ago, ends tomorrow.
const CURRENT = { id: "b2", status: "active", period: { starts_at: "2031-05-01T01:00:00Z", ends_at: "2031-05-02T02:00:00Z" } };

describe("which changes a block allows (SCRUM-54 AC2)", () => {
  it("a block that hasn't started can be shortened or removed, not ended now", () => {
    expect(blockActions(UPCOMING, NOW)).toEqual(["shorten", "remove"]);
  });

  it("a block in progress can be ended now or shortened, not removed", () => {
    expect(blockActions(CURRENT, NOW)).toEqual(["end_now", "shorten"]);
  });

  it("a block that has ended, or was removed, can't be changed", () => {
    expect(blockActions({ ...CURRENT, period: { ...CURRENT.period, ends_at: NOW.toISOString() } }, NOW)).toEqual([]);
    expect(blockActions({ ...UPCOMING, status: "removed" }, NOW)).toEqual([]);
  });

  it("a block starting exactly now counts as started", () => {
    expect(blockActions({ ...UPCOMING, period: { ...UPCOMING.period, starts_at: NOW.toISOString() } }, NOW))
      .toEqual(["end_now", "shorten"]);
  });

  it("no block, no changes", () => {
    expect(blockActions(null, NOW)).toEqual([]);
  });
});

describe("the change form (SCRUM-54 AC2)", () => {
  it("starts with the action chosen and nothing else", () => {
    expect(emptyBlockChange("shorten")).toEqual({ action: "shorten", endsAt: "", note: "" });
  });

  it("ending now or removing needs nothing more", () => {
    expect(validateBlockChange({ action: "end_now", endsAt: "", note: "" }, CURRENT, NOW)).toEqual({});
    expect(validateBlockChange({ action: "remove", endsAt: "", note: "" }, UPCOMING, NOW)).toEqual({});
  });

  it("asks what to do when nothing is chosen", () => {
    expect(validateBlockChange({ action: "", endsAt: "", note: "" }, CURRENT, NOW))
      .toEqual({ action: "Choose what to do." });
  });

  it("shortening needs a new end", () => {
    expect(validateBlockChange({ action: "shorten", endsAt: "", note: "" }, UPCOMING, NOW))
      .toEqual({ endsAt: "Choose the new end." });
  });

  it("accepts a new end between the start and the current end", () => {
    expect(validateBlockChange({ action: "shorten", endsAt: "2031-05-20T12:00", note: "" }, UPCOMING, NOW)).toEqual({});
  });

  it("refuses a new end at or after the current end: a block can't be lengthened", () => {
    for (const endsAt of ["2031-05-20T17:00", "2031-05-20T18:00"]) {
      expect(validateBlockChange({ action: "shorten", endsAt, note: "" }, UPCOMING, NOW).endsAt)
        .toBe("The new end must be earlier than the current end. To block for longer, add a new block.");
    }
  });

  it("refuses a new end at or before the start", () => {
    expect(validateBlockChange({ action: "shorten", endsAt: "2031-05-20T09:00", note: "" }, UPCOMING, NOW).endsAt)
      .toBe("The new end must be after the block's start.");
  });

  it("refuses a new end in the past, pointing to End now", () => {
    expect(validateBlockChange({ action: "shorten", endsAt: "2031-05-01T09:59", note: "" }, CURRENT, NOW).endsAt)
      .toBe("The new end must be in the future. To end the block now, choose End now.");
  });

  it("allows a note of 1000 characters and refuses a longer one", () => {
    const base = { action: "end_now", endsAt: "" };
    expect(validateBlockChange({ ...base, note: "n".repeat(BLOCK_CHANGE_NOTE_MAX_LENGTH) }, CURRENT, NOW)).toEqual({});
    expect(validateBlockChange({ ...base, note: "n".repeat(1001) }, CURRENT, NOW).note)
      .toBe("The note can be at most 1000 characters.");
  });

  it("counts the note after trimming", () => {
    expect(validateBlockChange({ action: "end_now", endsAt: "", note: ` ${"n".repeat(1000)} ` }, CURRENT, NOW))
      .toEqual({});
  });
});

describe("the change payload", () => {
  it("sends the new end as Singapore time when shortening", () => {
    expect(toBlockChangePayload({ action: "shorten", endsAt: "2031-05-20T12:00", note: "  Done early " }))
      .toEqual({ action: "shorten", ends_at: "2031-05-20T12:00:00+08:00", note: "Done early" });
  });

  it("sends no end for end now or remove, and a blank note as null", () => {
    expect(toBlockChangePayload({ action: "end_now", endsAt: "2031-05-20T12:00", note: "  " }))
      .toEqual({ action: "end_now", ends_at: null, note: null });
    expect(toBlockChangePayload({ action: "remove", endsAt: "", note: "" }))
      .toEqual({ action: "remove", ends_at: null, note: null });
  });
});

describe("how a block is described (SCRUM-54 AC1, AC4)", () => {
  it("labels each status", () => {
    expect(blockStatusLabel("ended_early")).toBe("Ended early");
    expect(blockStatusLabel("removed")).toBe("Removed");
    expect(blockStatusLabel("active")).toBe("Active");
    expect(blockStatusLabel(undefined)).toBe("Active");
  });

  it("names who set the block and when, in Singapore time", () => {
    expect(blockSetBy({ created_by: { id: "a", full_name: "Vera Staff" }, created_at: "2031-04-30T02:30:00Z" }))
      .toBe("Set by Vera Staff · 30 Apr 2031, 10:30");
  });

  it("says when who or when wasn't recorded, rather than inventing it", () => {
    expect(blockSetBy({ created_by: { id: "a", full_name: null }, created_at: null })).toBe("Set by Unknown user");
    expect(blockSetBy({})).toBe("Set by Unknown user");
  });
});

describe("a change with no note at all", () => {
  it("is valid and sends a null note", () => {
    expect(validateBlockChange({ action: "end_now", endsAt: "" }, CURRENT, NOW)).toEqual({});
    expect(toBlockChangePayload({ action: "end_now", endsAt: "" })).toEqual({ action: "end_now", ends_at: null, note: null });
  });
});
