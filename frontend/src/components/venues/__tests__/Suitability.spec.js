import { createApp, h, nextTick, ref } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
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

describe("RequestVenueModal acknowledgement (BR-R3)", () => {
  const WARNING = {
    verdict: "suitable_with_warnings",
    reasons: [{ code: "layout_not_supported", severity: "warning", message: "The banquet layout this event needs is not supported." }],
  };
  const props = { open: true, venueName: "Hall A", eventName: "Summit", period: "10 Oct" };
  const requestButton = () => document.querySelector("[aria-label='Request venue']");
  const checkbox = () => document.querySelector("[data-testid='acknowledge-warnings']");

  it("asks for the warnings to be acknowledged before the request can be sent", async () => {
    const onConfirm = vi.fn();
    await mountComponent(RequestVenueModal, { ...props, suitability: WARNING, onConfirm });

    expect(checkbox()).not.toBeNull();
    expect(requestButton().disabled).toBe(true);
    requestButton().click();
    expect(onConfirm).not.toHaveBeenCalled();

    checkbox().click();
    await nextTick();
    expect(requestButton().disabled).toBe(false);
    requestButton().click();
    expect(onConfirm).toHaveBeenCalledWith("", true);
  });

  it("forgets the acknowledgement when the dialog is opened again", async () => {
    const open = ref(true);
    const el = document.createElement("div");
    document.body.appendChild(el);
    const app = createApp({ render: () => h(RequestVenueModal, { ...props, open: open.value, suitability: WARNING }) });
    app.mount(el);
    mounted.push(app);
    await nextTick();
    checkbox().click();
    await nextTick();
    expect(checkbox().checked).toBe(true);

    open.value = false;
    await nextTick();
    open.value = true;
    await nextTick();

    expect(checkbox().checked).toBe(false);
  });

  it("sends a suitable venue's request with no acknowledgement", async () => {
    const onConfirm = vi.fn();
    await mountComponent(RequestVenueModal, { ...props, suitability: { verdict: "suitable", reasons: [] }, onConfirm });

    expect(checkbox()).toBeNull();
    requestButton().click();
    expect(onConfirm).toHaveBeenCalledWith("", false);
  });

  it("does not offer to request a venue that is unsuitable", async () => {
    const onConfirm = vi.fn();
    await mountComponent(RequestVenueModal, { ...props, suitability: UNSUITABLE, onConfirm });

    expect(checkbox()).toBeNull();
    expect(requestButton().disabled).toBe(true);
    expect(document.body.textContent).toContain("unsuitable");
    requestButton().click();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("leaves the request open when there is no verdict", async () => {
    const onConfirm = vi.fn();
    await mountComponent(RequestVenueModal, { ...props, onConfirm });

    expect(requestButton().disabled).toBe(false);
    requestButton().click();
    expect(onConfirm).toHaveBeenCalledWith("", false);
  });
});

describe("VenueResultCard availability and details", () => {
  it("shows no availability badge when the search did not check availability", async () => {
    const el = await card({ availability: "not_checked" });

    expect(el.querySelector("[data-testid='availability-badge']")).toBeNull();
    expect(el.textContent).not.toContain("Availability not checked");
  });

  it.each([
    ["available", "Available"],
    ["unavailable", "Unavailable"],
  ])("shows the %s badge when availability was checked", async (availability, label) => {
    const el = await card({ availability });

    expect(text(el, "[data-testid='availability-badge']")).toBe(label);
  });

  it("shows capacity and opening hours, and each layout, facility and accessibility feature as its own chip", async () => {
    const el = await mountComponent(VenueResultCard, {
      result: {
        venue: {
          ...VENUE,
          layouts: [{ layout: "theatre", capacity_for_layout: 120 }],
          facilities: ["projector", "wifi"],
          accessibility_features: ["wheelchair_access"],
        },
        availability: "available",
        excluded: false,
        reasons: [],
      },
    });

    expect(el.textContent).toContain("150 pax");
    expect(el.textContent).toContain("08:00–22:00");
    const chips = [...el.querySelectorAll("ul > li")].map((li) => li.textContent.trim());
    expect(chips).toHaveLength(4);
    expect(chips[0]).toContain("120");
  });

  it("shows the venue's setup and turnaround time, and 0 min when it records none", async () => {
    const withTimes = await mountComponent(VenueResultCard, {
      result: { venue: { ...VENUE, setup_minutes: 30, turnaround_minutes: 15 }, availability: "available", excluded: false, reasons: [] },
    });
    const time = (el, label) => [...el.querySelectorAll("dt")].find((dt) => dt.textContent.trim() === label).nextElementSibling.textContent.trim();
    expect(time(withTimes, "Setup")).toBe("30 min");
    expect(time(withTimes, "Turnaround")).toBe("15 min");

    document.body.innerHTML = "";
    const none = await card({});
    expect(time(none, "Setup")).toBe("0 min");
    expect(time(none, "Turnaround")).toBe("0 min");
  });

  it("says when a venue records no layouts, facilities or accessibility features", async () => {
    const el = await card({});

    expect(el.textContent).toContain("None recorded");
    expect(el.querySelectorAll("ul > li")).toHaveLength(0);
  });
});

describe("VenueResultCard image carousel", () => {
  const withVenue = (venue) =>
    mountComponent(VenueResultCard, {
      result: { venue: { ...VENUE, ...venue }, availability: "available", excluded: false, reasons: [] },
    });

  it("shows one slide per supported layout, labelled as a schematic, and steps through them", async () => {
    const el = await withVenue({
      layouts: [
        { layout: "theatre", capacity_for_layout: 120 },
        { layout: "banquet", capacity_for_layout: 80 },
      ],
    });

    const gallery = el.querySelector("[aria-roledescription='carousel']");
    expect(gallery.textContent).toContain("1 of 2");
    expect(gallery.textContent).toContain("Theatre · 120 pax");
    expect(gallery.textContent).toContain("Schematic, not this room's floor plan");

    gallery.querySelector("button[aria-label='Next slide']").click();
    await nextTick();
    expect(gallery.textContent).toContain("2 of 2");
    expect(gallery.textContent).toContain("Banquet · 80 pax");
  });

  it("moves the carousel to a layout when its chip is chosen, and the chip follows the carousel", async () => {
    const el = await withVenue({
      layouts: [
        { layout: "theatre", capacity_for_layout: 120 },
        { layout: "banquet", capacity_for_layout: 80 },
      ],
    });
    const gallery = el.querySelector("[aria-roledescription='carousel']");
    const chip = (label) => [...el.querySelectorAll("button[aria-pressed]")].find((b) => b.textContent.trim() === label);

    expect(chip("Theatre (120)").getAttribute("aria-pressed")).toBe("true");
    expect(chip("Banquet (80)").getAttribute("aria-pressed")).toBe("false");

    chip("Banquet (80)").click();
    await nextTick();
    expect(gallery.textContent).toContain("2 of 2");
    expect(gallery.textContent).toContain("Banquet · 80 pax");
    expect(chip("Banquet (80)").getAttribute("aria-pressed")).toBe("true");
    expect(chip("Theatre (120)").getAttribute("aria-pressed")).toBe("false");

    gallery.querySelector("button[aria-label='Previous slide']").click();
    await nextTick();
    expect(chip("Theatre (120)").getAttribute("aria-pressed")).toBe("true");
  });

  it("tells the user a layout can be previewed only when there is more than one to choose from", async () => {
    const two = await withVenue({
      layouts: [
        { layout: "theatre", capacity_for_layout: 120 },
        { layout: "banquet", capacity_for_layout: 80 },
      ],
    });
    expect(two.textContent).toContain("Select one to preview it");

    document.body.innerHTML = "";
    const one = await withVenue({ layouts: [{ layout: "theatre", capacity_for_layout: 120 }] });
    expect(one.textContent).not.toContain("Select one to preview it");
  });

  it("leads with the venue's photos when it has any", async () => {
    const el = await withVenue({
      layouts: [{ layout: "theatre", capacity_for_layout: 120 }],
      photos: [{ url: "https://example.test/hall-a.jpg", caption: "From the stage" }],
    });

    expect(el.querySelector("[aria-roledescription='carousel'] img").getAttribute("src")).toBe("https://example.test/hall-a.jpg");
    expect(el.textContent).toContain("1 of 2");
  });

  it("holds the frame with a note when the venue has no photos and no layouts", async () => {
    const el = await withVenue({ layouts: [], photos: [] });

    expect(el.querySelector("[aria-roledescription='carousel']")).toBeNull();
    expect(el.textContent).toContain("No images on file");
  });
});
