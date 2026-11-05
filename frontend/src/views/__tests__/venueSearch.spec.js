import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, eventsApi, venueBookingsApi, venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { useVenuesStore } from "@/features/venues/venueSearchStore";
import { criteriaFromEvent, criteriaFromSpace, venuePanelState } from "@/features/venues/bookingRequest";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { get: vi.fn() },
  venueBookingsApi: { request: vi.fn() },
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

// Apps from earlier tests would otherwise still react to the shared router.
const mountedApps = [];

async function mountView(component, { route, role = "event_coordinator" } = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = { id: "u1", role };
  authStore.sessionVerified = true;
  const { default: router } = await import("@/router");
  await router.push(route ?? { name: "venue-search", query: {} });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(component).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
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
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
    vi.clearAllMocks();
    eventsApi.get.mockReset();
    venueBookingsApi.request.mockReset();
    venuesApi.search.mockResolvedValue(RESPONSE);
  });

  it("loads the selected space requirements and requests a venue for that space", async () => {
    const event = {
      id: "event-1",
      name: "Partner Summit",
      status: "planning",
      event_timezone: "Asia/Singapore",
      starts_at: "2026-10-10T06:00:00Z",
      ends_at: "2026-10-10T09:00:00Z",
      expected_attendance: 100,
      layout_preference: "theatre",
      facilities_required: ["projector"],
      spaces: [{
        id: "space-1",
        label: "Breakout room",
        expected_pax: 20,
        layout_preference: "classroom",
        facilities_required: ["whiteboard"],
      }],
      venue_bookings: [],
    };
    eventsApi.get.mockResolvedValue(event);
    venueBookingsApi.request.mockResolvedValue({ id: "booking-1" });
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el, venuesStore } = await mountView(VenueSearchView, {
      route: { name: "venue-search", query: { event: event.id, space: "space-1" } },
    });

    await vi.waitFor(() => expect(el.textContent).toContain("Space: Breakout room"));
    expect(eventsApi.get).toHaveBeenCalledWith(event.id, "access");
    expect(venuesStore.criteria).toMatchObject({
      date: "2026-10-10",
      startTime: "14:00",
      endTime: "17:00",
      minCapacity: 20,
      layout: "classroom",
      facilities: ["whiteboard"],
    });

    el.querySelector('[aria-label="Request Hall A"]').click();
    await settle();
    const note = document.querySelector("#request-venue-note");
    note.value = "Breakout room setup";
    note.dispatchEvent(new Event("input", { bubbles: true }));
    await settle();
    document.querySelector('[aria-label="Request venue"]').click();

    await vi.waitFor(() => expect(venueBookingsApi.request).toHaveBeenCalledWith({
      event_space_request_id: "space-1",
      venue_id: HALL_A.id,
      note: "Breakout room setup",
    }, "access"));
  });

  it("keeps the legacy event-scoped request flow when no space is selected", async () => {
    const event = {
      id: "event-legacy",
      name: "Single-space event",
      status: "planning",
      event_timezone: "Asia/Singapore",
      starts_at: "2026-10-10T06:00:00Z",
      ends_at: "2026-10-10T09:00:00Z",
      expected_attendance: 80,
      layout_preference: "theatre",
      facilities_required: ["projector"],
    };
    eventsApi.get.mockResolvedValue(event);
    venueBookingsApi.request.mockResolvedValue({ id: "legacy-booking" });
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el, venuesStore } = await mountView(VenueSearchView, {
      route: { name: "venue-search", query: { event: event.id } },
    });

    await vi.waitFor(() => expect(el.textContent).toContain("Single-space event"));
    expect(venuesStore.criteria).toMatchObject({ minCapacity: 80, layout: "theatre", facilities: ["projector"] });
    expect(el.textContent).not.toContain("Space:");

    el.querySelector('[aria-label="Request Hall A"]').click();
    await settle();
    document.querySelector('[aria-label="Request venue"]').click();

    await vi.waitFor(() => expect(venueBookingsApi.request).toHaveBeenCalledWith({
      event_id: "event-legacy",
      venue_id: HALL_A.id,
      note: null,
    }, "access"));
  });

  describe("replacing an affected booking (CR-95 AC4)", () => {
    const AFFECTED = {
      id: "booking-affected", event_space_request_id: null, venue_id: "old-venue", venue_name: "Seminar Room 1",
      status: "approved", flag: "affected", flag_reason: "Venue unavailable: Maintenance",
    };
    const affectedEvent = (status = "confirmed") => ({
      id: "event-affected",
      name: "Partner Summit",
      status,
      event_timezone: "Asia/Singapore",
      starts_at: "2026-10-10T06:00:00Z",
      ends_at: "2026-10-10T09:00:00Z",
      expected_attendance: 80,
      layout_preference: "theatre",
      facilities_required: ["projector"],
      venue_bookings: [AFFECTED],
    });

    it("requests a venue for the affected booking and says the event goes back to planning", async () => {
      eventsApi.get.mockResolvedValue(affectedEvent());
      venueBookingsApi.request.mockResolvedValue({ id: "new-booking" });
      const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
      const { el } = await mountView(VenueSearchView, {
        route: { name: "venue-search", query: { event: "event-affected", replaces: AFFECTED.id } },
      });

      await vi.waitFor(() => expect(el.textContent).toContain("Partner Summit"));
      el.querySelector('[aria-label="Request Hall A"]').click();
      await settle();

      const dialog = document.querySelector('[role="dialog"]');
      expect(dialog.textContent).toContain("replaces Seminar Room 1");
      expect(dialog.textContent).toContain("back to Planning");
      document.querySelector('[aria-label="Request venue"]').click();

      await vi.waitFor(() => expect(venueBookingsApi.request).toHaveBeenCalledWith({
        event_id: "event-affected", venue_id: HALL_A.id, note: null, replaces_booking_id: AFFECTED.id,
      }, "access"));
    });

    it("does not say the event goes back to planning when it is already there", async () => {
      eventsApi.get.mockResolvedValue(affectedEvent("planning"));
      const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
      const { el } = await mountView(VenueSearchView, {
        route: { name: "venue-search", query: { event: "event-affected", replaces: AFFECTED.id } },
      });

      await vi.waitFor(() => expect(el.textContent).toContain("Partner Summit"));
      el.querySelector('[aria-label="Request Hall A"]').click();
      await settle();

      const dialog = document.querySelector('[role="dialog"]');
      expect(dialog.textContent).toContain("replaces Seminar Room 1");
      expect(dialog.textContent).not.toContain("back to Planning");
    });

    it.each([
      ["no booking is named", {}],
      ["the named booking is not the affected one", { replaces: "booking-other" }],
    ])("offers no request when %s", async (_label, extra) => {
      eventsApi.get.mockResolvedValue(affectedEvent());
      const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
      const { el } = await mountView(VenueSearchView, {
        route: { name: "venue-search", query: { event: "event-affected", ...extra } },
      });

      await vi.waitFor(() => expect(el.textContent).toContain("Partner Summit"));
      expect(el.querySelector('[aria-label="Request Hall A"]')).toBeNull();
    });

    it("requests a replacement for a Safety-rejected booking (D52)", async () => {
      const rejected = { ...AFFECTED, id: "booking-rejected", flag: "safety_rejected", flag_reason: "Exits blocked" };
      eventsApi.get.mockResolvedValue({ ...affectedEvent("planning"), venue_bookings: [rejected] });
      venueBookingsApi.request.mockResolvedValue({ id: "new-booking" });
      const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
      const { el } = await mountView(VenueSearchView, {
        route: { name: "venue-search", query: { event: "event-affected", replaces: rejected.id } },
      });

      await vi.waitFor(() => expect(el.textContent).toContain("Partner Summit"));
      el.querySelector('[aria-label="Request Hall A"]').click();
      await settle();

      const dialog = document.querySelector('[role="dialog"]');
      expect(dialog.textContent).toContain("replaces Seminar Room 1");
      expect(dialog.textContent).not.toContain("back to Planning");
      document.querySelector('[aria-label="Request venue"]').click();
      await vi.waitFor(() => expect(venueBookingsApi.request).toHaveBeenCalledWith({
        event_id: "event-affected", venue_id: HALL_A.id, note: null, replaces_booking_id: rejected.id,
      }, "access"));
    });

    it("offers no request for a Safety-rejected booking that already has a replacement", async () => {
      const rejected = { ...AFFECTED, id: "booking-rejected", flag: "safety_rejected", flag_reason: "Exits blocked" };
      const pending = { ...AFFECTED, id: "booking-new", flag: null, status: "held", replaces_booking_id: rejected.id };
      eventsApi.get.mockResolvedValue({ ...affectedEvent("planning"), venue_bookings: [rejected, pending] });
      const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
      const { el } = await mountView(VenueSearchView, {
        route: { name: "venue-search", query: { event: "event-affected", replaces: rejected.id } },
      });

      await vi.waitFor(() => expect(el.textContent).toContain("Partner Summit"));
      expect(el.querySelector('[aria-label="Request Hall A"]')).toBeNull();
    });
  });

  it("keeps the selected-space request dialog open and shows a booking refusal", async () => {
    const event = {
      id: "event-1",
      name: "Partner Summit",
      status: "planning",
      event_timezone: "Asia/Singapore",
      starts_at: "2026-10-10T06:00:00Z",
      ends_at: "2026-10-10T09:00:00Z",
      spaces: [{ id: "space-1", label: "Breakout room", expected_pax: 20, layout_preference: "classroom", facilities_required: [] }],
    };
    eventsApi.get.mockResolvedValue(event);
    venueBookingsApi.request.mockRejectedValue(new Error("Space already has a venue."));
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el } = await mountView(VenueSearchView, {
      route: { name: "venue-search", query: { event: event.id, space: "space-1" } },
    });
    await vi.waitFor(() => expect(el.textContent).toContain("Space: Breakout room"));

    el.querySelector('[aria-label="Request Hall A"]').click();
    await settle();
    document.querySelector('[aria-label="Request venue"]').click();

    await vi.waitFor(() => expect(document.querySelector('[role="alert"]').textContent).toContain("Space already has a venue."));
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();
  });

  it("hides venue requests when the selected space already has an active booking", async () => {
    const event = {
      id: "event-booked",
      name: "Booked event",
      status: "planning",
      event_timezone: "Asia/Singapore",
      starts_at: "2026-10-10T06:00:00Z",
      ends_at: "2026-10-10T09:00:00Z",
      spaces: [{ id: "space-booked", label: "Main venue", expected_pax: 40, layout_preference: "theatre", facilities_required: [] }],
      venue_bookings: [{ id: "booking-1", event_space_request_id: "space-booked", status: "held" }],
    };
    eventsApi.get.mockResolvedValue(event);
    venuesApi.search.mockResolvedValue(RESPONSE);
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el } = await mountView(VenueSearchView, {
      route: { name: "venue-search", query: { event: event.id, space: "space-booked" } },
    });

    await vi.waitFor(() => expect(el.textContent).toContain("Main venue"));
    expect(el.textContent).toContain("This space already has a venue.");
    expect(el.querySelector('[aria-label="Request Hall A"]')).toBeNull();
  });

  it("shows a failed event read in the selected-space search context", async () => {
    eventsApi.get.mockRejectedValue(new Error("Event could not be loaded."));
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el } = await mountView(VenueSearchView, {
      route: { name: "venue-search", query: { event: "missing-event", space: "missing-space" } },
    });

    await vi.waitFor(() => expect(el.querySelector('[role="alert"]')?.textContent).toContain("Event could not be loaded."));
    expect(el.querySelector('[aria-label="Request Hall A"]')).toBeNull();
  });

  it("hides the selected-space booking action when the search period is changed", async () => {
    const event = {
      id: "event-period",
      name: "Partner Summit",
      status: "planning",
      event_timezone: "Asia/Singapore",
      starts_at: "2026-10-10T06:00:00Z",
      ends_at: "2026-10-10T09:00:00Z",
      spaces: [{ id: "space-period", label: "Breakout room", expected_pax: 20, layout_preference: "classroom", facilities_required: [] }],
    };
    eventsApi.get.mockResolvedValue(event);
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el, venuesStore } = await mountView(VenueSearchView, {
      route: { name: "venue-search", query: { event: event.id, space: "space-period" } },
    });
    await vi.waitFor(() => expect(el.textContent).toContain("Space: Breakout room"));

    venuesStore.criteria.endTime = "18:00";
    await nextTick();

    expect(el.textContent).toContain("Search the selected space's date and times to request a venue for it.");
    expect(el.querySelector('[aria-label="Request Hall A"]')).toBeNull();
  });

  it("puts the page title above the filter card, which it labels, instead of a separate header card", async () => {
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el } = await mountView(VenueSearchView);
    await settle();

    const heading = el.querySelector("h1");
    expect(heading.textContent).toContain("Find a venue");
    const filterCard = el.querySelector("[data-testid='venue-filters']");
    expect(filterCard.contains(heading)).toBe(false);
    expect(filterCard.getAttribute("aria-labelledby")).toBe(heading.id);
    expect(filterCard.querySelector("form")).toBeTruthy();
    expect(el.textContent).not.toContain("Venue catalogue");
    // Grey like the coordinator's Events filter card, with no explanatory paragraph.
    expect(filterCard.className).toContain("bg-muted");
    expect(el.textContent).not.toContain("Every filter you set is strict");
  });

  it("lists matching venues first, then excluded ones greyed out with their reasons", async () => {
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el } = await mountView(VenueSearchView);
    await settle();

    expect(venuesApi.search).toHaveBeenCalledTimes(1);
    expect(el.textContent).toContain("1 matching venue");
    expect(el.textContent).toContain("Theatre (120)");
    expect(el.textContent).toContain("Add a date and time to check availability");
    expect(el.querySelector('button[role="switch"]')).toBeNull();

    const cards = [...el.querySelectorAll('[data-testid="venue-result"]')];
    expect(cards).toHaveLength(2);
    expect(cards[0].textContent).toContain("Hall A");
    expect(cards[0].classList.contains("bg-muted")).toBe(false);
    expect(cards[1].textContent).toContain("Hall B");
    expect(cards[1].classList.contains("bg-muted")).toBe(true);
    expect(cards[1].textContent).toContain("Capacity 100 is below the required 150");
    expect(cards[1].textContent).toContain("Held by another event 10 Oct 13:00–16:00");
    expect(cards[1].textContent).toContain("Unavailable");
    expect(el.textContent).toContain("Greyed-out venues don't meet every requirement");
  });

  it("keeps inactive venues out of the list (VC-R1) but greys out other excluded ones", async () => {
    const HALL_D = { ...HALL_A, id: "b0000000-0000-4000-8000-000000000004", name: "Hall D", is_active: false };
    venuesApi.search.mockResolvedValue({
      ...RESPONSE,
      results: [
        ...RESPONSE.results,
        {
          venue: HALL_D,
          availability: "unavailable",
          excluded: true,
          reasons: [{ code: "inactive", message: "Hall D is inactive" }],
        },
      ],
      excluded_count: 2,
    });
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el } = await mountView(VenueSearchView);
    await settle();

    const names = [...el.querySelectorAll('[data-testid="venue-result"] h3')].map((h) => h.textContent.trim());
    expect(names).toEqual(["Hall A", "Hall B"]);
    expect(el.textContent).not.toContain("Hall D");
  });

  it("sorts the matching venues from a Sort by control and keeps excluded ones last", async () => {
    const HALL_C = { ...HALL_A, id: "b0000000-0000-4000-8000-000000000003", name: "Hall C", capacity: 300 };
    venuesApi.search.mockResolvedValue({
      ...RESPONSE,
      results: [
        { venue: HALL_C, availability: "available", excluded: false, reasons: [] },
        ...RESPONSE.results,
      ],
      included_count: 2,
    });
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el } = await mountView(VenueSearchView);
    await settle();

    const order = () => [...el.querySelectorAll('[data-testid="venue-result"] h3')].map((h) => h.textContent.trim());
    expect(order()).toEqual(["Hall A", "Hall C", "Hall B"]);

    const sort = el.querySelector('select[aria-label="Sort venues by"]');
    expect(sort).toBeTruthy();
    sort.value = "capacity-desc";
    sort.dispatchEvent(new Event("change"));
    await settle();

    expect(order()).toEqual(["Hall C", "Hall A", "Hall B"]);
  });

  it("offers no Sort by control for a single match", async () => {
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el } = await mountView(VenueSearchView);
    await settle();

    expect(el.querySelector('select[aria-label="Sort venues by"]')).toBeNull();
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

describe("event and space booking criteria", () => {
  it("prefills search and booking context with the selected space window", async () => {
    const event = {
      id: "event-space-window",
      name: "Partner Summit",
      status: "planning",
      event_timezone: "Asia/Singapore",
      starts_at: "2026-10-20T01:00:00Z",
      ends_at: "2026-10-20T10:00:00Z",
      spaces: [{
        id: "space-afternoon",
        label: "Afternoon breakout",
        expected_pax: 20,
        layout_preference: "classroom",
        facilities_required: [],
        starts_at: "2026-10-20T05:00:00Z",
        ends_at: "2026-10-20T08:00:00Z",
      }],
    };
    eventsApi.get.mockResolvedValue(event);
    venuesApi.search.mockResolvedValue(RESPONSE);
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el, venuesStore } = await mountView(VenueSearchView, {
      route: { name: "venue-search", query: { event: event.id, space: "space-afternoon" } },
    });

    await vi.waitFor(() => expect(el.textContent).toContain("Space: Afternoon breakout"));
    expect(venuesStore.criteria).toMatchObject({ date: "2026-10-20", startTime: "13:00", endTime: "16:00" });
    expect(el.textContent).toContain("1:00 pm");
    expect(el.textContent).toContain("4:00 pm");
    expect(el.textContent).not.toContain("10:00 am");
  });

  it("overrides event-level capacity, layout and facilities with the selected space", () => {
    const event = {
      starts_at: "2026-10-10T06:00:00Z",
      ends_at: "2026-10-10T09:00:00Z",
      expected_attendance: 100,
      layout_preference: "theatre",
      facilities_required: ["projector"],
    };
    const criteria = criteriaFromSpace({
      expected_pax: 20,
      layout_preference: "classroom",
      facilities_required: ["whiteboard"],
    }, event);

    expect(criteria).toMatchObject({
      date: "2026-10-10",
      startTime: "14:00",
      endTime: "17:00",
      minCapacity: 20,
      layout: "classroom",
      facilities: ["whiteboard"],
    });
  });

  it("handles missing events and uses the booking belonging to the selected space", () => {
    expect(criteriaFromEvent({ starts_at: null, ends_at: null })).toMatchObject({ facilities: [] });
    expect(criteriaFromSpace(null, null)).toMatchObject({ facilities: [] });
    expect(venuePanelState(null)).toEqual({ kind: "none" });
    expect(venuePanelState({
      status: "planning",
      venue_bookings: [{ id: "booking-1", event_space_request_id: "space-1" }],
    }, { id: "space-1" })).toEqual({
      kind: "booked",
      booking: { id: "booking-1", event_space_request_id: "space-1" },
    });
    expect(venuePanelState({ status: "planning", venue_bookings: [] }, { id: "space-2" })).toEqual({ kind: "can-request" });
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

  async function openProfile(role) {
    const { default: VenueDetailView } = await import("@/views/venues/VenueDetailView.vue");
    const { el } = await mountView(VenueDetailView, { route: { name: "venue-detail", params: { id: HALL_A.id } }, role });
    await settle();
    return el;
  }

  const tab = (el, label) => [...el.querySelectorAll("[role='tab']")].find((b) => b.textContent.includes(label));

  async function openTab(el, label) {
    tab(el, label).click();
    await settle();
    return el.querySelector("[role='tabpanel']");
  }

  it("shows the whole profile from one request, across its tabs (AC1)", async () => {
    const el = await openProfile();

    expect(venuesApi.get).toHaveBeenCalledTimes(1);
    // Always visible, outside the tabs.
    expect(el.textContent).toContain("Hall A");
    expect(el.textContent).toContain("Bukit Timah Campus");

    const capacity = el.querySelector("[role='tabpanel']");
    expect(capacity.textContent).toContain("150 pax");
    expect(capacity.textContent).toMatch(/08:00.22:00/);
    expect(capacity.textContent).toContain("Default turnaround");
    expect(capacity.textContent).toContain("0 minutes");
    expect(capacity.textContent).toContain("Theatre");

    const facilities = await openTab(el, "Facilities & access");
    expect(facilities.textContent).toContain("Projector");
    expect(facilities.textContent).toContain("Wheelchair access");
  });

  it("opens on Capacity & hours and switches panels on click", async () => {
    const el = await openProfile();

    expect(tab(el, "Capacity & hours").getAttribute("aria-selected")).toBe("true");
    expect(el.querySelector("[role='tabpanel']").id).toBe("panel-capacity");

    await openTab(el, "Blocks");

    expect(tab(el, "Capacity & hours").getAttribute("aria-selected")).toBe("false");
    expect(tab(el, "Blocks").getAttribute("aria-selected")).toBe("true");
    // Only the selected panel is mounted.
    expect(el.querySelectorAll("[role='tabpanel']")).toHaveLength(1);
    expect(el.querySelector("[role='tabpanel']").id).toBe("panel-blocks");
  });

  it("counts what is behind the time-based tabs, so a closed tab never implies it is empty", async () => {
    const el = await openProfile();

    expect(tab(el, "Upcoming bookings").textContent).toContain("2");
    expect(tab(el, "Blocks").textContent).toContain("1");
    // Every venue has capacity and hours; a "0" there would read as "none recorded".
    expect(tab(el, "Capacity & hours").textContent).not.toMatch(/·/);
  });

  it("moves between tabs with the arrow keys", async () => {
    const el = await openProfile();

    el.querySelector("[role='tablist']").dispatchEvent(
      new window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true }),
    );
    await settle();

    expect(el.querySelector("[role='tabpanel']").id).toBe("panel-facilities");
  });

  it("renders the venue's blocks in Singapore time", async () => {
    const el = await openProfile();
    const blocks = await openTab(el, "Blocks");

    expect(venuesApi.get).toHaveBeenCalledWith(HALL_A.id, "access");
    expect(blocks.textContent).toContain("Maintenance");
    expect(blocks.textContent).toContain("Air-con servicing");
    // 00:00Z is 08:00 in Singapore.
    expect(blocks.textContent).toMatch(/08:00/);
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

  const statusSelect = (el) => el.querySelector("select[aria-label='Booking status']");
  const statusOption = (el, label) => [...statusSelect(el).options].find((o) => o.textContent.includes(label));
  const chooseStatus = async (el, label) => {
    const select = statusSelect(el);
    select.value = statusOption(el, label).value;
    select.dispatchEvent(new Event("change"));
    await settle();
  };

  it("summarises upcoming bookings, each naming its event and status (AC3)", async () => {
    const el = await openProfile();
    const summary = await openTab(el, "Upcoming bookings");

    // The total is stated once, above the Status list, so it is never hidden.
    expect(summary.textContent).toContain("2 upcoming");
    // Opens on every booking, tentative holds included, so nothing confirmed is hidden (AC3).
    expect(statusSelect(el).selectedOptions[0].textContent).toContain("All statuses");
    expect(summary.textContent).toContain("Annual Town Hall");
    expect(summary.textContent).toContain("Alumni Dinner");
    // 05:00Z is 13:00 in Singapore.
    expect(summary.textContent).toMatch(/13:00/);

    await chooseStatus(el, "Pending");
    expect(summary.textContent).toContain("Annual Town Hall");
    expect(summary.textContent).not.toContain("Alumni Dinner");

    await chooseStatus(el, "Approved");
    expect(summary.textContent).toContain("Alumni Dinner");
    expect(summary.textContent).not.toContain("Annual Town Hall");
  });

  it("lists the bookings soonest first", async () => {
    const el = await openProfile();
    const summary = await openTab(el, "Upcoming bookings");

    const [first, second] = [...PROFILE.upcoming_bookings].sort(
      (a, b) => new Date(a.period.starts_at) - new Date(b.period.starts_at),
    );
    const text = summary.textContent;
    expect(text.indexOf(first.event_name)).toBeLessThan(text.indexOf(second.event_name));
  });

  it("opens on All statuses whether or not a hold is waiting", async () => {
    venuesApi.get.mockResolvedValue({ ...PROFILE, upcoming_bookings: [PROFILE.upcoming_bookings[0]] });
    let el = await openProfile();
    let summary = await openTab(el, "Upcoming bookings");
    expect(statusSelect(el).selectedOptions[0].textContent).toContain("All statuses");
    expect(summary.textContent).toContain("Annual Town Hall");

    document.body.innerHTML = "";
    venuesApi.get.mockResolvedValue({ ...PROFILE, upcoming_bookings: [PROFILE.upcoming_bookings[1]] });
    el = await openProfile();
    summary = await openTab(el, "Upcoming bookings");
    expect(statusSelect(el).selectedOptions[0].textContent).toContain("All statuses");
    expect(summary.textContent).toContain("Alumni Dinner");
  });

  it("links each upcoming booking to its own booking page for venue staff, labelled with its status", async () => {
    const el = await openProfile("venue_staff");
    const summary = await openTab(el, "Upcoming bookings");

    const approved = summary.querySelector('a[href="/bookings/d2"]');
    expect(approved.textContent).toContain("Alumni Dinner");
    expect(approved.textContent).toContain("Approved");
    expect(approved.textContent).toContain("View booking");
    const pending = summary.querySelector('a[href="/bookings/d1"]');
    expect(pending.textContent).toContain("Annual Town Hall");
    expect(pending.textContent).toContain("Pending");
  });

  it("shows the bookings to a coordinator without links to booking pages they may not open", async () => {
    const el = await openProfile("event_coordinator");
    const summary = await openTab(el, "Upcoming bookings");

    expect(summary.textContent).toContain("Annual Town Hall");
    expect(summary.textContent).toContain("Pending");
    expect(summary.querySelector('a[href^="/bookings/"]')).toBeNull();
    expect(summary.textContent).not.toContain("View booking");
  });

  it("says None rather than going blank on a status with no bookings", async () => {
    venuesApi.get.mockResolvedValue({ ...PROFILE, upcoming_bookings: [PROFILE.upcoming_bookings[1]] });
    const el = await openProfile();
    const summary = await openTab(el, "Upcoming bookings");

    await chooseStatus(el, "Pending");

    expect(summary.textContent).toContain("None.");
  });

  it("always offers All statuses first, then every status an upcoming booking can have, each with its count (D88)", async () => {
    const el = await openProfile();
    await openTab(el, "Upcoming bookings");

    expect([...statusSelect(el).options].map((o) => o.textContent.trim())).toEqual([
      "All statuses (2)",
      "Pending (1)",
      "Re-review (0)",
      "Approved (1)",
    ]);
  });

  it("falls back to a short event reference when the booking has no event name", async () => {
    venuesApi.get.mockResolvedValue({
      ...PROFILE,
      upcoming_bookings: [
        { ...PROFILE.upcoming_bookings[0], event_name: null, event_id: "abcd1234-0000-4000-8000-000000000001" },
      ],
    });
    const el = await openProfile();

    expect((await openTab(el, "Upcoming bookings")).textContent).toContain("Event ABCD1234");
  });

  it("states that nothing is booked rather than leaving the section blank", async () => {
    venuesApi.get.mockResolvedValue({ ...PROFILE, upcoming_bookings: [] });
    const el = await openProfile();

    expect((await openTab(el, "Upcoming bookings")).textContent).toContain("No upcoming bookings");
  });

  it("shows a schematic of each supported layout instead of stock imagery (VC-R8)", async () => {
    const el = await openProfile();
    const gallery = el.querySelector("[aria-roledescription='carousel']");

    expect(el.querySelector("img")).toBeNull();
    expect(gallery.querySelector("svg")).toBeTruthy();
    expect(gallery.textContent).toContain("Theatre · 120 pax");
    expect(gallery.textContent).toContain("Schematic arrangement");
    expect(gallery.querySelector("svg title").textContent).toContain("not this room's floor plan");
  });

  it("says so when the capacity shown is the venue figure rather than measured for that layout (VS-R6)", async () => {
    venuesApi.get.mockResolvedValue({ ...PROFILE, layouts: [{ layout: "theatre", capacity_for_layout: null }] });
    const el = await openProfile();
    const gallery = el.querySelector("[aria-roledescription='carousel']");

    expect(gallery.textContent).toContain("Theatre · 150 pax");
    expect(gallery.textContent).toContain("capacity is the venue figure");
  });

  it("leads with real photos once they exist, keeping the schematics after them", async () => {
    venuesApi.get.mockResolvedValue({
      ...PROFILE,
      photos: [
        { url: "https://example.test/a.jpg", caption: "From the stage" },
        { url: "https://example.test/b.jpg", caption: null },
      ],
    });
    const el = await openProfile();

    expect(el.textContent).toContain("1 of 3");
    expect(el.querySelector("img").getAttribute("src")).toBe("https://example.test/a.jpg");
    expect(el.querySelector("img").getAttribute("alt")).toBe("From the stage");

    const next = [...el.querySelectorAll("button")].find((b) => b.getAttribute("aria-label") === "Next slide");
    next.click();
    await settle();
    expect(el.querySelector("img").getAttribute("src")).toBe("https://example.test/b.jpg");
    // No caption on the second photo, so the alt text describes the position.
    expect(el.querySelector("img").getAttribute("alt")).toBe("Hall A, photo 2 of 3");

    // Third slide is the layout schematic.
    next.click();
    await settle();
    expect(el.querySelector("img")).toBeNull();
    expect(el.textContent).toContain("Theatre · 120 pax");

    // And it wraps back to the first photo.
    next.click();
    await settle();
    expect(el.querySelector("img").getAttribute("src")).toBe("https://example.test/a.jpg");
  });

  it("says there is nothing to show when the venue has neither photos nor layouts", async () => {
    venuesApi.get.mockResolvedValue({ ...PROFILE, layouts: [] });
    const el = await openProfile();

    expect(el.textContent).toContain("Nothing to show");
    expect(el.querySelector("[aria-roledescription='carousel']")).toBeNull();
  });
});

describe("VenueSearchView suitability (SCRUM-18)", () => {
  const EVENT = {
    id: "event-1",
    name: "Partner Summit",
    status: "planning",
    event_timezone: "Asia/Singapore",
    starts_at: "2026-10-10T06:00:00Z",
    ends_at: "2026-10-10T09:00:00Z",
    expected_attendance: 100,
    layout_preference: "theatre",
    facilities_required: ["projector"],
    spaces: [{ id: "space-1", label: "Breakout room", expected_pax: 20, layout_preference: "classroom", facilities_required: [] }],
    venue_bookings: [],
  };
  const SUITABILITY = {
    verdict: "suitable_with_warnings",
    reasons: [{ code: "outside_operating_hours", severity: "warning", message: "The booking's time falls outside the venue's operating hours (08:00–22:00)." }],
  };
  const WITH_SUITABILITY = {
    ...RESPONSE,
    results: [{ ...RESPONSE.results[0], suitability: SUITABILITY }, RESPONSE.results[1]],
  };

  beforeEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
    vi.clearAllMocks();
    eventsApi.get.mockReset();
    eventsApi.get.mockResolvedValue(EVENT);
    venuesApi.search.mockResolvedValue(WITH_SUITABILITY);
  });

  it("asks for the selected space's suitability and shows it on each result (AC9)", async () => {
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el } = await mountView(VenueSearchView, { route: { name: "venue-search", query: { event: EVENT.id, space: "space-1" } } });

    await vi.waitFor(() => expect(venuesApi.search).toHaveBeenCalled());
    expect(venuesApi.search.mock.calls.at(-1)[0]).toMatchObject({ event_id: "event-1", space_id: "space-1" });
    await vi.waitFor(() => expect(el.querySelector("[data-testid='suitability-badge']")?.textContent.trim()).toBe("Suitable with warnings"));
    expect(el.textContent).toContain("outside the venue's operating hours");
  });

  it("asks for the event's suitability when no space is selected", async () => {
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    await mountView(VenueSearchView, { route: { name: "venue-search", query: { event: EVENT.id } } });

    await vi.waitFor(() => expect(venuesApi.search).toHaveBeenCalled());
    const params = venuesApi.search.mock.calls.at(-1)[0];
    expect(params.event_id).toBe("event-1");
    expect(params).not.toHaveProperty("space_id");
  });

  it("carries the verdict into the request dialog (AC9)", async () => {
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el } = await mountView(VenueSearchView, { route: { name: "venue-search", query: { event: EVENT.id, space: "space-1" } } });
    await vi.waitFor(() => expect(el.querySelector('[aria-label="Request Hall A"]')).not.toBeNull());

    el.querySelector('[aria-label="Request Hall A"]').click();
    await settle();

    const dialog = document.querySelector("[role='dialog']");
    expect(dialog.querySelector("[data-testid='suitability-badge']").textContent.trim()).toBe("Suitable with warnings");
  });

  it("sends the acknowledgement with a request for a venue that has warnings (BR-R3)", async () => {
    venueBookingsApi.request.mockResolvedValue({ id: "booking-1" });
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el } = await mountView(VenueSearchView, { route: { name: "venue-search", query: { event: EVENT.id, space: "space-1" } } });
    await vi.waitFor(() => expect(el.querySelector('[aria-label="Request Hall A"]')).not.toBeNull());

    el.querySelector('[aria-label="Request Hall A"]').click();
    await settle();
    document.querySelector("[data-testid='acknowledge-warnings']").click();
    await settle();
    document.querySelector('[aria-label="Request venue"]').click();

    await vi.waitFor(() =>
      expect(venueBookingsApi.request).toHaveBeenCalledWith(
        { event_space_request_id: "space-1", venue_id: HALL_A.id, note: null, acknowledge_warnings: true },
        "access",
      ),
    );
  });

  it("drops the event context, and its verdicts, when the search is opened without one", async () => {
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    const { el } = await mountView(VenueSearchView, { route: { name: "venue-search", query: { event: EVENT.id } } });
    await vi.waitFor(() => expect(venuesApi.search).toHaveBeenCalled());
    venuesApi.search.mockClear();
    venuesApi.search.mockResolvedValue(RESPONSE);

    const { default: router } = await import("@/router");
    await router.push({ name: "venue-search", query: {} });
    await vi.waitFor(() => expect(venuesApi.search).toHaveBeenCalled());

    const params = venuesApi.search.mock.calls.at(-1)[0];
    expect(params).not.toHaveProperty("event_id");
    await vi.waitFor(() => expect(el.querySelector("[data-testid='suitability-badge']")).toBeNull());
  });

  it("searches without an event when the event could not be read", async () => {
    eventsApi.get.mockRejectedValue(new Error("Event not found."));
    const { default: VenueSearchView } = await import("@/views/venues/VenueSearchView.vue");
    await mountView(VenueSearchView, { route: { name: "venue-search", query: { event: EVENT.id } } });

    await vi.waitFor(() => expect(venuesApi.search).toHaveBeenCalled());
    expect(venuesApi.search.mock.calls.at(-1)[0]).not.toHaveProperty("event_id");
  });
});

describe("VenueSearchView reset and failure", () => {
  const view = async () => (await import("@/views/venues/VenueSearchView.vue")).default;

  beforeEach(() => {
    document.body.innerHTML = "";
    localStorage.clear();
    vi.clearAllMocks();
    venuesApi.search.mockResolvedValue({ results: [] });
  });

  it("clears the criteria and searches again", async () => {
    const { el, venuesStore } = await mountView(await view());
    await vi.waitFor(() => expect(venuesStore.isLoading).toBe(false));
    venuesStore.criteria.location = "Bukit Timah";
    await nextTick();
    venuesApi.search.mockClear();

    [...el.querySelectorAll("button")].find((node) => node.textContent.trim() === "Clear").click();
    await vi.waitFor(() => expect(venuesApi.search).toHaveBeenCalled());

    expect(venuesStore.criteria.location).toBe("");
  });

  it("shows why the search failed", async () => {
    venuesApi.search.mockRejectedValue(new ApiError("Service unavailable", 503));

    const { el } = await mountView(await view());

    await vi.waitFor(() => expect(el.querySelector('[role="alert"]').textContent).toContain("Service unavailable"));
  });
});
