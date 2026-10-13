import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLeadDashboardStore } from "@/features/events/leadDashboardStore";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  eventsApi: { leadDashboard: vi.fn(), reassign: vi.fn() },
}));

const PAYLOAD = {
  unassigned: [{ event_id: "e1", event_name: "Queue Event", status: "under_review", coordinator: null }],
  active_events: [
    { event_id: "e2", event_name: "Assigned Event", status: "planning", coordinator: { id: "c1", full_name: "Marcus Lim" } },
  ],
  coordinators: [{ id: "c1", full_name: "Marcus Lim", active_count: 1 }],
};

function signedInLead() {
  const auth = useAuthStore();
  auth.token = "access-token";
  auth.profile = { id: "l1", role: "event_coordinator_lead", full_name: "Joyce" };
}

describe("lead dashboard store", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("loads the queue, active events and coordinators", async () => {
    signedInLead();
    eventsApi.leadDashboard.mockResolvedValue(PAYLOAD);
    const store = useLeadDashboardStore();

    await store.load();

    expect(eventsApi.leadDashboard).toHaveBeenCalledWith("access-token");
    expect(store.unassigned).toHaveLength(1);
    expect(store.activeEvents).toHaveLength(1);
    expect(store.coordinators).toHaveLength(1);
    expect(store.allEvents.map((e) => e.event_id)).toEqual(["e1", "e2"]);
    expect(store.eventById("e2").event_name).toBe("Assigned Event");
    expect(store.eventById("missing")).toBeUndefined();
    expect(store.hasSettled).toBe(true);
    expect(store.error).toBeNull();
  });

  it("settles without calling the API when nobody is signed in", async () => {
    const store = useLeadDashboardStore();

    await store.load();

    expect(eventsApi.leadDashboard).not.toHaveBeenCalled();
    expect(store.hasSettled).toBe(true);
  });

  it("treats a payload with missing lists as empty", async () => {
    signedInLead();
    eventsApi.leadDashboard.mockResolvedValue({});
    const store = useLeadDashboardStore();

    await store.load();

    expect(store.unassigned).toEqual([]);
    expect(store.activeEvents).toEqual([]);
    expect(store.coordinators).toEqual([]);
  });

  it("shows an error and clears stale rows when the load fails", async () => {
    signedInLead();
    const store = useLeadDashboardStore();
    eventsApi.leadDashboard.mockResolvedValueOnce(PAYLOAD);
    await store.load();
    eventsApi.leadDashboard.mockRejectedValueOnce(new ApiError("Insufficient role", 403));

    await store.load();

    expect(store.error).toBe("Insufficient role");
    expect(store.unassigned).toEqual([]);
    expect(store.activeEvents).toEqual([]);
    expect(store.coordinators).toEqual([]);
    expect(store.hasSettled).toBe(true);
  });

  it("reports a network failure in plain words", async () => {
    signedInLead();
    eventsApi.leadDashboard.mockRejectedValue(new TypeError("Failed to fetch"));
    const store = useLeadDashboardStore();

    await store.load();

    expect(store.error).toBe("Unable to reach the server. Please try again.");
  });

  it("reassigns, then reloads, and returns true", async () => {
    signedInLead();
    eventsApi.leadDashboard.mockResolvedValue(PAYLOAD);
    eventsApi.reassign.mockResolvedValue({ id: "e1" });
    const store = useLeadDashboardStore();

    expect(await store.reassign("e1", "c1")).toBe(true);

    expect(eventsApi.reassign).toHaveBeenCalledWith("e1", "c1", "access-token");
    expect(eventsApi.leadDashboard).toHaveBeenCalledTimes(1);
    expect(store.reassignError).toBeNull();
    expect(store.isReassigning).toBe(false);
  });

  it("keeps the server's reason when a reassign is refused, and returns false", async () => {
    signedInLead();
    eventsApi.reassign.mockRejectedValue(new ApiError("This event was updated by someone else. Reload.", 409));
    const store = useLeadDashboardStore();

    expect(await store.reassign("e1", "c1")).toBe(false);

    expect(store.reassignError).toBe("This event was updated by someone else. Reload.");
    expect(store.isReassigning).toBe(false);
    expect(eventsApi.leadDashboard).not.toHaveBeenCalled();
  });

  it("reports a network failure while reassigning", async () => {
    signedInLead();
    eventsApi.reassign.mockRejectedValue(new TypeError("Failed to fetch"));
    const store = useLeadDashboardStore();

    expect(await store.reassign("e1", "c1")).toBe(false);

    expect(store.reassignError).toBe("Unable to reach the server. Please try again.");
  });
});
