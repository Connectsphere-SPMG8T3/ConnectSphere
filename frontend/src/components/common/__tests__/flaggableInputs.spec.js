import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import BauhausCheckboxGroup from "@/components/common/BauhausCheckboxGroup.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";

const mounted = [];

async function mount(component, props) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(component, props) });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el;
}

const OPTIONS = [{ value: "a", label: "Option A" }];

describe("flag prop on common inputs (SCRUM-33)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it.each([
    ["BauhausInput", BauhausInput, { label: "Purpose", modelValue: "" }, "input"],
    ["BauhausSelect", BauhausSelect, { label: "Layout", options: OPTIONS }, "select"],
    ["BauhausCheckboxGroup", BauhausCheckboxGroup, { label: "Facilities", options: OPTIONS }, "fieldset"],
  ])("%s shows the flag and links it to the control", async (_name, component, props, selector) => {
    const el = await mount(component, { ...props, flag: "Flagged by coordinator" });

    const control = el.querySelector(selector);
    const flagId = control.getAttribute("aria-describedby");
    expect(control.dataset.flagged).toBe("true");
    expect(flagId).toBeTruthy();
    expect(el.querySelector(`#${flagId}`).textContent).toContain("Flagged by coordinator");
  });

  it.each([
    ["BauhausInput", BauhausInput, { label: "Purpose", modelValue: "" }, "input"],
    ["BauhausSelect", BauhausSelect, { label: "Layout", options: OPTIONS }, "select"],
    ["BauhausCheckboxGroup", BauhausCheckboxGroup, { label: "Facilities", options: OPTIONS }, "fieldset"],
  ])("%s is unchanged without a flag", async (_name, component, props, selector) => {
    const el = await mount(component, props);

    const control = el.querySelector(selector);
    expect(control.dataset.flagged).toBeUndefined();
    expect(control.getAttribute("aria-describedby")).toBeNull();
    expect(el.textContent).not.toContain("Flagged");
  });

  it.each([
    ["BauhausInput", BauhausInput, { label: "Purpose", modelValue: "" }, "input"],
    ["BauhausSelect", BauhausSelect, { label: "Layout", options: OPTIONS }, "select"],
  ])("%s swaps its white fill for the flag tint rather than stacking both", async (_name, component, props, selector) => {
    // Both are single-class utilities of equal specificity; the later one in the
    // stylesheet wins, and bg-canvas comes later, so the tint never showed.
    const flagged = (await mount(component, { ...props, flag: "Flagged by coordinator" })).querySelector(selector);
    const plain = (await mount(component, props)).querySelector(selector);

    expect(flagged.classList.contains("bg-bauhaus-yellow/30")).toBe(true);
    expect(flagged.classList.contains("bg-canvas")).toBe(false);
    expect(plain.classList.contains("bg-canvas")).toBe(true);
  });

  it("accepts a number as its value without a prop-type warning", async () => {
    // The event form binds numeric fields (attendance, capacity) straight from the API.
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    const el = await mount(BauhausInput, { label: "Expected attendance", type: "number", modelValue: 40 });

    expect(el.querySelector("input").value).toBe("40");
    expect(warn.mock.calls.flat().join(" ")).not.toContain('Invalid prop: type check failed for prop "modelValue"');
    warn.mockRestore();
  });

  it("describes an input by both its error and its flag", async () => {
    const el = await mount(BauhausInput, { label: "Purpose", modelValue: "", error: "Enter the event purpose.", flag: "Flagged by coordinator" });

    const ids = el.querySelector("input").getAttribute("aria-describedby").split(" ");
    expect(ids).toHaveLength(2);
    expect(el.textContent).toContain("Enter the event purpose.");
    expect(el.textContent).toContain("Flagged by coordinator");
  });
});
