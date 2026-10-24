// Story 32 in a real browser, on a throwaway planning event: the organiser proposes
// changes in the request form and the assigned coordinator sees them. Cases:
// docs/test-cases/events.md.
import { createThrowawayEvent, createThrowawaySpace, readThrowawayEvent } from "./support/throwaway.js";
import { expect, seedSession, test } from "./support/fixtures.js";

const REASON = "live-check: sponsor wants more seats";

test("TC-CHANGE-008 the organiser requests changes and the coordinator sees them", async ({ browser, page, sharedSessions }) => {
  const event = createThrowawayEvent("change", "2031-11-11 09:00+08", "2031-11-11 12:00+08");
  createThrowawaySpace(event, "Main hall", 20, "theatre");
  await seedSession(page, await sharedSessions("event_organiser"));
  await page.goto(`/events/${event.id}`);

  await page.getByRole("button", { name: "Request changes" }).click();
  await expect(page).toHaveURL(new RegExp(`/events/${event.id}/request-change$`));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Request changes");
  const send = page.getByRole("button", { name: "Send change request" });
  await expect(send).toBeDisabled();
  await expect(page.getByRole("button", { name: "Add space request" })).toHaveCount(0);

  // The form fills in once the event has loaded; typing before that would be overwritten.
  await expect(page.getByLabel("Expected attendance")).toHaveValue("20");
  await page.getByLabel("Expected attendance").fill("40");
  await page.getByLabel("Expected pax").fill("40");
  await send.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByTestId("change-summary")).toContainText("Expected attendance: 20 → 40");
  await expect(dialog.getByTestId("change-summary")).toContainText("Main hall: attendance: 20 → 40");
  await dialog.getByLabel("Reason (required)").fill(REASON);
  const sent = page.waitForResponse((r) => r.url().endsWith(`/events/${event.id}/change-request`));
  await dialog.getByRole("button", { name: "Send change request" }).click();

  expect((await sent).status()).toBe(201);
  await expect(page).toHaveURL(new RegExp(`/events/${event.id}$`));
  const banner = page.getByTestId("change-request-banner");
  await expect(banner).toContainText("Change requested");
  await expect(banner).toContainText("Expected attendance: 20 → 40");
  await expect(banner).toContainText(REASON);
  await expect(page.getByRole("button", { name: "Request changes" })).toHaveCount(0);
  expect(readThrowawayEvent(event.id).status).toBe("planning");

  // A session is seeded once per tab, so the coordinator gets a browser context of their own.
  const coordinatorContext = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  const coordinatorPage = await coordinatorContext.newPage();
  await seedSession(coordinatorPage, await sharedSessions("event_coordinator"));
  await coordinatorPage.goto(`/coordinator/events/${event.id}`);
  const coordinatorBanner = coordinatorPage.getByTestId("change-request-banner");
  await expect(coordinatorBanner).toContainText("Significant change");
  await expect(coordinatorBanner).toContainText("Main hall: attendance: 20 → 40");
  await expect(coordinatorBanner).toContainText(REASON);
  await coordinatorContext.close();
});
