import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { venueToEditForm } from "@/features/venues/venueProfile";
import { useVenueEditStore } from "@/features/venues/venueEditStore";
import { venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  venuesApi: { get: vi.fn(), history: vi.fn(), update: vi.fn(), deactivate: vi.fn(), reactivate: vi.fn() },
}));

const VENUE = {
  id: "venue-1",
  name: "Hall A",
  location: "Bukit Timah Campus",
  capacity: 150,
  layouts: [{ layout: "theatre", capacity_for_layout: null }],
  facilities: ["projector"],
  accessibility_features: [],
  opens_at: "08:00:00",
  closes_at: "22:00:00",
  description: null,
  version: 3,
};

function signedInVenueStaff() {
  const auth = useAuthStore();
  auth.token = "access-token";
  auth.profile = { id: "staff-1", role: "venue_staff", full_name: "Val Staff" };
}

describe("useVenueEditStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    signedInVenueStaff();
  });

  it("loads the venue by id", async () => {
    venuesApi.get.mockResolvedValue(VENUE);
    const store = useVenueEditStore();

    await store.load("venue-1");

    expect(venuesApi.get).toHaveBeenCalledWith("venue-1", "access-token");
    expect(store.venue).toEqual(VENUE);
    expect(store.isLoading).toBe(false);
  });

  it("ignores a stale load response that resolves after a newer request", async () => {
    let resolveA;
    let resolveB;
    venuesApi.get
      .mockImplementationOnce(() => new Promise((resolve) => { resolveA = resolve; }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveB = resolve; }));
    const store = useVenueEditStore();
    const VENUE_B = { ...VENUE, id: "venue-2", name: "Hall B" };

    const pendingA = store.load("venue-1");
    const pendingB = store.load("venue-2");

    // B (the newer request) resolves first...
    resolveB(VENUE_B);
    await pendingB;
    // ...then A (the older, now-stale request) resolves last.
    resolveA(VENUE);
    await pendingA;

    expect(store.venue).toEqual(VENUE_B);
  });

  it("saves directly when the API reports no warnings", async () => {
    venuesApi.get.mockResolvedValue(VENUE);
    venuesApi.update.mockResolvedValue({ saved: true, venue: { ...VENUE, capacity: 130 }, warnings: [] });
    const store = useVenueEditStore();
    await store.load("venue-1");

    const saved = await store.submit(venueToEditForm({ ...VENUE, capacity: 130 }));

    expect(saved).toBe(true);
    expect(store.venue.capacity).toBe(130);
    expect(store.warnings).toEqual([]);
  });

  it("returns false and keeps the warnings without writing when the API withholds the save", async () => {
    venuesApi.get.mockResolvedValue(VENUE);
    const warning = { booking_id: "b1", event_id: "e1", event_name: "Annual Gala", reasons: ["Capacity..."] };
    venuesApi.update.mockResolvedValue({ saved: false, venue: null, warnings: [warning] });
    const store = useVenueEditStore();
    await store.load("venue-1");

    const saved = await store.submit(venueToEditForm({ ...VENUE, capacity: 100 }));

    expect(saved).toBe(false);
    expect(store.warnings).toEqual([warning]);
    expect(store.venue).toEqual(VENUE);
  });

  it("confirms past the warning by sending confirm:true", async () => {
    venuesApi.get.mockResolvedValue(VENUE);
    venuesApi.update.mockResolvedValue({ saved: true, venue: { ...VENUE, capacity: 100 }, warnings: [] });
    const store = useVenueEditStore();
    await store.load("venue-1");

    await store.submit(venueToEditForm({ ...VENUE, capacity: 100 }), { confirm: true });

    expect(venuesApi.update).toHaveBeenCalledWith("venue-1", expect.objectContaining({ confirm: true }), "access-token");
  });

  it("surfaces a conflict error without touching the loaded venue", async () => {
    venuesApi.get.mockResolvedValue(VENUE);
    venuesApi.update.mockRejectedValue(new Error("This venue was updated by someone else. Reload."));
    const store = useVenueEditStore();
    await store.load("venue-1");

    await expect(store.submit(venueToEditForm(VENUE))).rejects.toThrow("updated by someone else");
    expect(store.error).toMatch(/updated by someone else/);
    expect(store.venue).toEqual(VENUE);
  });

  it("loads the edit history", async () => {
    const entry = { id: "h1", before: { capacity: 150 }, after: { capacity: 100 }, at: "2026-10-06T10:00:00Z", actor: null };
    venuesApi.history.mockResolvedValue({ entries: [entry] });
    const store = useVenueEditStore();
    store.venueId = "venue-1";

    const history = await store.loadHistory("venue-1");

    expect(history).toEqual([entry]);
    expect(store.history).toEqual([entry]);
  });

  describe("deactivate and reactivate (SCRUM-64)", () => {
    it("previews affected bookings without saving", async () => {
      venuesApi.deactivate.mockResolvedValue({ saved: false, affected: [{ booking_id: "b1", event_name: "Gala" }] });
      const store = useVenueEditStore();
      const saved = await store.deactivate("venue-1", { reason: "permanently_closed", note: "  ", version: 3 });
      expect(saved).toBe(false);
      expect(store.affected).toHaveLength(1);
      expect(venuesApi.deactivate).toHaveBeenCalledWith(
        "venue-1", { reason: "permanently_closed", note: null, version: 3, confirm: false }, "access-token");
    });

    it("saves on confirm and clears the preview", async () => {
      venuesApi.deactivate.mockResolvedValue({ saved: true, venue: { id: "venue-1", is_active: false }, affected: [] });
      const store = useVenueEditStore();
      expect(await store.deactivate("venue-1", { reason: "other", note: " Lease ended ", version: 3 }, { confirm: true })).toBe(true);
      expect(venuesApi.deactivate.mock.calls[0][1]).toMatchObject({ note: "Lease ended", confirm: true });
      expect(store.affected).toEqual([]);
      expect(store.isSaving).toBe(false);
    });

    it("keeps a deactivate error for the modal and rethrows", async () => {
      venuesApi.deactivate.mockRejectedValue(new Error("This venue is already inactive."));
      const store = useVenueEditStore();
      await expect(store.deactivate("venue-1", { reason: "permanently_closed", note: null, version: 3 }, { confirm: true }))
        .rejects.toThrow("This venue is already inactive.");
      expect(store.error).toBe("This venue is already inactive.");
      expect(store.isSaving).toBe(false);
    });

    it("reactivates with the loaded version", async () => {
      venuesApi.reactivate.mockResolvedValue({ id: "venue-1", is_active: true });
      const store = useVenueEditStore();
      await store.reactivate("venue-1", 4);
      expect(venuesApi.reactivate).toHaveBeenCalledWith("venue-1", { version: 4 }, "access-token");
    });
  });
});
