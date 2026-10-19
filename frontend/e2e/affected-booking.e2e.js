// A venue block over a booked event (CR-95) against real data, on a throwaway
// Confirmed event, whose booking sits on the event's first space. Cases: docs/test-cases/venues.md (TC-BOOK-048 to 050).
import { expect, seedSession, test } from "./support/fixtures.js";
import {
  createThrowawayBlock,
  createThrowawayBooking,
  createThrowawayEvent,
  deleteThrowawayBlocks,
  readThrowawayBooking,
  setThrowawayEventStatus,
} from "./support/throwaway.js";

const SEMINAR_ROOM_1 = "b0000000-0000-4000-8000-000000000003";
const STARTS = "2031-12-01 10:00+08";
const ENDS = "2031-12-01 12:00+08";

test.afterEach(() => deleteThrowawayBlocks());

test("TC-BOOK-048/049/050 a block flags a Confirmed event; the coordinator replaces, venue staff restore", async ({
  page,
  browser,
  baseURL,
  sharedSessions,
}) => {
  const event = createThrowawayEvent("cr95", STARTS, ENDS);
  setThrowawayEventStatus(event, "confirmed");
  const booking = createThrowawayBooking(event, SEMINAR_ROOM_1, STARTS, ENDS, "approved");
  createThrowawayBlock(SEMINAR_ROOM_1, "2031-12-01 00:00+08", "2031-12-02 00:00+08");

  // AC1, AC2: flagged, not cancelled, the event still Confirmed.
  expect(readThrowawayBooking(booking.id)).toEqual({ status: "approved", flag: "affected" });

  // AC3: the coordinator's dashboard leads with the alert.
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto("/dashboard/coordinator");
  await expect(page.getByText("Needs alternative venue").first()).toBeVisible();
  await expect(page.getByText(event.name).first()).toBeVisible();

  // AC3, AC4: the event's space card (the booking is linked to the event's first space)
  // says why and opens a pre-filled search.
  await page.goto(`/coordinator/events/${event.id}`);
  const panel = page.getByTestId("event-spaces").locator("article").first();
  await expect(panel).toContainText("Seminar Room 1");
  await expect(panel).toContainText("Needs alternative venue");
  await expect(panel).toContainText("Venue unavailable: Maintenance");
  await panel.getByRole("button", { name: "Find replacement" }).click();
  await expect(page).toHaveURL(new RegExp(`replaces=${booking.id}`));

  // AC4, AC7: the dialog says what happens; requesting returns the event to Planning.
  await page.getByRole("button", { name: "Request Innovation Lab" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("replaces Seminar Room 1");
  await expect(dialog).toContainText("back to Planning");
  await dialog.getByRole("button", { name: "Request venue" }).click();

  await expect(page).toHaveURL(new RegExp(`/coordinator/events/${event.id}`));
  await expect(panel).toContainText("Replacement requested");
  await expect(panel).toContainText("Innovation Lab");
  await expect(panel.getByRole("button", { name: "Find replacement" })).toHaveCount(0);
  await expect(page.getByText("Planning", { exact: true }).first()).toBeVisible();
  // AC6: the original is untouched beside it.
  expect(readThrowawayBooking(booking.id)).toEqual({ status: "approved", flag: "affected" });

  // AC9: venue staff find it, and cannot restore while the block stands.
  // Venue staff are a different session, so their own browser context.
  const staffContext = await browser.newContext({ baseURL });
  const staffPage = await staffContext.newPage();
  await seedSession(staffPage, await sharedSessions("venue_staff"));
  await staffPage.goto(`/bookings/${booking.id}`);
  await expect(staffPage.getByTestId("booking-affected")).toContainText("Venue unavailable: Maintenance");
  await staffPage.getByRole("button", { name: "Restore original booking" }).click();
  await expect(staffPage.getByRole("alert")).toContainText("still blocked");

  // The block goes; now the booking can be restored and the replacement is cancelled.
  deleteThrowawayBlocks();
  await staffPage.reload();
  await staffPage.getByRole("button", { name: "Restore original booking" }).click();
  await expect(staffPage.getByTestId("booking-affected")).toHaveCount(0);
  expect(readThrowawayBooking(booking.id)).toEqual({ status: "approved", flag: null });
  await staffContext.close();
});
