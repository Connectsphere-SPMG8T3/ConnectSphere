import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VenueStaffDashboard from "@/views/dashboards/VenueStaffDashboard.vue";
import { ApiError, venueBookingsApi, venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  venuesApi: { search: vi.fn(), get: vi.fn(), venueStaffDashboard: vi.fn() },
  venueBookingsApi: { changeExpiry: vi.fn() },
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
      // The newer request expires first, so the queue isn't in age order.
      expires_at: "2026-09-20T01:00:00Z",
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
      expires_at: "2026-09-25T01:00:00Z",
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

  const columnCounts = (el) =>
    Object.fromEntries(
      [...el.querySelectorAll("[data-status-group]")].map((column) => [
        column.dataset.statusGroup,
        column.querySelector("p.text-2xl").textContent.trim(),
      ]),
    );

  it("shows Flagged bookings, Pending requests in the middle, and Approved, with their counts", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue({
      ...PAYLOAD,
      affected_bookings: [
        { id: "d-7", event_id: "e7", event_name: "Staff Retreat", venue_id: "b-5", venue_name: "Rooftop Terrace",
          period: { starts_at: "2026-10-21T09:00:00+08:00", ends_at: "2026-10-21T12:00:00+08:00" },
          status: "approved", flag: "affected", restorable: true },
      ],
      booking_requests: [
        ...PAYLOAD.pending_holds,
        { id: "d-9", event_id: "e9", event_name: "Alumni Dinner", venue_id: "b-1", venue_name: "Grand Ballroom",
          period: { starts_at: "2026-10-15T09:00:00+08:00", ends_at: "2026-10-15T12:00:00+08:00" }, status: "approved" },
      ],
    });

    const el = await mountDashboard();

    expect(el.querySelector("#booking-status").textContent).toContain("Booking status");
    expect([...el.querySelectorAll("[data-status-group]")].map((column) => column.dataset.statusGroup)).toEqual([
      "flagged",
      "pending",
      "re_review",
      "approved",
    ]);
    expect(columnCounts(el)).toEqual({ flagged: "1", pending: "2", re_review: "1", approved: "1" });
    expect(el.querySelector('[data-status-group="re_review"]').textContent).toContain("Grand Ballroom");
    expect(el.querySelector('[data-status-group="approved"]').textContent).toContain("Alumni Dinner");
    expect(el.querySelector('[data-status-group="flagged"]').textContent).toContain("Staff Retreat");
    expect(el.querySelector('[data-status-group="flagged"]').textContent).toContain("Venue free again: ready to restore");
    // The legend explains only the colours the board uses.
    expect(el.querySelector("[data-board-legend]").textContent).not.toContain("Blue");
  });

  it("carries none of the fabricated metrics it replaced", async () => {
    // Defect D8: this dashboard used to show three invented figures.
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    expect(el.textContent).not.toContain("Venues Managed");
    expect(el.textContent).not.toContain("Booking Requests");
    expect(el.textContent).not.toContain("Availability Updates Due");
    // The old tile values were 12 / 6 / 2. Assert on the board's own counts rather than on
    // bare digits, which also appear as day numbers in the calendar grid.
    expect(columnCounts(el)).toEqual({ flagged: "0", pending: "2", re_review: "1", approved: "0" });
  });

  it("lists every venue with its status, linking to the venue page", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    const links = [...el.querySelectorAll('a[href^="/venues/"]')];
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/venues/b-5", "/venues/b-1", "/venues/b-8"]);
    expect(el.textContent).toContain("Block scheduled");
    expect(el.textContent).toContain("Inactive");
  });

  it("filters the venue list by status, and counts each status on its control", async () => {
    // AC2: status at a glance. With one block sitting on the Rooftop Terrace,
    // the three venues split one apiece.
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    const filters = () => [...el.querySelectorAll('[aria-label="Filter venues by status"] button')];

    expect(filters().map((b) => b.textContent.replace(/\s+/g, " ").trim())).toEqual([
      "All 3",
      "Block scheduled 1",
      "Active 1",
      "Inactive 1",
    ]);

    filters().find((b) => b.textContent.includes("Block scheduled")).click();
    await nextTick();

    const links = [...el.querySelectorAll('a[href^="/venues/"]')];
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/venues/b-5"]);
    expect(filters().find((b) => b.textContent.includes("Block scheduled")).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("colours the ACTIVE badge on a venue row green, and nothing else", async () => {
    // Green marks the one status that asks nothing of the person reading it.
    // It belongs on the row badge, beside the venue, not on the filter row:
    // being filtered on is a different question from being active.
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    const badgeFor = (venueId) =>
      [...el.querySelector(`a[href="/venues/${venueId}"]`).querySelectorAll("span")].find(
        (s) => s.className.includes("border-ink") && s.textContent.trim(),
      );

    // b-1 has no block on it and is flagged active.
    expect(badgeFor("b-1").textContent.trim()).toBe("Active");
    expect(badgeFor("b-1").className).toContain("bg-bauhaus-green");

    // Every other status keeps its own colour.
    expect(badgeFor("b-5").className).not.toContain("bg-bauhaus-green");
    expect(badgeFor("b-8").className).not.toContain("bg-bauhaus-green");

    // The filter controls stay plain — the colour is not repeated there.
    const filters = [...el.querySelectorAll('[aria-label="Filter venues by status"] button')];
    expect(filters.every((b) => !b.className.includes("bg-bauhaus-green"))).toBe(true);
  });

  it("brings every venue back when All is chosen again", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    const filters = () => [...el.querySelectorAll('[aria-label="Filter venues by status"] button')];

    filters().find((b) => b.textContent.includes("Inactive")).click();
    await nextTick();
    expect(el.querySelectorAll('a[href^="/venues/"]')).toHaveLength(1);

    filters().find((b) => b.textContent.startsWith("All")).click();
    await nextTick();
    expect(el.querySelectorAll('a[href^="/venues/"]')).toHaveLength(3);
  });

  it("offers no filter that would empty the list", async () => {
    // Every venue is active here, so a "Blocked now" control would be a dead
    // one — it is not offered at all.
    venuesApi.venueStaffDashboard.mockResolvedValue({
      ...PAYLOAD,
      venues: [{ id: "b-2", name: "Auditorium A", location: "Bukit Timah", is_active: true }],
      blocks: [],
    });

    const el = await mountDashboard();
    const labels = [...el.querySelectorAll('[aria-label="Filter venues by status"] button')].map((b) =>
      b.textContent.replace(/\s+/g, " ").trim(),
    );

    expect(labels).toEqual(["All 1", "Active 1"]);
  });

  it("scrolls the venue list rather than letting it run off the page", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    const venues = el.querySelector("#all-venues-list");

    expect(venues.className).toContain("overflow-y-auto");
    expect(venues.className).toMatch(/max-h-/);
  });

  it("opens the approved bookings from their column", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    el.querySelector('[data-status-group="approved"] button').click();

    const { default: router } = await import("@/router");
    await vi.waitFor(() => expect(router.currentRoute.value.query).toEqual({ status: "approved" }));
    expect(router.currentRoute.value.name).toBe("dashboard-venue-staff-requests");
  });

  it("opens the booking requests page on Re-review from the Re-review column", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    el.querySelector('[data-status-group="re_review"] button').click();

    const { default: router } = await import("@/router");
    await vi.waitFor(() => expect(router.currentRoute.value.query).toEqual({ status: "re_review" }));
    expect(router.currentRoute.value.name).toBe("dashboard-venue-staff-requests");
  });

  it("shows a flagged booking once, in Flagged only, and leaves past approved bookings out", async () => {
    const flagged = { id: "d-7", event_id: "e7", event_name: "Staff Retreat", venue_id: "b-5", venue_name: "Rooftop Terrace",
      period: { starts_at: "2026-10-21T09:00:00+08:00", ends_at: "2026-10-21T12:00:00+08:00" },
      status: "approved", flag: "affected", restorable: true };
    venuesApi.venueStaffDashboard.mockResolvedValue({
      ...PAYLOAD,
      affected_bookings: [flagged, { ...PAYLOAD.pending_holds[0] }],
      booking_requests: [
        ...PAYLOAD.pending_holds,
        flagged,
        { id: "d-0", event_id: "e0", event_name: "Last Year's Gala", venue_id: "b-1", venue_name: "Grand Ballroom",
          period: { starts_at: "2026-03-01T09:00:00+08:00", ends_at: "2026-03-01T12:00:00+08:00" }, status: "approved" },
      ],
    });

    const el = await mountDashboard();

    expect(columnCounts(el)).toEqual({ flagged: "2", pending: "1", re_review: "1", approved: "0" });
    expect(el.querySelector("#booking-status").parentElement.textContent).toContain("4 total");
    expect(el.querySelector('[data-status-group="approved"]').textContent).not.toContain("Last Year's Gala");
    expect(el.querySelector('[data-status-group="approved"]').textContent).not.toContain("Staff Retreat");
  });

  it("opens the dedicated booking requests page from the Pending requests column", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    el.querySelector('[data-status-group="pending"] button').click();

    const { default: router } = await import("@/router");
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("dashboard-venue-staff-requests"));
    expect(router.currentRoute.value.query).toEqual({});
  });

  it("lists each pending request as a card with its venue and expiry, opening its booking (AC5)", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    const cards = [...el.querySelectorAll('[data-status-group="pending"] a')];

    // The hold that expires first leads.
    expect(cards.map((card) => card.getAttribute("href"))).toEqual(["/bookings/d-2", "/bookings/d-4"]);
    expect(cards[0].textContent).toContain("Grand Ballroom");
    expect(cards[0].textContent).toContain("Expires");
  });

  it("opens the calendar on the month that actually has something in it", async () => {
    // Today is in September; every block and request sits in October.
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    expect(el.textContent).toContain("October 2026");
  });

  it("offers Today as the way back, enabled only when the month has been left", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    const today = () => el.querySelector('button[aria-label="Jump to the current month"]');

    // Opened on October, so Today is live.
    expect(today().disabled).toBe(false);
    today().click();
    await nextTick();

    expect(el.textContent).toContain("September 2026");
    expect(today().disabled).toBe(true);
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

  it("clears the selected day from the detail column", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    const cell = [...el.querySelectorAll("button[aria-label]")].find((b) =>
      b.getAttribute("aria-label").includes("10 October 2026"),
    );
    cell.click();
    await nextTick();
    el.querySelector('button[aria-label="Clear the selected day"]').click();
    await nextTick();

    expect(el.textContent).not.toContain("Saturday, 10 October 2026");
    expect(el.textContent).toContain("Select a marked day to see what is on it.");
  });

  it("names each item in the month grid rather than dotting it", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    // Opens on October, where all three bookings and the block sit.
    expect(el.textContent).toContain("October 2026");
    const calendar = el.querySelector('section[aria-labelledby="venue-calendar-heading"]');
    expect(calendar.textContent).toContain("Grand Ballroom");
    expect(calendar.textContent).toContain("Rooftop Terrace");
  });

  it("draws a multi-day block as one bar spanning its days", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    // The seeded block runs 20-22 Oct, so it covers two days as a single bar
    // rather than appearing once per day.
    const bars = [...el.querySelectorAll("span[style*='grid-column']")].filter((b) =>
      b.textContent.includes("Rooftop Terrace"),
    );
    const spanning = bars.filter((b) => b.getAttribute("style").includes("span 2"));
    expect(spanning).toHaveLength(1);
  });

  it("returns from the week view to the month that week sits in", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);
    const el = await mountDashboard();
    const view = (label) => [...el.querySelectorAll("button")].find((b) => b.textContent.trim() === label);

    view("Week").click();
    await nextTick();
    view("Month").click();
    await nextTick();

    expect(view("Month").getAttribute("aria-pressed")).toBe("true");
    expect(el.textContent).toContain("October 2026");
  });

  it("switches to a week view that names the items instead of dotting them", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    const weekButton = [...el.querySelectorAll("button")].find((b) => b.textContent.trim() === "Week");
    weekButton.click();
    await nextTick();

    // Opens on the first week carrying something: 5-11 Oct holds the 10 Oct hold.
    expect(el.textContent).toContain("5 Oct – 11 Oct 2026");
    // The venue is named in the day columns themselves, not hidden behind a dot.
    const dayColumn = [...el.querySelectorAll("button[aria-label]")].find((b) =>
      b.getAttribute("aria-label").includes("10 October 2026"),
    );
    expect(dayColumn.textContent).toContain("Grand Ballroom");
  });

  it("steps by a week in the week view and by a month in the month view", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    const next = () => el.querySelector('button[aria-label="Next month"]');
    const nextWeek = () => el.querySelector('button[aria-label="Next week"]');

    next().click();
    await nextTick();
    expect(el.textContent).toContain("November 2026");

    [...el.querySelectorAll("button")].find((b) => b.textContent.trim() === "Week").click();
    await nextTick();
    nextWeek().click();
    await nextTick();

    // Switching carried November over rather than snapping back to today.
    expect(el.textContent).toContain("Nov");
    expect(el.querySelector('button[aria-label="Next month"]')).toBeNull();
  });

  it("keeps Today and the back-stop working per view", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    [...el.querySelectorAll("button")].find((b) => b.textContent.trim() === "Week").click();
    await nextTick();

    const today = () => el.querySelector('button[aria-label="Jump to the current week"]');
    expect(today().disabled).toBe(false);
    today().click();
    await nextTick();

    // Back on the week containing 19 Sep 2026, which starts Monday the 14th.
    expect(el.textContent).toContain("14 Sept – 20 Sept 2026");
    expect(today().disabled).toBe(true);
    expect(el.querySelector('button[aria-label="Previous week"]').disabled).toBe(true);
  });

  it("exports every item as a calendar file, not just the month on screen", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    // jsdom's Blob has no .text(), so capture the content as it is built.
    const OriginalBlob = globalThis.Blob;
    let captured = null;
    let capturedType = null;
    globalThis.Blob = class extends OriginalBlob {
      constructor(parts, options) {
        super(parts, options);
        captured = parts.join("");
        capturedType = options?.type;
      }
    };
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    URL.createObjectURL = () => "blob:stub";
    URL.revokeObjectURL = () => {};

    // jsdom does not implement navigation, so stub the anchor's click.
    const clicked = [];
    const originalClick = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function stub() {
      clicked.push({ download: this.download });
    };

    try {
      const el = await mountDashboard();
      const exportButton = el.querySelector('button[aria-label^="Export every block"]');
      expect(exportButton.disabled).toBe(false);
      exportButton.click();

      expect(clicked).toEqual([{ download: "connectsphere-venues-2026-09-19.ics" }]);
      expect(capturedType).toContain("text/calendar");
      expect(captured).toContain("BEGIN:VCALENDAR");
      // All four items, though the calendar is showing October only.
      expect(captured.match(/BEGIN:VEVENT/g)).toHaveLength(4);
      expect(captured).toContain("SUMMARY:Blocked: Rooftop Terrace (safety)");
    } finally {
      globalThis.Blob = OriginalBlob;
      URL.createObjectURL = originalCreate;
      URL.revokeObjectURL = originalRevoke;
      HTMLAnchorElement.prototype.click = originalClick;
    }
  });

  it("offers nothing to export when there is nothing to export", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue({
      generated_at: "2026-09-19T04:00:00Z",
      venues: [],
      pending_holds: [],
      re_review_bookings: [],
      blocks: [],
    });

    const el = await mountDashboard();

    expect(el.querySelector('button[aria-label^="Export every block"]').disabled).toBe(true);
  });

  it("withholds the board until the first load settles", async () => {
    venuesApi.venueStaffDashboard.mockReturnValue(new Promise(() => {}));

    const el = await mountDashboard();

    expect(el.textContent).toContain("Loading bookings");
    expect(el.querySelector("[data-status-group]")).toBeNull();
    expect(el.textContent).toContain("Checking for updates");
  });

  it("shows an outage rather than an empty queue", async () => {
    venuesApi.venueStaffDashboard.mockRejectedValue(new ApiError("Venue service unavailable", 503));

    const el = await mountDashboard();

    expect(el.querySelector('[role="alert"]').textContent).toContain("Venue service unavailable");
    expect(el.textContent).not.toContain("Nothing is waiting on your decision");
  });

  it("says plainly when there are genuinely no venues", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue({
      generated_at: "2026-09-19T04:00:00Z",
      venues: [],
      pending_holds: [],
      re_review_bookings: [],
      blocks: [],
    });

    const el = await mountDashboard();

    expect(el.textContent).toContain("No venues in the catalogue");
  });
});
