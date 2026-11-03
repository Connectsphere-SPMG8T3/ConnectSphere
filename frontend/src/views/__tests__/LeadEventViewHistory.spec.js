import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// SCRUM-81 AC4: the Lead sees an event's reassignments (from, to, by whom, when) on its page.
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { leadDashboard: vi.fn(), reassign: vi.fn(), assign: vi.fn(), reassignmentHistory: vi.fn() },
}));

const ASSIGNED_ID = "e0000000-0000-4000-8000-000000000302";

const PAYLOAD = {
  unassigned: [],
  active_events: [
    {
      event_id: ASSIGNED_ID, event_name: "Year-End Dinner", status: "planning", starts_at: "2026-12-12T02:00:00Z", version: 8,
      organiser_name: "Olivia Tan", purpose: null, expected_attendance: null,
      coordinator: { id: "c2", full_name: "Priya Nair" }, assigned_at: "2026-11-02T09:00:00Z",
    },
  ],
  coordinators: [
    { id: "c1", full_name: "Marcus Lim", active_count: 0 },
    { id: "c2", full_name: "Priya Nair", active_count: 1 },
  ],
};

const ENTRY = {
  id: "h1",
  kind: "reassignment",
  at: "2026-11-02T09:00:00Z",
  actor: { id: "l1", full_name: "Joyce Lim" },
  from_coordinator: { id: "c1", full_name: "Marcus Lim" },
  to_coordinator: { id: "c2", full_name: "Priya Nair" },
};

const mountedApps = [];

async function flush() {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
    await nextTick();
  }
}

async function mountView(eventId) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "l1", full_name: "Joyce Lim", role: "event_coordinator_lead" };
  auth.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "lead-event", params: { id: eventId } });
  const { default: View } = await import("@/views/events/LeadEventView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await flush();
  return el;
}

const section = (el) => el.querySelector('[data-testid="reassignment-history"]');

describe("LeadEventView reassignment history (SCRUM-81 AC4)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    eventsApi.leadDashboard.mockResolvedValue(PAYLOAD);
    eventsApi.reassignmentHistory.mockResolvedValue({ entries: [ENTRY] });
  });

  it("asks for this event's history with the Lead's session", async () => {
    await mountView(ASSIGNED_ID);

    expect(eventsApi.reassignmentHistory).toHaveBeenCalledWith(ASSIGNED_ID, "access");
  });

  it("lists each reassignment: to whom, from whom, by whom and when", async () => {
    const el = await mountView(ASSIGNED_ID);

    expect(section(el).querySelector("h2").textContent).toBe("Reassignment history");
    const text = section(el).textContent;
    expect(text).toContain("Reassigned to Priya Nair");
    expect(text).toContain("from Marcus Lim");
    expect(text).toContain("by Joyce Lim");
    expect(text).toContain("2 Nov 2026");
  });

  it("says so when the event has never been reassigned", async () => {
    eventsApi.reassignmentHistory.mockResolvedValue({ entries: [] });

    const el = await mountView(ASSIGNED_ID);

    expect(section(el).textContent).toContain("No reassignments yet.");
    expect(section(el).textContent).not.toContain("No status changes");
  });

  it("shows why it could not load, without hiding the event or the reassign control", async () => {
    eventsApi.reassignmentHistory.mockRejectedValue(new ApiError("Something went wrong.", 500));

    const el = await mountView(ASSIGNED_ID);

    expect(section(el).textContent).toContain("Something went wrong.");
    expect(section(el).textContent).not.toContain("No reassignments yet.");
    expect(el.textContent).toContain("Year-End Dinner");
    expect(el.querySelector('button[aria-label="Reassign event"]')).not.toBeNull();
  });

  it("is not shown for an event outside the Lead's scope", async () => {
    const el = await mountView("e0000000-0000-4000-8000-0000000000ff");

    expect(el.textContent).toContain("This event isn't in your scope");
    expect(section(el)).toBeNull();
  });
});
