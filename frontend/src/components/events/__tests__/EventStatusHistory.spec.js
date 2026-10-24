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
});
