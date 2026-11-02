import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useEventReviewStore } from "@/features/events/eventReviewStore";
import { useLeadDashboardStore } from "@/features/events/leadDashboardStore";
import { canRequestReassignment, REASSIGNMENT_REASON_MAX_LENGTH } from "@/features/events/reassignmentRequest";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// CR-106. The real eventsApi is used by the first describe; the stores' describes replace it.
const realFetch = globalThis.fetch;

describe("CR-106 reassignment request rules", () => {
  it("caps the reason at the API's 1000 characters", () => {
    expect(REASSIGNMENT_REASON_MAX_LENGTH).toBe(1000);
  });

  it("offers a request on an active event that has none open (AC1)", () => {
    // Preparation included: it is still the coordinator's work and a Lead can reassign it (QA3-3, D73).
    for (const status of ["under_review", "returned", "planning", "safety_review", "confirmed", "preparation"]) {
      expect(canRequestReassignment({ status, open_reassignment_request: null })).toBe(true);
    }
  });

  it("does not offer a second request while one is open (AC5)", () => {
    expect(canRequestReassignment({ status: "planning", open_reassignment_request: { id: "r1" } })).toBe(false);
  });

  it("does not offer it on an event a Lead can no longer reassign", () => {
    for (const status of ["draft", "submitted", "rejected", "cancelled", "completed"]) {
      expect(canRequestReassignment({ status })).toBe(false);
    }
  });

  it("offers nothing without an event", () => {
    expect(canRequestReassignment(null)).toBe(false);
    expect(canRequestReassignment(undefined)).toBe(false);
  });
});

describe("CR-106 API calls", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts the request and the decline with the session and the reason", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => ({ id: "r1" }) });
    vi.stubGlobal("fetch", fetchMock);

    await eventsApi.requestReassignment("event/one", "On leave", "token");
    await eventsApi.declineReassignment("event/one", "No cover", "token");

    expect(fetchMock.mock.calls.map(([url, options]) => [url, options.method, options.body])).toEqual([
      ["http://localhost:8000/api/v1/events/event%2Fone/reassignment-request", "POST",
        JSON.stringify({ reason: "On leave" })],
      ["http://localhost:8000/api/v1/events/event%2Fone/reassignment-request/decline", "POST",
        JSON.stringify({ reason: "No cover" })],
    ]);
    expect(fetchMock.mock.calls.every(([, options]) => options.headers.Authorization === "Bearer token")).toBe(true);
  });
});

describe("CR-106 coordinator store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.restoreAllMocks();
    const auth = useAuthStore();
    auth.token = "access-token";
    auth.profile = { id: "c1", role: "event_coordinator", full_name: "Marcus Lim" };
  });

  // Each test changes a mock after this returns, so a default is never applied over an override.
  function stubApi() {
    return {
      requestReassignment: vi.spyOn(eventsApi, "requestReassignment").mockResolvedValue({ id: "r1" }),
      get: vi.spyOn(eventsApi, "get").mockResolvedValue({
        id: "event-1", status: "planning", open_reassignment_request: { id: "r1" },
      }),
      history: vi.spyOn(eventsApi, "history").mockResolvedValue({ entries: [{ id: "r1", kind: "reassignment_requested" }] }),
    };
  }

  it("sends the trimmed reason, then shows the open request and its history entry", async () => {
    const api = stubApi();
    const store = useEventReviewStore();
    store.event = { id: "event-1", status: "planning", open_reassignment_request: null };
    store.historyEventId = "event-1";

    const event = await store.requestReassignment("  On leave  ");

    expect(api.requestReassignment).toHaveBeenCalledWith("event-1", "On leave", "access-token");
    expect(event.open_reassignment_request).toEqual({ id: "r1" });
    expect(store.event.open_reassignment_request).toEqual({ id: "r1" });
    expect(store.history).toEqual([{ id: "r1", kind: "reassignment_requested" }]);
    expect(store.isActing).toBe(false);
    expect(store.error).toBeNull();
  });

  it("keeps the API's refusal for the dialog and rethrows, such as a second open request", async () => {
    const api = stubApi();
    api.requestReassignment.mockRejectedValue(new ApiError("A reassignment request is already open for this event.", 409));
    const store = useEventReviewStore();
    store.event = { id: "event-1", status: "planning" };

    await expect(store.requestReassignment("On leave")).rejects.toThrow("already open");

    expect(store.error).toBe("A reassignment request is already open for this event.");
    expect(store.isActing).toBe(false);
  });

  it("still counts the request as sent when the reload fails", async () => {
    const api = stubApi();
    api.get.mockRejectedValue(new TypeError("Failed to fetch"));
    const store = useEventReviewStore();
    store.event = { id: "event-1", status: "planning" };
    store.historyEventId = "event-1";

    await expect(store.requestReassignment("On leave")).resolves.toEqual({ id: "event-1", status: "planning" });

    expect(store.error).toBeNull();
  });

  it("does not put another event's page over the one now open", async () => {
    stubApi();
    const store = useEventReviewStore();
    store.event = { id: "event-1", status: "planning" };
    store.historyEventId = "event-2";

    await store.requestReassignment("On leave");

    expect(store.event).toEqual({ id: "event-1", status: "planning" });
  });
});

describe("CR-106 Lead store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.restoreAllMocks();
    const auth = useAuthStore();
    auth.token = "access-token";
    auth.profile = { id: "l1", role: "event_coordinator_lead", full_name: "Joyce" };
  });

  it("declines with the reason, then reloads the dashboard, and returns true (AC5)", async () => {
    const decline = vi.spyOn(eventsApi, "declineReassignment").mockResolvedValue({ id: "r1", status: "declined" });
    const dashboard = vi.spyOn(eventsApi, "leadDashboard").mockResolvedValue({
      unassigned: [], active_events: [{ event_id: "e1", open_reassignment_request: null }], coordinators: [],
    });
    const store = useLeadDashboardStore();

    expect(await store.declineReassignment("e1", "  No cover  ")).toBe(true);

    expect(decline).toHaveBeenCalledWith("e1", "No cover", "access-token");
    expect(dashboard).toHaveBeenCalledTimes(1);
    expect(store.eventById("e1").open_reassignment_request).toBeNull();
    expect(store.declineError).toBeNull();
    expect(store.isDeclining).toBe(false);
  });

  it("keeps the server's reason when the decline is refused, and returns false", async () => {
    vi.spyOn(eventsApi, "declineReassignment")
      .mockRejectedValue(new ApiError("There is no open reassignment request for this event.", 409));
    const dashboard = vi.spyOn(eventsApi, "leadDashboard");
    const store = useLeadDashboardStore();

    expect(await store.declineReassignment("e1", "No cover")).toBe(false);

    expect(store.declineError).toBe("There is no open reassignment request for this event.");
    expect(store.isDeclining).toBe(false);
    expect(dashboard).not.toHaveBeenCalled();
  });

  it("reports a network failure in plain words", async () => {
    vi.spyOn(eventsApi, "declineReassignment").mockRejectedValue(new TypeError("Failed to fetch"));
    const store = useLeadDashboardStore();

    expect(await store.declineReassignment("e1", "No cover")).toBe(false);

    expect(store.declineError).toBe("Unable to reach the server. Please try again.");
  });

  it("forgets a decline error on reset", async () => {
    vi.spyOn(eventsApi, "declineReassignment").mockRejectedValue(new ApiError("Nope", 409));
    const store = useLeadDashboardStore();
    await store.declineReassignment("e1", "No cover");

    store.reset();

    expect(store.declineError).toBeNull();
  });
});

afterEach(() => {
  globalThis.fetch = realFetch;
});
