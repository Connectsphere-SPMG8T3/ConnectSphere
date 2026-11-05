import { describe, expect, it } from "vitest";

import {
  BOOKING_GROUPS,
  VENUE_PROFILE_TABS,
  countBookings,
  editFormToPayload,
  lastEditorName,
  stepIndex,
  INACTIVE_REASONS,
  formatVenuePeriod,
  inactiveReasonLabel,
  summariseEditHistoryEntry,
  formatVenueInstant,
  venueProfileTabs,
  venueSlides,
  venueToEditForm,
} from "@/features/venues/venueProfile";

const booking = (id, status, startHour) => ({
  id,
  event_id: `e${id}`,
  status,
  period: {
    starts_at: `2026-10-10T0${startHour}:00:00Z`,
    ends_at: `2026-10-10T0${startHour + 1}:00:00Z`,
  },
});

describe("lastEditorName (SCRUM-67 AC2)", () => {
  it("names the editor", () => {
    expect(lastEditorName({ id: "a1", full_name: "Val Staff" })).toBe("Val Staff");
  });

  it("falls back to a short id when the account has no name", () => {
    expect(lastEditorName({ id: "a0000000-1111-4000-8000-000000000003" })).toBe("Account A0000000");
  });

  it("reports that nothing was recorded rather than inventing an editor", () => {
    expect(lastEditorName(null)).toBe("Not recorded");
    expect(lastEditorName(undefined)).toBe("Not recorded");
  });
});

describe("venueProfileTabs", () => {
  const venue = {
    upcoming_bookings: [booking("1", "approved", 1), booking("2", "held", 2)],
    upcoming_blocks: [{ id: "c1" }],
  };

  it("returns the profile tabs in a fixed order", () => {
    expect(venueProfileTabs(venue).map((t) => t.key)).toEqual(VENUE_PROFILE_TABS.map((t) => t.key));
    expect(venueProfileTabs(venue).map((t) => t.key)).toEqual(["capacity", "facilities", "bookings", "blocks", "history"]);
  });

  it("counts what is behind the time-based tabs, so a closed tab still shows there is something in it", () => {
    const byKey = Object.fromEntries(venueProfileTabs(venue).map((t) => [t.key, t.count]));

    expect(byKey.bookings).toBe(2);
    expect(byKey.blocks).toBe(1);
  });

  it("gives the attribute tabs no count, rather than a misleading zero", () => {
    const byKey = Object.fromEntries(venueProfileTabs(venue).map((t) => [t.key, t.count]));

    expect(byKey.capacity).toBeNull();
    expect(byKey.facilities).toBeNull();
    expect(byKey.history).toBeNull();
  });

  it("counts zero for an empty venue, and tolerates a missing venue", () => {
    expect(venueProfileTabs({}).find((t) => t.key === "bookings").count).toBe(0);
    expect(venueProfileTabs().find((t) => t.key === "blocks").count).toBe(0);
  });
});

describe("stepIndex (photo carousel)", () => {
  it("moves forward and backward", () => {
    expect(stepIndex(0, 3, 1)).toBe(1);
    expect(stepIndex(2, 3, -1)).toBe(1);
  });

  it("wraps at both ends, so the carousel never dead-ends", () => {
    expect(stepIndex(2, 3, 1)).toBe(0);
    expect(stepIndex(0, 3, -1)).toBe(2);
  });

  it("stays at zero when there is nothing to show", () => {
    expect(stepIndex(0, 0, 1)).toBe(0);
    expect(stepIndex(0, 0, -1)).toBe(0);
  });

  it("handles a single photo without moving", () => {
    expect(stepIndex(0, 1, 1)).toBe(0);
  });
});

