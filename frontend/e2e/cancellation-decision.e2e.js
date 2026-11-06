// Story 115 and 115-R in a real browser, on throwaway events: the assigned coordinator approves
// the organiser's open request, or cancels a confirmed event directly. Cases: docs/test-cases/events.md.
import {
  createThrowawayCancellationRequest, createThrowawayEvent, createThrowawayRegistrationEvent, readThrowawayEvent,
} from "./support/throwaway.js";
import { expect, seedSession, test } from "./support/fixtures.js";

const REQUEST_REASON = "live-check: keynote speaker withdrew";
const CANCEL_REASON = "live-check: no replacement venue";

test("TC-CANCEL-019 the coordinator approves the organiser's cancellation request", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("cancel-approve", "2031-11-10 09:00+08", "2031-11-10 12:00+08");
  createThrowawayCancellationRequest(event, REQUEST_REASON);
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);

  const banner = page.getByTestId("cancellation-request-banner");
  await expect(banner).toContainText(REQUEST_REASON);
  await banner.getByRole("button", { name: "Approve cancellation" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Approve the cancellation?");
  const sent = page.waitForResponse((r) => r.url().endsWith(`/events/${event.id}/cancellation-request/approve`));
  await dialog.getByRole("button", { name: "Cancel the event" }).click();

  expect((await sent).status()).toBe(200);
  await expect(banner).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Cancel event" })).toHaveCount(0);
  expect(readThrowawayEvent(event.id).status).toBe("cancelled");
});

test("TC-CANCEL-020 the coordinator cancels a confirmed event directly with a reason", async ({ page, sharedSessions }) => {
  const event = createThrowawayRegistrationEvent("cancel-direct", "2031-11-11 09:00+08", "2031-11-11 12:00+08");
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);

  await page.getByRole("button", { name: "Cancel event" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Confirm cancel event" })).toBeDisabled();
  await dialog.getByLabel("Reason (required)").fill(CANCEL_REASON);
  const sent = page.waitForResponse((r) => r.url().endsWith(`/events/${event.id}/cancel`));
  await dialog.getByRole("button", { name: "Confirm cancel event" }).click();

  expect((await sent).status()).toBe(200);
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Cancel event" })).toHaveCount(0);
  await expect(page.getByText(CANCEL_REASON)).toBeVisible();
  expect(readThrowawayEvent(event.id).status).toBe("cancelled");
});

test("TC-CANCEL-027 a planning event offers Reject, not Cancel event", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("reject-only", "2031-11-15 09:00+08", "2031-11-15 12:00+08");
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);

  await expect(page.getByRole("button", { name: "Open reject dialog" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Cancel event" })).toHaveCount(0);
});

test("TC-CANCEL-028 an open request is answered first, then Reject comes back", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("answer-first", "2031-11-16 09:00+08", "2031-11-16 12:00+08");
  createThrowawayCancellationRequest(event, REQUEST_REASON);
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);

  const banner = page.getByTestId("cancellation-request-banner");
  await expect(banner).toContainText(REQUEST_REASON);
  await expect(page.getByRole("button", { name: "Open reject dialog" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Cancel event" })).toHaveCount(0);

  await banner.getByRole("button", { name: "Reject cancellation" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Reason (required)").fill(CANCEL_REASON);
  await dialog.getByRole("button", { name: "Reject cancellation request" }).click();

  await expect(banner).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open reject dialog" })).toBeVisible();
});
