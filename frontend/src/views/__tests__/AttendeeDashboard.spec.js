import { createApp, h, nextTick } from "vue";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { registrationsApi, authStore } = vi.hoisted(() => ({
  registrationsApi: {
    directory: vi.fn(),
    myRegistrations: vi.fn(),
  },
  authStore: {
    profile: { full_name: "Avery Attendee" },
    withSession: vi.fn((callback) => callback("attendee-token")),
  },
}));

vi.mock("@/services/api", () => ({ registrationsApi }));
vi.mock("@/stores/auth", () => ({ useAuthStore: () => authStore }));

import AttendeeDashboard from "@/views/dashboards/AttendeeDashboard.vue";

const mountedApps = [];

async function mountDashboard(initialPath = "/dashboard/attendee") {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/dashboard/attendee", name: "dashboard-attendee", component: AttendeeDashboard },
      { path: "/dashboard/attendee/events/:id", name: "attendee-registered-event", component: { render: () => null } },
      { path: "/attendee/events/:id", name: "public-event-detail", component: { render: () => null } },
    ],
  });
  await router.push(initialPath);
  const app = createApp({ render: () => h(RouterView) }).use(createPinia()).use(router);
  app.mount(el);
  mountedApps.push(app);
  await nextTick();
  return { el, router };
}

