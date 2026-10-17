import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useBookingDecisionStore } from "@/features/venues/bookingDecisionStore";
import { ApiError, venueBookingsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  venueBookingsApi: { request: vi.fn(), get: vi.fn(), reject: vi.fn(), approve: vi.fn() },
}));

const HELD = { id: "b1", status: "held", venue_name: "Innovation Lab", decision: null, history: [] };
const REJECTED = {
  ...HELD, status: "rejected",
  decision: { reason: "Capacity exceeded", suggestion: null, decided_by_name: "Venue Staff", decided_at: "2031-03-01T02:00:00Z" },
};

function signedInVenueStaff() {
  setActivePinia(createPinia());
  const auth = useAuthStore();
  auth.token = "access-token";
  auth.refreshToken = "refresh-token";
  auth.profile = { id: "s1", role: "venue_staff" };
  return useBookingDecisionStore();
}

describe("useBookingDecisionStore (SCRUM-38)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads one booking request", async () => {
    const store = signedInVenueStaff();
    venueBookingsApi.get.mockResolvedValue(HELD);

    await store.load("b1");

    expect(venueBookingsApi.get).toHaveBeenCalledWith("b1", "access-token");
    expect(store.booking).toEqual(HELD);
    expect(store.isLoading).toBe(false);
    expect(store.loadError).toBeNull();
  });

  it("keeps the API's message when the booking can't be loaded", async () => {
    const store = signedInVenueStaff();
    venueBookingsApi.get.mockRejectedValue(new ApiError("Booking not found.", 404));

    await store.load("missing");

    expect(store.booking).toBeNull();
    expect(store.loadError).toBe("Booking not found.");
    expect(store.isLoading).toBe(false);
  });

  it("rejects with the trimmed reason and replaces the booking with the decided one", async () => {
    const store = signedInVenueStaff();
    store.booking = HELD;
    venueBookingsApi.reject.mockResolvedValue(REJECTED);

    const ok = await store.reject("b1", { reason: "  Capacity exceeded ", suggestion: " " });

    expect(ok).toBe(true);
    expect(venueBookingsApi.reject).toHaveBeenCalledWith(
      "b1", { reason: "Capacity exceeded", suggestion: null }, "access-token",
    );
    expect(store.booking).toEqual(REJECTED);
    expect(store.error).toBeNull();
    expect(store.isRejecting).toBe(false);
  });

  it("reloads and explains when the booking was decided elsewhere first (AC10)", async () => {
    const store = signedInVenueStaff();
    store.booking = HELD;
    venueBookingsApi.reject.mockRejectedValue(
      new ApiError("Only a held booking can be rejected. This one is approved.", 409),
    );
    venueBookingsApi.get.mockResolvedValue({ ...HELD, status: "approved" });

    const ok = await store.reject("b1", { reason: "Closed" });

    expect(ok).toBe(false);
    expect(store.error).toBe("Only a held booking can be rejected. This one is approved.");
    expect(store.conflict).toBe(true);
    expect(venueBookingsApi.get).toHaveBeenCalledWith("b1", "access-token");
    expect(store.booking.status).toBe("approved");
  });

  it("keeps the form's error when the API refuses the text", async () => {
    const store = signedInVenueStaff();
    store.booking = HELD;
    venueBookingsApi.reject.mockRejectedValue(new ApiError("Must be 1 to 1000 characters.", 422));

    const ok = await store.reject("b1", { reason: "x" });

    expect(ok).toBe(false);
    expect(store.error).toBe("Must be 1 to 1000 characters.");
    expect(store.conflict).toBe(false);
    expect(venueBookingsApi.get).not.toHaveBeenCalled();
    expect(store.booking).toEqual(HELD);
  });

  it("does nothing while a rejection is already being sent", async () => {
    const store = signedInVenueStaff();
    store.isRejecting = true;

    expect(await store.reject("b1", { reason: "Closed" })).toBe(false);
    expect(venueBookingsApi.reject).not.toHaveBeenCalled();
  });

  it("clears an earlier error when the next attempt starts", async () => {
    const store = signedInVenueStaff();
    store.error = "old";
    store.conflict = true;
    venueBookingsApi.reject.mockResolvedValue(REJECTED);

    await store.reject("b1", { reason: "Closed" });

    expect(store.error).toBeNull();
    expect(store.conflict).toBe(false);
  });
});

describe("useBookingDecisionStore approve (SCRUM-36)", () => {
  beforeEach(() => vi.clearAllMocks());

  const APPROVED = {
    ...HELD, status: "approved",
    history: [{ action: "approved", from_status: "held", to_status: "approved", actor_name: "Venue Staff",
      reason: null, suggestion: null, at: "2031-03-01T02:00:00Z" }],
  };

  it("AC2 approves and replaces the booking with the approved one", async () => {
    const store = signedInVenueStaff();
    store.booking = HELD;
    venueBookingsApi.approve.mockResolvedValue(APPROVED);

    const ok = await store.approve("b1");

    expect(ok).toBe(true);
    expect(venueBookingsApi.approve).toHaveBeenCalledWith("b1", "access-token");
    expect(store.booking).toEqual(APPROVED);
    expect(store.error).toBeNull();
    expect(store.isApproving).toBe(false);
  });

  it.each([
    "This hold has expired, so it can't be approved.",
    "Venue blocked for this time.",
    "This venue is inactive, so the booking can't be approved.",
    "Only a held booking can be approved. This one is already rejected.",
  ])("AC3, AC4, AC6, AC9 reloads and explains a refusal: %s", async (message) => {
    const store = signedInVenueStaff();
    store.booking = HELD;
    venueBookingsApi.approve.mockRejectedValue(new ApiError(message, 409));
    venueBookingsApi.get.mockResolvedValue({ ...HELD, status: "expired" });

    const ok = await store.approve("b1");

    expect(ok).toBe(false);
    expect(store.error).toBe(message);
    expect(store.conflict).toBe(true);
    expect(venueBookingsApi.get).toHaveBeenCalledWith("b1", "access-token");
    expect(store.booking.status).toBe("expired");
  });

  it("keeps the booking and reports an error that isn't a conflict", async () => {
    const store = signedInVenueStaff();
    store.booking = HELD;
    venueBookingsApi.approve.mockRejectedValue(new ApiError("Forbidden", 403));

    const ok = await store.approve("b1");

    expect(ok).toBe(false);
    expect(store.error).toBe("Forbidden");
    expect(store.conflict).toBe(false);
    expect(venueBookingsApi.get).not.toHaveBeenCalled();
    expect(store.booking).toEqual(HELD);
  });

  it("does nothing while any decision is already being sent", async () => {
    const store = signedInVenueStaff();
    store.isApproving = true;
    expect(await store.approve("b1")).toBe(false);
    store.isApproving = false;
    store.isRejecting = true;
    expect(await store.approve("b1")).toBe(false);
    expect(await store.reject("b1", { reason: "Closed" })).toBe(false);
    store.isRejecting = false;
    store.isApproving = true;
    expect(await store.reject("b1", { reason: "Closed" })).toBe(false);

    expect(venueBookingsApi.approve).not.toHaveBeenCalled();
    expect(venueBookingsApi.reject).not.toHaveBeenCalled();
  });
});
