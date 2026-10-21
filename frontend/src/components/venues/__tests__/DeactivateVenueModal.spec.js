import { createApp, h, nextTick, reactive } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import DeactivateVenueModal from "@/components/venues/DeactivateVenueModal.vue";

const mounted = [];

async function mountModal(props = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(DeactivateVenueModal, { open: true, venueName: "Hall A", onConfirm, onCancel, ...props }),
  });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return { onConfirm, onCancel };
}

async function choose(value) {
  const select = document.querySelector("select");
  select.value = value;
  select.dispatchEvent(new Event("change"));
  await nextTick();
}

async function typeNote(text) {
  const textarea = document.querySelector("textarea");
  textarea.value = text;
  textarea.dispatchEvent(new Event("input"));
  await nextTick();
}

const button = (label) => document.querySelector(`button[aria-label="${label}"]`);

const AFFECTED = [
  {
    booking_id: "d-1",
    event_id: "e0000000-0000-4000-8000-000000000301",
    event_name: "Partner Summit",
    period: { starts_at: "2031-05-20T14:00:00+08:00", ends_at: "2031-05-20T17:00:00+08:00" },
    status: "held",
  },
];

describe("DeactivateVenueModal (SCRUM-64)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("submits the chosen reason as a preview first", async () => {
    const { onConfirm } = await mountModal();
    await choose("permanently_closed");
    button("Deactivate venue").click();
    expect(onConfirm).toHaveBeenCalledWith({ reason: "permanently_closed", note: "", confirm: false });
  });

  it("requires a note when the reason is Other", async () => {
    await mountModal();
    await choose("other");
    expect(button("Deactivate venue").disabled).toBe(true);
    await typeNote("   ");
    expect(button("Deactivate venue").disabled).toBe(true);
    await typeNote("Lease ended");
    expect(button("Deactivate venue").disabled).toBe(false);
  });

  it("needs a reason before it can be submitted", async () => {
    await mountModal();
    expect(button("Deactivate venue").disabled).toBe(true);
  });

  it("lists the bookings that would be flagged instead of the first-step button", async () => {
    await mountModal({ affected: AFFECTED });
    expect(document.body.textContent).toContain("Partner Summit");
    expect(document.body.textContent).toContain("These bookings will be flagged Affected and their coordinators notified.");
    expect(document.body.textContent).toContain("20 May 2031");
    expect(document.body.textContent).toContain("Tentative");
    expect(button("Deactivate venue")).toBeNull();
  });

  it("lists a booking still flagged from an earlier deactivation and says it keeps that flag", async () => {
    await mountModal({
      affected: [
        { ...AFFECTED[0], flag: "affected" },
        { ...AFFECTED[0], booking_id: "d-2", event_name: "Board Retreat", flag: "safety_rejected" },
        { ...AFFECTED[0], booking_id: "d-3", event_name: "Town Hall", flag: null },
      ],
    });
    const text = document.body.textContent;
    expect(text).toContain("These bookings are affected. Any not already flagged will be flagged Affected and their coordinators notified.");
    expect(text).toContain("Already flagged: Affected");
    expect(text).toContain("Already flagged: Safety rejected");
    const rows = [...document.querySelectorAll("li")].map((li) => li.textContent);
    expect(rows[2]).not.toContain("Already flagged");
    expect(button("Deactivate anyway")).not.toBeNull();
  });

  it("shows an unrecognised flag as it is rather than hiding it", async () => {
    await mountModal({ affected: [{ ...AFFECTED[0], flag: "under_review" }] });
    expect(document.body.textContent).toContain("Already flagged: under_review");
  });

  it("refers to a booking whose event has no name by its short id", async () => {
    await mountModal({ affected: [{ ...AFFECTED[0], event_name: null }] });
    expect(document.body.textContent).toContain("Event E0000000");
  });

  it("keeps the reason and note across the preview and confirms on Deactivate anyway", async () => {
    const onConfirm = vi.fn();
    const state = reactive({ affected: [] });
    const el = document.createElement("div");
    document.body.appendChild(el);
    const app = createApp({
      render: () => h(DeactivateVenueModal, { open: true, venueName: "Hall A", affected: state.affected, onConfirm }),
    });
    app.mount(el);
    mounted.push(app);
    await nextTick();
    await choose("long_term_renovation");
    await typeNote("Roof works");
    state.affected = AFFECTED;
    await nextTick();
    button("Deactivate anyway").click();
    expect(onConfirm).toHaveBeenLastCalledWith({ reason: "long_term_renovation", note: "Roof works", confirm: true });
  });

  it("disables both actions while busy", async () => {
    await mountModal({ busy: true, affected: AFFECTED });
    expect(button("Deactivate anyway").disabled).toBe(true);
  });

  it("shows an error from the API", async () => {
    await mountModal({ error: "This venue is already inactive." });
    expect(document.querySelector('[role="alert"]').textContent).toContain("This venue is already inactive.");
  });

  it("cancels", async () => {
    const { onCancel } = await mountModal();
    button("Cancel").click();
    expect(onCancel).toHaveBeenCalled();
  });
});