describe("AttendeeDashboard registered events", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-24T08:00:00Z"));
    vi.clearAllMocks();
    registrationsApi.directory.mockResolvedValue({ events: [] });
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    vi.useRealTimers();
  });

  it("shows attendee registrations with status and separates events by their end time", async () => {
    registrationsApi.myRegistrations.mockResolvedValue({
      registrations: [
        {
          id: "registration-past",
          status: "registered",
          event: {
            id: "event-past",
            name: "Past Design Forum",
            starts_at: "2026-10-22T01:00:00Z",
            ends_at: "2026-10-22T04:00:00Z",
            event_timezone: "Asia/Singapore",
            venues: [{ id: "venue-past", name: "Central Hall", location: "Downtown", capacity: 100 }],
          },
        },
        {
          id: "registration-upcoming",
          status: "waitlisted",
          event: {
            id: "event-upcoming",
            name: "Upcoming City Forum",
            starts_at: "2026-10-24T09:00:00Z",
            ends_at: "2026-10-24T10:00:00Z",
            event_timezone: "Asia/Singapore",
            venues: [
              { id: "venue-one", name: "Main Hall", location: "Downtown", capacity: 100 },
              { id: "venue-two", name: "Workshop Room", location: "Downtown", capacity: 40 },
            ],
          },
        },
      ],
    });

    const { el } = await mountDashboard("/dashboard/attendee?tab=events");

    await vi.waitFor(() => expect(el.textContent).toContain("Past Design Forum"));
    expect(el.textContent).toContain("Upcoming City Forum");
    expect(el.textContent).toContain("Registered");
    expect(el.textContent).toContain("Waitlisted");
    expect(el.textContent).toContain("Past");
    expect(el.textContent).toContain("Upcoming");
    expect(el.textContent).toContain("Main Hall");
    expect(el.textContent).toContain("Workshop Room");
    const upcoming = el.querySelector('[data-testid="upcoming-registrations"]');
    const past = el.querySelector('[data-testid="past-registrations"]');
    expect(upcoming.textContent).toContain("Upcoming City Forum");
    expect(upcoming.textContent).not.toContain("Past Design Forum");
    expect(past.textContent).toContain("Past Design Forum");
    expect(past.textContent).not.toContain("Upcoming City Forum");
    expect(registrationsApi.myRegistrations).toHaveBeenCalledOnce();
  });

  it("shows an empty state when there are no current registrations", async () => {
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [] });

    const { el } = await mountDashboard("/dashboard/attendee?tab=events");

    await vi.waitFor(() => expect(el.textContent).toContain("No registered events yet"));
  });

  it("keeps empty event sections and omits venue text when none is confirmed", async () => {
    registrationsApi.myRegistrations.mockResolvedValue({
      registrations: [{
        id: "registration-upcoming",
        status: "registered",
        event: {
          id: "event-upcoming",
          name: "Upcoming City Forum",
          starts_at: "2026-10-24T09:00:00Z",
          ends_at: "2026-10-24T10:00:00Z",
          event_timezone: "Asia/Singapore",
          venues: [],
        },
      }],
    });

    const { el } = await mountDashboard("/dashboard/attendee?tab=events");
    await vi.waitFor(() => expect(el.textContent).toContain("Upcoming City Forum"));

    expect(el.querySelector('[data-testid="past-registrations"]').textContent).toContain("No past events");
    expect(el.textContent).not.toContain("Venue:");
  });

  it("shows a loading status while the registrations request is pending", async () => {
    let resolveRequest;
    registrationsApi.myRegistrations.mockImplementation(
      () => new Promise((resolve) => { resolveRequest = resolve; }),
    );

    const { el } = await mountDashboard("/dashboard/attendee?tab=events");

    expect(el.querySelector('[role="status"]').textContent).toContain("Loading your registered events");
    resolveRequest({ registrations: [] });
    await vi.waitFor(() => expect(el.textContent).toContain("No registered events yet"));
  });

  it("shows the registrations request error in the dashboard", async () => {
    registrationsApi.myRegistrations.mockRejectedValue(new Error("Unable to load registrations."));

    const { el } = await mountDashboard("/dashboard/attendee?tab=events");

    await vi.waitFor(() => expect(el.textContent).toContain("Unable to load registrations."));
    expect(el.querySelector('[role="alert"]').textContent).toContain("Unable to load registrations.");
  });

  it("shows errors and unavailable summary values instead of reporting zero when loads fail", async () => {
    registrationsApi.myRegistrations.mockRejectedValue(new Error("Unable to load registrations."));
    registrationsApi.directory.mockRejectedValue(new Error("Unable to load public events."));

    const { el } = await mountDashboard();

    await vi.waitFor(() => expect(el.querySelectorAll('[role="alert"]')).toHaveLength(2));
    expect(el.textContent).toContain("Unable to load registrations.");
    expect(el.textContent).toContain("Unable to load public events.");
    expect(el.querySelector('[data-testid="summary-upcoming-registrations"]').textContent).toContain("—");
    expect(el.querySelector('[data-testid="summary-open-events"]').textContent).toContain("—");
    expect(el.querySelector('[data-testid="summary-past-registrations"]').textContent).toContain("—");
  });

  it("shows live summary counts for upcoming registrations, open events, and past registrations", async () => {
    registrationsApi.myRegistrations.mockResolvedValue({
      registrations: [
        {
          id: "past-registration",
          status: "registered",
          event: { id: "past-event", name: "Past Event", starts_at: "2026-10-22T01:00:00Z", ends_at: "2026-10-22T04:00:00Z", event_timezone: "Asia/Singapore", venues: [] },
        },
        {
          id: "upcoming-registration",
          status: "registered",
          event: { id: "upcoming-event", name: "Upcoming Event", starts_at: "2026-10-25T01:00:00Z", ends_at: "2026-10-25T04:00:00Z", event_timezone: "Asia/Singapore", venues: [] },
        },
      ],
    });
    registrationsApi.directory.mockResolvedValue({
      events: [
        { id: "open-event", name: "Open Event", availability: "open" },
        { id: "full-event", name: "Full Event", availability: "full" },
      ],
    });

    const { el } = await mountDashboard();

    await vi.waitFor(() => expect(el.textContent).toContain("Events open for registration"));
    expect(el.querySelector('[data-testid="summary-upcoming-registrations"]').textContent).toContain("1");
    expect(el.querySelector('[data-testid="summary-open-events"]').textContent).toContain("1");
    expect(el.querySelector('[data-testid="summary-past-registrations"]').textContent).toContain("1");
  });

  it("filters My events by time period and links an event to its detail page", async () => {
    registrationsApi.myRegistrations.mockResolvedValue({
      registrations: [
        {
          id: "past-registration",
          status: "registered",
          event: { id: "past-event", name: "Past Event", starts_at: "2026-10-22T01:00:00Z", ends_at: "2026-10-22T04:00:00Z", event_timezone: "Asia/Singapore", venues: [] },
        },
        {
          id: "upcoming-registration",
          status: "waitlisted",
          event: { id: "upcoming-event", name: "Upcoming Event", starts_at: "2026-10-25T01:00:00Z", ends_at: "2026-10-25T04:00:00Z", event_timezone: "Asia/Singapore", venues: [] },
        },
      ],
    });

    const { el, router } = await mountDashboard("/dashboard/attendee?tab=events");
    await vi.waitFor(() => expect(el.textContent).toContain("Upcoming Event"));

    const upcomingLink = el.querySelector('a[href="/dashboard/attendee/events/upcoming-event"]');
    expect(upcomingLink).toBeTruthy();
    expect(upcomingLink.textContent).toContain("Waitlisted");
    const pastFilter = [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Past");
    pastFilter.click();
    await nextTick();
    expect(el.textContent).toContain("Past Event");
    expect(el.textContent).not.toContain("Upcoming Event");

    const pastLink = el.querySelector('a[href="/dashboard/attendee/events/past-event"]');
    await pastLink.click();
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("attendee-registered-event"));
  });

  it("offers organiser-style event filters and registration cards", async () => {
    registrationsApi.myRegistrations.mockResolvedValue({
      registrations: [
        {
          id: "registration-garden",
          status: "registered",
          event: {
            id: "event-garden",
            name: "Garden Supper",
            starts_at: "2026-10-25T09:00:00Z",
            ends_at: "2026-10-25T11:00:00Z",
            event_timezone: "Asia/Singapore",
            status: "confirmed",
            venues: [],
          },
        },
        {
          id: "registration-city",
          status: "waitlisted",
          event: {
            id: "event-city",
            name: "City Forum",
            starts_at: "2026-10-26T09:00:00Z",
            ends_at: "2026-10-26T11:00:00Z",
            event_timezone: "Asia/Singapore",
            status: "confirmed",
            venues: [],
          },
        },
      ],
    });

    const { el } = await mountDashboard("/dashboard/attendee?tab=events");
    await vi.waitFor(() => expect(el.textContent).toContain("Garden Supper"));

    expect(el.textContent).toContain("Find my event");
    expect(el.querySelector('[data-testid="registration-filters"]')).toBeTruthy();
    expect(el.querySelector('[data-event-row="event-garden"]')).toBeTruthy();
    expect(el.querySelector('[data-event-row="event-city"]')).toBeTruthy();
    expect(el.querySelector('[data-event-row="event-garden"]').getAttribute("data-tone")).toBe("done");
    expect(el.querySelector('[data-event-row="event-city"]').getAttribute("data-tone")).toBe("waiting");

    const search = el.querySelector('input[aria-label="Search my events"]');
    search.value = "City";
    search.dispatchEvent(new Event("input"));
    await nextTick();
    expect(el.textContent).toContain("City Forum");
    expect(el.textContent).not.toContain("Garden Supper");

    search.value = "";
    search.dispatchEvent(new Event("input"));
    await nextTick();

    const sortBy = el.querySelector('button[aria-label="Sort my events by"]');
    sortBy.click();
    await nextTick();
    [...el.querySelectorAll('[role="option"]')]
      .find((option) => option.textContent.trim() === "Event name")
      .click();
    await nextTick();
    expect([...el.querySelectorAll('[data-testid="upcoming-registrations"] [data-event-row]')]
      .map((card) => card.querySelector("p").textContent))
      .toEqual(["City Forum", "Garden Supper"]);

    const direction = el.querySelector('button[aria-label^="Toggle sort direction"]');
    direction.click();
    await nextTick();
    expect([...el.querySelectorAll('[data-testid="upcoming-registrations"] [data-event-row]')]
      .map((card) => card.querySelector("p").textContent))
      .toEqual(["Garden Supper", "City Forum"]);

    const statusButton = el.querySelector('button[aria-label="Filter registrations by status"]');
    statusButton.click();
    await nextTick();
    const waitlisted = el.querySelector('input[type="checkbox"][value="waitlisted"]');
    waitlisted.checked = true;
    waitlisted.dispatchEvent(new Event("change"));
    await nextTick();
    expect(el.textContent).toContain("City Forum");
    expect(el.textContent).not.toContain("Garden Supper");

    el.querySelector('button[aria-label="Clear my event filters"]').click();
    await nextTick();
    expect(el.textContent).toContain("City Forum");
    expect(el.textContent).toContain("Garden Supper");
    expect(direction.getAttribute("aria-label")).toBe(
      "Toggle sort direction, currently Ascending by Event date",
    );
  });

  it("shows the existing public directory content in Explore with name search", async () => {
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [] });
    registrationsApi.directory.mockResolvedValue({
      events: [
        {
          id: "event-city",
          name: "City Gathering",
          description: "A community event.",
          starts_at: "2026-11-03T11:00:00Z",
          ends_at: "2026-11-03T13:00:00Z",
          event_timezone: "Asia/Singapore",
          status: "confirmed",
          availability: "open",
          venues: [{ id: "venue-1", name: "Civic Hall" }],
        },
        {
          id: "event-garden",
          name: "Garden Supper",
          description: "",
          starts_at: "2026-11-04T11:00:00Z",
          ends_at: "2026-11-04T13:00:00Z",
          event_timezone: "Asia/Singapore",
          status: "confirmed",
          availability: "full",
          venues: [],
        },
      ],
    });

    const { el } = await mountDashboard("/dashboard/attendee?tab=explore");
    await vi.waitFor(() => expect(el.textContent).toContain("City Gathering"));
    expect(el.textContent).toContain("A community event.");
    expect(el.textContent).toContain("Civic Hall");
    expect(el.textContent).toContain("Venue details to be announced");
    expect(el.textContent).toContain("3 Nov 2026 7:00pm - 9:00pm");
    expect(el.textContent).not.toContain("confirmed");
    expect(el.querySelector('a[href="/attendee/events/event-city"]')).toBeTruthy();

    const search = el.querySelector('input[aria-label="Search public events"]');
    search.value = "Garden";
    search.dispatchEvent(new Event("input"));
    await nextTick();
    expect(el.textContent).toContain("Garden Supper");
    expect(el.textContent).not.toContain("City Gathering");

    search.value = "";
    search.dispatchEvent(new Event("input"));
    await nextTick();
    const directionButton = el.querySelector('button[aria-label^="Toggle sort direction"]');
    expect(directionButton.getAttribute("aria-label")).toBe(
      "Toggle sort direction, currently Ascending by Event date",
    );
    directionButton.click();
    await nextTick();
    expect(directionButton.getAttribute("aria-label")).toBe(
      "Toggle sort direction, currently Descending by Event date",
    );
    expect([...el.querySelectorAll("article h3")].map((heading) => heading.textContent))
      .toEqual(["Garden Supper", "City Gathering"]);
  });

  it("shows the public directory error in Explore instead of an empty state", async () => {
    registrationsApi.myRegistrations.mockResolvedValue({ registrations: [] });
    registrationsApi.directory.mockRejectedValue(new Error("Unable to load public events."));

    const { el } = await mountDashboard("/dashboard/attendee?tab=explore");

    await vi.waitFor(() => expect(el.textContent).toContain("Unable to load public events."));
    expect(el.querySelector('[role="alert"]').textContent).toContain("Unable to load public events.");
    expect(el.textContent).not.toContain("No public events yet");
  });
});
