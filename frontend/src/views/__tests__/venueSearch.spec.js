import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { useVenuesStore } from "@/features/venues/venueSearchStore";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  venuesApi: { search: vi.fn(), get: vi.fn() },
}));

const HALL_A = {
  id: "b0000000-0000-4000-8000-000000000001",
  name: "Hall A",
  location: "Bukit Timah Campus",
  capacity: 150,
  layouts: [{ layout: "theatre", capacity_for_layout: 120 }],
  facilities: ["projector", "wifi"],
  accessibility_features: ["wheelchair_access"],
  opens_at: "08:00:00",
  closes_at: "22:00:00",
  is_active: true,
  description: null,
};
const HALL_B = { ...HALL_A, id: "b0000000-0000-4000-8000-000000000002", name: "Hall B", capacity: 100 };

const RESPONSE = {
  criteria: {},
  results: [
    { venue: HALL_A, availability: "available", excluded: false, reasons: [] },
    {
      venue: HALL_B,
      availability: "unavailable",
      excluded: true,
      reasons: [
        { code: "capacity_below_minimum", message: "Capacity 100 is below the required 150" },
        { code: "held", message: "Held by another event 10 Oct 13:00–16:00" },
      ],
    },
  ],
  included_count: 1,
  excluded_count: 1,
};

async function mountView(component, { route } = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = { id: "u1", role: "event_coordinator" };
  authStore.sessionVerified = true;
  const { default: router } = await import("@/router");
  if (route) await router.push(route);
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(component).use(pinia).use(router);
  app.mount(el);
  await nextTick();
  await nextTick();
  return { el, venuesStore: useVenuesStore() };
}

async function settle() {
  await Promise.resolve();
  await nextTick();
  await nextTick();
}

describe("VenueSearchView", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
    venuesApi.search.mockResolvedValue(RESPONSE);
  });

  it("lists matching venues on first visit and reveals excluded ones with reasons on demand", async () => {
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el, venuesStore } = await mountView(VenueSearchView);
    await settle();

    expect(venuesApi.search).toHaveBeenCalledTimes(1);
    expect(el.textContent).toContain("1 matching venue");
    expect(el.textContent).toContain("Hall A");
    expect(el.textContent).toContain("Theatre (120)");
    expect(el.textContent).toContain("Add a date and time to check availability");
    expect(el.textContent).not.toContain("Hall B");

    const toggle = [...el.querySelectorAll("button")].find((b) => b.textContent.includes("Show 1 excluded"));
    expect(toggle).toBeTruthy();
    toggle.click();
    await settle();

    expect(venuesStore.showExcluded).toBe(true);
    expect(el.textContent).toContain("Excluded venues");
    expect(el.textContent).toContain("Hall B");
    expect(el.textContent).toContain("Capacity 100 is below the required 150");
    expect(el.textContent).toContain("Held by another event 10 Oct 13:00–16:00");
    expect(el.textContent).toContain("Unavailable");
  });

  it("shows field errors instead of searching when the period is incomplete", async () => {
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el, venuesStore } = await mountView(VenueSearchView);
    await settle();
    venuesApi.search.mockClear();

    venuesStore.criteria.date = "2026-10-10";
    venuesStore.criteria.startTime = "14:00";
    el.querySelector("form").dispatchEvent(new Event("submit", { cancelable: true }));
    await settle();

    expect(venuesApi.search).not.toHaveBeenCalled();
    expect(el.textContent).toContain("Enter the end time.");
  });

  it("sends the filled-in criteria as Singapore-time query params", async () => {
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el, venuesStore } = await mountView(VenueSearchView);
    await settle();
    venuesApi.search.mockClear();

    Object.assign(venuesStore.criteria, {
      date: "2026-10-10",
      startTime: "14:00",
      endTime: "17:00",
      minCapacity: "150",
      facilities: ["projector"],
    });
    el.querySelector("form").dispatchEvent(new Event("submit", { cancelable: true }));
    await settle();

    expect(venuesApi.search).toHaveBeenCalledWith(
      {
        starts_at: "2026-10-10T14:00:00+08:00",
        ends_at: "2026-10-10T17:00:00+08:00",
        min_capacity: 150,
        facilities: ["projector"],
        include_excluded: true,
      },
      "access",
    );
  });
});

