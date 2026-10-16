import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { canApprove, canReject, canReturn, canSendForSafetyCheck, REJECT_REASON_MAX_LENGTH, useEventReviewStore } from "@/features/events/eventReviewStore";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  eventsApi: { safetyDecisions: vi.fn().mockResolvedValue([]), get: vi.fn(), history: vi.fn(), approve: vi.fn(), reject: vi.fn(), returnForAmendment: vi.fn(), sendForSafetyCheck: vi.fn(), setPrimarySpace: vi.fn(), clearPrimarySpace: vi.fn() },
}));

const EVENT = { id: "event-1", name: "Partner Summit", status: "under_review", version: 3 };
const ENTRY = { id: "h1", from_status: "under_review", to_status: "planning", actor: { id: "c1", full_name: "Marcus Lim" }, reason: null, at: "2026-09-24T03:00:00Z" };

function signedInCoordinator() {
  const auth = useAuthStore();
  auth.token = "access-token";
  auth.profile = { id: "c1", role: "event_coordinator", full_name: "Marcus Lim" };
}

describe("canApprove / canReject", () => {
  it("SCRUM-82 sends only ready planning events", () => {
    for (const [status, readiness, expected] of [["planning", true, true], ["planning", false, false], ["planning", null, false], ["safety_review", true, false]]) {
      expect(canSendForSafetyCheck({status, safety_readiness: readiness === null ? null : {ready: readiness}})).toBe(expected);
    }
  });
  it("allows approve only from under_review (SCRUM-34)", () => {
    expect(canApprove("under_review")).toBe(true);
    for (const status of ["draft", "submitted", "returned", "planning", "confirmed", "rejected", "cancelled", "completed"]) {
      expect(canApprove(status)).toBe(false);
    }
  });

  it("allows reject from under_review or planning only (SCRUM-52)", () => {
    expect(canReject("under_review")).toBe(true);
    expect(canReject("planning")).toBe(true);
    for (const status of ["draft", "submitted", "returned", "confirmed", "rejected", "cancelled", "completed"]) {
      expect(canReject(status)).toBe(false);
    }
  });

  it("allows return only from under_review (SCRUM-33)", () => {
    expect(canReturn("under_review")).toBe(true);
    for (const status of ["draft", "submitted", "returned", "planning", "confirmed", "rejected", "cancelled", "completed"]) {
      expect(canReturn(status)).toBe(false);
    }
  });

  it("caps the reason at the API's 1000 characters", () => {
    expect(REJECT_REASON_MAX_LENGTH).toBe(1000);
  });
});

