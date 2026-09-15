import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { criteriaToParams, emptyCriteria, toSingaporeIso, useVenuesStore } from "@/stores/venues";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  venuesApi: { search: vi.fn(), get: vi.fn() },
}));

const HALL_A = { id: "v1", name: "Hall A", location: "Bukit Timah", capacity: 150, layouts: [], facilities: [], accessibility_features: [], opens_at: "08:00:00", closes_at: "22:00:00", is_active: true };
const HALL_B = { ...HALL_A, id: "v2", name: "Hall B" };

function searchResponse() {
  return {
    criteria: {},
    results: [
      { venue: HALL_A, availability: "available", excluded: false, reasons: [] },
      { venue: HALL_B, availability: "unavailable", excluded: true, reasons: [{ code: "held", message: "Held by another event 10 Oct 13:00–16:00" }] },
    ],
    included_count: 1,
    excluded_count: 1,
  };
}

function signedInStore() {
  setActivePinia(createPinia());
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = { id: "u1", role: "event_coordinator" };
  return useVenuesStore();
}

describe("venue search criteria", () => {
  it("builds Singapore-time ISO timestamps from date and time inputs", () => {
    expect(toSingaporeIso("2026-10-10", "14:00")).toBe("2026-10-10T14:00:00+08:00");
  });

  it("turns the form into query params, dropping what is unset", () => {
    const params = criteriaToParams({
      ...emptyCriteria(),
      date: "2026-10-10",
      startTime: "14:00",
      endTime: "17:00",
      minCapacity: "150",
      location: " Bukit ",
      layout: "theatre",
      facilities: ["projector", "wifi"],
      accessibility: ["wheelchair_access"],
    });

    expect(params).toEqual({
      starts_at: "2026-10-10T14:00:00+08:00",
      ends_at: "2026-10-10T17:00:00+08:00",
      min_capacity: 150,
      location: "Bukit",
      layout: "theatre",
      facilities: ["projector", "wifi"],
      accessibility: ["wheelchair_access"],
      include_excluded: true,
    });
  });

  it("sends only the toggle when the form is empty", () => {
    expect(criteriaToParams(emptyCriteria())).toEqual({ include_excluded: true });
  });
});

describe("venues store", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("splits results into included and excluded venues", async () => {
    const store = signedInStore();
    venuesApi.search.mockResolvedValue(searchResponse());

    await store.search();

    expect(venuesApi.search).toHaveBeenCalledWith({ include_excluded: true }, "access");
    expect(store.hasSearched).toBe(true);
    expect(store.includedResults.map((r) => r.venue.name)).toEqual(["Hall A"]);
    expect(store.excludedResults.map((r) => r.venue.name)).toEqual(["Hall B"]);
    expect(store.includedCount).toBe(1);
    expect(store.excludedCount).toBe(1);
    expect(store.error).toBeNull();
  });

  it("refuses a date without both times and does not call the API", async () => {
    const store = signedInStore();
    store.criteria.date = "2026-10-10";
    store.criteria.startTime = "14:00";

    await store.search();

    expect(venuesApi.search).not.toHaveBeenCalled();
    expect(store.fieldErrors.endTime).toBeTruthy();
  });

  it("refuses an end time at or before the start time", async () => {
    const store = signedInStore();
    store.criteria.date = "2026-10-10";
    store.criteria.startTime = "17:00";
    store.criteria.endTime = "14:00";

    await store.search();

    expect(venuesApi.search).not.toHaveBeenCalled();
    expect(store.fieldErrors.endTime).toBe("End time must be after start time.");
  });

  it("refuses a non-positive attendance figure", async () => {
    const store = signedInStore();
    store.criteria.minCapacity = "0";

    await store.search();

    expect(venuesApi.search).not.toHaveBeenCalled();
    expect(store.fieldErrors.minCapacity).toBeTruthy();
  });

  it("surfaces an API failure without clearing the previous results", async () => {
    const store = signedInStore();
    venuesApi.search.mockResolvedValueOnce(searchResponse());
    await store.search();
    venuesApi.search.mockRejectedValueOnce(new ApiError("The authentication service is temporarily unavailable.", 503));

    await store.search();

    expect(store.error).toBe("The authentication service is temporarily unavailable.");
    expect(store.includedResults).toHaveLength(1);
  });

  it("loads one venue's detail through the session", async () => {
    const store = signedInStore();
    venuesApi.get.mockResolvedValue({ ...HALL_A, upcoming_blocks: [], upcoming_bookings: [] });

    const venue = await store.fetchVenue("v1");

    expect(venuesApi.get).toHaveBeenCalledWith("v1", "access");
    expect(venue.name).toBe("Hall A");
    expect(store.selectedVenue.id).toBe("v1");
  });

  it("reports a missing venue", async () => {
    const store = signedInStore();
    venuesApi.get.mockRejectedValue(new ApiError("Venue not found.", 404));

    await expect(store.fetchVenue("nope")).rejects.toThrow();

    expect(store.selectedVenue).toBeNull();
    expect(store.error).toBe("Venue not found.");
  });
});
