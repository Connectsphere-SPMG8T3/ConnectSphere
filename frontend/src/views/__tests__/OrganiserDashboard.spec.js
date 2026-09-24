import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { useEventsStore } from "@/stores/events";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), submit: vi.fn() },
}));

const EVENT_RESPONSES = [
  {
    id: "draft-1",
    name: "Regional Workshop",
    status: "draft",
    event_timezone: "Asia/Singapore",
    starts_at: null,
    ends_at: null,
    expected_attendance: null,
    facilities_required: [],
    registration_enabled: false,
  },
  {
    id: "review-1",
    name: "Annual Conference",
    status: "under_review",
    event_timezone: "Asia/Singapore",
    starts_at: "2026-11-01T02:00:00Z",
    ends_at: "2026-11-01T07:00:00Z",
    expected_attendance: 150,
    facilities_required: [],
    registration_enabled: false,
    coordinator_id: null,
  },
  {
    id: "confirmed-1",
    name: "Leadership Forum",
    status: "confirmed",
    event_timezone: "Asia/Singapore",
    starts_at: "2026-10-10T02:00:00Z",
    ends_at: "2026-10-10T05:00:00Z",
    expected_attendance: 80,
    facilities_required: [],
    registration_enabled: false,
    venue_name: "Hall A",
    coordinator_id: "coordinator-1",
  },
  {
    id: "returned-1",
    name: "Product Briefing",
    status: "returned",
    event_timezone: "Asia/Singapore",
    starts_at: "2026-12-01T02:00:00Z",
    ends_at: "2026-12-01T04:00:00Z",
    expected_attendance: 40,
    facilities_required: [],
    registration_enabled: false,
    coordinator_id: "coordinator-1",
  },
];

const mountedApps = [];

async function mountDashboard() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = { id: "organiser-1", full_name: "Priya Nair", role: "event_organiser" };
  authStore.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "dashboard-organiser" });
  const { default: OrganiserDashboard } = await import("@/views/dashboards/OrganiserDashboard.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(OrganiserDashboard).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await settle();
  return { el, router, eventsStore: useEventsStore() };
}

async function settle() {
  await Promise.resolve();
  await nextTick();
  await nextTick();
}

function buttonByText(el, text) {
  return [...el.querySelectorAll("button")].find((button) => button.textContent.includes(text));
}

async function openEvents(el) {
  const { default: router } = await import("@/router");
  await router.push({ name: "dashboard-organiser", query: { tab: "events" } });
  await settle();
}

