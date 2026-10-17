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

  it("keeps what refused the request, and forgets it on the next one (SCRUM-21)", async () => {
    const store = signedInCoordinator();
    const conflict = {
      kind: "booking", event_name: "Alumni Night", block_reason: null,
      starts_at: "2031-04-07T01:30:00Z", ends_at: "2031-04-07T04:45:00Z",
    };
    venueBookingsApi.request.mockRejectedValueOnce(
      new ApiError("Venue already held for this time by another event.", 409, null, conflict),
    );

    await expect(store.requestForSpace("space-1", "v1", "")).rejects.toThrow("Venue already held");
    expect(store.conflict).toEqual(conflict);

    venueBookingsApi.request.mockResolvedValueOnce(BOOKING);
    await store.request("event-1", "v2", "");
    expect(store.conflict).toBeNull();
    expect(store.error).toBeNull();
  });

  it("has no conflict when the request failed without one", async () => {
    const store = signedInCoordinator();
    venueBookingsApi.request.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(store.requestForSpace("space-1", "v1", "")).rejects.toThrow("Failed to fetch");
    await expect(store.request("event-1", "v1", "")).rejects.toThrow("Failed to fetch");
    expect(store.conflict).toBeNull();
  });

  it("requests a venue for a selected space with a trimmed note", async () => {
    const store = signedInCoordinator();
    venueBookingsApi.request.mockResolvedValue({ ...BOOKING, event_space_request_id: "space-1" });

    const booking = await store.requestForSpace("space-1", "v1", "  Breakout room  ");

    expect(venueBookingsApi.request).toHaveBeenCalledWith({
      event_space_request_id: "space-1",
      venue_id: "v1",
      note: "Breakout room",
    }, "access-token");
    expect(booking.event_space_request_id).toBe("space-1");
    expect(store.error).toBeNull();
    expect(store.isRequesting).toBe(false);
  });

  it("sends a null note for a space booking when the note is blank", async () => {
    const store = signedInCoordinator();
    venueBookingsApi.request.mockResolvedValue({ ...BOOKING, event_space_request_id: "space-1", note: null });

    await store.requestForSpace("space-1", "v1", "   ");

    expect(venueBookingsApi.request).toHaveBeenCalledWith({
      event_space_request_id: "space-1",
      venue_id: "v1",
      note: null,
    }, "access-token");
  });

  it("surfaces a space-booking refusal and clears the requesting state", async () => {
    const store = signedInCoordinator();
    venueBookingsApi.request.mockRejectedValue(new ApiError("Space already has a venue.", 409));

    await expect(store.requestForSpace("space-1", "v1", "")).rejects.toThrow("Space already has a venue.");

    expect(store.error).toBe("Space already has a venue.");
    expect(store.isRequesting).toBe(false);
    expect(useAuthStore().token).toBe("access-token");
  });
});
