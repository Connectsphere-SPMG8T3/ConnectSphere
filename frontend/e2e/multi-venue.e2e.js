// Several venues per event (CR-97) against real data. Cases: docs/test-cases/venues.md.
import { expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayEvent, createThrowawayHold, createThrowawaySpace } from "./support/throwaway.js";

const INNOVATION_LAB = "b0000000-0000-4000-8000-000000000006";

test("TC-BOOK-034 each space card shows its own booking, and the coordinator picks the primary venue", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("B034", "2031-06-26 10:00+08", "2031-06-26 12:00+08");
  const main = createThrowawaySpace(event, "Main hall", 20);
  createThrowawaySpace(event, "Breakout room", 10);
  createThrowawayHold(event, INNOVATION_LAB, "2031-06-26 10:00+08", "2031-06-26 12:00+08", "held", "2031-06-20 12:00+08", main.id);
  await seedSession(page, await sharedSessions("event_coordinator"));

  await page.goto(`/coordinator/events/${event.id}`);
  const cards = page.getByTestId("event-spaces").locator("article");
  const mainCard = cards.filter({ hasText: "Main hall" });
  const breakoutCard = cards.filter({ hasText: "Breakout room" });
  await expect(mainCard.getByTestId("space-booking")).toContainText("Innovation Lab");
  await expect(mainCard.getByTestId("space-booking")).toContainText("Tentative hold");
  await expect(mainCard.getByRole("link", { name: "Find venue" })).toHaveCount(0);
  await expect(breakoutCard.getByRole("link", { name: "Find venue" })).toBeVisible();

  await breakoutCard.getByRole("button", { name: "Make Breakout room the primary venue" }).click();
  await expect(breakoutCard.getByTestId("primary-badge")).toHaveText("Primary venue");
  await expect(mainCard.getByTestId("primary-badge")).toHaveCount(0);

  await page.reload();
  await expect(breakoutCard.getByTestId("primary-badge")).toHaveText("Primary venue");
  await breakoutCard.getByRole("button", { name: "Unset Breakout room as the primary venue" }).click();
  await expect(page.getByTestId("primary-badge")).toHaveCount(0);
});
