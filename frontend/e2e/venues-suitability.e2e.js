// Venue suitability (SCRUM-18) against real data. Cases: docs/test-cases/venues.md.
import { expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayEvent, createThrowawaySpace, setThrowawayEventAccessibilityNeeds } from "./support/throwaway.js";

test("TC-SUIT-005 a search opened from a space shows suitability beside availability, and the request dialog repeats it", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("SUIT005", "2031-07-20 10:00+08", "2031-07-20 12:00+08");
  const space = createThrowawaySpace(event, "Breakout", 10);
  await seedSession(page, await sharedSessions("event_coordinator"));
  const searched = page.waitForRequest((request) => request.url().includes("/venues?") && request.url().includes("space_id="));

  await page.goto(`/venues?event=${event.id}&space=${space.id}`);

  const request = await searched;
  expect(request.url()).toContain(`event_id=${event.id}`);
  const lab = page.getByTestId("venue-result").filter({ has: page.getByRole("heading", { name: "Innovation Lab" }) });
  await expect(lab.getByTestId("suitability-badge")).toBeVisible();
  await expect(lab.getByTestId("availability-badge")).toHaveText("Available");

  await lab.getByRole("button", { name: "Request Innovation Lab" }).click();
  await expect(page.getByRole("dialog").getByTestId("suitability-badge")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
});

test("TC-SUIT-006 a plain venue search shows no suitability", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_coordinator"));

  await page.goto("/venues");

  await expect(page.getByTestId("availability-badge").first()).toBeVisible();
  await expect(page.getByTestId("suitability-badge")).toHaveCount(0);
});

test("TC-SUIT-009 a venue with warnings is requested only after the warnings are acknowledged (BR-R3)", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("SUIT009", "2031-07-21 10:00+08", "2031-07-21 12:00+08");
  setThrowawayEventAccessibilityNeeds(event, "Quiet room for sensory breaks");
  await seedSession(page, await sharedSessions("event_coordinator"));

  await page.goto(`/venues?event=${event.id}`);

  const lab = page.getByTestId("venue-result").filter({ has: page.getByRole("heading", { name: "Innovation Lab" }) });
  await expect(lab.getByTestId("suitability-badge")).toHaveText("Suitable with warnings");
  await lab.getByRole("button", { name: "Request Innovation Lab" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Request venue" })).toBeDisabled();
  await dialog.getByTestId("acknowledge-warnings").check();
  await expect(dialog.getByRole("button", { name: "Request venue" })).toBeEnabled();
  await dialog.getByRole("button", { name: "Cancel" }).click();
});
