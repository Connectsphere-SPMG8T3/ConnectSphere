import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, eventsApi, venueBookingsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// SCRUM-85: the assigned coordinator cancels a venue booking from the event page.
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: {
    safetyDecisions: vi.fn().mockResolvedValue([]), get: vi.fn(), history: vi.fn(), listComments: vi.fn(),
    addComment: vi.fn(),
  },
  venueBookingsApi: { cancel: vi.fn() },
}));

const BOOKING = { id: "booking-1", venue_id: "v1", venue_name: "Innovation Lab", status: "approved", expires_at: null };

function eventResponse(overrides = {}) {
  return {
    id: "event-1", name: "Partner Summit", status: "confirmed", version: 3,
    event_timezone: "Asia/Singapore", purpose: "Quarterly partner meeting", description: null,
    starts_at: "2099-11-12T02:00:00Z", ends_at: "2099-11-12T04:00:00Z", expected_attendance: 12,
    layout_preference: "boardroom", facilities_required: [], accessibility_needs: null,
    preliminary_equipment_needs: null, coordinator_id: "c1", organiser_id: "o1",
    venue_booking: BOOKING, venue_bookings: [BOOKING], ...overrides,
  };
}

const mountedApps = [];

async function mountView(response) {
  eventsApi.get.mockResolvedValue(response);
  eventsApi.history.mockResolvedValue({ entries: [] });
  eventsApi.listComments.mockResolvedValue({ comments: [] });
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "c1", full_name: "Marcus Lim", role: "event_coordinator" };
  auth.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "coordinator-event", params: { id: response.id } });
  const { default: View } = await import("@/views/events/CoordinatorEventView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await vi.waitFor(() => expect(el.textContent).toContain(response.name));
  await nextTick();
  return el;
}

function button(root, label) {
  return root.querySelector(`button[aria-label="${label}"]`);
}

function dialog() {
  return document.body.querySelector('[role="dialog"]');
}

function dialogButton(text) {
  return [...dialog().querySelectorAll("button")].find((b) => b.textContent.trim() === text);
}

describe("SCRUM-85 coordinator cancels a venue booking", () => {
  beforeEach(() => vi.clearAllMocks());

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("asks first, says a Confirmed event goes back to Planning, then cancels and offers another venue", async () => {
    const el = await mountView(eventResponse());
    venueBookingsApi.cancel.mockResolvedValue({ ...BOOKING, status: "cancelled" });
    eventsApi.get.mockResolvedValue(eventResponse({ status: "planning", venue_booking: null, venue_bookings: [] }));

    button(el, "Cancel booking: Innovation Lab").click();
    await nextTick();
    expect(dialog().textContent).toContain("Cancel this venue booking?");
    expect(dialog().textContent).toContain("Innovation Lab will be free for this event's time again");
    expect(dialog().textContent).toContain("goes back to Planning");
    expect(venueBookingsApi.cancel).not.toHaveBeenCalled();

    dialogButton("Cancel booking").click();

    await vi.waitFor(() => expect(venueBookingsApi.cancel).toHaveBeenCalledWith("booking-1", "access"));
    await vi.waitFor(() => expect(el.textContent).toContain("No venue requested yet"));
    expect(button(el, "Cancel booking: Innovation Lab")).toBeNull();
  });

  it("doesn't mention Planning for an event already in it (AC8)", async () => {
    const el = await mountView(eventResponse({ status: "planning", venue_booking: { ...BOOKING, status: "held" } }));

    button(el, "Cancel booking: Innovation Lab").click();
    await nextTick();

    expect(dialog().textContent).not.toContain("Planning");
  });

  it("keeps the booking when the coordinator changes their mind", async () => {
    const el = await mountView(eventResponse());

    button(el, "Cancel booking: Innovation Lab").click();
    await nextTick();
    dialogButton("Keep booking").click();
    await nextTick();

    expect(dialog()).toBeNull();
    expect(venueBookingsApi.cancel).not.toHaveBeenCalled();
  });

  it("shows why the API refused (AC3)", async () => {
    const el = await mountView(eventResponse());
    venueBookingsApi.cancel.mockRejectedValue(new ApiError("Only a Held or Approved booking can be cancelled.", 409));

    button(el, "Cancel booking: Innovation Lab").click();
    await nextTick();
    dialogButton("Cancel booking").click();

    await vi.waitFor(() => expect(el.querySelector('[role="alert"]')?.textContent)
      .toContain("Only a Held or Approved booking can be cancelled."));
  });

  it("offers to cancel a pending replacement beside the affected booking (AC1)", async () => {
    const affected = { ...BOOKING, flag: "affected", flag_reason: "Venue unavailable: Maintenance" };
    const replacement = { id: "booking-2", venue_id: "v2", venue_name: "Heritage Hall", status: "held",
      replaces_booking_id: "booking-1", expires_at: null };
    const el = await mountView(eventResponse({ status: "planning", venue_booking: affected,
      venue_bookings: [affected, replacement] }));

    expect(button(el, "Cancel booking: Innovation Lab")).not.toBeNull();
    expect(button(el, "Cancel replacement request: Heritage Hall")).not.toBeNull();
  });

  it.each([
    ["an expired hold", { venue_booking: { ...BOOKING, status: "expired", expires_at: "2099-11-01T00:00:00Z" } }],
    ["a cancelled event", { status: "cancelled" }],
    ["an event that has started", { starts_at: "2020-01-01T00:00:00Z" }],
  ])("offers nothing for %s (AC3, AC10)", async (_, overrides) => {
    const el = await mountView(eventResponse(overrides));

    expect(el.querySelector('[data-testid="cancel-booking-actions"]')).toBeNull();
  });

  it("offers each space's booking on its own card (AC7)", async () => {
    const plenary = { ...BOOKING, event_space_request_id: "s1" };
    const breakout = { ...BOOKING, id: "booking-3", venue_name: "Heritage Hall", event_space_request_id: "s2" };
    const el = await mountView(eventResponse({
      venue_booking: plenary, venue_bookings: [plenary, breakout],
      spaces: [
        { id: "s1", label: "Plenary", expected_pax: 80, facilities_required: [] },
        { id: "s2", label: "Breakout", expected_pax: 20, facilities_required: [] },
      ],
    }));

    expect(el.querySelectorAll('[data-testid="cancel-booking-actions"]')).toHaveLength(2);
    expect(button(el, "Cancel booking: Heritage Hall")).not.toBeNull();
  });
});
