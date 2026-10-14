import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { emptyEvent, emptySpace, eventToPayload, spaceToPayload, useEventsStore } from "@/stores/events";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), submit: vi.fn(), resubmit: vi.fn(), clone: vi.fn(), createSpace: vi.fn(), updateSpace: vi.fn(), removeSpace: vi.fn() },
}));

function signedInStore() {
  setActivePinia(createPinia());
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = { id: "u1", role: "event_organiser" };
  return useEventsStore();
}

describe("event store", () => {
  beforeEach(() => vi.clearAllMocks());

  it("builds a request payload in the event timezone and omits empty optional values", () => {
    const event = {
      ...emptyEvent(),
      name: "Planning workshop",
      eventTimezone: "Asia/Bangkok",
      purpose: "Coordinate teams",
      date: "2026-10-10",
      startTime: "14:00",
      endTime: "17:00",
      expectedAttendance: "150",
      layoutPreference: "theatre",
      facilitiesRequired: ["projector"],
      registrationOpensAt: "2026-09-20T09:00",
      registrationClosesAt: "2026-10-09T18:00",
    };

    expect(eventToPayload(event)).toEqual({
      name: "Planning workshop",
      event_timezone: "Asia/Bangkok",
      purpose: "Coordinate teams",
      starts_at: "2026-10-10T07:00:00.000Z",
      ends_at: "2026-10-10T10:00:00.000Z",
      expected_attendance: 150,
      registration_enabled: false,
      registration_opens_at: "2026-09-20T02:00:00.000Z",
      registration_closes_at: "2026-10-09T11:00:00.000Z",
    });
  });

  it("sends null for cleared optional fields when editing an existing event, so the API clears them", () => {
    const event = { ...emptyEvent(), name: "Planning workshop", expectedAttendance: "", accessibilityNeeds: "  " };

    const payload = eventToPayload(event, { clearing: true });

    expect(payload).toMatchObject({
      purpose: null,
      description: null,
      expected_attendance: null,
      accessibility_needs: null,
      preliminary_equipment_needs: null,
      registration_capacity: null,
      registration_opens_at: null,
      registration_closes_at: null,
    });
    // The pair is constrained to be both set or both empty, and required to submit,
    // so an incomplete time is left out rather than half-cleared.
    expect(payload).not.toHaveProperty("starts_at");
    expect(payload).not.toHaveProperty("ends_at");
  });

  it("creates a draft through the authenticated session", async () => {
    const store = signedInStore();
    const event = { ...emptyEvent(), name: "Planning workshop" };
    eventsApi.create.mockResolvedValue({ id: "e1", status: "draft", name: event.name });

    const result = await store.saveDraft(event);

    expect(eventsApi.create).toHaveBeenCalledWith({ name: event.name, event_timezone: "Asia/Singapore", registration_enabled: false }, "access");
    expect(result.id).toBe("e1");
    expect(store.events).toEqual([result]);
  });

  it("clones an event through the authenticated session and stores the new draft", async () => {
    const store = signedInStore();
    eventsApi.clone.mockResolvedValue({
      id: "e2",
      status: "draft",
      name: "Planning workshop",
      event_timezone: "Asia/Singapore",
      facilities_required: [],
      registration_enabled: false,
    });

    const result = await store.clone("e1");

    expect(eventsApi.clone).toHaveBeenCalledWith("e1", "access");
    expect(result).toMatchObject({ id: "e2", status: "draft", name: "Planning workshop" });
    expect(store.events).toEqual([result]);
  });

  it("keeps the clone failure and clears saving state", async () => {
    const store = signedInStore();
    eventsApi.clone.mockRejectedValue(new ApiError("Event not found.", 404));

    await expect(store.clone("missing-event")).rejects.toThrow("Event not found.");

    expect(store.error).toBe("Event not found.");
    expect(store.isSaving).toBe(false);
    expect(store.events).toEqual([]);
  });

  it("loads one event request through the authenticated session", async () => {
    const store = signedInStore();
    eventsApi.get.mockResolvedValue({
      id: "e1",
      status: "under_review",
      name: "Planning workshop",
      event_timezone: "Asia/Bangkok",
      starts_at: "2026-10-10T07:00:00Z",
      ends_at: "2026-10-10T10:00:00Z",
      facilities_required: [],
      registration_enabled: false,
    });

    const result = await store.get("e1");

    expect(eventsApi.get).toHaveBeenCalledWith("e1", "access");
    expect(result).toMatchObject({ id: "e1", status: "under_review", eventTimezone: "Asia/Bangkok", date: "2026-10-10", startTime: "14:00", endTime: "17:00" });
  });

  it("creates and submits a new event request", async () => {
    const store = signedInStore();
    const event = { ...emptyEvent(), name: "Planning workshop" };
    eventsApi.create.mockResolvedValue({ id: "e1", status: "draft", name: event.name });
    eventsApi.submit.mockResolvedValue({ id: "e1", status: "under_review", name: event.name });

    const result = await store.createAndSubmit(event);

    expect(eventsApi.create).toHaveBeenCalledWith(
      { name: event.name, event_timezone: "Asia/Singapore", registration_enabled: false },
      "access",
    );
    // Submitting edits the draft the create call just made, so empty fields go as null.
    expect(eventsApi.submit).toHaveBeenCalledWith("e1", eventToPayload(event, { clearing: true }), "access");
    expect(result.status).toBe("under_review");
  });

  it("keeps the form error when submission is rejected", async () => {
    const store = signedInStore();
    eventsApi.submit.mockRejectedValue(new ApiError("Purpose is required.", 422));

    await expect(store.submit("e1", { ...emptyEvent(), name: "Planning workshop" })).rejects.toThrow();

    expect(store.error).toBe("Purpose is required.");
    expect(store.isSaving).toBe(false);
  });

  it("resubmits a returned request with the form's fields and a trimmed note (SCRUM-33)", async () => {
    const store = signedInStore();
    eventsApi.resubmit.mockResolvedValue({ id: "e1", name: "Planning workshop", status: "under_review", amendment: null });
    const form = { ...emptyEvent(), name: "Planning workshop", expectedAttendance: "40" };

    const result = await store.resubmit("e1", form, "  Attendance is now 40  ");

    expect(eventsApi.resubmit).toHaveBeenCalledWith(
      "e1", { ...eventToPayload(form, { clearing: true }), resubmission_note: "Attendance is now 40" }, "access",
    );
    expect(result.status).toBe("under_review");
    expect(store.events.find((event) => event.id === "e1").status).toBe("under_review");
  });

  it("clears a field the organiser emptied when resubmitting (SCRUM-33 AC3)", async () => {
    const store = signedInStore();
    eventsApi.resubmit.mockResolvedValue({ id: "e1", name: "Planning workshop", status: "under_review", amendment: null });
    const form = { ...emptyEvent(), name: "Planning workshop", preliminaryEquipmentNeeds: "" };

    await store.resubmit("e1", form, "Removed the equipment note");

    expect(eventsApi.resubmit.mock.calls[0][1].preliminary_equipment_needs).toBeNull();
  });

  it("clears a field the organiser emptied when saving changes", async () => {
    const store = signedInStore();
    eventsApi.update.mockResolvedValue({ id: "e1", name: "Planning workshop", status: "returned" });

    await store.updateDraft("e1", { ...emptyEvent(), name: "Planning workshop", description: "" });

    expect(eventsApi.update.mock.calls[0][1].description).toBeNull();
  });

  it("keeps the API's error when a resubmission is refused", async () => {
    const store = signedInStore();
    eventsApi.resubmit.mockRejectedValue(new ApiError("Cannot resubmit an event that is under review", 409));

    await expect(store.resubmit("e1", { ...emptyEvent(), name: "Planning workshop" }, "note")).rejects.toThrow();

    expect(store.error).toBe("Cannot resubmit an event that is under review");
    expect(store.isSaving).toBe(false);
  });

  it("normalizes nullable draft fields before updating the draft", async () => {
    const store = signedInStore();
    eventsApi.list.mockResolvedValue([
      {
        id: "e1",
        status: "draft",
        name: "Planning workshop",
        purpose: null,
        description: null,
        starts_at: null,
        ends_at: null,
        expected_attendance: null,
        layout_preference: null,
        facilities_required: null,
        accessibility_needs: null,
        preliminary_equipment_needs: null,
        registration_enabled: false,
        registration_capacity: null,
        registration_opens_at: null,
        registration_closes_at: null,
      },
    ]);
    eventsApi.update.mockResolvedValue({
      id: "e1",
      status: "draft",
      name: "Updated workshop",
      purpose: null,
      description: null,
        starts_at: null,
      ends_at: null,
      expected_attendance: null,
      layout_preference: null,
      facilities_required: [],
      registration_enabled: false,
    });

    await store.load();
    const draft = store.events[0];

    await expect(store.updateDraft("e1", { ...draft, name: "Updated workshop" })).resolves.toMatchObject({
      id: "e1",
      name: "Updated workshop",
      purpose: "",
      description: "",
      facilitiesRequired: [],
    });
    expect(eventsApi.update).toHaveBeenCalledWith(
      "e1",
      expect.objectContaining({ name: "Updated workshop" }),
      "access",
    );
  });

  it("creates and serializes a venue requirement space", () => {
    expect(emptySpace()).toEqual({
      id: null,
      version: 1,
      label: "",
      expectedPax: "",
      layoutPreference: "",
      facilitiesRequired: [],
      useEventSchedule: true,
      startsAt: "",
      endsAt: "",
    });
    expect(spaceToPayload({
      label: "  Main venue  ",
      expectedPax: "120",
      layoutPreference: "theatre",
      facilitiesRequired: ["projector"],
    })).toEqual({
      label: "Main venue",
      expected_pax: 120,
      layout_preference: "theatre",
      facilities_required: ["projector"],
      starts_at: null,
      ends_at: null,
    });
  });

  it("serializes a custom space window in the event timezone", () => {
    expect(spaceToPayload({
      label: "Breakout",
      expectedPax: "40",
      layoutPreference: "classroom",
      facilitiesRequired: [],
      useEventSchedule: false,
      startsAt: "2026-10-20T17:00",
      endsAt: "2026-10-20T19:00",
    }, "Asia/Singapore")).toMatchObject({
      starts_at: "2026-10-20T09:00:00.000Z",
      ends_at: "2026-10-20T11:00:00.000Z",
    });
  });

  it("normalizes spaces from an event response including nullable legacy fields", async () => {
    const store = signedInStore();
    eventsApi.get.mockResolvedValue({
      id: "e1",
      status: "draft",
      name: "Planning workshop",
      spaces: [
        { id: "s1", event_id: "e1", label: "Main venue", expected_pax: 120, layout_preference: "theatre", facilities_required: ["projector"], version: 2 },
        { id: "s2", event_id: "e1", label: "Breakout", expected_pax: null, layout_preference: null, facilities_required: null },
      ],
    });

    const result = await store.get("e1");

    expect(result.spaces).toEqual([
      { ...emptySpace(), id: "s1", event_id: "e1", label: "Main venue", expected_pax: 120, layout_preference: "theatre", facilities_required: ["projector"], version: 2, expectedPax: 120, layoutPreference: "theatre", facilitiesRequired: ["projector"] },
      { ...emptySpace(), id: "s2", event_id: "e1", label: "Breakout", expected_pax: null, layout_preference: null, facilities_required: null, expectedPax: "", layoutPreference: "", facilitiesRequired: [] },
    ]);
  });

  it("creates, updates and removes space requests with the active session", async () => {
    const store = signedInStore();
    eventsApi.createSpace.mockResolvedValue({ id: "s1" });
    eventsApi.updateSpace.mockResolvedValue({ id: "s1", version: 2 });
    eventsApi.removeSpace.mockResolvedValue(undefined);

    await store.createSpace("e1", { label: "Main venue" });
    await store.updateSpace("e1", "s1", { label: "Updated venue", version: 1 });
    await store.removeSpace("e1", "s1");

    expect(eventsApi.createSpace).toHaveBeenCalledWith("e1", { label: "Main venue" }, "access");
    expect(eventsApi.updateSpace).toHaveBeenCalledWith("e1", "s1", { label: "Updated venue", version: 1 }, "access");
    expect(eventsApi.removeSpace).toHaveBeenCalledWith("e1", "s1", "access");
  });

  it("stores and rethrows a space CRUD refusal", async () => {
    const store = signedInStore();
    eventsApi.removeSpace.mockRejectedValue(new ApiError("The event space was changed by another request.", 409));

    await expect(store.removeSpace("e1", "s1")).rejects.toThrow("The event space was changed by another request.");

    expect(store.error).toBe("The event space was changed by another request.");
  });
});
