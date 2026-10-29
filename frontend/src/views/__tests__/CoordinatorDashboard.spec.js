import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CoordinatorDashboard from "@/views/dashboards/CoordinatorDashboard.vue";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { coordinatorDashboard: vi.fn(), list: vi.fn(), get: vi.fn() },
}));

// Matches the padding the Events card lists keep for card shadows (CoordinatorDashboard.vue).
const CARD_LIST_SHADOW_ROOM = 8;

const UNDER_REVIEW_ID = "e0000000-0000-4000-8000-000000000201";
const PLANNING_ID = "e0000000-0000-4000-8000-000000000202";
const CONFIRMED_ID = "e0000000-0000-4000-8000-000000000203";
const REJECTED_ID = "e0000000-0000-4000-8000-000000000298";

// The shape `GET /events/dashboard/coordinator` returns (SCRUM-72).
const PAYLOAD = {
  action_items: [
    {
      event_id: UNDER_REVIEW_ID,
      event_name: "Partner Summit",
      kind: "awaiting_review",
      starts_at: "2026-10-05T02:00:00Z",
      occurred_at: "2026-09-23T12:53:07Z",
      organiser_name: "Olivia Tan",
    },
  ],
  active_events: [
    {
      event_id: UNDER_REVIEW_ID,
      event_name: "Partner Summit",
      status: "under_review",
      starts_at: "2026-10-05T02:00:00Z",
      flags: [],
      readiness: { venue: "pending", equipment: "not_required", technical: "not_required" },
    },
    {
      event_id: PLANNING_ID,
      event_name: "Year-End Dinner",
      status: "planning",
      starts_at: "2026-10-06T02:00:00Z",
      flags: [],
      readiness: { venue: "pending", equipment: "not_required", technical: "not_required" },
    },
    {
      event_id: CONFIRMED_ID,
      event_name: "Gala Night",
      status: "confirmed",
      starts_at: "2026-12-06T02:00:00Z",
      flags: [],
      readiness: { venue: "ready", equipment: "ready", technical: "ready" },
    },
  ],
};

async function flush() {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
    await nextTick();
  }
}

async function mountDashboard(path = "/dashboard/coordinator") {
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = { id: "c1", role: "event_coordinator", full_name: "Marcus Lim" };
  authStore.sessionVerified = true;
  const { default: router } = await import("@/router");
  await router.push(path);
  await router.isReady();
  const el = document.createElement("div");
  document.body.appendChild(el);
  createApp(CoordinatorDashboard).use(pinia).use(router).mount(el);
  await flush();
  return { el, router };
}

function input(el, value) {
  el.value = value;
  el.dispatchEvent(new Event("input"));
}

