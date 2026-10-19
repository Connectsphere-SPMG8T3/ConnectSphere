import { createApp, h, nextTick, reactive } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import BlockVenueModal from "@/components/venues/BlockVenueModal.vue";

const mounted = [];

async function mountModal(initial = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const props = reactive({ open: true, venueName: "Hall A", affected: [], result: null, busy: false, error: null,
    ...initial });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(BlockVenueModal, { ...props, onConfirm, onCancel }) });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return { onConfirm, onCancel, props };
}

async function fill(selector, value, event = "input") {
  const field = document.querySelector(selector);
  field.value = value;
  field.dispatchEvent(new Event(event));
  await nextTick();
}

async function fillValid() {
  await fill('input[aria-label="Block start"]', "2031-05-20T09:00");
  await fill('input[aria-label="Block end"]', "2031-05-20T17:00");
  await fill("select", "maintenance", "change");
}

const button = (label) => document.querySelector(`button[aria-label="${label}"]`);
const text = () => document.body.textContent;

const BOOKING = {
  booking_id: "d-1",
  event_id: "e0000000-0000-4000-8000-000000000511",
  event_name: "Partner Summit",
  status: "approved",
  period: { starts_at: "2031-05-20T02:00:00Z", ends_at: "2031-05-20T05:00:00Z" },
  block_reason: "Maintenance",
};

describe("BlockVenueModal (SCRUM-51)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("offers the six reason categories", async () => {
    await mountModal();
    const options = [...document.querySelectorAll("select option")].map((o) => o.value).filter(Boolean);
    expect(options).toEqual(["maintenance", "equipment_failure", "renovation", "safety", "internal_activity", "other"]);
  });

  it("submits a valid block as a preview first, in Singapore time", async () => {
    const { onConfirm } = await mountModal();
    await fillValid();
    button("Block venue").click();
    expect(onConfirm).toHaveBeenCalledWith({
      starts_at: "2031-05-20T09:00:00+08:00", ends_at: "2031-05-20T17:00:00+08:00",
      reason: "maintenance", detail: null, confirm: false,
    });
  });

  it("names every problem and sends nothing while the form is incomplete", async () => {
    const { onConfirm } = await mountModal();
    button("Block venue").click();
    await nextTick();
    expect(onConfirm).not.toHaveBeenCalled();
    expect(text()).toContain("Choose a start date and time.");
    expect(text()).toContain("Choose an end date and time.");
    expect(text()).toContain("Choose a reason.");
  });

  it("refuses an end before the start", async () => {
    const { onConfirm } = await mountModal();
    await fillValid();
    await fill('input[aria-label="Block end"]', "2031-05-20T08:00");
    button("Block venue").click();
    await nextTick();
    expect(onConfirm).not.toHaveBeenCalled();
    expect(text()).toContain("End must be after start.");
  });

  it("marks the detail required for Other and refuses it blank", async () => {
    const { onConfirm } = await mountModal();
    await fillValid();
    await fill("select", "other", "change");
    expect(text()).toContain("Detail (required)");
    button("Block venue").click();
    await nextTick();
    expect(onConfirm).not.toHaveBeenCalled();
    expect(text()).toContain("A detail is required when the reason is Other.");
    await fill("#block-detail", "Film shoot");
    button("Block venue").click();
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ reason: "other", detail: "Film shoot" }));
  });

  it("counts the detail against its 1000-character limit", async () => {
    await mountModal();
    await fill("#block-detail", "Aircon");
    expect(text()).toContain("6 / 1000");
    expect(document.querySelector("#block-detail").getAttribute("maxlength")).toBe("1000");
  });

  it("lists the bookings the block would affect and confirms with Block anyway", async () => {
    const { onConfirm, props } = await mountModal();
    await fillValid();
    props.affected = [BOOKING];
    await nextTick();
    expect(text()).toContain("Partner Summit");
    expect(text()).toContain("flagged Affected");
    expect(button("Block venue")).toBeNull();
    button("Block anyway").click();
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ confirm: true }));
  });

  it("after saving, shows each affected booking with its event, status and the block reason (AC6)", async () => {
    const { onCancel } = await mountModal({ result: { block: { id: "blk-1" }, affected: [BOOKING] } });
    expect(text()).toContain("Venue blocked");
    expect(text()).toContain("Partner Summit");
    expect(text()).toContain("Confirmed");
    expect(text()).toContain("Maintenance");
    expect(document.querySelector('input[aria-label="Block start"]')).toBeNull();
    button("Done").click();
    expect(onCancel).toHaveBeenCalled();
  });

  it("says so when the saved block affected no bookings", async () => {
    await mountModal({ result: { block: { id: "blk-1" }, affected: [] } });
    expect(text()).toContain("No bookings were affected.");
  });

  it("shows the API's error and disables saving while busy", async () => {
    await mountModal({ error: "Venue not found.", busy: true });
    await fillValid();
    expect(document.querySelector('[role="alert"]').textContent).toContain("Venue not found.");
    expect(button("Block venue").disabled).toBe(true);
  });

  it("clears the form each time it opens", async () => {
    const { props } = await mountModal();
    await fill("#block-detail", "Aircon");
    props.open = false;
    await nextTick();
    props.open = true;
    await nextTick();
    expect(document.querySelector("#block-detail").value).toBe("");
  });

  it("cancels from the Cancel button", async () => {
    const { onCancel } = await mountModal();
    button("Cancel").click();
    expect(onCancel).toHaveBeenCalled();
  });
});
