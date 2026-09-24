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
});
