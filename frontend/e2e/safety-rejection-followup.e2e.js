// D51: written for the post-migration run; changes disposable records only.
import { expect, seedSession, test } from "./support/fixtures.js";
import {
  createThrowawayBooking,
  createThrowawayEvent,
  createThrowawayVenue,
  setThrowawayBookingSafetyRejected,
} from "./support/throwaway.js";

test("TC-SDEC-033 coordinator replaces a Safety-rejected venue from its notice", async ({ page, sharedSessions }) => {
  const starts = "2031-08-21 10:00+08", ends = "2031-08-21 12:00+08";
  const event = createThrowawayEvent("SDEC033", starts, ends);
  const oldVenue = createThrowawayVenue("SDEC033 old");
  const replacement = createThrowawayVenue("SDEC033 replacement");
  const booking = createThrowawayBooking(event, oldVenue.id, starts, ends, "approved");
  setThrowawayBookingSafetyRejected(booking.id);
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);
  const notice = page.getByTestId("venue-safety-rejected");
  await expect(notice).toContainText("Safety rejected");
  await notice.getByRole("button", {name: "Replace venue", exact: true}).click();
  await expect(page).toHaveURL(new RegExp(`replaces=${booking.id}`));
  await page.getByRole("button", {name: `Request ${replacement.name}`, exact: true}).click();
  await page.getByRole("dialog").getByRole("button", {name: "Request venue", exact: true}).click();
  await expect(page).toHaveURL(new RegExp(`/coordinator/events/${event.id}`));
  await expect(notice).toContainText(`Replacement requested: ${replacement.name}`);
  await expect(notice.getByRole("button", {name: "Mark as revised", exact: true})).toHaveCount(0);
  await expect(notice.getByRole("button", {name: "Replace venue", exact: true})).toHaveCount(0);
});
