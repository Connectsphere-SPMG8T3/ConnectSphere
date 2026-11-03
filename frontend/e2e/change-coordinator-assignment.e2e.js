// SCRUM-81 in a real browser, on throwaway planning events: the Lead sees an event's
// reassignments on its page, and a coordinator's page that was already open when the event
// was reassigned is refused. Cases: docs/test-cases/dashboards.md.
import { createThrowawayEvent, readThrowawayEvent } from "./support/throwaway.js";
import { expect, seedSession, test } from "./support/fixtures.js";

const PREVIOUS_COORDINATOR = "a0000000-0000-4000-8000-000000000002";
const REASON = "live-check: the venue is not available";

// The Lead reassigns through the page, as they would: the first real coordinator other than
// the current one, then the confirmation. Returns that coordinator's name.
async function reassignThroughThePage(leadPage, eventId) {
  await leadPage.goto(`/lead/events/${eventId}`);
  const picker = leadPage.getByLabel("Choose a coordinator");
  await expect(picker).toBeVisible();
  await picker.selectOption({ index: 1 });
  const name = (await picker.locator("option:checked").textContent()).trim();
  await leadPage.getByRole("button", { name: "Reassign event" }).click();
  const moved = leadPage.waitForResponse((r) => r.url().endsWith(`/events/${eventId}/reassign`));
  await leadPage.getByRole("dialog").getByRole("button", { name: "Reassign" }).click();
  expect((await moved).status()).toBe(200);
  return name;
}

test("TC-ASSIGN-022 the Lead sees an event's reassignments on its page", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("81-history", "2031-12-02 09:00+08", "2031-12-02 12:00+08");
  await seedSession(page, await sharedSessions("event_coordinator_lead"));

  const history = page.getByTestId("reassignment-history");
  const loaded = page.waitForResponse((r) => r.url().endsWith(`/events/${event.id}/reassignment-history`));
  await page.goto(`/lead/events/${event.id}`);
  expect((await loaded).status()).toBe(200);
  await expect(history.getByRole("heading", { name: "Reassignment history" })).toBeVisible();
  await expect(history).toContainText("No reassignments yet.");

  const name = await reassignThroughThePage(page, event.id);

  await page.goto(`/lead/events/${event.id}`);
  await expect(history).not.toContainText("No reassignments yet.");
  await expect(history).toContainText(`Reassigned to ${name}`);
  await expect(history).toContainText("Marcus Lim");
  await expect(history).toContainText("Grace Chua");
  expect(readThrowawayEvent(event.id).coordinator_id).not.toBe(PREVIOUS_COORDINATOR);
});

test("TC-ASSIGN-023 a coordinator's page that was already open is refused after the reassignment", async ({
  browser,
  page,
  sharedSessions,
}) => {
  const event = createThrowawayEvent("81-stale", "2031-12-03 09:00+08", "2031-12-03 12:00+08");
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);
  await expect(page.getByRole("heading", { name: event.name })).toBeVisible();

  // Meanwhile the Lead moves the event, in a context of their own.
  const leadContext = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  const leadPage = await leadContext.newPage();
  await seedSession(leadPage, await sharedSessions("event_coordinator_lead"));
  await reassignThroughThePage(leadPage, event.id);
  await leadContext.close();

  // The first coordinator's page still shows the actions, and the write is refused.
  await page.getByRole("button", { name: "Open reject dialog" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Reason (required)").fill(REASON);
  const refused = page.waitForResponse((r) => r.url().endsWith(`/events/${event.id}/reject`));
  await dialog.getByRole("button", { name: "Reject request" }).click();

  expect((await refused).status()).toBe(403);
  await expect(dialog.getByRole("alert")).toContainText("Only the event's assigned coordinator can do this.");
  expect(readThrowawayEvent(event.id).status).toBe("planning");
  expect(readThrowawayEvent(event.id).coordinator_id).not.toBe(PREVIOUS_COORDINATOR);
});
