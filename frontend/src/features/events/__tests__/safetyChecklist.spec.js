// CR-108 AC1-AC3: the safety checklist's marks, completeness and outcome rules.
import { describe, expect, it } from "vitest";
import {
  SAFETY_FACTORS, SAFETY_RATINGS, VENUE_FACTORS, buildChecklist, canApprove, factorLabel, hasConcern,
  markKey, missingMarks, ratingLabel,
} from "../safetyChecklist";

const A = "booking-a";
const B = "booking-b";

function fullMarks(bookings, rating = "satisfactory") {
  const marks = {};
  for (const booking of bookings) {
    for (const factor of VENUE_FACTORS) marks[markKey(factor, booking)] = { rating, note: "" };
  }
  marks[markKey("equipment_placement", null)] = { rating, note: "" };
  return marks;
}

describe("the six factors (AC1)", () => {
  it("lists attendance/capacity, layout, emergency access, accessibility, equipment placement and venue restrictions", () => {
    expect(SAFETY_FACTORS.map((f) => f.label)).toEqual([
      "Attendance/capacity", "Layout", "Emergency access", "Accessibility", "Equipment placement", "Venue restrictions",
    ]);
  });

  it("answers five of them per venue and equipment placement once for the event (AC2)", () => {
    expect(VENUE_FACTORS).toEqual(["attendance_capacity", "layout", "emergency_access", "accessibility", "venue_restrictions"]);
    expect(SAFETY_FACTORS.filter((f) => f.scope === "event").map((f) => f.value)).toEqual(["equipment_placement"]);
  });

  it("offers Satisfactory, Concern and Not applicable", () => {
    expect(SAFETY_RATINGS.map((r) => r.label)).toEqual(["Satisfactory", "Concern", "Not applicable"]);
  });

  it("names a factor and a rating, and shows an unknown one as given", () => {
    expect(factorLabel("emergency_access")).toBe("Emergency access");
    expect(ratingLabel("not_applicable")).toBe("Not applicable");
    expect(factorLabel("other")).toBe("other");
    expect(ratingLabel("other")).toBe("other");
  });
});

describe("markKey", () => {
  it("is per booking for a venue factor and per event for equipment placement", () => {
    expect(markKey("layout", A)).not.toBe(markKey("layout", B));
    expect(markKey("equipment_placement", null)).toBe(markKey("equipment_placement", undefined));
  });
});

describe("missingMarks (AC3)", () => {
  it("names every mark when nothing is marked: five per venue plus equipment placement", () => {
    expect(missingMarks({}, [A, B])).toHaveLength(11);
  });

  it("names the venue factor and its booking", () => {
    const marks = fullMarks([A, B]);
    delete marks[markKey("layout", B)];
    expect(missingMarks(marks, [A, B])).toEqual([{ factor: "layout", bookingId: B }]);
  });

  it("treats a mark with no rating as missing, even when it has a note", () => {
    const marks = fullMarks([A]);
    marks[markKey("accessibility", A)] = { rating: null, note: "Ramp is steep" };
    expect(missingMarks(marks, [A])).toEqual([{ factor: "accessibility", bookingId: A }]);
  });

  it("needs only equipment placement when the event has no venue yet", () => {
    expect(missingMarks({}, [])).toEqual([{ factor: "equipment_placement", bookingId: null }]);
  });

  it("is empty when everything is marked", () => {
    expect(missingMarks(fullMarks([A, B]), [A, B])).toEqual([]);
  });
});

describe("hasConcern and canApprove (AC3, team decision: a Concern blocks approval)", () => {
  it("allows approval when every factor is marked without a concern, including Not applicable", () => {
    expect(canApprove(fullMarks([A], "satisfactory"), [A])).toBe(true);
    expect(canApprove(fullMarks([A], "not_applicable"), [A])).toBe(true);
  });

  it("blocks approval while any factor is a Concern", () => {
    const marks = fullMarks([A, B]);
    marks[markKey("venue_restrictions", B)] = { rating: "concern", note: "Open flames planned" };
    expect(hasConcern(marks)).toBe(true);
    expect(canApprove(marks, [A, B])).toBe(false);
  });

  it("blocks approval while the checklist is incomplete", () => {
    expect(canApprove({}, [A])).toBe(false);
  });

  it("ignores marks for a venue that is no longer on the review", () => {
    const marks = fullMarks([A]);
    marks[markKey("layout", B)] = { rating: "concern", note: "" };
    expect(hasConcern(marks, [A])).toBe(false);
    expect(canApprove(marks, [A])).toBe(true);
  });
});

describe("buildChecklist", () => {
  it("sends one row per mark, with the booking for a venue factor and none for equipment placement", () => {
    const marks = fullMarks([A]);
    marks[markKey("layout", A)] = { rating: "concern", note: "  Aisle too narrow  " };
    const rows = buildChecklist(marks, [A]);
    expect(rows).toHaveLength(6);
    expect(rows).toContainEqual({ factor: "layout", booking_id: A, rating: "concern", note: "Aisle too narrow" });
    expect(rows).toContainEqual({ factor: "equipment_placement", booking_id: null, rating: "satisfactory", note: null });
  });

  it("sends a blank note as no note", () => {
    const marks = fullMarks([A]);
    marks[markKey("layout", A)] = { rating: "concern", note: "   " };
    expect(buildChecklist(marks, [A]).find((r) => r.factor === "layout").note).toBeNull();
  });

  it("leaves out an unmarked factor rather than guessing a rating", () => {
    expect(buildChecklist({}, [A])).toEqual([]);
  });

  it("does not send marks for a venue that is not on the review", () => {
    const marks = fullMarks([A, B]);
    expect(buildChecklist(marks, [A]).some((r) => r.booking_id === B)).toBe(false);
  });
});
