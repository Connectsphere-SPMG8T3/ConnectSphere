import { createApp, h, nextTick, reactive } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import VenueAvailabilityCalendar from "@/components/venues/VenueAvailabilityCalendar.vue";

// SCRUM-57: one venue's availability calendar.

const mounted = [];
// Mon 10 Mar 2031, 10:00 Singapore time.
const NOW = new Date("2031-03-10T02:00:00Z");

const CONFIRMED = {
  id: "d1", kind: "booking", type: "confirmed", status: "approved", event_id: "e1", event_name: "Gala",
  // Tue 11 Mar, 10:00–12:00 SGT, occupying 09:30–12:45.
  period: { starts_at: "2031-03-11T02:00:00Z", ends_at: "2031-03-11T04:00:00Z" },
  occupied_period: { starts_at: "2031-03-11T01:30:00Z", ends_at: "2031-03-11T04:45:00Z" },
  setup_minutes: 30, turnaround_minutes: 45, expires_at: null, flag: null, flag_reason: null,
  reason: null, notes: null, created_by: null, created_at: null,
};
const HOLD = {
  ...CONFIRMED, id: "d2", type: "tentative", status: "held", event_name: "Workshop",
  period: { starts_at: "2031-03-12T06:00:00Z", ends_at: "2031-03-12T08:00:00Z" },
  occupied_period: { starts_at: "2031-03-12T06:00:00Z", ends_at: "2031-03-12T08:00:00Z" },
  setup_minutes: 0, turnaround_minutes: 0, expires_at: "2031-03-11T10:00:00Z",
};
const AFFECTED = { ...CONFIRMED, id: "d3", type: "affected", flag: "affected", event_name: "Summit",
  flag_reason: "Venue unavailable: maintenance" };
const BLOCK = {
  ...CONFIRMED, id: "b1", kind: "block", type: "blocked", status: null, event_id: null, event_name: null,
  period: { starts_at: "2031-03-13T00:00:00Z", ends_at: "2031-03-13T06:00:00Z" },
  occupied_period: { starts_at: "2031-03-13T00:00:00Z", ends_at: "2031-03-13T06:00:00Z" },
  setup_minutes: 0, turnaround_minutes: 0, reason: "maintenance", notes: "Aircon",
  created_by: { id: "a1", full_name: "Vera Staff" }, created_at: "2031-03-01T01:00:00Z",
};
const VENUES = [
  { id: "v1", name: "Hall A", is_active: true },
  { id: "v2", name: "Hall B", is_active: false },
];

function payload(entries, venue = VENUES[0]) {
  return { venue, timezone: "Asia/Singapore", entries, venues: VENUES };
}

async function mountCalendar(initial = {}) {
  const handlers = {
    onSelectVenue: vi.fn(), onSetView: vi.fn(), onStep: vi.fn(), onToday: vi.fn(), onRefresh: vi.fn(),
    onOpenDay: vi.fn(),
  };
  const props = reactive({
    calendar: payload([CONFIRMED, HOLD, AFFECTED, BLOCK]), view: "week", anchorKey: "2031-03-10",
    isLoading: false, hasLoaded: true, error: "", now: NOW, ...initial,
  });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { render: () => null } },
      { path: "/bookings/:id", name: "booking-request", component: { render: () => null } },
    ],
  });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(VenueAvailabilityCalendar, { ...props, ...handlers }) }).use(router);
  app.mount(el);
  mounted.push(app);
  await router.isReady();
  await nextTick();
  return { el, props, ...handlers };
}

const entries = (el) => [...el.querySelectorAll('[data-testid="calendar-entry"]')];
const entry = (el, type) => el.querySelector(`[data-testid="calendar-entry"][data-type="${type}"]`);
const buttonByText = (el, text) => [...el.querySelectorAll("button")].find((b) => b.textContent.trim() === text);

afterEach(() => {
  mounted.splice(0).forEach((app) => app.unmount());
  document.body.innerHTML = "";
});

