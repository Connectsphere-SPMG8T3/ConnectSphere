import { createPinia, setActivePinia } from "pinia";
import { createApp, h, nextTick } from "vue";
import { RouterView } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { authApi, registrationsApi } = vi.hoisted(() => ({
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  registrationsApi: { directory: vi.fn(), event: vi.fn(), register: vi.fn(), myRegistrations: vi.fn() },
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
