import { describe, expect, it } from "vitest";

import {
  canRequestEquipment,
  canSubmit,
  duplicateEquipmentIds,
  emptyLine,
  inventoryWarning,
  quantityError,
  REQUEST_STATUS_LABELS,
  TECHNICAL_REQUIREMENTS_MAX_LENGTH,
  technicalRequirementsError,
  toPayload,
} from "@/features/equipment/equipmentRequest";

const PROJECTOR = { equipment_id: "p1", name: "Projector", equipment_type: "AV", total_quantity: 20 };

function line(overrides = {}) {
  return { ...emptyLine(), equipmentId: "p1", quantity: "4", ...overrides };
}

describe("quantityError (AC3)", () => {
  it.each(["1", "4", 1, 20, "21"])("accepts the whole number %s", (value) => {
    expect(quantityError(value)).toBeNull();
  });

  it.each(["", "  ", null, undefined])("asks for a quantity when it is empty (%s)", (value) => {
    expect(quantityError(value)).toBe("Enter a quantity.");
  });

  it.each(["0", "-1", "2.5", "1e2", "abc", 0, -3, 1.5])("refuses %s as not a whole number of at least 1", (value) => {
    expect(quantityError(value)).toBe("Quantity must be a whole number of at least 1.");
  });
});

describe("inventoryWarning (AC5, EQ-R1)", () => {
  it("warns when the quantity is above the catalogue total", () => {
    expect(inventoryWarning(PROJECTOR, "21")).toBe("Only 20 exist in the catalogue. You can still submit.");
  });

  it("says nothing at or below the total", () => {
    expect(inventoryWarning(PROJECTOR, "20")).toBe("");
    expect(inventoryWarning(PROJECTOR, "1")).toBe("");
  });

  it("says nothing until there is an item and a valid quantity", () => {
    expect(inventoryWarning(null, "50")).toBe("");
    expect(inventoryWarning(PROJECTOR, "")).toBe("");
    expect(inventoryWarning(PROJECTOR, "2.5")).toBe("");
  });

  it("never blocks submission", () => {
    expect(canSubmit([line({ quantity: "500" })])).toBe(true);
  });
});

describe("technicalRequirementsError (AC2)", () => {
  it("is optional", () => {
    expect(technicalRequirementsError("")).toBeNull();
    expect(technicalRequirementsError(undefined)).toBeNull();
  });

  it("accepts exactly the limit and refuses one more", () => {
    expect(TECHNICAL_REQUIREMENTS_MAX_LENGTH).toBe(1000);
    expect(technicalRequirementsError("x".repeat(1000))).toBeNull();
    expect(technicalRequirementsError("x".repeat(1001))).toBe("Keep it to 1000 characters.");
  });
});

describe("canSubmit (AC4)", () => {
  it("needs at least one line", () => {
    expect(canSubmit([])).toBe(false);
  });

  it("needs every line to name an item and a valid quantity", () => {
    expect(canSubmit([line()])).toBe(true);
    expect(canSubmit([line({ equipmentId: "" })])).toBe(false);
    expect(canSubmit([line(), line({ equipmentId: "m1", quantity: "0" })])).toBe(false);
    expect(canSubmit([line({ technicalRequirements: "x".repeat(1001) })])).toBe(false);
  });

  it("refuses the same item twice", () => {
    const lines = [line(), line({ quantity: "2" })];
    expect(duplicateEquipmentIds(lines)).toEqual(new Set(["p1"]));
    expect(canSubmit(lines)).toBe(false);
  });
});

describe("toPayload", () => {
  it("sends whole-number quantities and trims or drops technical requirements", () => {
    const payload = toPayload("e1", [
      line({ quantity: " 4 ", technicalRequirements: "  HDMI  " }),
      line({ equipmentId: "m1", quantity: "2", technicalRequirements: "   " }),
    ]);

    expect(payload).toEqual({
      event_id: "e1",
      items: [
        { equipment_id: "p1", quantity: 4, technical_requirements: "HDMI" },
        { equipment_id: "m1", quantity: 2, technical_requirements: null },
      ],
    });
  });
});

describe("canRequestEquipment (AC7)", () => {
  it("is open only while the event is in planning", () => {
    expect(canRequestEquipment("planning")).toBe(true);
    for (const status of ["under_review", "returned", "confirmed", "rejected", "cancelled", "completed"]) {
      expect(canRequestEquipment(status)).toBe(false);
    }
  });
});

describe("REQUEST_STATUS_LABELS (AC6)", () => {
  it("reads a pending line as Pending", () => {
    expect(REQUEST_STATUS_LABELS.pending).toBe("Pending");
  });
});
