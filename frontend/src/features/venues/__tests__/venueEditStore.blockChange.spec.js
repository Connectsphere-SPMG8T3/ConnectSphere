import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useVenueEditStore } from "@/features/venues/venueEditStore";
import { venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  venuesApi: { changeBlock: vi.fn() },
}));

const PAYLOAD = { action: "end_now", ends_at: null, note: "Fixed" };

describe("useVenueEditStore.changeBlock (SCRUM-54)", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    const auth = useAuthStore();
    auth.token = "access-token";
    auth.profile = { id: "staff-1", role: "venue_staff", full_name: "Val Staff" };
  });

  it("sends the change and keeps the changed block and the bookings it freed", async () => {
    const response = { block: { id: "blk-1", status: "ended_early" }, restorable: [{ booking_id: "b1" }] };
    venuesApi.changeBlock.mockResolvedValue(response);
    const store = useVenueEditStore();

    await store.changeBlock("venue-1", "blk-1", PAYLOAD);

    expect(venuesApi.changeBlock).toHaveBeenCalledWith("venue-1", "blk-1", PAYLOAD, "access-token");
    expect(store.blockChangeResult).toEqual(response);
    expect(store.isSaving).toBe(false);
  });

  it("keeps the error for the dialog, clears any earlier result and rethrows", async () => {
    venuesApi.changeBlock.mockRejectedValue(new Error("This block has already ended, so it can't be changed."));
    const store = useVenueEditStore();
    store.blockChangeResult = { block: { id: "old" }, restorable: [] };

    await expect(store.changeBlock("venue-1", "blk-1", PAYLOAD)).rejects.toThrow("already ended");

    expect(store.error).toBe("This block has already ended, so it can't be changed.");
    expect(store.blockChangeResult).toBeNull();
  });

  it("clearBlockChange forgets the last result and error", () => {
    const store = useVenueEditStore();
    store.blockChangeResult = { block: { id: "old" }, restorable: [] };
    store.error = "x";
    store.clearBlockChange();
    expect(store.blockChangeResult).toBeNull();
    expect(store.error).toBeNull();
  });
});
