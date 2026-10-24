import { createApp, h, nextTick } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
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

describe("BauhausButton hover", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("turns gray with black text on hover in every variant", async () => {
    for (const variant of ["primary", "secondary", "yellow", "outline"]) {
      const button = await mountButton({ variant });
      for (const name of ["hover:bg-muted", "hover:text-ink"]) expect(button.classList.contains(name)).toBe(true);
    }
  });

  it("has no hover fill while disabled", async () => {
    const button = await mountButton({ disabled: true });
    expect(button.classList.contains("hover:bg-muted")).toBe(false);
  });
});

describe("BauhausButton as a link", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("renders a router link with the button's look when given a destination", async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/:any(.*)", component: { render: () => null } }] });
    const el = document.createElement("div");
    document.body.appendChild(el);
    const app = createApp({ render: () => h(BauhausButton, { to: "/login", variant: "outline", size: "sm" }, () => "Sign in") }).use(router);
    app.mount(el);
    mounted.push(app);
    await router.isReady();
    await nextTick();

    expect(el.querySelector("button")).toBeNull();
    const link = el.querySelector("a");
    expect(link.getAttribute("href")).toBe("/login");
    expect(link.getAttribute("type")).toBeNull();
    for (const name of ["border-2", "border-ink", "shadow-hard", "bg-canvas", "px-4", "hover:bg-muted", "active-press"]) {
      expect(link.classList.contains(name)).toBe(true);
    }
  });
});
