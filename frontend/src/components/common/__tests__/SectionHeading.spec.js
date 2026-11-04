import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import SectionHeading from "@/components/common/SectionHeading.vue";

const mounted = [];

async function mountHeading(props) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(SectionHeading, props, () => "Past events") });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el.querySelector("h2");
}

describe("SectionHeading", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("renders as the heading level asked for, so a page title can use it as an h1", async () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    const app = createApp({ render: () => h(SectionHeading, { id: "find", tone: "red", as: "h1" }, () => "Find a venue") });
    app.mount(el);
    mounted.push(app);
    await nextTick();

    expect(el.querySelector("h1").id).toBe("find");
    expect(el.querySelector("h2")).toBeNull();
  });

  it("is an h2 with the given id and text on a black-bordered colour block", async () => {
    const heading = await mountHeading({ id: "past-events", tone: "blue" });
    expect(heading.dataset.tone).toBe("blue");
    expect(heading.id).toBe("past-events");
    expect(heading.textContent).toBe("Past events");
    for (const name of ["inline-block", "border-2", "border-ink", "sm:border-4", "shadow-hard"]) {
      expect(heading.classList.contains(name)).toBe(true);
    }
  });

  it("uses white text on red and blue, black text on yellow", async () => {
    const red = await mountHeading({ id: "a", tone: "red" });
    expect(red.className).toContain("bg-bauhaus-red");
    expect(red.className).toContain("text-canvas");
    const blue = await mountHeading({ id: "b", tone: "blue" });
    expect(blue.className).toContain("bg-bauhaus-blue");
    expect(blue.className).toContain("text-canvas");
    const yellow = await mountHeading({ id: "c", tone: "yellow" });
    expect(yellow.className).toContain("bg-bauhaus-yellow");
    expect(yellow.className).toContain("text-ink");
  });
});
