import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import RequestVenueModal from "@/components/venues/RequestVenueModal.vue";

const mounted = [];

async function mountModal(props = {}) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(RequestVenueModal, {
      open: true, venueName: "Innovation Lab", eventName: "Partner Summit",
      period: "7 Apr 2031, 12:30 pm – 7 Apr 2031, 2:00 pm", ...props,
    }),
  });
  app.mount(el);
  mounted.push(app);
  await nextTick();
}

afterEach(() => {
  mounted.splice(0).forEach((app) => app.unmount());
  document.body.innerHTML = "";
});

describe("RequestVenueModal (SCRUM-21 AC2)", () => {
  it("shows what is in the way under the refusal", async () => {
    await mountModal({
      error: "Venue already held for this time by another event.",
      conflict: "\"Alumni Night\" occupies it 7 Apr 2031, 9:30 am – 12:45 pm, including setup and turnaround.",
    });

    const alert = document.querySelector("[role='alert']");
    expect(alert.textContent).toContain("Venue already held for this time by another event.");
    expect(alert.textContent).toContain("\"Alumni Night\" occupies it 7 Apr 2031, 9:30 am – 12:45 pm");
  });

  it("shows the refusal alone when nothing was named", async () => {
    await mountModal({ error: "This venue is inactive." });

    expect(document.querySelector("[role='alert']").textContent.trim()).toBe("This venue is inactive.");
  });
});
