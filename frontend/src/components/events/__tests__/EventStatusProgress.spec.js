import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import EventStatusProgress from "@/components/events/EventStatusProgress.vue";

const mounted = [];

async function mountProgress(status) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(EventStatusProgress, { status }) });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el;
}

const steps = (el) => [...el.querySelectorAll("li")];

describe("EventStatusProgress", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("lists every step and marks the current one for assistive technology", async () => {
    const el = await mountProgress("planning");
    expect(el.querySelector("ol").getAttribute("aria-label")).toBe("Event progress");
    expect(steps(el).map((li) => li.textContent.trim().replace(/\s+/g, " ")))
      .toEqual(["Under review (done)", "Planning", "Safety review", "Confirmed", "Completed"]);
    const current = el.querySelectorAll('[aria-current="step"]');
    expect(current).toHaveLength(1);
    expect(current[0].textContent).toContain("Planning");
  });

  it("fills done steps in ink, the current step in blue and leaves later steps empty", async () => {
    const el = await mountProgress("safety_review");
    const bars = steps(el).map((li) => li.querySelector("[data-bar]"));
    expect(bars[0].classList.contains("bg-ink")).toBe(true);
    expect(bars[1].classList.contains("bg-ink")).toBe(true);
    expect(bars[2].classList.contains("bg-bauhaus-blue")).toBe(true);
    expect(bars[3].classList.contains("bg-canvas")).toBe(true);
  });

  it("shows a returned request in red at the first step", async () => {
    const el = await mountProgress("returned");
    const first = steps(el)[0];
    expect(first.getAttribute("aria-current")).toBe("step");
    expect(first.textContent).toContain("Returned for amendment");
    expect(first.querySelector("[data-bar]").classList.contains("bg-bauhaus-red")).toBe(true);
  });

  it.each([["rejected", "Rejected"], ["cancelled", "Cancelled"]])("shows only the outcome badge when %s", async (status, label) => {
    const el = await mountProgress(status);
    expect(el.querySelector("ol")).toBeNull();
    expect(el.querySelector('[data-testid="status-outcome"]').textContent.trim()).toBe(label);
  });
});
