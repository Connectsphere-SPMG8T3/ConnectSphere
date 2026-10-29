// SCRUM-33: returning a request for amendment. The fields a coordinator can flag,
// in the request form's order and wording. `value` is the API's `EventField`
// name; the list plugs straight into BauhausCheckboxGroup's `options`.
export const EVENT_FIELD_LABELS = [
  { value: "name", label: "Event title" },
  { value: "purpose", label: "Purpose" },
  { value: "description", label: "Description" },
  { value: "starts_at", label: "Proposed date and start time" },
  { value: "event_timezone", label: "Event timezone" },
  { value: "ends_at", label: "Proposed end time" },
  { value: "expected_attendance", label: "Expected attendance" },
  { value: "layout_preference", label: "Preferred layout" },
  { value: "facilities_required", label: "Facilities required" },
  { value: "accessibility_needs", label: "Accessibility needs" },
  { value: "preliminary_equipment_needs", label: "Preliminary equipment needs" },
  { value: "registration_enabled", label: "Attendee registration" },
  { value: "registration_capacity", label: "Registration capacity" },
  { value: "registration_opens_at", label: "Registration opens" },
  { value: "registration_closes_at", label: "Registration closes" },
  { value: "withdrawal_closes_at", label: "Withdrawal cutoff" },
  { value: "re_registration_allowed", label: "Re-registration after withdrawal" },
  { value: "waitlist_enabled", label: "Waitlist when full" },
];

// Mirrors the API's AMENDMENT_TEXT_MAX_LENGTH ([Assumption], REQUIREMENTS §9).
export const AMENDMENT_TEXT_MAX_LENGTH = 1000;

export const FLAG_TEXT = "Flagged by coordinator";

// The form splits the event's start and end instants into date and time inputs,
// so one API field can highlight more than one input.
const FORM_KEYS_BY_FIELD = {
  name: ["name"],
  purpose: ["purpose"],
  description: ["description"],
  starts_at: ["date", "startTime"],
  event_timezone: ["eventTimezone"],
  ends_at: ["endTime"],
  expected_attendance: ["expectedAttendance"],
  layout_preference: ["layoutPreference"],
  facilities_required: ["facilitiesRequired"],
  accessibility_needs: ["accessibilityNeeds"],
  preliminary_equipment_needs: ["preliminaryEquipmentNeeds"],
  registration_enabled: ["registrationEnabled"],
  registration_capacity: ["registrationCapacity"],
  registration_opens_at: ["registrationOpensAt"],
  registration_closes_at: ["registrationClosesAt"],
  withdrawal_closes_at: ["withdrawalClosesAt"],
  re_registration_allowed: ["reRegistrationAllowed"],
  waitlist_enabled: ["waitlistEnabled"],
};

export function fieldLabel(field) {
  return EVENT_FIELD_LABELS.find((option) => option.value === field)?.label ?? String(field).replaceAll("_", " ");
}

export function flaggedFormKeys(flaggedFields) {
  return new Set((flaggedFields ?? []).flatMap((field) => FORM_KEYS_BY_FIELD[field] ?? []));
}
