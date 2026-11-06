// D75: tech support's Requests page opens on every status, so a Reserved line on an
// event ready for technical preparation is listed without changing the filter.
// "Waiting on you" stays one choice away in the Status filter.
import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import EquipmentRequestQueue from "@/components/equipment/EquipmentRequestQueue.vue";

const LINE = {
  equipment_id: "q1", equipment_name: "4K Projector", equipment_type: "AV", quantity: 1,
  technical_requirements: null, not_available_reason: null, requested_by: { full_name: "Casey Coordinator" },
  created_at: "2031-11-01T01:00:00Z",
};
const LINES = [
  { ...LINE, id: "pending-line", event_id: "e1", event_name: "Planning gala", status: "pending", event_starts_at: "2031-12-01T01:00:00Z" },
  { ...LINE, id: "reserved-line", event_id: "e2", event_name: "Confirmed summit", status: "reserved", event_starts_at: "2031-12-02T01:00:00Z" },
];
const mounted = [];

async function mountQueue(lines = LINES) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: {} }, { name: "tech-support-event", path: "/tech-support/events/:id", component: {} }],
  });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(EquipmentRequestQueue, { queue: { lines, isLoading: false, error: null } }) });
  app.use(router);
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el;
}

const cards = (el) => [...el.querySelectorAll('[data-testid="equipment-request-card"]')].map((c) => c.dataset.requestStatus);
const statusSelect = (el) => [...el.querySelectorAll("select")][0];

afterEach(() => {
  mounted.splice(0).forEach((app) => app.unmount());
  document.body.innerHTML = "";
});

describe("EquipmentRequestQueue default filter (D75)", () => {
  it("opens on All statuses, so a Reserved line is listed without changing the filter", async () => {
    const el = await mountQueue();

    expect(statusSelect(el).value).toBe("all");
    expect(cards(el)).toEqual(["pending", "reserved"]);
    expect(el.textContent).toContain("Confirmed summit");
  });

  it("still narrows to the lines waiting on tech support when Waiting on you is chosen", async () => {
    const el = await mountQueue();

    statusSelect(el).value = "waiting";
    statusSelect(el).dispatchEvent(new Event("change"));
    await nextTick();

    expect(cards(el)).toEqual(["pending"]);
  });

  it("says that every line is listed and where to find only the waiting ones", async () => {
    const el = await mountQueue();

    expect(el.textContent).toContain("Every line on an open event is listed");
    expect(el.textContent).toContain("Waiting on you");
    expect(el.textContent).not.toContain("Lines waiting on you appear first");
  });
});
