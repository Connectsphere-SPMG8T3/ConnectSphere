// SCRUM-39: the venue search page. Seeded catalogue; bookings are throwaway and dated 2031.
// Cases: docs/test-cases/venues.md (TC-VENUE-003, 008, 009, 010, 012, 055).
import { expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayBooking, createThrowawayEvent } from "./support/throwaway.js";

const AUDITORIUM_A = "b0000000-0000-4000-8000-000000000002";
const SEMINAR_ROOM_1 = "b0000000-0000-4000-8000-000000000003";

test("TC-VENUE-003 a back-to-back booking doesn't exclude a venue", async ({ page, sharedSessions }) => {
  const starts = "2031-07-07 11:00+08";
  const ends = "2031-07-07 14:00+08";
  const event = createThrowawayEvent("search003", starts, ends);
  createThrowawayBooking(event, AUDITORIUM_A, starts, ends, "approved");

  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto("/venues");
  await page.getByLabel("Event date").fill("2031-07-07");
  await page.getByLabel("Start time").fill("14:00");
  await page.getByLabel("End time").fill("17:00");
  await page.getByRole("button", { name: "Search venues" }).click();
  const card = page.getByTestId("venue-result").filter({ hasText: "Auditorium A" });
  await expect(card.getByTestId("availability-badge")).toHaveText("Available");

  await page.goto(`/venues/${AUDITORIUM_A}`);
  await page.getByRole("tab", { name: /Upcoming bookings/ }).click();
  await expect(page.locator("#panel-bookings")).toContainText(event.name);
  await expect(page.locator("#panel-bookings")).toContainText("Approved");
});

test("TC-VENUE-008 an incomplete or inverted period is refused before any request", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto("/venues");
  await expect(page.getByTestId("venue-filters")).toBeVisible();
  let searches = 0;
  page.on("request", (request) => {
    if (/\/api\/v1\/venues\?/.test(request.url())) searches += 1;
  });

  await page.getByLabel("Event date").fill("2031-07-08");
  await page.getByLabel("Start time").fill("14:00");
  await page.getByRole("button", { name: "Search venues" }).click();
  await expect(page.getByText("Enter the end time.")).toBeVisible();

  await page.getByLabel("Start time").fill("17:00");
  await page.getByLabel("End time").fill("14:00");
  await page.getByRole("button", { name: "Search venues" }).click();
  await expect(page.getByText("End time must be after start time.")).toBeVisible();
  expect(searches).toBe(0);
});

test("TC-VENUE-009 the detail page shows the venue and its upcoming bookings", async ({ page, sharedSessions }) => {
  const starts = "2031-07-09 13:00+08";
  const ends = "2031-07-09 16:00+08";
  const event = createThrowawayEvent("search009", starts, ends);
  createThrowawayBooking(event, SEMINAR_ROOM_1, starts, ends, "held");

  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto("/venues");
  await page.getByRole("link", { name: "Seminar Room 1" }).first().click();
  await expect(page).toHaveURL(`/venues/${SEMINAR_ROOM_1}`);
  const capacity = page.locator("#panel-capacity");
  await expect(capacity).toContainText("60");
  await expect(capacity).toContainText("08:00");
  await expect(capacity).toContainText("22:00");
  await expect(capacity).toContainText("Classroom");
  await page.getByRole("tab", { name: /Upcoming bookings/ }).click();
  await expect(page.locator("#panel-bookings")).toContainText("Pending");
  await expect(page.locator("#panel-bookings")).toContainText(event.name);

  await page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("link", { name: "Venues" }).click();
  await expect(page).toHaveURL("/venues");
  await expect(page.getByRole("link", { name: "Seminar Room 1" }).first()).toBeVisible();
});

test("TC-VENUE-010 venue staff reach search", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("venue_staff"));
  await page.goto("/venues");
  await expect(page.getByTestId("venue-filters")).toBeVisible();
});

for (const [role, dashboard] of [
  ["event_organiser", "/dashboard/organiser"],
  ["attendee", "/dashboard/attendee"],
  ["tech_support", "/dashboard/tech-support"],
]) {
  test(`TC-VENUE-010 ${role} goes to their own dashboard`, async ({ page, sharedSessions }) => {
    await seedSession(page, await sharedSessions(role));
    await page.goto("/venues");
    await expect(page).toHaveURL(new RegExp(dashboard));
  });
}

test("TC-VENUE-012 an API outage keeps the previous results on screen", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto("/venues");
  await expect(page.getByRole("link", { name: "Seminar Room 1" }).first()).toBeVisible();

  await page.route(/\/api\/v1\/venues\?/, (route) => route.abort());
  await page.getByRole("button", { name: "Search venues" }).click();
  await expect(page.getByRole("alert").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Seminar Room 1" }).first()).toBeVisible();
  await expect(page).toHaveURL(/\/venues/);
});

test("TC-VENUE-055 pressing Enter in a search field runs the search", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto("/venues");
  await expect(page.getByRole("link", { name: "Seminar Room 1" }).first()).toBeVisible();
  const search = page.waitForRequest((request) => /\/api\/v1\/venues\?.*min_capacity=50/.test(request.url()));
  await page.getByLabel("Expected attendance").fill("50");
  await page.getByLabel("Expected attendance").press("Enter");
  await search;
});
