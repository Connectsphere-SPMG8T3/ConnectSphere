import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import VenueDetailView from "@/views/venues/VenueDetailView.vue";
import { venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// SCRUM-64: deactivate and reactivate from the venue profile page.
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  venuesApi: { search: vi.fn(), get: vi.fn(), history: vi.fn(), deactivate: vi.fn(), reactivate: vi.fn() },
}));

const VENUE_ID = "b0000000-0000-4000-8000-000000000001";
const ACTIVE = {
  id: VENUE_ID,
  name: "Hall A",
  location: "Bukit Timah Campus",
  capacity: 150,
  layouts: [{ layout: "theatre", capacity_for_layout: null }],
  facilities: [],
  accessibility_features: [],
  opens_at: "08:00:00",
  closes_at: "22:00:00",
  is_active: true,
  inactive_reason: null,
  inactive_note: null,
  description: null,
  updated_at: "2026-09-18T10:30:00+08:00",
  updated_by: null,
  version: 3,
  turnaround_minutes: 0,
  photos: [],
  upcoming_blocks: [],
  upcoming_bookings: [],
};
const INACTIVE = { ...ACTIVE, is_active: false, inactive_reason: "long_term_renovation", inactive_note: "Roof works", version: 4 };

const apps = [];

async function drain() {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
    await nextTick();
  }
}

async function mountView(role, venue) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = { id: "s1", role, full_name: "Val Staff" };
  authStore.sessionVerified = true;
  venuesApi.get.mockResolvedValue(venue);
  const { default: router } = await import("@/router");
  await router.push(`/venues/${VENUE_ID}`);
  await router.isReady();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(VenueDetailView).use(pinia).use(router);
  app.mount(el);
  apps.push(app);
  await drain();
  return el;
}

const button = (label) => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === label);

async function chooseReason(value) {
  const select = document.querySelector('[role="dialog"] select');
  select.value = value;
  select.dispatchEvent(new Event("change"));
  await nextTick();
}

