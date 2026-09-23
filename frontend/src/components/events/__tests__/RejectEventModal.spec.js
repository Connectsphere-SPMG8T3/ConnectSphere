import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import RejectEventModal from "@/components/events/RejectEventModal.vue";

const mounted = [];

async function mountModal(props = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(RejectEventModal, { open: true, eventName: "Partner Summit", onConfirm, onCancel, ...props }),
  });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return { onConfirm, onCancel };
}

function typeReason(text) {
  const textarea = document.querySelector("textarea");
  textarea.value = text;
  textarea.dispatchEvent(new Event("input"));
  return nextTick();
}

const confirmButton = () => document.querySelector('button[aria-label="Reject request"]');

describe("RejectEventModal (SCRUM-52)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("names the event and asks for a reason", async () => {
    await mountModal();

    expect(document.body.textContent).toContain("Partner Summit");
    expect(document.querySelector("textarea").getAttribute("maxlength")).toBe("1000");
  });

  it("cannot be confirmed without a reason", async () => {
    await mountModal();

    expect(confirmButton().disabled).toBe(true);
  });

  it("cannot be confirmed with a whitespace-only reason", async () => {
    await mountModal();
    await typeReason("   \n  ");

    expect(confirmButton().disabled).toBe(true);
  });

  it("emits the trimmed reason on confirm", async () => {
    const { onConfirm } = await mountModal();
    await typeReason("  Venue unavailable on that date  ");

    confirmButton().click();

    expect(onConfirm).toHaveBeenCalledWith("Venue unavailable on that date");
  });

  it("shows how many characters are used", async () => {
    await mountModal();
    await typeReason("Venue unavailable");

    expect(document.body.textContent).toContain("17 / 1000");
  });

  it("is disabled while the request is in flight", async () => {
    await mountModal({ busy: true });
    await typeReason("Venue unavailable");

    expect(confirmButton().disabled).toBe(true);
  });

  it("shows the API's error", async () => {
    await mountModal({ error: "Cannot reject an event that is confirmed" });

    expect(document.querySelector('[role="alert"]').textContent).toContain("Cannot reject an event that is confirmed");
  });

  it("emits cancel", async () => {
    const { onCancel } = await mountModal();

    document.querySelector('button[aria-label="Cancel"]').click();

    expect(onCancel).toHaveBeenCalled();
  });
});
