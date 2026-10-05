// SCRUM-45 equipment request rules (REQUIREMENTS §6.15). The API is the enforcement
// point (equipment/service.py, public.submit_equipment_request); these only avoid
// offering a submission that would fail, and show the EQ-R1 inventory warning.

// Mirrors the API's TECHNICAL_REQUIREMENTS_MAX_LENGTH.
export const TECHNICAL_REQUIREMENTS_MAX_LENGTH = 1000;

// The full §6.15 line lifecycle; SCRUM-45 only creates `pending` lines.
export const REQUEST_STATUS_LABELS = {
  pending: "Pending",
  reserved: "Reserved",
  rejected: "Rejected",
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
