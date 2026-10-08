// D23 and D24 regressions on the organiser's event page. Read-only: the seeded
// organiser's fixture event `…0201` is opened, never changed.
import { expect, seedSession, test } from "./support/fixtures.js";

const FIXTURE = "/events/e0000000-0000-4000-8000-000000000201";

test("TC-EVENT-043 the registration card's timezone line is readable on its white surface", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_organiser"));
  await page.goto(FIXTURE);

  const timezone = page.locator("aside p", { hasText: /^Asia\/Singapore$/ }).first();
  await expect(timezone).toBeVisible();
  // White text (`text-canvas`) on BauhausCard's white surface was invisible (D23).
  expect(await timezone.evaluate((el) => getComputedStyle(el).color)).not.toMatch(/^rgba?\(255, 255, 255/);
});

test("TC-EVENT-044 the planning status card names the coordinator, not their account ID", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_organiser"));
  await page.goto(FIXTURE);

  await expect(page.getByText("Coordinator: Marcus Lim")).toBeVisible();
  await expect(page.getByText(/Coordinator: a0000000-/)).toHaveCount(0);
});
