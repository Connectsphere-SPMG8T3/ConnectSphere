// CR-108 AC1-AC2: the officer's checklist form, five factors per venue plus equipment placement once.
import { createApp, h, nextTick, ref } from "vue";
import { afterEach, describe, expect, it } from "vitest";
import SafetyChecklist from "@/components/events/SafetyChecklist.vue";
import { markKey } from "@/features/events/safetyChecklist";

const VENUES = [
  { booking_id: "b1", venue_name: "Town Hall" },
  { booking_id: "b2", venue_name: "Atrium" },
];
const apps = [];

async function mount({ venues = VENUES, marks = {}, disabled = false } = {}) {
  const model = ref(marks);
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(SafetyChecklist, {
      venues, disabled, modelValue: model.value,
      "onUpdate:modelValue": (value) => { model.value = value; },
    }),
  });
  apps.push(app);
  app.mount(el);
  await nextTick();
  return { el, model };
}
const legends = (el) => [...el.querySelectorAll("legend")].map((legend) => legend.textContent.replace("*", "").trim());
const radio = (el, legend, value, venueIndex = 0) => {
  const group = [...el.querySelectorAll("fieldset")].filter((f) => f.querySelector("legend").textContent.includes(legend))[venueIndex];
  return group.querySelector(`input[value="${value}"]`);
};

afterEach(() => { apps.splice(0).forEach((app) => app.unmount()); document.body.innerHTML = ""; });

describe("SafetyChecklist", () => {
  it("asks the five venue factors for each venue and equipment placement once", async () => {
    const { el } = await mount();
    expect(legends(el).filter((l) => l === "Layout")).toHaveLength(2);
    expect(legends(el).filter((l) => l === "Equipment placement")).toHaveLength(1);
    expect(legends(el)).toHaveLength(11);
    expect(legends(el).slice(0, 5)).toEqual(["Attendance/capacity", "Layout", "Emergency access", "Accessibility", "Venue restrictions"]);
  });

  it("names each venue and the whole event", async () => {
    const { el } = await mount();
    const headings = [...el.querySelectorAll("h3")].map((h) => h.textContent.trim());
    expect(headings).toEqual(["Town Hall", "Atrium", "Whole event"]);
  });

  it("offers Satisfactory, Concern and Not applicable for every factor", async () => {
    const { el } = await mount();
    expect(el.querySelectorAll("input[type=radio]")).toHaveLength(11 * 3);
    expect(el.textContent).toContain("Not applicable");
  });

  it("asks only for equipment placement when there is no venue yet", async () => {
    const { el } = await mount({ venues: [] });
    expect(legends(el)).toEqual(["Equipment placement"]);
  });

  it("records a rating under its venue without disturbing the other marks", async () => {
    const existing = { [markKey("layout", "b2")]: { rating: "concern", note: "Narrow aisle" } };
    const { el, model } = await mount({ marks: existing });
    radio(el, "Layout", "satisfactory", 0).click();
    await nextTick();
    expect(model.value[markKey("layout", "b1")]).toEqual({ rating: "satisfactory", note: "" });
    expect(model.value[markKey("layout", "b2")]).toEqual({ rating: "concern", note: "Narrow aisle" });
  });

  it("records equipment placement against the event, not a venue", async () => {
    const { el, model } = await mount();
    radio(el, "Equipment placement", "not_applicable").click();
    await nextTick();
    expect(model.value[markKey("equipment_placement", null)].rating).toBe("not_applicable");
  });

  it("changes a rating and keeps its note", async () => {
    const { el, model } = await mount({ marks: { [markKey("layout", "b1")]: { rating: "satisfactory", note: "Checked" } } });
    radio(el, "Layout", "concern", 0).click();
    await nextTick();
    expect(model.value[markKey("layout", "b1")]).toEqual({ rating: "concern", note: "Checked" });
  });

  it("keeps every mark when several are made before the page re-renders", async () => {
    const { el, model } = await mount();
    radio(el, "Layout", "concern", 0).click();
    radio(el, "Layout", "satisfactory", 1).click();
    radio(el, "Equipment placement", "satisfactory").click();
    await nextTick();
    expect(Object.fromEntries(Object.entries(model.value).map(([key, mark]) => [key, mark.rating]))).toEqual({
      [markKey("layout", "b1")]: "concern",
      [markKey("layout", "b2")]: "satisfactory",
      [markKey("equipment_placement", null)]: "satisfactory",
    });
  });

  it("keeps a note typed before the rating is chosen", async () => {
    const { el, model } = await mount();
    const note = el.querySelector('input[aria-label="Layout note for Town Hall"]');
    note.value = "Chairs near the door";
    note.dispatchEvent(new Event("input"));
    await nextTick();
    expect(model.value[markKey("layout", "b1")]).toEqual({ rating: null, note: "Chairs near the door" });
  });

  it("shows the recorded ratings and notes", async () => {
    const { el } = await mount({ marks: { [markKey("accessibility", "b2")]: { rating: "concern", note: "Ramp is steep" } } });
    expect(radio(el, "Accessibility", "concern", 1).checked).toBe(true);
    expect(el.querySelector('input[aria-label="Accessibility note for Atrium"]').value).toBe("Ramp is steep");
    expect(radio(el, "Accessibility", "concern", 0).checked).toBe(false);
  });

  it("limits a note to 1000 characters, marks it optional and labels it for its venue", async () => {
    const { el } = await mount();
    const note = el.querySelector('input[aria-label="Equipment placement note for Whole event"]');
    expect(note.maxLength).toBe(1000);
    expect(el.textContent).toContain("Note (optional)");
  });

  it("cannot be changed while a decision is being sent", async () => {
    const { el, model } = await mount({ disabled: true });
    expect([...el.querySelectorAll("fieldset")].every((f) => f.disabled)).toBe(true);
    expect([...el.querySelectorAll("input[type=text]")].every((input) => input.disabled)).toBe(true);
    radio(el, "Layout", "concern", 0).click();
    await nextTick();
    expect(model.value).toEqual({});
  });
});
