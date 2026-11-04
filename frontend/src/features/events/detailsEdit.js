// Story 112: the assigned coordinator's direct edit of an event's ordinary details.
// The API is the enforcement point (events/service.py `edit_details`, schemas.py
// `EventDetailsEdit`); these only avoid offering an edit, or sending a form, that it would refuse.
import { eventDescriptionError, eventNameError, eventPurposeError } from "@/features/events/eventTextRules";

const EDITABLE_STATUSES = ["under_review", "planning", "safety_review", "confirmed", "preparation"];

// AC1, AC6: a returned request is the organiser's to edit; terminal events are read-only.
export function canEditDetails(status) {
  return EDITABLE_STATUSES.includes(status);
}

const FIELDS = ["name", "purpose", "description", "accessibility_needs"];
// Name and purpose stay required once a request is submitted; the other two can be cleared.
const REQUIRED = ["name", "purpose"];

export function detailsFormFrom(event) {
  return Object.fromEntries(FIELDS.map((field) => [field, event?.[field] ?? ""]));
}

/** The fields whose trimmed text differs from the event's, as the API takes them. */
export function changedDetails(event, form) {
  const changes = {};
  for (const field of FIELDS) {
    const next = (form[field] ?? "").trim();
    const before = (event?.[field] ?? "").trim();
    if (next === before) continue;
    // A cleared optional field is null; a cleared required one goes as "" so the API names it.
    changes[field] = next === "" && !REQUIRED.includes(field) ? null : next;
  }
  return changes;
}

/** `{field: message}` for every field the API would refuse, so all show together (AC3). */
export function detailsFormErrors(form) {
  const errors = {};
  const name = eventNameError(form.name);
  if (name) errors.name = name;
  const purpose = eventPurposeError(form.purpose);
  if (purpose) errors.purpose = purpose;
  const description = eventDescriptionError(form.description);
  if (description) errors.description = description;
  return errors;
}
