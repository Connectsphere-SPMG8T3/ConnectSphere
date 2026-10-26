// SCRUM-45 equipment request rules (REQUIREMENTS §6.15). The API is the enforcement
// point (equipment/service.py, public.submit_equipment_request); these only avoid
// offering a submission that would fail, and show the EQ-R1 inventory warning.

// Mirrors the API's TECHNICAL_REQUIREMENTS_MAX_LENGTH.
export const TECHNICAL_REQUIREMENTS_MAX_LENGTH = 1000;

// The full §6.15 line lifecycle. AC9 (SCRUM-24): `rejected` reads "Not available".
export const REQUEST_STATUS_LABELS = {
  pending: "Pending",
  reserved: "Reserved",
  rejected: "Not available",
  re_review: "Re-review",
  released: "Released",
};

const WHOLE_NUMBER = /^\d+$/;

export function emptyLine() {
  return { equipmentId: "", quantity: "", technicalRequirements: "" };
}

// QA-22: equipment is requested once the event is in planning.
export function canRequestEquipment(status) {
  return status === "planning";
}

function parseQuantity(value) {
  const text = String(value ?? "").trim();
  return WHOLE_NUMBER.test(text) ? Number(text) : null;
}

export function quantityError(value) {
  if (String(value ?? "").trim() === "") return "Enter a quantity.";
  const quantity = parseQuantity(value);
  if (quantity === null || quantity < 1) return "Quantity must be a whole number of at least 1.";
  return null;
}

// EQ-R1: above the total inventory is a warning, never a block. Window-specific
// availability is tech support's check (§6.16).
export function inventoryWarning(catalogueItem, quantity) {
  if (!catalogueItem || quantityError(quantity)) return "";
  const total = catalogueItem.total_quantity;
  return parseQuantity(quantity) > total ? `Only ${total} exist in the catalogue. You can still submit.` : "";
}

export function technicalRequirementsError(text) {
  return (text ?? "").trim().length > TECHNICAL_REQUIREMENTS_MAX_LENGTH
    ? `Keep it to ${TECHNICAL_REQUIREMENTS_MAX_LENGTH} characters.`
    : null;
}

// [Assumption] REQUIREMENTS §9: one line per item in a submission.
export function duplicateEquipmentIds(lines) {
  const seen = new Set();
  const duplicates = new Set();
  for (const { equipmentId } of lines) {
    if (!equipmentId) continue;
    if (seen.has(equipmentId)) duplicates.add(equipmentId);
    seen.add(equipmentId);
  }
  return duplicates;
}

export function canSubmit(lines) {
  if (!lines.length || duplicateEquipmentIds(lines).size) return false;
  return lines.every(
    (line) => line.equipmentId && !quantityError(line.quantity) && !technicalRequirementsError(line.technicalRequirements),
  );
}

export function toPayload(eventId, lines) {
  return {
    event_id: eventId,
    items: lines.map((line) => ({
      equipment_id: line.equipmentId,
      quantity: parseQuantity(line.quantity),
      technical_requirements: (line.technicalRequirements ?? "").trim() || null,
    })),
  };
}

// --- SCRUM-44: changing or removing a recorded line --------------------------
// The API decides; these offer the actions only where they can succeed and say
// what each will do before the coordinator commits to it.

const RE_REVIEW_NOTICE = "Technical Support will re-check this line. Its reservation is kept until they re-approve or reject it.";

const CHANGE_NOTICES = {
  pending: "",
  reserved: RE_REVIEW_NOTICE,
  re_review: RE_REVIEW_NOTICE,
  rejected: "The line goes back to Pending and Technical Support are told.",
};

const REMOVE_NOTICES = {
  pending: "It leaves the request. Technical Support haven't acted on it yet.",
  reserved: "Its reservation is released and Technical Support are told.",
  re_review: "Its reservation is released and Technical Support are told.",
  rejected: "It leaves the request. It was marked Not available, so nothing is held.",
};

// AC1, AC2, AC4: any line still on the request, while the event is in planning.
export function canChangeLine(eventStatus, lineStatus) {
  return eventStatus === "planning" && lineStatus in CHANGE_NOTICES;
}

// A removed line is kept as released for the history (AC8), not listed.
export function liveLines(lines) {
  return lines.filter((line) => line.status !== "released");
}

export function lineToDraft(line) {
  return {
    equipmentId: line.equipment_id,
    quantity: String(line.quantity),
    technicalRequirements: line.technical_requirements ?? "",
  };
}

export function canSaveLine(draft) {
  return canSubmit([draft]);
}

// AC6: the status the coordinator saw goes with the change, so a reservation
// that landed first refuses it.
export function toLineUpdate(draft, expectedStatus) {
  const [item] = toPayload(null, [draft]).items;
  return { ...item, expected_status: expectedStatus };
}

export function changeNotice(lineStatus) {
  return CHANGE_NOTICES[lineStatus] ?? "";
}

export function removeNotice(lineStatus) {
  return REMOVE_NOTICES[lineStatus] ?? "";
}
