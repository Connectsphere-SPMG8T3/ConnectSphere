import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import EventStatusHistory from "@/components/events/EventStatusHistory.vue";

// CR-106 AC6: the request and the Lead's response are lines in the event history.
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

describe("EventStatusHistory reassignment requests (CR-106 AC6)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("names a request, who asked, why and when", async () => {
    const el = await mountHistory([
      { id: "r1", kind: "reassignment_requested", actor: { id: "c1", full_name: "Marcus Lim" },
        reason: "On leave", at: "2026-10-27T01:00:00Z" },
    ]);

    const item = el.querySelector("li");
    expect(item.textContent).toContain("Reassignment requested");
    expect(item.textContent).toContain("Marcus Lim");
    expect(item.textContent).toContain("On leave");
  });

  it("names a decline with the Lead and the Lead's reason", async () => {
    const el = await mountHistory([
      { id: "r1:declined", kind: "reassignment_declined", actor: { id: "l1", full_name: "Lena Lead" },
        reason: "No cover this month", at: "2026-10-28T01:00:00Z" },
    ]);

    const item = el.querySelector("li");
    expect(item.textContent).toContain("Reassignment request declined");
    expect(item.textContent).toContain("Lena Lead");
    expect(item.textContent).toContain("No cover this month");
  });

  it("names an automatic close and does not invent a person", async () => {
    const el = await mountHistory([
      { id: "r1:closed", kind: "reassignment_request_closed", actor: null,
        reason: "Closed because the event was cancelled.", at: "2026-10-28T01:00:00Z" },
    ]);

    const item = el.querySelector("li");
    expect(item.textContent).toContain("Reassignment request closed");
    expect(item.textContent).toContain("Closed because the event was cancelled.");
  });
});
