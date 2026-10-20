import { createApp, h, nextTick, reactive } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import EquipmentLineArrangement from "@/components/equipment/EquipmentLineArrangement.vue";

const LINE = {
  id: "l1", equipment_name: "4K Projector", quantity: 3, technical_requirements: "HDMI",
  status: "pending", technical_notes: null, not_available_reason: null,
};
const apps = [];

function mountLine(overrides = {}, props = {}) {
  const state = reactive({ line: { ...LINE, ...overrides }, ...props });
  const events = [];
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(EquipmentLineArrangement, {
      ...state,
      onReserve: () => events.push(["reserve"]),
      "onNot-available": (reason) => events.push(["not-available", reason]),
      "onSave-note": (note) => events.push(["save-note", note]),
    }),
  });
  app.mount(el);
  apps.push(app);
  return { state, events };
}

const button = (text) => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === text);

async function type(element, value) {
  element.value = value;
  element.dispatchEvent(new Event("input"));
  await nextTick();
}

afterEach(() => {
  apps.splice(0).forEach((app) => app.unmount());
  document.body.innerHTML = "";
});

describe("EquipmentLineArrangement (SCRUM-24)", () => {
  it("a pending line offers Reserve and Mark not available (AC1, AC3)", async () => {
    const { events } = mountLine();

    expect(document.body.textContent).toContain("4K Projector");
    expect(document.body.textContent).toContain("Pending");
    button("Reserve").click();

    expect(events).toEqual([["reserve"]]);
  });

  it("a flagged line explains itself and offers Reserve again (AC7, D8)", () => {
    mountLine({ status: "re_review" });

    expect(document.body.textContent).toContain("no longer fits");
    expect(button("Reserve again")).toBeTruthy();
  });

  it("a reserved line can only be marked not available", () => {
    mountLine({ status: "reserved" });

    expect(button("Reserve")).toBeUndefined();
    expect(button("Mark not available")).toBeTruthy();
  });

  it("a Not available line shows its reason and offers no action", () => {
    mountLine({ status: "rejected", not_available_reason: "Only 2 in stock" });

    expect(document.body.textContent).toContain("Not available: Only 2 in stock");
    expect(button("Reserve")).toBeUndefined();
    expect(button("Mark not available")).toBeUndefined();
  });

  it("marking not available needs a reason, then sends it (AC3, AC9)", async () => {
    const { events } = mountLine();
    button("Mark not available").click();
    await nextTick();

    button("Confirm not available").click();
    await nextTick();
    expect(document.body.textContent).toContain("Give a reason the line is not available.");
    expect(document.querySelector("#line-l1-reason").getAttribute("aria-invalid")).toBe("true");
    expect(events).toEqual([]);

    await type(document.querySelector("#line-l1-reason"), "Only 2 in stock");
    button("Confirm not available").click();
    await nextTick();
    expect(events).toEqual([["not-available", "Only 2 in stock"]]);
  });

  it("cancelling the reason puts the button back", async () => {
    mountLine();
    button("Mark not available").click();
    await nextTick();

    button("Cancel").click();
    await nextTick();

    expect(document.querySelector("#line-l1-reason")).toBeNull();
    expect(button("Mark not available")).toBeTruthy();
  });

  it("the reason form closes when the line's status changes", async () => {
    const { state } = mountLine();
    button("Mark not available").click();
    await nextTick();

    state.line = { ...state.line, status: "reserved" };
    await nextTick();

    expect(document.querySelector("#line-l1-reason")).toBeNull();
  });

  it("notes save only once changed, and follow the saved value (AC9)", async () => {
    const { state, events } = mountLine({ technical_notes: "From store B" });
    const notes = document.querySelector("#line-l1-notes");
    expect(notes.value).toBe("From store B");
    expect(button("Save notes").disabled).toBe(true);

    await type(notes, "From store C");
    button("Save notes").click();
    await nextTick();
    expect(events).toEqual([["save-note", "From store C"]]);

    state.line = { ...state.line, technical_notes: "From store C" };
    await nextTick();
    expect(document.querySelector("#line-l1-notes").value).toBe("From store C");
    expect(button("Save notes").disabled).toBe(true);
  });

  it("notes over the limit are flagged and not sent", async () => {
    const { events } = mountLine();
    const notes = document.querySelector("#line-l1-notes");

    await type(notes, "x".repeat(2001));
    document.querySelector("#line-l1-notes").closest("form").dispatchEvent(new Event("submit"));
    await nextTick();

    expect(document.body.textContent).toContain("Keep the notes to 2000 characters.");
    expect(events).toEqual([]);
  });

  it("an error stays beside the line (AC3)", () => {
    mountLine({}, { error: "Not enough available: 1 free for this event's time. The line stays Pending." });

    expect(document.querySelector('[role="alert"]').textContent).toContain("1 free");
  });

  it("while busy or locked nothing can be pressed", () => {
    mountLine({}, { busy: true });
    expect(button("Working…").disabled).toBe(true);
    expect(document.querySelector("#line-l1-notes").disabled).toBe(true);
  });

  it("on a closed event the notes are read-only and no action is offered", () => {
    mountLine({ status: "released", technical_notes: "Returned to store" }, { open: false });

    expect(document.querySelector("textarea")).toBeNull();
    expect(document.querySelectorAll("button")).toHaveLength(0);
    expect(document.body.textContent).toContain("Technical notes: Returned to store");
  });
});
