// An event's change history (story 62) against real data. Cases: docs/test-cases/events.md.
// Every check uses a throwaway 2031 event, deleted after the run.
import { expect, seedSession, test } from "./support/fixtures.js";
import {
  createThrowawayEdit,
  createThrowawayEvent,
  createThrowawayTechnicalEntry,
  setThrowawayEventStatus,
} from "./support/throwaway.js";

test("TC-HIST-011 both sides see an edit with its old and new value; only the coordinator sees technical updates", async ({ page, browser, sharedSessions }) => {
  const event = createThrowawayEvent("HIST011", "2031-12-13 09:00+08", "2031-12-13 12:00+08");
  setThrowawayEventStatus(event, "planning");
  createThrowawayEdit(event, "description", "Before the keynote", "Now with a keynote");
  createThrowawayTechnicalEntry(event, "preparation");

  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);
  const coordinatorEdit = page.getByRole("listitem").filter({ hasText: "Description changed" });
  await expect(coordinatorEdit).toContainText("by Olivia Tan");
  await expect(coordinatorEdit).toContainText("From: Before the keynote");
  await expect(coordinatorEdit).toContainText("To: Now with a keynote");
  await expect(page.getByRole("listitem").filter({ hasText: "Equipment: Preparation stage changed" })).toBeVisible();

  // A session is seeded once per tab, so the organiser gets a browser context of their own.
  const context = await browser.newContext();
  try {
    const organiserPage = await context.newPage();
    await seedSession(organiserPage, await sharedSessions("event_organiser"));
    await organiserPage.goto(`/events/${event.id}`);
    await expect(organiserPage.getByRole("listitem").filter({ hasText: "Description changed" })).toContainText("To: Now with a keynote");
    await expect(organiserPage.locator("body")).not.toContainText("Equipment: Preparation stage changed");
  } finally {
    await context.close();
  }
});
