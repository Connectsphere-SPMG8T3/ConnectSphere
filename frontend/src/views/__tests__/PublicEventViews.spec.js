import { createPinia, setActivePinia } from "pinia";
import { createApp, h, nextTick } from "vue";
import { RouterView } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { registrationsApi } from "@/services/api";
import { dismissToast, toastState } from "@/composables/useToast";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  registrationsApi: { directory: vi.fn(), event: vi.fn(), register: vi.fn(), myRegistrations: vi.fn() },
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
    vi.resetAllMocks();
    dismissToast();
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    dismissToast();
  });

  it("shows public events as one accessible navigation link per card", async () => {
    registrationsApi.directory.mockResolvedValue({ events: [event()] });
    const { el } = await mountAt("/");

    await vi.waitFor(() => expect(el.textContent).toContain("Evening with the City"));
    const eventLink = el.querySelector('a[href="/attendee/events/event-1"]');
    expect(eventLink?.textContent).toContain("View event");
    expect(eventLink?.querySelector("button")).toBeNull();
    expect(el.textContent).toContain("Registration open");
  });

  it("pins the landing header to the top, outside the page content, with sign-in and sign-up buttons", async () => {
    registrationsApi.directory.mockResolvedValue({ events: [] });
    const { el } = await mountAt("/");

    const header = el.querySelector("header");
    expect(header.closest("main")).toBeNull();
    for (const name of ["sticky", "top-0", "bg-canvas"]) expect(header.classList.contains(name)).toBe(true);
    const signIn = header.querySelector('a[href="/login"]');
    const signUp = header.querySelector('a[href="/signup/attendee"]');
    expect(signIn?.textContent.trim()).toBe("Sign in");
    expect(signUp?.textContent.trim()).toBe("Sign up");
    for (const link of [signIn, signUp]) expect(link.classList.contains("shadow-hard")).toBe(true);
  });

  it("asks what the visitor is looking for and shows events to join by default", async () => {
    registrationsApi.directory.mockResolvedValue({ events: [event()] });
    const { el } = await mountAt("/");

    await vi.waitFor(() => expect(el.textContent).toContain("Evening with the City"));
    expect(el.querySelector("h1")?.textContent).toBe("What are you up to?");
    const tabs = [...el.querySelectorAll('[role="tab"]')];
    expect(tabs.map((tab) => tab.textContent.trim())).toEqual(["Finding something fun to join", "Planning an event of my own"]);
    expect(tabs.map((tab) => tab.getAttribute("aria-selected"))).toEqual(["true", "false"]);
    expect(tabs[0].classList.contains("bg-ink")).toBe(true);
    const panel = el.querySelector('[role="tabpanel"]');
    expect(panel.getAttribute("aria-labelledby")).toBe(tabs[0].id);
    expect(panel.textContent).toContain("Happening soon");
    expect(el.textContent).not.toContain("From idea to event in four steps");
    const art = el.querySelector('[data-testid="hero-illustration"]');
    expect(art.getAttribute("aria-hidden")).toBe("true");
    expect(art.textContent).toContain("Admit one");
    expect(el.querySelector(".rounded-full.h-44")).toBeNull();
    expect(el.querySelector('header a[href="/signup/attendee"]')?.textContent.trim()).toBe("Sign up");
  });

  it("switches to the organiser view, records it in the URL and points sign-up at organisers", async () => {
    registrationsApi.directory.mockResolvedValue({ events: [event()] });
    const { el, router } = await mountAt("/");

    await vi.waitFor(() => expect(el.textContent).toContain("Evening with the City"));
    el.querySelectorAll('[role="tab"]')[1].click();

    await vi.waitFor(() => expect(router.currentRoute.value.query.for).toBe("organisers"));
    await nextTick();
    const tabs = [...el.querySelectorAll('[role="tab"]')];
    expect(tabs.map((tab) => tab.getAttribute("aria-selected"))).toEqual(["false", "true"]);
    const panel = el.querySelector('[role="tabpanel"]');
    expect(panel.getAttribute("aria-labelledby")).toBe(tabs[1].id);
    expect(panel.textContent).toContain("From idea to event in four steps");
    expect(el.querySelector('[data-testid="hero-illustration"]').textContent).toContain("Event plan");
    expect(panel.querySelectorAll("ol > li")).toHaveLength(4);
    expect(panel.querySelector('a[href="/signup/organiser"]')?.textContent.trim()).toBe("Create organiser account");
    expect(panel.querySelectorAll("a")).toHaveLength(1);
    expect(el.textContent).not.toContain("Happening soon");
    expect(el.querySelector('header a[href="/signup/organiser"]')?.textContent.trim()).toBe("Sign up");
  });

  it("opens the organiser view from a shared link", async () => {
    registrationsApi.directory.mockResolvedValue({ events: [] });
    const { el } = await mountAt("/?for=organisers");

    await vi.waitFor(() => expect(el.textContent).toContain("From idea to event in four steps"));
    expect(el.querySelectorAll('[role="tab"]')[1].getAttribute("aria-selected")).toBe("true");
  });

  it("animates the hero illustration when motion is allowed", async () => {
    window.matchMedia = vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    try {
      registrationsApi.directory.mockResolvedValue({ events: [] });
      const { el } = await mountAt("/");

      const ticket = el.querySelector('[data-testid="hero-illustration"]').firstElementChild;
      const before = ticket.className;
      await vi.waitFor(() => expect(ticket.className).not.toBe(before), { timeout: 2500 });

      el.querySelectorAll('[role="tab"]')[1].click();
      await vi.waitFor(() => expect(el.textContent).toContain("Event plan"));
      const ticks = () => el.querySelectorAll('[data-testid="hero-illustration"] [data-done="true"]').length;
      expect(ticks()).toBe(0);
      await vi.waitFor(() => expect(ticks()).toBe(1), { timeout: 2000 });
    } finally {
      delete window.matchMedia;
    }
  });

  it("moves between the options with the arrow keys", async () => {
    registrationsApi.directory.mockResolvedValue({ events: [] });
    const { el, router } = await mountAt("/");

    const tabs = () => [...el.querySelectorAll('[role="tab"]')];
    expect(tabs().map((tab) => tab.tabIndex)).toEqual([0, -1]);
    tabs()[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    await vi.waitFor(() => expect(router.currentRoute.value.query.for).toBe("organisers"));
    await nextTick();
    expect(document.activeElement).toBe(tabs()[1]);
    expect(tabs().map((tab) => tab.tabIndex)).toEqual([-1, 0]);

    tabs()[1].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
    await vi.waitFor(() => expect(router.currentRoute.value.query.for).toBeUndefined());
    await nextTick();
    expect(document.activeElement).toBe(tabs()[0]);
  });

  it.each(["/", "/attendee/events/event-1"])("ends %s with the ConnectSphere footer, outside the page content", async (path) => {
    registrationsApi.directory.mockResolvedValue({ events: [event()] });
    registrationsApi.event.mockResolvedValue(event());
    const { el } = await mountAt(path);

    await vi.waitFor(() => expect(el.textContent).toContain("Civic Hall"));
    const footer = el.querySelector("footer");
    expect(footer.closest("main")).toBeNull();
    expect(footer.previousElementSibling?.tagName).toBe("MAIN");
    const links = Object.fromEntries([...footer.querySelectorAll("a")].map((link) => [link.textContent.trim(), link.getAttribute("href")]));
    expect(links).toMatchObject({
      "Browse events": "/",
      "Create attendee account": "/signup/attendee",
      "Create organiser account": "/signup/organiser",
      "Sign in": "/login",
    });
    expect(footer.textContent).toContain(`© ${new Date().getFullYear()} ConnectSphere`);
  });

  it("uses the same pinned header on the event page", async () => {
    registrationsApi.event.mockResolvedValue(event());
    const { el } = await mountAt("/attendee/events/event-1");

    await vi.waitFor(() => expect(el.textContent).toContain("Civic Hall"));
    const header = el.querySelector("header");
    expect(header.closest("main")).toBeNull();
    expect(header.classList.contains("sticky")).toBe(true);
    const allEvents = [...header.querySelectorAll("a")].find((link) => link.textContent.trim() === "All events");
    expect(allEvents?.getAttribute("href")).toBe("/");
  });

  it("returns a signed-out visitor to the event after choosing Register", async () => {
    registrationsApi.event.mockResolvedValue(event());
    const { el, router } = await mountAt("/attendee/events/event-1");

    await vi.waitFor(() => expect(el.textContent).toContain("Civic Hall"));
    [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Register").click();

    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("login"));
    expect(router.currentRoute.value.query.redirect).toBe("/attendee/events/event-1");
  });

  it("confirms an Attendee registration immediately", async () => {
    registrationsApi.event
      .mockResolvedValueOnce(event())
      .mockResolvedValueOnce(event({ registered_count: 13 }));
    registrationsApi.register.mockResolvedValue({ registration_id: "registration-1", status: "registered" });
    const { el } = await mountAt("/attendee/events/event-1", {
      signedInAs: { id: "attendee-1", full_name: "Avery Attendee", role: "attendee", roles: ["attendee"] },
    });

    await vi.waitFor(() => expect(el.textContent).toContain("Civic Hall"));
    [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Register").click();

    await vi.waitFor(() => expect(el.textContent).toContain("13 of 80 places registered"));
    const button = [...el.querySelectorAll("button")].find((item) => item.textContent.trim() === "Registered");
    expect(button?.disabled).toBe(true);
    expect(toastState.value).toMatchObject({ message: "You are registered for this event.", tone: "success" });
    expect(registrationsApi.event).toHaveBeenCalledTimes(2);
    expect(registrationsApi.register).toHaveBeenCalledWith("event-1", "access");
  });

  it("uses the refreshed server count for an existing registration", async () => {
    registrationsApi.event
      .mockResolvedValueOnce(event())
      .mockResolvedValueOnce(event({ registered_count: 12 }));
    registrationsApi.register.mockResolvedValue({ registration_id: "registration-1", status: "already_registered" });
    const { el } = await mountAt("/attendee/events/event-1", {
      signedInAs: { id: "attendee-1", full_name: "Avery Attendee", role: "attendee", roles: ["attendee"] },
    });

    await vi.waitFor(() => expect(el.textContent).toContain("Civic Hall"));
    [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Register").click();

    await vi.waitFor(() => expect(toastState.value).toMatchObject({ message: "You are already registered for this event." }));
    expect(el.textContent).toContain("12 of 80 places registered");
    const button = [...el.querySelectorAll("button")].find((item) => item.textContent.trim() === "Registered");
    expect(button?.disabled).toBe(true);
    expect(toastState.value).toMatchObject({ tone: "success" });
  });

  it("lets an active Attendee join an enabled waitlist", async () => {
    registrationsApi.event.mockResolvedValue(event({ availability: "full", registered_count: 80 }));
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [] });
    registrationsApi.register.mockResolvedValue({ registration_id: "registration-1", status: "waitlisted" });
    const { el } = await mountAt("/attendee/events/event-1", {
      signedInAs: { id: "attendee-1", full_name: "Avery Attendee", role: "attendee", roles: ["attendee"] },
    });

    await vi.waitFor(() => expect(el.textContent).toContain("Join waitlist"));
    const joinButton = [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Join waitlist");
    expect(joinButton.disabled).toBe(false);
    joinButton.click();

    await vi.waitFor(() => expect(registrationsApi.register).toHaveBeenCalledWith("event-1", "access"));
    await vi.waitFor(() => expect(el.textContent).toContain("Waitlisted"));
  });

  it("does not offer a waitlist action when waitlisting is disabled", async () => {
    registrationsApi.event.mockResolvedValue(event({ availability: "full", waitlist_enabled: false }));
    const { el } = await mountAt("/attendee/events/event-1");

    await vi.waitFor(() => expect(el.textContent).toContain("Full"));
    expect(el.textContent).not.toContain("Join waitlist");
  });
});