describe("venueSlides", () => {
  const venue = {
    capacity: 60,
    photos: [],
    layouts: [
      { layout: "classroom", capacity_for_layout: 40 },
      { layout: "theatre", capacity_for_layout: null },
    ],
  };

  it("turns each supported layout into a schematic slide", () => {
    const slides = venueSlides(venue);

    expect(slides.map((s) => [s.kind, s.layout, s.capacity])).toEqual([
      ["layout", "classroom", 40],
      ["layout", "theatre", 60],
    ]);
  });

  it("labels the layout as the catalogue does", () => {
    expect(venueSlides(venue)[0].label).toBe("Classroom");
  });

  it("flags when the figure is the venue capacity rather than a per-layout one (VS-R6)", () => {
    const [classroom, theatre] = venueSlides(venue);

    expect(classroom.usesVenueCapacity).toBe(false);
    expect(theatre.usesVenueCapacity).toBe(true);
  });

  it("leads with real photos once they exist, keeping the schematics after them", () => {
    const slides = venueSlides({ ...venue, photos: [{ url: "a.jpg", caption: "From the stage" }] });

    expect(slides.map((s) => s.kind)).toEqual(["photo", "layout", "layout"]);
    expect(slides[0]).toMatchObject({ url: "a.jpg", caption: "From the stage" });
  });

  it("returns nothing when the venue records neither photos nor layouts", () => {
    expect(venueSlides({ capacity: 60, photos: [], layouts: [] })).toEqual([]);
    expect(venueSlides()).toEqual([]);
  });

  it("gives every slide a stable unique key", () => {
    const keys = venueSlides(venue).map((s) => s.key);

    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe("venueToEditForm / editFormToPayload (SCRUM-63)", () => {
  const venue = {
    name: "Hall A",
    location: "Bukit Timah Campus",
    capacity: 150,
    layouts: [
      { layout: "theatre", capacity_for_layout: null },
      { layout: "banquet", capacity_for_layout: 100 },
    ],
    facilities: ["projector"],
    accessibility_features: ["wheelchair_access"],
    opens_at: "08:00:00",
    closes_at: "22:00:00",
    description: "The main hall.",
  };

  it("builds a form the edit view can bind to directly", () => {
    const form = venueToEditForm(venue);

    expect(form.selectedLayouts).toEqual(["theatre", "banquet"]);
    expect(form.layoutCapacities).toEqual({ theatre: "", banquet: "100" });
    expect(form.opensAt).toBe("08:00");
    expect(form.closesAt).toBe("22:00");
  });

  it("round-trips back into the API's PATCH shape", () => {
    const payload = editFormToPayload(venueToEditForm(venue));

    expect(payload).toEqual({
      name: "Hall A",
      location: "Bukit Timah Campus",
      capacity: 150,
      layouts: [
        { layout: "theatre", capacity_for_layout: null },
        { layout: "banquet", capacity_for_layout: 100 },
      ],
      facilities: ["projector"],
      accessibility_features: ["wheelchair_access"],
      opens_at: "08:00:00",
      closes_at: "22:00:00",
      description: "The main hall.",
      setup_minutes: 0,
      turnaround_minutes: 0,
      emergency_access: null,
      restrictions: null,
      confirm: false,
    });
  });

  it("sends confirm:true once the caller has seen the warnings", () => {
    const payload = editFormToPayload(venueToEditForm(venue), { confirm: true });
    expect(payload.confirm).toBe(true);
  });

  it("trims text fields and sends null for an emptied description", () => {
    const form = venueToEditForm({ ...venue, description: null });
    form.name = "  Hall A  ";
    form.description = "   ";

    const payload = editFormToPayload(form);

    expect(payload.name).toBe("Hall A");
    expect(payload.description).toBeNull();
  });

  it("handles a venue with no layouts or facilities recorded", () => {
    const form = venueToEditForm({ ...venue, layouts: [], facilities: [], accessibility_features: [] });
    expect(editFormToPayload(form).layouts).toEqual([]);
  });
});

describe("CR-100 venue buffers and safety details", () => {
  it("loads defaults and safety details into the existing edit form", () => {
    const form = venueToEditForm({ setup_minutes: 30, turnaround_minutes: 45,
      emergency_access: "East exit", restrictions: "No flames" });
    expect(form).toMatchObject({ setupMinutes: "30", turnaroundMinutes: "45",
      emergencyAccess: "East exit", restrictions: "No flames" });
    expect(venueToEditForm(null)).toMatchObject({ setupMinutes: "0", turnaroundMinutes: "0",
      emergencyAccess: "", restrictions: "" });
  });

  it("sends numeric buffers and trimmed safety text, including cleared fields", () => {
    const form = { ...venueToEditForm(null), setupMinutes: "0", turnaroundMinutes: "2147483647",
      emergencyAccess: "  East exit\nCourtyard  ", restrictions: "   " };
    expect(editFormToPayload(form)).toMatchObject({ setup_minutes: 0, turnaround_minutes: 2147483647,
      emergency_access: "East exit\nCourtyard", restrictions: null });
  });

  it.each(["", " ", "abc", "-1", "1.5", "0x10", "1e3", "2147483648"])("rejects invalid minutes %j before sending", (value) => {
    for (const field of ["setupMinutes", "turnaroundMinutes"]) {
      expect(() => editFormToPayload({ ...venueToEditForm(null), [field]: value })).toThrow(/whole number/);
    }
  });

  it("includes buffers and cleared safety facts in the visible history", () => {
    expect(summariseEditHistoryEntry({ before: { setup_minutes: 0, restrictions: "No flames" },
      after: { setup_minutes: 30, restrictions: null } })).toEqual([
      { field: "setup_minutes", label: "Default setup (minutes)", before: "0", after: "30" },
      { field: "restrictions", label: "Restrictions", before: "No flames", after: "None recorded" },
    ]);
  });
});

describe("summariseEditHistoryEntry (SCRUM-63, VC-R3)", () => {
  it("reads a block's history row as one added block (SCRUM-51 AC9)", () => {
    const entry = {
      before: {},
      after: { block: { starts_at: "2031-05-20T01:00:00+00:00", ends_at: "2031-05-20T09:00:00+00:00",
        reason: "equipment_failure", notes: "Projector down" } },
    };

    expect(summariseEditHistoryEntry(entry)).toEqual([{
      field: "block",
      label: "Block added",
      before: "None",
      after: "20 May 2031, 09:00 – 20 May 2031, 17:00 · Equipment failure · Projector down",
    }]);
  });

  it("leaves out a missing block detail", () => {
    const entry = { before: {}, after: { block: { starts_at: "2031-05-20T01:00:00Z", ends_at: "2031-05-20T09:00:00Z",
      reason: "safety", notes: null } } };
    expect(summariseEditHistoryEntry(entry)[0].after).toBe("20 May 2031, 09:00 – 20 May 2031, 17:00 · Safety");
  });

  it("reports only the fields that actually changed", () => {
    const entry = {
      before: { capacity: 150, name: "Hall A", facilities: ["projector"] },
      after: { capacity: 100, name: "Hall A", facilities: ["projector"] },
    };

    const diff = summariseEditHistoryEntry(entry);

    expect(diff).toEqual([{ field: "capacity", label: "Capacity", before: "150", after: "100" }]);
  });

  it("formats layouts and facilities as readable lists", () => {
    const entry = {
      before: { layouts: [] },
      after: { layouts: [{ layout: "theatre", capacity_for_layout: 100 }] },
    };

    const diff = summariseEditHistoryEntry(entry);

    expect(diff).toEqual([{ field: "layouts", label: "Layouts", before: "None", after: "Theatre (100)" }]);
  });

  it("reports nothing when nothing changed", () => {
    const entry = { before: { capacity: 150 }, after: { capacity: 150 } };
    expect(summariseEditHistoryEntry(entry)).toEqual([]);
  });
});

describe("summariseEditHistoryEntry: deactivation (SCRUM-64)", () => {
  it("summarises a deactivation entry", () => {
    const diff = summariseEditHistoryEntry({
      before: { is_active: true, inactive_reason: null, inactive_note: null },
      after: { is_active: false, inactive_reason: "long_term_renovation", inactive_note: "Roof works" },
    });
    expect(diff).toEqual([
      { field: "is_active", label: "Status", before: "Active", after: "Inactive" },
      { field: "inactive_reason", label: "Inactive reason", before: "None recorded", after: "Long-term renovation" },
      { field: "inactive_note", label: "Inactive note", before: "None recorded", after: "Roof works" },
    ]);
  });
});

describe("inactiveReasonLabel (SCRUM-64)", () => {
  it("labels known reasons and passes unknown ones through", () => {
    expect(INACTIVE_REASONS.map((r) => inactiveReasonLabel(r.value))).toEqual(["Permanently closed", "Long-term renovation", "Other"]);
    expect(inactiveReasonLabel("mystery")).toBe("mystery");
  });
});

describe("formatVenuePeriod", () => {
  it("formats both ends in Singapore time", () => {
    expect(
      formatVenuePeriod({ starts_at: "2031-05-20T06:00:00Z", ends_at: "2031-05-20T09:00:00Z" }),
    ).toBe("20 May 2031, 14:00 – 20 May 2031, 17:00");
  });
});

describe("countBookings", () => {
  it("counts bookings in the singular for one and the plural otherwise", () => {
    expect(countBookings(1)).toBe("1 booking");
    expect(countBookings(2)).toBe("2 bookings");
    expect(countBookings(0)).toBe("0 bookings");
  });
});

describe("a block change in the venue history (SCRUM-54 AC4)", () => {
  const before = { block: { starts_at: "2031-05-20T01:00:00+00:00", ends_at: "2031-05-20T09:00:00+00:00",
    reason: "maintenance", notes: "Aircon" } };

  it("reads an ended-early block as the original period and the new one, with the note", () => {
    const entry = { before, after: { block: { ...before.block, ends_at: "2031-05-20T04:00:00+00:00",
      status: "ended_early", note: "Fixed early" } } };

    expect(summariseEditHistoryEntry(entry)).toEqual([{
      field: "block",
      label: "Block ended early",
      before: "20 May 2031, 09:00 – 20 May 2031, 17:00 · Maintenance · Aircon",
      after: "20 May 2031, 09:00 – 20 May 2031, 12:00 · Maintenance · Aircon · Note: Fixed early",
    }]);
  });

  it("reads a removed block as removed, with no period after", () => {
    const entry = { before, after: { block: { ...before.block, ends_at: null, status: "removed", note: null } } };

    expect(summariseEditHistoryEntry(entry)[0]).toMatchObject({ label: "Block removed", after: "Removed" });
  });

  it("adds the note to a removal", () => {
    const entry = { before, after: { block: { ...before.block, ends_at: null, status: "removed", note: "Cancelled" } } };
    expect(summariseEditHistoryEntry(entry)[0].after).toBe("Removed · Note: Cancelled");
  });
});

describe("formatVenueInstant", () => {
  it("shows one instant in Singapore time", () => {
    expect(formatVenueInstant("2031-04-30T02:30:00Z")).toBe("30 Apr 2031, 10:30");
  });
});

describe("edit history of a list that wasn't stored as one", () => {
  it.each([
    ["facilities", "Facilities"],
    ["accessibility_features", "Accessibility"],
  ])("reads %s as empty rather than failing", (field) => {
    const [change] = summariseEditHistoryEntry({ before: { [field]: "not a list" }, after: { [field]: ["other"] } });

    expect(change.before).toBe("None");
    expect(change.after).toBe("other");
  });
});
