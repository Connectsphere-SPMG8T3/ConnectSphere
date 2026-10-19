// Equipment reservation (SCRUM-24) against real data. Cases: docs/test-cases/equipment.md.
// Every check uses a throwaway 2031 event and its own throwaway catalogue item,
// so seeded stock is never reserved; both are deleted after the run.
import { expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayEquipment, createThrowawayEvent, createThrowawayLine } from "./support/throwaway.js";

test("TC-EQR-027 TC-EQR-033 tech support reserve a line, tick the exit check, and the coordinator sees it Ready", async ({ page, browser, sharedSessions }) => {
  const event = createThrowawayEvent("EQR027", "2031-08-10 09:00+08", "2031-08-10 12:00+08");
  const item = createThrowawayEquipment("027", 3);
  createThrowawayLine(event, item, 2);

  await seedSession(page, await sharedSessions("tech_support"));
  // AC1: the dashboard's Active requests tile opens the requests page; from
  // there, open the event and reserve the line.
  await page.goto("/dashboard/tech-support");
  const tile = page.getByTestId("tile").filter({ hasText: "Active requests" });
  // TC-EQR-033: the tile counts waiting lines (this run's line among them), never "—".
  await expect(tile).toContainText(/\d+/);
  await expect(tile).not.toContainText("—");
  await tile.click();
  await expect(page).toHaveURL("/dashboard/tech-support/requests");
  await page.getByRole("link", { name: new RegExp(event.name) }).click();
  await expect(page).toHaveURL(`/tech-support/events/${event.id}`);
  const line = page.locator("article").filter({ hasText: item.name });
  await line.getByRole("button", { name: "Reserve", exact: true }).click();
  await expect(line).toContainText("Reserved");

  // AC10, AC11: the tick makes the event Ready and names who ticked it.
  await page.getByLabel("Equipment does not block exits or walkways").check();
  await expect(page.getByText(/^Confirmed by /)).toBeVisible();
  await expect(page.getByText("Technical status", { exact: true }).locator("..")).toContainText("Ready");
  // AC13: the history records both.
  await expect(page.getByRole("list").filter({ hasText: "Exit check ticked" })).toContainText("Technical status changed");

  // AC9: the coordinator sees the line Reserved and the event Ready. A session
  // is seeded once per tab, so the coordinator gets a browser context of their own.
  const context = await browser.newContext();
  try {
    const coordinatorPage = await context.newPage();
    await seedSession(coordinatorPage, await sharedSessions("event_coordinator"));
    await coordinatorPage.goto(`/coordinator/events/${event.id}`);
    const panel = coordinatorPage.locator('section[aria-labelledby="equipment-request-title"]');
    await expect(panel).toContainText("Reserved");
    await expect(panel).toContainText("Ready");
    await expect(panel).toContainText("Confirmed by");
  } finally {
    await context.close();
  }
});

test("TC-EQR-028 a refused reserve shows how many are free; Not available needs a reason", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("EQR028", "2031-08-11 09:00+08", "2031-08-11 12:00+08");
  const item = createThrowawayEquipment("028", 1);
  createThrowawayLine(event, item, 2);

  await seedSession(page, await sharedSessions("tech_support"));
  await page.goto(`/tech-support/events/${event.id}`);
  const line = page.locator("article").filter({ hasText: item.name });

  // AC3: refused, with the free count, and the line stays Pending.
  await line.getByRole("button", { name: "Reserve", exact: true }).click();
  await expect(line.getByRole("alert")).toContainText("Not enough available: 1 free for this event's time. The line stays Pending.");
  await expect(line).toContainText("Pending");

  // AC3, AC9: Not available needs a reason, then shows it and makes the event Issue.
  await line.getByRole("button", { name: "Mark not available" }).click();
  await line.getByRole("button", { name: "Confirm not available" }).click();
  await expect(line).toContainText("Give a reason the line is not available.");
  await line.getByLabel("Why is it not available? *").fill("Only 1 in stock");
  await line.getByRole("button", { name: "Confirm not available" }).click();
  await expect(line).toContainText("Not available: Only 1 in stock");
  await expect(page.getByText("Technical status", { exact: true }).locator("..")).toContainText("Issue");
});
