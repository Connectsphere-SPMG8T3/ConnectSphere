import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { emptyLine } from "@/features/equipment/equipmentRequest";
import { useEquipmentQueueStore } from "@/features/equipment/equipmentQueueStore";
import { useEquipmentRequestStore } from "@/features/equipment/equipmentRequestStore";
import { equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  equipmentApi: {
    catalogue: vi.fn(),
    eventRequests: vi.fn(),
    submitRequest: vi.fn(),
    requestList: vi.fn(),
    sendLineForReReview: vi.fn(),
    updateLine: vi.fn(),
    removeLine: vi.fn(),
    eventHistory: vi.fn(),
  },
}));

const PROJECTOR = { equipment_id: "p1", name: "Projector", equipment_type: "AV", total_quantity: 20 };
const LINE = {
  id: "l1", submission_id: "s1", event_id: "event-1", equipment_id: "p1", equipment_name: "Projector",
  quantity: 4, technical_requirements: "HDMI", status: "pending",
  requested_by: { id: "m1", full_name: "Marcus Lim" }, created_at: "2026-10-06T02:00:00Z",
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
  auth.profile = { id: "m1", role: "event_coordinator", full_name: "Marcus Lim" };
});

describe("useEquipmentRequestStore (SCRUM-45)", () => {
  it("keeps the event's technical status and exit check (SCRUM-24 AC9)", async () => {
    const exit = { confirmed_by_name: "Tan Wei", confirmed_at: "2026-10-19T03:00:00Z" };
    equipmentApi.catalogue.mockResolvedValue({ items: [] });
    equipmentApi.eventRequests.mockResolvedValueOnce({ lines: [LINE], technical_status: "ready", exit_confirmation: exit });
    const store = useEquipmentRequestStore();

    await store.load("event-1");
    expect(store.technicalStatus).toBe("ready");
    expect(store.exitConfirmation).toEqual(exit);

    equipmentApi.eventRequests.mockResolvedValueOnce({ lines: [] });
    await store.load("event-2");
    expect(store.technicalStatus).toBeNull();
    expect(store.exitConfirmation).toBeNull();
  });

  it("loads the catalogue and the event's lines", async () => {
    equipmentApi.catalogue.mockResolvedValue({ items: [PROJECTOR] });
    equipmentApi.eventRequests.mockResolvedValue({ lines: [LINE] });
    const store = useEquipmentRequestStore();

    await store.load("event-1");

    expect(equipmentApi.eventRequests).toHaveBeenCalledWith("event-1", "access");
    expect(store.catalogue).toEqual([PROJECTOR]);
    expect(store.lines).toEqual([LINE]);
    expect(store.isLoading).toBe(false);
    expect(store.error).toBeNull();
  });

  it("reports a load failure without inventing data", async () => {
    equipmentApi.catalogue.mockResolvedValue({ items: [PROJECTOR] });
    equipmentApi.eventRequests.mockRejectedValue(new Error("Only the event's assigned coordinator can do this."));
    const store = useEquipmentRequestStore();

    await store.load("event-1");

    expect(store.lines).toEqual([]);
    expect(store.error).toBe("Only the event's assigned coordinator can do this.");
  });

  it("drops a slow response for a previous event", async () => {
    equipmentApi.catalogue.mockResolvedValue({ items: [PROJECTOR] });
    const slow = deferred();
    equipmentApi.eventRequests.mockReturnValueOnce(slow.promise).mockResolvedValueOnce({ lines: [] });
    const store = useEquipmentRequestStore();

    const first = store.load("event-1");
    await store.load("event-2");
    slow.resolve({ lines: [LINE] });
    await first;

    expect(store.eventId).toBe("event-2");
    expect(store.lines).toEqual([]);
  });

  it("submits the batch and appends the saved pending lines", async () => {
    equipmentApi.catalogue.mockResolvedValue({ items: [PROJECTOR] });
    equipmentApi.eventRequests.mockResolvedValue({ lines: [] });
    equipmentApi.submitRequest.mockResolvedValue({ lines: [LINE] });
    const store = useEquipmentRequestStore();
    await store.load("event-1");

    const ok = await store.submit([{ ...emptyLine(), equipmentId: "p1", quantity: "4", technicalRequirements: "HDMI" }]);

    expect(ok).toBe(true);
    expect(equipmentApi.submitRequest).toHaveBeenCalledWith(
      { event_id: "event-1", items: [{ equipment_id: "p1", quantity: 4, technical_requirements: "HDMI" }] },
      "access",
    );
    expect(store.lines).toEqual([LINE]);
    expect(store.isSubmitting).toBe(false);
  });

  it("doesn't call the API for a submission that can't pass", async () => {
    const store = useEquipmentRequestStore();
    store.eventId = "event-1";

    expect(await store.submit([])).toBe(false);
    expect(await store.submit([{ ...emptyLine(), equipmentId: "p1", quantity: "0" }])).toBe(false);
    expect(equipmentApi.submitRequest).not.toHaveBeenCalled();
  });

  it("keeps the API's refusal for the form to show", async () => {
    equipmentApi.submitRequest.mockRejectedValue(new Error("Equipment can only be requested for an event in planning; this event is confirmed."));
    const store = useEquipmentRequestStore();
    store.eventId = "event-1";

    const ok = await store.submit([{ ...emptyLine(), equipmentId: "p1", quantity: "4" }]);

    expect(ok).toBe(false);
    expect(store.submitError).toContain("in planning");
    expect(store.lines).toEqual([]);
  });
});

