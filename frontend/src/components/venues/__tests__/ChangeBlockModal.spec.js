import { createApp, h, nextTick, reactive } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import ChangeBlockModal from "@/components/venues/ChangeBlockModal.vue";

const mounted = [];
// 1 May 2031, 10:00 Singapore time.
const NOW = new Date("2031-05-01T02:00:00Z");
// 20 May 2031, 09:00–17:00 Singapore time: hasn't started.
const UPCOMING = {
  id: "blk-1", status: "active", reason: "maintenance", notes: "Aircon",
  period: { starts_at: "2031-05-20T01:00:00Z", ends_at: "2031-05-20T09:00:00Z" },
  created_by: { id: "a3", full_name: "Vera Staff" }, created_at: "2031-04-30T02:30:00Z",
};
// Started an hour ago, ends tomorrow at 10:00.
const CURRENT = { ...UPCOMING, id: "blk-2", period: { starts_at: "2031-05-01T01:00:00Z", ends_at: "2031-05-02T02:00:00Z" } };
const BOOKING = {
  booking_id: "d-1", event_id: "e0000000-0000-4000-8000-000000000541", event_name: "Partner Summit",
  status: "approved", period: { starts_at: "2031-05-20T06:00:00Z", ends_at: "2031-05-20T08:00:00Z" },
  block_reason: "Maintenance", has_pending_replacement: false,
};

async function mountModal(initial = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const props = reactive({ open: true, venueName: "Hall A", block: UPCOMING, result: null, busy: false, error: null,
    now: NOW, ...initial });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { render: () => null } },
      { path: "/bookings/:id", name: "booking-request", component: { render: () => null } },
    ],
  });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(ChangeBlockModal, { ...props, onConfirm, onCancel }) }).use(router);
  app.mount(el);
  mounted.push(app);
  await router.isReady();
  await nextTick();
  return { onConfirm, onCancel, props };
}

async function fill(selector, value, event = "input") {
  const field = document.querySelector(selector);
  field.value = value;
  field.dispatchEvent(new Event(event));
  await nextTick();
}

async function choose(action) {
  const radio = document.querySelector(`input[type="radio"][value="${action}"]`);
  radio.checked = true;
  radio.dispatchEvent(new Event("change"));
  await nextTick();
}

const button = (label) => document.querySelector(`button[aria-label="${label}"]`);
const actions = () => [...document.querySelectorAll('input[type="radio"]')].map((r) => r.value);
const said = () => document.body.textContent.replace(/\s+/g, " ");

describe("ChangeBlockModal (SCRUM-54)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("shows the block it changes, with who set it and when (AC1)", async () => {
    await mountModal();
    expect(said()).toContain("20 May 2031, 09:00 – 20 May 2031, 17:00");
    expect(said()).toContain("Maintenance · Aircon");
    expect(said()).toContain("Set by Vera Staff · 30 Apr 2031, 10:30");
  });

  it("offers shorten or remove for a block that hasn't started, with shorten chosen (AC2)", async () => {
    await mountModal();
    expect(actions()).toEqual(["shorten", "remove"]);
    expect(document.querySelector('input[value="shorten"]').checked).toBe(true);
    expect(document.querySelector('input[aria-label="New end"]')).not.toBeNull();
  });

  it("offers end now or shorten for a block in progress, with end now chosen (AC2)", async () => {
    await mountModal({ block: CURRENT });
    expect(actions()).toEqual(["end_now", "shorten"]);
    expect(document.querySelector('input[value="end_now"]').checked).toBe(true);
    expect(document.querySelector('input[aria-label="New end"]')).toBeNull();
  });

  it("says flagged bookings stay Affected until restored (AC5)", async () => {
    await mountModal();
    expect(said()).toContain("Bookings this block marked Affected stay Affected until venue staff restore them.");
  });

  it("names a problem with the new end and sends nothing", async () => {
    const { onConfirm } = await mountModal();
    await fill('input[aria-label="New end"]', "2031-05-20T18:00");
    button("Save change").click();
    await nextTick();
    expect(said()).toContain("The new end must be earlier than the current end. To block for longer, add a new block.");
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("sends a shortened end as Singapore time, with the note", async () => {
    const { onConfirm } = await mountModal();
    await fill('input[aria-label="New end"]', "2031-05-20T12:00");
    await fill("#block-change-note", "  Fixed early ");
    button("Save change").click();
    await nextTick();
    expect(onConfirm).toHaveBeenCalledWith({ action: "shorten", ends_at: "2031-05-20T12:00:00+08:00", note: "Fixed early" });
  });

  it("sends a removal", async () => {
    const { onConfirm } = await mountModal();
    await choose("remove");
    expect(document.querySelector('input[aria-label="New end"]')).toBeNull();
    button("Save change").click();
    await nextTick();
    expect(onConfirm).toHaveBeenCalledWith({ action: "remove", ends_at: null, note: null });
  });

  it("counts the note against its 1000-character limit", async () => {
    await mountModal({ block: CURRENT });
    await fill("#block-change-note", "abc");
    expect(said()).toContain("3 / 1000");
    expect(document.querySelector("#block-change-note").getAttribute("maxlength")).toBe("1000");
  });

  it("does not send while busy", async () => {
    const { onConfirm } = await mountModal({ block: CURRENT, busy: true });
    button("Save change").click();
    await nextTick();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("shows the API's error", async () => {
    await mountModal({ error: "This block has already ended, so it can't be changed." });
    expect(document.querySelector('[role="alert"]').textContent).toContain("already ended");
  });

  it("cancels", async () => {
    const { onCancel } = await mountModal();
    button("Cancel").click();
    expect(onCancel).toHaveBeenCalled();
  });

  it("after ending early, lists the bookings that can be restored, linked to each (AC5, AC6)", async () => {
    const block = { ...CURRENT, status: "ended_early", period: { starts_at: CURRENT.period.starts_at, ends_at: NOW.toISOString() } };
    await mountModal({ block: CURRENT, result: { block, restorable: [BOOKING] } });
    expect(document.querySelector("#change-block-title").textContent).toContain("Block ended early");
    expect(said()).toContain("1 booking can be restored");
    const link = document.querySelector('[data-testid="block-restorable"] a');
    expect(link.getAttribute("href")).toBe("/bookings/d-1");
    expect(link.textContent).toContain("Partner Summit");
    expect(said()).not.toContain("Replacement requested");
  });

  it("marks a booking whose coordinator already asked for a replacement (AC7)", async () => {
    await mountModal({ result: { block: { ...UPCOMING, status: "removed" },
      restorable: [{ ...BOOKING, has_pending_replacement: true }] } });
    expect(document.querySelector("#change-block-title").textContent).toContain("Block removed");
    expect(said()).toContain("Replacement requested: restoring this booking cancels it.");
  });

  it("says when no booking is waiting to be restored", async () => {
    await mountModal({ result: { block: { ...UPCOMING, status: "removed" }, restorable: [] } });
    expect(said()).toContain("No bookings are waiting to be restored.");
    button("Done").click();
  });

  it("resets the form each time it opens", async () => {
    const { props } = await mountModal();
    await fill('input[aria-label="New end"]', "2031-05-20T12:00");
    props.open = false;
    await nextTick();
    props.open = true;
    await nextTick();
    expect(document.querySelector('input[aria-label="New end"]').value).toBe("");
  });
});
