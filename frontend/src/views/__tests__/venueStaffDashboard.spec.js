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

  it("lists pending requests soonest expiry first, each linking to its own page", async () => {
    // CR-99 (W7 CR-04): expiry, not age, orders the queue.
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    const links = [...el.querySelectorAll('a[href^="/bookings/"]')];
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/bookings/d-2", "/bookings/d-4"]);
    expect(links[0].textContent).toContain("Grand Ballroom");
  });

  it("shows each hold's expiry in Singapore time", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();

    expect(el.querySelector('[data-testid="hold-expiry-d-2"]').textContent).toContain("Expires 20 Sep 2026, 09:00");
  });

  it("closes the expiry form on Cancel without saving", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);
    const el = await mountDashboard();

    el.querySelector('[data-testid="hold-expiry-d-2"]').parentElement.querySelector("button").click();
    await nextTick();
    [...el.querySelectorAll("form button")].find((b) => b.textContent.includes("Cancel")).click();
    await nextTick();

    expect(el.querySelector("form")).toBeNull();
    expect(venueBookingsApi.changeExpiry).not.toHaveBeenCalled();
  });

  it("changes a hold's expiry from its row (CR-99 AC2)", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);
    venueBookingsApi.changeExpiry.mockResolvedValue({ id: "d-2", status: "held", expires_at: "2026-09-23T10:30:00Z" });
    const el = await mountDashboard();

    el.querySelector('[data-testid="hold-expiry-d-2"]').parentElement.querySelector("button").click();
    await nextTick();
    const input = el.querySelector('input[type="datetime-local"]');
    expect(input.getAttribute("max")).toBe("2026-10-10T13:00");
    input.value = "2026-09-23T18:30";
    input.dispatchEvent(new Event("input"));
    el.querySelector("form").dispatchEvent(new Event("submit"));
    for (let i = 0; i < 10; i += 1) {
      await Promise.resolve();
      await nextTick();
    }

    expect(venueBookingsApi.changeExpiry).toHaveBeenCalledWith(
      "d-2", { expires_at: "2026-09-23T18:30:00+08:00" }, "access",
    );
    expect(el.querySelector("form")).toBeNull();
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
        (s) => s.className.includes("tracking-widest") && s.textContent.trim(),
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

  it("scrolls both list panels rather than letting them run off the page", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    const venues = el.querySelector("#all-venues-list");
    const requests = el.querySelector("#pending-requests-list");

    // A capped height is what makes `overflow-y-auto` engage; without it the
    // panel just grows and the scrollbar never appears.
    for (const list of [venues, requests]) {
      expect(list.className).toContain("overflow-y-auto");
      expect(list.className).toMatch(/max-h-/);
    }

    // The two sit side by side, so they cap at the same height or the columns
    // fall out of step as soon as one of them fills up.
    const capOf = (list) => list.className.match(/max-h-\[[^\]]+\]/)[0];
    expect(capOf(requests)).toBe(capOf(venues));
  });

  it("jumps from the pending requests tile to the list further down the page", async () => {
    venuesApi.venueStaffDashboard.mockResolvedValue(PAYLOAD);

    const el = await mountDashboard();
    const jump = el.querySelector('a[href="#pending-requests"]');

    expect(jump).not.toBeNull();
    expect(jump.textContent).toContain("Pending requests");
    // The cue is revealed on hover and focus rather than standing on the tile,
    // but it stays in the DOM so it is part of the link's accessible name.
    const cue = [...jump.querySelectorAll("span")].find((s) => s.textContent.includes("See the list"));
    expect(cue).toBeDefined();
    expect(cue.className).toContain("opacity-0");
    expect(cue.className).toContain("group-hover:opacity-100");
    expect(jump.className).toContain("group");
    // The anchor is worthless without its target, and the target must clear
    // the sticky top bar once jumped to.
    const target = el.querySelector("#pending-requests");
    expect(target).not.toBeNull();
    expect(target.closest("section").className).toMatch(/scroll-mt-/);
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
