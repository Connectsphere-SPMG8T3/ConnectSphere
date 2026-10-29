import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const { registrationsApi, authStore } = vi.hoisted(() => ({
  registrationsApi: {
    directory: vi.fn(),
    event: vi.fn(),
    register: vi.fn(),
    withdraw: vi.fn(),
    myRegistrations: vi.fn(),
    acceptInvitation: vi.fn(),
    leaveWaitlist: vi.fn(),
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

  it("withdraws a registration, removes it from My events, and refreshes public availability", async () => {
    const remaining = [{ id: "registration-2", event: { id: "event-2" } }];
    registrationsApi.withdraw.mockResolvedValue({ status: "withdrawn" });
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: remaining });
    registrationsApi.directory.mockResolvedValue({ events: [{ id: "event-1", registered_count: 4 }] });
    const store = useRegistrationStore();
    store.myRegistrations = [
      { id: "registration-1", event: { id: "event-1" } },
      ...remaining,
    ];

    const result = await store.withdraw("event-1");

    expect(registrationsApi.withdraw).toHaveBeenCalledWith("event-1", "attendee-token");
    expect(registrationsApi.myRegistrations).toHaveBeenCalledWith("attendee-token");
    expect(registrationsApi.directory).toHaveBeenCalledOnce();
    expect(result).toEqual({ status: "withdrawn" });
    expect(store.myRegistrations).toEqual(remaining);
    expect(store.events).toEqual([{ id: "event-1", registered_count: 4 }]);
  });

  it("keeps a successful withdrawal when refreshing event data fails", async () => {
    registrationsApi.withdraw.mockResolvedValue({ status: "withdrawn" });
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [] });
    registrationsApi.directory.mockRejectedValue(new Error("Directory refresh failed."));
    const store = useRegistrationStore();
    store.myRegistrations = [{ id: "registration-1", event: { id: "event-1" } }];

    const result = await store.withdraw("event-1");

    expect(result).toEqual({ status: "withdrawn" });
    expect(store.myRegistrations).toEqual([]);
    expect(store.error).toContain("Registration was withdrawn, but updated event data could not be loaded:");
    expect(store.error).toContain("Directory refresh failed.");
  });

  it("asks the attendee to refresh when withdrawal refresh fails without a message", async () => {
    registrationsApi.withdraw.mockResolvedValue({ status: "withdrawn" });
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [] });
    registrationsApi.directory.mockRejectedValue(new Error(""));
    const store = useRegistrationStore();

    await store.withdraw("event-1");

    expect(store.error).toContain("Please refresh and try again.");
  });

  it("keeps the registration when the withdrawal request fails", async () => {
    const registration = { id: "registration-1", event: { id: "event-1" } };
    registrationsApi.withdraw.mockRejectedValue(new Error("The withdrawal cutoff has passed."));
    const store = useRegistrationStore();
    store.myRegistrations = [registration];

    await expect(store.withdraw("event-1")).rejects.toThrow("The withdrawal cutoff has passed.");

    expect(store.myRegistrations).toEqual([registration]);
    expect(registrationsApi.myRegistrations).not.toHaveBeenCalled();
    expect(registrationsApi.directory).not.toHaveBeenCalled();
  });

  it("surfaces a registration-list error and clears its loading state", async () => {
    const error = new Error("Unable to load registrations.");
    registrationsApi.myRegistrations.mockRejectedValue(error);
    const store = useRegistrationStore();

    await expect(store.loadMyRegistrations()).rejects.toBe(error);

    expect(store.myRegistrationsError).toBe("Unable to load registrations.");
    expect(store.isLoadingMyRegistrations).toBe(false);
  });

  it("accepts an invitation with the attendee session and refreshes registrations", async () => {
    registrationsApi.acceptInvitation.mockResolvedValue({ status: "registered" });
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [{ id: "registration-1", status: "registered" }] });
    const store = useRegistrationStore();

    await store.acceptInvitation("registration-1");

    expect(registrationsApi.acceptInvitation).toHaveBeenCalledWith("registration-1", "attendee-token");
    expect(store.myRegistrations).toEqual([{ id: "registration-1", status: "registered" }]);
  });

  it("leaves a waitlist with the attendee session and refreshes registrations", async () => {
    registrationsApi.leaveWaitlist.mockResolvedValue(null);
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [] });
    const store = useRegistrationStore();

    await store.leaveWaitlist("registration-1");

    expect(registrationsApi.leaveWaitlist).toHaveBeenCalledWith("registration-1", "attendee-token");
    expect(store.myRegistrations).toEqual([]);
  });
});