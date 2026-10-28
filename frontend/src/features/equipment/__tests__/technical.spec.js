import { describe, expect, it } from "vitest";

import {
  canMarkNotAvailable,
  canReserve,
  exitConfirmationText,
  formatTechnicalTime,
  hasLiveLines,
  historyActor,
  historyEntryText,
  reReviewCause,
  reReviewText,
  isOpenForArrangements,
  NOT_AVAILABLE_REASON_MAX_LENGTH,
  notesError,
  reasonError,
  TECHNICAL_NOTES_MAX_LENGTH,
} from "@/features/equipment/technical";

describe("SCRUM-24 which actions a line offers", () => {
  it.each([
    ["pending", true, true],
    ["re_review", true, true],
    ["reserved", false, true],
    ["rejected", false, false],
    ["released", false, false],
  ])("a %s line: reserve %s, not available %s", (status, reserve, notAvailable) => {
    expect(canReserve(status)).toBe(reserve);
    expect(canMarkNotAvailable(status)).toBe(notAvailable);
  });

  it.each([
    ["planning", true], ["safety_review", true], ["confirmed", true],
    ["under_review", false], ["rejected", false], ["completed", false],
  ])("an event in %s is open for arrangements: %s", (status, open) => {
    expect(isOpenForArrangements(status)).toBe(open);
  });

  it("only an event with a line that isn't released has anything to tick (AC10)", () => {
    expect(hasLiveLines([])).toBe(false);
    expect(hasLiveLines([{ status: "released" }])).toBe(false);
    expect(hasLiveLines([{ status: "released" }, { status: "pending" }])).toBe(true);
  });
});

describe("SCRUM-24 reason and notes limits", () => {
  it("a Not available reason is required and bounded (AC3, EQ-R3)", () => {
    expect(reasonError("")).toBe("Give a reason the line is not available.");
    expect(reasonError("   ")).toBe("Give a reason the line is not available.");
    expect(reasonError(null)).toBe("Give a reason the line is not available.");
    expect(reasonError("x".repeat(NOT_AVAILABLE_REASON_MAX_LENGTH))).toBeNull();
    expect(reasonError("x".repeat(NOT_AVAILABLE_REASON_MAX_LENGTH + 1))).toBe("Keep the reason to 500 characters.");
  });

  it("notes are optional and bounded (AC9)", () => {
    expect(notesError("")).toBeNull();
    expect(notesError(undefined)).toBeNull();
    expect(notesError("x".repeat(TECHNICAL_NOTES_MAX_LENGTH))).toBeNull();
    expect(notesError("x".repeat(TECHNICAL_NOTES_MAX_LENGTH + 1))).toBe("Keep the notes to 2000 characters.");
  });
});

describe("SCRUM-24 how the tick and history read", () => {
  it("the exit tick names who and when, in Singapore time (AC10)", () => {
    expect(exitConfirmationText(null)).toBe("Not recorded");
    expect(exitConfirmationText({ confirmed_by_name: "Tan Wei", confirmed_at: "2026-10-19T03:00:00Z" }))
      .toBe(`Confirmed by Tan Wei · ${formatTechnicalTime("2026-10-19T03:00:00Z")}`);
    expect(exitConfirmationText({ confirmed_by_name: null, confirmed_at: "2026-10-19T03:00:00Z" }))
      .toMatch(/^Confirmed by a former staff member · /);
  });

  it("a missing time reads as not set", () => {
    expect(formatTechnicalTime(null)).toBe("Date not set");
    expect(formatTechnicalTime("2026-10-19T03:00:00Z")).toContain("2026");
  });

  it("history names the action, the line and the change (AC13)", () => {
    expect(historyEntryText({ action: "not_available", line_label: "3 × 4K Projector", from_status: "pending", to_status: "rejected" }))
      .toBe("Marked not available · 3 × 4K Projector · Pending → Not available");
    expect(historyEntryText({ action: "technical_status", line_label: null, from_status: "pending", to_status: "ready" }))
      .toBe("Technical status changed · Pending → Ready");
    expect(historyEntryText({ action: "refused", line_label: "3 × Mic", from_status: "pending", to_status: "pending" }))
      .toBe("Reserve refused · 3 × Mic");
    expect(historyEntryText({ action: "exit_cleared", line_label: null, from_status: null, to_status: null }))
      .toBe("Exit check cleared");
    // SCRUM-44 AC8: the coordinator's change and removal.
    expect(historyEntryText({ action: "edited", line_label: "4 × Projector", from_status: "reserved", to_status: "re_review" }))
      .toBe("Changed by the coordinator · 4 × Projector · Reserved → Re-review");
    expect(historyEntryText({ action: "removed", line_label: "4 × Projector", from_status: "pending", to_status: "released" }))
      .toBe("Removed by the coordinator · 4 × Projector · Pending → Removed");
    expect(historyEntryText({ action: "something_new", line_label: null, from_status: "a", to_status: "b" }))
      .toBe("something_new · a → b");
  });

  it("an entry without an actor was the system", () => {
    expect(historyActor({ actor_name: null })).toBe("System");
    expect(historyActor({ actor_name: "Tan Wei" })).toBe("Tan Wei");
  });
});

describe("D70 why a line is under re-review", () => {
  const entry = (overrides) => ({
    action: "edited", request_id: "l1", from_status: "reserved", to_status: "re_review",
    detail: "Quantity: 2 → 4.", created_at: "2026-10-26T02:00:00Z", ...overrides,
  });

  it("takes the newest entry that put this line under re-review", () => {
    const history = [
      entry({ action: "reserved", to_status: "reserved", detail: null }),
      entry({ detail: "Quantity: 4 → 5." }),
      entry({ action: "sent_for_re_review", detail: null }),
    ];

    expect(reReviewCause("l1", history)).toEqual({ action: "edited", detail: "Quantity: 4 → 5." });
  });

  it("ignores other lines and entries that didn't put it there", () => {
    const history = [
      entry({ request_id: "l2" }),
      entry({ action: "note_updated", from_status: null, to_status: null }),
    ];

    expect(reReviewCause("l1", history)).toBeNull();
    expect(reReviewCause("l1", [])).toBeNull();
  });

  it.each([
    [{ action: "edited", detail: "Quantity: 2 → 4." }, "The coordinator changed this line. Quantity: 2 → 4."],
    [{ action: "edited", detail: null }, "The coordinator changed this line."],
    [{ action: "sent_for_re_review", detail: null }, "The coordinator sent this line for re-review after an approved change to the event."],
    [{ action: "sent_for_re_review", detail: "Check the bigger room" }, "The coordinator sent this line for re-review after an approved change to the event. Note: Check the bigger room"],
    [{ action: "re_review", detail: "Event time changed; 1 free for 3." }, "The event's time changed and this no longer fits."],
    [null, "This line needs re-review."],
  ])("says why: %j", (cause, expected) => {
    expect(reReviewText(cause)).toBe(expected);
  });
});