describe("VenueDetailView: deactivation (SCRUM-64)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    apps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("CR-100 shows both defaults and the recorded safety facts", async () => {
    await mountView("event_coordinator", { ...ACTIVE, setup_minutes: 30, turnaround_minutes: 45,
      emergency_access: "East exit\nCourtyard", restrictions: "No flames" });
    expect(document.querySelector("#panel-capacity").textContent).toContain("Default setup");
    expect(document.querySelector("#panel-capacity").textContent).toContain("30 minutes");
    expect(document.querySelector("#panel-capacity").textContent).toContain("45 minutes");
    document.querySelector("#tab-facilities").click();
    await nextTick();
    expect(document.querySelector("#panel-facilities").textContent).toContain("East exit\nCourtyard");
    expect(document.querySelector("#panel-facilities").textContent).toContain("No flames");
  });

  it("CR-100 labels missing safety facts instead of inventing them", async () => {
    await mountView("venue_staff", { ...ACTIVE, setup_minutes: 0, emergency_access: null, restrictions: null });
    document.querySelector("#tab-facilities").click();
    await nextTick();
    const panel = document.querySelector("#panel-facilities");
    expect(panel.textContent).toContain("Emergency access");
    expect(panel.textContent).toContain("Restrictions");
    expect(panel.querySelectorAll("dd")[0].textContent).toBe("Not recorded");
    expect(panel.querySelectorAll("dd")[1].textContent).toBe("Not recorded");
  });

  it("offers Deactivate to venue staff on an active venue", async () => {
    await mountView("venue_staff", ACTIVE);
    expect(button("Deactivate venue")).toBeTruthy();
    expect(button("Reactivate venue")).toBeUndefined();
    expect(document.querySelector('[data-testid="venue-inactive-banner"]')).toBeNull();
  });

  it("offers neither action to a coordinator", async () => {
    await mountView("event_coordinator", INACTIVE);
    expect(button("Deactivate venue")).toBeUndefined();
    expect(button("Reactivate venue")).toBeUndefined();
  });

  it("shows why an inactive venue is inactive", async () => {
    await mountView("event_coordinator", INACTIVE);
    const banner = document.querySelector('[data-testid="venue-inactive-banner"]');
    expect(banner.textContent).toContain("Inactive: Long-term renovation");
    expect(banner.textContent).toContain("Roof works");
  });

  it("deactivates straight away when nothing is booked, and shows the banner", async () => {
    await mountView("venue_staff", ACTIVE);
    venuesApi.deactivate.mockResolvedValue({ saved: true, venue: INACTIVE, affected: [] });

    button("Deactivate venue").click();
    await nextTick();
    await chooseReason("long_term_renovation");
    document.querySelector('[role="dialog"] button[aria-label="Deactivate venue"]').click();
    await drain();

    expect(venuesApi.deactivate).toHaveBeenCalledWith(
      VENUE_ID, { reason: "long_term_renovation", note: null, version: 3, confirm: false }, "access");
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(document.querySelector('[data-testid="venue-inactive-banner"]').textContent).toContain("Long-term renovation");
  });

  it("previews affected bookings, then confirms", async () => {
    await mountView("venue_staff", ACTIVE);
    venuesApi.deactivate
      .mockResolvedValueOnce({
        saved: false,
        venue: null,
        affected: [{
          booking_id: "d-1", event_id: "e-1", event_name: "Partner Summit", status: "approved",
          period: { starts_at: "2031-05-20T14:00:00+08:00", ends_at: "2031-05-20T17:00:00+08:00" },
        }],
      })
      .mockResolvedValueOnce({ saved: true, venue: INACTIVE, affected: [] });

    button("Deactivate venue").click();
    await nextTick();
    await chooseReason("permanently_closed");
    document.querySelector('[role="dialog"] button[aria-label="Deactivate venue"]').click();
    await drain();
    expect(document.querySelector('[role="dialog"]').textContent).toContain("Partner Summit");

    document.querySelector('[role="dialog"] button[aria-label="Deactivate anyway"]').click();
    await drain();
    expect(venuesApi.deactivate).toHaveBeenLastCalledWith(
      VENUE_ID, { reason: "permanently_closed", note: null, version: 3, confirm: true }, "access");
    expect(document.querySelector('[data-testid="venue-inactive-banner"]')).toBeTruthy();
  });

  it("keeps the dialog open with the API's message when deactivation is refused", async () => {
    await mountView("venue_staff", ACTIVE);
    venuesApi.deactivate.mockRejectedValue(new Error("This venue is already inactive."));

    button("Deactivate venue").click();
    await nextTick();
    await chooseReason("permanently_closed");
    document.querySelector('[role="dialog"] button[aria-label="Deactivate venue"]').click();
    await drain();

    expect(document.querySelector('[role="dialog"] [role="alert"]').textContent).toContain("This venue is already inactive.");
  });

  it("reloads the venue after a refusal and leaves no stale error once the dialog is closed", async () => {
    await mountView("venue_staff", ACTIVE);
    venuesApi.deactivate.mockRejectedValue(new Error("This venue is already inactive."));
    venuesApi.get.mockResolvedValue(INACTIVE); // someone else deactivated it meanwhile

    button("Deactivate venue").click();
    await nextTick();
    await chooseReason("permanently_closed");
    document.querySelector('[role="dialog"] button[aria-label="Deactivate venue"]').click();
    await drain();
    document.querySelector('[role="dialog"] button[aria-label="Cancel"]').click();
    await drain();

    expect(document.querySelector('[data-testid="venue-inactive-banner"]')).toBeTruthy();
    expect(document.querySelector('[role="alert"]')).toBeNull();
  });

  it("does not show an error left in the shared edit store by another page", async () => {
    const { useVenueEditStore } = await import("@/features/venues/venueEditStore");
    await mountView("venue_staff", ACTIVE);
    useVenueEditStore().error = "Venue not found.";
    await nextTick();
    expect(document.querySelector('[role="alert"]')).toBeNull();
  });

  it("shows a refused reactivation on the page and refreshes the venue", async () => {
    await mountView("venue_staff", INACTIVE);
    venuesApi.reactivate.mockRejectedValue(new Error("This venue is already active."));
    venuesApi.get.mockResolvedValue(ACTIVE); // reactivated in another tab meanwhile

    button("Reactivate venue").click();
    await nextTick();
    document.querySelector('button[aria-label="Reactivate"]').click();
    await drain(); // the refusal, then the refresh behind it
    await drain();

    expect(document.querySelector('[role="alert"]').textContent).toContain("This venue is already active.");
    expect(document.querySelector('[data-testid="venue-inactive-banner"]')).toBeNull();
  });

  it("clears that message when moving to another venue", async () => {
    await mountView("venue_staff", INACTIVE);
    venuesApi.reactivate.mockRejectedValue(new Error("This venue is already active."));
    button("Reactivate venue").click();
    await nextTick();
    document.querySelector('button[aria-label="Reactivate"]').click();
    await drain();

    venuesApi.get.mockResolvedValue({ ...ACTIVE, id: "b0000000-0000-4000-8000-000000000002", name: "Hall B" });
    const { default: router } = await import("@/router");
    await router.push("/venues/b0000000-0000-4000-8000-000000000002");
    await drain();

    expect(document.body.textContent).toContain("Hall B");
    expect(document.querySelector('[role="alert"]')).toBeNull();
  });

  it("reactivates after confirming", async () => {
    await mountView("venue_staff", INACTIVE);
    venuesApi.reactivate.mockResolvedValue(ACTIVE);

    button("Reactivate venue").click();
    await nextTick();
    document.querySelector('button[aria-label="Reactivate"]').click();
    await drain();

    expect(venuesApi.reactivate).toHaveBeenCalledWith(VENUE_ID, { version: 4 }, "access");
    expect(document.querySelector('[data-testid="venue-inactive-banner"]')).toBeNull();
    expect(button("Deactivate venue")).toBeTruthy();
  });
});
