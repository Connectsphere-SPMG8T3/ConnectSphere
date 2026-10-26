import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import EquipmentLineEditForm from "@/components/equipment/EquipmentLineEditForm.vue";

const PROJECTOR = { equipment_id: "p1", name: "Projector", equipment_type: "AV", total_quantity: 20 };
const MIC = { equipment_id: "m1", name: "Wireless microphone", equipment_type: "Audio", total_quantity: 8 };
const LINE = {
  id: "l1", equipment_id: "p1", equipment_name: "Projector", quantity: 4,
  technical_requirements: "HDMI", status: "pending",
};
const apps = [];

function mountForm(line = LINE, props = {}) {
  const events = [];
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(EquipmentLineEditForm, {
      line, catalogue: [PROJECTOR, MIC], busy: false, ...props,
      onSave: (draft) => events.push(["save", draft]),
      onCancel: () => events.push(["cancel"]),
    }),
  });
  app.mount(el);
  apps.push(app);
  return events;
}

async function setValue(element, value, eventName = "input") {
  element.value = value;
  element.dispatchEvent(new Event(eventName));
  await nextTick();
}

const button = (text) => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === text);
const quantity = () => document.querySelector('input[type="number"]');

afterEach(() => {
  apps.splice(0).forEach((app) => app.unmount());
  document.body.innerHTML = "";
});

describe("EquipmentLineEditForm (SCRUM-44)", () => {
  it("starts from the line as recorded (AC2)", () => {
    mountForm();

    expect(document.querySelector("select").value).toBe("p1");
    expect(quantity().value).toBe("4");
    expect(document.querySelector("textarea").value).toBe("HDMI");
  });

  it("saves the new item, quantity and requirements (AC2)", async () => {
    const events = mountForm();

    await setValue(document.querySelector("select"), "m1", "change");
    await setValue(quantity(), "2");
    await setValue(document.querySelector("textarea"), "Lapel mics");
    button("Save changes").click();

    expect(events).toEqual([["save", { equipmentId: "m1", quantity: "2", technicalRequirements: "Lapel mics" }]]);
  });

  it.each(["0", "1.5", ""])("won't save a quantity of %j (AC2)", async (value) => {
    const events = mountForm();

    await setValue(quantity(), value);

    expect(button("Save changes").disabled).toBe(true);
    button("Save changes").click();
    expect(events).toEqual([]);
  });

  it("warns above the catalogue total but still saves (AC2, 45 AC2)", async () => {
    mountForm();

    await setValue(quantity(), "25");

    expect(document.body.textContent).toContain("Only 20 exist in the catalogue. You can still submit.");
    expect(button("Save changes").disabled).toBe(false);
  });

  it("counts technical requirements against the 1000-character limit", async () => {
    mountForm();

    await setValue(document.querySelector("textarea"), "x".repeat(1001));

    expect(document.body.textContent).toContain("Keep it to 1000 characters.");
    expect(button("Save changes").disabled).toBe(true);
  });

  it("says before saving that a reserved line goes back to Technical Support (AC3)", () => {
    mountForm({ ...LINE, status: "reserved" });

    expect(document.body.textContent).toContain("Technical Support will re-check this line. Its reservation is kept until they re-approve or reject it.");
  });

  it("cancels without saving", () => {
    const events = mountForm();

    button("Cancel").click();

    expect(events).toEqual([["cancel"]]);
  });

  it("can't be saved twice while saving", () => {
    mountForm(LINE, { busy: true });

    expect(button("Saving…").disabled).toBe(true);
  });
});
