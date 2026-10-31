import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import EventStatusHistory from "@/components/events/EventStatusHistory.vue";

const mounted = [];

async function mountHistory(entries) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(EventStatusHistory, { entries }) });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el;
}

// The exact rendering of "Sept"/"Sep" depends on Node's bundled ICU, so the
// expectation is computed with the same formatter options rather than
// hardcoded, per the task brief's fallback.
const expectedDate = new Intl.DateTimeFormat("en-SG", {
  dateStyle: "medium",
  timeZone: "Asia/Singapore",
}).format(new Date("2026-09-24T06:05:00Z"));

describe("EventStatusHistory (QA-70)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("lists each change with its label, who made it, when and why", async () => {
    const el = await mountHistory([
      { id: "h2", from_status: "under_review", to_status: "rejected", reason: "Venue unavailable",
        at: "2026-09-24T06:05:00Z", actor: { id: "c1", full_name: "Marcus Lim" } },
      { id: "h1", from_status: "under_review", to_status: "planning", reason: null,
        at: "2026-09-23T03:00:00Z", actor: { id: "c1", full_name: "Marcus Lim" } },
    ]);

    const items = el.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain("Rejected");
    expect(items[0].textContent).toContain("Marcus Lim");
    expect(items[0].textContent).toContain("Venue unavailable");
    expect(items[0].textContent).toContain(expectedDate);
    expect(items[1].textContent).toContain("Planning");
  });

  it("never calls planning 'approved' (QA2-8)", async () => {
    const el = await mountHistory([
      { id: "h1", from_status: "under_review", to_status: "planning", reason: null,
        at: "2026-09-23T03:00:00Z", actor: { id: "c1", full_name: "Marcus Lim" } },
    ]);

    expect(el.textContent.toLowerCase()).not.toContain("approved");
  });

  it("names a removed account honestly", async () => {
    const el = await mountHistory([
      { id: "h1", from_status: null, to_status: "under_review", reason: null, at: "2026-09-23T03:00:00Z", actor: null },
    ]);

    expect(el.textContent).toContain("Unknown user");
  });

  it("says so when there is no history yet", async () => {
    const el = await mountHistory([]);

    expect(el.textContent).toContain("No status changes recorded yet.");
  });

  it("says who an event was reassigned from and to, and who did it (SCRUM-12)", async () => {
    const el = await mountHistory([
      { id: "a1", kind: "reassignment", from_status: null, to_status: null, reason: null,
        at: "2026-09-24T06:05:00Z", actor: { id: "l1", full_name: "Joyce Lim" },
        from_coordinator: { id: "c1", full_name: "Marcus Lim" }, to_coordinator: { id: "c2", full_name: "Priya Nair" } },
      { id: "h1", kind: "status", from_status: "submitted", to_status: "under_review", reason: "Assigned to Marcus Lim",
        at: "2026-09-23T03:00:00Z", actor: { id: "l1", full_name: "Joyce Lim" } },
    ]);

    const [reassigned, assigned] = el.querySelectorAll("li");
    expect(reassigned.textContent).toContain("Reassigned to Priya Nair");
    expect(reassigned.textContent).toContain("from Marcus Lim");
    expect(reassigned.textContent).toContain("by Joyce Lim");
    expect(reassigned.textContent).not.toContain("Unknown");
    expect(assigned.textContent).toContain("Under review");
  });

  it("reads a reassignment with no previous coordinator as an assignment", async () => {
    const el = await mountHistory([
      { id: "a1", kind: "reassignment", from_status: null, to_status: null, reason: null,
        at: "2026-09-24T06:05:00Z", actor: null, from_coordinator: null, to_coordinator: { id: "c2", full_name: "Priya Nair" } },
    ]);

    expect(el.textContent).toContain("Assigned to Priya Nair");
    expect(el.textContent).not.toContain("from ");
  });

  it("story 84 heads a cancellation request with who asked and why", async () => {
    const el = await mountHistory([
      { id: "r1", kind: "cancellation_requested", from_status: null, to_status: null, reason: "Speaker withdrew",
        at: "2026-10-23T01:00:00Z", actor: { id: "o1", full_name: "Priya Nair" } },
    ]);

    const [item] = el.querySelectorAll("li");
    expect(item.querySelector("p").textContent).toBe("Cancellation requested");
    expect(item.textContent).toContain("by Priya Nair");
    expect(item.textContent).toContain("Speaker withdrew");
  });

  it("story 115 heads a rejected cancellation request with who rejected it and why", async () => {
    const el = await mountHistory([
      { id: "r1:rejected", kind: "cancellation_rejected", from_status: null, to_status: null,
        reason: "The venue is already paid for", at: "2026-10-24T02:00:00Z",
        actor: { id: "c1", full_name: "Marcus Lim" } },
    ]);

    const [item] = el.querySelectorAll("li");
    expect(item.querySelector("p").textContent).toBe("Cancellation request rejected");
    expect(item.textContent).toContain("by Marcus Lim");
    expect(item.textContent).toContain("The venue is already paid for");
  });
});

