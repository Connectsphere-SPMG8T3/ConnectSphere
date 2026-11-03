import { describe, expect, it } from "vitest";

import {
  DETAIL_LIMITS,
  STALE_EVENT_MESSAGE,
  canEditDetails,
  changedDetails,
  detailsFormFrom,
  detailsFormErrors,
  isStaleMessage,
} from "@/features/events/detailsEdit";

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

describe("detailsFormErrors (the bounds the API enforces)", () => {
  const ok = detailsFormFrom(EVENT);

  it("has none for a valid form", () => {
    expect(detailsFormErrors(ok)).toEqual({});
  });

  it.each([["ab", true], ["abc", false], ["a".repeat(150), false], ["a".repeat(151), true], ["   ", true]])(
    "name %j is an error: %s", (name, isError) => {
      expect("name" in detailsFormErrors({ ...ok, name })).toBe(isError);
    },
  );

  it("requires a purpose and caps it at 500", () => {
    expect("purpose" in detailsFormErrors({ ...ok, purpose: " " })).toBe(true);
    expect("purpose" in detailsFormErrors({ ...ok, purpose: "p".repeat(500) })).toBe(false);
    expect("purpose" in detailsFormErrors({ ...ok, purpose: "p".repeat(501) })).toBe(true);
  });

  it("caps the description at 5000 and leaves accessibility notes optional", () => {
    expect("description" in detailsFormErrors({ ...ok, description: "d".repeat(5000) })).toBe(false);
    expect("description" in detailsFormErrors({ ...ok, description: "d".repeat(5001) })).toBe(true);
    expect(detailsFormErrors({ ...ok, accessibility_needs: "" })).toEqual({});
  });

  it("reports every error together (AC3)", () => {
    const errors = detailsFormErrors({ ...ok, name: "ab", purpose: "", description: "d".repeat(5001) });
    expect(Object.keys(errors).sort()).toEqual(["description", "name", "purpose"]);
  });

  it("exposes the limits for the form's counters", () => {
    expect(DETAIL_LIMITS).toEqual({ nameMin: 3, nameMax: 150, purposeMax: 500, descriptionMax: 5000 });
  });
});

describe("isStaleMessage (AC4)", () => {
  it("recognises the API's stale-version message", () => {
    expect(STALE_EVENT_MESSAGE).toBe("This event was updated by someone else. Reload.");
    expect(isStaleMessage(STALE_EVENT_MESSAGE)).toBe(true);
    expect(isStaleMessage("Significant changes go through a change request.")).toBe(false);
    expect(isStaleMessage(null)).toBe(false);
  });
});
