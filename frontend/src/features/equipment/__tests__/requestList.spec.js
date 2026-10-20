import { describe, expect, it } from "vitest";

import {
  ALL_ITEMS,
  ALL_STATUSES,
  equipmentFilterOptions,
  filterRequests,
  REQUEST_SORT_OPTIONS,
  requestStatusFilterOptions,
  sortRequests,
  WAITING,
  waitingCount,
  waitingDays,
} from "@/features/equipment/requestList";

const NOW = new Date("2026-10-20T04:00:00Z");

function line(overrides = {}) {
  return {
    id: "l1", status: "pending", equipment_id: "p1", equipment_name: "4K Projector", equipment_type: "AV",
    event_name: "Year-End Dinner", event_starts_at: "2026-11-20T02:00:00Z", created_at: "2026-10-17T04:00:00Z",
    ...overrides,
  };
}

const LINES = [
  line({ id: "a", status: "pending", event_name: "Summit", event_starts_at: "2026-11-01T02:00:00Z", created_at: "2026-10-19T04:00:00Z", equipment_type: "Video" }),
  line({ id: "b", status: "re_review", event_name: "Annual Dinner", event_starts_at: "2026-12-01T02:00:00Z", created_at: "2026-10-10T04:00:00Z", equipment_type: "Audio", equipment_id: "m1", equipment_name: "Wireless Mic" }),
  line({ id: "c", status: "reserved", event_name: "Career Fair", event_starts_at: "2026-11-15T02:00:00Z", created_at: "2026-10-15T04:00:00Z" }),
  line({ id: "d", status: "rejected", event_name: "Breakfast", event_starts_at: null, created_at: "2026-10-18T04:00:00Z", equipment_type: null }),
];

describe("tech support's equipment request list (SCRUM-24)", () => {
  it("waiting means pending or flagged for re-review", () => {
    expect(waitingCount(LINES)).toBe(2);
    expect(waitingCount([])).toBe(0);
  });

  it("the status filter starts with Waiting and All, then each status present, with counts", () => {
    expect(requestStatusFilterOptions(LINES)).toEqual([
      { value: WAITING, label: "Waiting on you (2)" },
      { value: ALL_STATUSES, label: "All statuses (4)" },
      { value: "pending", label: "Pending (1)" },
      { value: "re_review", label: "Re-review (1)" },
      { value: "reserved", label: "Reserved (1)" },
      { value: "rejected", label: "Not available (1)" },
    ]);
  });

  it("the equipment filter lists each item once, by name", () => {
    expect(equipmentFilterOptions(LINES)).toEqual([
      { value: ALL_ITEMS, label: "All equipment" },
      { value: "p1", label: "4K Projector" },
      { value: "m1", label: "Wireless Mic" },
    ]);
  });

  it("filters by status, item and the event's Singapore date", () => {
    const ids = (filters) => filterRequests(LINES, filters).map((l) => l.id);
    expect(ids({ status: WAITING })).toEqual(["a", "b"]);
    expect(ids({ status: ALL_STATUSES })).toEqual(["a", "b", "c", "d"]);
    expect(ids({ status: "reserved" })).toEqual(["c"]);
    expect(ids({ status: ALL_STATUSES, equipmentId: "m1" })).toEqual(["b"]);
    expect(ids({ status: ALL_STATUSES, startDate: "2026-11-15" })).toEqual(["b", "c"]);
    expect(ids({ status: ALL_STATUSES, endDate: "2026-11-15" })).toEqual(["a", "c"]);
    expect(ids({})).toEqual(["a", "b", "c", "d"]);
    expect(filterRequests()).toEqual([]);
  });

  it("offers the venue-staff sorts plus event name and equipment type (§6.15)", () => {
    expect(REQUEST_SORT_OPTIONS.map((o) => o.value)).toEqual([
      "event_soonest", "event_latest", "event_name", "equipment_type", "waiting_longest", "waiting_shortest",
    ]);
  });

  it("sorts by event date either way, undated events last", () => {
    expect(sortRequests(LINES, "event_soonest").map((l) => l.id)).toEqual(["a", "c", "b", "d"]);
    expect(sortRequests(LINES, "event_latest").map((l) => l.id)).toEqual(["b", "c", "a", "d"]);
  });

  it("sorts by event name and by equipment type, untyped last", () => {
    expect(sortRequests(LINES, "event_name").map((l) => l.id)).toEqual(["b", "d", "c", "a"]);
    expect(sortRequests(LINES, "equipment_type").map((l) => l.id)).toEqual(["b", "c", "a", "d"]);
  });

  it("sorts by how long a line has waited", () => {
    expect(sortRequests(LINES, "waiting_longest", NOW).map((l) => l.id)).toEqual(["b", "c", "d", "a"]);
    expect(sortRequests(LINES, "waiting_shortest", NOW).map((l) => l.id)).toEqual(["a", "d", "c", "b"]);
  });

  it("an unknown sort keeps soonest first, and sorting never changes the input", () => {
    const copy = [...LINES];
    expect(sortRequests(LINES, "nonsense").map((l) => l.id)).toEqual(["a", "c", "b", "d"]);
    expect(LINES).toEqual(copy);
    expect(sortRequests()).toEqual([]);
  });

  it("waiting days count whole days since submission", () => {
    expect(waitingDays(line({ created_at: "2026-10-17T04:00:00Z" }), NOW)).toBe(3);
    expect(waitingDays(line({ created_at: "2026-10-21T04:00:00Z" }), NOW)).toBe(0);
    expect(waitingDays(line({ created_at: null }), NOW)).toBeNull();
  });
});
