import { createPinia, setActivePinia } from "pinia";
import { createApp, h, nextTick } from "vue";
import { RouterView } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { authApi, registrationsApi } = vi.hoisted(() => ({
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  registrationsApi: { directory: vi.fn(), event: vi.fn(), register: vi.fn(), withdraw: vi.fn(), myRegistrations: vi.fn() },
}));

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi,
  registrationsApi,
}));

const mountedApps = [];

async function mountAt(path) {
  const pinia = createPinia();
  setActivePinia(pinia);
  vi.resetModules();
  const { useAuthStore } = await import("@/stores/auth");
  const auth = useAuthStore();
  auth.token = "attendee-token";
  auth.refreshToken = "refresh-token";
  auth.profile = { id: "attendee-1", role: "attendee", roles: ["attendee"] };
  auth.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push(path);
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(RouterView) }).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await nextTick();
  return { el, router };
}

const registration = (eventId, eventOverrides = {}) => ({
  id: `registration-${eventId}`,
  status: "registered",
  event: {
    id: eventId,
    name: "Completed Design Forum",
    description: "An attendee-only historical event detail.",
    starts_at: "2026-10-20T01:00:00Z",
    ends_at: "2026-10-20T04:00:00Z",
    event_timezone: "Asia/Singapore",
    status: "completed",
    venues: [{ id: "venue-1", name: "Central Hall" }],
    ...eventOverrides,
  },
});

