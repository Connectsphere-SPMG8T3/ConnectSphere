import { describe, expect, it } from "vitest";

import {
  ACTION_KINDS,
  ACTIVE_COORDINATOR_STATUSES,
  STATUS_DESCRIPTIONS,
  STATUS_LABELS,
  actionKindMeta,
  countByStatus,
  groupActiveEventsByStatus,
  outstandingReadiness,
  prioritiseActionItems,
  readinessGaps,
  summariseActionItems,
} from "@/features/events/dashboard";

const NOW = new Date("2026-10-01T09:00:00Z");

function actionItem(overrides = {}) {
  return {
    event_id: "e1",
    event_name: "Annual Conference",
    kind: "awaiting_review",
    status: "under_review",
    starts_at: "2026-11-01T02:00:00Z",
    occurred_at: "2026-09-30T02:00:00Z",
    organiser_name: "Priya Nair",
    ...overrides,
  };
}

function activeEvent(overrides = {}) {
  return {
    event_id: "e1",
    event_name: "Annual Conference",
    status: "planning",
    starts_at: "2026-11-01T02:00:00Z",
    organiser_name: "Priya Nair",
    readiness: { venue: "ready", equipment: "ready", technical: "ready" },
    flags: [],
    ...overrides,
  };
}

describe("action item prioritisation (SCRUM-72 AC1)", () => {
  it("orders action kinds by the configured rank, most urgent first", () => {
    const items = [
      actionItem({ event_id: "a", kind: "awaiting_review" }),
      actionItem({ event_id: "b", kind: "arrangement_issue" }),
      actionItem({ event_id: "c", kind: "resubmitted" }),
      actionItem({ event_id: "d", kind: "cancellation_request" }),
    ];

    expect(prioritiseActionItems(items).map((item) => item.kind)).toEqual([
      "arrangement_issue",
      "cancellation_request",
      "resubmitted",
      "awaiting_review",
    ]);
  });

  it("breaks ties within a kind by the soonest event date", () => {
    const items = [
      actionItem({ event_id: "later", starts_at: "2026-12-01T02:00:00Z" }),
      actionItem({ event_id: "sooner", starts_at: "2026-10-05T02:00:00Z" }),
    ];

    expect(prioritiseActionItems(items).map((item) => item.event_id)).toEqual(["sooner", "later"]);
  });

  it("breaks a same-date tie by how long the item has been waiting, oldest first", () => {
    const items = [
      actionItem({ event_id: "fresh", occurred_at: "2026-09-30T02:00:00Z" }),
      actionItem({ event_id: "stale", occurred_at: "2026-09-20T02:00:00Z" }),
    ];

    expect(prioritiseActionItems(items).map((item) => item.event_id)).toEqual(["stale", "fresh"]);
  });

  it("keeps an unrecognised kind in the queue, ranked last, rather than dropping it", () => {
    // NFR-M1: the backend may add a kind before the SPA knows about it. Losing a
    // coordinator's action item silently is worse than showing it unstyled.
    const items = [
      actionItem({ event_id: "future-kind", kind: "something_new" }),
      actionItem({ event_id: "known", kind: "awaiting_review" }),
    ];

    expect(prioritiseActionItems(items).map((item) => item.event_id)).toEqual([
      "known",
      "future-kind",
    ]);
  });

  it("does not mutate the array it is given", () => {
    const items = [
      actionItem({ event_id: "a", kind: "awaiting_review" }),
      actionItem({ event_id: "b", kind: "arrangement_issue" }),
    ];
    const order = items.map((item) => item.event_id);

    prioritiseActionItems(items);

    expect(items.map((item) => item.event_id)).toEqual(order);
  });

  it("tolerates a missing event date without throwing", () => {
    const items = [actionItem({ event_id: "no-date", starts_at: null }), actionItem({ event_id: "dated" })];

    expect(prioritiseActionItems(items)).toHaveLength(2);
  });

  it("every configured kind has a unique key and a display label", () => {
    const keys = ACTION_KINDS.map((kind) => kind.key);
    expect(new Set(keys).size).toBe(keys.length);
    ACTION_KINDS.forEach((kind) => expect(kind.label).toBeTruthy());
  });
});

