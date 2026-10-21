import { createApp, nextTick } from "vue";
import { afterEach, expect, it } from "vitest";
import SafetyDecisionDetails from "@/components/events/SafetyDecisionDetails.vue";

const apps = [];
const BASE = {id: "d1", decided_at: "2031-01-01T02:00:00Z", decided_by_name: "Officer"};
async function mount(decision) {
  const el = document.createElement("div"); document.body.appendChild(el);
  const app = createApp(SafetyDecisionDetails, {decision}); apps.push(app); app.mount(el);
  await nextTick(); return el;
}
afterEach(() => { apps.splice(0).forEach(app => app.unmount()); document.body.innerHTML = ""; });

it("names the rejected venue and the coordinator's response", async () => {
  const el = await mount({...BASE, decision: "arrangement_rejected", comment: "Exits blocked",
    rejected_venues: [{venue_id: "v1", venue_name: "Heritage Hall"}],
    affected_bookings: [{booking_id: "b1", venue_name: "Heritage Hall"}],
    revision: {note: "Moved the barriers\nKept the aisle clear", by_name: "Marcus", at: "2031-01-02T02:00:00Z"}});
  for (const text of ["Rejected venue: Heritage Hall", "Coordinator's response:", "Moved the barriers", "Marcus"])
    expect(el.textContent).toContain(text);
  expect(el.textContent).not.toContain("Affected bookings: 1");
  expect(el.querySelector(".whitespace-pre-wrap")).not.toBeNull();
});
it("lists what a change request concerns, with fallbacks", async () => {
  const el = await mount({...BASE, decision: "changes_requested",
    affected_bookings: [{booking_id: "b1", venue_name: "Heritage Hall"}, {booking_id: "b2", venue_name: null}],
    affected_equipment: [{id: "q1", equipment_name: "Projector"}, {id: "q2", equipment_name: null}]});
  expect(el.textContent).toContain("Concerns: Heritage Hall · a booking that no longer exists · Projector · an equipment request that no longer exists");
});
it("shows nothing extra for a decision with no arrangements", async () => {
  const el = await mount({...BASE, decision: "approved"});
  expect(el.textContent).not.toContain("Concerns:");
  expect(el.textContent).not.toContain("Coordinator's response:");
});
it("shows an old rejection without a response and falls back for missing names", async () => {
  const el = await mount({...BASE, decision: "arrangement_rejected", rejected_venues: [{venue_id: "v1", venue_name: null}]});
  expect(el.textContent).toContain("Rejected venue: a venue that no longer exists");
  expect(el.textContent).not.toContain("Coordinator's response:");
});
it("falls back to Coordinator when the response author no longer exists", async () => {
  const el = await mount({...BASE, decision: "arrangement_rejected", revision: {note: "Moved", by_name: null, at: "2031-01-02T02:00:00Z"}});
  expect(el.textContent).toContain("Coordinator ·");
});