describe("CoordinatorDashboard", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    localStorage.clear();
    vi.clearAllMocks();
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-30T12:00:00+08:00"));
    eventsApi.coordinatorDashboard.mockResolvedValue(PAYLOAD);
  });

  describe("Overview (the default view)", () => {
    it("opens straight onto the event status board, with no welcome header or action list", async () => {
      const { el } = await mountDashboard();

      expect(el.textContent).not.toContain("Event Coordinator Dashboard");
      expect(el.textContent).not.toContain("Welcome");
      expect(el.textContent).not.toContain("Awaiting data");
      expect(el.textContent).not.toContain("Needs your action");
      expect(el.querySelector('[aria-label="Show Awaiting approval events"]')).toBeNull();
      expect(el.querySelector("ol")).toBeNull();
      expect(el.querySelector('[data-status-group="under_review"]').textContent).toContain("1");
      // Unassigned events are the Event Coordinator Lead's queue, not this dashboard's.
      expect(el.querySelector('[data-testid="unassigned-alert"]')).toBeNull();
      expect(el.textContent.toLowerCase()).not.toContain("awaiting assignment");
    });

    it("colours section headings red, blue, yellow in page order, like the organiser's", async () => {
      const { el } = await mountDashboard();
      const tones = ["active-events", "past-events", "rejected-events"].map((id) => el.querySelector(`h2#${id}`).dataset.tone);
      expect(tones).toEqual(["red", "blue", "yellow"]);
    });

    it("withholds every count until the first load settles (TC-DASH-003)", async () => {
      eventsApi.coordinatorDashboard.mockReturnValue(new Promise(() => {}));

      const { el } = await mountDashboard();

      expect(el.querySelector('[role="status"]').textContent).toMatch(/loading/i);
      expect(el.querySelector("[data-status-group]")).toBeNull();
    });

    it("shows a server failure instead of an empty dashboard (TC-DASH-004)", async () => {
      eventsApi.coordinatorDashboard.mockRejectedValue(new ApiError("Service unavailable", 503));

      const { el } = await mountDashboard();

      expect(el.querySelector('[role="alert"]').textContent).toContain("Service unavailable");
      expect(el.textContent).not.toContain("No outstanding actions");
    });

    it("lists events needing attention first in each column, highlighted in red, then the rest by date", async () => {
      const SECOND_PLANNING_ID = "e0000000-0000-4000-8000-000000000204";
      eventsApi.coordinatorDashboard.mockResolvedValue({
        action_items: [
          ...PAYLOAD.action_items,
          {
            event_id: SECOND_PLANNING_ID,
            event_name: "Board Retreat",
            kind: "needs_alternative_venue",
            starts_at: "2026-11-20T02:00:00Z",
            occurred_at: "2026-09-29T02:00:00Z",
            organiser_name: "Olivia Tan",
          },
        ],
        active_events: [
          ...PAYLOAD.active_events,
          {
            event_id: SECOND_PLANNING_ID,
            event_name: "Board Retreat",
            status: "planning",
            starts_at: "2026-11-20T02:00:00Z",
            flags: [],
            readiness: { venue: "pending", equipment: "not_required", technical: "not_required" },
          },
        ],
      });
      const { el } = await mountDashboard();
      const planning = el.querySelector('[data-status-group="planning"]');
      const names = [...planning.querySelectorAll("li a p:first-child")].map((p) => p.textContent.trim());

      // Board Retreat starts later but needs attention, so it leads the column.
      expect(names).toEqual(["Board Retreat", "Year-End Dinner"]);
      const retreat = planning.querySelector(`a[href="/coordinator/events/${SECOND_PLANNING_ID}"]`);
      const dinner = planning.querySelector(`a[href="/coordinator/events/${PLANNING_ID}"]`);
      expect(retreat.textContent).toContain("Needs alternative venue");
      expect(retreat.className).toContain("border-l-bauhaus-red");
      expect(dinner.className).not.toContain("border-l-bauhaus-red");
      expect(retreat.className).toContain("border-ink");
      expect(el.querySelector('[aria-label="Order status board by"]')).toBeNull();

      // A legend explains what the red highlight means.
      const legend = el.querySelector('[aria-labelledby="active-events"] [data-board-legend]');
      expect(legend.textContent).toContain("Red: needs your action");
      expect(legend.textContent).toContain("Grey: waiting on others");
      expect(legend.textContent).toContain("Green: confirmed");

      // A column holding anything that needs attention gets a red header; the rest stay grey.
      const header = (status) => el.querySelector(`[data-status-group="${status}"] [data-column-header]`);
      expect(header("planning").className).toContain("bg-bauhaus-red");
      expect(header("under_review").className).toContain("bg-bauhaus-red");
      expect(header("confirmed").className).toContain("bg-muted");
      // Cards, not columns, carry the tone: a confirmed event is green, one needing action red.
      const card = (id) => el.querySelector(`a[href="/coordinator/events/${id}"][data-tone]`);
      expect(card(SECOND_PLANNING_ID).dataset.tone).toBe("attention");
      expect(card(PLANNING_ID).dataset.tone).toBe("editable");
      expect(card(CONFIRMED_ID).dataset.tone).toBe("done");
      expect(card(CONFIRMED_ID).className).toContain("border-l-bauhaus-green");
      expect(el.querySelector('[data-status-group="confirmed"]').className).not.toContain("bauhaus-green");
    });

    it("lists every active status, each row opening its review page", async () => {
      const { el } = await mountDashboard();

      const groups = [...el.querySelectorAll("[data-status-group]")].map((group) => group.dataset.statusGroup);
      expect(groups).toEqual(["under_review", "returned", "planning", "safety_review", "confirmed", "preparation"]);
      const planning = el.querySelector('[data-status-group="planning"]');
      expect(planning.querySelector(`a[href="/coordinator/events/${PLANNING_ID}"]`).textContent).toContain(
        "Year-End Dinner",
      );
      expect(el.querySelector('[data-status-group="returned"]').textContent).toContain("None.");
    });

    it("opens the Events view filtered to a status from its card", async () => {
      const { el, router } = await mountDashboard();

      el.querySelector('[aria-label="View all Planning events"]').click();

      await vi.waitFor(() =>
        expect(router.currentRoute.value.query).toMatchObject({ tab: "events", status: "planning" }),
      );
    });

    it("moves confirmed events whose date has passed off the board into Past events", async () => {
      const PAST_ID = "e0000000-0000-4000-8000-000000000299";
      eventsApi.coordinatorDashboard.mockResolvedValue({
        ...PAYLOAD,
        active_events: [
          ...PAYLOAD.active_events,
          {
            event_id: PAST_ID,
            event_name: "Spring Mixer",
            status: "confirmed",
            starts_at: "2026-09-20T02:00:00Z",
            flags: [],
            readiness: { venue: "ready", equipment: "ready", technical: "ready" },
          },
        ],
      });
      const { el } = await mountDashboard();

      const board = el.querySelector('[aria-labelledby="active-events"]');
      expect(board.querySelector('[data-status-group="confirmed"]').textContent).not.toContain("Spring Mixer");
      expect(board.querySelector('[data-status-group="confirmed"]').textContent).toContain("Gala Night");
      expect(board.textContent).toContain("3 total");
      const past = el.querySelector('[aria-labelledby="past-events"]');
      expect(past.closest('[aria-labelledby="active-events"]')).toBeNull();
      expect(past.querySelector(`[data-event-card][href="/coordinator/events/${PAST_ID}"]`).dataset.tone).toBe("done");
      expect(past.textContent).toContain("1 total");
    });

    it("lists the coordinator's rejected events in their own section", async () => {
      eventsApi.coordinatorDashboard.mockResolvedValue({
        ...PAYLOAD,
        rejected_events: [{ event_id: REJECTED_ID, event_name: "Turned Down", starts_at: "2026-10-30T11:00:00Z" }],
      });
      const { el } = await mountDashboard();

      const rejected = el.querySelector('[aria-labelledby="rejected-events"]');
      expect(rejected.textContent).toContain("Rejected events");
      expect(rejected.textContent).toContain("1 total");
      expect(rejected.querySelector(`[data-event-card][href="/coordinator/events/${REJECTED_ID}"]`).dataset.tone).toBe(
        "rejected",
      );
      // It sits below Past events, and the board does not count it.
      const past = el.querySelector('[aria-labelledby="past-events"]');
      expect(past.compareDocumentPosition(rejected) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(el.querySelector('[aria-labelledby="active-events"]').textContent).not.toContain("Turned Down");
    });

    it("says when there are no rejected events", async () => {
      const { el } = await mountDashboard();

      expect(el.querySelector('[aria-labelledby="rejected-events"]').textContent).toContain("No rejected events");
    });

    it("has no readiness gaps section", async () => {
      const { el } = await mountDashboard();

      expect(el.querySelector('[aria-labelledby="readiness"]')).toBeNull();
      expect(el.textContent).not.toContain("Readiness gaps");
    });
  });

  describe("Events view", () => {
    it("continues the red, blue, yellow order down the Events view", async () => {
      const { el } = await mountDashboard("/dashboard/coordinator?tab=events");
      const ids = ["needs-action-events", "in-progress-events", "past-events", "rejected-events"];
      expect(ids.map((id) => el.querySelector(`h2#${id}`).dataset.tone)).toEqual(["red", "blue", "yellow", "red"]);
    });

    it("shows a card per assigned event, split by whether it needs action", async () => {
      const { el } = await mountDashboard("/dashboard/coordinator?tab=events");

      expect(el.textContent).toContain("Find an event");
      expect(el.querySelector('[aria-labelledby="event-filters"]').className).toContain("bg-muted");
      // The Events view opens straight onto its filters, with no header card.
      expect(el.textContent).not.toContain("Events I'm coordinating");
      expect(el.textContent).not.toContain("Search venues");
      const needsAction = el.querySelector('[aria-labelledby="needs-action-events"]');
      const inProgress = el.querySelector('[aria-labelledby="in-progress-events"]');
      expect(needsAction.textContent).toContain("Partner Summit");
      expect(needsAction.textContent).toContain("Awaiting first review");
      expect(inProgress.textContent).toContain("Year-End Dinner");
      expect(inProgress.textContent).toContain("Gala Night");
    });

    it("shows needs-action and in-progress side by side, cards coloured like the status board", async () => {
      const { el } = await mountDashboard("/dashboard/coordinator?tab=events");
      const card = (id) => el.querySelector(`[data-event-card][href="/coordinator/events/${id}"]`);

      const columns = el.querySelector("[data-card-columns]");
      expect(columns.className).toContain("lg:grid-cols-2");
      expect([...columns.children].map((section) => section.getAttribute("aria-labelledby"))).toEqual([
        "needs-action-events",
        "in-progress-events",
      ]);
      expect(el.querySelector('[aria-labelledby="in-progress-events"] [data-card-grid]').className).not.toContain("grid-cols-3");
      expect(card(UNDER_REVIEW_ID).dataset.tone).toBe("attention");
      expect(card(UNDER_REVIEW_ID).querySelector("[data-action-badge]").textContent).toContain("Awaiting first review");
      expect(card(PLANNING_ID).dataset.tone).toBe("editable");
      expect([...card(PLANNING_ID).querySelectorAll("[data-outstanding]")].map((chip) => chip.textContent.trim())).toEqual([
        "Venue",
      ]);
      expect(card(CONFIRMED_ID).dataset.tone).toBe("done");
      expect(card(CONFIRMED_ID).textContent).toContain("All arrangements in place");
      expect(card(CONFIRMED_ID).querySelector("[data-outstanding]")).toBeNull();
    });

    it("lists Past and Rejected events one per row, three before scrolling", async () => {
      const rejected = Array.from({ length: 6 }, (_, i) => ({
        event_id: `e0000000-0000-4000-8000-0000000004${String(i).padStart(2, "0")}`,
        event_name: `Refused ${i}`,
        starts_at: "2026-11-01T02:00:00Z",
      }));
      eventsApi.coordinatorDashboard.mockResolvedValue({ ...PAYLOAD, rejected_events: rejected });
      const rect = vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function () {
        if (this.matches("[data-capped-rows] > li")) {
          const top = [...this.parentElement.children].indexOf(this) * 100;
          return { top, bottom: top + 90 };
        }
        return { top: 0, bottom: 0 };
      });

      const { el } = await mountDashboard();
      rect.mockRestore();

      const list = el.querySelector('[aria-labelledby="rejected-events"] [data-capped-rows]');
      expect(list.className).toContain("overflow-y-auto");
      expect(list.className).not.toMatch(/grid-cols-[23]/);
      // The third card ends at 290px.
      expect(list.style.maxHeight).toBe(`${290 + CARD_LIST_SHADOW_ROOM}px`);
    });

    it("caps each column at four cards and scrolls the rest", async () => {
      const extra = Array.from({ length: 4 }, (_, i) => ({
        event_id: `e0000000-0000-4000-8000-00000000030${i}`,
        event_name: `Extra Event ${i}`,
        status: "planning",
        starts_at: `2026-11-0${i + 1}T02:00:00Z`,
        flags: [],
        readiness: { venue: "ready", equipment: "ready", technical: "ready" },
      }));
      eventsApi.coordinatorDashboard.mockResolvedValue({ ...PAYLOAD, active_events: [...PAYLOAD.active_events, ...extra] });
      // jsdom has no layout: give each card a 100px slot, 90px tall, and the list a top of 0.
      const rect = vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function () {
        if (this.matches("[data-card-grid] > li")) {
          const index = [...this.parentElement.children].indexOf(this);
          return { top: index * 100, bottom: index * 100 + 90 };
        }
        return { top: 0, bottom: 0 };
      });

      const { el } = await mountDashboard("/dashboard/coordinator?tab=events");
      const inProgress = el.querySelector('[aria-labelledby="in-progress-events"] [data-card-grid]');
      const needsAction = el.querySelector('[aria-labelledby="needs-action-events"] [data-card-grid]');
      rect.mockRestore();

      expect(inProgress.children).toHaveLength(6);
      expect(inProgress.className).toContain("overflow-y-auto");
      // The fourth card ends at 390px; the list keeps room for the card shadows below it.
      expect(inProgress.style.maxHeight).toBe(`${390 + CARD_LIST_SHADOW_ROOM}px`);
      // One card needs no cap.
      expect(needsAction.style.maxHeight).toBe("");
    });

    it("lists confirmed events whose date has passed in a full-width Past events section", async () => {
      const PAST_ID = "e0000000-0000-4000-8000-000000000299";
      eventsApi.coordinatorDashboard.mockResolvedValue({
        action_items: [
          ...PAYLOAD.action_items,
          { event_id: PAST_ID, event_name: "Spring Mixer", kind: "needs_alternative_venue", starts_at: "2026-09-20T02:00:00Z" },
        ],
        active_events: [
          ...PAYLOAD.active_events,
          {
            event_id: PAST_ID,
            event_name: "Spring Mixer",
            status: "confirmed",
            starts_at: "2026-09-20T02:00:00Z",
            flags: [],
            readiness: { venue: "ready", equipment: "ready", technical: "ready" },
          },
        ],
      });
      const { el } = await mountDashboard("/dashboard/coordinator?tab=events");

      const past = el.querySelector('[aria-labelledby="past-events"]');
      expect(past.textContent).toContain("Past events");
      expect(past.textContent).toContain("1 total");
      expect(past.closest("[data-card-columns]")).toBeNull();
      const card = past.querySelector(`[data-event-card][href="/coordinator/events/${PAST_ID}"]`);
      expect(card.dataset.tone).toBe("done");
      // Nothing can be done about a past event, so it carries no action badge and leaves Needs your action.
      expect(card.querySelector("[data-action-badge]")).toBeNull();
      expect(el.querySelector('[aria-labelledby="needs-action-events"]').textContent).not.toContain("Spring Mixer");
      expect(el.querySelector('[aria-labelledby="in-progress-events"]').textContent).not.toContain("Spring Mixer");
    });

    it("says when there are no past events", async () => {
      const { el } = await mountDashboard("/dashboard/coordinator?tab=events");

      expect(el.querySelector('[aria-labelledby="past-events"]').textContent).toContain("No past events");
    });

    it("filters rejected events by name, and hides them under a status filter", async () => {
      eventsApi.coordinatorDashboard.mockResolvedValue({
        ...PAYLOAD,
        rejected_events: [{ event_id: REJECTED_ID, event_name: "Turned Down", starts_at: "2026-10-30T11:00:00Z" }],
      });
      const { el } = await mountDashboard("/dashboard/coordinator?tab=events");
      const rejected = () => el.querySelector('[aria-labelledby="rejected-events"]');
      expect(rejected().textContent).toContain("Turned Down");

      input(el.querySelector('input[placeholder="Search by event name"]'), "gala");
      await flush();
      expect(rejected().textContent).toContain("No rejected events");

      document.body.innerHTML = "";
      const filtered = await mountDashboard("/dashboard/coordinator?tab=events&status=planning");
      expect(filtered.el.querySelector('[aria-labelledby="rejected-events"]').textContent).not.toContain("Turned Down");
    });

    it("filters by name", async () => {
      const { el } = await mountDashboard("/dashboard/coordinator?tab=events");

      input(el.querySelector('input[placeholder="Search by event name"]'), "gala");
      await flush();

      expect(el.textContent).toContain("Gala Night");
      expect(el.textContent).not.toContain("Year-End Dinner");
    });

    it("applies the status and action filters from the route", async () => {
      const { el } = await mountDashboard("/dashboard/coordinator?tab=events&status=planning");
      expect(el.textContent).toContain("Year-End Dinner");
      expect(el.textContent).not.toContain("Gala Night");

      document.body.innerHTML = "";
      const second = await mountDashboard("/dashboard/coordinator?tab=events&action=awaitingApproval");
      expect(second.el.textContent).toContain("Partner Summit");
      expect(second.el.textContent).not.toContain("Year-End Dinner");
      expect(second.el.textContent).toContain("Awaiting approval");
    });

    it("says so when nothing matches", async () => {
      const { el } = await mountDashboard("/dashboard/coordinator?tab=events");

      input(el.querySelector('input[placeholder="Search by event name"]'), "no such event");
      await flush();

      expect(el.textContent).toContain("No matching events");
    });

    it("opens the review page when a card is clicked", async () => {
      const { el, router } = await mountDashboard("/dashboard/coordinator?tab=events");

      el.querySelector('a[aria-label="More details about Gala Night"]').click();

      await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe(`/coordinator/events/${CONFIRMED_ID}`));
    });

    it("renders exactly one card per assigned event", async () => {
      const { el } = await mountDashboard("/dashboard/coordinator?tab=events");

      expect(el.querySelectorAll("[data-event-card]").length).toBe(3);
    });
  });
});