describe("useEquipmentQueueStore (SCRUM-45, SCRUM-24)", () => {
  it("loads every line on open events and counts those waiting", async () => {
    const pending = { ...LINE, event_name: "Year-End Dinner", event_starts_at: "2026-11-05T10:00:00Z" };
    const reserved = { ...pending, id: "l2", status: "reserved" };
    equipmentApi.requestList.mockResolvedValue({ lines: [pending, reserved] });
    const store = useEquipmentQueueStore();
    expect(store.isLoaded).toBe(false);

    await store.load();

    expect(equipmentApi.requestList).toHaveBeenCalledWith("access");
    expect(store.lines).toEqual([pending, reserved]);
    expect(store.waitingCount).toBe(1);
    expect(store.isLoaded).toBe(true);
    expect(store.error).toBeNull();
    expect(store.isLoading).toBe(false);
  });

  it("reports a failure instead of an empty queue", async () => {
    equipmentApi.requestList.mockRejectedValue(new Error("Service unavailable"));
    const store = useEquipmentQueueStore();

    await store.load();

    expect(store.lines).toEqual([]);
    expect(store.isLoaded).toBe(false);
    expect(store.error).toBe("Service unavailable");
  });
});

describe("useEquipmentRequestStore send for re-review (story 37)", () => {
  it("does nothing before an event is loaded", async () => {
    const store = useEquipmentRequestStore();

    expect(await store.sendForReReview("l1", null)).toBe(false);
    expect(equipmentApi.sendLineForReReview).not.toHaveBeenCalled();
  });

  it("drops the answer for an event the panel has since left", async () => {
    equipmentApi.catalogue.mockResolvedValue({ items: [] });
    equipmentApi.eventRequests.mockResolvedValue({ lines: [LINE] });
    const store = useEquipmentRequestStore();
    await store.load("event-1");
    const pending = deferred();
    equipmentApi.sendLineForReReview.mockReturnValue(pending.promise);

    const sending = store.sendForReReview("l1", null);
    await store.load("event-2");
    pending.resolve(null);

    expect(await sending).toBe(true);
    expect(store.eventId).toBe("event-2");
    expect(store.isSubmitting).toBe(false);
    expect(equipmentApi.eventRequests).toHaveBeenCalledTimes(2);
  });

  it("doesn't show the old event's refusal on the new one", async () => {
    equipmentApi.catalogue.mockResolvedValue({ items: [] });
    equipmentApi.eventRequests.mockResolvedValue({ lines: [LINE] });
    const store = useEquipmentRequestStore();
    await store.load("event-1");
    let reject;
    equipmentApi.sendLineForReReview.mockReturnValue(new Promise((_, r) => { reject = r; }));

    const sending = store.sendForReReview("l1", null);
    await store.load("event-2");
    reject(new Error("This equipment line doesn't need re-review."));

    expect(await sending).toBe(false);
    expect(store.actionError).toBeNull();
  });
});


