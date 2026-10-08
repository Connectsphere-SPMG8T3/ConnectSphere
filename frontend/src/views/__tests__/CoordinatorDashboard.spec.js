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

const UNDER_REVIEW_ID = "e0000000-0000-4000-8000-000000000201";
const PLANNING_ID = "e0000000-0000-4000-8000-000000000202";
const CONFIRMED_ID = "e0000000-0000-4000-8000-000000000203";

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
    it("shows the coordinator's header and counts from the payload", async () => {
      const { el } = await mountDashboard();

      expect(el.textContent).toContain("Event Coordinator Dashboard");
      expect(el.textContent).toContain("Welcome, Marcus Lim");
      expect(el.textContent).not.toContain("Awaiting data");
      const awaiting = el.querySelector('[aria-label="Show Awaiting approval events"]');
      expect(awaiting.textContent).toContain("1");
      // Unassigned events are the Event Coordinator Lead's queue, not this dashboard's.
      expect(el.querySelector('[data-testid="unassigned-alert"]')).toBeNull();
      expect(el.textContent.toLowerCase()).not.toContain("awaiting assignment");
    });

    it("withholds every count until the first load settles (TC-DASH-003)", async () => {
      eventsApi.coordinatorDashboard.mockReturnValue(new Promise(() => {}));

      const { el } = await mountDashboard();

      expect(el.querySelector('[role="status"]').textContent).toMatch(/loading/i);
      expect(el.querySelector('[aria-label="Show Awaiting approval events"]')).toBeNull();
    });

    it("shows a server failure instead of an empty dashboard (TC-DASH-004)", async () => {
      eventsApi.coordinatorDashboard.mockRejectedValue(new ApiError("Service unavailable", 503));

      const { el } = await mountDashboard();

      expect(el.querySelector('[role="alert"]').textContent).toContain("Service unavailable");
      expect(el.textContent).not.toContain("No outstanding actions");
    });

    it("opens the Events view filtered to a category when its tile is clicked", async () => {
      const { el, router } = await mountDashboard();

      el.querySelector('[aria-label="Show Awaiting approval events"]').click();

      await vi.waitFor(() =>
        expect(router.currentRoute.value.query).toMatchObject({ tab: "events", action: "awaitingApproval" }),
      );
    });

    it("links each prioritised action to the coordinator review page", async () => {
      const { el } = await mountDashboard();

      const actionLink = el.querySelector(`ol a[href="/coordinator/events/${UNDER_REVIEW_ID}"]`);
      expect(actionLink.textContent).toContain("Partner Summit");
      expect(actionLink.textContent).toContain("Olivia Tan");
    });

    it("lists every active status, each row opening its review page", async () => {
      const { el } = await mountDashboard();

      const groups = [...el.querySelectorAll("[data-status-group]")].map((group) => group.dataset.statusGroup);
      expect(groups).toEqual(["under_review", "returned", "planning", "safety_review", "confirmed"]);
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

    it("links a readiness gap to the review page", async () => {
      const { el } = await mountDashboard();

      const gaps = el.querySelector('[aria-labelledby="readiness"]');
      expect(gaps.querySelector(`a[href="/coordinator/events/${PLANNING_ID}"]`)).not.toBeNull();
      // Fully ready, and outside the 14-day window anyway.
      expect(gaps.querySelector(`a[href="/coordinator/events/${CONFIRMED_ID}"]`)).toBeNull();
    });
  });

  describe("Events view", () => {
    it("shows a card per assigned event, split by whether it needs action", async () => {
      const { el } = await mountDashboard("/dashboard/coordinator?tab=events");

      expect(el.textContent).toContain("Find an event");
      const needsAction = el.querySelector('[aria-labelledby="needs-action-events"]');
      const inProgress = el.querySelector('[aria-labelledby="in-progress-events"]');
      expect(needsAction.textContent).toContain("Partner Summit");
      expect(needsAction.textContent).toContain("Awaiting first review");
      expect(inProgress.textContent).toContain("Year-End Dinner");
      expect(inProgress.textContent).toContain("Outstanding: Venue");
      expect(inProgress.textContent).toContain("Gala Night");
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

    it("opens the review page from a card's Review button", async () => {
      const { el, router } = await mountDashboard("/dashboard/coordinator?tab=events");

      const button = [...el.querySelectorAll("button")].find(
        (candidate) => candidate.getAttribute("aria-label") === "Review Gala Night",
      );
      button.click();

      await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe(`/coordinator/events/${CONFIRMED_ID}`));
    });

    it("renders exactly one card per assigned event", async () => {
      const { el } = await mountDashboard("/dashboard/coordinator?tab=events");

      expect(el.querySelectorAll("[data-event-card]").length).toBe(3);
    });
  });
});
