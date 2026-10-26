import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const { registrationsApi, authStore } = vi.hoisted(() => ({
  registrationsApi: {
    directory: vi.fn(),
    event: vi.fn(),
    register: vi.fn(),
    myRegistrations: vi.fn(),
  },
  authStore: { token: "attendee-token", withSession: vi.fn((callback) => callback("attendee-token")) },
}));

vi.mock("@/services/api", () => ({ registrationsApi }));
vi.mock("@/stores/auth", () => ({ useAuthStore: () => authStore }));

import { useRegistrationStore } from "@/features/registrations/store";

describe("registration discovery store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    authStore.token = "attendee-token";
    authStore.withSession.mockImplementation((callback) => callback("attendee-token"));
  });

  it("loads the anonymous public directory", async () => {
    registrationsApi.directory.mockResolvedValue({ events: [{ id: "event-1" }] });
    const store = useRegistrationStore();

    await store.loadDirectory();

    expect(registrationsApi.directory).toHaveBeenCalledOnce();
    expect(store.events).toEqual([{ id: "event-1" }]);
  });

  it("uses an empty list when the directory response has no events", async () => {
    registrationsApi.directory.mockResolvedValue({ events: null });
    const store = useRegistrationStore();

    await store.loadDirectory();

    expect(store.events).toEqual([]);
  });

  it("shows a fallback error and clears loading when the directory request fails", async () => {
    const error = new Error("");
    registrationsApi.directory.mockRejectedValue(error);
    const store = useRegistrationStore();

    await expect(store.loadDirectory()).rejects.toBe(error);

    expect(store.error).toBe("Unable to load events. Please try again.");
    expect(store.isLoading).toBe(false);
  });

  it("shows the detail request error and clears loading when loading fails", async () => {
    const error = new Error("Event not found.");
    registrationsApi.event.mockRejectedValue(error);
    const store = useRegistrationStore();

    await expect(store.loadEvent("event-1")).rejects.toBe(error);

    expect(store.error).toBe("Event not found.");
    expect(store.isLoading).toBe(false);
  });

  it("registers with the session token and stores the immediate result", async () => {
    registrationsApi.register.mockResolvedValue({ status: "registered" });
    const store = useRegistrationStore();

    await store.register("event-1");

    expect(registrationsApi.register).toHaveBeenCalledWith("event-1", "attendee-token");
    expect(store.registrationResult).toEqual({ status: "registered" });
  });

  it("keeps a successful registration when the place-count refresh fails", async () => {
    registrationsApi.register.mockResolvedValue({ status: "registered" });
    registrationsApi.event.mockRejectedValue(new Error("Refresh failed."));
    const store = useRegistrationStore();
    store.event = { id: "event-1", registered_count: 12 };

    const result = await store.register("event-1");

    expect(result).toEqual({ status: "registered" });
    expect(store.registrationResult).toEqual({ status: "registered" });
    expect(store.event.registered_count).toBe(12);
    expect(store.error).toBe("You are registered, but the updated place count could not be loaded.");
  });

  it("marks the event full when the atomic registration rejects the final-place race", async () => {
    const store = useRegistrationStore();
    store.event = { id: "event-1", availability: "open" };
    registrationsApi.register.mockRejectedValue({ status: 409, message: "Event is full." });

    await expect(store.register("event-1")).rejects.toMatchObject({ status: 409 });

    expect(store.event.availability).toBe("full");
  });

  it("loads the signed-in attendee's registrations with the session token", async () => {
    const registrations = [{ id: "registration-1", status: "registered" }];
    registrationsApi.myRegistrations.mockResolvedValue({ registrations });
    const store = useRegistrationStore();

    await store.loadMyRegistrations();

    expect(registrationsApi.myRegistrations).toHaveBeenCalledWith("attendee-token");
    expect(store.myRegistrations).toEqual(registrations);
    expect(store.isLoadingMyRegistrations).toBe(false);
    expect(store.myRegistrationsError).toBeNull();
  });

  it("surfaces a registration-list error and clears its loading state", async () => {
    const error = new Error("Unable to load registrations.");
    registrationsApi.myRegistrations.mockRejectedValue(error);
    const store = useRegistrationStore();

    await expect(store.loadMyRegistrations()).rejects.toBe(error);

    expect(store.myRegistrationsError).toBe("Unable to load registrations.");
    expect(store.isLoadingMyRegistrations).toBe(false);
  });
});