import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VenueStaffDashboard from "@/views/dashboards/VenueStaffDashboard.vue";
import { ApiError, venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  venuesApi: { search: vi.fn(), get: vi.fn(), venueStaffDashboard: vi.fn() },
}));

const PAYLOAD = {
  generated_at: "2026-09-19T04:00:00Z",
  venues: [
    { id: "b-1", name: "Grand Ballroom", location: "Marina Bay", is_active: true },
    { id: "b-5", name: "Rooftop Terrace", location: "Orchard Road", is_active: true },
    { id: "b-8", name: "Old Lecture Theatre", location: "Bukit Timah", is_active: false },
  ],
  pending_holds: [
    {
      id: "d-2",
      event_id: "e0000000-0000-4000-8000-000000000102",
      event_name: null,
      venue_id: "b-1",
      venue_name: "Grand Ballroom",
      period: { starts_at: "2026-10-10T13:00:00+08:00", ends_at: "2026-10-10T16:00:00+08:00" },
      status: "held",
      requested_at: "2026-09-03T10:30:00+08:00",
    },
    {
      id: "d-4",
      event_id: "e0000000-0000-4000-8000-000000000104",
      event_name: null,
      venue_id: "b-5",
      venue_name: "Rooftop Terrace",
      period: { starts_at: "2026-10-13T09:00:00+08:00", ends_at: "2026-10-13T12:00:00+08:00" },
      status: "held",
      requested_at: "2026-08-28T16:15:00+08:00",
    },
  ],
  re_review_bookings: [
    {
      id: "d-5",
      event_id: "e0000000-0000-4000-8000-000000000105",
      event_name: null,
      venue_id: "b-1",
      venue_name: "Grand Ballroom",
      period: { starts_at: "2026-10-12T09:00:00+08:00", ends_at: "2026-10-12T12:00:00+08:00" },
      status: "re_review",
      requested_at: "2026-09-10T11:45:00+08:00",
    },
  ],
  blocks: [
    {
      id: "c-3",
      venue_id: "b-5",
      venue_name: "Rooftop Terrace",
      period: { starts_at: "2026-10-20T00:00:00+08:00", ends_at: "2026-10-22T00:00:00+08:00" },
      reason: "safety",
      notes: "Railing inspection.",
    },
  ],
};

async function mountDashboard() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = { id: "s1", role: "venue_staff", full_name: "Priya Nair" };
  authStore.sessionVerified = true;
  const { default: router } = await import("@/router");
  await router.push("/dashboard/venue-staff");
  await router.isReady();
  const el = document.createElement("div");
  document.body.appendChild(el);
  createApp(VenueStaffDashboard).use(pinia).use(router).mount(el);
  // `load()` is fired from onMounted and not awaited, and a rejection travels
  // through more microtask turns than a resolve does, so drain generously.
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
    await nextTick();
  }
  return el;
}

describe("VenueStaffDashboard", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-19T12:00:00+08:00"));
  });

  it("shows the four counts from the payload", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    const text = el.textContent;
    expect(text).toContain("Pending requests");
    expect(text).toContain("In re-review");
    expect(text).toContain("Active & upcoming blocks");
    expect(text).toContain("2 active · 1 inactive");
  });

  it("carries none of the fabricated metrics it replaced", async () => {
    // Defect D8: this dashboard used to show three invented figures.
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    expect(el.textContent).not.toContain("Venues Managed");
    expect(el.textContent).not.toContain("Booking Requests");
    expect(el.textContent).not.toContain("Availability Updates Due");
    // The old tile values were 12 / 6 / 2. Assert on the figures the tiles
    // actually carry rather than on the bare digits, which also appear as day
    // numbers in the calendar grid.
    const tileValues = [...el.querySelectorAll("p.text-5xl")].map((p) => p.textContent.trim());
    expect(tileValues).toEqual(["2", "1", "1", "3"]);
  });

  it("lists pending requests oldest first, each linking to its own page", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    const links = [...el.querySelectorAll('a[href^="/bookings/"]')];
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/bookings/d-4", "/bookings/d-2"]);
    expect(links[0].textContent).toContain("Rooftop Terrace");
  });

  it("states how long a request has waited without dressing it as overdue", async () => {
    // BR-R4 sanctions showing the age; LC-R4 rules out deadline pressure.
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    const oldest = el.querySelector('a[href="/bookings/d-4"]');
    expect(oldest.textContent).toContain("Waiting 21 days");
    expect(oldest.innerHTML).not.toContain("bauhaus-red");
  });

  it("falls back to a short event id rather than inventing a name", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    expect(el.textContent).toContain("Event E0000000");
  });

  it("lists every venue with its status, linking to the venue page", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    const links = [...el.querySelectorAll('a[href^="/venues/"]')];
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/venues/b-5", "/venues/b-1", "/venues/b-8"]);
    expect(el.textContent).toContain("Block scheduled");
    expect(el.textContent).toContain("Inactive");
  });

  it("opens the calendar on the month that actually has something in it", async () => {
    // Today is in September; every block and request sits in October.
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    expect(el.textContent).toContain("October 2026");
    expect(el.textContent).toContain("September 2026 has nothing scheduled");
  });

  it("will not page back before the current month", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    const prev = el.querySelector('button[aria-label="Previous month"]');
    prev.click();
    await nextTick();
    prev.click();
    await nextTick();

    // October -> September, and then no further: the payload is upcoming-only.
    expect(el.textContent).toContain("September 2026");
    expect(el.querySelector('button[aria-label="Previous month"]').disabled).toBe(true);
  });

  it("marks the days a block covers and stops at its exclusive end", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    const labelled = (day) =>
      [...el.querySelectorAll("button[aria-label]")].find((b) => b.getAttribute("aria-label").includes(day));
    // Seeded block runs 20–22 Oct; the 22nd is free.
    expect(labelled("20 October 2026").getAttribute("aria-label")).toContain("1 item");
    expect(labelled("21 October 2026").getAttribute("aria-label")).toContain("1 item");
    expect(labelled("22 October 2026").getAttribute("aria-label")).toContain("0 items");
  });

  it("lists a day's items when that day is selected", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    const cell = [...el.querySelectorAll("button[aria-label]")].find((b) =>
      b.getAttribute("aria-label").includes("10 October 2026"),
    );
    cell.click();
    await nextTick();

    expect(el.textContent).toContain("Saturday, 10 October 2026");
    expect(el.textContent).toContain("Pending hold");
  });

  it("withholds every count until the first load settles", async () => {
    venuesApi.venueStaffDashboard.mockReturnValue(new Promise(() => {}));

    const el = await mountDashboard();

    expect(el.textContent).toContain("—");
    expect(el.textContent).toContain("Loading your queue");
  });

  it("shows an outage rather than an empty queue", async () => {
    venuesApi.venueStaffDashboard.mockRejectedValue(new ApiError("Venue service unavailable", 503));

    const el = await mountDashboard();

    expect(el.querySelector('[role="alert"]').textContent).toContain("Venue service unavailable");
    expect(el.textContent).not.toContain("Nothing is waiting on your decision");
  });

  it("says plainly when there is genuinely nothing to do", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue({
      generated_at: "2026-09-19T04:00:00Z",
      venues: [],
      pending_holds: [],
      re_review_bookings: [],
      blocks: [],
    });

    const el = await mountDashboard();

    expect(el.textContent).toContain("Nothing is waiting on your decision right now.");
  });
});
