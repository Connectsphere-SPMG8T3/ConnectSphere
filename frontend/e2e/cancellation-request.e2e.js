// Story 84 in a real browser, on a throwaway planning event: the organiser asks to
// cancel and the assigned coordinator sees the request. Cases: docs/test-cases/events.md.
import { createThrowawayEvent, readThrowawayEvent } from "./support/throwaway.js";
import { expect, seedSession, test } from "./support/fixtures.js";

const REASON = "live-check: keynote speaker withdrew";

test("TC-CANCEL-009 the organiser requests cancellation and the coordinator sees it", async ({ browser, page, sharedSessions }) => {
  const event = createThrowawayEvent("cancel", "2031-10-08 09:00+08", "2031-10-08 12:00+08");
  await seedSession(page, await sharedSessions("event_organiser"));
  await page.goto(`/events/${event.id}`);

  await page.getByRole("button", { name: "Request cancellation" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Send request" })).toBeDisabled();
  await dialog.getByLabel("Reason (required)").fill(REASON);
  const sent = page.waitForResponse((r) => r.url().endsWith(`/events/${event.id}/cancellation-request`));
  await dialog.getByRole("button", { name: "Send request" }).click();

  expect((await sent).status()).toBe(201);
  await expect(dialog).toHaveCount(0);
  const banner = page.getByTestId("cancellation-request-banner");
  await expect(banner).toContainText("Cancellation requested");
  await expect(banner).toContainText(REASON);
  await expect(page.getByRole("button", { name: "Request cancellation" })).toHaveCount(0);
  await expect(page.getByText("Cancellation requested").last()).toBeVisible();
  expect(readThrowawayEvent(event.id).status).toBe("planning");

  // A session is seeded once per tab, so the coordinator gets a browser context of their own.
  const coordinatorContext = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  const coordinatorPage = await coordinatorContext.newPage();
  await seedSession(coordinatorPage, await sharedSessions("event_coordinator"));
  await coordinatorPage.goto(`/coordinator/events/${event.id}`);
  await expect(coordinatorPage.getByTestId("cancellation-request-banner")).toContainText(REASON);
  await coordinatorContext.close();
});
