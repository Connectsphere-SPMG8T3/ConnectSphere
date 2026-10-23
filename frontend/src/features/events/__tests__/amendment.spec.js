import { describe, expect, it } from "vitest";

import { AMENDMENT_TEXT_MAX_LENGTH, EVENT_FIELD_LABELS, FLAG_TEXT, fieldLabel, flaggedFormKeys } from "@/features/events/amendment";

describe("amendment field labels (SCRUM-33)", () => {
  it("offers exactly the fields the API accepts, each once", () => {
    const values = EVENT_FIELD_LABELS.map((option) => option.value);

    expect(values).toEqual([
      "name", "purpose", "description", "starts_at", "event_timezone", "ends_at",
      "expected_attendance", "layout_preference", "facilities_required", "accessibility_needs",
      "preliminary_equipment_needs", "registration_enabled", "registration_capacity",
      "registration_opens_at", "registration_closes_at", "re_registration_allowed", "waitlist_enabled",
    ]);
    expect(new Set(values).size).toBe(values.length);
  });

  it("labels a field with the request form's own wording", () => {
    expect(fieldLabel("expected_attendance")).toBe("Expected attendance");
    expect(fieldLabel("starts_at")).toBe("Proposed date and start time");
  });

  it("falls back to a readable label for a field this client doesn't know", () => {
    expect(fieldLabel("venue_notes")).toBe("venue notes");
  });

  it("maps a flagged date/time field onto every input that edits it", () => {
    expect([...flaggedFormKeys(["starts_at"])]).toEqual(["date", "startTime"]);
    expect([...flaggedFormKeys(["ends_at", "expected_attendance"])]).toEqual(["endTime", "expectedAttendance"]);
  });

  it("ignores unknown or missing flags rather than failing", () => {
    expect(flaggedFormKeys(["venue_notes"]).size).toBe(0);
    expect(flaggedFormKeys().size).toBe(0);
    expect(flaggedFormKeys(null).size).toBe(0);
  });

  it("mirrors the API's limits and wording", () => {
    expect(AMENDMENT_TEXT_MAX_LENGTH).toBe(1000);
    expect(FLAG_TEXT).toBe("Flagged by coordinator");
  });
});
