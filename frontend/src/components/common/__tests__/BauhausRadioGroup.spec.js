// CR-108: a single-choice chip group, modelled on BauhausCheckboxGroup.
import { createApp, h, nextTick, ref } from "vue";
import { afterEach, describe, expect, it } from "vitest";
import BauhausRadioGroup from "@/components/common/BauhausRadioGroup.vue";

const OPTIONS = [
  { value: "satisfactory", label: "Satisfactory" },
  { value: "concern", label: "Concern" },
  { value: "not_applicable", label: "Not applicable" },
];
const apps = [];

async function mount(props = {}) {
  const model = ref(props.modelValue ?? null);
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(BauhausRadioGroup, {
      label: "Layout", options: OPTIONS, ...props, modelValue: model.value,
      "onUpdate:modelValue": (value) => { model.value = value; },
    }),
  });
  apps.push(app);
  app.mount(el);
  await nextTick();
  return { el, model };
}

afterEach(() => { apps.splice(0).forEach((app) => app.unmount()); document.body.innerHTML = ""; });

describe("BauhausRadioGroup", () => {
  it("is a labelled fieldset with one native radio per option", async () => {
    const { el } = await mount();
    expect(el.querySelector("fieldset legend").textContent).toContain("Layout");
    const radios = [...el.querySelectorAll("input[type=radio]")];
    expect(radios.map((radio) => radio.value)).toEqual(["satisfactory", "concern", "not_applicable"]);
    expect(el.textContent).toContain("Not applicable");
  });

  it("puts the radios in one group so only one can be chosen", async () => {
    const { el } = await mount();
    const names = new Set([...el.querySelectorAll("input[type=radio]")].map((radio) => radio.name));
    expect(names.size).toBe(1);
    expect([...names][0]).not.toBe("");
  });

  it("gives two groups different names", async () => {
    const first = await mount();
    const second = await mount();
    expect(first.el.querySelector("input").name).not.toBe(second.el.querySelector("input").name);
  });

  it("starts with nothing chosen and checks the model's value", async () => {
    expect([...(await mount()).el.querySelectorAll("input:checked")]).toHaveLength(0);
    const { el } = await mount({ modelValue: "concern" });
    expect([...el.querySelectorAll("input:checked")].map((radio) => radio.value)).toEqual(["concern"]);
  });

  it("updates the model when an option is chosen, and again when the choice changes", async () => {
    const { el, model } = await mount();
    el.querySelectorAll("input")[1].click();
    await nextTick();
    expect(model.value).toBe("concern");
    el.querySelectorAll("input")[2].click();
    await nextTick();
    expect(model.value).toBe("not_applicable");
    expect([...el.querySelectorAll("input:checked")].map((radio) => radio.value)).toEqual(["not_applicable"]);
  });

  it("marks a required group with an asterisk hidden from screen readers", async () => {
    const { el } = await mount({ required: true });
    expect(el.querySelector("legend [aria-hidden=true]").textContent).toContain("*");
    expect((await mount()).el.querySelector("legend [aria-hidden=true]")).toBeNull();
  });

  it("cannot be changed while disabled", async () => {
    const { el, model } = await mount({ disabled: true });
    expect(el.querySelector("fieldset").disabled).toBe(true);
    el.querySelectorAll("input")[0].click();
    await nextTick();
    expect(model.value).toBeNull();
  });

  it("can disable one option and leave the others", async () => {
    const { el } = await mount({ options: [{ value: "a", label: "A", disabled: true }, { value: "b", label: "B" }] });
    const [a, b] = el.querySelectorAll("input");
    expect(a.disabled).toBe(true);
    expect(b.disabled).toBe(false);
  });

  it("fills the chosen option so the choice is visible without colour alone being the cue", async () => {
    const { el } = await mount({ modelValue: "concern" });
    const labels = [...el.querySelectorAll("label")];
    expect(labels[1].className).toContain("bg-bauhaus-yellow");
    expect(labels[0].className).toContain("bg-canvas");
  });
});
