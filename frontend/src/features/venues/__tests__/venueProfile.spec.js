import { describe, expect, it } from "vitest";

import {
  BOOKING_GROUPS,
  VENUE_PROFILE_TABS,
  defaultBookingGroupKey,
  editFormToPayload,
  formatTurnaround,
  groupUpcomingBookings,
  lastEditorName,
  stepIndex,
  INACTIVE_REASONS,
  inactiveReasonLabel,
  summariseEditHistoryEntry,
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

describe("groupUpcomingBookings (SCRUM-67 AC3)", () => {
  it("splits occupying bookings into confirmed, tentative and re-review", () => {
    const groups = groupUpcomingBookings([
      booking("1", "held", 1),
      booking("2", "approved", 2),
      booking("3", "re_review", 3),
      booking("4", "approved", 4),
    ]);

    expect(groups.map((g) => [g.key, g.bookings.map((b) => b.id)])).toEqual([
      ["confirmed", ["2", "4"]],
      ["tentative", ["1"]],
      ["reReview", ["3"]],
    ]);
  });

  it("orders each group soonest first, whatever order the API sent", () => {
    const groups = groupUpcomingBookings([booking("late", "approved", 8), booking("early", "approved", 2)]);

    expect(groups[0].bookings.map((b) => b.id)).toEqual(["early", "late"]);
  });

  it("returns every group even when empty, so the profile can say 'none'", () => {
    const groups = groupUpcomingBookings([]);

    expect(groups).toHaveLength(BOOKING_GROUPS.length);
    expect(groups.every((g) => g.bookings.length === 0)).toBe(true);
  });

  it("tolerates a missing list", () => {
    expect(groupUpcomingBookings().every((g) => g.bookings.length === 0)).toBe(true);
  });

  it("never silently drops a booking whose status it does not recognise", () => {
    const groups = groupUpcomingBookings([booking("1", "approved", 1), booking("9", "invented", 2)]);
    const shown = groups.flatMap((g) => g.bookings.map((b) => b.id));

    expect(shown).toContain("9");
  });
});

describe("formatTurnaround (QA-28)", () => {
  it("says back-to-back is allowed when the buffer is zero", () => {
    expect(formatTurnaround(0)).toBe("None — bookings may run back to back");
  });

  it("words a real buffer in hours and minutes", () => {
    expect(formatTurnaround(30)).toBe("30 min between bookings");
    expect(formatTurnaround(60)).toBe("1 h between bookings");
    expect(formatTurnaround(90)).toBe("1 h 30 min between bookings");
  });

  it("says nothing rather than guessing when the figure is missing", () => {
    expect(formatTurnaround(null)).toBe("Not recorded");
    expect(formatTurnaround(undefined)).toBe("Not recorded");
  });
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

describe("defaultBookingGroupKey", () => {
  it("opens on the first group that actually has bookings", () => {
    const groups = groupUpcomingBookings([booking("1", "held", 1)]);

    expect(defaultBookingGroupKey(groups)).toBe("tentative");
  });

  it("prefers the earlier group when several have bookings", () => {
    const groups = groupUpcomingBookings([booking("1", "held", 1), booking("2", "approved", 2)]);

    expect(defaultBookingGroupKey(groups)).toBe("confirmed");
  });

  it("falls back to the first group when everything is empty", () => {
    expect(defaultBookingGroupKey(groupUpcomingBookings([]))).toBe("confirmed");
  });

  it("tolerates being given nothing", () => {
    expect(defaultBookingGroupKey([])).toBe(BOOKING_GROUPS[0].key);
    expect(defaultBookingGroupKey()).toBe(BOOKING_GROUPS[0].key);
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

describe("summariseEditHistoryEntry (SCRUM-63, VC-R3)", () => {
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
