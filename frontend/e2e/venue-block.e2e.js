// Block a venue (SCRUM-51) against real data, on a throwaway venue with a
// throwaway approved booking. Cases: docs/test-cases/venues.md.
import { expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayBooking, createThrowawayEvent, createThrowawayVenue } from "./support/throwaway.js";

test("TC-BLOCK-014 venue staff block a booked venue: preview, confirm, then see the affected booking", async ({
  page,
  sharedSessions,
}) => {
  const venue = createThrowawayVenue("B014");
  const event = createThrowawayEvent("B014", "2031-09-14 10:00+08", "2031-09-14 12:00+08");
  createThrowawayBooking(event, venue.id, "2031-09-14 10:00+08", "2031-09-14 12:00+08", "approved");
  await seedSession(page, await sharedSessions("venue_staff"));

  await page.goto(`/venues/${venue.id}`);
  await page.getByRole("button", { name: "Block venue" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Block start").fill("2031-09-14T09:00");
  await dialog.getByLabel("Block end").fill("2031-09-14T13:00");
  await dialog.getByLabel("Reason (required)").selectOption("equipment_failure");
  await dialog.getByLabel("Detail (optional)").fill("Projector rig down");

  // Preview: nothing saved yet, the booking is listed.
  await dialog.getByRole("button", { name: "Block venue" }).click();
  await expect(dialog).toContainText("This block overlaps 1 booking");
  await expect(dialog).toContainText(event.name);

  await dialog.getByRole("button", { name: "Block anyway" }).click();
  await expect(dialog).toContainText("Venue blocked");
  await expect(dialog).toContainText("1 booking affected");
  const affected = dialog.getByTestId("block-affected");
  await expect(affected).toContainText(event.name);
  await expect(affected).toContainText("Confirmed");
  await expect(affected).toContainText("Equipment failure");

  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("tab", { name: /Blocks/ }).click();
  await expect(page.getByTestId("upcoming-blocks")).toContainText("Equipment failure");
  await expect(page.getByTestId("upcoming-blocks")).toContainText("Projector rig down");
});

test("TC-BLOCK-015 the form names a missing reason and an end before the start, and sends nothing", async ({
  page,
  sharedSessions,
}) => {
  const venue = createThrowawayVenue("B015");
  await seedSession(page, await sharedSessions("venue_staff"));
  let sent = false;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith(`/venues/${venue.id}/blocks`)) sent = true;
  });

  await page.goto(`/venues/${venue.id}`);
  await page.getByRole("button", { name: "Block venue" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Block start").fill("2031-09-15T13:00");
  await dialog.getByLabel("Block end").fill("2031-09-15T09:00");
  await dialog.getByRole("button", { name: "Block venue" }).click();

  await expect(dialog).toContainText("End must be after start.");
  await expect(dialog).toContainText("Choose a reason.");
  expect(sent).toBe(false);
});

test("TC-BLOCK-016 a coordinator sees no Block venue action", async ({ page, sharedSessions }) => {
  const venue = createThrowawayVenue("B016");
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/venues/${venue.id}`);
  await expect(page.getByRole("heading", { name: venue.name })).toBeVisible();
  await expect(page.getByRole("button", { name: "Block venue" })).toHaveCount(0);
});
