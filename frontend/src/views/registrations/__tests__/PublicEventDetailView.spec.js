import { createPinia, setActivePinia } from "pinia";
import { createApp, h, nextTick } from "vue";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { registrationsApi, authStore } = vi.hoisted(() => ({
  registrationsApi: {
    directory: vi.fn(),
    event: vi.fn(),
    register: vi.fn(),
    myRegistrations: vi.fn(),
  },
  authStore: {
    isAuthenticated: false,
    role: null,
    withSession: vi.fn((operation) => operation("attendee-token")),
  },
}));

vi.mock("@/services/api", () => ({ registrationsApi }));
vi.mock("@/stores/auth", () => ({ useAuthStore: () => authStore }));

import PublicEventDetailView from "@/views/registrations/PublicEventDetailView.vue";

const mountedApps = [];

async function mountEventDetail() {
  setActivePinia(createPinia());
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/attendee/events/:id", name: "public-event-detail", component: PublicEventDetailView },
      { path: "/", name: "public-events", component: { render: () => null } },
      { path: "/login", name: "login", component: { render: () => null } },
      { path: "/signup/:role", name: "signup", component: { render: () => null } },
    ],
  });
  await router.push("/attendee/events/event-1");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(RouterView) }).use(createPinia()).use(router);
  app.mount(el);
  mountedApps.push(app);
  await nextTick();
  return { el, router };
}

describe("public event details", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
    authStore.isAuthenticated = false;
    authStore.role = null;
    authStore.withSession.mockImplementation((operation) => operation("attendee-token"));
    registrationsApi.event.mockResolvedValue({
      id: "event-1",
      name: "Community Design Forum",
      description: "A public event for neighbours.",
      starts_at: "2026-11-03T11:00:00Z",
      ends_at: "2026-11-03T13:00:00Z",
      event_timezone: "Asia/Singapore",
      status: "confirmed",
      availability: "open",
      effective_capacity: 100,
      registered_count: 24,
      waitlist_enabled: false,
      venues: [{
        id: "venue-1",
        name: "Civic Hall",
        location: "Singapore",
        capacity: 100,
      }],
    });
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  it("uses the shared event-detail layout and preserves public registration actions", async () => {
    const { el } = await mountEventDetail();

    await vi.waitFor(() => expect(el.textContent).toContain("Community Design Forum"));
    expect(el.querySelector('[data-testid="event-details-page"]')).toBeTruthy();
    expect(el.querySelector("header")).toBeTruthy();
    expect(el.textContent).toContain("ConnectSphere");
    expect(el.textContent).toContain("All events");
    expect(el.textContent).toContain("About this event");
    expect(el.textContent).toContain("Civic Hall");
    expect(el.textContent).toContain("Registration open");
    expect(el.textContent).toContain("Tuesday 3 November 2026 7:00pm - 9:00pm");
    expect(el.textContent).not.toContain("confirmed");
    expect(el.textContent).not.toContain("Ends ");
    expect(el.querySelector("button").textContent).toContain("Register");
  });

  it("routes unauthenticated users to sign in before registration", async () => {
    const { el, router } = await mountEventDetail();

    await vi.waitFor(() => expect(el.textContent).toContain("Community Design Forum"));
    el.querySelector("button").click();

    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("login"));
    expect(router.currentRoute.value.query.redirect).toBe("/attendee/events/event-1");
  });

  it("omits the public page header for a signed-in active Attendee", async () => {
    authStore.isAuthenticated = true;
    authStore.role = "attendee";
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [] });

    const { el } = await mountEventDetail();

    await vi.waitFor(() => expect(el.textContent).toContain("Community Design Forum"));
    expect(el.querySelector('[data-testid="event-details-page"] > header')).toBeNull();
    expect(el.textContent).not.toContain("ConnectSphere");
    expect(el.textContent).not.toContain("All events");
  });

  it("shows Registered instead of an active Register button for an existing Attendee registration", async () => {
    authStore.isAuthenticated = true;
    authStore.role = "attendee";
    registrationsApi.myRegistrations.mockResolvedValue({
      registrations: [{
        id: "registration-1",
        status: "registered",
        event: { id: "event-1" },
      }],
    });

    const { el } = await mountEventDetail();

    await vi.waitFor(() => expect(registrationsApi.myRegistrations).toHaveBeenCalledWith("attendee-token"));
    const button = el.querySelector("button");
    expect(button.textContent).toContain("Registered");
    expect(button.disabled).toBe(true);
    expect(registrationsApi.register).not.toHaveBeenCalled();
  });

  it("keeps Register available when the active Attendee has no existing registration", async () => {
    authStore.isAuthenticated = true;
    authStore.role = "attendee";
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [] });

    const { el } = await mountEventDetail();

    await vi.waitFor(() => expect(registrationsApi.myRegistrations).toHaveBeenCalledWith("attendee-token"));
    const button = el.querySelector("button");
    await vi.waitFor(() => expect(button.disabled).toBe(false));
    expect(button.textContent).toContain("Register");
  });

  it("keeps Register disabled until the active Attendee's registration lookup finishes", async () => {
    authStore.isAuthenticated = true;
    authStore.role = "attendee";
    let resolveRegistrations;
    registrationsApi.myRegistrations.mockReturnValue(new Promise((resolve) => {
      resolveRegistrations = resolve;
    }));

    const { el } = await mountEventDetail();

    await vi.waitFor(() => expect(registrationsApi.myRegistrations).toHaveBeenCalledWith("attendee-token"));
    await vi.waitFor(() => expect(el.querySelector("button")).toBeTruthy());
    const button = el.querySelector("button");
    expect(button.disabled).toBe(true);

    resolveRegistrations({ registrations: [] });
    await vi.waitFor(() => expect(button.disabled).toBe(false));
  });

  it("requires the active Attendee role before allowing registration", async () => {
    authStore.isAuthenticated = true;
    authStore.role = "organiser";
    const { el } = await mountEventDetail();

    await vi.waitFor(() => expect(el.textContent).toContain("Switch your active role to Attendee to register."));
    expect(el.querySelector("button").disabled).toBe(true);
    expect(registrationsApi.myRegistrations).not.toHaveBeenCalled();
    expect(registrationsApi.register).not.toHaveBeenCalled();
  });

  it("shows an error when the existing registration check fails", async () => {
    authStore.isAuthenticated = true;
    authStore.role = "attendee";
    registrationsApi.myRegistrations.mockRejectedValue(new Error("Unable to load your registered events."));

    const { el } = await mountEventDetail();

    await vi.waitFor(() =>
      expect(el.querySelector('[role="alert"]')?.textContent).toContain("Unable to load your registered events."),
    );
  });

  it("shows registration errors returned by the registration store", async () => {
    authStore.isAuthenticated = true;
    authStore.role = "attendee";
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [] });
    registrationsApi.register.mockRejectedValue(new Error("Registration failed"));
    const { el } = await mountEventDetail();

    await vi.waitFor(() => expect(el.textContent).toContain("Community Design Forum"));
    const button = el.querySelector("button");
    await vi.waitFor(() => expect(button.disabled).toBe(false));
    button.click();

    await vi.waitFor(() =>
      expect(el.querySelector('[role="alert"]')?.textContent).toContain("Registration failed"),
    );
    expect(registrationsApi.register).toHaveBeenCalledWith("event-1", "attendee-token");
  });
});
