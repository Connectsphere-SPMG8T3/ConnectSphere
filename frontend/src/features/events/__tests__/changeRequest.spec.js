import { describe, expect, it } from "vitest";

import { canRequestChange, describeChanges, diffProposal, hasChanges } from "@/features/events/changeRequest";

const BEFORE = {
  event: {
    name: "Partner Summit",
    description: null,
    starts_at: "2026-11-12T10:00:00+08:00",
    expected_attendance: 80,
    facilities_required: ["projector", "microphone"],
  },
  spaces: [{ id: "s1", label: "Main hall", expected_pax: 80, layout_preference: "theatre", facilities_required: ["projector"] }],
};

function copy(value) {
  return JSON.parse(JSON.stringify(value));
}

describe("diffProposal (story 32)", () => {
  it("proposes only the event and space fields that changed", () => {
    const after = copy(BEFORE);
    after.event.expected_attendance = 120;
    after.spaces[0].layout_preference = "banquet";

    expect(diffProposal(BEFORE, after)).toEqual({
      event: { expected_attendance: 120 },
      spaces: [{ id: "s1", layout_preference: "banquet" }],
    });
  });

  it("ignores values that only look different (Q10)", () => {
    const after = copy(BEFORE);
    after.event.facilities_required = ["microphone", "projector"];
    after.event.description = "   ";
    after.event.starts_at = "2026-11-12T02:00:00.000Z";

    expect(diffProposal(BEFORE, after)).toEqual({ event: {}, spaces: [] });
    expect(hasChanges(diffProposal(BEFORE, after))).toBe(false);
  });

  it("sends a cleared field as null", () => {
    const before = copy(BEFORE);
    before.event.description = "Two keynotes";
    const after = copy(before);
    after.event.description = null;

    expect(diffProposal(before, after).event).toEqual({ description: null });
  });

  it("reports a proposal with any change as having changes", () => {
    expect(hasChanges({ event: {}, spaces: [{ id: "s1", label: "Grand hall" }] })).toBe(true);
    expect(hasChanges({ event: { name: "New" }, spaces: [] })).toBe(true);
  });
});

describe("canRequestChange (CR-R15)", () => {
  const future = "2026-11-12T10:00:00+08:00";
  const now = new Date("2026-10-24T09:00:00Z");

  it.each(["submitted", "under_review", "planning", "safety_review", "confirmed", "preparation"])(
    "offers a change request on a %s event that hasn't started",
    (status) => {
      expect(canRequestChange({ status, starts_at: future }, now)).toBe(true);
    },
  );

  it.each(["draft", "returned", "rejected", "cancelled", "completed"])("doesn't offer one on a %s event", (status) => {
    expect(canRequestChange({ status, starts_at: future }, now)).toBe(false);
  });

  it("doesn't offer one once the event has started", () => {
    expect(canRequestChange({ status: "preparation", starts_at: "2026-10-24T08:00:00Z" }, now)).toBe(false);
  });

  it("doesn't offer one while a change or cancellation request is open (CR-R14)", () => {
    expect(canRequestChange({ status: "planning", starts_at: future, open_change_request: { id: "r1" } }, now)).toBe(false);
    expect(canRequestChange({ status: "planning", starts_at: future, open_cancellation_request: { id: "r2" } }, now)).toBe(false);
  });
});

describe("describeChanges", () => {
  it("labels each change with the form's wording, spaces under their name", () => {
    const changes = {
      event: [{ field: "expected_attendance", before: 80, after: 120 }],
      spaces: [{ space_id: "s1", label: "Main hall", fields: [{ field: "layout_preference", before: "theatre", after: "banquet" }] }],
    };

    expect(describeChanges(changes)).toEqual([
      { key: "event:expected_attendance", label: "Expected attendance", before: "80", after: "120" },
      { key: "s1:layout_preference", label: "Main hall: layout", before: "theatre", after: "banquet" },
    ]);
  });

  it("shows empty values, lists and switches in words", () => {
    const changes = {
      event: [
        { field: "description", before: null, after: "Two keynotes" },
        { field: "waitlist_enabled", before: true, after: false },
      ],
      spaces: [{ space_id: "s1", label: "Main hall", fields: [{ field: "facilities_required", before: [], after: ["projector", "stage"] }] }],
    };

    expect(describeChanges(changes).map(({ before, after }) => [before, after])).toEqual([
      ["(none)", "Two keynotes"],
      ["Yes", "No"],
      ["(none)", "projector, stage"],
    ]);
  });

  it("is empty for a request without changes", () => {
    expect(describeChanges(null)).toEqual([]);
  });
});
