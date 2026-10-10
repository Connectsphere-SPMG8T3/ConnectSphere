// CR-103/104: read-only route denials using existing seeded roles.
import { ACCOUNTS, expect, seedSession, test } from "./support/fixtures.js";

for (const [role, account] of Object.entries(ACCOUNTS)) {
  test(`TC-SDEC-004 ${role} cannot open the Safety Officer queue or review`, async ({ page, sharedSessions }) => {
    await seedSession(page, await sharedSessions(role));
    for (const route of ["/dashboard/safety", "/safety/events/00000000-0000-4000-8000-000000000000"]) {
      await page.goto(route);
      await expect(page).toHaveURL(account.dashboard);
    }
  });
}
