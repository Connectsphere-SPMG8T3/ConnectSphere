import { describe, expect, it } from "vitest";

import { reasonLabel, suitabilityBadge } from "@/features/venues/suitability";

// SCRUM-18 AC6, AC7: the three verdicts and the plain wording of each finding.
describe("suitabilityBadge", () => {
  it("names the three verdicts", () => {
    expect(suitabilityBadge({ verdict: "suitable", reasons: [] }).text).toBe("Suitable");
    expect(suitabilityBadge({ verdict: "suitable_with_warnings", reasons: [] }).text).toBe("Suitable with warnings");
    expect(suitabilityBadge({ verdict: "unsuitable", reasons: [] }).text).toBe("Unsuitable");
  });

  it("gives each verdict its own look so warnings are not mistaken for a pass", () => {
    const classes = ["suitable", "suitable_with_warnings", "unsuitable"].map(
      (verdict) => suitabilityBadge({ verdict, reasons: [] }).classes,
    );
    expect(new Set(classes).size).toBe(3);
  });

  it("is null when the search named no event", () => {
    expect(suitabilityBadge(null)).toBeNull();
    expect(suitabilityBadge(undefined)).toBeNull();
  });
});

describe("reasonLabel", () => {
  it("tells a failed rule from a warning", () => {
    expect(reasonLabel({ severity: "unsuitable" })).toBe("Fails");
    expect(reasonLabel({ severity: "warning" })).toBe("Warning");
  });
});