describe("Attendee registered event details", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    localStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  it("opens completed event details from the attendee's own current registrations", async () => {
    registrationsApi.myRegistrations.mockResolvedValue({
      registrations: [registration("event-1")],
    });

    const { el, router } = await mountAt("/dashboard/attendee/events/event-1");

    expect(router.currentRoute.value.name).toBe("attendee-registered-event");
    await vi.waitFor(() => expect(el.textContent).toContain("Completed Design Forum"));
    expect(el.querySelector('[data-testid="event-details-page"]')).toBeTruthy();
    expect(el.textContent).toContain("About this event");
    expect(el.textContent).toContain("Registered");
    expect(el.textContent).toContain("Central Hall");
    expect(el.textContent).not.toContain("ConnectSphere");
    expect(el.querySelector("header")).toBeNull();
    expect(el.textContent).not.toContain("Back to My events");
    expect(el.textContent).not.toContain("Event status");
    expect(el.textContent).not.toContain("completed");
    expect(registrationsApi.myRegistrations).toHaveBeenCalledWith("attendee-token");
  });

  it("confirms withdrawal before the configured cutoff and returns to My events", async () => {
    const upcoming = registration("event-1", {
      starts_at: "2099-10-24T09:00:00Z",
      ends_at: "2099-10-24T12:00:00Z",
      withdrawal_closes_at: "2099-10-24T08:00:00Z",
    });
    registrationsApi.myRegistrations
      .mockResolvedValueOnce({ registrations: [upcoming] })
      .mockResolvedValue({ registrations: [] });
    registrationsApi.withdraw.mockResolvedValue({ status: "withdrawn" });
    registrationsApi.directory.mockResolvedValue({ events: [] });

    const { el, router } = await mountAt("/dashboard/attendee/events/event-1");

    await vi.waitFor(() =>
      expect(
        [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Withdraw registration"),
      ).toBeTruthy(),
    );
    const withdrawButton = [...el.querySelectorAll("button")]
      .find((button) => button.textContent.trim() === "Withdraw registration");
    expect(withdrawButton).toBeTruthy();
    withdrawButton.click();
    await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy());

    const keepButton = [...document.querySelectorAll('[role="dialog"] button')]
      .find((button) => button.textContent.trim() === "Keep registration");
    keepButton.click();
    await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeNull());
    expect(registrationsApi.withdraw).not.toHaveBeenCalled();

    withdrawButton.click();
    await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy());
    const confirmButton = [...document.querySelectorAll('[role="dialog"] button')]
      .find((button) => button.textContent.trim() === "Confirm withdrawal");
    confirmButton.click();

    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("dashboard-attendee"));
    expect(registrationsApi.withdraw).toHaveBeenCalledWith("event-1", "attendee-token");
  });

  it("shows the API error when withdrawal is refused", async () => {
    const upcoming = registration("event-1", {
      starts_at: "2099-10-24T09:00:00Z",
      ends_at: "2099-10-24T12:00:00Z",
      withdrawal_closes_at: "2099-10-24T08:00:00Z",
    });
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [upcoming] });
    registrationsApi.withdraw.mockRejectedValue(new Error("The withdrawal cutoff has passed."));

    const { el } = await mountAt("/dashboard/attendee/events/event-1");
    await vi.waitFor(() => expect(el.textContent).toContain("Withdraw registration"));

    [...el.querySelectorAll("button")]
      .find((button) => button.textContent.trim() === "Withdraw registration")
      .click();
    await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy());
    [...document.querySelectorAll('[role="dialog"] button')]
      .find((button) => button.textContent.trim() === "Confirm withdrawal")
      .click();

    await vi.waitFor(() => expect(el.textContent).toContain("The withdrawal cutoff has passed."));
    expect(registrationsApi.withdraw).toHaveBeenCalledWith("event-1", "attendee-token");
  });

  it("shows a fallback error when withdrawal fails without a message", async () => {
    const upcoming = registration("event-1", {
      starts_at: "2099-10-24T09:00:00Z",
      ends_at: "2099-10-24T12:00:00Z",
      withdrawal_closes_at: "2099-10-24T08:00:00Z",
    });
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [upcoming] });
    registrationsApi.withdraw.mockRejectedValue(new Error(""));

    const { el } = await mountAt("/dashboard/attendee/events/event-1");
    await vi.waitFor(() => expect(el.textContent).toContain("Withdraw registration"));
    [...el.querySelectorAll("button")]
      .find((button) => button.textContent.trim() === "Withdraw registration")
      .click();
    await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy());
    [...document.querySelectorAll('[role="dialog"] button')]
      .find((button) => button.textContent.trim() === "Confirm withdrawal")
      .click();

    await vi.waitFor(() => expect(el.textContent).toContain("Registration could not be withdrawn."));
    expect(registrationsApi.withdraw).toHaveBeenCalledWith("event-1", "attendee-token");
  });

  it.each([
    ["the registration disappears", (store) => { store.myRegistrations = []; }],
    ["the cutoff passes", (store) => { store.myRegistrations[0].event.withdrawal_closes_at = "2000-01-01T00:00:00Z"; }],
    ["another withdrawal starts", (store) => { store.isWithdrawing = true; }],
  ])("does not withdraw when %s while confirmation is open", async (_scenario, makeIneligible) => {
    const upcoming = registration("event-1", {
      starts_at: "2099-10-24T09:00:00Z",
      ends_at: "2099-10-24T12:00:00Z",
      withdrawal_closes_at: "2099-10-24T08:00:00Z",
    });
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [upcoming] });
    const { el } = await mountAt("/dashboard/attendee/events/event-1");
    await vi.waitFor(() => expect(el.textContent).toContain("Withdraw registration"));
    [...el.querySelectorAll("button")]
      .find((button) => button.textContent.trim() === "Withdraw registration")
      .click();
    await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy());
    const { useRegistrationStore } = await import("@/features/registrations/store");
    makeIneligible(useRegistrationStore());

    [...document.querySelectorAll('[role="dialog"] button')]
      .find((button) => button.textContent.trim() === "Confirm withdrawal")
      .click();

    expect(registrationsApi.withdraw).not.toHaveBeenCalled();
  });

  it("does not show an event that is absent from the attendee's current registrations", async () => {
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [] });

    const { el, router } = await mountAt("/dashboard/attendee/events/not-owned");

    expect(router.currentRoute.value.name).toBe("attendee-registered-event");
    await vi.waitFor(() => expect(el.textContent).toContain("Event not found"));
    expect(el.querySelector('[data-testid="event-details-page"]')).toBeTruthy();
    expect(el.textContent).not.toContain("Completed Design Forum");
  });

  it("shows the registration-list error instead of a false not-found result", async () => {
    registrationsApi.myRegistrations.mockRejectedValue(new Error("Unable to load registrations."));

    const { el, router } = await mountAt("/dashboard/attendee/events/event-1");

    expect(router.currentRoute.value.name).toBe("attendee-registered-event");
    await vi.waitFor(() => expect(el.textContent).toContain("Unable to load registrations."));
    expect(el.textContent).not.toContain("Event not found");
  });
});
