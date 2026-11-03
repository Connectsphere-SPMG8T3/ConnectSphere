// CR-108: the Safety Officer's checklist in a real browser. Changes disposable records only.
// Set E2E_SCREENSHOT_DIR to also save the PR screenshots (docs/screenshots/<branch-name>/).
import path from "node:path";
import { expect, seedSession, test } from "./support/fixtures.js";
import {
  createThrowawayBooking,
  createThrowawayEvent,
  createThrowawayVenue,
  readThrowawayEvent,
  setThrowawayEventStatus,
} from "./support/throwaway.js";

const PRIVATE_NOTE = "PRIVATE-NOTE-SDEC046";
const CHECKLIST_NOTE = "CHECKLIST-NOTE-SDEC046";
const COMMENT = "Widen the aisle by the stage";

// The runner's login can hit a keep-alive connection the backend already closed (ECONNRESET, and
// Node does not retry a POST). Signing in again is harmless, so retry that error only.
async function signedIn(sharedSessions, role) {
  for (let attempt = 1; ; attempt++) {
    try {
      return await sharedSessions(role);
    } catch (error) {
      if (attempt >= 3 || !String(error.cause?.message ?? error.message).match(/ECONNRESET|fetch failed/)) throw error;
    }
  }
}

async function shot(page, name) {
  if (process.env.E2E_SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.E2E_SCREENSHOT_DIR, name), fullPage: true });
}

test("TC-SDEC-046 officer completes the checklist; the organiser sees the comment, never the private note", async ({ page, context, sharedSessions }) => {
  test.setTimeout(90_000); // about 30s of steps; the default limit is 30s
  const starts = "2031-09-10 10:00+08", ends = "2031-09-10 12:00+08";
  const event = createThrowawayEvent("SDEC046", starts, ends);
  const venue = createThrowawayVenue("SDEC046");
  createThrowawayBooking(event, venue.id, starts, ends, "approved");
  setThrowawayEventStatus(event, "safety_review");

  // Sign every role in up front: a session opened early would sit idle through the form work and
  // the backend closes idle connections, which makes a later login on the same socket fail.
  const officerSession = await signedIn(sharedSessions, "safety_officer");
  const organiserSession = await signedIn(sharedSessions, "event_organiser");
  const coordinatorSession = await signedIn(sharedSessions, "event_coordinator");

  await seedSession(page, officerSession);
  await page.goto(`/safety/events/${event.id}`);
  const request = page.getByRole("button", { name: "Request changes", exact: true });
  const approve = page.getByRole("button", { name: "Approve", exact: true });

  // AC3: nothing can be decided until every factor is marked.
  await expect(page.getByText("6 checklist marks still to make.")).toBeVisible();
  await page.locator("#safety-organiser-comment").fill(COMMENT);
  await expect(request).toBeDisabled();
  await expect(approve).toBeDisabled();
  await shot(page, "officer-checklist-empty.png");

  // AC1, AC2: five factors for the venue, equipment placement for the whole event.
  for (const radio of await page.getByRole("radio", { name: "Satisfactory" }).all()) await radio.check();
  await expect(page.getByText("still to make")).toHaveCount(0);
  await expect(approve).toBeEnabled();
  await expect(request).toBeEnabled();

  // Team decision: a Concern blocks approval but not a request for changes.
  await page.getByRole("radio", { name: "Concern" }).nth(1).check();
  await page.getByLabel(/^Layout note for /).fill(CHECKLIST_NOTE);
  await expect(approve).toBeDisabled();
  await expect(page.getByText("Approval isn't available while a factor is marked Concern.")).toBeVisible();
  await expect(request).toBeEnabled();
  await page.locator("#safety-private-note").fill(PRIVATE_NOTE);
  await shot(page, "officer-checklist-complete.png");

  await request.click();
  await page.getByRole("dialog").getByRole("button", { name: "Request changes", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard\/safety/);
  expect(readThrowawayEvent(event.id).status).toBe("planning");

  // AC5: the organiser sees the outcome and the comment, and nothing else the officer wrote.
  // A new tab per role: seedSession writes the session once per tab.
  const organiser = await context.newPage();
  await seedSession(organiser, organiserSession);
  await organiser.goto(`/events/${event.id}`);
  await expect(organiser.getByText("Comment from the Safety Officer")).toBeVisible();
  await expect(organiser.getByText(COMMENT)).toBeVisible();
  await expect(organiser.getByText("The Safety Officer asked for changes to the arrangements.")).toBeVisible();
  for (const secret of [PRIVATE_NOTE, CHECKLIST_NOTE]) await expect(organiser.getByText(secret)).toHaveCount(0);
  expect(await organiser.content()).not.toContain(PRIVATE_NOTE);
  await shot(organiser, "organiser-sees-comment.png");

  // The assigned coordinator sees the comment, the private note and the checklist.
  const coordinator = await context.newPage();
  await seedSession(coordinator, coordinatorSession);
  await coordinator.goto(`/coordinator/events/${event.id}`);
  await expect(coordinator.getByText("Safety Officer's decision").first()).toBeVisible();
  await expect(coordinator.getByText(PRIVATE_NOTE).first()).toBeVisible();
  await expect(coordinator.getByText(CHECKLIST_NOTE).first()).toBeVisible();
  await shot(coordinator, "coordinator-sees-everything.png");
});
