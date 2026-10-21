import { describe, expect, it } from "vitest";

import { COORDINATOR_PROGRESS_STEPS, statusProgress } from "@/features/events/statusProgress";

const states = (progress) => progress.steps.map((step) => step.state);

describe("statusProgress", () => {
  it("follows the coordinator's part of the lifecycle, in order", () => {
    expect(COORDINATOR_PROGRESS_STEPS).toEqual(["under_review", "planning", "safety_review", "confirmed", "completed"]);
    expect(statusProgress("under_review").steps.map((step) => step.label))
      .toEqual(["Under review", "Planning", "Safety review", "Confirmed", "Completed"]);
  });

  it.each([
    ["under_review", ["current", "upcoming", "upcoming", "upcoming", "upcoming"]],
    ["planning", ["done", "current", "upcoming", "upcoming", "upcoming"]],
    ["safety_review", ["done", "done", "current", "upcoming", "upcoming"]],
    ["confirmed", ["done", "done", "done", "current", "upcoming"]],
  ])("marks earlier steps done and later ones upcoming at %s", (status, expected) => {
    const progress = statusProgress(status);
    expect(progress.kind).toBe("on-track");
    expect(states(progress)).toEqual(expected);
  });

  it("marks every step done once the event is completed", () => {
    expect(states(statusProgress("completed"))).toEqual(["done", "done", "done", "done", "done"]);
  });

  it("shows a returned request as held at Under review, with the returned label", () => {
    const progress = statusProgress("returned");
    expect(progress.kind).toBe("returned");
    expect(states(progress)).toEqual(["returned", "upcoming", "upcoming", "upcoming", "upcoming"]);
    expect(progress.steps[0].label).toBe("Returned for amendment");
  });

  it.each(["rejected", "cancelled"])("has no position on the bar when %s, only the outcome", (status) => {
    const progress = statusProgress(status);
    expect(progress.kind).toBe("ended");
    expect(progress.steps).toEqual([]);
    expect(progress.label).toBe(status === "rejected" ? "Rejected" : "Cancelled");
  });

  it("falls back to the raw status when it is unknown", () => {
    expect(statusProgress("something_new")).toEqual({ kind: "ended", steps: [], label: "something_new" });
  });
});
