// Deactivate and reactivate a venue (SCRUM-64) against real data, on a throwaway
// venue. Cases: docs/test-cases/venues.md.
import { expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayBooking, createThrowawayEvent, createThrowawayVenue } from "./support/throwaway.js";

test("TC-VENUE-065 venue staff deactivate a venue with a reason and reactivate it", async ({ page, sharedSessions }) => {
  const venue = createThrowawayVenue("065");
  await seedSession(page, await sharedSessions("venue_staff"));

  await page.goto(`/venues/${venue.id}`);
  await page.getByRole("button", { name: "Deactivate venue" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Reason (required)").selectOption("long_term_renovation");
  await dialog.getByLabel("Note (optional)").fill("Roof works");
  await dialog.getByRole("button", { name: "Deactivate venue" }).click();

  const banner = page.getByTestId("venue-inactive-banner");
  await expect(banner).toContainText("Inactive: Long-term renovation");
  await expect(banner).toContainText("Roof works");

  await page.getByRole("button", { name: "Reactivate venue" }).click();
  await page.getByRole("button", { name: "Reactivate", exact: true }).click();
  await expect(banner).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Deactivate venue" })).toBeVisible();
});

test("TC-VENUE-097 deactivating again after reactivation lists the still-flagged booking", async ({ page, sharedSessions }) => {
  const venue = createThrowawayVenue("097");
  const event = createThrowawayEvent("097", "2031-07-04 10:00+08", "2031-07-04 12:00+08");
  createThrowawayBooking(event, venue.id, "2031-07-04 10:00+08", "2031-07-04 12:00+08", "held");
  await seedSession(page, await sharedSessions("venue_staff"));
  await page.goto(`/venues/${venue.id}`);
  const dialog = page.getByRole("dialog");

  async function deactivate() {
    await page.getByRole("button", { name: "Deactivate venue" }).click();
    await dialog.getByLabel("Reason (required)").selectOption("long_term_renovation");
    await dialog.getByRole("button", { name: "Deactivate venue" }).click();
    await expect(dialog).toContainText(event.name);
  }

  await deactivate();
  await expect(dialog).not.toContainText("Already flagged");
  await dialog.getByRole("button", { name: "Deactivate anyway" }).click();
  await page.getByRole("button", { name: "Reactivate venue" }).click();
  await page.getByRole("button", { name: "Reactivate", exact: true }).click();
  await expect(page.getByTestId("venue-inactive-banner")).toHaveCount(0);

  await deactivate();
  await expect(dialog).toContainText("Already flagged: Affected");
  await expect(dialog).toContainText("It is already flagged, so it keeps its flag");
  await dialog.getByRole("button", { name: "Deactivate anyway" }).click();
  await expect(page.getByTestId("venue-inactive-banner")).toContainText("Inactive: Long-term renovation");
});
