import { describe, expect, it } from "vitest";

import {
  coordinatorEventCards,
  filterCoordinatorEvents,
  groupCoordinatorEvents,
  sortCoordinatorEvents,
} from "@/features/events/coordinatorDashboard";

const READY = { venue: "ready", equipment: "not_required", technical: "ready" };

function event(id, overrides = {}) {
  return {
    event_id: id,
    event_name: `Event ${id}`,
    status: "planning",
    starts_at: "2026-10-10T02:00:00Z",
    flags: [],
    readiness: READY,
    ...overrides,
  };
}

describe("coordinatorEventCards", () => {
  it("attaches each event's most urgent action item and outstanding readiness", () => {
    const cards = coordinatorEventCards(
      [event("a", { status: "under_review", readiness: { ...READY, venue: "pending" } }), event("b")],
      [
        { event_id: "a", kind: "awaiting_review" },
        { event_id: "a", kind: "arrangement_issue" },
      ],
    );

    expect(cards[0]).toMatchObject({ id: "a", name: "Event a", actionKind: "arrangement_issue", outstanding: ["Venue"] });
    expect(cards[1]).toMatchObject({ id: "b", actionKind: null, outstanding: [] });
  });

  it("tolerates missing lists", () => {
    expect(coordinatorEventCards()).toEqual([]);
  });
});

describe("filterCoordinatorEvents", () => {
  const cards = coordinatorEventCards(
    [
      event("a", { event_name: "Partner Summit", status: "under_review" }),
      event("b", { event_name: "Year-End Dinner", status: "under_review" }),
      event("c", { event_name: "Tech Talk", status: "planning" }),
    ],
    [
      { event_id: "a", kind: "awaiting_review" },
      { event_id: "b", kind: "resubmitted" },
    ],
  );
  const ids = (list) => list.map((card) => card.id);

  it("returns everything with no filters", () => {
    expect(ids(filterCoordinatorEvents(cards))).toEqual(["a", "b", "c"]);
  });

  it("matches the name case-insensitively", () => {
    expect(ids(filterCoordinatorEvents(cards, { search: "  summit " }))).toEqual(["a"]);
  });

  it("keeps any of the selected statuses", () => {
    expect(ids(filterCoordinatorEvents(cards, { status: ["planning"] }))).toEqual(["c"]);
    expect(ids(filterCoordinatorEvents(cards, { status: ["planning", "under_review"] }))).toEqual(["a", "b", "c"]);
  });

  it("keeps the events in one AC1 action category", () => {
    expect(ids(filterCoordinatorEvents(cards, { action: "awaitingApproval" }))).toEqual(["a"]);
    expect(ids(filterCoordinatorEvents(cards, { action: "clarificationResponses" }))).toEqual(["b"]);
    expect(ids(filterCoordinatorEvents(cards, { action: "immediate" }))).toEqual([]);
  });

  it("ignores an unknown action category rather than hiding everything", () => {
    expect(ids(filterCoordinatorEvents(cards, { action: "nonsense" }))).toEqual(["a", "b", "c"]);
  });
});

describe("sortCoordinatorEvents", () => {
  const cards = coordinatorEventCards([
    event("a", { event_name: "Bravo", status: "planning", starts_at: "2026-10-12T02:00:00Z" }),
    event("b", { event_name: "alpha", status: "confirmed", starts_at: "2026-10-10T02:00:00Z" }),
    event("c", { event_name: "Charlie", status: "under_review", starts_at: null }),
  ]);
  const ids = (list) => list.map((card) => card.id);

  it("sorts by date with undated events last", () => {
    expect(ids(sortCoordinatorEvents(cards, { field: "date" }))).toEqual(["b", "a", "c"]);
  });

  it("sorts by name ignoring case, either direction", () => {
    expect(ids(sortCoordinatorEvents(cards, { field: "name" }))).toEqual(["b", "a", "c"]);
    expect(ids(sortCoordinatorEvents(cards, { field: "name", direction: "desc" }))).toEqual(["c", "a", "b"]);
  });

  it("sorts by lifecycle order of status", () => {
    expect(ids(sortCoordinatorEvents(cards, { field: "status" }))).toEqual(["c", "a", "b"]);
  });

  it("returns a new array", () => {
    expect(sortCoordinatorEvents(cards)).not.toBe(cards);
  });
});

describe("groupCoordinatorEvents", () => {
  it("splits events that need the coordinator from those that don't", () => {
    const cards = coordinatorEventCards([event("a"), event("b")], [{ event_id: "b", kind: "awaiting_review" }]);

    const groups = groupCoordinatorEvents(cards);

    expect(groups.needsAction.map((card) => card.id)).toEqual(["b"]);
    expect(groups.inProgress.map((card) => card.id)).toEqual(["a"]);
  });
});