const PROFILE = {
  ...HALL_A,
  updated_at: "2026-09-18T02:30:00Z",
  updated_by: { id: "a0000000-0000-4000-8000-000000000003", full_name: "Val Staff" },
  turnaround_minutes: 0,
  upcoming_blocks: [
    {
      id: "c1",
      period: { starts_at: "2026-10-10T00:00:00Z", ends_at: "2026-10-10T04:00:00Z" },
      reason: "maintenance",
      notes: "Air-con servicing",
    },
  ],
  upcoming_bookings: [
    {
      id: "d1",
      event_id: "e1",
      event_name: "Annual Town Hall",
      period: { starts_at: "2026-10-10T05:00:00Z", ends_at: "2026-10-10T08:00:00Z" },
      status: "held",
    },
    {
      id: "d2",
      event_id: "e2",
      event_name: "Alumni Dinner",
      period: { starts_at: "2026-10-12T03:00:00Z", ends_at: "2026-10-12T06:00:00Z" },
      status: "approved",
    },
  ],
};

describe("VenueDetailView (SCRUM-67)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
    venuesApi.get.mockResolvedValue(PROFILE);
  });

  async function openProfile() {
    const { default: VenueDetailView } = await import("@/views/venues/VenueDetailView.vue");
    const { el } = await mountView(VenueDetailView, { route: { name: "venue-detail", params: { id: HALL_A.id } } });
    await settle();
    return el;
  }

  it("renders the venue with its upcoming blocks in Singapore time", async () => {
    const el = await openProfile();

    expect(venuesApi.get).toHaveBeenCalledWith(HALL_A.id, "access");
    expect(el.textContent).toContain("Hall A");
    expect(el.textContent).toContain("Maintenance");
    expect(el.textContent).toContain("Air-con servicing");
    // 05:00Z is 13:00 in Singapore.
    expect(el.textContent).toMatch(/13:00/);
  });

  it("shows the whole profile in one place, from one request (AC1)", async () => {
    const el = await openProfile();

    expect(venuesApi.get).toHaveBeenCalledTimes(1);
    expect(el.textContent).toContain("Bukit Timah Campus"); // location
    expect(el.textContent).toContain("150 pax"); // capacity
    expect(el.textContent).toContain("Theatre"); // supported layout
    expect(el.textContent).toContain("Projector"); // facility
    expect(el.textContent).toContain("Wheelchair access"); // accessibility
    expect(el.textContent).toMatch(/08:00.22:00/); // operating hours
    expect(el.textContent).toContain("bookings may run back to back"); // turnaround
  });

  it("says when the profile was last updated and by whom (AC2)", async () => {
    const el = await openProfile();

    expect(el.textContent).toContain("Last updated");
    expect(el.textContent).toContain("Val Staff");
    // 02:30Z on 18 Sep is 10:30 in Singapore. The month abbreviation is left to
    // the platform's ICU data ("Sep" or "Sept"), which is not what is under test.
    expect(el.textContent).toMatch(/18 Sept? 2026, 10:30/);
  });

  it("reports an unrecorded editor instead of inventing one (AC2)", async () => {
    venuesApi.get.mockResolvedValue({ ...PROFILE, updated_by: null });
    const el = await openProfile();

    expect(el.textContent).toContain("Not recorded");
    expect(el.textContent).not.toContain("Val Staff");
  });

  it("summarises upcoming confirmed and tentative bookings, each naming its event (AC3)", async () => {
    const el = await openProfile();

    const summary = el.querySelector("[data-testid='upcoming-bookings']");
    expect(summary).toBeTruthy();
    expect(summary.textContent).toContain("Confirmed");
    expect(summary.textContent).toContain("Alumni Dinner");
    expect(summary.textContent).toContain("Tentative");
    expect(summary.textContent).toContain("Annual Town Hall");
    expect(summary.textContent).toContain("2 upcoming");
  });

  it("falls back to a short event reference when the booking has no event name", async () => {
    venuesApi.get.mockResolvedValue({
      ...PROFILE,
      upcoming_bookings: [
        { ...PROFILE.upcoming_bookings[0], event_name: null, event_id: "abcd1234-0000-4000-8000-000000000001" },
      ],
    });
    const el = await openProfile();

    expect(el.querySelector("[data-testid='upcoming-bookings']").textContent).toContain("Event ABCD1234");
  });

  it("states that nothing is booked rather than leaving the section blank", async () => {
    venuesApi.get.mockResolvedValue({ ...PROFILE, upcoming_bookings: [] });
    const el = await openProfile();

    expect(el.querySelector("[data-testid='upcoming-bookings']").textContent).toContain("No upcoming bookings");
  });
});
