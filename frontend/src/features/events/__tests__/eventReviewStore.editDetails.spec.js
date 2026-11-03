import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useEventReviewStore } from "@/features/events/eventReviewStore";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  eventsApi: { get: vi.fn(), history: vi.fn(), editDetails: vi.fn() },
}));

const EVENT = { id: "event-1", name: "Partner Summit", status: "planning", version: 4, spaces: [{ id: "s1" }] };
const SAVED = { ...EVENT, name: "Partner Summit 2027", version: 5 };

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
  const auth = useAuthStore();
  auth.token = "access-token";
  auth.profile = { id: "c1", role: "event_coordinator", full_name: "Marcus Lim" };
  eventsApi.get.mockResolvedValue({ ...SAVED, safety_readiness: { ready: true } });
  eventsApi.history.mockResolvedValue({ entries: [{ id: "h1" }] });
});

function loaded() {
  const store = useEventReviewStore();
  store.event = { ...EVENT };
  store.historyEventId = EVENT.id;
  return store;
}

describe("eventReview.editDetails (story 112)", () => {
  it("sends the changed fields with the version the page was loaded at", async () => {
    eventsApi.editDetails.mockResolvedValue(SAVED);
    const store = loaded();

    await store.editDetails({ name: "Partner Summit 2027" });

    expect(eventsApi.editDetails).toHaveBeenCalledWith(
      "event-1", { version: 4, name: "Partner Summit 2027" }, "access-token",
    );
  });

  it("shows the saved row at once, keeping what the edit's answer lacks, without waiting for the re-read", async () => {
    eventsApi.editDetails.mockResolvedValue({ id: "event-1", name: "Partner Summit 2027", version: 5 });
    eventsApi.get.mockReturnValue(new Promise(() => {}));
    const store = loaded();

    await store.editDetails({ name: "Partner Summit 2027" });

    expect(store.event.name).toBe("Partner Summit 2027");
    expect(store.event.version).toBe(5);
    expect(store.event.spaces).toEqual([{ id: "s1" }]);
    expect(store.isActing).toBe(false);
    expect(store.error).toBeNull();
  });

  it("then reads the whole event and the history again in the background", async () => {
    eventsApi.editDetails.mockResolvedValue({ id: "event-1", name: "Partner Summit 2027", version: 5 });
    const store = loaded();

    await store.editDetails({ name: "Partner Summit 2027" });

    await vi.waitFor(() => expect(store.event.safety_readiness).toEqual({ ready: true }));
    await vi.waitFor(() => expect(store.history).toEqual([{ id: "h1" }]));
  });

  it("keeps the API's refusal for the dialog and rethrows", async () => {
    eventsApi.editDetails.mockRejectedValue(new ApiError("Significant changes go through a change request.", 422));
    const store = loaded();

    await expect(store.editDetails({ name: "x" })).rejects.toThrow("Significant changes");

    expect(store.error).toBe("Significant changes go through a change request.");
    expect(store.isActing).toBe(false);
    expect(store.event.version).toBe(4);
    expect(eventsApi.get).not.toHaveBeenCalled();
  });

  it("marks a 409 as a conflict so the dialog can offer a reload, whatever the wording", async () => {
    eventsApi.editDetails.mockRejectedValue(new ApiError("Some future wording.", 409));
    const store = loaded();

    await expect(store.editDetails({ name: "x" })).rejects.toThrow();

    expect(store.error).toBe("Some future wording.");
    expect(store.editConflict).toBe(true);
  });

  it("does not mark any other refusal as a conflict, and clears the mark on the next try", async () => {
    eventsApi.editDetails.mockRejectedValueOnce(new ApiError("Stale.", 409));
    const store = loaded();
    await expect(store.editDetails({ name: "x" })).rejects.toThrow();
    expect(store.editConflict).toBe(true);

    eventsApi.editDetails.mockRejectedValueOnce(new ApiError("Significant changes go through a change request.", 422));
    await expect(store.editDetails({ name: "x" })).rejects.toThrow();
    expect(store.editConflict).toBe(false);

    eventsApi.editDetails.mockResolvedValueOnce(SAVED);
    await store.editDetails({ name: "x" });
    expect(store.editConflict).toBe(false);
  });

  it("does not report a saved edit as failed when the refresh fails", async () => {
    eventsApi.editDetails.mockResolvedValue(SAVED);
    eventsApi.get.mockRejectedValue(new Error("offline"));
    const store = loaded();

    await expect(store.editDetails({ name: "Partner Summit 2027" })).resolves.toBeDefined();

    expect(store.error).toBeNull();
    expect(store.isActing).toBe(false);
  });

  it("ignores a second call while one is in flight", async () => {
    eventsApi.editDetails.mockResolvedValue(SAVED);
    const store = loaded();
    store.isActing = true;

    await store.editDetails({ name: "x" });

    expect(eventsApi.editDetails).not.toHaveBeenCalled();
  });
});

describe("eventsApi.editDetails", () => {
  it("PATCHes /events/{id}/details with the bearer token", async () => {
    const { eventsApi: real } = await vi.importActual("@/services/api");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => SAVED });
    vi.stubGlobal("fetch", fetchMock);

    await real.editDetails("event 1", { version: 4, name: "Partner Summit 2027" }, "tok");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/events\/event%201\/details$/);
    expect(options.method).toBe("PATCH");
    expect(options.headers.Authorization).toBe("Bearer tok");
    expect(JSON.parse(options.body)).toEqual({ version: 4, name: "Partner Summit 2027" });
    vi.unstubAllGlobals();
  });
});
