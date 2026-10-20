import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import RequestVenueModal from "@/components/venues/RequestVenueModal.vue";
import SuitabilityFindings from "@/components/venues/SuitabilityFindings.vue";
import VenueResultCard from "@/components/venues/VenueResultCard.vue";

const VENUE = {
  id: "v1", name: "Hall A", location: "Bukit Timah", capacity: 150, layouts: [], facilities: [],
  accessibility_features: [], opens_at: "08:00:00", closes_at: "22:00:00", is_active: true,
};
const UNSUITABLE = {
  verdict: "unsuitable",
  reasons: [
    { code: "missing_facility", severity: "unsuitable", message: "Missing facilities this event needs: projector." },
    { code: "layout_not_supported", severity: "warning", message: "The u shape layout this event needs is not supported." },
  ],
};

const mounted = [];

async function mountComponent(component, props) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: {} }, { name: "venue-detail", path: "/venues/:id", component: {} }],
  });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(component, props) });
  app.use(router);
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el;
}

const card = (result) =>
  mountComponent(VenueResultCard, { result: { venue: VENUE, availability: "available", excluded: false, reasons: [], ...result } });
const text = (el, selector) => el.querySelector(selector).textContent.trim();

afterEach(() => {
  mounted.splice(0).forEach((app) => app.unmount());
  document.body.innerHTML = "";
});

describe("SuitabilityFindings", () => {
  it("lists every finding with its plain-language reason", async () => {
    const el = await mountComponent(SuitabilityFindings, { suitability: UNSUITABLE });

    const items = el.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain("Missing facilities this event needs: projector.");
    expect(items[0].textContent).toContain("Fails");
    expect(items[1].textContent).toContain("Warning");
  });

  it("renders nothing for a clean pass", async () => {
    const el = await mountComponent(SuitabilityFindings, { suitability: { verdict: "suitable", reasons: [] } });

    expect(el.querySelector("li")).toBeNull();
  });
});

describe("VenueResultCard suitability (AC8, AC9)", () => {
  it("shows suitability beside, and apart from, availability", async () => {
    const el = await card({ availability: "unavailable", suitability: { verdict: "suitable", reasons: [] } });

    expect(text(el, "[data-testid='availability-badge']")).toBe("Unavailable");
    expect(text(el, "[data-testid='suitability-badge']")).toBe("Suitable");
  });

  it("lists the reasons a venue is unsuitable", async () => {
    const el = await card({ suitability: UNSUITABLE });

    expect(text(el, "[data-testid='suitability-badge']")).toBe("Unsuitable");
    expect(el.textContent).toContain("Missing facilities this event needs: projector.");
  });

  it("shows no suitability when the search named no event", async () => {
    const el = await card({ suitability: null });

    expect(el.querySelector("[data-testid='suitability-badge']")).toBeNull();
    expect(el.querySelector("[data-testid='suitability-findings']")).toBeNull();
  });
});

describe("RequestVenueModal suitability (AC9)", () => {
  const props = { open: true, venueName: "Hall A", eventName: "Summit", period: "10 Oct" };

  it("shows the venue's verdict and findings on the selection step", async () => {
    await mountComponent(RequestVenueModal, { ...props, suitability: UNSUITABLE });

    expect(text(document.body, "[data-testid='suitability-badge']")).toBe("Unsuitable");
    expect(document.body.textContent).toContain("Missing facilities this event needs: projector.");
  });

  it("shows nothing when there is no verdict", async () => {
    await mountComponent(RequestVenueModal, props);

    expect(document.querySelector("[data-testid='suitability-badge']")).toBeNull();
  });
});
