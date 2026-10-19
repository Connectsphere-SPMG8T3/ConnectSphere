import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import BauhausButton from "@/components/common/BauhausButton.vue";

const mounted = [];

async function mountButton(props = {}) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(BauhausButton, props, () => "Go") });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el.querySelector("button");
}

describe("BauhausButton size", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("keeps the standard size by default", async () => {
    const button = await mountButton();
    for (const name of ["px-6", "py-3", "text-sm", "sm:border-4"]) expect(button.classList.contains(name)).toBe(true);
  });

  it("is tighter and keeps the thin border at size sm", async () => {
    const button = await mountButton({ size: "sm" });
    for (const name of ["px-4", "py-2", "text-xs"]) expect(button.classList.contains(name)).toBe(true);
    for (const name of ["px-6", "py-3", "text-sm", "sm:border-4"]) expect(button.classList.contains(name)).toBe(false);
  });
});
