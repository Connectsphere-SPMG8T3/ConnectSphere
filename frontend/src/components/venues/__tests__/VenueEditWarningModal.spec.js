import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import VenueEditWarningModal from "@/components/venues/VenueEditWarningModal.vue";

const mounted = [];

async function mountModal(warnings) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(VenueEditWarningModal, { open: true, warnings }) });
  app.mount(el);
  mounted.push(app);
  await nextTick();
}

const unsuitable = {
  booking_id: "d-1",
  event_id: "e0000000-0000-4000-8000-000000000101",
  event_name: "Annual Gala",
  outcome: "unsuitable",
  reasons: ["Capacity 100 is below the expected attendance of 120."],
};
const warningOnly = {
  booking_id: "d-2",
  event_id: "e0000000-0000-4000-8000-000000000102",
  event_name: "Board Meeting",
  outcome: "warning",
  reasons: ["The theatre layout this event needs is not supported."],
};

const items = () => [...document.querySelectorAll("[data-testid='affected-booking']")];
const badge = (item) => item.querySelector("[data-testid='outcome-badge']");

describe("VenueEditWarningModal (CR-94)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("marks a booking the edit makes unsuitable, with its reason", async () => {
    await mountModal([unsuitable]);

    const [item] = items();
    expect(badge(item).textContent.trim()).toBe("Unsuitable");
    expect(badge(item).className).toContain("bg-bauhaus-red");
    expect(item.textContent).toContain("Annual Gala");
    expect(item.textContent).toContain("Capacity 100 is below the expected attendance of 120.");
  });

  it("marks a warning-only booking as a warning", async () => {
    await mountModal([warningOnly]);

    const [item] = items();
    expect(badge(item).textContent.trim()).toBe("Warning");
    expect(badge(item).className).toContain("bg-bauhaus-yellow");
  });

  it("labels each booking on its own when both kinds are listed", async () => {
    await mountModal([unsuitable, warningOnly]);

    expect(items().map((item) => badge(item).textContent.trim())).toEqual(["Unsuitable", "Warning"]);
  });

  it("says Unsuitable bookings will be flagged but not cancelled (AC3, AC6)", async () => {
    await mountModal([unsuitable, warningOnly]);

    const text = document.body.textContent;
    expect(text).toContain("Saving will not cancel or move any booking.");
    expect(text).toContain("Bookings marked Unsuitable will be flagged for follow-up");
  });

  it("does not mention flagging when every booking is only a warning (AC4)", async () => {
    await mountModal([warningOnly]);

    expect(document.body.textContent).toContain("Saving will not cancel or move any booking.");
    expect(document.body.textContent).not.toMatch(/flagged/i);
  });

  it("names an event with no name by its id", async () => {
    await mountModal([{ ...warningOnly, event_name: null }]);

    expect(items()[0].textContent).toContain("Event e0000000");
  });
});

describe("VenueEditWarningModal failure", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("shows why the save failed beside the warnings", async () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    const app = createApp({
      render: () => h(VenueEditWarningModal, { open: true, warnings: [unsuitable], error: "Could not save." }),
    });
    app.mount(el);
    mounted.push(app);
    await nextTick();

    expect(document.body.querySelector('[role="alert"]').textContent).toContain("Could not save.");
  });
});
