// SCRUM-44 modify or remove equipment requirements, against real data. Cases:
// docs/test-cases/equipment.md. Every check uses a throwaway 2031 event and its
// own throwaway catalogue items, deleted after the run.
import { expect, seedSession, test } from "./support/fixtures.js";
import {
  createThrowawayEquipment,
  createThrowawayEvent,
  createThrowawayLine,
  setThrowawayEventStatus,
} from "./support/throwaway.js";

test("TC-EQR-052 TC-EQR-054 the coordinator changes one line and removes another; the history keeps both", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("EQR054", "2031-09-10 09:00+08", "2031-09-10 12:00+08");
  const kept = createThrowawayEquipment("054-a", 5);
  const removed = createThrowawayEquipment("054-b", 5);
  createThrowawayLine(event, kept, 2);
  createThrowawayLine(event, removed, 1);

  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);
  const panel = page.locator('section[aria-labelledby="equipment-request-title"]');
  const keptLine = panel.getByTestId("equipment-line").filter({ hasText: kept.name });

  // AC2, AC3: change the quantity; a Pending line stays Pending.
  await panel.getByRole("button", { name: `Edit ${kept.name}` }).click();
  await keptLine.getByLabel("Quantity").fill("3");
  await keptLine.getByRole("button", { name: `Save changes to ${kept.name}` }).click();
  await expect(keptLine).toContainText("× 3");
  await expect(keptLine).toContainText("Pending");
  await expect(keptLine.getByRole("button", { name: `Save changes to ${kept.name}` })).toHaveCount(0);

  // AC1: removal asks first, then the line leaves the list.
  await panel.getByRole("button", { name: `Remove ${removed.name} from the request` }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(`Remove 1 × ${removed.name}?`);
  await dialog.getByRole("button", { name: "Remove line" }).click();
  await expect(panel.getByTestId("equipment-line").filter({ hasText: removed.name })).toHaveCount(0);

  // AC8: both are in the history, the removed line still named.
  const history = panel.locator('section[aria-labelledby="equipment-history-title"]');
  await expect(history).toContainText(`Removed by the coordinator · 1 × ${removed.name}`);
  await expect(history).toContainText(`Changed by the coordinator · 3 × ${kept.name}`);
  await expect(history).toContainText("Quantity: 2 → 3.");
});

test("TC-EQR-055 outside planning the coordinator is told equipment can't be changed", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("EQR055", "2031-09-11 09:00+08", "2031-09-11 12:00+08");
  const item = createThrowawayEquipment("055", 2);
  createThrowawayLine(event, item, 1);
  setThrowawayEventStatus(event, "safety_review");

  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);
  const panel = page.locator('section[aria-labelledby="equipment-request-title"]');

  await expect(panel).toContainText(item.name);
  await expect(panel).toContainText("Equipment can only be changed while the event is in Planning.");
  await expect(panel.getByRole("button", { name: `Edit ${item.name}` })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: `Remove ${item.name} from the request` })).toHaveCount(0);
});