describe("useEventReviewStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    signedInCoordinator();
  });

  it("SCRUM-82 sends and refreshes history", async () => {
    const store = useEventReviewStore(); store.event = {...EVENT, status: "planning"};
    eventsApi.sendForSafetyCheck.mockResolvedValue({...EVENT, status: "safety_review"});
    eventsApi.history.mockResolvedValue({entries: [ENTRY]});
    await store.sendForSafetyCheck();
    expect(eventsApi.sendForSafetyCheck).toHaveBeenCalledWith("event-1", "access-token");
    expect(store.event.status).toBe("safety_review"); expect(store.history).toEqual([ENTRY]);
  });
  it("CR-97 makes a space the primary venue and shows the event the API returns", async () => {
    const store = useEventReviewStore(); store.event = {...EVENT, status: "planning"}; store.historyEventId = EVENT.id;
    const updated = {...EVENT, status: "planning", spaces: [{id: "s1", label: "Main hall", is_primary: true}]};
    eventsApi.setPrimarySpace.mockResolvedValue(updated);
    eventsApi.history.mockResolvedValue({entries: []});
    await store.setPrimarySpace("s1");
    expect(eventsApi.setPrimarySpace).toHaveBeenCalledWith("event-1", "s1", "access-token");
    expect(store.event).toEqual(updated);
  });
  it("CR-97 clears the primary venue", async () => {
    const store = useEventReviewStore(); store.event = {...EVENT, status: "planning"}; store.historyEventId = EVENT.id;
    const updated = {...EVENT, status: "planning", spaces: [{id: "s1", is_primary: false}, {id: "s2", is_primary: false}]};
    eventsApi.clearPrimarySpace.mockResolvedValue(updated);
    eventsApi.history.mockResolvedValue({entries: []});
    await store.clearPrimarySpace();
    expect(eventsApi.clearPrimarySpace).toHaveBeenCalledWith("event-1", "access-token");
    expect(store.event).toEqual(updated);
  });
  it("SCRUM-82 reloads stale readiness while preserving the refusal", async () => {
    const store = useEventReviewStore(); store.event = {...EVENT, status: "planning"}; store.historyEventId = EVENT.id;
    eventsApi.sendForSafetyCheck.mockRejectedValue(new ApiError("Not ready", 409));
    eventsApi.get.mockResolvedValue({...EVENT, status: "planning", safety_readiness: {ready: false, missing: ["Changed"]}});
    eventsApi.history.mockResolvedValue({entries: []});
    await expect(store.sendForSafetyCheck()).rejects.toThrow("Not ready");
    expect(store.error).toBe("Not ready"); expect(store.event.safety_readiness.ready).toBe(false);
  });
  it("returns the request with a trimmed message and the flagged fields, then refreshes history", async () => {
    const store = useEventReviewStore();
    store.event = { ...EVENT };
    store.historyEventId = EVENT.id;
    const returnedEvent = { ...EVENT, status: "returned", version: 4,
      amendment: { id: "a1", message: "Confirm attendance", flagged_fields: ["expected_attendance"], returned_at: "2026-09-24T03:00:00Z" } };
    eventsApi.returnForAmendment.mockResolvedValue(returnedEvent);
    eventsApi.history.mockResolvedValue({ entries: [ENTRY] });

    await store.returnForAmendment("  Confirm attendance  ", ["expected_attendance"]);

    expect(eventsApi.returnForAmendment).toHaveBeenCalledWith(
      "event-1", { message: "Confirm attendance", flagged_fields: ["expected_attendance"] }, "access-token",
    );
    expect(store.event.status).toBe("returned");
    expect(store.event.amendment.flagged_fields).toEqual(["expected_attendance"]);
    expect(eventsApi.history).toHaveBeenCalledWith("event-1", "access-token");
  });

  it("loads the event and its history", async () => {
    eventsApi.get.mockResolvedValue(EVENT);
    eventsApi.history.mockResolvedValue({ entries: [ENTRY] });
    const store = useEventReviewStore();

    await store.load("event-1");

    expect(eventsApi.get).toHaveBeenCalledWith("event-1", "access-token");
    expect(store.event).toEqual(EVENT);
    expect(store.history).toEqual([ENTRY]);
    expect(store.error).toBeNull();
  });

  it("approves, then shows the new status and refreshed history", async () => {
    eventsApi.get.mockResolvedValue(EVENT);
    eventsApi.history.mockResolvedValue({ entries: [] });
    const store = useEventReviewStore();
    await store.load("event-1");
    eventsApi.approve.mockResolvedValue({ ...EVENT, status: "planning", version: 4 });
    eventsApi.history.mockResolvedValue({ entries: [ENTRY] });

    await store.approve();

    expect(eventsApi.approve).toHaveBeenCalledWith("event-1", "access-token");
    expect(store.event.status).toBe("planning");
    expect(store.history).toEqual([ENTRY]);
    expect(store.isActing).toBe(false);
  });

  it("keeps a completed decision even when the history refresh afterward fails (SCRUM-34/52)", async () => {
    eventsApi.get.mockResolvedValue(EVENT);
    eventsApi.history.mockResolvedValueOnce({ entries: [ENTRY] });
    const store = useEventReviewStore();
    await store.load("event-1");
    const previousHistory = store.history;
    eventsApi.approve.mockResolvedValue({ ...EVENT, status: "planning", version: 4 });
    eventsApi.history.mockRejectedValueOnce(new ApiError("Unable to reach the server. Please try again.", 500));

    await expect(store.approve()).resolves.toEqual({ ...EVENT, status: "planning", version: 4 });

    expect(store.event.status).toBe("planning");
    expect(store.error).toBeNull();
    expect(store.isActing).toBe(false);
    expect(store.history).toEqual(previousHistory);
  });

  it("sends a trimmed reason when rejecting", async () => {
    eventsApi.get.mockResolvedValue(EVENT);
    eventsApi.history.mockResolvedValue({ entries: [] });
    const store = useEventReviewStore();
    await store.load("event-1");
    eventsApi.reject.mockResolvedValue({ ...EVENT, status: "rejected" });

    await store.reject("  Venue unavailable  ");

    expect(eventsApi.reject).toHaveBeenCalledWith("event-1", "Venue unavailable", "access-token");
    expect(store.event.status).toBe("rejected");
  });

  it("keeps the event and reports the API's message when an action fails", async () => {
    eventsApi.get.mockResolvedValue(EVENT);
    eventsApi.history.mockResolvedValue({ entries: [] });
    const store = useEventReviewStore();
    await store.load("event-1");
    eventsApi.approve.mockRejectedValue(new ApiError("Cannot approve an event that is returned", 409));

    await expect(store.approve()).rejects.toThrow("Cannot approve an event that is returned");

    expect(store.error).toBe("Cannot approve an event that is returned");
    expect(store.event.status).toBe("under_review");
    expect(store.isActing).toBe(false);
  });

  it("reports a load failure", async () => {
    eventsApi.get.mockRejectedValue(new ApiError("Only the event's assigned coordinator can do this.", 403));
    eventsApi.history.mockResolvedValue({ entries: [] });
    const store = useEventReviewStore();

    await store.load("event-1");

    expect(store.event).toBeNull();
    expect(store.error).toBe("Only the event's assigned coordinator can do this.");
  });

  it("does not leak one event's history onto another when the new event's fetch fails (SCRUM-52)", async () => {
    eventsApi.history.mockResolvedValueOnce({ entries: [ENTRY] });
    const store = useEventReviewStore();
    await store.loadHistory("event-A");
    expect(store.history).toEqual([ENTRY]);

    eventsApi.history.mockRejectedValueOnce(new ApiError("Unable to reach the server. Please try again.", 500));

    await expect(store.loadHistory("event-B")).rejects.toThrow();
    expect(store.history).toEqual([]);
  });

  it("clears history for the new event before its fetch resolves, not after (SCRUM-52)", async () => {
    eventsApi.history.mockResolvedValueOnce({ entries: [ENTRY] });
    const store = useEventReviewStore();
    await store.loadHistory("event-A");
    expect(store.history).toEqual([ENTRY]);

    let resolveHistory;
    eventsApi.history.mockImplementationOnce(
      () => new Promise((resolve) => { resolveHistory = resolve; }),
    );
    const pending = store.loadHistory("event-B");

    expect(store.history).toEqual([]);

    resolveHistory({ entries: [] });
    await pending;
  });

  it("ignores a stale loadHistory response that resolves after a newer request (SCRUM-52)", async () => {
    let resolveA;
    let resolveB;
    eventsApi.history
      .mockImplementationOnce(() => new Promise((resolve) => { resolveA = resolve; }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveB = resolve; }));
    const store = useEventReviewStore();

    const pendingA = store.loadHistory("event-A");
    const pendingB = store.loadHistory("event-B");

    // B (the newer request) resolves first...
    resolveB({ entries: [{ ...ENTRY, id: "h-b" }] });
    await pendingB;
    // ...then A (the older, now-stale request) resolves last.
    resolveA({ entries: [{ ...ENTRY, id: "h-a" }] });
    await pendingA;

    expect(store.historyEventId).toBe("event-B");
    expect(store.history).toEqual([{ ...ENTRY, id: "h-b" }]);
  });

  it("ignores a stale load response that resolves after a newer request", async () => {
    let resolveGetA;
    let resolveHistoryA;
    let resolveGetB;
    let resolveHistoryB;
    eventsApi.get
      .mockImplementationOnce(() => new Promise((resolve) => { resolveGetA = resolve; }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveGetB = resolve; }));
    eventsApi.history
      .mockImplementationOnce(() => new Promise((resolve) => { resolveHistoryA = resolve; }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveHistoryB = resolve; }));
    const store = useEventReviewStore();
    const EVENT_B = { ...EVENT, id: "event-B", name: "Year-End Dinner" };

    const pendingA = store.load("event-A");
    const pendingB = store.load("event-B");

    // B (the newer request) resolves first...
    resolveGetB(EVENT_B);
    resolveHistoryB({ entries: [] });
    await pendingB;
    // ...then A (the older, now-stale request) resolves last.
    resolveGetA(EVENT);
    resolveHistoryA({ entries: [ENTRY] });
    await pendingA;

    expect(store.event).toEqual(EVENT_B);
    expect(store.history).toEqual([]);
    expect(store.error).toBeNull();
  });
});