describe("OrganiserDashboard", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
    eventsApi.list.mockResolvedValue(EVENT_RESPONSES);
  });

  it("renders every owned event with key details in separate drafts and requests sections", async () => {
    const { el } = await mountDashboard();
    await openEvents(el);

    expect(el.textContent).toContain("Drafts");
    expect(el.textContent).toContain("Requests");
    expect(el.textContent).toContain("Regional Workshop");
    expect(el.textContent).toContain("Annual Conference");
    expect(el.textContent).toContain("10 Oct 2026");
    expect(el.textContent).toContain("80");
    expect(el.textContent).toContain("Hall A");
    expect(el.textContent).toContain("Coordinator assigned");
    expect(el.textContent).toContain("Awaiting assignment");
    expect(el.textContent).toContain("Awaiting assignment");
  });

  it("shows overview counts and switches to the full events tab", async () => {
    const { el, router } = await mountDashboard();

    expect(el.textContent).toContain("Needs your action");
    expect(el.textContent).toContain("Drafts");
    expect(el.textContent).toContain("My events");
    expect(el.textContent).toContain("Under review");
    expect(el.textContent).toContain("My events by status");

    await router.push({ name: "dashboard-organiser", query: { tab: "events" } });
    await settle();
    expect(el.textContent).toContain("Find my event");
    expect(el.textContent).toContain("Regional Workshop");
  });

  it("shows organiser attention states and status-specific actions", async () => {
    const { el } = await mountDashboard();
    await openEvents(el);
    el.querySelector('button[aria-label="Filter events by status"]').click();
    await settle();

    expect(el.textContent).toContain("Awaiting assignment");
    expect(el.textContent).toContain("Amend and resubmit");
    expect(el.textContent).toContain("Edit draft");
    expect(el.textContent).toContain("View event");
    const underReviewCard = [...el.querySelectorAll('[data-event-name]')]
      .find((node) => node.querySelector("h3")?.textContent.trim() === "Annual Conference")
      .closest(".border-4");
    expect(underReviewCard.textContent).not.toContain("Action needed: review this request.");
  });

  it("matches event card hover tints to their status rail colors", async () => {
    const { el } = await mountDashboard();
    await openEvents(el);

    const cardFor = (name) => [...el.querySelectorAll('[data-event-name]')]
      .find((node) => node.querySelector("h3")?.textContent.trim() === name)
      .closest(".border-4");
    const draftCard = cardFor("Regional Workshop");
    const returnedCard = cardFor("Product Briefing");
    const confirmedCard = cardFor("Leadership Forum");

    expect(draftCard.className).toContain("hover:bg-bauhaus-blue/10");
    expect(returnedCard.className).toContain("hover:bg-bauhaus-red/10");
    expect(confirmedCard.className).toContain("hover:bg-bauhaus-blue/10");
    expect(draftCard.className).toContain("border-4");
    expect(draftCard.className).toContain("shadow-none");
    expect(draftCard.querySelector("button").className).toContain("shadow-none");
    expect(draftCard.querySelector("button").className).toContain("hover:bg-bauhaus-blue/20");
    expect(returnedCard.querySelector("button").className).toContain("shadow-none");
    expect(returnedCard.querySelector("button").className).toContain("hover:bg-bauhaus-red/20");
    expect(confirmedCard.querySelector("button").className).toContain("hover:bg-bauhaus-blue/20");
  });

  it("opens the events view filtered to the selected action category", async () => {
    const { el, router } = await mountDashboard();

    const draftsCard = el.querySelector('[role="button"][aria-label="Show Drafts events"]');
    draftsCard.click();
    await vi.waitFor(() => expect(router.currentRoute.value.query).toEqual({ tab: "events", status: "draft" }));
    await settle();

    expect(router.currentRoute.value.query).toEqual({ tab: "events", status: "draft" });
    el.querySelector('button[aria-label="Filter events by status"]').click();
    await settle();
    expect(el.querySelector('input[type="checkbox"][value="draft"]').checked).toBe(true);
    expect(el.textContent).toContain("Regional Workshop");
    expect(el.textContent).not.toContain("Annual Conference");
  });

  it("uses the urgent visual treatment for returned requests and subtle hover tones for action cards", async () => {
    const { el } = await mountDashboard();

    const draftsCard = el.querySelector('[aria-label="Show Drafts events"]');
    const returnedCard = el.querySelector('[aria-label="Show Returned for amendments events"]');
    const rejectedCard = el.querySelector('[aria-label="Show Rejected events"]');

    expect(draftsCard.className).toContain("bg-bauhaus-blue/10");
    expect(draftsCard.querySelector("span").className).toContain("bg-bauhaus-blue");
    expect(returnedCard.className).toContain("bg-bauhaus-red/10");
    expect(returnedCard.querySelector("span").className).toContain("bg-bauhaus-red");
    expect(rejectedCard.className).toContain("bg-bauhaus-yellow/10");
  });

  it("paginates status previews by two events and opens a selected event detail", async () => {
    const { el, router, eventsStore } = await mountDashboard();
    eventsStore.events.push(
      { ...eventsStore.events[2], id: "confirmed-2", name: "Confirmed Two" },
      { ...eventsStore.events[2], id: "confirmed-3", name: "Confirmed Three" },
      { ...eventsStore.events[2], id: "confirmed-4", name: "Confirmed Four" },
    );
    await settle();

    const confirmedGroup = el.querySelector('[data-status-group="confirmed"]');
    expect(confirmedGroup.querySelectorAll("[data-event-row]")).toHaveLength(2);
    expect(confirmedGroup.textContent).toContain("1 / 2");
    expect(confirmedGroup.textContent).not.toContain("Confirmed Three");

    confirmedGroup.querySelector('[aria-label="Next confirmed events page"]').click();
    await settle();
    expect(confirmedGroup.querySelectorAll("[data-event-row]")).toHaveLength(2);
    expect(confirmedGroup.textContent).toContain("Confirmed Three");
    expect(confirmedGroup.textContent).toContain("Confirmed Four");

    confirmedGroup.querySelector('[data-event-row="confirmed-3"] button').click();
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-detail"));
    expect(router.currentRoute.value.params.id).toBe("confirmed-3");
  });

  it("opens a status-filtered events view from the status card header", async () => {
    const { el, router } = await mountDashboard();

    el.querySelector('[data-status-group="confirmed"] [aria-label="View all Confirmed events"]').click();
    await vi.waitFor(() => expect(router.currentRoute.value.query).toEqual({ tab: "events", status: "confirmed" }));
    el.querySelector('button[aria-label="Filter events by status"]').click();
    await settle();
    expect(el.querySelector('input[type="checkbox"][value="confirmed"]').checked).toBe(true);
  });

  it("filters the loaded collection by status and event name", async () => {
    const { el } = await mountDashboard();
    await openEvents(el);
    const statusToggle = el.querySelector('button[aria-label="Filter events by status"]');
    const search = el.querySelector('input[aria-label="Search events"]');

    statusToggle.click();
    await settle();
    const confirmed = el.querySelector('input[type="checkbox"][value="confirmed"]');
    confirmed.click();
    await settle();
    expect(el.textContent).toContain("Leadership Forum");
    expect(el.textContent).not.toContain("Annual Conference");

    confirmed.click();
    search.value = "product";
    search.dispatchEvent(new Event("input"));
    await settle();
    expect(el.textContent).toContain("Product Briefing");
    expect(el.textContent).not.toContain("Regional Workshop");
  });

  it("supports selecting multiple statuses from the status filter", async () => {
    const { el } = await mountDashboard();
    await openEvents(el);

    const statusToggle = el.querySelector('button[aria-label="Filter events by status"]');
    statusToggle.click();
    await settle();

    const confirmed = el.querySelector('input[type="checkbox"][value="confirmed"]');
    confirmed.checked = true;
    confirmed.dispatchEvent(new Event("change", { bubbles: true }));
    await settle();
    const returned = el.querySelector('input[type="checkbox"][value="returned"]');
    returned.checked = true;
    returned.dispatchEvent(new Event("change", { bubbles: true }));
    await settle();

    expect(el.textContent).toContain("Leadership Forum");
    expect(el.textContent).toContain("Product Briefing");
    expect(el.textContent).not.toContain("Annual Conference");
  });

  it("shows only the matching event section for a draft-only filter", async () => {
    const { el } = await mountDashboard();
    await openEvents(el);
    el.querySelector('button[aria-label="Filter events by status"]').click();
    await settle();

    const draft = el.querySelector('input[type="checkbox"][value="draft"]');
    draft.checked = true;
    draft.dispatchEvent(new Event("change", { bubbles: true }));
    await settle();

    expect(el.querySelector('[aria-labelledby="drafts-heading"]')).not.toBeNull();
    expect(el.querySelector('[aria-labelledby="requests-heading"]')).toBeNull();
  });

  it("hides drafts when the active filter contains only request statuses", async () => {
    const { el } = await mountDashboard();
    await openEvents(el);
    el.querySelector('button[aria-label="Filter events by status"]').click();
    await settle();

    const confirmed = el.querySelector('input[type="checkbox"][value="confirmed"]');
    confirmed.checked = true;
    confirmed.dispatchEvent(new Event("change", { bubbles: true }));
    await settle();

    expect(el.querySelector('[aria-labelledby="drafts-heading"]')).toBeNull();
    expect(el.querySelector('[aria-labelledby="requests-heading"]')).not.toBeNull();
  });

  it("uses a compact direction toggle without Any sort options", async () => {
    const { el } = await mountDashboard();
    await openEvents(el);

    const sortToggle = el.querySelector('button[aria-label="Sort events by"]');
    const direction = el.querySelector('button[aria-label^="Toggle sort direction"]');

    sortToggle.click();
    await settle();
    expect([...el.querySelectorAll('[role="option"]')].map((option) => option.textContent.trim())).toEqual(["Event date", "Event name", "Status"]);
    expect(direction.querySelector("img").getAttribute("src")).toContain("calendar-arrow-up");
    expect(direction.getAttribute("title")).toBe("Ascending by Event date");
    direction.click();
    await settle();
    expect(direction.querySelector("img").getAttribute("src")).toContain("calendar-arrow-down");
    expect(direction.getAttribute("title")).toBe("Descending by Event date");

    sortToggle.click();
    await settle();
    el.querySelector('[role="option"]:nth-child(2)').click();
    await settle();
    expect(direction.querySelector("img").getAttribute("src")).toContain("arrow-down-z-a");

    sortToggle.click();
    await settle();
    el.querySelector('[role="option"]:nth-child(3)').click();
    await settle();
    expect(direction.querySelector("img").getAttribute("src")).toContain("arrow-down-z-a");
  });

  it("sorts the currently displayed events without reloading them", async () => {
    const { el } = await mountDashboard();
    await openEvents(el);
    const names = () => [...el.querySelectorAll("[data-event-name] h3")].map((node) => node.textContent.trim());

    el.querySelector('button[aria-label="Sort events by"]').click();
    await settle();
    el.querySelector('[role="option"]:nth-child(2)').click();
    await settle();

    expect(names()).toEqual(["Regional Workshop", "Annual Conference", "Leadership Forum", "Product Briefing"]);
    expect(eventsApi.list).toHaveBeenCalledTimes(1);
  });

  it("opens a draft through the existing request flow and opens a new request from the dashboard", async () => {
    const { el, router } = await mountDashboard();
    await openEvents(el);

    buttonByText(el, "Edit draft").click();
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-new"));
    expect(router.currentRoute.value.name).toBe("event-new");
    expect(router.currentRoute.value.query.id).toBe("draft-1");

    await router.push({ name: "dashboard-organiser" });
    await settle();
    buttonByText(el, "New event request").click();
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-new"));
    expect(router.currentRoute.value.name).toBe("event-new");
  });

  it("opens a returned request on the request form to amend and resubmit (SCRUM-33)", async () => {
    const { el, router } = await mountDashboard();
    await openEvents(el);

    buttonByText(el, "Amend and resubmit").click();

    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-new"));
    expect(router.currentRoute.value.query.id).toBe("returned-1");
  });

  it("distinguishes loading from an empty successful dashboard", async () => {
    let resolveEvents;
    eventsApi.list.mockImplementation(() => new Promise((resolve) => {
      resolveEvents = resolve;
    }));

    const { el } = await mountDashboard();

    expect(el.querySelector('[role="status"]')?.textContent).toContain("Loading events...");
    expect(el.textContent).not.toContain("No drafts");
    expect(el.textContent).not.toContain("No submitted requests");

    resolveEvents([]);
    await vi.waitFor(() => expect(el.querySelector('[role="status"]')).toBeNull());
    await openEvents(el);
    expect(el.textContent).toContain("No event requests yet");
  });

  it("shows a server error instead of presenting an empty successful dashboard", async () => {
    eventsApi.list.mockRejectedValue(new ApiError("Unable to load events.", 503));

    const { el } = await mountDashboard();

    await vi.waitFor(() => expect(el.querySelector('[role="alert"]')).not.toBeNull());
    expect(el.textContent).toContain("Unable to load events.");
    expect(el.textContent).not.toContain("Regional Workshop");
    expect(el.textContent).not.toContain("No drafts");
    expect(el.textContent).not.toContain("No submitted requests");
  });
});
