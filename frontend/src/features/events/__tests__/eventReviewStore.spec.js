import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { canApprove, canReject, REJECT_REASON_MAX_LENGTH, useEventReviewStore } from "@/features/events/eventReviewStore";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  eventsApi: { get: vi.fn(), history: vi.fn(), approve: vi.fn(), reject: vi.fn() },
}));

const EVENT = { id: "event-1", name: "Partner Summit", status: "under_review", version: 3 };
const ENTRY = { id: "h1", from_status: "under_review", to_status: "planning", actor: { id: "c1", full_name: "Marcus Lim" }, reason: null, at: "2026-09-24T03:00:00Z" };

function signedInCoordinator() {
  const auth = useAuthStore();
  auth.token = "access-token";
  auth.profile = { id: "c1", role: "event_coordinator", full_name: "Marcus Lim" };
}

describe("canApprove / canReject", () => {
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
});
