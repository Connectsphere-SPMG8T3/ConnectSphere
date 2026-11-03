import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLeadDashboardStore } from "@/features/events/leadDashboardStore";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// SCRUM-81 AC4: the Lead's read-only reassignment history for one event.
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  eventsApi: { leadDashboard: vi.fn(), reassign: vi.fn(), assign: vi.fn(), reassignmentHistory: vi.fn() },
}));

const ENTRY = {
  id: "h1",
  kind: "reassignment",
  at: "2026-11-02T09:00:00Z",
  actor: { id: "l1", full_name: "Joyce Lim" },
  from_coordinator: { id: "c1", full_name: "Marcus Lim" },
  to_coordinator: { id: "c2", full_name: "Priya Nair" },
};

function signedInLead() {
  const auth = useAuthStore();
  auth.token = "access-token";
  auth.profile = { id: "l1", role: "event_coordinator_lead", full_name: "Joyce" };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("lead dashboard store: reassignment history", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("loads the entries for the event", async () => {
    signedInLead();
    eventsApi.reassignmentHistory.mockResolvedValue({ entries: [ENTRY] });
    const store = useLeadDashboardStore();

    await store.loadHistory("e2");

    expect(eventsApi.reassignmentHistory).toHaveBeenCalledWith("e2", "access-token");
    expect(store.history).toEqual([ENTRY]);
    expect(store.historyError).toBeNull();
    expect(store.isLoadingHistory).toBe(false);
  });

  it("treats a payload without entries as empty", async () => {
    signedInLead();
    eventsApi.reassignmentHistory.mockResolvedValue({});
    const store = useLeadDashboardStore();

    await store.loadHistory("e2");

    expect(store.history).toEqual([]);
  });

  it("does not call the API when nobody is signed in", async () => {
    const store = useLeadDashboardStore();

    await store.loadHistory("e2");

    expect(eventsApi.reassignmentHistory).not.toHaveBeenCalled();
    expect(store.history).toEqual([]);
  });

  it("keeps the server's message when the load fails, and shows no entries", async () => {
    signedInLead();
    eventsApi.reassignmentHistory.mockRejectedValue(new ApiError("That event is managed by another Lead.", 403));
    const store = useLeadDashboardStore();
    store.history = [ENTRY];

    await store.loadHistory("e2");

    expect(store.history).toEqual([]);
    expect(store.historyError).toBe("That event is managed by another Lead.");
    expect(store.isLoadingHistory).toBe(false);
  });

  it("explains a network failure in plain words", async () => {
    signedInLead();
    eventsApi.reassignmentHistory.mockRejectedValue(new TypeError("Failed to fetch"));
    const store = useLeadDashboardStore();

    await store.loadHistory("e2");

    expect(store.historyError).toBe("Unable to reach the server. Please try again.");
  });

  it("ignores a slow response for an event the Lead has since left", async () => {
    signedInLead();
    const slow = deferred();
    eventsApi.reassignmentHistory.mockReturnValueOnce(slow.promise).mockResolvedValueOnce({ entries: [] });
    const store = useLeadDashboardStore();

    const first = store.loadHistory("e1");
    await store.loadHistory("e2");
    slow.resolve({ entries: [ENTRY] });
    await first;

    expect(store.history).toEqual([]);
    expect(store.historyEventId).toBe("e2");
  });

  it("ignores a failure that arrives after the Lead has moved on", async () => {
    signedInLead();
    let fail;
    eventsApi.reassignmentHistory.mockReturnValueOnce(new Promise((_, reject) => { fail = reject; }));
    const store = useLeadDashboardStore();

    const pending = store.loadHistory("e1");
    store.reset();
    fail(new ApiError("late", 500));
    await pending;

    expect(store.historyError).toBeNull();
    expect(store.isLoadingHistory).toBe(false);
  });

  it("forgets the history on reset", () => {
    const store = useLeadDashboardStore();
    store.history = [ENTRY];
    store.historyEventId = "e2";
    store.historyError = "boom";
    store.isLoadingHistory = true;

    store.reset();

    expect(store.history).toEqual([]);
    expect(store.historyEventId).toBeNull();
    expect(store.historyError).toBeNull();
    expect(store.isLoadingHistory).toBe(false);
  });
});
