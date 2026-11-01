// Deactivate and reactivate a venue (SCRUM-64) against real data, on a throwaway
// venue. Cases: docs/test-cases/venues.md.
import { expect, seedSession, test } from "./support/fixtures.js";
import {
  createThrowawayBooking,
  createThrowawayEvent,
  createThrowawayVenue,
  readThrowawayEvent,
  setThrowawayEventStatus,
} from "./support/throwaway.js";

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

// D71 (CR-104 AC10): flagging a Preparation event's booking returns it to Planning,
// as it does a Confirmed one. Case: docs/test-cases/safety-decisions.md.
test("TC-SDEC-037 deactivating the venue of a Preparation event returns it to Planning", async ({ page, browser, sharedSessions }, testInfo) => {
  const venue = createThrowawayVenue("SDEC037");
  const event = createThrowawayEvent("SDEC037", "2031-07-08 10:00+08", "2031-07-08 12:00+08");
  createThrowawayBooking(event, venue.id, "2031-07-08 10:00+08", "2031-07-08 12:00+08", "approved");
  setThrowawayEventStatus(event, "preparation");

  await seedSession(page, await sharedSessions("venue_staff"));
  await page.goto(`/venues/${venue.id}`);
  await page.getByRole("button", { name: "Deactivate venue" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Reason (required)").selectOption("long_term_renovation");
  await dialog.getByRole("button", { name: "Deactivate venue" }).click();
  await expect(dialog).toContainText(event.name);
  await dialog.getByRole("button", { name: "Deactivate anyway" }).click();
  await expect(page.getByTestId("venue-inactive-banner")).toBeVisible();
  await expect.poll(() => readThrowawayEvent(event.id).status).toBe("planning");

  // The coordinator's own tab: a session is seeded once per tab.
  const context = await browser.newContext();
  try {
    const coordinatorPage = await context.newPage();
    await seedSession(coordinatorPage, await sharedSessions("event_coordinator"));
    await coordinatorPage.goto(`/coordinator/events/${event.id}`);
    await expect(coordinatorPage.getByText("Planning", { exact: true }).first()).toBeVisible();
    await coordinatorPage.screenshot({ path: testInfo.outputPath("preparation-returned-to-planning.png"), fullPage: true });
  } finally {
    await context.close();
  }
});
