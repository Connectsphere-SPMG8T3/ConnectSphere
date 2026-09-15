import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { emptyEvent, eventToPayload, useEventsStore } from "@/stores/events";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), submit: vi.fn() },
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

  it("builds a Singapore-time request payload and omits empty optional values", () => {
    const event = {
      ...emptyEvent(),
      name: "Planning workshop",
      purpose: "Coordinate teams",
      date: "2026-10-10",
      startTime: "14:00",
      endTime: "17:00",
      expectedAttendance: "150",
      layoutPreference: "theatre",
      facilitiesRequired: ["projector"],
    };

    expect(eventToPayload(event)).toEqual({
      name: "Planning workshop",
      purpose: "Coordinate teams",
      starts_at: "2026-10-10T14:00:00+08:00",
      ends_at: "2026-10-10T17:00:00+08:00",
      expected_attendance: 150,
      layout_preference: "theatre",
      facilities_required: ["projector"],
      registration_enabled: false,
    });
  });

  it("creates a draft through the authenticated session", async () => {
    const store = signedInStore();
    const event = { ...emptyEvent(), name: "Planning workshop" };
    eventsApi.create.mockResolvedValue({ id: "e1", status: "draft", name: event.name });

    const result = await store.saveDraft(event);

    expect(eventsApi.create).toHaveBeenCalledWith({ name: event.name, facilities_required: [], registration_enabled: false }, "access");
    expect(result.id).toBe("e1");
    expect(store.events).toEqual([result]);
  });

  it("keeps the form error when submission is rejected", async () => {
    const store = signedInStore();
    eventsApi.submit.mockRejectedValue(new ApiError("Purpose is required.", 422));

    await expect(store.submit("e1", { ...emptyEvent(), name: "Planning workshop" })).rejects.toThrow();

    expect(store.error).toBe("Purpose is required.");
    expect(store.isSaving).toBe(false);
  });
});
