import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import VenueDetailView from "@/views/venues/VenueDetailView.vue";
import { venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// SCRUM-54: end, shorten or remove a block from the venue profile's Blocks tab.
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  venuesApi: { search: vi.fn(), get: vi.fn(), history: vi.fn(), deactivate: vi.fn(), reactivate: vi.fn(), createBlock: vi.fn(),
    changeBlock: vi.fn() },
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


// Far enough ahead that it hasn't started whenever the suite runs.
const BLOCK = {
  id: "blk-1", status: "active", reason: "maintenance", notes: "Aircon",
  period: { starts_at: "2099-05-20T01:00:00Z", ends_at: "2099-05-20T09:00:00Z" },
  created_by: { id: "a3", full_name: "Vera Staff" }, created_at: "2099-04-30T02:30:00Z",
};
const BOOKING = { booking_id: "d-1", event_id: "e-1", event_name: "Partner Summit", status: "approved",
  period: { starts_at: "2099-05-20T06:00:00Z", ends_at: "2099-05-20T08:00:00Z" }, block_reason: "Maintenance",
  has_pending_replacement: false };

async function openBlocksTab() {
  document.querySelector("#tab-blocks").click();
  await drain();
}

const changeButton = () => document.querySelector('[data-testid="upcoming-blocks"] button[aria-label^="Change block"]');

describe("VenueDetailView: changing a block (SCRUM-54)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    apps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("shows venue staff who set each block and when (AC1)", async () => {
    await mountView("venue_staff", { ...ACTIVE, upcoming_blocks: [BLOCK] });
    await openBlocksTab();
    expect(document.querySelector('[data-testid="upcoming-blocks"]').textContent)
      .toContain("Set by Vera Staff · 30 Apr 2099, 10:30");
  });

  it("shows a coordinator the block but not who set it (AC9)", async () => {
    const { created_by: _by, created_at: _at, ...plain } = BLOCK;
    await mountView("event_coordinator", { ...ACTIVE, upcoming_blocks: [plain] });
    await openBlocksTab();
    const tab = document.querySelector('[data-testid="upcoming-blocks"]').textContent;
    expect(tab).toContain("Maintenance");
    expect(tab).not.toContain("Set by");
  });

  it("offers Change only to a session acting as venue staff (AC9)", async () => {
    await mountView("event_coordinator", { ...ACTIVE, upcoming_blocks: [BLOCK] });
    await openBlocksTab();
    expect(changeButton()).toBeNull();
    apps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";

    await mountView("venue_staff", { ...ACTIVE, upcoming_blocks: [BLOCK] });
    await openBlocksTab();
    expect(changeButton()).not.toBeNull();
  });

  it("removes a block, lists the booking to restore, and reloads the venue on Done (AC2, AC5)", async () => {
    await mountView("venue_staff", { ...ACTIVE, upcoming_blocks: [BLOCK] });
    await openBlocksTab();
    venuesApi.changeBlock.mockResolvedValue({ block: { ...BLOCK, status: "removed" }, restorable: [BOOKING] });
    venuesApi.get.mockResolvedValue({ ...ACTIVE, upcoming_blocks: [] });

    changeButton().click();
    await drain();
    const remove = document.querySelector('[role="dialog"] input[value="remove"]');
    remove.checked = true;
    remove.dispatchEvent(new Event("change"));
    await nextTick();
    document.querySelector('[role="dialog"] button[aria-label="Save change"]').click();
    await drain();

    expect(venuesApi.changeBlock).toHaveBeenCalledWith(VENUE_ID, "blk-1",
      { action: "remove", ends_at: null, note: null }, "access");
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog.textContent).toContain("Block removed");
    expect(dialog.textContent).toContain("Partner Summit");

    document.querySelector('[role="dialog"] button[aria-label="Done"]').click();
    await drain();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(venuesApi.get).toHaveBeenCalledTimes(2);
    expect(document.querySelector('[data-testid="upcoming-blocks"]').textContent).toContain("No blocks scheduled.");
  });

  it("keeps the dialog open with the API's message when a change is refused, and reloads on Cancel", async () => {
    await mountView("venue_staff", { ...ACTIVE, upcoming_blocks: [BLOCK] });
    await openBlocksTab();
    venuesApi.changeBlock.mockRejectedValue(new Error("This block was removed, so it can't be changed."));

    changeButton().click();
    await drain();
    const remove = document.querySelector('[role="dialog"] input[value="remove"]');
    remove.checked = true;
    remove.dispatchEvent(new Event("change"));
    await nextTick();
    document.querySelector('[role="dialog"] button[aria-label="Save change"]').click();
    await drain();

    expect(document.querySelector('[role="dialog"] [role="alert"]').textContent).toContain("was removed");
    document.querySelector('[role="dialog"] button[aria-label="Cancel"]').click();
    await drain();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    // The block changed under us; the page re-reads the venue.
    expect(venuesApi.get).toHaveBeenCalledTimes(2);
  });
});
