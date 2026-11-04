import { createApp, nextTick } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { describe, expect, it } from "vitest";

import BauhausBreadcrumb from "@/components/common/BauhausBreadcrumb.vue";

async function mountBreadcrumb(items) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/:pathMatch(.*)*", component: { template: "<div />" } }],
  });
  await router.push("/");
  const el = document.createElement("div");
  document.body.appendChild(el);
  createApp(BauhausBreadcrumb, { items }).use(router).mount(el);
  await nextTick();
  return el;
}

describe("BauhausBreadcrumb", () => {
  it("links every item but the last and marks the last as the current page", async () => {
    const el = await mountBreadcrumb([
      { label: "Venues", to: "/venues" },
      { label: "Marina Hall" },
    ]);

    const links = [...el.querySelectorAll("a")];
    expect(links.map((a) => a.textContent.trim())).toEqual(["Venues"]);
    expect(links[0].getAttribute("href")).toBe("/venues");
    expect(el.querySelector('[aria-current="page"]').textContent.trim()).toBe("Marina Hall");
    expect(el.querySelector("nav").getAttribute("aria-label")).toBe("Breadcrumb");
  });

  it("puts a separator between items and none before the first", async () => {
    const el = await mountBreadcrumb([
      { label: "Venues", to: "/venues" },
      { label: "Marina Hall", to: "/venues/1" },
      { label: "Edit" },
    ]);

    expect([...el.querySelectorAll("li")].map((li) => li.textContent.trim())).toEqual([
      "Venues",
      "/",
      "Marina Hall",
      "/",
      "Edit",
    ]);
  });

  it("shows a single item as the current page with no link", async () => {
    const el = await mountBreadcrumb([{ label: "Venues" }]);

    expect(el.querySelectorAll("a")).toHaveLength(0);
    expect(el.querySelector('[aria-current="page"]').textContent.trim()).toBe("Venues");
  });
});
