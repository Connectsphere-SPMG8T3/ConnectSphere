// Coordinator assignment (SCRUM-12) in a real browser, on a throwaway queued event.
// Cases: docs/test-cases/dashboards.md.
import { createQueuedThrowawayEvent, readThrowawayEvent } from "./support/throwaway.js";
import { expect, seedSession, test } from "./support/fixtures.js";

test("TC-ASSIGN-011 a Lead assigns a queued event from the dashboard", async ({ page, sharedSessions }) => {
  const event = createQueuedThrowawayEvent("assign", "2031-08-12 09:00+08", "2031-08-12 17:00+08");
  await seedSession(page, await sharedSessions("event_coordinator_lead"));
  await page.goto("/dashboard/coordinator-lead");

  const row = page.locator(`[data-lead-event="${event.id}"]`);
  await expect(row).toContainText(event.name);
  await expect(row).toContainText("64 expected");
  await expect(row).toContainText("Theatre · Projector");
  await row.click();

  await expect(page.getByRole("heading", { name: "Assign coordinator" })).toBeVisible();
  await page.getByLabel("Choose a coordinator").first().selectOption({ label: "Marcus Lim" }).catch(async () => {
    await page.getByLabel("Choose a coordinator").first().selectOption({ index: 1 });
  });
  await page.getByRole("button", { name: "Assign event" }).click();
  const assigned = page.waitForResponse((r) => r.url().endsWith(`/events/${event.id}/assign`));
  await page.getByRole("dialog").getByRole("button", { name: "Assign", exact: true }).click();

  expect((await assigned).status()).toBe(200);
  await expect(page).toHaveURL(/\/dashboard\/coordinator-lead$/);
  await expect(page.locator(`[data-testid="unassigned-queue"] [data-lead-event="${event.id}"]`)).toHaveCount(0);
  await expect(page.locator(`[data-testid="active-events"] [data-lead-event="${event.id}"]`)).toContainText("Under review");
  const stored = readThrowawayEvent(event.id);
  expect(stored.status).toBe("under_review");
  expect(stored.coordinator_id).not.toBeNull();
});

test("TC-ASSIGN-014 a coordinator is sent away from the Lead event page", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_coordinator"));

  await page.goto("/lead/events/e0000000-0000-4000-8000-000000000201");

  await expect(page).toHaveURL(/\/dashboard\/coordinator$/);
});
