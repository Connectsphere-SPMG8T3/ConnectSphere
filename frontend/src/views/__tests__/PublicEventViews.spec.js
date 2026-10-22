import { createPinia, setActivePinia } from "pinia";
import { createApp, h, nextTick } from "vue";
import { RouterView } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { registrationsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  registrationsApi: { directory: vi.fn(), event: vi.fn(), register: vi.fn() },
}));

const event = (overrides = {}) => ({
  id: "event-1",
  name: "Evening with the City",
  description: "A gathering for neighbours.",
  starts_at: "2026-11-03T11:00:00Z",
  ends_at: "2026-11-03T13:00:00Z",
  event_timezone: "Asia/Singapore",
  status: "confirmed",
  availability: "open",
  effective_capacity: 80,
  registered_count: 12,
  waitlist_enabled: true,
  venues: [{ id: "venue-1", name: "Civic Hall", location: "Singapore", capacity: 80 }],
  ...overrides,
});

const mountedApps = [];

async function settle() {
  for (let index = 0; index < 5; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    await nextTick();
  }
}

async function mountAt(path, { signedInAs } = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  if (signedInAs) {
    const auth = useAuthStore();
    auth.token = "access";
    auth.refreshToken = "refresh";
    auth.profile = signedInAs;
    auth.sessionVerified = true;
  }
  const { default: router } = await import("@/router");
  await router.push(path);
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(RouterView) }).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await settle();
  return { el, router };
}

describe("public event pages", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  it("shows public events as one accessible navigation link per card", async () => {
    registrationsApi.directory.mockResolvedValue({ events: [event()] });
    const { el } = await mountAt("/");

    await vi.waitFor(() => expect(el.textContent).toContain("Evening with the City"));
    const eventLink = el.querySelector('a[href="/public/events/event-1"]');
    expect(eventLink?.textContent).toContain("View event");
    expect(eventLink?.querySelector("button")).toBeNull();
    expect(el.textContent).toContain("Registration open");
  });

  it("returns a signed-out visitor to the event after choosing Register", async () => {
    registrationsApi.event.mockResolvedValue(event());
    const { el, router } = await mountAt("/public/events/event-1");

    await vi.waitFor(() => expect(el.textContent).toContain("Civic Hall"));
    [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Register").click();

    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("login"));
    expect(router.currentRoute.value.query.redirect).toBe("/public/events/event-1");
  });

  it("confirms an Attendee registration immediately", async () => {
    registrationsApi.event.mockResolvedValue(event());
    registrationsApi.register.mockResolvedValue({ registration_id: "registration-1", status: "registered" });
    const { el } = await mountAt("/public/events/event-1", {
      signedInAs: { id: "attendee-1", full_name: "Avery Attendee", role: "attendee", roles: ["attendee"] },
    });

    await vi.waitFor(() => expect(el.textContent).toContain("Civic Hall"));
    [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Register").click();

    await vi.waitFor(() => expect(el.textContent).toContain("Registration confirmed."));
    expect(registrationsApi.register).toHaveBeenCalledWith("event-1", "access");
  });

  it("shows Join waitlist only as a non-enrolling CTA when enabled", async () => {
    registrationsApi.event.mockResolvedValue(event({ availability: "full" }));
    const { el } = await mountAt("/public/events/event-1");

    await vi.waitFor(() => expect(el.textContent).toContain("Join waitlist"));
    expect([...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Join waitlist").disabled).toBe(true);
    expect(registrationsApi.register).not.toHaveBeenCalled();
  });

  it("does not offer a waitlist action when waitlisting is disabled", async () => {
    registrationsApi.event.mockResolvedValue(event({ availability: "full", waitlist_enabled: false }));
    const { el } = await mountAt("/public/events/event-1");

    await vi.waitFor(() => expect(el.textContent).toContain("Full"));
    expect(el.textContent).not.toContain("Join waitlist");
  });
});