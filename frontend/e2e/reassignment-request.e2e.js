// CR-106 in a real browser, on throwaway planning events: the assigned coordinator asks the Lead
// to reassign, and the Lead sees the request and declines it. Cases: docs/test-cases/dashboards.md.
import {
  createThrowawayEvent,
  createThrowawayReassignmentRequest,
  readThrowawayEvent,
  readThrowawayReassignmentRequests,
} from "./support/throwaway.js";
import { expect, seedSession, test } from "./support/fixtures.js";

const REASON = "live-check: on leave this month";
const DECLINE_REASON = "live-check: nobody else is free";

test("TC-REASSIGN-014 the coordinator asks for a reassignment and the Lead sees it", async ({ browser, page, sharedSessions }) => {
  const event = createThrowawayEvent("reassign-ask", "2031-11-14 09:00+08", "2031-11-14 12:00+08");
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);

  await page.getByRole("button", { name: "Request reassignment" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Ask the Lead to reassign this event?");
  await expect(dialog.getByRole("button", { name: "Send reassignment request" })).toBeDisabled();
  await dialog.getByLabel("Reason (required)").fill(REASON);
  const sent = page.waitForResponse((r) => r.url().endsWith(`/events/${event.id}/reassignment-request`));
  await dialog.getByRole("button", { name: "Send reassignment request" }).click();

  expect((await sent).status()).toBe(201);
  await expect(dialog).toHaveCount(0);
  const banner = page.getByTestId("reassignment-request-banner");
  await expect(banner).toContainText("Reassignment requested");
  await expect(banner).toContainText(REASON);
  await expect(page.getByRole("button", { name: "Request reassignment" })).toHaveCount(0);
  // The request changes nothing on its own (AC3).
  expect(readThrowawayEvent(event.id)).toMatchObject({ status: "planning", coordinator_id: "a0000000-0000-4000-8000-000000000002" });

  // It is in the coordinator's history.
  await expect(page.getByText("Reassignment requested").last()).toBeVisible();

  // A session is seeded once per tab, so the Lead gets a browser context of their own.
  const leadContext = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  const leadPage = await leadContext.newPage();
  await seedSession(leadPage, await sharedSessions("event_coordinator_lead"));
  await leadPage.goto(`/lead/events/${event.id}`);
  const leadBanner = leadPage.getByTestId("reassignment-request-banner");
  await expect(leadBanner).toContainText("asked to be reassigned");
  await expect(leadBanner).toContainText(REASON);
  await leadContext.close();
});

test("TC-REASSIGN-015 the Lead declines the request with a reason and the coordinator may ask again", async ({ browser, page, sharedSessions }) => {
  const event = createThrowawayEvent("reassign-decline", "2031-11-15 09:00+08", "2031-11-15 12:00+08");
  createThrowawayReassignmentRequest(event, REASON);
  await seedSession(page, await sharedSessions("event_coordinator_lead"));
  await page.goto(`/lead/events/${event.id}`);

  await page.getByRole("button", { name: "Decline request" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Decline the reassignment request?");
  await expect(dialog.getByRole("button", { name: "Confirm decline reassignment request" })).toBeDisabled();
  await dialog.getByLabel("Reason (required)").fill(DECLINE_REASON);
  const declined = page.waitForResponse((r) => r.url().endsWith(`/events/${event.id}/reassignment-request/decline`));
  await dialog.getByRole("button", { name: "Confirm decline reassignment request" }).click();

  expect((await declined).status()).toBe(200);
  await expect(dialog).toHaveCount(0);
  await expect(page.getByTestId("reassignment-request-banner")).toHaveCount(0);
  expect(readThrowawayReassignmentRequests(event.id)).toEqual([{ status: "declined", decision_reason: DECLINE_REASON }]);
  expect(readThrowawayEvent(event.id).coordinator_id).toBe("a0000000-0000-4000-8000-000000000002");

  // The coordinator is still assigned, sees no pending request, and may ask again.
  const coordinatorContext = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  const coordinatorPage = await coordinatorContext.newPage();
  await seedSession(coordinatorPage, await sharedSessions("event_coordinator"));
  await coordinatorPage.goto(`/coordinator/events/${event.id}`);
  await expect(coordinatorPage.getByTestId("reassignment-request-banner")).toHaveCount(0);
  await expect(coordinatorPage.getByRole("button", { name: "Request reassignment" })).toBeVisible();
  await expect(coordinatorPage.getByText("Reassignment request declined")).toBeVisible();
  await coordinatorContext.close();
});

test("TC-REASSIGN-016 the organiser's event page shows no reassignment request or button", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("reassign-denied", "2031-11-16 09:00+08", "2031-11-16 12:00+08");
  createThrowawayReassignmentRequest(event, REASON);
  await seedSession(page, await sharedSessions("event_organiser"));
  await page.goto(`/events/${event.id}`);

  await expect(page.getByText(REASON)).toHaveCount(0);
  await expect(page.getByTestId("reassignment-request-banner")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Request reassignment" })).toHaveCount(0);
});
