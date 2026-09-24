import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { emptyEvent, eventToPayload, useEventsStore } from "@/stores/events";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), submit: vi.fn(), resubmit: vi.fn() },
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
      layout_preference: "theatre",
      facilities_required: ["projector"],
      registration_enabled: false,
      registration_opens_at: "2026-09-20T02:00:00.000Z",
      registration_closes_at: "2026-10-09T11:00:00.000Z",
    });
  });

  it("creates a draft through the authenticated session", async () => {
    const store = signedInStore();
    const event = { ...emptyEvent(), name: "Planning workshop" };
    eventsApi.create.mockResolvedValue({ id: "e1", status: "draft", name: event.name });

    const result = await store.saveDraft(event);

    expect(eventsApi.create).toHaveBeenCalledWith({ name: event.name, event_timezone: "Asia/Singapore", facilities_required: [], registration_enabled: false }, "access");
    expect(result.id).toBe("e1");
    expect(store.events).toEqual([result]);
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
      { name: event.name, event_timezone: "Asia/Singapore", facilities_required: [], registration_enabled: false },
      "access",
    );
    expect(eventsApi.submit).toHaveBeenCalledWith(
      "e1",
      { name: event.name, event_timezone: "Asia/Singapore", facilities_required: [], registration_enabled: false },
      "access",
    );
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
      "e1", { ...eventToPayload(form), resubmission_note: "Attendance is now 40" }, "access",
    );
    expect(result.status).toBe("under_review");
    expect(store.events.find((event) => event.id === "e1").status).toBe("under_review");
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
      expect.objectContaining({ name: "Updated workshop", facilities_required: [] }),
      "access",
    );
  });
});
