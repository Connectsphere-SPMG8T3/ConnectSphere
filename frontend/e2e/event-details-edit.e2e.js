// The assigned coordinator edits an event's ordinary details (story 112) against real data.
// Cases: docs/test-cases/events.md. Every check uses a throwaway 2031 event, deleted after the run.
import { expect, seedSession, test } from "./support/fixtures.js";
import { bumpThrowawayEventVersion, createThrowawayEvent, setThrowawayEventStatus } from "./support/throwaway.js";

test("TC-EDIT-005 the coordinator edits the description; it saves, the History shows it, and the organiser sees it too", async ({ page, browser, sharedSessions }) => {
  const event = createThrowawayEvent("EDIT005", "2031-12-22 09:00+08", "2031-12-22 12:00+08");
  setThrowawayEventStatus(event, "planning");

  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);
  await page.getByRole("button", { name: "Edit event details" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("change request");
  await dialog.getByLabel("Description").fill("Agreed with the organiser by phone");
  await dialog.getByRole("button", { name: "Save details" }).click();

  await expect(dialog).toBeHidden();
  await expect(page.getByText("Event details saved")).toBeVisible();
  const edit = page.getByRole("listitem").filter({ hasText: "Description changed" });
  await expect(edit).toContainText("To: Agreed with the organiser by phone");
  await expect(page.locator("body")).toContainText("Agreed with the organiser by phone");

  const context = await browser.newContext();
  try {
    const organiserPage = await context.newPage();
    await seedSession(organiserPage, await sharedSessions("event_organiser"));
    await organiserPage.goto(`/events/${event.id}`);
    await expect(organiserPage.getByRole("listitem").filter({ hasText: "Description changed" })).toContainText("To: Agreed with the organiser by phone");
  } finally {
    await context.close();
  }
});

test("TC-EDIT-006 the form can't change a significant field, and a returned request has no Edit button", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("EDIT006", "2031-12-23 09:00+08", "2031-12-23 12:00+08");
  setThrowawayEventStatus(event, "planning");

  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);
  await page.getByRole("button", { name: "Edit event details" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("textbox")).toHaveCount(4);
  for (const label of ["Name", "Purpose", "Description", "Accessibility notes"]) {
    await expect(dialog.getByLabel(label)).toBeVisible();
  }
  await expect(dialog.getByLabel(/start|end|attendance|venue|equipment/i)).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "Save details" })).toBeDisabled();

  setThrowawayEventStatus(event, "returned");
  await page.reload();
  await expect(page.getByRole("button", { name: "Edit event details" })).toHaveCount(0);
});

test("TC-EDIT-007 saving after someone else did shows the reload message and keeps their change", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("EDIT007", "2031-12-24 09:00+08", "2031-12-24 12:00+08");
  setThrowawayEventStatus(event, "planning");

  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);
  await page.getByRole("button", { name: "Edit event details" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Description").fill("My version from a stale page");
  // Someone else saves first, so the version the page loaded is out of date.
  bumpThrowawayEventVersion(event);
  await dialog.getByRole("button", { name: "Save details" }).click();

  await expect(dialog.getByRole("alert")).toContainText("This event was updated by someone else. Reload.");
  await dialog.getByRole("button", { name: "Reload event" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.locator("body")).not.toContainText("My version from a stale page");
});
