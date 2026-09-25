import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import ResubmitEventModal from "@/components/events/ResubmitEventModal.vue";

const mounted = [];

async function mountModal(props = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(ResubmitEventModal, { open: true, eventName: "Partner Summit", onConfirm, onCancel, ...props }),
  });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return { onConfirm, onCancel };
}

function typeNote(text) {
  const textarea = document.querySelector("textarea");
  textarea.value = text;
  textarea.dispatchEvent(new Event("input"));
  return nextTick();
}

const confirmButton = () => document.querySelector('button[aria-label="Resubmit request"]');

describe("ResubmitEventModal (SCRUM-33)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("names the event and asks what changed", async () => {
    await mountModal();

    expect(document.body.textContent).toContain("Partner Summit");
    expect(document.querySelector("textarea").getAttribute("maxlength")).toBe("1000");
  });

  it("cannot be confirmed without a note", async () => {
    await mountModal();
    await typeNote("   ");

    expect(confirmButton().disabled).toBe(true);
  });

  it("emits the trimmed note", async () => {
    const { onConfirm } = await mountModal();
    await typeNote("  Attendance is now 40  ");

    confirmButton().click();

    expect(onConfirm).toHaveBeenCalledWith("Attendance is now 40");
  });

  it("can't be sent twice while the first is in flight", async () => {
    await mountModal({ busy: true });
    await typeNote("Attendance is now 40");

    expect(confirmButton().disabled).toBe(true);
  });

  it("shows the API's error", async () => {
    await mountModal({ error: "This event was updated by someone else. Reload." });

    expect(document.querySelector('[role="alert"]').textContent).toContain("updated by someone else");
  });

  it("emits cancel", async () => {
    const { onCancel } = await mountModal();

    document.querySelector('button[aria-label="Cancel"]').click();

    expect(onCancel).toHaveBeenCalled();
  });
});
