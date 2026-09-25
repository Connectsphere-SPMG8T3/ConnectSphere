import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import ReturnEventModal from "@/components/events/ReturnEventModal.vue";

const mounted = [];

async function mountModal(props = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(ReturnEventModal, { open: true, eventName: "Partner Summit", onConfirm, onCancel, ...props }),
  });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return { onConfirm, onCancel };
}

function typeMessage(text) {
  const textarea = document.querySelector("textarea");
  textarea.value = text;
  textarea.dispatchEvent(new Event("input"));
  return nextTick();
}

function tick(label) {
  const box = [...document.querySelectorAll('input[type="checkbox"]')]
    .find((input) => input.closest("label").textContent.includes(label));
  box.checked = true;
  box.dispatchEvent(new Event("change"));
  return nextTick();
}

const confirmButton = () => document.querySelector('button[aria-label="Return request"]');

describe("ReturnEventModal (SCRUM-33)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("names the event, asks for a message and offers every flaggable field", async () => {
    await mountModal();

    expect(document.body.textContent).toContain("Partner Summit");
    expect(document.querySelector("textarea").getAttribute("maxlength")).toBe("1000");
    expect(document.querySelectorAll('input[type="checkbox"]')).toHaveLength(15);
  });

  it("cannot be confirmed without a message, even with fields flagged", async () => {
    await mountModal();
    await tick("Expected attendance");

    expect(confirmButton().disabled).toBe(true);
  });

  it("cannot be confirmed with a whitespace-only message", async () => {
    await mountModal();
    await typeMessage("   \n ");

    expect(confirmButton().disabled).toBe(true);
  });

  it("emits the trimmed message and the flagged fields", async () => {
    const { onConfirm } = await mountModal();
    await typeMessage("  Please confirm the attendance  ");
    await tick("Expected attendance");

    confirmButton().click();

    expect(onConfirm).toHaveBeenCalledWith({ message: "Please confirm the attendance", flaggedFields: ["expected_attendance"] });
  });

  it("shows how many characters are used", async () => {
    await mountModal();
    await typeMessage("Confirm");

    expect(document.body.textContent).toContain("7 / 1000");
  });

  it("is disabled while the request is in flight", async () => {
    await mountModal({ busy: true });
    await typeMessage("Confirm");

    expect(confirmButton().disabled).toBe(true);
  });

  it("shows the API's error", async () => {
    await mountModal({ error: "Cannot return an event that is planning" });

    expect(document.querySelector('[role="alert"]').textContent).toContain("Cannot return an event that is planning");
  });

  it("keeps its top reachable when taller than a phone screen", async () => {
    // A scrolling flex overlay that centres its child pushes an over-tall child
    // above the scroll origin, where it can't be scrolled to (found at 375x812).
    // jsdom has no layout, so pin the alignment that avoids it.
    await mountModal();

    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog.parentElement.className).toContain("items-start");
    expect(dialog.parentElement.className).not.toMatch(/(^|\s)items-center(\s|$)/);
    expect(dialog.className).toContain("my-auto");
  });

  it("emits cancel", async () => {
    const { onCancel } = await mountModal();

    document.querySelector('button[aria-label="Cancel"]').click();

    expect(onCancel).toHaveBeenCalled();
  });
});
