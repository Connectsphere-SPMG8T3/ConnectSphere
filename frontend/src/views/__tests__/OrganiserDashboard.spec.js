import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { useEventsStore } from "@/stores/events";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), submit: vi.fn(), clone: vi.fn() },
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
  // Only Date is faked, so timers and promises behave normally.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-01T00:00:00Z"));
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
    vi.useRealTimers();
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

  it("opens on the board without count tiles and switches to the full events tab", async () => {
    const { el, router } = await mountDashboard();

    expect(el.textContent).not.toContain("Needs your action");
    expect(el.querySelector('[aria-label="Show Drafts events"]')).toBeNull();
    expect(el.textContent).toContain("Under review");
    expect(el.textContent).toContain("Event status");

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

  it("uses the shared gray hover on event cards whatever their status rail color", async () => {
    const { el } = await mountDashboard();
    await openEvents(el);

    const cardFor = (name) => [...el.querySelectorAll('[data-event-name]')]
      .find((node) => node.querySelector("h3")?.textContent.trim() === name)
      .closest(".border-4");
    const draftCard = cardFor("Regional Workshop");
    const returnedCard = cardFor("Product Briefing");
    const confirmedCard = cardFor("Leadership Forum");

    expect(draftCard.className).toContain("hover:bg-muted");
    expect(returnedCard.className).toContain("hover:bg-muted");
    expect(confirmedCard.className).toContain("hover:bg-muted");
    expect(draftCard.className).toContain("border-4");
    expect(draftCard.className).toContain("shadow-none");
    expect(draftCard.querySelector("button").className).toContain("shadow-none");
    expect(draftCard.querySelector("button").className).toContain("hover:bg-muted");
    expect(returnedCard.querySelector("button").className).toContain("shadow-none");
    expect(returnedCard.querySelector("button").className).toContain("hover:bg-muted");
    expect(confirmedCard.querySelector("button").className).toContain("hover:bg-muted");
  });

  it("has no welcome card on the Overview; New event request sits beside the Event status heading", async () => {
    const { el, router } = await mountDashboard();

    expect(el.textContent).not.toContain("Welcome,");
    expect(el.querySelector("h1").className).toContain("sr-only");
    const statusSection = el.querySelector('[aria-labelledby="my-events-status"]');
    const headingRow = statusSection.querySelector("#my-events-status").parentElement;
    const button = headingRow.querySelector('button[aria-label="New event request"]');
    expect(button.textContent.trim()).toBe("+ Request");
    expect(el.querySelectorAll('button[aria-label="New event request"]')).toHaveLength(1);

    button.click();
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-new"));
  });

  it("colours section headings red, blue, yellow in page order", async () => {
    const { el } = await mountDashboard();
    const tones = (ids) => ids.map((id) => el.querySelector(`h2#${id}`).dataset.tone);
    expect(tones(["my-events-status", "past-events", "rejected-events"])).toEqual(["red", "blue", "yellow"]);

    await openEvents(el);
    expect(tones(["drafts-heading", "requests-heading"])).toEqual(["red", "blue"]);
  });

  it("shows my events as the coordinator's kanban board, with a red Returned column", async () => {
    const { el } = await mountDashboard();

    const columns = [...el.querySelectorAll("[data-status-group]")].map((node) => node.dataset.statusGroup);
    expect(columns).toEqual(["draft", "under_review", "returned", "planning", "safety_review", "confirmed"]);
    expect(el.querySelector('[data-status-group="draft"] [data-event-row="draft-1"]').dataset.tone).toBe("editable");
    expect(el.querySelector("[data-board-legend]")).not.toBeNull();

    const returned = el.querySelector('[data-status-group="returned"]');
    expect(returned.querySelector("[data-column-header]").className).toContain("bg-bauhaus-red");
    const returnedCard = returned.querySelector('[data-event-row="returned-1"]');
    expect(returnedCard.dataset.tone).toBe("attention");
    expect(returnedCard.textContent).toContain("Amend and resubmit");

    const review = el.querySelector('[data-status-group="under_review"]');
    expect(review.querySelector("[data-column-header]").className).toContain("bg-muted");
    expect(review.querySelector('[data-event-row="review-1"]').dataset.tone).toBe("waiting");
    expect(el.querySelector('[data-event-row="confirmed-1"]').dataset.tone).toBe("done");
    expect(el.querySelector('[data-status-group="planning"]').textContent).toContain("None.");
  });

  it("lists every event in a status column, without pages, and opens the one picked", async () => {
    const { el, router, eventsStore } = await mountDashboard();
    eventsStore.events.push(
      { ...eventsStore.events[2], id: "confirmed-2", name: "Confirmed Two" },
      { ...eventsStore.events[2], id: "confirmed-3", name: "Confirmed Three" },
      { ...eventsStore.events[2], id: "confirmed-4", name: "Confirmed Four" },
    );
    await settle();

    const confirmedGroup = el.querySelector('[data-status-group="confirmed"]');
    expect(confirmedGroup.querySelectorAll("[data-event-row]")).toHaveLength(4);
    expect(confirmedGroup.querySelector('[aria-label="Next confirmed events page"]')).toBeNull();
    expect(el.textContent).toMatch(/7 total/);

    confirmedGroup.querySelector('[data-event-row="confirmed-3"]').click();
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-detail"));
    expect(router.currentRoute.value.params.id).toBe("confirmed-3");
  });

  it("opens drafts and returned requests on the request form, other board cards on the event page", async () => {
    const { el } = await mountDashboard();
    const href = (id) => el.querySelector(`[data-status-group] [data-event-row="${id}"]`).getAttribute("href");
    expect(href("draft-1")).toBe("/events/new?id=draft-1");
    expect(href("returned-1")).toBe("/events/new?id=returned-1");
    expect(href("review-1")).toBe("/events/review-1");
  });

  it("lists past or rejected events one per row, three before scrolling", async () => {
    const { el, eventsStore } = await mountDashboard();
    for (let i = 0; i < 6; i += 1) {
      eventsStore.events.push({ ...eventsStore.events[2], id: `rejected-${i}`, name: `Refused ${i}`, status: "rejected" });
    }
    // jsdom has no layout: one card a row, rows 100px apart, each card 90px tall.
    const rect = vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function () {
      if (this.matches("[data-capped-rows] > li")) {
        const top = [...this.parentElement.children].indexOf(this) * 100;
        return { top, bottom: top + 90 };
      }
      return { top: 0, bottom: 0 };
    });
    await settle();
    await settle();
    rect.mockRestore();

    const rejected = el.querySelector('[aria-labelledby="rejected-events"] [data-capped-rows]');
    expect(rejected.className).toContain("overflow-y-auto");
    expect(rejected.className).not.toMatch(/grid-cols-[23]/);
    expect(rejected.style.maxHeight).toBe("298px");
    expect(el.querySelector('[aria-labelledby="past-events"] [data-capped-rows]')).toBeNull();
  });

  it("puts past and rejected events in their own sections below the board", async () => {
    const { el, eventsStore } = await mountDashboard();
    expect(el.querySelector('[aria-labelledby="past-events"]').textContent).toContain("No past events");
    expect(el.querySelector('[aria-labelledby="rejected-events"]').textContent).toContain("No rejected events");

    eventsStore.events.push(
      { ...eventsStore.events[2], id: "completed-1", name: "Finished Expo", status: "completed" },
      { ...eventsStore.events[2], id: "confirmed-old", name: "Last Month Forum", date: "2026-09-15" },
      { ...eventsStore.events[2], id: "rejected-1", name: "Refused Gala", status: "rejected" },
    );
    await settle();

    const past = el.querySelector('[aria-labelledby="past-events"]');
    expect([...past.querySelectorAll("[data-event-row]")].map((node) => node.dataset.eventRow)).toEqual(["completed-1", "confirmed-old"]);
    expect(past.querySelector('[data-event-row="completed-1"]').dataset.tone).toBe("done");
    expect(past.textContent).toContain("2 total");

    const rejected = el.querySelector('[aria-labelledby="rejected-events"]');
    expect(rejected.querySelector('[data-event-row="rejected-1"]').dataset.tone).toBe("rejected");
    expect(rejected.textContent).toContain("Refused Gala");

    const board = el.querySelector("[data-board-legend]").parentElement;
    for (const id of ["completed-1", "confirmed-old", "rejected-1"]) {
      expect(board.querySelector(`[data-status-group] [data-event-row="${id}"]`)).toBeNull();
    }
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
    el.querySelector('button[aria-label="New event request"]').click();
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-new"));
    expect(router.currentRoute.value.name).toBe("event-new");
  });

  it("uses the copy icon to create and open a new template draft", async () => {
    const { el, router } = await mountDashboard();
    await openEvents(el);
    eventsApi.clone.mockResolvedValue({
      id: "cloned-1",
      status: "draft",
      name: "Annual Conference",
      event_timezone: "Asia/Singapore",
      facilities_required: [],
      registration_enabled: false,
    });

    const copyButton = el.querySelector('button[aria-label="Use Annual Conference as a template"]');
    expect(copyButton).not.toBeNull();
    expect(copyButton.querySelector("svg")).not.toBeNull();
    copyButton.click();

    await vi.waitFor(() => expect(eventsApi.clone).toHaveBeenCalledWith("review-1", "access"));
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-new"));
    expect(router.currentRoute.value.query.id).toBe("cloned-1");
  });

  it("opens mobile event actions from the three-dot menu", async () => {
    const { el, router } = await mountDashboard();
    await openEvents(el);

    const menuButton = el.querySelector('button[aria-label="Open actions for Regional Workshop"]');
    expect(menuButton).not.toBeNull();
    expect(menuButton.getAttribute("aria-expanded")).toBe("false");

    menuButton.click();
    await settle();

    expect(menuButton.getAttribute("aria-expanded")).toBe("true");
    const menu = menuButton.parentElement.querySelector('[role="menu"]');
    expect([...menu.querySelectorAll('[role="menuitem"]')].map((item) => item.textContent.trim())).toEqual([
      "Edit draft",
      "Use as template",
    ]);

    menu.querySelector('[role="menuitem"]').click();
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-new"));
    expect(router.currentRoute.value.query.id).toBe("draft-1");
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
