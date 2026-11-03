import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import OrganiserVenueList from "@/components/events/OrganiserVenueList.vue";

const VENUE = {
  booking_id: "b-1",
  space_label: "Main hall",
  venue_name: "Marina Hall",
  location: "1 Bayfront Ave",
  starts_at: "2026-11-12T02:00:00Z",
  ends_at: "2026-11-12T04:00:00Z",
  is_primary: false,
  status: "approved",
  status_label: "Approved",
  next_action: "Nothing is needed from you.",
};

const mounted = [];

async function mount(props) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(OrganiserVenueList, { timezone: "Asia/Singapore", ...props }) });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el;
}

describe("OrganiserVenueList (CR-111)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("lists each venue separately with its location, window, status and next action", async () => {
    const el = await mount({ venues: [VENUE, { ...VENUE, booking_id: "b-2", venue_name: "Harbour Foyer", space_label: "Foyer" }] });

    const rows = el.querySelectorAll("[data-testid='organiser-venue']");
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("Marina Hall");
    expect(rows[0].textContent).toContain("1 Bayfront Ave");
    expect(rows[0].textContent).toContain("Main hall");
    expect(rows[0].textContent).toContain("10:00");
    expect(rows[0].textContent).toContain("Approved");
    expect(rows[0].textContent).toContain("Nothing is needed from you.");
    expect(rows[1].textContent).toContain("Harbour Foyer");
  });

  it("marks the primary venue", async () => {
    const el = await mount({ venues: [{ ...VENUE, is_primary: true }, { ...VENUE, booking_id: "b-2" }] });

    const rows = el.querySelectorAll("[data-testid='organiser-venue']");
    expect(rows[0].textContent).toContain("Primary venue");
    expect(rows[1].textContent).not.toContain("Primary venue");
  });

  it("shows an affected venue as affected, with the next action", async () => {
    const el = await mount({ venues: [{ ...VENUE, status: "affected", status_label: "Affected", next_action: "This venue is no longer available. Your coordinator will contact you about the next step." }] });

    const row = el.querySelector("[data-testid='organiser-venue']");
    expect(row.getAttribute("data-status")).toBe("affected");
    expect(row.textContent).toContain("Affected");
    expect(row.textContent).toContain("Your coordinator will contact you");
  });

  it("copes with a venue that has no location or space label", async () => {
    const el = await mount({ venues: [{ ...VENUE, location: null, space_label: null }] });

    expect(el.textContent).toContain("Marina Hall");
    expect(el.textContent).not.toContain("null");
  });

  it("renders nothing when there are no venues", async () => {
    const el = await mount({ venues: [] });

    expect(el.querySelector("[data-testid='organiser-venues']")).toBeNull();
  });
});
