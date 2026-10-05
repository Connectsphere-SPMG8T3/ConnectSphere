import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useVenueBookingStore } from "@/features/venues/venueBookingStore";
import { ApiError, venueBookingsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  venueBookingsApi: { request: vi.fn() },
}));

const BOOKING = { id: "b1", event_id: "event-1", venue_id: "v1", status: "held", note: "Early access" };

function signedInCoordinator() {
  setActivePinia(createPinia());
  const auth = useAuthStore();
  auth.token = "access-token";
  auth.refreshToken = "refresh-token";
  auth.profile = { id: "c1", role: "event_coordinator" };
  return useVenueBookingStore();
}

describe("useVenueBookingStore.request (SCRUM-19)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("requests the venue for the event with the trimmed note and returns the hold", async () => {
    const store = signedInCoordinator();
    venueBookingsApi.request.mockResolvedValue(BOOKING);

    const booking = await store.request("event-1", "v1", "  Early access  ");

    expect(venueBookingsApi.request).toHaveBeenCalledWith(
      { event_id: "event-1", venue_id: "v1", note: "Early access" }, "access-token",
    );
    expect(booking).toEqual(BOOKING);
    expect(store.error).toBeNull();
    expect(store.isRequesting).toBe(false);
  });

  it("sends no note when the coordinator left it blank", async () => {
    const store = signedInCoordinator();
    venueBookingsApi.request.mockResolvedValue({ ...BOOKING, note: null });

    await store.request("event-1", "v1", "   ");

    expect(venueBookingsApi.request).toHaveBeenCalledWith(
      { event_id: "event-1", venue_id: "v1", note: null }, "access-token",
    );
  });

  it("surfaces the API's refusal and keeps the session", async () => {
    const store = signedInCoordinator();
    venueBookingsApi.request.mockRejectedValue(
      new ApiError("Venue already held for this time by another event.", 409),
    );

    await expect(store.request("event-1", "v1", "")).rejects.toThrow("Venue already held");

    expect(store.error).toBe("Venue already held for this time by another event.");
    expect(store.isRequesting).toBe(false);
    // A 409 is a refusal, not a rejected session (isSessionRejected).
    expect(useAuthStore().token).toBe("access-token");
  });
});
