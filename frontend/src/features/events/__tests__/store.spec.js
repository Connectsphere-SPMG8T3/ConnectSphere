import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCoordinatorDashboardStore } from "@/features/events/store";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  eventsApi: { coordinatorDashboard: vi.fn() },
}));

const PAYLOAD = {
  action_items: [
    {
      event_id: "e2",
      event_name: "Product Launch",
      kind: "awaiting_review",
      status: "under_review",
      starts_at: "2026-11-02T02:00:00Z",
      occurred_at: "2026-09-30T02:00:00Z",
    },
    {
      event_id: "e1",
      event_name: "Annual Conference",
      kind: "cancellation_request",
      status: "planning",
      starts_at: "2026-11-01T02:00:00Z",
      occurred_at: "2026-09-29T02:00:00Z",
    },
  ],
  active_events: [
    {
      event_id: "e1",
      event_name: "Annual Conference",
      status: "planning",
      starts_at: "2026-11-01T02:00:00Z",
      readiness: { venue: "pending", equipment: "ready", technical: "ready" },
      flags: [],
    },
  ],
};

function signedInCoordinator() {
  const auth = useAuthStore();
  auth.token = "access-token";
  auth.profile = { id: "c1", role: "event_coordinator", full_name: "Marcus Lim" };
  return auth;
}

describe("coordinator dashboard store", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("loads the dashboard and exposes actions in priority order", async () => {
    signedInCoordinator();
    eventsApi.coordinatorDashboard.mockResolvedValue(PAYLOAD);
    const store = useCoordinatorDashboardStore();

    await store.load();

    expect(eventsApi.coordinatorDashboard).toHaveBeenCalledWith("access-token");
    // Cancellation outranks an initial review, so e1 comes first despite
    // arriving second in the payload.
    expect(store.prioritisedActions.map((item) => item.event_id)).toEqual(["e1", "e2"]);
    expect(store.$state).not.toHaveProperty("unassignedCount");
    expect(store.error).toBeNull();
  });

  it("derives the status overview and readiness gaps from the loaded events", async () => {
    signedInCoordinator();
    eventsApi.coordinatorDashboard.mockResolvedValue(PAYLOAD);
    const store = useCoordinatorDashboardStore();

    await store.load();

    const planning = store.statusGroups.find((group) => group.status === "planning");
    expect(planning.events).toHaveLength(1);
    expect(store.readinessGaps({ now: new Date("2026-10-25T00:00:00Z") })).toHaveLength(1);
  });

  it("treats a 404 as 'not built yet' and shows empty widgets without an error", async () => {
    // The events module has no `GET /events/dashboard/coordinator` route yet.
    // Until it ships, the dashboard must read as empty rather than broken.
    signedInCoordinator();
    eventsApi.coordinatorDashboard.mockRejectedValue(new ApiError("Not Found", 404));
    const store = useCoordinatorDashboardStore();

    await store.load();

    expect(store.error).toBeNull();
    expect(store.isAvailable).toBe(false);
    expect(store.prioritisedActions).toEqual([]);
    expect(store.statusGroups.every((group) => group.events.length === 0)).toBe(true);
  });

  it("surfaces a real failure so the coordinator is not shown a falsely empty queue", async () => {
    signedInCoordinator();
    eventsApi.coordinatorDashboard.mockRejectedValue(new ApiError("Service unavailable.", 503));
    const store = useCoordinatorDashboardStore();

    await store.load();

    expect(store.error).toBe("Service unavailable.");
    expect(store.isAvailable).toBe(false);
  });

  it("does not call the API when there is no session", async () => {
    const store = useCoordinatorDashboardStore();

    await store.load();

    expect(eventsApi.coordinatorDashboard).not.toHaveBeenCalled();
  });

  it("clears a previous error when a later load succeeds", async () => {
    signedInCoordinator();
    const store = useCoordinatorDashboardStore();
    eventsApi.coordinatorDashboard.mockRejectedValueOnce(new ApiError("Service unavailable.", 503));
    await store.load();
    expect(store.error).toBe("Service unavailable.");

    eventsApi.coordinatorDashboard.mockResolvedValue(PAYLOAD);
    await store.load();

    expect(store.error).toBeNull();
    expect(store.isAvailable).toBe(true);
  });

  it("starts empty so a widget never renders invented figures before data arrives", () => {
    const store = useCoordinatorDashboardStore();

    expect(store.prioritisedActions).toEqual([]);
    expect(store.activeEvents).toEqual([]);
  });

  it("withholds its counts until a load has settled, so a zero is never guesswork", async () => {
    // Observed in the browser: the request takes seconds, and until it returns a
    // bare "0" reads as a fact the dashboard has not established yet.
    signedInCoordinator();
    let release;
    eventsApi.coordinatorDashboard.mockReturnValue(
      new Promise((resolve) => {
        release = () => resolve(PAYLOAD);
      }),
    );
    const store = useCoordinatorDashboardStore();

    const pending = store.load();
    expect(store.hasSettled).toBe(false);

    release();
    await pending;

    expect(store.hasSettled).toBe(true);
  });

  it("counts as settled even when the load failed, so the page stops showing a spinner", async () => {
    signedInCoordinator();
    eventsApi.coordinatorDashboard.mockRejectedValue(new ApiError("Not Found", 404));
    const store = useCoordinatorDashboardStore();

    await store.load();

    expect(store.hasSettled).toBe(true);
  });

  it("counts as settled when there is no session to load with", async () => {
    const store = useCoordinatorDashboardStore();

    await store.load();

    expect(store.hasSettled).toBe(true);
  });
});
