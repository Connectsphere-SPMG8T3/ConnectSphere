import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useVenueCalendarStore } from "@/features/venues/venueCalendarStore";
import { venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// SCRUM-57: the venue, view and period on screen, and what occupies it.

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  venuesApi: { calendar: vi.fn() },
}));

const TODAY = new Date("2031-03-12T02:00:00Z"); // Wed 12 Mar 2031 SGT

function calendar(venueId, entries = []) {
  return { venue: { id: venueId, name: venueId, is_active: true }, entries, venues: [] };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("useVenueCalendarStore (SCRUM-57)", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    const auth = useAuthStore();
    auth.token = "access-token";
    auth.profile = { id: "staff-1", role: "venue_staff", full_name: "Val Staff" };
  });

  it("opens a venue on this week and asks for the week's range", async () => {
    venuesApi.calendar.mockResolvedValue(calendar("v1"));
    const store = useVenueCalendarStore();

    await store.open("v1", { today: TODAY });

    expect(store.view).toBe("week");
    expect(store.anchorKey).toBe("2031-03-12");
    const [venueId, range, token] = venuesApi.calendar.mock.calls[0];
    expect(venueId).toBe("v1");
    expect(range.startsAt.toISOString()).toBe("2031-03-09T16:00:00.000Z");
    expect(range.endsAt.toISOString()).toBe("2031-03-16T16:00:00.000Z");
    expect(token).toBe("access-token");
    expect(store.calendar).toEqual(calendar("v1"));
    expect(store.isLoading).toBe(false);
    expect(store.hasLoaded).toBe(true);
  });

  it("switching view or stepping asks again for the new range (AC1, AC4)", async () => {
    venuesApi.calendar.mockResolvedValue(calendar("v1"));
    const store = useVenueCalendarStore();
    await store.open("v1", { today: TODAY });

    await store.setView("day");
    expect(venuesApi.calendar.mock.calls[1][1].startsAt.toISOString()).toBe("2031-03-11T16:00:00.000Z");

    await store.step(1);
    expect(store.anchorKey).toBe("2031-03-13");

    await store.setView("month");
    expect(venuesApi.calendar.mock.calls[3][1].startsAt.toISOString()).toBe("2031-02-23T16:00:00.000Z");
    await store.step(-1);
    expect(store.anchorKey).toBe("2031-02-01");

    await store.goToToday(TODAY);
    expect(store.anchorKey).toBe("2031-03-12");
    expect(venuesApi.calendar).toHaveBeenCalledTimes(6);
  });

  it("choosing the same view again asks nothing", async () => {
    venuesApi.calendar.mockResolvedValue(calendar("v1"));
    const store = useVenueCalendarStore();
    await store.open("v1", { today: TODAY });
    await store.setView("week");
    expect(venuesApi.calendar).toHaveBeenCalledTimes(1);
  });

  it("refresh asks again for the same venue and period, keeping what is shown meanwhile", async () => {
    venuesApi.calendar.mockResolvedValueOnce(calendar("v1", [{ id: "old" }]));
    const store = useVenueCalendarStore();
    await store.open("v1", { today: TODAY });
    const later = deferred();
    venuesApi.calendar.mockReturnValueOnce(later.promise);

    const refreshing = store.refresh();
    expect(store.calendar.entries).toEqual([{ id: "old" }]);
    expect(store.isLoading).toBe(true);
    later.resolve(calendar("v1", [{ id: "new" }]));
    await refreshing;

    expect(venuesApi.calendar.mock.calls[1][1]).toEqual(venuesApi.calendar.mock.calls[0][1]);
    expect(store.calendar.entries).toEqual([{ id: "new" }]);
  });

  it("switching venue keeps the view and period, and a slower answer for the old venue is ignored", async () => {
    const slow = deferred();
    venuesApi.calendar.mockReturnValueOnce(slow.promise).mockResolvedValueOnce(calendar("v2"));
    const store = useVenueCalendarStore();

    const first = store.open("v1", { today: TODAY });
    await store.open("v2");
    slow.resolve(calendar("v1"));
    await first;

    expect(store.venueId).toBe("v2");
    expect(store.anchorKey).toBe("2031-03-12");
    expect(store.calendar.venue.id).toBe("v2");
  });

  it("keeps the error and clears the calendar for a venue that can't be read", async () => {
    venuesApi.calendar.mockRejectedValue(new Error("Venue not found."));
    const store = useVenueCalendarStore();
    store.calendar = calendar("old");

    await store.open("v1", { today: TODAY });

    expect(store.error).toBe("Venue not found.");
    expect(store.calendar).toBeNull();
    expect(store.isLoading).toBe(false);
  });

  it("does nothing without a venue", async () => {
    const store = useVenueCalendarStore();
    await store.refresh();
    expect(venuesApi.calendar).not.toHaveBeenCalled();
  });
});
