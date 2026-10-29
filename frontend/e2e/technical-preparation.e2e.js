// Technical preparation (CR-110) against real data. Cases: docs/test-cases/equipment.md.
// Every check uses a throwaway 2031 event, deleted after the run.
import { expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayEvent, setThrowawayEventStatus } from "./support/throwaway.js";

test("TC-TPREP-012 tech support record a stage on a Confirmed event; the organiser sees the stage, never the note", async ({ page, browser, sharedSessions }) => {
  const event = createThrowawayEvent("TPREP012", "2031-12-10 09:00+08", "2031-12-10 12:00+08");
  setThrowawayEventStatus(event, "confirmed");

  await seedSession(page, await sharedSessions("tech_support"));
  await page.goto(`/tech-support/events/${event.id}`);
  const card = page.getByTestId("technical-preparation");
  await expect(card.getByLabel("Stage")).toHaveValue("not_started");
  await card.getByLabel("Stage").selectOption("in_progress");
  await card.getByLabel("Preparation notes (internal)").fill("Live-check cabling note");
  await card.getByRole("button", { name: "Save preparation" }).click();

  // AC3: the first update moves the event to Preparation; AC5: the history records it.
  await expect(page.getByText("Event status", { exact: true }).locator("..")).toContainText("Preparation");
  await expect(card).toContainText("Last updated by");
  await expect(page.getByRole("list").filter({ hasText: "Preparation stage changed" })).toContainText("Not started → In progress");

  // AC4: the organiser's Arrangements card shows the stage only. A session is
  // seeded once per tab, so the organiser gets a browser context of their own.
  const context = await browser.newContext();
  try {
    const organiserPage = await context.newPage();
    await seedSession(organiserPage, await sharedSessions("event_organiser"));
    await organiserPage.goto(`/events/${event.id}`);
    await expect(organiserPage.getByText("Technical preparation: In progress")).toBeVisible();
    await expect(organiserPage.locator("body")).not.toContainText("Live-check cabling note");
  } finally {
    await context.close();
  }
});

test("TC-TPREP-013 technical preparation is locked until the Safety Officer confirms the event", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("TPREP013", "2031-12-11 09:00+08", "2031-12-11 12:00+08");

  await seedSession(page, await sharedSessions("tech_support"));
  await page.goto(`/tech-support/events/${event.id}`);
  const card = page.getByTestId("technical-preparation");
  await expect(card).toContainText("Technical preparation opens once the Safety Officer has confirmed the event.");
  await expect(card.getByLabel("Stage")).toBeDisabled();
  await expect(card.getByRole("button", { name: "Save preparation" })).toHaveCount(0);
});
