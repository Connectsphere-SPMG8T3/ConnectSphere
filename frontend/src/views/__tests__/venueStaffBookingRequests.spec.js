import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VenueStaffBookingRequestsView from "@/views/venues/VenueStaffBookingRequestsView.vue";
import { venueBookingsApi, venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  venuesApi: { venueStaffDashboard: vi.fn() },
  venueBookingsApi: { changeExpiry: vi.fn() },
}));

const PAYLOAD = {
  venues: [
    { id: "venue-1", name: "Grand Ballroom", location: "Marina Bay", is_active: true },
    { id: "venue-2", name: "Rooftop Terrace", location: "Orchard Road", is_active: true },
  ],
  booking_requests: [
    {
      id: "booking-held",
      event_id: "event-1",
      venue_id: "venue-1",
      venue_name: "Grand Ballroom",
      status: "held",
      requested_at: "2026-09-03T10:30:00+08:00",
      expires_at: "2026-09-20T01:00:00Z",
      period: { starts_at: "2026-10-10T13:00:00+08:00", ends_at: "2026-10-10T16:00:00+08:00" },
    },
    {
      id: "booking-approved",
      event_id: "event-2",
      venue_id: "venue-2",
      venue_name: "Rooftop Terrace",
      status: "approved",
      requested_at: "2026-09-04T10:30:00+08:00",
      period: { starts_at: "2026-10-13T09:00:00+08:00", ends_at: "2026-10-13T12:00:00+08:00" },
    },
    {
      id: "booking-rejected",
      event_id: "event-3",
      venue_id: "venue-1",
      venue_name: "Grand Ballroom",
      status: "rejected",
      requested_at: "2026-09-05T10:30:00+08:00",
      period: { starts_at: "2026-10-15T09:00:00+08:00", ends_at: "2026-10-15T12:00:00+08:00" },
    },
  ],
  pending_holds: [],
  re_review_bookings: [],
  blocks: [],
};

async function mountPage() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = { id: "staff-1", role: "venue_staff", full_name: "Priya Nair" };
  authStore.sessionVerified = true;
  const { default: router } = await import("@/router");
  await router.push("/dashboard/venue-staff/requests");
  await router.isReady();
  const el = document.createElement("div");
  document.body.appendChild(el);
  createApp(VenueStaffBookingRequestsView).use(pinia).use(router).mount(el);
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
    await nextTick();
  }
  return { el, router };
}

describe("VenueStaffBookingRequestsView", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    localStorage.clear();
    vi.clearAllMocks();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-19T12:00:00+08:00"));
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);
  });

  it("loads as a dedicated venue-staff page and links back to the dashboard", async () => {
    const { el, router } = await mountPage();

    expect(router.currentRoute.value.name).toBe("dashboard-venue-staff-requests");
    expect(el.querySelector("h1").textContent).toContain("Booking requests");
    expect(el.querySelector('a[href="/dashboard/venue-staff"]')).toBeTruthy();
  });

  it("renders each request across the full page width", async () => {
    const { el } = await mountPage();

    expect(el.querySelector("#booking-requests-list").className).not.toContain("xl:grid-cols-2");
  });

  it("uses status colours on request cards like the event request cards", async () => {
    const { el } = await mountPage();
    const status = el.querySelectorAll("select")[0];

    status.value = "all";
    status.dispatchEvent(new Event("change"));
    await nextTick();

    expect(el.querySelector('[data-request-status="held"] .bg-bauhaus-yellow')).toBeTruthy();
    expect(el.querySelector('[data-request-status="approved"] .bg-bauhaus-blue')).toBeTruthy();
    expect(el.querySelector('[data-request-status="rejected"] .bg-bauhaus-red')).toBeTruthy();
  });

  it("offers one unrestricted status option instead of duplicate Any and All choices", async () => {
    const { el } = await mountPage();
    const [status, venue] = el.querySelectorAll("select");

    expect([...status.options].map((option) => option.textContent.trim())).not.toContain("Any");
    expect([...status.options].map((option) => option.textContent.trim())).toContain("All statuses");
    expect([...venue.options].map((option) => option.textContent.trim())).not.toContain("Any");
    expect([...venue.options].map((option) => option.textContent.trim())).toContain("All venues");
  });

  it("shows pending requests by default and all loaded history when All statuses is selected", async () => {
    const { el } = await mountPage();
    const [status] = el.querySelectorAll("select");

    expect(el.querySelectorAll('a[href^="/bookings/"]')).toHaveLength(1);
    expect(status.value).toBe("pending");

    status.value = "all";
    status.dispatchEvent(new Event("change"));
    await nextTick();

    expect(el.querySelectorAll('a[href^="/bookings/"]')).toHaveLength(3);
  });

  it("filters resolved requests by status and venue", async () => {
    const { el } = await mountPage();
    const [status, venue] = el.querySelectorAll("select");

    status.value = "approved";
    status.dispatchEvent(new Event("change"));
    await nextTick();
    expect(el.querySelectorAll('a[href^="/bookings/"]')).toHaveLength(1);
    expect(el.querySelector('a[href="/bookings/booking-approved"]')).toBeTruthy();

    venue.value = "venue-1";
    venue.dispatchEvent(new Event("change"));
    await nextTick();
    expect(el.querySelectorAll('a[href^="/bookings/"]')).toHaveLength(0);
  });

  it("keeps hold expiry controls on the dedicated page", async () => {
    const { el } = await mountPage();

    expect(el.querySelector('[data-testid="hold-expiry-booking-held"]').textContent).toContain("Expires 20 Sep 2026, 09:00");
    el.querySelector('[data-testid="hold-expiry-booking-held"]').parentElement.querySelector("button").click();
    await nextTick();
    expect(el.querySelector('input[type="datetime-local"]')).toBeTruthy();
  });
});
