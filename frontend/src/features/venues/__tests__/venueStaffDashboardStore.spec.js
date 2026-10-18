import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useVenueStaffDashboardStore } from "@/features/venues/venueStaffDashboardStore";
import { ApiError, venueBookingsApi, venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  venuesApi: { venueStaffDashboard: vi.fn() },
  venueBookingsApi: { changeExpiry: vi.fn() },
}));

const PAYLOAD = {
  generated_at: "2026-09-19T04:00:00Z",
  venues: [
    { id: "b-1", name: "Grand Ballroom", location: "Marina Bay", is_active: true },
    { id: "b-8", name: "Old Lecture Theatre", location: "Bukit Timah", is_active: false },
  ],
  pending_holds: [
    {
      id: "d-2",
      event_id: "e-102",
      event_name: null,
      venue_id: "b-1",
      venue_name: "Grand Ballroom",
      period: { starts_at: "2026-10-10T13:00:00+08:00", ends_at: "2026-10-10T16:00:00+08:00" },
      status: "held",
      requested_at: "2026-09-03T10:30:00+08:00",
      expires_at: "2026-09-22T09:00:00+08:00",
    },
    {
      id: "d-4",
      event_id: "e-104",
      event_name: null,
      venue_id: "b-8",
      venue_name: "Old Lecture Theatre",
      period: { starts_at: "2026-10-13T09:00:00+08:00", ends_at: "2026-10-13T12:00:00+08:00" },
      status: "held",
      requested_at: "2026-08-28T16:15:00+08:00",
      expires_at: "2026-09-20T09:00:00+08:00",
    },
  ],
  re_review_bookings: [
    {
      id: "d-5",
      event_id: "e-105",
      event_name: null,
      venue_id: "b-1",
      venue_name: "Grand Ballroom",
      period: { starts_at: "2026-10-12T09:00:00+08:00", ends_at: "2026-10-12T12:00:00+08:00" },
      status: "re_review",
      requested_at: "2026-09-10T11:45:00+08:00",
    },
  ],
  blocks: [
    {
      id: "c-3",
      venue_id: "b-1",
      venue_name: "Grand Ballroom",
      period: { starts_at: "2026-10-20T00:00:00+08:00", ends_at: "2026-10-22T00:00:00+08:00" },
      reason: "safety",
      notes: "Railing inspection.",
    },
  ],
};

function signedInVenueStaff() {
  const auth = useAuthStore();
  auth.token = "access-token";
  auth.profile = { id: "s1", role: "venue_staff", full_name: "Priya Nair" };
  return auth;
}