describe("needs an alternative venue (CR-95 AC3)", () => {
  it("is labelled for the coordinator and shown in red", () => {
    const meta = actionKindMeta("needs_alternative_venue");

    expect(meta.label).toBe("Needs alternative venue");
    expect(meta.tone).toBe("red");
    expect(meta.description).toMatch(/venue/i);
  });

  it("outranks every other kind, including an arrangement issue", () => {
    const items = [
      actionItem({ event_id: "a", kind: "arrangement_issue" }),
      actionItem({ event_id: "b", kind: "needs_alternative_venue" }),
      actionItem({ event_id: "c", kind: "awaiting_review" }),
    ];

    expect(prioritiseActionItems(items).map((item) => item.kind)).toEqual([
      "needs_alternative_venue",
      "arrangement_issue",
      "awaiting_review",
    ]);
  });

  it("counts as an immediate action", () => {
    const summary = summariseActionItems([
      actionItem({ event_id: "a", kind: "needs_alternative_venue" }),
      actionItem({ event_id: "b", kind: "awaiting_review" }),
    ]);

    expect(summary).toEqual({ immediate: 1, awaitingApproval: 1, clarificationResponses: 0, total: 2 });
  });
});

describe("action summary — the three categories named in SCRUM-72 AC1", () => {
  it("counts immediate-action items, first reviews, and clarification responses separately", () => {
    const items = [
      actionItem({ event_id: "a", kind: "arrangement_issue" }),
      actionItem({ event_id: "b", kind: "cancellation_request" }),
      actionItem({ event_id: "c", kind: "awaiting_review" }),
      actionItem({ event_id: "d", kind: "resubmitted" }),
      actionItem({ event_id: "e", kind: "resubmitted" }),
    ];

    expect(summariseActionItems(items)).toEqual({
      immediate: 2,
      awaitingApproval: 1,
      clarificationResponses: 2,
      total: 5,
    });
  });

  it("reports zeroes rather than throwing when there is nothing to do", () => {
    expect(summariseActionItems([])).toEqual({
      immediate: 0,
      awaitingApproval: 0,
      clarificationResponses: 0,
      total: 0,
    });
  });

  it("counts an unrecognised kind in the total but in no named category", () => {
    const summary = summariseActionItems([actionItem({ kind: "something_new" })]);

    expect(summary.total).toBe(1);
    expect(summary.immediate + summary.awaitingApproval + summary.clarificationResponses).toBe(0);
  });
});

