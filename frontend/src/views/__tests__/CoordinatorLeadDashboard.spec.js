import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CoordinatorLeadDashboard from "@/views/dashboards/CoordinatorLeadDashboard.vue";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { leadDashboard: vi.fn(), reassign: vi.fn() },
}));

const QUEUE_ID = "e0000000-0000-4000-8000-000000000301";
const PLANNING_ID = "e0000000-0000-4000-8000-000000000302";
const CONFIRMED_ID = "e0000000-0000-4000-8000-000000000303";

const MARCUS = { id: "c1", full_name: "Marcus Lim" };
const PRIYA = { id: "c2", full_name: "Priya Nair" };

// The shape `GET /events/dashboard/lead` returns (CR-101).
const PAYLOAD = {
  unassigned: [
    {
      event_id: QUEUE_ID, event_name: "Partner Summit", status: "under_review", starts_at: "2026-11-12T02:00:00Z",
      organiser_name: "Olivia Tan", coordinator: null,
    },
  ],
  active_events: [
    {
      event_id: PLANNING_ID, event_name: "Year-End Dinner", status: "planning", starts_at: "2026-12-12T02:00:00Z",
      organiser_name: "Olivia Tan", coordinator: MARCUS,
    },
    {
      event_id: CONFIRMED_ID, event_name: "Gala Night", status: "confirmed", starts_at: "2026-12-20T02:00:00Z",
      organiser_name: "Olivia Tan", coordinator: PRIYA,
    },
  ],
  coordinators: [
    { ...MARCUS, active_count: 1 },
    { ...PRIYA, active_count: 1 },
    { id: "c3", full_name: "Idle Person", active_count: 0 },
  ],
};

const mountedApps = [];

async function flush() {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
    await nextTick();
  }
}

async function mountDashboard() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "l1", role: "event_coordinator_lead", full_name: "Joyce Lim" };
  auth.sessionVerified = true;
  const { default: router } = await import("@/router");
  await router.push("/dashboard/coordinator-lead");
  await router.isReady();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(CoordinatorLeadDashboard).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await flush();
  return { el, router };
}

const activeSection = (el) => el.querySelector('[data-testid="active-events"]');
const queueSection = (el) => el.querySelector('[data-testid="unassigned-queue"]');
const rows = (section) => [...section.querySelectorAll("[data-lead-event]")].map((row) => row.dataset.leadEvent);

function pick(el, label, value) {
  const select = el.querySelector(`select[aria-label="${label}"]`);
  select.value = value;
  select.dispatchEvent(new Event("change"));
}

describe("CoordinatorLeadDashboard (CR-101)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    eventsApi.leadDashboard.mockResolvedValue(PAYLOAD);
  });

  it("welcomes the Lead", async () => {
    const { el } = await mountDashboard();

    expect(el.textContent).toContain("Event Coordinator Lead Dashboard");
    expect(el.textContent).toContain("Welcome, Joyce Lim");
  });

  it("withholds every figure until the first load settles", async () => {
    eventsApi.leadDashboard.mockReturnValue(new Promise(() => {}));

    const { el } = await mountDashboard();

    expect(el.querySelector('[role="status"]').textContent).toMatch(/loading/i);
    expect(queueSection(el)).toBeNull();
    expect(activeSection(el)).toBeNull();
  });

  it("shows a server failure instead of empty lists", async () => {
    eventsApi.leadDashboard.mockRejectedValue(new ApiError("Service unavailable", 503));

    const { el } = await mountDashboard();

    expect(el.querySelector('[role="alert"]').textContent).toContain("Service unavailable");
    expect(queueSection(el)).toBeNull();
    expect(el.textContent).not.toContain("No active events");
  });

  it("lists the unassigned queue with each event's status", async () => {
    const { el } = await mountDashboard();

    expect(rows(queueSection(el))).toEqual([QUEUE_ID]);
    expect(queueSection(el).textContent).toContain("Partner Summit");
    expect(queueSection(el).textContent).toContain("Under review");
  });

  it("lists the active events with their coordinator and status (AC1)", async () => {
    const { el } = await mountDashboard();

    expect(rows(activeSection(el))).toEqual([PLANNING_ID, CONFIRMED_ID]);
    const planning = activeSection(el).querySelector(`[data-lead-event="${PLANNING_ID}"]`);
    expect(planning.textContent).toContain("Year-End Dinner");
    expect(planning.textContent).toContain("Planning");
    expect(planning.textContent).toContain("Marcus Lim");
  });

  it("shows how many active events each coordinator has, including none (AC2)", async () => {
    const { el } = await mountDashboard();

    const chips = [...el.querySelectorAll('[data-testid="coordinator-counts"] li')].map((li) =>
      [...li.children].map((part) => part.textContent.trim()).join(" "),
    );
    expect(chips).toEqual(["Marcus Lim 1", "Priya Nair 1", "Idle Person 0"]);
  });

  it("filters the active events by coordinator (AC2)", async () => {
    const { el } = await mountDashboard();

    pick(el, "Filter events by coordinator", "c2");
    await flush();

    expect(rows(activeSection(el))).toEqual([CONFIRMED_ID]);
    // The shared queue is unaffected by an active-events filter.
    expect(rows(queueSection(el))).toEqual([QUEUE_ID]);
  });

  it("filters the active events by status (AC2)", async () => {
    const { el } = await mountDashboard();

    el.querySelector('button[aria-label="Filter events by status"]').click();
    await flush();
    el.querySelector('input[type="checkbox"][value="planning"]').click();
    await flush();

    expect(rows(activeSection(el))).toEqual([PLANNING_ID]);
  });

  it("says nothing matches, and Clear restores the list", async () => {
    const { el } = await mountDashboard();
    pick(el, "Filter events by coordinator", "c3");
    await flush();
    expect(activeSection(el).textContent).toContain("No matching events");

    [...el.querySelectorAll("button")].find((b) => b.textContent.trim() === "Clear").click();
    await flush();

    expect(rows(activeSection(el))).toEqual([PLANNING_ID, CONFIRMED_ID]);
  });

  it("searches active events by name", async () => {
    const { el } = await mountDashboard();

    const search = el.querySelector('input[placeholder="Search by event name"]');
    search.value = "gala";
    search.dispatchEvent(new Event("input"));
    await flush();

    expect(rows(activeSection(el))).toEqual([CONFIRMED_ID]);
  });

  it("links every event to its Lead page, where it can be reassigned (AC3)", async () => {
    const { el } = await mountDashboard();

    for (const id of [QUEUE_ID, PLANNING_ID, CONFIRMED_ID]) {
      expect(el.querySelector(`a[href="/lead/events/${id}"]`)).not.toBeNull();
    }
  });

  it("shows empty states, not zeros dressed as data, when there is nothing", async () => {
    eventsApi.leadDashboard.mockResolvedValue({ unassigned: [], active_events: [], coordinators: [] });

    const { el } = await mountDashboard();

    expect(queueSection(el).textContent).toContain("Nothing waiting to be assigned");
    expect(activeSection(el).textContent).toContain("No active events");
    expect(el.querySelector('[data-testid="coordinator-counts"]')).toBeNull();
  });
});