describe("venue staff dashboard store", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("loads the four lists and marks itself available", async () => {
    signedInVenueStaff();
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);
    const store = useVenueStaffDashboardStore();

    await store.load();

    expect(venuesApi.venueStaffDashboard).toHaveBeenCalledWith("access-token");
    expect(store.venues).toHaveLength(2);
    expect(store.pendingHolds).toHaveLength(2);
    expect(store.reReviewBookings).toHaveLength(1);
    expect(store.blocks).toHaveLength(1);
    expect(store.isAvailable).toBe(true);
    expect(store.hasSettled).toBe(true);
    expect(store.error).toBeNull();
  });

  it("holds the affected bookings the API lists, and none when it lists none (CR-95 AC9)", async () => {
    signedInVenueStaff();
    const affected = { id: "d-9", venue_name: "Grand Ballroom", status: "approved", flag: "affected" };
    venuesApi.venueStaffDashboard.mockResolvedValue({ ...PAYLOAD, affected_bookings: [affected] });
    const store = useVenueStaffDashboardStore();

    await store.load();
    expect(store.affectedBookings).toEqual([affected]);

    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);
    await store.load();
    expect(store.affectedBookings).toEqual([]);

    store.affectedBookings = [affected];
    store.reset();
    expect(store.affectedBookings).toEqual([]);
  });

  it("derives the tile counts from the lists", async () => {
    signedInVenueStaff();
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);
    const store = useVenueStaffDashboardStore();

    await store.load();

    expect(store.counts).toEqual({
      pendingHolds: 2,
      reReview: 1,
      blocks: 1,
      venuesTotal: 2,
      venuesActive: 1,
      venuesInactive: 1,
    });
  });

  it("orders holds soonest expiry first regardless of the order they arrived in", async () => {
    signedInVenueStaff();
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);
    const store = useVenueStaffDashboardStore();

    await store.load();

    expect(store.soonestExpiryHolds.map((h) => h.id)).toEqual(["d-4", "d-2"]);
  });

  it("flattens everything the calendar has to place", async () => {
    signedInVenueStaff();
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);
    const store = useVenueStaffDashboardStore();

    await store.load();

    expect(store.calendarItems.map((item) => item.kind)).toEqual(["block", "held", "held", "re_review"]);
  });

  it("derives venue statuses at a given instant", async () => {
    signedInVenueStaff();
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);
    const store = useVenueStaffDashboardStore();

    await store.load();

    const rows = store.venueStatuses(new Date("2026-10-21T00:00:00+08:00"));
    expect(rows.map((r) => [r.venue.name, r.status])).toEqual([
      ["Grand Ballroom", "blocked"],
      ["Old Lecture Theatre", "inactive"],
    ]);
  });

  it("stays quiet on a 404, which means the backend is older than this page", async () => {
    signedInVenueStaff();
    venuesApi.venueStaffDashboard.mockRejectedValue(new ApiError("Not Found", 404));
    const store = useVenueStaffDashboardStore();

    await store.load();

    expect(store.error).toBeNull();
    expect(store.isAvailable).toBe(false);
    expect(store.hasSettled).toBe(true);
    expect(store.venues).toEqual([]);
  });

  it("surfaces a server error instead of rendering an empty queue", async () => {
    // An outage that showed as "nothing to do" would be worse than an error.
    signedInVenueStaff();
    venuesApi.venueStaffDashboard.mockRejectedValue(new ApiError("Venue service unavailable", 503));
    const store = useVenueStaffDashboardStore();

    await store.load();

    expect(store.error).toBe("Venue service unavailable");
    expect(store.isAvailable).toBe(false);
    expect(store.pendingHolds).toEqual([]);
  });

  it("reports a network failure in plain words", async () => {
    signedInVenueStaff();
    venuesApi.venueStaffDashboard.mockRejectedValue(new TypeError("Failed to fetch"));
    const store = useVenueStaffDashboardStore();

    await store.load();

    expect(store.error).toBe("Unable to reach the server. Please try again.");
  });

  it("clears stale data when a later load fails", async () => {
    signedInVenueStaff();
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);
    const store = useVenueStaffDashboardStore();
    await store.load();

    venuesApi.venueStaffDashboard.mockRejectedValue(new ApiError("Boom", 500));
    await store.load();

    expect(store.pendingHolds).toEqual([]);
    expect(store.counts.pendingHolds).toBe(0);
    expect(store.error).toBe("Boom");
  });

  it("does not call the API without a session", async () => {
    const store = useVenueStaffDashboardStore();

    await store.load();

    expect(venuesApi.venueStaffDashboard).not.toHaveBeenCalled();
    expect(store.hasSettled).toBe(true);
  });

  it("withholds counts until the first load settles", () => {
    signedInVenueStaff();
    const store = useVenueStaffDashboardStore();

    expect(store.hasSettled).toBe(false);
    expect(store.counts.pendingHolds).toBe(0);
  });
});

describe("changing a hold's expiry (CR-99 AC2)", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("sends the new expiry, reloads the queue and reports success", async () => {
    signedInVenueStaff();
    venueBookingsApi.changeExpiry.mockResolvedValue({ id: "d-2", status: "held", expires_at: "2026-09-25T10:30:00Z" });
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);
    const store = useVenueStaffDashboardStore();

    const saved = await store.changeHoldExpiry("d-2", "2026-09-25T18:30:00+08:00");

    expect(saved).toBe(true);
    expect(venueBookingsApi.changeExpiry).toHaveBeenCalledWith(
      "d-2", { expires_at: "2026-09-25T18:30:00+08:00" }, "access-token",
    );
    expect(venuesApi.venueStaffDashboard).toHaveBeenCalledTimes(1);
    expect(store.expiryError).toBeNull();
    expect(store.isChangingExpiry).toBe(false);
  });

  it("shows the server's reason when the change is refused, and keeps the queue", async () => {
    signedInVenueStaff();
    venueBookingsApi.changeExpiry.mockRejectedValue(new ApiError("This hold has already expired.", 409));
    const store = useVenueStaffDashboardStore();

    const saved = await store.changeHoldExpiry("d-2", "2026-09-25T18:30:00+08:00");

    expect(saved).toBe(false);
    expect(store.expiryError).toBe("This hold has already expired.");
    expect(venuesApi.venueStaffDashboard).not.toHaveBeenCalled();
  });

  it("reports a network failure in plain words", async () => {
    signedInVenueStaff();
    venueBookingsApi.changeExpiry.mockRejectedValue(new TypeError("Failed to fetch"));
    const store = useVenueStaffDashboardStore();

    expect(await store.changeHoldExpiry("d-2", "2026-09-25T18:30:00+08:00")).toBe(false);
    expect(store.expiryError).toBe("Unable to reach the server. Please try again.");
  });

  it("refuses an incomplete pick without calling the API", async () => {
    signedInVenueStaff();
    const store = useVenueStaffDashboardStore();

    expect(await store.changeHoldExpiry("d-2", null)).toBe(false);
    expect(store.expiryError).toBe("Choose a date and time for the new expiry.");
    expect(venueBookingsApi.changeExpiry).not.toHaveBeenCalled();
  });
});
