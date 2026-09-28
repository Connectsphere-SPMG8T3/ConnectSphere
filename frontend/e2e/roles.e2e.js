// Multi-role accounts and the "Acting as" switcher (SCRUM-74/75/76/78).
// Cases: docs/test-cases/roles-and-access.md. The seeded coordinator also
// holds venue_staff; every other seeded account has one role.
import { ACCOUNTS, apiLogin, expect, seedSession, test } from "./support/fixtures.js";

const COORDINATOR = ACCOUNTS.event_coordinator.dashboard;
const VENUE_STAFF = ACCOUNTS.venue_staff.dashboard;

const actingAs = (page) => page.getByLabel("Acting as");

test("TC-ROLE-001 a single-role account has no role switcher", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("attendee"));
  await page.goto(ACCOUNTS.attendee.dashboard);

  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
  await expect(actingAs(page)).toHaveCount(0);
});

test("TC-ROLE-002 the switcher lists exactly the held roles, by name", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(COORDINATOR);

  await expect(actingAs(page)).toHaveValue("event_coordinator");
  await expect(actingAs(page).locator("option:not([value=''])")).toHaveText(["Event Coordinator", "Venue Staff"]);
});

test("TC-ROLE-003 TC-ROLE-004 switching role opens that dashboard and survives a reload", async ({ page }) => {
  await seedSession(page, await apiLogin("event_coordinator")); // its own session: it switches role
  await page.goto(COORDINATOR);

  await actingAs(page).selectOption("venue_staff");
  await expect(page).toHaveURL(VENUE_STAFF);
  await expect(actingAs(page)).toHaveValue("venue_staff");

  await page.reload();
  await expect(page).toHaveURL(VENUE_STAFF);
  await expect(actingAs(page)).toHaveValue("venue_staff");
});

test("TC-ROLE-005 switching in one session leaves another session of the same account alone", async ({
  page,
  browser,
}) => {
  await seedSession(page, await apiLogin("event_coordinator"));
  const otherContext = await browser.newContext();
  const other = await otherContext.newPage();
  const otherSession = await apiLogin("event_coordinator");
  await seedSession(other, otherSession);

  try {
    await page.goto(COORDINATOR);
    await actingAs(page).selectOption("venue_staff");
    await expect(page).toHaveURL(VENUE_STAFF);

    await other.goto(COORDINATOR);
    await expect(other).toHaveURL(COORDINATOR);
    await expect(actingAs(other)).toHaveValue("event_coordinator");
  } finally {
    await other.getByRole("button", { name: "Logout" }).click().catch(() => {});
    await otherContext.close();
  }
});

test("TC-ROLE-015 the profile lists every role of a multi-role account", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto("/profile/me");

  const allRoles = page.locator("dt", { hasText: "All Roles" }).locator("xpath=following-sibling::dd[1]");
  await expect(allRoles).toContainText("Event Coordinator");
  await expect(allRoles).toContainText("Venue Staff");
});

test("TC-ROLE-016 the profile has no All Roles section for a single-role account", async ({
  page,
  sharedSessions,
}) => {
  await seedSession(page, await sharedSessions("event_organiser"));
  await page.goto("/profile/me");

  await expect(page.getByText(ACCOUNTS.event_organiser.email)).toBeVisible();
  await expect(page.getByText("All Roles")).toHaveCount(0);
});

test("TC-ROLE-019 a page opens for the active role only", async ({ page }) => {
  await seedSession(page, await apiLogin("event_coordinator"));
  await page.goto(VENUE_STAFF);
  await expect(page).toHaveURL(COORDINATOR);

  await actingAs(page).selectOption("venue_staff");
  await expect(page).toHaveURL(VENUE_STAFF);
  await page.goto(VENUE_STAFF);
  await expect(page).toHaveURL(VENUE_STAFF);
});
