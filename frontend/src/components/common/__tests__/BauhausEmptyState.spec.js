import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";

async function mount(props) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  createApp({ render: () => h(BauhausEmptyState, props) }).mount(el);
  await nextTick();
  return el;
}

describe("BauhausEmptyState", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("shows the title and detail in sentence case", async () => {
    const el = await mount({ title: "No events", detail: "Nothing yet." });

    expect(el.querySelector("p").textContent).toBe("No events");
    expect(el.querySelector("p").className).not.toContain("uppercase");
    expect(el.textContent).toContain("Nothing yet.");
  });
});
