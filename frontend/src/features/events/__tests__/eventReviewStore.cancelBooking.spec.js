// SCRUM-85: the coordinator's event page cancels one of its venue bookings and reads
// the event again, so a return to Planning (AC4) and a freed venue panel (AC2) show.
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useEventReviewStore } from "@/features/events/eventReviewStore";
import { ApiError, eventsApi, venueBookingsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  venueBookingsApi: { cancel: vi.fn() },
  eventsApi: { safetyDecisions: vi.fn().mockResolvedValue([]), get: vi.fn(), history: vi.fn() },
}));

const EVENT = { id: "event-1", name: "Partner Summit", status: "confirmed", version: 3 };

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
  const auth = useAuthStore();
  auth.token = "access-token";
  auth.profile = { id: "c1", role: "event_coordinator", full_name: "Marcus Lim" };
  eventsApi.history.mockResolvedValue({ entries: [] });
});

describe("useEventReviewStore.cancelBooking", () => {
  it("cancels the booking and shows the event as it now is", async () => {
    const store = useEventReviewStore();
    store.event = { ...EVENT };
    venueBookingsApi.cancel.mockResolvedValue({ id: "b1", status: "cancelled" });
    eventsApi.get.mockResolvedValue({ ...EVENT, status: "planning" });

    await store.cancelBooking("b1");

    expect(venueBookingsApi.cancel).toHaveBeenCalledWith("b1", "access-token");
    expect(store.event.status).toBe("planning");
    expect(store.error).toBeNull();
    expect(store.isActing).toBe(false);
  });

  it("cancels once when asked twice at the same time (AC9)", async () => {
    const store = useEventReviewStore();
    store.event = { ...EVENT };
    venueBookingsApi.cancel.mockResolvedValue({ id: "b1", status: "cancelled" });
    eventsApi.get.mockResolvedValue(EVENT);

    await Promise.all([store.cancelBooking("b1"), store.cancelBooking("b1")]);

    expect(venueBookingsApi.cancel).toHaveBeenCalledTimes(1);
  });

  it("shows why it was refused and reads the event again, so the panel is current (AC3)", async () => {
    const store = useEventReviewStore();
    store.event = { ...EVENT };
    venueBookingsApi.cancel.mockRejectedValue(new ApiError("Only a Held or Approved booking can be cancelled.", 409));
    eventsApi.get.mockResolvedValue({ ...EVENT, status: "planning" });

    await expect(store.cancelBooking("b1")).rejects.toThrow("Only a Held or Approved booking can be cancelled.");

    expect(eventsApi.get).toHaveBeenCalledWith(EVENT.id, "access-token");
    expect(store.event.status).toBe("planning");
    expect(store.error).toBe("Only a Held or Approved booking can be cancelled.");
    expect(store.isActing).toBe(false);
  });

  it("keeps the refusal when reading the event again fails too", async () => {
    const store = useEventReviewStore();
    store.event = { ...EVENT };
    venueBookingsApi.cancel.mockRejectedValue(new ApiError("Forbidden", 403));
    eventsApi.get.mockRejectedValue(new ApiError("Service unavailable", 503));

    await expect(store.cancelBooking("b1")).rejects.toThrow("Forbidden");

    expect(store.error).toBe("Forbidden");
    expect(store.event.status).toBe("confirmed");
  });
});
