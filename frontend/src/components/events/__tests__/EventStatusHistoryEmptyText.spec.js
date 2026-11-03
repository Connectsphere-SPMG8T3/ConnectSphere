import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import EventStatusHistory from "@/components/events/EventStatusHistory.vue";

// SCRUM-81: the Lead's reassignment list is empty far more often than a status history is,
// and "No status changes recorded yet." would be the wrong thing to tell them.
const mounted = [];

async function mountHistory(props) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(EventStatusHistory, props) });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el;
}

const REASSIGNMENT = {
  id: "h1",
  kind: "reassignment",
  at: "2026-11-02T09:00:00Z",
  actor: { full_name: "Joyce" },
  from_coordinator: { full_name: "Marcus" },
  to_coordinator: { full_name: "Priya" },
};

describe("EventStatusHistory empty text", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("keeps its default wording", async () => {
    const el = await mountHistory({ entries: [] });
    expect(el.textContent.trim()).toBe("No status changes recorded yet.");
  });

  it("uses the wording a screen passes", async () => {
    const el = await mountHistory({ entries: [], emptyText: "No reassignments yet." });
    expect(el.textContent.trim()).toBe("No reassignments yet.");
  });

  it("ignores the empty text once there are entries", async () => {
    const el = await mountHistory({ entries: [REASSIGNMENT], emptyText: "No reassignments yet." });
    expect(el.textContent).not.toContain("No reassignments yet.");
    expect(el.textContent).toContain("Reassigned to Priya");
  });
});
