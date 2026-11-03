import { describe, expect, it } from "vitest";

import { canEditDetails, changedDetails, detailsFormErrors, detailsFormFrom } from "@/features/events/detailsEdit";

const EVENT = {
  id: "e1", version: 4, name: "Partner Summit", purpose: "Quarterly meeting",
  description: null, accessibility_needs: "Step-free access",
};

describe("canEditDetails (story 112 AC1, AC6)", () => {
  it.each(["under_review", "planning", "safety_review", "confirmed", "preparation"])("is offered in %s", (status) => {
    expect(canEditDetails(status)).toBe(true);
  });

  it.each(["draft", "submitted", "returned", "rejected", "cancelled", "completed", undefined, null])(
    "is not offered in %s",
    (status) => {
      expect(canEditDetails(status)).toBe(false);
    },
  );
});

describe("detailsFormFrom", () => {
  it("starts from the event's four ordinary fields, with blanks as empty text", () => {
    expect(detailsFormFrom(EVENT)).toEqual({
      name: "Partner Summit", purpose: "Quarterly meeting", description: "", accessibility_needs: "Step-free access",
    });
  });
});

describe("changedDetails", () => {
  it("is empty when nothing changed, even if only whitespace differs", () => {
    const form = { ...detailsFormFrom(EVENT), name: "  Partner Summit  ", description: "   " };
    expect(changedDetails(EVENT, form)).toEqual({});
  });

  it("holds only the changed fields, trimmed", () => {
    const form = { ...detailsFormFrom(EVENT), name: "  Partner Summit 2027 ", description: "Agreed offline" };
    expect(changedDetails(EVENT, form)).toEqual({ name: "Partner Summit 2027", description: "Agreed offline" });
  });

  it("sends a cleared optional field as null", () => {
    const form = { ...detailsFormFrom(EVENT), accessibility_needs: "  " };
    expect(changedDetails(EVENT, form)).toEqual({ accessibility_needs: null });
  });

  it("sends a cleared required field as an empty string, so the API refuses it by name", () => {
    const form = { ...detailsFormFrom(EVENT), purpose: "" };
    expect(changedDetails(EVENT, form)).toEqual({ purpose: "" });
  });
});

describe("detailsFormErrors", () => {
  const ok = detailsFormFrom(EVENT);

  it("has none for a valid form", () => {
    expect(detailsFormErrors(ok)).toEqual({});
  });

  it("says what the organiser's form says (the shared rules)", () => {
    expect(detailsFormErrors({ ...ok, name: "" }).name).toBe("Enter an event title.");
    expect(detailsFormErrors({ ...ok, name: "ab" }).name).toBe("Use at least 3 characters.");
    expect(detailsFormErrors({ ...ok, purpose: " " }).purpose).toBe("Enter the event purpose.");
    expect(detailsFormErrors({ ...ok, description: "d".repeat(5001) }).description).toBe("Use at most 5000 characters.");
  });

  it("leaves accessibility notes optional and unbounded", () => {
    expect(detailsFormErrors({ ...ok, accessibility_needs: "" })).toEqual({});
    expect(detailsFormErrors({ ...ok, accessibility_needs: "a".repeat(10000) })).toEqual({});
  });

  it("reports every error together (AC3)", () => {
    const errors = detailsFormErrors({ ...ok, name: "ab", purpose: "", description: "d".repeat(5001) });
    expect(Object.keys(errors).sort()).toEqual(["description", "name", "purpose"]);
  });
});
