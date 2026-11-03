import { createApp, h, nextTick, ref } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import EditEventDetailsModal from "@/components/events/EditEventDetailsModal.vue";

const EVENT = {
  id: "e1", version: 4, name: "Partner Summit", purpose: "Quarterly meeting",
  description: null, accessibility_needs: "Step-free access",
};
const mounted = [];

async function mountModal(props = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const onReload = vi.fn();
  const open = ref(props.open ?? true);
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(EditEventDetailsModal, { event: EVENT, busy: false, error: null, ...props, open: open.value, onConfirm, onCancel, onReload }),
  });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return { onConfirm, onCancel, onReload, open };
}

const field = (label) => [...document.querySelectorAll("input, textarea")]
  .find((control) => document.querySelector(`label[for="${control.id}"]`)?.textContent.includes(label));
async function type(label, text) {
  const control = field(label);
  control.value = text;
  control.dispatchEvent(new Event("input"));
  await nextTick();
}
const save = () => document.querySelector('button[aria-label="Save details"]');

describe("EditEventDetailsModal (story 112)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("shows the four ordinary fields filled from the event, and nothing else", async () => {
    await mountModal();

    expect(field("Event title").value).toBe("Partner Summit");
    expect(field("Purpose").value).toBe("Quarterly meeting");
    expect(field("Description").value).toBe("");
    expect(field("Accessibility").value).toBe("Step-free access");
    expect(document.querySelectorAll("input, textarea")).toHaveLength(4);
  });

  it("says where date, attendance, venue and equipment changes go", async () => {
    await mountModal();

    expect(document.body.textContent).toContain("change request");
  });

  it("cannot be saved until something changes", async () => {
    await mountModal();

    expect(save().disabled).toBe(true);
    await type("Event title", "  Partner Summit  ");
    expect(save().disabled).toBe(true);
  });

  it("emits only the changed fields, trimmed", async () => {
    const { onConfirm } = await mountModal();
    await type("Description", "  Agreed offline  ");

    save().click();

    expect(onConfirm).toHaveBeenCalledWith({ description: "Agreed offline" });
  });

  it("shows every field error together and does not emit (AC3)", async () => {
    const { onConfirm } = await mountModal();
    await type("Event title", "ab");
    await type("Purpose", "");

    expect(save().disabled).toBe(true);
    save().click();

    expect(onConfirm).not.toHaveBeenCalled();
    const text = document.body.textContent;
    expect(text).toContain("Use at least 3 characters.");
    expect(text).toContain("Enter the event purpose.");
  });

  it("checks only the fields being changed, as the API does", async () => {
    const { onConfirm } = await mountModal({ event: { ...EVENT, purpose: null } });
    await type("Description", "Agreed offline");

    expect(document.body.textContent).not.toContain("Enter the event purpose.");
    save().click();

    expect(onConfirm).toHaveBeenCalledWith({ description: "Agreed offline" });
  });

  it("starts again from the event each time it opens", async () => {
    const { open } = await mountModal();
    await type("Event title", "Something else");

    open.value = false;
    await nextTick();
    open.value = true;
    await nextTick();

    expect(field("Event title").value).toBe("Partner Summit");
  });

  it("is disabled while the request is in flight", async () => {
    await mountModal({ busy: true });
    await type("Description", "x");

    expect(save().disabled).toBe(true);
  });

  it("shows the API's refusal", async () => {
    await mountModal({ error: "Significant changes go through a change request." });

    expect(document.querySelector('[role="alert"]').textContent).toContain("Significant changes go through a change request.");
  });

  it("offers a reload when the save was refused as a conflict (AC4)", async () => {
    const { onReload } = await mountModal({ error: "This event was updated by someone else. Reload.", conflict: true });

    document.querySelector('button[aria-label="Reload event"]').click();

    expect(onReload).toHaveBeenCalled();
  });

  it("decides on the conflict, not on the wording of the message", async () => {
    await mountModal({ error: "Some other wording.", conflict: true });

    expect(document.querySelector('button[aria-label="Reload event"]')).not.toBeNull();
  });

  it("offers no reload for an error that isn't a conflict, even with the stale wording", async () => {
    await mountModal({ error: "This event was updated by someone else. Reload.", conflict: false });

    expect(document.querySelector('button[aria-label="Reload event"]')).toBeNull();
  });

  it("offers no reload when there is no error to reload from", async () => {
    await mountModal({ error: null, conflict: true });

    expect(document.querySelector('button[aria-label="Reload event"]')).toBeNull();
  });

  it("renders nothing while closed", async () => {
    await mountModal({ open: false });

    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });

  it("keeps its top reachable when taller than a phone screen", async () => {
    await mountModal();

    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog.parentElement.className).toContain("items-start");
    expect(dialog.className).toContain("my-auto");
  });

  it("emits cancel", async () => {
    const { onCancel } = await mountModal();

    document.querySelector('button[aria-label="Cancel"]').click();

    expect(onCancel).toHaveBeenCalled();
  });
});