// CR-104: coordinator-only supplementary decision history.
describe("private safety decisions", () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks(); signedInCoordinator(); });
  it("loads full safety history alongside coordinator details", async () => {
    eventsApi.get.mockResolvedValue(EVENT); eventsApi.history.mockResolvedValue({ entries: [] });
    eventsApi.safetyDecisions.mockResolvedValue([{ id: "d1", comment: "Private" }]);
    const store = useEventReviewStore(); await store.load(EVENT.id);
    expect(store.safetyDecisions).toEqual([{ id: "d1", comment: "Private" }]);
    expect(eventsApi.safetyDecisions).toHaveBeenCalledWith(EVENT.id, "access-token");
  });
  it("clears private decisions before switching events and on a failed read", async () => {
    const store = useEventReviewStore();
    expect(store.loadSafetyDecisions).toBeTypeOf("function");
    store.historyEventId = "event-A"; eventsApi.safetyDecisions.mockResolvedValue([{ id: "d1" }]);
    await store.loadSafetyDecisions("event-A");
    store.historyEventId = "event-B"; eventsApi.safetyDecisions.mockRejectedValue(new Error("Unavailable"));
    const pending = store.loadSafetyDecisions("event-B"); expect(store.safetyDecisions).toEqual([]);
    await expect(pending).rejects.toThrow("Unavailable"); expect(store.safetyDecisions).toEqual([]);
  });
  it("never fetches or retains comments for a session acting as organiser", async () => {
    const store = useEventReviewStore(); expect(store.loadSafetyDecisions).toBeTypeOf("function");
    store.safetyDecisions = [{ comment: "Private" }]; useAuthStore().profile.role = "event_organiser";
    useAuthStore().profile.roles = ["event_organiser", "event_coordinator"];
    await store.loadSafetyDecisions(EVENT.id);
    expect(eventsApi.safetyDecisions).not.toHaveBeenCalled(); expect(store.safetyDecisions).toEqual([]);
  });
  it("ignores stale private history after navigating to another event", async () => {
    const store = useEventReviewStore(); expect(store.loadSafetyDecisions).toBeTypeOf("function");
    let resolve; eventsApi.safetyDecisions.mockImplementationOnce(() => new Promise((r) => { resolve = r; }));
    store.historyEventId = "event-A"; const pending = store.loadSafetyDecisions("event-A");
    store.historyEventId = "event-B"; eventsApi.safetyDecisions.mockResolvedValue([{ id: "b" }]);
    await store.loadSafetyDecisions("event-B"); resolve([{ id: "a", comment: "Wrong event" }]); await pending;
    expect(store.safetyDecisions).toEqual([{ id: "b" }]);
  });
  it("keeps event details if the private history request fails", async () => {
    const store = useEventReviewStore(); eventsApi.get.mockResolvedValue(EVENT); eventsApi.history.mockResolvedValue({ entries: [] });
    eventsApi.safetyDecisions.mockRejectedValue(new Error("Unavailable"));
    await store.load(EVENT.id); expect(store.event).toEqual(EVENT); expect(store.error).toBeNull(); expect(store.safetyDecisions).toEqual([]);
  });
  it("clears the previous event's latest private decision before another event loads", async () => {
    const store = useEventReviewStore(); store.event = { ...EVENT, latest_safety_decision: { comment: "Wrong event" } };
    eventsApi.get.mockImplementationOnce(() => new Promise(() => {}));
    eventsApi.history.mockResolvedValue({ entries: [] });
    store.load("event-B");
    expect(store.event).toBeNull();
  });

});