describe("EventStatusHistory change requests (story 32)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("titles a change request and lists what it would change, then why", async () => {
    const el = await mountHistory([{
      id: "r1", kind: "change_requested", actor: { full_name: "Priya Nair" }, at: "2026-10-24T01:00:00Z",
      reason: "Sponsor wants more seats",
      changes: {
        event: [{ field: "expected_attendance", before: 80, after: 120 }],
        spaces: [{ space_id: "s1", label: "Main hall", fields: [{ field: "layout_preference", before: "theatre", after: "banquet" }] }],
      },
    }]);

    expect(el.querySelector("li p").textContent).toBe("Change requested");
    expect(el.textContent).toContain("Expected attendance: 80 → 120");
    expect(el.textContent).toContain("Main hall: layout: theatre → banquet");
    expect(el.textContent).toContain("Sponsor wants more seats");
  });

  it("titles a superseded request as closed, with why", async () => {
    const el = await mountHistory([{
      id: "r1:closed", kind: "change_request_closed", actor: null, at: "2026-10-25T01:00:00Z",
      reason: "Closed because the event was cancelled.", changes: null,
    }]);

    expect(el.querySelector("li p").textContent).toBe("Change request closed");
    expect(el.textContent).toContain("Closed because the event was cancelled.");
  });
});

describe("EventStatusHistory change decisions (story 37)", () => {
  it("heads an approved change with who approved it and what changed", async () => {
    const el = await mountHistory([
      { id: "r1:approved", kind: "change_approved", from_status: null, to_status: null, reason: null,
        changes: { event: [{ field: "expected_attendance", before: 80, after: 120 }], spaces: [] },
        at: "2026-10-25T02:00:00Z", actor: { id: "c1", full_name: "Marcus Lim" } },
    ]);

    const [item] = el.querySelectorAll("li");
    expect(item.querySelector("p").textContent).toBe("Change approved");
    expect(item.textContent).toContain("by Marcus Lim");
    expect(item.textContent).toContain("120");
  });

  it("heads a rejected change with who rejected it and why", async () => {
    const el = await mountHistory([
      { id: "r1:rejected", kind: "change_rejected", from_status: null, to_status: null,
        reason: "The venue can't take more people", at: "2026-10-25T02:00:00Z",
        actor: { id: "c1", full_name: "Marcus Lim" } },
    ]);

    const [item] = el.querySelectorAll("li");
    expect(item.querySelector("p").textContent).toBe("Change request rejected");
    expect(item.textContent).toContain("by Marcus Lim");
    expect(item.textContent).toContain("The venue can't take more people");
  });
});

