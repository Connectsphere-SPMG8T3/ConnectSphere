import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useTechnicalEventStore } from "@/features/equipment/technicalEventStore";
import { ApiError, equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  equipmentApi: {
    technicalView: vi.fn(),
    reserveLine: vi.fn(),
    markNotAvailable: vi.fn(),
    setLineNote: vi.fn(),
    setExitConfirmation: vi.fn(),
  },
}));

const VIEW = {
  event: { id: "event-1", name: "Year-End Dinner", status: "planning" },
  technical_status: "pending",
  exit_confirmation: null,
  lines: [{ id: "l1", status: "pending" }],
  history: [],
};

function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
  const auth = useAuthStore();
  auth.token = "access";
  auth.profile = { id: "t1", role: "tech_support", full_name: "Tan Wei" };
  equipmentApi.technicalView.mockResolvedValue(VIEW);
});

describe("useTechnicalEventStore (SCRUM-24)", () => {
  it("loads one event's technical view", async () => {
    const store = useTechnicalEventStore();

    await store.load("event-1");

    expect(equipmentApi.technicalView).toHaveBeenCalledWith("event-1", "access");
    expect(store.view).toEqual(VIEW);
    expect(store.isLoading).toBe(false);
  });

  it("a failed load keeps the message", async () => {
    equipmentApi.technicalView.mockRejectedValue(new ApiError("Event not found.", 404));
    const store = useTechnicalEventStore();

    await store.load("event-1");

    expect(store.error).toBe("Event not found.");
  });

  it("a slow answer for a previous event never lands on the current one", async () => {
    const slow = deferred();
    equipmentApi.technicalView.mockReturnValueOnce(slow.promise).mockResolvedValueOnce({ ...VIEW, event: { id: "event-2" } });
    const store = useTechnicalEventStore();

    const first = store.load("event-1");
    await store.load("event-2");
    slow.resolve(VIEW);
    await first;

    expect(store.view.event.id).toBe("event-2");
  });

  it("a failed load for a previous event is not reported on the current one", async () => {
    const slow = deferred();
    equipmentApi.technicalView.mockReturnValueOnce(slow.promise.then(() => { throw new Error("old"); }))
      .mockResolvedValueOnce(VIEW);
    const store = useTechnicalEventStore();

    const first = store.load("event-1");
    await store.load("event-2");
    slow.resolve();
    await first;

    expect(store.error).toBeNull();
    expect(store.isLoading).toBe(false);
  });

  it("reserving calls the API, then reloads (AC1)", async () => {
    equipmentApi.reserveLine.mockResolvedValue({ line_id: "l1", status: "reserved", free_quantity: 2 });
    const store = useTechnicalEventStore();
    await store.load("event-1");

    expect(await store.reserve("l1")).toBe(true);

    expect(equipmentApi.reserveLine).toHaveBeenCalledWith("l1", "access");
    expect(equipmentApi.technicalView).toHaveBeenCalledTimes(2);
    expect(store.busy).toBeNull();
  });

  it("a refusal stays beside its line with the free count (AC3)", async () => {
    const message = "Not enough available: 1 free for this event's time. The line stays Pending.";
    equipmentApi.reserveLine.mockRejectedValue(new ApiError(message, 409));
    const store = useTechnicalEventStore();
    await store.load("event-1");

    expect(await store.reserve("l1")).toBe(false);

    expect(store.lineErrors.l1).toBe(message);
  });

  it("marking Not available sends the trimmed reason (AC9)", async () => {
    equipmentApi.markNotAvailable.mockResolvedValue({});
    const store = useTechnicalEventStore();
    await store.load("event-1");

    await store.markNotAvailable("l1", "  Only 2 in stock  ");

    expect(equipmentApi.markNotAvailable).toHaveBeenCalledWith("l1", "Only 2 in stock", "access");
  });

  it("a blank note is sent as a clear (AC9)", async () => {
    equipmentApi.setLineNote.mockResolvedValue({});
    const store = useTechnicalEventStore();
    await store.load("event-1");

    await store.saveNote("l1", "   ");
    await store.saveNote("l1", " From store B ");

    expect(equipmentApi.setLineNote).toHaveBeenNthCalledWith(1, "l1", null, "access");
    expect(equipmentApi.setLineNote).toHaveBeenNthCalledWith(2, "l1", "From store B", "access");
  });

  it("ticking the exit box calls the API and reloads (AC10)", async () => {
    equipmentApi.setExitConfirmation.mockResolvedValue(null);
    const store = useTechnicalEventStore();
    await store.load("event-1");

    expect(await store.setExitConfirmation(true)).toBe(true);

    expect(equipmentApi.setExitConfirmation).toHaveBeenCalledWith("event-1", true, "access");
    expect(equipmentApi.technicalView).toHaveBeenCalledTimes(2);
  });

  it("a refused tick keeps its message", async () => {
    equipmentApi.setExitConfirmation.mockRejectedValue(new ApiError("This event has no equipment lines, so there is nothing to confirm.", 409));
    const store = useTechnicalEventStore();
    await store.load("event-1");

    expect(await store.setExitConfirmation(true)).toBe(false);

    expect(store.exitError).toBe("This event has no equipment lines, so there is nothing to confirm.");
  });

  it("nothing is sent before a load or while another action runs", async () => {
    const store = useTechnicalEventStore();
    expect(await store.reserve("l1")).toBe(false);
    expect(await store.setExitConfirmation(true)).toBe(false);

    await store.load("event-1");
    store.busy = "l2";
    expect(await store.reserve("l1")).toBe(false);
    expect(await store.setExitConfirmation(true)).toBe(false);
    expect(equipmentApi.reserveLine).not.toHaveBeenCalled();
    expect(equipmentApi.setExitConfirmation).not.toHaveBeenCalled();
  });

  it("an action's answer for an event left behind is not shown on the new one", async () => {
    const slow = deferred();
    equipmentApi.reserveLine.mockReturnValue(slow.promise.then(() => { throw new ApiError("old", 409); }));
    equipmentApi.setExitConfirmation.mockReturnValue(slow.promise.then(() => { throw new ApiError("old", 409); }));
    const store = useTechnicalEventStore();
    await store.load("event-1");

    const reserving = store.reserve("l1");
    store.busy = null;
    const ticking = store.setExitConfirmation(true);
    await store.load("event-2");
    slow.resolve();
    await reserving;
    await ticking;

    expect(store.lineErrors).toEqual({});
    expect(store.exitError).toBeNull();
  });
});
