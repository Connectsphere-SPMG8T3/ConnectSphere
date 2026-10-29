import { describe, expect, it } from "vitest";

import {
  canChangeLine,
  canRequestEquipment,
  canSaveLine,
  canSubmit,
  changeNotice,
  duplicateEquipmentIds,
  emptyLine,
  inventoryWarning,
  lineToDraft,
  liveLines,
  quantityError,
  removeNotice,
  REQUEST_STATUS_LABELS,
  TECHNICAL_REQUIREMENTS_MAX_LENGTH,
  technicalRequirementsError,
  toLineUpdate,
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

describe("SCRUM-44 changing or removing a recorded line", () => {
  const LINE = {
    id: "l1", equipment_id: "p1", equipment_name: "Projector", quantity: 4,
    technical_requirements: "HDMI", status: "reserved",
  };

  it.each([
    ["planning", "pending", true],
    ["planning", "reserved", true],
    ["planning", "re_review", true],
    ["planning", "rejected", true],
    ["planning", "released", false],
    ["safety_review", "pending", false],
    ["confirmed", "reserved", false],
    ["returned", "pending", false],
  ])("an event in %s offers a %s line for change: %s (AC1, AC2, AC4)", (eventStatus, lineStatus, expected) => {
    expect(canChangeLine(eventStatus, lineStatus)).toBe(expected);
  });

  it("starts the edit form from the line as recorded", () => {
    expect(lineToDraft(LINE)).toEqual({ equipmentId: "p1", quantity: "4", technicalRequirements: "HDMI" });
    expect(lineToDraft({ ...LINE, technical_requirements: null }).technicalRequirements).toBe("");
  });

  it("saves only a complete, valid line (AC2)", () => {
    expect(canSaveLine(lineToDraft(LINE))).toBe(true);
    expect(canSaveLine({ ...lineToDraft(LINE), equipmentId: "" })).toBe(false);
    expect(canSaveLine({ ...lineToDraft(LINE), quantity: "0" })).toBe(false);
    expect(canSaveLine({ ...lineToDraft(LINE), quantity: "1.5" })).toBe(false);
    expect(canSaveLine({ ...lineToDraft(LINE), technicalRequirements: "x".repeat(1001) })).toBe(false);
    expect(canSaveLine({ ...lineToDraft(LINE), quantity: "500" })).toBe(true);
  });

  it("sends the new values with the status the coordinator saw (AC6)", () => {
    expect(toLineUpdate({ equipmentId: "m1", quantity: " 6 ", technicalRequirements: "  " }, "reserved")).toEqual({
      equipment_id: "m1", quantity: 6, technical_requirements: null, expected_status: "reserved",
    });
    expect(toLineUpdate({ equipmentId: "m1", quantity: "2", technicalRequirements: " VGA " }, "pending")
      .technical_requirements).toBe("VGA");
  });

  it.each([
    ["pending", ""],
    ["reserved", "Technical Support will re-check this line. Its reservation is kept until they re-approve or reject it."],
    ["re_review", "Technical Support will re-check this line. Its reservation is kept until they re-approve or reject it."],
    ["rejected", "The line goes back to Pending and Technical Support are told."],
  ])("says what saving a %s line does (AC3)", (status, expected) => {
    expect(changeNotice(status)).toBe(expected);
  });

  it.each([
    ["pending", "It leaves the request. Technical Support haven't acted on it yet."],
    ["reserved", "Its reservation is released and Technical Support are told."],
    ["re_review", "Its reservation is released and Technical Support are told."],
    ["rejected", "It leaves the request. It was marked Not available, so nothing is held."],
  ])("says what removing a %s line does (AC1)", (status, expected) => {
    expect(removeNotice(status)).toBe(expected);
  });

  it("lists only lines still on the request; removed ones stay in the history (AC8)", () => {
    expect(liveLines([LINE, { ...LINE, id: "l2", status: "released" }]).map((l) => l.id)).toEqual(["l1"]);
  });
});
