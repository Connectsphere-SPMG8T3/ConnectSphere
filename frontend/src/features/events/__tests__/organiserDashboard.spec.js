import { describe, expect, it } from "vitest";

import {
  filterOrganiserEvents,
  getOrganiserAction,
  groupOrganiserEvents,
  groupOrganiserActiveEvents,
  summariseOrganiserEvents,
  needsOrganiserAttention,
  sortOrganiserEvents,
} from "@/features/events/organiserDashboard";

function event(overrides = {}) {
  return {
    id: "e1",
    name: "Annual Conference",
    status: "under_review",
    date: "2026-11-01",
    startTime: "10:00",
    endTime: "15:00",
    eventTimezone: "Asia/Singapore",
    expectedAttendance: 150,
    venueName: "Hall A",
    coordinatorId: "c1",
    ...overrides,
  };
}

describe("organiser event filtering", () => {
  it("filters by status without mutating the source collection", () => {
    const events = [event({ id: "draft", status: "draft" }), event({ id: "confirmed", status: "confirmed" })];

    expect(filterOrganiserEvents(events, { status: "draft" }).map((item) => item.id)).toEqual(["draft"]);
    expect(events.map((item) => item.id)).toEqual(["draft", "confirmed"]);
  });

  it("filters by any selected status when multiple statuses are provided", () => {
    const events = [
      event({ id: "draft", status: "draft" }),
      event({ id: "confirmed", status: "confirmed" }),
      event({ id: "returned", status: "returned" }),
    ];

    expect(filterOrganiserEvents(events, { status: ["draft", "confirmed"] }).map((item) => item.id)).toEqual([
      "draft",
      "confirmed",
    ]);
  });

  it("searches event names case-insensitively and trims the query", () => {
    const events = [event({ id: "one", name: "Regional Planning Workshop" }), event({ id: "two", name: "Annual Dinner" })];

    expect(filterOrganiserEvents(events, { search: "  planning  " }).map((item) => item.id)).toEqual(["one"]);
    expect(filterOrganiserEvents(events, { search: "DINNER" }).map((item) => item.id)).toEqual(["two"]);
  });

  it("applies status and name filters together", () => {
    const events = [
      event({ id: "draft-match", name: "Planning Workshop", status: "draft" }),
      event({ id: "request-match", name: "Planning Workshop", status: "under_review" }),
      event({ id: "other", name: "Annual Dinner", status: "draft" }),
    ];

    expect(filterOrganiserEvents(events, { status: "draft", search: "planning" }).map((item) => item.id)).toEqual([
      "draft-match",
    ]);
  });

  it("returns all events when filters are empty", () => {
    const events = [event({ id: "one" }), event({ id: "two" })];

    expect(filterOrganiserEvents(events, {})).toEqual(events);
  });
});

describe("organiser event sorting", () => {
  it("sorts by event date ascending and puts missing dates last", () => {
    const events = [
      event({ id: "missing", date: "" }),
      event({ id: "later", date: "2026-12-01" }),
      event({ id: "sooner", date: "2026-10-01" }),
    ];

    expect(sortOrganiserEvents(events, { field: "date", direction: "asc" }).map((item) => item.id)).toEqual([
      "sooner",
      "later",
      "missing",
    ]);
  });

  it("sorts names case-insensitively in descending order", () => {
    const events = [event({ id: "a", name: "Annual Dinner" }), event({ id: "z", name: "Regional Workshop" })];

    expect(sortOrganiserEvents(events, { field: "name", direction: "desc" }).map((item) => item.id)).toEqual(["z", "a"]);
  });

  it("sorts by lifecycle status with a stable event-id tie breaker", () => {
    const events = [
      event({ id: "b", status: "confirmed" }),
      event({ id: "a", status: "confirmed" }),
      event({ id: "c", status: "draft" }),
    ];

    expect(sortOrganiserEvents(events, { field: "status", direction: "asc" }).map((item) => item.id)).toEqual([
      "c",
      "a",
      "b",
    ]);
  });
});

describe("organiser dashboard grouping and actions", () => {
  it("groups organiser events using the active-status overview shape", () => {
    const groups = groupOrganiserActiveEvents([
      event({ id: "submitted", status: "submitted" }),
      event({ id: "review", status: "under_review" }),
      event({ id: "planning", status: "planning" }),
      event({ id: "confirmed", status: "confirmed" }),
      event({ id: "completed", status: "completed" }),
      event({ id: "draft", status: "draft" }),
    ]);

    expect(groups.map((group) => group.status)).toEqual([
      "under_review",
      "planning",
      "confirmed",
      "completed",
    ]);
    expect(groups[0].events.map((item) => item.id)).toEqual(["submitted", "review"]);
    expect(groups[3].events.map((item) => item.id)).toEqual(["completed"]);
  });

  it("summarises overview counts into action and lifecycle groups", () => {
    const events = [
      event({ id: "draft", status: "draft" }),
      event({ id: "returned", status: "returned" }),
      event({ id: "rejected", status: "rejected" }),
      event({ id: "submitted", status: "submitted" }),
      event({ id: "review", status: "under_review" }),
      event({ id: "planning", status: "planning" }),
      event({ id: "confirmed", status: "confirmed" }),
      event({ id: "completed", status: "completed" }),
    ];

    expect(summariseOrganiserEvents(events)).toEqual({
      needsAction: { drafts: 1, returned: 1, rejected: 1, total: 3 },
      myEvents: { underReview: 2, planning: 1, confirmed: 1, completed: 1, total: 5 },
    });
  });

  it("keeps drafts separate from submitted requests and includes every lifecycle status", () => {
    const events = [
      event({ id: "draft", status: "draft" }),
      event({ id: "review", status: "under_review" }),
      event({ id: "done", status: "completed" }),
    ];

    const groups = groupOrganiserEvents(events);

    expect(groups.drafts.map((item) => item.id)).toEqual(["draft"]);
    expect(groups.requests.map((item) => item.id)).toEqual(["review", "done"]);
  });

  it("identifies organiser attention states", () => {
    expect(needsOrganiserAttention(event({ status: "draft" }))).toBe(true);
    expect(needsOrganiserAttention(event({ status: "returned" }))).toBe(true);
    expect(needsOrganiserAttention(event({ status: "submitted", coordinatorId: null }))).toBe(true);
    expect(needsOrganiserAttention(event({ status: "under_review" }))).toBe(false);
    expect(needsOrganiserAttention(event({ status: "confirmed" }))).toBe(false);
  });

  it("returns only lifecycle-appropriate dashboard actions", () => {
    expect(getOrganiserAction(event({ status: "draft" }))).toEqual({ kind: "continue_draft", label: "Edit draft" });
    expect(getOrganiserAction(event({ status: "returned" }))).toEqual({ kind: "amend", label: "Amend and resubmit" });
    expect(getOrganiserAction(event({ status: "submitted", coordinatorId: null }))).toEqual({ kind: "view", label: "View event" });
    expect(getOrganiserAction(event({ status: "confirmed" }))).toEqual({ kind: "view", label: "View event" });
  });
});
