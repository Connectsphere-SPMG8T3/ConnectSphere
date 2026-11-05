// End, shorten or remove a venue block early (SCRUM-54) against real data, on a
// throwaway venue with a throwaway approved booking. Cases: docs/test-cases/venues.md.
import { expect, seedSession, test } from "./support/fixtures.js";
import {
  createThrowawayBlock,
  createThrowawayBooking,
  createThrowawayEvent,
  createThrowawayVenue,
  readThrowawayBooking,
} from "./support/throwaway.js";

test("TC-BLOCK-026 venue staff shorten a block, see the booking it freed, restore it, and read the history", async ({
  page,
  sharedSessions,
}) => {
  const venue = createThrowawayVenue("B026");
  const event = createThrowawayEvent("B026", "2031-09-26 10:00+08", "2031-09-26 12:00+08");
  const booking = createThrowawayBooking(event, venue.id, "2031-09-26 10:00+08", "2031-09-26 12:00+08", "approved");
  // The block trigger flags the booking Affected (CR-95).
  createThrowawayBlock(venue.id, "2031-09-26 09:00+08", "2031-09-26 17:00+08");
  await seedSession(page, await sharedSessions("venue_staff"));

  await page.goto(`/venues/${venue.id}`);
  await page.getByRole("tab", { name: /Blocks/ }).click();
  const blocks = page.getByTestId("upcoming-blocks");
  await expect(blocks).toContainText("Set by");
  await blocks.getByRole("button", { name: /Change block/ }).click();

  const dialog = page.getByRole("dialog");
  // It hasn't started: shorten or remove, never end now.
  await expect(dialog.getByRole("radio")).toHaveCount(2);
  await dialog.getByLabel("New end").fill("2031-09-26T09:30");
  await dialog.locator("#block-change-note").fill("Contractor finished early");
  await dialog.getByRole("button", { name: "Save change" }).click();

  await expect(dialog).toContainText("Block ended early");
  await expect(dialog).toContainText("1 booking can be restored");
  const listed = dialog.getByTestId("block-restorable");
  await expect(listed).toContainText(event.name);
  // AC5: shortening alone clears no flag.
  expect(readThrowawayBooking(booking.id).flag).toBe("affected");

  await listed.getByRole("link").click();
  await page.getByRole("button", { name: "Restore original booking" }).click();
  await expect(page.getByTestId("booking-affected")).toHaveCount(0);
  expect(readThrowawayBooking(booking.id)).toMatchObject({ status: "approved", flag: null });

  await page.goto(`/venues/${venue.id}`);
  await page.getByRole("tab", { name: /History/ }).click();
  const history = page.getByTestId("edit-history");
  await expect(history).toContainText("Block ended early");
  await expect(history).toContainText("Note: Contractor finished early");
});

test("TC-BLOCK-027 a coordinator sees the block but not who set it, and no Change action", async ({ page, sharedSessions }) => {
  const venue = createThrowawayVenue("B027");
  createThrowawayBlock(venue.id, "2031-09-27 09:00+08", "2031-09-27 17:00+08");
  await seedSession(page, await sharedSessions("event_coordinator"));

  await page.goto(`/venues/${venue.id}`);
  await page.getByRole("tab", { name: /Blocks/ }).click();
  const blocks = page.getByTestId("upcoming-blocks");
  await expect(blocks).toContainText("Maintenance");
  await expect(blocks).not.toContainText("Set by");
  await expect(blocks.getByRole("button", { name: /Change block/ })).toHaveCount(0);
});

test("TC-BLOCK-032 venue staff edit a venue with an upcoming block and land on its profile (D89)", async ({
  page,
  sharedSessions,
}) => {
  const venue = createThrowawayVenue("B032");
  createThrowawayBlock(venue.id, "2031-09-24T09:00:00+08:00", "2031-09-24T12:00:00+08:00");
  await seedSession(page, await sharedSessions("venue_staff"));

  await page.goto(`/venues/${venue.id}/edit`);
  await page.getByLabel("Default setup (minutes)").fill("30");
  await page.getByRole("button", { name: "Save changes" }).click();

  await expect(page).toHaveURL(`/venues/${venue.id}`);
  await expect(page.locator("#panel-capacity")).toContainText("30 minutes");
});