describe("EventStatusHistory change history (story 62)", () => {
  const olivia = { id: "o1", full_name: "Olivia Tan" };

  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("heads an edit with the field, then what it changed from and to", async () => {
    const el = await mountHistory([
      { id: "e1", kind: "edit", field: "description", old_value: null, new_value: "Now with a keynote",
        at: "2026-09-24T06:05:00Z", actor: olivia },
    ]);

    const item = el.querySelector("li");
    expect(item.querySelector("p").textContent).toBe("Description changed");
    expect(item.textContent).toContain("by Olivia Tan");
    expect(item.textContent).toContain("From: (empty)");
    expect(item.textContent).toContain("To: Now with a keynote");
  });

  it("reads numbers, yes/no, lists and times as a person would", async () => {
    const el = await mountHistory([
      { id: "e1", kind: "edit", field: "expected_attendance", old_value: 12, new_value: 40,
        at: "2026-09-24T06:05:00Z", actor: olivia },
      { id: "e2", kind: "edit", field: "waitlist_enabled", old_value: false, new_value: true,
        at: "2026-09-24T06:04:00Z", actor: olivia },
      { id: "e3", kind: "edit", field: "facilities_required", old_value: [], new_value: ["projector", "wifi"],
        at: "2026-09-24T06:03:00Z", actor: olivia },
      { id: "e4", kind: "edit", field: "starts_at", old_value: "2026-09-24T06:05:00+00:00",
        new_value: "2026-09-25T06:05:00+00:00", at: "2026-09-24T06:02:00Z", actor: olivia },
    ]);

    const [attendance, waitlist, facilities, start] = el.querySelectorAll("li");
    expect(attendance.textContent).toContain("From: 12");
    expect(attendance.textContent).toContain("To: 40");
    expect(waitlist.querySelector("p").textContent).toBe("Waitlist when full changed");
    expect(waitlist.textContent).toContain("From: No");
    expect(waitlist.textContent).toContain("To: Yes");
    expect(facilities.textContent).toContain("From: (empty)");
    expect(facilities.textContent).toContain("To: projector, wifi");
    expect(start.textContent).toContain(`From: ${expectedDate}`);
  });

  it("heads a safety decision with its outcome, and shows a comment only when one is sent", async () => {
    const el = await mountHistory([
      { id: "s2", kind: "safety_decision", decision: "changes_requested", reason: "Add a second exit",
        at: "2026-09-24T06:05:00Z", actor: { id: "s", full_name: "Hafiz Ismail" } },
      { id: "s1", kind: "safety_decision", decision: "approved", reason: null,
        at: "2026-09-23T06:05:00Z", actor: { id: "s", full_name: "Hafiz Ismail" } },
    ]);

    const [requested, approved] = el.querySelectorAll("li");
    expect(requested.querySelector("p").textContent).toBe("Safety check: Changes requested");
    expect(requested.textContent).toContain("Add a second exit");
    expect(approved.querySelector("p").textContent).toBe("Safety check: Approved");
    expect(approved.querySelectorAll("p")).toHaveLength(2);
  });

  it("heads a booking step with its venue and what happened, and names the system when no one acted", async () => {
    const el = await mountHistory([
      { id: "b1", kind: "booking", action: "approved", venue_name: "Hall A", reason: null,
        at: "2026-09-24T06:05:00Z", actor: { id: "v", full_name: "Priya Nair" } },
      { id: "b2", kind: "booking", action: "expired", venue_name: "Hall B", reason: null,
        at: "2026-09-23T06:05:00Z", actor: null },
    ]);

    const [approved, expired] = el.querySelectorAll("li");
    expect(approved.querySelector("p").textContent).toBe("Hall A: Approved");
    expect(approved.textContent).toContain("by Priya Nair");
    expect(expired.textContent).toContain("by System");
  });

  it("heads a technical update with what happened and to which line", async () => {
    const el = await mountHistory([
      { id: "t1", kind: "technical", action: "preparation", line_label: null, detail: null,
        at: "2026-09-24T06:05:00Z", actor: { id: "t", full_name: "Daniel Wong" } },
      { id: "t2", kind: "technical", action: "reserved", line_label: "2 × Projector", detail: null,
        at: "2026-09-23T06:05:00Z", actor: { id: "t", full_name: "Daniel Wong" } },
    ]);

    const [preparation, reserved] = el.querySelectorAll("li");
    expect(preparation.querySelector("p").textContent).toBe("Equipment: Preparation stage changed");
    expect(reserved.querySelector("p").textContent).toContain("2 × Projector");
  });

  it("heads a venue edit with the venue and lists only what changed", async () => {
    const el = await mountHistory([
      { id: "v1", kind: "venue_edit", venue_name: "Hall A", old_value: { capacity: 120, name: "Hall A" },
        new_value: { capacity: 100, name: "Hall A" }, at: "2026-09-24T06:05:00Z",
        actor: { id: "v", full_name: "Priya Nair" } },
    ]);

    const item = el.querySelector("li");
    expect(item.querySelector("p").textContent).toBe("Hall A details changed");
    expect(item.textContent).toContain("by Priya Nair");
    expect(item.textContent).toContain("Capacity: 120 → 100");
    expect(item.textContent).not.toContain("Name:");
  });
});