describe("active event status overview (SCRUM-72 AC2)", () => {
  it("groups events under every active status, keeping empty statuses visible", () => {
    const groups = groupActiveEventsByStatus([activeEvent({ status: "planning" })]);

    expect(groups.map((group) => group.status)).toEqual([...ACTIVE_COORDINATOR_STATUSES]);
    expect(groups.find((group) => group.status === "planning").events).toHaveLength(1);
    expect(groups.find((group) => group.status === "confirmed").events).toEqual([]);
  });

  it("excludes drafts, which never appear in a staff queue or count (DR-R2)", () => {
    const events = [activeEvent({ event_id: "d", status: "draft" }), activeEvent({ event_id: "p" })];

    const groups = groupActiveEventsByStatus(events);

    expect(groups.flatMap((group) => group.events).map((event) => event.event_id)).toEqual(["p"]);
    expect(countByStatus(events).draft).toBeUndefined();
  });

  it("excludes terminal statuses from the active overview", () => {
    const events = ["rejected", "cancelled", "completed"].map((status, index) =>
      activeEvent({ event_id: `t${index}`, status }),
    );

    expect(groupActiveEventsByStatus(events).flatMap((group) => group.events)).toEqual([]);
  });

  it("orders events within a status by the soonest date first", () => {
    const events = [
      activeEvent({ event_id: "later", starts_at: "2026-12-01T02:00:00Z" }),
      activeEvent({ event_id: "sooner", starts_at: "2026-10-05T02:00:00Z" }),
    ];

    const planning = groupActiveEventsByStatus(events).find((group) => group.status === "planning");

    expect(planning.events.map((event) => event.event_id)).toEqual(["sooner", "later"]);
  });

  it("labels every active status in plain language (LC-R3)", () => {
    ACTIVE_COORDINATOR_STATUSES.forEach((status) => {
      expect(STATUS_LABELS[status]).toBeTruthy();
    });
  });

  it("labels the safety review status in plain language (SCRUM-82, W7 CR-06)", () => {
    expect(STATUS_LABELS.safety_review).toBe("Safety review");
    expect(STATUS_DESCRIPTIONS.safety_review).toBe("Waiting on the Safety Officer's operational safety check.");
  });

  it("calls planning 'Planning', not 'Approved' (QA-18, QA2-8)", () => {
    expect(STATUS_LABELS.planning).toBe("Planning");
  });

  it("reserves 'approved' for no status but confirmed, which the customer treats as the same thing (QA2-8)", () => {
    [...Object.entries(STATUS_LABELS), ...Object.entries(STATUS_DESCRIPTIONS)]
      .filter(([status]) => status !== "confirmed")
      .forEach(([, text]) => {
        expect(text).not.toMatch(/\bapproved\b/i);
      });
  });
});

describe("readiness gaps (schedule overview)", () => {
  it("lists only the blocking arrangements that are not ready (RD-R1)", () => {
    const event = activeEvent({
      readiness: { venue: "pending", equipment: "ready", technical: "not_required" },
    });

    expect(outstandingReadiness(event)).toEqual(["Venue"]);
  });

  it("treats not_required as ready, so an event with no equipment is not flagged", () => {
    const event = activeEvent({
      readiness: { venue: "ready", equipment: "not_required", technical: "not_required" },
    });

    expect(outstandingReadiness(event)).toEqual([]);
  });

  it("reports every outstanding item when nothing is arranged yet", () => {
    const event = activeEvent({
      readiness: { venue: "pending", equipment: "pending", technical: "pending" },
    });

    expect(outstandingReadiness(event)).toEqual(["Venue", "Equipment", "Technical readiness"]);
  });

  it("returns planning events starting inside the window that still have gaps", () => {
    const events = [
      activeEvent({
        event_id: "soon-gap",
        starts_at: "2026-10-08T02:00:00Z",
        readiness: { venue: "pending", equipment: "ready", technical: "ready" },
      }),
      activeEvent({
        event_id: "soon-ready",
        starts_at: "2026-10-08T02:00:00Z",
        readiness: { venue: "ready", equipment: "ready", technical: "ready" },
      }),
      activeEvent({
        event_id: "far-gap",
        starts_at: "2026-12-08T02:00:00Z",
        readiness: { venue: "pending", equipment: "ready", technical: "ready" },
      }),
    ];

    expect(readinessGaps(events, { now: NOW, days: 14 }).map((event) => event.event_id)).toEqual([
      "soon-gap",
    ]);
  });

  it("ignores events that have already started", () => {
    const events = [
      activeEvent({
        event_id: "past",
        starts_at: "2026-09-01T02:00:00Z",
        readiness: { venue: "pending", equipment: "ready", technical: "ready" },
      }),
    ];

    expect(readinessGaps(events, { now: NOW, days: 14 })).toEqual([]);
  });

  it("includes an event exactly on the window boundary", () => {
    const events = [
      activeEvent({
        event_id: "boundary",
        starts_at: "2026-10-15T09:00:00Z",
        readiness: { venue: "pending", equipment: "ready", technical: "ready" },
      }),
    ];

    expect(readinessGaps(events, { now: NOW, days: 14 }).map((event) => event.event_id)).toEqual([
      "boundary",
    ]);
  });
});
