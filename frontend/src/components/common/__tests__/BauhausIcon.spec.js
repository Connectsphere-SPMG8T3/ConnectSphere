import { createApp, h, nextTick } from "vue";
import { describe, expect, it } from "vitest";

import BauhausIcon from "@/components/common/BauhausIcon.vue";

async function mountIcon(name) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  createApp({ render: () => h(BauhausIcon, { name }) }).mount(el);
  await nextTick();
  return el.querySelector("svg");
}

describe("BauhausIcon", () => {
  it.each(["edit", "calendar", "block", "deactivate", "reactivate"])("draws the %s icon, hidden from screen readers", async (name) => {
    const svg = await mountIcon(name);

    expect(svg.getAttribute("aria-hidden")).toBe("true");
    expect(svg.getAttribute("stroke")).toBe("currentColor");
    expect(svg.children.length).toBeGreaterThan(0);
  });

  it("draws only straight edges and circles: no rounded rectangles", async () => {
    const svg = await mountIcon("calendar");

    expect(svg.querySelector("[rx], [ry]")).toBeNull();
  });
});
