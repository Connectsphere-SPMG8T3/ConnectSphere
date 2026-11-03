// A venue's availability calendar (SCRUM-57) against real data, on throwaway
// venues with a throwaway booking tomorrow. Cases: docs/test-cases/venues.md.
import { expect, seedSession, test } from "./support/fixtures.js";
import {
  createThrowawayBlock,
  createThrowawayBooking,
  createThrowawayEvent,
  createThrowawayVenue,
  setThrowawayBookingBuffers,
} from "./support/throwaway.js";

// Tomorrow in Singapore, so the booking is upcoming whatever day the run is on.
const TOMORROW = new Date(Date.now() + 32 * 60 * 60 * 1000).toISOString().slice(0, 10);

test("TC-VCAL-005 venue staff open a venue's calendar, read a booking's bands and details, refresh in place, " +
  "and switch to an empty venue", async ({ page, sharedSessions }) => {
  const venue = createThrowawayVenue("VC005");
  const quiet = createThrowawayVenue("VC005 quiet");
  const event = createThrowawayEvent("VC005", `${TOMORROW} 09:00+08`, `${TOMORROW} 13:00+08`);
  const booking = createThrowawayBooking(event, venue.id, `${TOMORROW} 10:00+08`, `${TOMORROW} 12:00+08`, "approved");
  setThrowawayBookingBuffers(booking.id, 30, 45);
  await seedSession(page, await sharedSessions("venue_staff"));

  await page.goto(`/venues/${venue.id}`);
  await page.getByRole("link", { name: "View calendar" }).click();
  await expect(page).toHaveURL(new RegExp(`/venue-calendar/${venue.id}$`));
  await page.getByRole("button", { name: "Day", exact: true }).click();
  await page.getByRole("button", { name: "Next day" }).click();

  // AC2, AC5: labelled by type, setup and turnaround as their own bands.
  const entry = page.getByTestId("calendar-entry").filter({ hasText: event.name });
  await expect(entry).toHaveAttribute("data-type", "confirmed");
  await expect(entry.locator('[data-band="setup"]')).toContainText("Setup");
  await expect(entry.locator('[data-band="event"]')).toContainText("Confirmed");
  await expect(entry.locator('[data-band="event"]')).toContainText("10:00–12:00");
  await expect(entry.locator('[data-band="turnaround"]')).toContainText("Turnaround");

  // AC9: its details.
  await entry.click();
  const details = page.getByTestId("entry-details");
  await expect(details).toContainText(event.name);
  await expect(details).toContainText("09:30–12:45");
  await expect(details).toContainText("30 min before, 45 min after");

  // AC4: a block added elsewhere shows on Refresh, without reloading the page.
  await page.evaluate(() => {
    window.__notReloaded = true;
  });
  createThrowawayBlock(venue.id, `${TOMORROW} 14:00+08`, `${TOMORROW} 16:00+08`);
  await page.getByRole("button", { name: "Refresh" }).click();
  await expect(page.getByTestId("calendar-entry").filter({ hasText: "Maintenance" })).toHaveAttribute(
    "data-type",
    "blocked",
  );
  expect(await page.evaluate(() => window.__notReloaded)).toBe(true);

  // AC1, AC10: switching venue, and an empty one says so.
  await page.getByLabel("Venue", { exact: true }).selectOption(quiet.id);
  await expect(page).toHaveURL(new RegExp(`/venue-calendar/${quiet.id}$`));
  await expect(page.getByTestId("calendar-empty")).toContainText(`No bookings, holds or blocks at ${quiet.name}`);
});

test("TC-VCAL-006 a coordinator has no venue calendar: no nav link, and the address sends them to their dashboard",
  async ({ page, sharedSessions }) => {
    const venue = createThrowawayVenue("VC006");
    await seedSession(page, await sharedSessions("event_coordinator"));

    await page.goto(`/venue-calendar/${venue.id}`);

    await expect(page).toHaveURL(/\/dashboard\/coordinator/);
    await expect(page.getByRole("link", { name: "Venue calendar" })).toHaveCount(0);
  });
