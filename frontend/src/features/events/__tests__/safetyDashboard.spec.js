// CR-103 AC7: the Safety Officer dashboard's figures, counted from complete lists.
import { describe, expect, it } from "vitest";
import { outcomeCounts, queueSummary } from "../safetyDashboard";

const NOW = new Date("2026-10-09T12:00:00Z");
const waitingSince = (entered_review_at) => ({ event_id: entered_review_at, entered_review_at });

describe("queueSummary", () => {
  it("says nobody is waiting when the queue is empty", () => {
    expect(queueSummary([], NOW)).toEqual({ waiting: 0, oldestWaitLabel: "—" });
  });

  it("counts the queue and measures the oldest entry, whatever the order", () => {
    const queue = [waitingSince("2026-10-09T09:00:00Z"), waitingSince("2026-10-06T11:00:00Z")];
    expect(queueSummary(queue, NOW)).toEqual({ waiting: 2, oldestWaitLabel: "3 days" });
  });

  it.each([
    ["2026-10-09T11:30:00Z", "Under an hour"],
    ["2026-10-09T11:00:00Z", "1 hour"],
    ["2026-10-09T01:00:00Z", "11 hours"],
    ["2026-10-08T12:00:00Z", "1 day"],
    ["2026-10-07T11:00:00Z", "2 days"],
  ])("labels a wait that began at %s as %s", (enteredAt, label) => {
    expect(queueSummary([waitingSince(enteredAt)], NOW).oldestWaitLabel).toBe(label);
  });
});

describe("outcomeCounts", () => {
  it("is all zeros with no decisions", () => {
    expect(outcomeCounts([])).toEqual({ approved: 0, changesRequested: 0, arrangementRejected: 0 });
  });

  it("counts each officer outcome and leaves system withdrawals out", () => {
    const history = ["approved", "approved", "changes_requested", "arrangement_rejected", "withdrawn"]
      .map((decision) => ({ decision }));
    expect(outcomeCounts(history)).toEqual({ approved: 2, changesRequested: 1, arrangementRejected: 1 });
  });
});
