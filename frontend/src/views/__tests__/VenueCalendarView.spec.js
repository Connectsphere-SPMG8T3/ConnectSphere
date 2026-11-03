import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useVenueCalendarStore } from "@/features/venues/venueCalendarStore";
import { venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import VenueCalendarView from "@/views/venues/VenueCalendarView.vue";

// SCRUM-57: the venue calendar page.

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  venuesApi: { calendar: vi.fn(), search: vi.fn() },
}));

const VENUES = [
  { id: "v1", name: "Hall A", is_active: true },
  { id: "v2", name: "Hall B", is_active: true },
];
const calendar = (venueId) => ({
  venue: VENUES.find((v) => v.id === venueId), timezone: "Asia/Singapore", entries: [], venues: VENUES,
});
const mounted = [];

async function flush() {
  // A router navigation settles over several promise hops.
  for (let i = 0; i < 3; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    await nextTick();
  }
}

async function mountView(path) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access-token";
  auth.profile = { id: "staff-1", role: "venue_staff", full_name: "Val Staff" };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/venue-calendar/:venueId?", name: "venue-calendar", component: VenueCalendarView },
      { path: "/venues/:id", name: "venue-detail", component: { render: () => null } },
      { path: "/bookings/:id", name: "booking-request", component: { render: () => null } },
    ],
  });
  await router.push(path);
  await router.isReady();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ template: "<RouterView />" }).use(pinia).use(router);
  app.mount(el);
  mounted.push(app);
  await flush();
  return { el, router, store: useVenueCalendarStore() };
}

describe("VenueCalendarView (SCRUM-57)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    venuesApi.calendar.mockImplementation(async (venueId) => calendar(venueId));
  });

  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("opens the venue named in the address and titles the page with it", async () => {
    const { el } = await mountView("/venue-calendar/v2");

    expect(venuesApi.calendar.mock.calls[0][0]).toBe("v2");
    expect(el.querySelector("h1").textContent).toContain("Hall B");
    expect(el.querySelector('a[href="/venues/v2"]').textContent).toContain("Venue profile");
    expect(venuesApi.search).not.toHaveBeenCalled();
  });

  it("with no venue named, opens the first active one", async () => {
    venuesApi.search.mockResolvedValue({
      results: [{ venue: { id: "v9" }, excluded: true }, { venue: { id: "v1" }, excluded: false }],
    });
    const { router } = await mountView("/venue-calendar");

    expect(router.currentRoute.value.params.venueId).toBe("v1");
    expect(venuesApi.calendar.mock.calls[0][0]).toBe("v1");
  });

  it("falls back to an excluded venue when none is active", async () => {
    venuesApi.search.mockResolvedValue({ results: [{ venue: { id: "v2" }, excluded: true }] });
    const { router } = await mountView("/venue-calendar");
    expect(router.currentRoute.value.params.venueId).toBe("v2");
  });

  it("says so when there are no venues at all", async () => {
    venuesApi.search.mockResolvedValue({});
    const { el } = await mountView("/venue-calendar");
    expect(el.textContent).toContain("No venues yet");
    expect(venuesApi.calendar).not.toHaveBeenCalled();
  });

  it("shows why the venues couldn't be listed", async () => {
    venuesApi.search.mockRejectedValue(new Error("Service unavailable."));
    const { el } = await mountView("/venue-calendar");
    expect(el.querySelector('[role="alert"]').textContent).toContain("Service unavailable.");
  });

  it("switching venue changes the address and loads that venue (AC1)", async () => {
    const { el, router } = await mountView("/venue-calendar/v1");
    const select = el.querySelector("select");
    select.value = "v2";
    select.dispatchEvent(new Event("change"));
    await flush();

    expect(router.currentRoute.value.params.venueId).toBe("v2");
    expect(venuesApi.calendar.mock.calls.at(-1)[0]).toBe("v2");
  });

  it("asks again when the tab is shown again, and not while hidden (AC4)", async () => {
    await mountView("/venue-calendar/v1");
    const visibility = vi.spyOn(document, "visibilityState", "get");

    visibility.mockReturnValue("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    visibility.mockReturnValue("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    await flush();

    expect(venuesApi.calendar).toHaveBeenCalledTimes(2);
    visibility.mockRestore();
  });

  it("Refresh asks again, and a day number opens the day view", async () => {
    const { el, store } = await mountView("/venue-calendar/v1");
    [...el.querySelectorAll("button")].find((b) => b.textContent.trim() === "Refresh").click();
    await flush();
    expect(venuesApi.calendar).toHaveBeenCalledTimes(2);

    [...el.querySelectorAll("button")].find((b) => b.textContent.trim() === "Month").click();
    await flush();
    el.querySelector('button[aria-label^="Open "]').click();
    await flush();
    expect(store.view).toBe("day");
    expect(venuesApi.calendar).toHaveBeenCalledTimes(4);
  });

  it("choosing the venue already shown does nothing", async () => {
    const { el, router } = await mountView("/venue-calendar/v1");
    const push = vi.spyOn(router, "push");
    const select = el.querySelector("select");
    select.value = "v1";
    select.dispatchEvent(new Event("change"));
    await flush();
    expect(push).not.toHaveBeenCalled();
  });

  it("moves its clock on each minute, so an expired hold stops showing (AC6)", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    vi.setSystemTime(new Date("2031-03-10T02:00:00Z"));
    venuesApi.calendar.mockImplementation(async (venueId) => ({
      ...calendar(venueId),
      entries: [{
        id: "d2", kind: "booking", type: "tentative", status: "held", event_id: "e1", event_name: "Workshop",
        period: { starts_at: "2031-03-12T06:00:00Z", ends_at: "2031-03-12T08:00:00Z" },
        occupied_period: { starts_at: "2031-03-12T06:00:00Z", ends_at: "2031-03-12T08:00:00Z" },
        setup_minutes: 0, turnaround_minutes: 0, expires_at: "2031-03-10T02:00:30Z",
      }],
    }));
    try {
      const { el } = await mountView("/venue-calendar/v1");
      expect(el.querySelector('[data-type="tentative"]')).not.toBeNull();

      vi.advanceTimersByTime(60_000);
      await flush();

      expect(el.querySelector('[data-type="tentative"]')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops its clock and listener when left", async () => {
    const remove = vi.spyOn(document, "removeEventListener");
    await mountView("/venue-calendar/v1");
    mounted.splice(0).forEach((app) => app.unmount());
    expect(remove).toHaveBeenCalledWith("visibilitychange", expect.any(Function));
    remove.mockRestore();
  });
});