describe("useEquipmentRequestStore changes and removals (SCRUM-44)", () => {
  const ENTRY = { action: "removed", line_label: "4 × Projector", detail: "Removed 4 × Projector.", created_at: "2026-10-26T02:00:00Z" };
  const DRAFT = { equipmentId: "p1", quantity: "6", technicalRequirements: "" };

  async function loaded() {
    equipmentApi.catalogue.mockResolvedValue({ items: [PROJECTOR] });
    equipmentApi.eventRequests.mockResolvedValue({ lines: [LINE] });
    equipmentApi.eventHistory.mockResolvedValue({ history: [ENTRY] });
    const store = useEquipmentRequestStore();
    await store.load("event-1");
    return store;
  }

  it("loads the event's equipment history on its own (AC8)", async () => {
    const store = await loaded();

    await store.loadHistory("event-1");

    expect(equipmentApi.eventHistory).toHaveBeenCalledWith("event-1", "access");
    expect(store.history).toEqual([ENTRY]);
    expect(store.historyError).toBeNull();
  });

  it("keeps the lines when the history can't be read", async () => {
    const store = await loaded();
    equipmentApi.eventHistory.mockRejectedValue(new Error("down"));

    await store.loadHistory("event-1");

    expect(store.history).toEqual([]);
    expect(store.historyError).toBe("down");
    expect(store.lines).toEqual([LINE]);
  });

  it("drops a history answer for an event the panel has since left", async () => {
    const store = await loaded();
    const pending = deferred();
    equipmentApi.eventHistory.mockReturnValue(pending.promise);

    const reading = store.loadHistory("event-1");
    equipmentApi.eventRequests.mockResolvedValue({ lines: [] });
    await store.load("event-2");
    pending.resolve({ history: [ENTRY] });
    await reading;

    expect(store.history).toEqual([]);
  });

  it("saves a change with the status it was seen in, then reloads the lines and history (AC2, AC6)", async () => {
    const store = await loaded();
    equipmentApi.updateLine.mockResolvedValue({ line_id: "l1", status: "pending" });
    equipmentApi.eventRequests.mockClear();

    expect(await store.updateLine(LINE, DRAFT)).toBe(true);

    expect(equipmentApi.updateLine).toHaveBeenCalledWith("l1", {
      equipment_id: "p1", quantity: 6, technical_requirements: null, expected_status: "pending",
    }, "access");
    expect(equipmentApi.eventRequests).toHaveBeenCalled();
    expect(equipmentApi.eventHistory).toHaveBeenCalled();
    expect(store.busyLineId).toBeNull();
  });

  it("removes a line with the status it was seen in, then reloads (AC1, AC6)", async () => {
    const store = await loaded();
    equipmentApi.removeLine.mockResolvedValue({ line_id: "l1", status: "released" });
    equipmentApi.eventRequests.mockClear();

    expect(await store.removeLine({ ...LINE, status: "reserved" })).toBe(true);

    expect(equipmentApi.removeLine).toHaveBeenCalledWith("l1", "reserved", "access");
    expect(equipmentApi.eventRequests).toHaveBeenCalled();
  });

  it("shows a refusal and reloads, so a line that moved shows its new status (AC4, AC6)", async () => {
    const store = await loaded();
    equipmentApi.updateLine.mockRejectedValue(new Error("This line changed while you were editing it. Reload to see its current status."));
    equipmentApi.eventRequests.mockClear();

    expect(await store.updateLine(LINE, DRAFT)).toBe(false);

    expect(store.actionError).toBe("This line changed while you were editing it. Reload to see its current status.");
    expect(equipmentApi.eventRequests).toHaveBeenCalled();
    expect(store.actionError).not.toBeNull();
  });

  it("keeps a removal's refusal on screen", async () => {
    const store = await loaded();
    equipmentApi.removeLine.mockRejectedValue(new Error("Equipment can only be changed while the event is in Planning."));

    expect(await store.removeLine(LINE)).toBe(false);
    expect(store.actionError).toBe("Equipment can only be changed while the event is in Planning.");
  });

  it("doesn't save an invalid draft or act while another line is busy", async () => {
    const store = await loaded();

    expect(await store.updateLine(LINE, { ...DRAFT, quantity: "0" })).toBe(false);
    store.busyLineId = "l9";
    expect(await store.updateLine(LINE, DRAFT)).toBe(false);
    expect(await store.removeLine(LINE)).toBe(false);
    expect(equipmentApi.updateLine).not.toHaveBeenCalled();
    expect(equipmentApi.removeLine).not.toHaveBeenCalled();
  });

  it("drops the answer for an event the panel has since left", async () => {
    const store = await loaded();
    let reject;
    equipmentApi.removeLine.mockReturnValue(new Promise((_, r) => { reject = r; }));

    const removing = store.removeLine(LINE);
    await store.load("event-2");
    reject(new Error("refused"));

    expect(await removing).toBe(false);
    expect(store.actionError).toBeNull();
    expect(store.busyLineId).toBeNull();
  });
});
