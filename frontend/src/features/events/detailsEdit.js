// Story 112: the assigned coordinator's direct edit of an event's ordinary details.
// The API is the enforcement point (events/service.py `edit_details`); these only
// avoid offering an edit, or sending a form, that it would refuse.

export const STALE_EVENT_MESSAGE = "This event was updated by someone else. Reload.";

// Mirrors the API's `EventFields` bounds, which this edit shares with creation (AC3).
export const DETAIL_LIMITS = { nameMin: 3, nameMax: 150, purposeMax: 500, descriptionMax: 5000 };

const EDITABLE_STATUSES = ["under_review", "planning", "safety_review", "confirmed", "preparation"];

// AC1, AC6: a returned request is the organiser's to edit; terminal events are read-only.
export function canEditDetails(status) {
  return EDITABLE_STATUSES.includes(status);
}

export function isStaleMessage(message) {
  return message === STALE_EVENT_MESSAGE;
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
  const name = (form.name ?? "").trim();
  if (name.length < DETAIL_LIMITS.nameMin || name.length > DETAIL_LIMITS.nameMax) {
    errors.name = `Name must be ${DETAIL_LIMITS.nameMin} to ${DETAIL_LIMITS.nameMax} characters.`;
  }
  const purpose = (form.purpose ?? "").trim();
  if (!purpose) errors.purpose = "Purpose is required.";
  else if (purpose.length > DETAIL_LIMITS.purposeMax) {
    errors.purpose = `Purpose can be at most ${DETAIL_LIMITS.purposeMax} characters.`;
  }
  if ((form.description ?? "").trim().length > DETAIL_LIMITS.descriptionMax) {
    errors.description = `Description can be at most ${DETAIL_LIMITS.descriptionMax} characters.`;
  }
  return errors;
}
