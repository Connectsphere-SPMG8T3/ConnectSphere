import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CoordinatorDashboard from "@/views/dashboards/CoordinatorDashboard.vue";
import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { coordinatorDashboard: vi.fn(), list: vi.fn(), get: vi.fn() },
}));

const UNDER_REVIEW_ID = "e0000000-0000-4000-8000-000000000201";
const PLANNING_ID = "e0000000-0000-4000-8000-000000000202";

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
  ],
  unassigned_count: 7,
};

async function mountDashboard() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = { id: "c1", role: "event_coordinator", full_name: "Marcus Lim" };
  authStore.sessionVerified = true;
  const { default: router } = await import("@/router");
  await router.push("/dashboard/coordinator");
  await router.isReady();
  const el = document.createElement("div");
  document.body.appendChild(el);
  createApp(CoordinatorDashboard).use(pinia).use(router).mount(el);
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
    await nextTick();
  }
  return el;
}

function reviewLinks(el, eventId) {
  return [...el.querySelectorAll(`a[href="/coordinator/events/${eventId}"]`)];
}

describe("CoordinatorDashboard with real data (SCRUM-72)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    localStorage.clear();
    vi.clearAllMocks();
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-30T12:00:00+08:00"));
    eventsApi.coordinatorDashboard.mockResolvedValue(PAYLOAD);
  });

  it("renders the payload instead of the awaiting-data notice", async () => {
    const el = await mountDashboard();

    expect(el.textContent).not.toContain("Awaiting data");
    expect(el.textContent).toContain("Partner Summit");
    expect(el.textContent).toContain("Olivia Tan");
    expect(el.textContent).toContain("7");
  });

  it("links each action item to the coordinator review page", async () => {
    const el = await mountDashboard();

    const [actionLink] = reviewLinks(el, UNDER_REVIEW_ID);
    expect(actionLink?.closest("ol")).not.toBeNull();
    expect(actionLink.textContent).toContain("Partner Summit");
  });

  it("links each active event, under its status, to the review page", async () => {
    const el = await mountDashboard();

    const planningLinks = reviewLinks(el, PLANNING_ID);
    expect(planningLinks.length).toBeGreaterThan(0);
    expect(planningLinks[0].textContent).toContain("Year-End Dinner");
    // Under review appears both as an action item and in the status overview.
    expect(reviewLinks(el, UNDER_REVIEW_ID).length).toBeGreaterThanOrEqual(2);
  });

  it("links a readiness gap to the review page", async () => {
    const el = await mountDashboard();

    const gapSection = el.querySelector('[aria-labelledby="readiness"]');
    expect(gapSection.querySelector(`a[href="/coordinator/events/${PLANNING_ID}"]`)).not.toBeNull();
  });
});
