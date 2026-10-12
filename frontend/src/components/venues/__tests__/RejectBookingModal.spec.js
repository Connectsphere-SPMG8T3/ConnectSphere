import { createApp, h, nextTick, ref } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import RejectBookingModal from "@/components/venues/RejectBookingModal.vue";

const mounted = [];

async function mountModal(props = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(RejectBookingModal, {
      open: true, venueName: "Innovation Lab", eventName: "Partner Summit", onConfirm, onCancel, ...props,
    }),
  });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return { onConfirm, onCancel };
}

function type(id, text) {
  const field = document.getElementById(id);
  field.value = text;
  field.dispatchEvent(new Event("input"));
  return nextTick();
}

const confirmButton = () => document.querySelector('button[aria-label="Reject booking request"]');

describe("RejectBookingModal (SCRUM-38)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("names the venue and event, and says who will see the reason (AC6)", async () => {
    await mountModal();

    expect(document.body.textContent).toContain("Innovation Lab");
    expect(document.body.textContent).toContain("Partner Summit");
    expect(document.body.textContent).toContain("The event's coordinator will see your reason");
    expect(document.getElementById("reject-booking-reason").getAttribute("maxlength")).toBe("1000");
    expect(document.getElementById("reject-booking-suggestion").getAttribute("maxlength")).toBe("1000");
  });

  it("cannot be confirmed without a reason, or with only spaces (AC2)", async () => {
    const { onConfirm } = await mountModal();
    expect(confirmButton().disabled).toBe(true);

    await type("reject-booking-reason", "   \n ");
    confirmButton().click();

    expect(confirmButton().disabled).toBe(true);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("emits the trimmed reason and suggestion", async () => {
    const { onConfirm } = await mountModal();
    await type("reject-booking-reason", "  Capacity exceeded  ");
    await type("reject-booking-suggestion", "  Try Heritage Hall ");

    confirmButton().click();

    expect(onConfirm).toHaveBeenCalledWith({ reason: "Capacity exceeded", suggestion: "Try Heritage Hall" });
  });

  it("sends no suggestion when it was left empty (AC3)", async () => {
    const { onConfirm } = await mountModal();
    await type("reject-booking-reason", "Closed for maintenance");

    confirmButton().click();

    expect(onConfirm).toHaveBeenCalledWith({ reason: "Closed for maintenance", suggestion: null });
  });

  it("counts what has been typed in each box", async () => {
    await mountModal();
    await type("reject-booking-reason", "Closed");
    await type("reject-booking-suggestion", "Hall B, 2pm");

    expect(document.body.textContent).toContain("6 / 1000");
    expect(document.body.textContent).toContain("11 / 1000");
  });

  it("stays disabled while the rejection is being sent", async () => {
    const { onConfirm } = await mountModal({ busy: true });
    await type("reject-booking-reason", "Closed");

    confirmButton().click();

    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("shows the API's error", async () => {
    await mountModal({ error: "Must be 1 to 1000 characters." });

    expect(document.querySelector('[role="alert"]').textContent).toContain("Must be 1 to 1000 characters.");
  });

  it("cancels from the button and from the backdrop", async () => {
    const { onCancel } = await mountModal();

    document.querySelector('button[aria-label="Cancel"]').click();
    document.querySelector('[role="presentation"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));

    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it("clears what was typed when it opens again", async () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    const isOpen = ref(true);
    const app = createApp({
      render: () => h(RejectBookingModal, { open: isOpen.value, venueName: "Lab", eventName: "Summit" }),
    });
    app.mount(el);
    mounted.push(app);
    await nextTick();
    await type("reject-booking-reason", "Closed");

    isOpen.value = false;
    await nextTick();
    isOpen.value = true;
    await nextTick();

    expect(document.getElementById("reject-booking-reason").value).toBe("");
  });
});
