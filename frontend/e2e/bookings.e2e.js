// Venue booking request (SCRUM-19) against real data. Cases: docs/test-cases/venues.md.
import { expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayEvent } from "./support/throwaway.js";

test("TC-BOOK-008 a coordinator finds a venue from the event and requests it", async ({ page, sharedSessions }) => {
  // 26 May 2031, 10:00–12:00 Singapore time: far enough ahead that nothing real is booked.
  const event = createThrowawayEvent("008", "2031-05-26 10:00+08", "2031-05-26 12:00+08");
  await seedSession(page, await sharedSessions("event_coordinator"));

  await page.goto(`/coordinator/events/${event.id}`);
  const panel = page.getByTestId("venue-panel");
  await expect(panel).toContainText("No venue requested yet");
  await panel.getByRole("button", { name: "Find a venue" }).click();

  // The search opens pre-filled with the event's date and times.
  await expect(page).toHaveURL(new RegExp(`/venues\\?event=${event.id}`));
  await expect(page.getByTestId("booking-event-context")).toContainText(event.name);
  await page.getByRole("button", { name: "Request Innovation Lab" }).click();

  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Note for venue staff (optional)").fill("Early access at 09:30 please");
  await dialog.getByRole("button", { name: "Request venue" }).click();

  // Back on the event, which now shows the tentative hold.
  await expect(page).toHaveURL(`/coordinator/events/${event.id}`);
  await expect(page.getByTestId("venue-panel")).toContainText("Innovation Lab");
  await expect(page.getByTestId("venue-panel")).toContainText("Tentative hold");
});
