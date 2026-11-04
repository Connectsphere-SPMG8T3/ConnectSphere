// What an event's title, purpose and description must look like, and what to say when they
// don't. The organiser's request form and the coordinator's edit dialog (story 112) both use
// these, so the two always say the same thing. The API is the enforcement point: the bounds
// mirror its `EventName`, `EventPurpose` and `EventDescription` (events/schemas.py).

export const EVENT_TEXT_LIMITS = { nameMin: 3, nameMax: 150, purposeMax: 500, descriptionMax: 5000 };

/** "" when the title is fine, otherwise what to tell the person. */
export function eventNameError(value) {
  const name = (value ?? "").trim();
  if (!name) return "Enter an event title.";
  if (name.length < EVENT_TEXT_LIMITS.nameMin) return `Use at least ${EVENT_TEXT_LIMITS.nameMin} characters.`;
  if (name.length > EVENT_TEXT_LIMITS.nameMax) return `Use at most ${EVENT_TEXT_LIMITS.nameMax} characters.`;
  return "";
}

/** A purpose is required once a request is submitted (the organiser's form only asks on submit). */
export function eventPurposeError(value) {
  const purpose = (value ?? "").trim();
  if (!purpose) return "Enter the event purpose.";
  if (purpose.length > EVENT_TEXT_LIMITS.purposeMax) return `Use at most ${EVENT_TEXT_LIMITS.purposeMax} characters.`;
  return "";
}

export function eventDescriptionError(value) {
  if ((value ?? "").trim().length > EVENT_TEXT_LIMITS.descriptionMax) {
    return `Use at most ${EVENT_TEXT_LIMITS.descriptionMax} characters.`;
  }
  return "";
}
