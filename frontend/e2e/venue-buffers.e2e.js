// CR-100: real browser, API and PostgREST; only throwaway venues/events.
import { API_URL, expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayVenue, createThrowawayEvent, createThrowawayBooking, setThrowawayEventStatus,
  venueBufferMigrationPresent } from "./support/throwaway.js";

test.beforeEach(() => {
  test.skip(!venueBufferMigrationPresent(), "Blocked: CR-100 migration is not deployed to the shared project.");
});

test("TC-VENUE-094 venue staff edit defaults, safety facts and history", async ({ page, sharedSessions }) => {
  const venue = createThrowawayVenue("094");
  await seedSession(page, await sharedSessions("venue_staff"));
  await page.goto(`/venues/${venue.id}/edit`);
  await expect(page.getByLabel("Default setup (minutes)")).toHaveValue("0");
  await expect(page.getByLabel("Default turnaround (minutes)")).toHaveValue("0");
  await page.getByLabel("Default setup (minutes)").fill("30");
  await page.getByLabel("Default turnaround (minutes)").fill("45");
  await page.getByLabel("Emergency access").fill("East exit\nCourtyard");
  await page.getByLabel("Restrictions").fill("No open flames");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page).toHaveURL(`/venues/${venue.id}`);
  await expect(page.locator("#panel-capacity")).toContainText("30 minutes");
  await expect(page.locator("#panel-capacity")).toContainText("45 minutes");
  await page.getByRole("tab", { name: "Facilities & access" }).click();
  await expect(page.locator("#panel-facilities")).toContainText("East exit");
  await expect(page.locator("#panel-facilities")).toContainText("No open flames");
  await page.getByRole("tab", { name: "History" }).click();
  await expect(page.getByTestId("edit-history")).toContainText("Default setup (minutes)");
  await expect(page.getByTestId("edit-history")).toContainText("Emergency access");
});

test("TC-VENUE-091 Safety Officer reads the venue's recorded safety facts", async ({ page, sharedSessions }) => {
  const venue = createThrowawayVenue("091");
  const staff = await sharedSessions("venue_staff");
  const saved = await fetch(`${API_URL}/venues/${venue.id}`, { method: "PATCH",
    headers: { Authorization: `Bearer ${staff.token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name: venue.name, location: "Live check", capacity: 50, opens_at: "08:00:00",
      closes_at: "22:00:00", setup_minutes: 30, turnaround_minutes: 45,
      emergency_access: "East exit\nCourtyard", restrictions: "No open flames" }) });
  expect(saved.status).toBe(200);
  const event = createThrowawayEvent("091", "2035-02-10T10:00:00Z", "2035-02-10T12:00:00Z");
  createThrowawayBooking(event, venue.id, "2035-02-10T10:00:00Z", "2035-02-10T12:00:00Z", "approved");
  setThrowawayEventStatus(event, "safety_review");
  await seedSession(page, await sharedSessions("safety_officer"));
  await page.goto(`/safety/events/${event.id}`);
  await expect(page.getByText("East exit", { exact: false })).toBeVisible();
  await expect(page.getByText("No open flames", { exact: false })).toBeVisible();
});
