import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import AmendmentBanner from "@/components/events/AmendmentBanner.vue";

const AMENDMENT = {
  id: "a1",
  message: "Please confirm the attendance",
  flagged_fields: ["expected_attendance", "starts_at"],
  returned_at: "2026-09-24T03:00:00Z",
};

const mounted = [];

async function mount(props, slot) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(AmendmentBanner, props, slot ? { default: slot } : undefined) });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el;
}

describe("AmendmentBanner (SCRUM-33)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("shows the organiser the coordinator's message and the fields to review", async () => {
    const el = await mount({ amendment: AMENDMENT });

    expect(el.textContent).toContain("Your coordinator asked for changes");
    expect(el.textContent).toContain("Please confirm the attendance");
    expect(el.textContent).toContain("Expected attendance");
    expect(el.textContent).toContain("Proposed date and start time");
  });

  it("tells the coordinator it is waiting on the organiser", async () => {
    const el = await mount({ amendment: AMENDMENT, audience: "coordinator" });

    expect(el.textContent).toContain("Waiting for the organiser to amend");
  });

  it("shows when it was returned, in Singapore time", async () => {
    const el = await mount({ amendment: AMENDMENT });

    expect(el.textContent).toContain("24 Sept 2026");
    expect(el.textContent).toContain("11:00");
  });

  it("omits the field list when nothing was flagged", async () => {
    const el = await mount({ amendment: { ...AMENDMENT, flagged_fields: [] } });

    expect(el.textContent).not.toContain("Fields to review");
  });

  it("renders an unknown field readably", async () => {
    const el = await mount({ amendment: { ...AMENDMENT, flagged_fields: ["venue_notes"] } });

    expect(el.textContent).toContain("venue notes");
  });

  it("renders actions passed in its slot", async () => {
    const el = await mount({ amendment: AMENDMENT }, () => h("button", "Amend and resubmit"));

    expect(el.querySelector("button").textContent).toBe("Amend and resubmit");
  });
});
