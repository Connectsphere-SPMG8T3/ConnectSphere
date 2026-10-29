import { createApp, h } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import TechnicalHistoryList from "@/components/equipment/TechnicalHistoryList.vue";

const apps = [];

function mountList(entries) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(TechnicalHistoryList, { entries }) });
  app.mount(el);
  apps.push(app);
}

afterEach(() => {
  apps.splice(0).forEach((app) => app.unmount());
  document.body.innerHTML = "";
});

describe("TechnicalHistoryList (SCRUM-24 AC13, SCRUM-44 AC8)", () => {
  it("names each change, the line, its before and after values, who and when", () => {
    mountList([{
      action: "edited", line_label: "6 × Projector", from_status: "reserved", to_status: "re_review",
      detail: "Quantity: 4 → 6.", actor_name: "Marcus Lim", created_at: "2026-10-26T02:00:00Z",
    }]);

    const item = document.querySelector("li").textContent;
    expect(item).toContain("Changed by the coordinator · 6 × Projector · Reserved → Re-review");
    expect(item).toContain("Quantity: 4 → 6.");
    expect(item).toContain("Marcus Lim · 26 Oct 2026, 10:00 am");
  });

  it("an entry without an actor was the system", () => {
    mountList([{ action: "technical_status", line_label: null, from_status: "pending", to_status: "ready",
      detail: null, actor_name: null, created_at: "2026-10-26T02:00:00Z" }]);

    expect(document.querySelector("li").textContent).toContain("System");
  });

  it("says so when nothing is recorded", () => {
    mountList([]);

    expect(document.body.textContent).toContain("Nothing recorded yet.");
    expect(document.querySelector("ol")).toBeNull();
  });
});
