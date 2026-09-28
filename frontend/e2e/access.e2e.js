// Route guards: who can open which page. Cases: docs/test-cases/roles-and-access.md.
import { ACCOUNTS, expect, seedSession, test } from "./support/fixtures.js";

test("TC-RBAC-001 a signed-out visitor is sent to login with the page remembered", async ({ page }) => {
  await page.goto("/dashboard/attendee");

  await expect(page).toHaveURL("/login?redirect=/dashboard/attendee");
});

for (const [role, own] of Object.entries(ACCOUNTS)) {
  const caseIds = role === "attendee" ? "TC-RBAC-002 TC-RBAC-003" : "TC-RBAC-003";

  test(`${caseIds} ${role} is kept out of every other role's dashboard`, async ({ page, sharedSessions }) => {
    await seedSession(page, await sharedSessions(role));

    for (const [otherRole, other] of Object.entries(ACCOUNTS)) {
      if (otherRole === role) continue;
      await page.goto(other.dashboard);
      await expect(page, `${role} visiting ${other.dashboard}`).toHaveURL(own.dashboard);
    }
  });
}

test("TC-RBAC-004 a signed-in user who opens login is sent to their dashboard", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_organiser"));

  await page.goto("/login");

  await expect(page).toHaveURL(ACCOUNTS.event_organiser.dashboard);
  await expect(page.getByRole("button", { name: "Sign In" })).toHaveCount(0);
});

test("TC-RBAC-005 an unknown path goes to login", async ({ page }) => {
  await page.goto("/this-page-does-not-exist");

  await expect(page).toHaveURL("/login");
});
