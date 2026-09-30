// Role dashboards against real data. Cases: docs/test-cases/dashboards.md.
import { expect, seedSession, test } from "./support/fixtures.js";

// supabase/seed.sql: under review, assigned to coordinator@connectsphere.dev.
const REVIEW_FIXTURE_ID = "e0000000-0000-4000-8000-000000000201";

test("TC-DASH-001 the coordinator dashboard loads from the real endpoint", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_coordinator"));

  const response = page.waitForResponse((r) => r.url().endsWith("/events/dashboard/coordinator"));
  await page.goto("/dashboard/coordinator");

  expect((await response).status()).toBe(200);
  await expect(page.getByText("Awaiting data")).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator(`a[href="/coordinator/events/${REVIEW_FIXTURE_ID}"]`).first()).toBeVisible();
});

test("TC-DASH-019 a dashboard row opens that event's review page", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto("/dashboard/coordinator");

  const overview = page.locator('section[aria-labelledby="active-events"]');
  const row = overview.locator('a[href^="/coordinator/events/"]').first();
  const href = await row.getAttribute("href");
  const name = (await row.locator("p").first().textContent()).trim();
  await row.click();

  await expect(page).toHaveURL(href);
  await expect(page.getByText(name, { exact: false }).first()).toBeVisible();
});