describe("VenueAvailabilityCalendar (SCRUM-57)", () => {
  it("draws every type in the week, each labelled as well as coloured (AC2, AC3)", async () => {
    const { el } = await mountCalendar();

    expect(entries(el).map((node) => node.dataset.type).sort()).toEqual(
      ["affected", "blocked", "confirmed", "tentative"],
    );
    expect(entry(el, "confirmed").textContent).toContain("Confirmed");
    expect(entry(el, "affected").textContent).toContain("Affected");
    expect(entry(el, "blocked").textContent).toContain("Maintenance");
    expect(entry(el, "affected").innerHTML).toContain("bg-stripes-red");
    expect(entry(el, "blocked").innerHTML).toContain("bg-crosshatch");
    expect(entry(el, "tentative").innerHTML).toContain("border-dashed");
    const legend = el.querySelector('[data-testid="calendar-legend"]').textContent;
    for (const label of ["Confirmed", "Tentative", "Affected", "Re-review", "Blocked", "Setup / turnaround"]) {
      expect(legend).toContain(label);
    }
  });

  it("draws a booking's setup and turnaround as separate hatched bands, a hold and a block with none (AC5)", async () => {
    const { el } = await mountCalendar();

    const bands = (type) => [...entry(el, type).querySelectorAll("[data-band]")].map((band) => band.dataset.band);
    expect(bands("confirmed")).toEqual(["setup", "event", "turnaround"]);
    expect(entry(el, "confirmed").querySelector('[data-band="setup"]').className).toContain("bg-hatch");
    expect(entry(el, "confirmed").querySelector('[data-band="setup"]').textContent).toContain("Setup");
    expect(entry(el, "confirmed").querySelector('[data-band="turnaround"]').textContent).toContain("Turnaround");
    expect(bands("tentative")).toEqual(["event"]);
    expect(bands("blocked")).toEqual(["event"]);
    expect(entry(el, "confirmed").textContent).toContain("10:00–12:00");
  });

  it("shows a hold's expiry and stops drawing it once it has expired (AC6)", async () => {
    const { el, props } = await mountCalendar();
    expect(entry(el, "tentative").textContent).toContain("Tentative · expires Tue 11 Mar 2031, 18:00");

    props.now = new Date("2031-03-11T10:00:00Z");
    await nextTick();

    expect(entry(el, "tentative")).toBeNull();
  });

  it("places each entry in its Singapore day's column", async () => {
    const { el } = await mountCalendar();
    expect(entry(el, "confirmed").closest("[data-day]").dataset.day).toBe("2031-03-11");
    expect(entry(el, "blocked").closest("[data-day]").dataset.day).toBe("2031-03-13");
  });

  it("opens an entry's details and closes them again (AC9)", async () => {
    const { el } = await mountCalendar();
    const details = () => el.querySelector('[data-testid="entry-details"]').textContent;
    expect(details()).toContain("Select an entry");

    entry(el, "affected").click();
    await nextTick();
    expect(details()).toContain("Summit");
    expect(details()).toContain("Approved");
    expect(details()).toContain("Tue 11 Mar 2031, 09:30–12:45");
    expect(details()).toContain("Venue unavailable: maintenance");
    expect(el.querySelector('[data-testid="entry-details"] a').getAttribute("href")).toBe("/bookings/d3");

    entry(el, "blocked").click();
    await nextTick();
    expect(details()).toContain("Maintenance");
    expect(details()).toContain("Aircon");
    expect(details()).toContain("Vera Staff");
    expect(el.querySelector('[data-testid="entry-details"] a')).toBeNull();

    el.querySelector('button[aria-label="Close the details"]').click();
    await nextTick();
    expect(details()).toContain("Select an entry");
  });

  it("clicking the selected entry again deselects it, and a new period clears it", async () => {
    const { el, props } = await mountCalendar();
    entry(el, "confirmed").click();
    await nextTick();
    entry(el, "confirmed").click();
    await nextTick();
    expect(el.querySelector('[data-testid="entry-details"]').textContent).toContain("Select an entry");

    entry(el, "confirmed").click();
    await nextTick();
    props.anchorKey = "2031-03-17";
    await nextTick();
    expect(el.querySelector('[data-testid="entry-details"]').textContent).toContain("Select an entry");
  });

  it("shows the empty state for a venue with nothing in the period (AC10)", async () => {
    const { el } = await mountCalendar({ calendar: payload([]) });
    expect(el.querySelector('[data-testid="calendar-empty"]').textContent).toContain(
      "No bookings, holds or blocks at Hall A in this period.",
    );
  });

  it("names the timezone and the period shown (AC10)", async () => {
    const { el } = await mountCalendar();
    expect(el.querySelector("h2").textContent).toContain("10 Mar – 16 Mar 2031");
    expect(el.textContent).toContain("Asia/Singapore");
  });

  it("offers every venue to switch to, marking an inactive one (AC1)", async () => {
    const { el, onSelectVenue } = await mountCalendar();
    const select = el.querySelector("select");
    expect([...select.options].map((option) => option.textContent.trim())).toEqual(["Hall A", "Hall B (inactive)"]);

    select.value = "v2";
    select.dispatchEvent(new Event("change"));
    await nextTick();
    expect(onSelectVenue).toHaveBeenCalledWith("v2");
  });

  it("says when the venue shown is inactive", async () => {
    const { el } = await mountCalendar({ calendar: payload([CONFIRMED], VENUES[1]) });
    expect(el.textContent).toContain("Hall B is inactive.");
  });

  it("asks the parent to change view, step, go to today and refresh (AC1, AC4)", async () => {
    const { el, onSetView, onStep, onToday, onRefresh } = await mountCalendar({ anchorKey: "2031-03-24" });

    buttonByText(el, "Day").click();
    el.querySelector('button[aria-label="Previous week"]').click();
    el.querySelector('button[aria-label="Next week"]').click();
    buttonByText(el, "Today").click();
    buttonByText(el, "Refresh").click();

    expect(onSetView).toHaveBeenCalledWith("day");
    expect(onStep.mock.calls).toEqual([[-1], [1]]);
    expect(onToday).toHaveBeenCalled();
    expect(onRefresh).toHaveBeenCalled();
  });

  it("disables Today when today is in view, and Refresh while loading", async () => {
    const { el } = await mountCalendar({ isLoading: true });
    expect(buttonByText(el, "Today").disabled).toBe(true);
    expect(buttonByText(el, "Refreshing…").disabled).toBe(true);
  });

  it("draws a day view as one column", async () => {
    const { el } = await mountCalendar({ view: "day", anchorKey: "2031-03-11" });
    expect(el.querySelectorAll("[data-day]")).toHaveLength(1);
    expect(entries(el).map((node) => node.dataset.type).sort()).toEqual(["affected", "confirmed"]);
  });

  it("draws a month as bars that open their details, and a day number opens that day (AC1)", async () => {
    const { el, onOpenDay } = await mountCalendar({ view: "month", anchorKey: "2031-03-01" });

    expect(el.querySelector('[data-testid="month-grid"]')).not.toBeNull();
    expect(el.querySelector('[data-testid="time-grid"]')).toBeNull();
    expect(entry(el, "blocked").textContent).toContain("Blocked · Maintenance");
    expect(buttonByText(el, "Today").disabled).toBe(true);

    entry(el, "confirmed").click();
    await nextTick();
    expect(el.querySelector('[data-testid="entry-details"]').textContent).toContain("Gala");

    el.querySelector('button[aria-label="Open 2031-03-12 in the day view"]').click();
    expect(onOpenDay).toHaveBeenCalledWith("2031-03-12");
  });

  it("counts what doesn't fit in a month cell and opens that day", async () => {
    const many = Array.from({ length: 5 }, (_, i) => ({ ...BLOCK, id: `b${i}` }));
    const { el, onOpenDay } = await mountCalendar({ view: "month", anchorKey: "2031-03-01",
      calendar: payload(many) });

    const more = buttonByText(el, "+2 more");
    expect(more).toBeTruthy();
    more.click();
    expect(onOpenDay).toHaveBeenCalledWith("2031-03-13");
  });

  it("shows an error and a first load", async () => {
    const { el } = await mountCalendar({ calendar: null, hasLoaded: false, error: "" });
    expect(el.textContent).toContain("Loading the calendar…");

    const failed = await mountCalendar({ calendar: null, error: "Venue not found." });
    expect(failed.el.querySelector('[role="alert"]').textContent).toContain("Venue not found.");
  });
});
