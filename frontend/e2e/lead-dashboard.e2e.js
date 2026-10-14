// The Event Coordinator Lead dashboard against real data. Cases: docs/test-cases/dashboards.md.
import { expect, seedSession, test } from "./support/fixtures.js";

test("TC-LEAD-006 the Lead dashboard loads from the real endpoint", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_coordinator_lead"));

  const response = page.waitForResponse((r) => r.url().endsWith("/events/dashboard/lead"));
  await page.goto("/dashboard/coordinator-lead");

  expect((await response).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "Unassigned queue" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Active events" })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("TC-LEAD-007 a coordinator is sent away from the Lead dashboard", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_coordinator"));

  await page.goto("/dashboard/coordinator-lead");

  await expect(page).toHaveURL(/\/dashboard\/coordinator$/);
});
