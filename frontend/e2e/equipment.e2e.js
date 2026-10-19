// Equipment requests against real data (SCRUM-45). Cases: docs/test-cases/equipment.md.
// The submission writes real lines on the planning fixture; each is marked with
// LIVE_CHECK_NOTE and deleted after the run, so the seeded data is left as it was.
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, seedSession, test } from "./support/fixtures.js";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const PROJECT_REF = "vuiryrzzyfecjqftwicj";
// supabase/seed.sql: in planning, assigned to coordinator@connectsphere.dev.
const PLANNING_FIXTURE_ID = "e0000000-0000-4000-8000-000000000202";
// supabase/seed.sql: 4K Projector, 14 in total.
const PROJECTOR_ID = "b0000000-0000-4000-8000-000000000001";
const LIVE_CHECK_NOTE = "live-check SCRUM-45";

function deleteLiveCheckLines() {
  execFileSync(
    "supabase",
    [
      "db", "query", "--linked", "--project-ref", PROJECT_REF,
      `delete from public.equipment_requests where event_id = '${PLANNING_FIXTURE_ID}' ` +
        `and technical_requirements like '${LIVE_CHECK_NOTE}%'`,
    ],
    { cwd: REPO_ROOT, stdio: "pipe" },
  );
}

test.afterAll(() => deleteLiveCheckLines());

test("TC-EQR-005 TC-EQR-006 a coordinator submits above inventory and tech support see it pending", async ({ page, browser, sharedSessions }) => {
  const note = `${LIVE_CHECK_NOTE} e2e ${Date.now()}: lectern HDMI`;
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${PLANNING_FIXTURE_ID}`);

  const panel = page.locator('section[aria-labelledby="equipment-request-title"]');
  await expect(panel.getByText("Loading equipment")).toHaveCount(0);
  await panel.locator("form select").first().selectOption(PROJECTOR_ID);
  await panel.locator('form input[type="number"]').first().fill("15");
  // EQ-R1: warned, not blocked.
  await expect(panel.getByText("Only 14 exist in the catalogue. You can still submit.")).toBeVisible();
  await panel.locator("form textarea").first().fill(note);
  const submitted = page.waitForResponse((r) => r.url().endsWith("/equipment/requests") && r.request().method() === "POST");
  await panel.getByRole("button", { name: "Submit equipment request" }).click();

  expect((await submitted).status()).toBe(201);
  const line = panel.locator("li", { hasText: note });
  await expect(line).toContainText("Pending");
  await expect(line).toContainText("× 15");

  // seedSession seeds a tab once, so tech support get a browser context of their own.
  const techContext = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  try {
    const techPage = await techContext.newPage();
    await seedSession(techPage, await sharedSessions("tech_support"));
    // SCRUM-24 moved the list from the dashboard to its own requests page.
    await techPage.goto("/dashboard/tech-support/requests");
    const queue = techPage.locator('section[aria-labelledby="equipment-requests-heading"]').locator("li", { hasText: note });
    await expect(queue).toContainText("Pending");
    await expect(queue).toContainText("× 15");
  } finally {
    await techContext.close();
  }
});

test("TC-EQR-008 an event under review offers no equipment form", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto("/coordinator/events/e0000000-0000-4000-8000-000000000201");

  const panel = page.locator('section[aria-labelledby="equipment-request-title"]');
  await expect(panel.getByText("New equipment can only be requested while the event is in planning.")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Submit equipment request" })).toHaveCount(0);
});

test("TC-EQR-037 the availability check offers items added after the original five (D47)", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("tech_support"));
  await page.goto("/dashboard/tech-support?tab=availability");

  // supabase/seed.sql: Sound System (b…0006) was added on 2026-10-19. Read-only: nothing is reserved.
  const picker = page.getByLabel("Equipment ID / type").first();
  await expect(picker.locator("option", { hasText: "Sound System · audio" })).toHaveCount(1);
  await picker.selectOption("b0000000-0000-4000-8000-000000000006");
  await page.getByRole("button", { name: "Check real-time availability" }).click();

  const row = page.locator('section[aria-labelledby="result-heading"] tbody tr').filter({ hasText: "Sound System" });
  await expect(row).toContainText("Sufficient");
});
