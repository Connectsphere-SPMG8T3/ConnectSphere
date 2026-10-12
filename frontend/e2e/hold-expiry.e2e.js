// Tentative hold expiry (CR-99) against real data. Cases: docs/test-cases/venues.md.
import { expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayEvent, createThrowawayHold } from "./support/throwaway.js";

const INNOVATION_LAB = "b0000000-0000-4000-8000-000000000006";

test("TC-HOLD-004 venue staff change a hold's expiry from the dashboard", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("H004", "2031-06-24 10:00+08", "2031-06-24 12:00+08");
  const hold = createThrowawayHold(
    event, INNOVATION_LAB, "2031-06-24 10:00+08", "2031-06-24 12:00+08", "held", "2031-06-01 12:00+08",
  );
  await seedSession(page, await sharedSessions("venue_staff"));

  await page.goto("/dashboard/venue-staff");
  const expiry = page.getByTestId(`hold-expiry-${hold.id}`);
  await expect(expiry).toContainText("Expires 1 Jun 2031, 12:00");
  await expiry.locator("..").getByRole("button", { name: "Change" }).click();

  await page.getByLabel("New expiry (Singapore time)").fill("2031-06-10T09:30");
  await page.getByRole("button", { name: "Save expiry" }).click();

  await expect(page.getByTestId(`hold-expiry-${hold.id}`)).toContainText("Expires 10 Jun 2031, 09:30");
  await expect(page.getByRole("button", { name: "Save expiry" })).toHaveCount(0);
});

test("TC-HOLD-005 the coordinator sees an expired hold and can look for a venue again", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("H005", "2031-06-25 10:00+08", "2031-06-25 12:00+08");
  createThrowawayHold(event, INNOVATION_LAB, "2031-06-25 10:00+08", "2031-06-25 12:00+08", "expired", "2031-06-01 12:00+08");
  await seedSession(page, await sharedSessions("event_coordinator"));

  await page.goto(`/coordinator/events/${event.id}`);
  const panel = page.getByTestId("venue-panel");
  await expect(panel).toContainText("Innovation Lab");
  await expect(panel).toContainText("Expired");
  await expect(panel).toContainText("The hold expired on 1 Jun 2031, 12:00");
  await panel.getByRole("button", { name: "Find a venue" }).click();
  await expect(page).toHaveURL(new RegExp(`/venues\\?event=${event.id}`));
});
