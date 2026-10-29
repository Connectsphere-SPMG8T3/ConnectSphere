import { describe, expect, it } from "vitest";

import { isOpenForPreparation, preparationStageLabel } from "@/features/equipment/preparation";

describe("technical preparation helpers (CR-110)", () => {
  it("labels each stage, and no stage as Not started", () => {
    expect(preparationStageLabel("in_preparation")).toBe("In preparation");
    expect(preparationStageLabel(null)).toBe("Not started");
    expect(preparationStageLabel(undefined)).toBe("Not started");
  });

  it("shows an unknown stage as sent rather than hiding it", () => {
    expect(preparationStageLabel("paused")).toBe("paused");
  });

  it("opens only for Confirmed and Preparation (AC1)", () => {
    expect(["confirmed", "preparation"].every(isOpenForPreparation)).toBe(true);
    expect(["planning", "safety_review", "completed", "cancelled"].some(isOpenForPreparation)).toBe(false);
  });
});
