// SCRUM-82: read-only fixture check.
import { expect, seedSession, test } from "./support/fixtures.js";
test("TC-SAFE-004 a held booking disables send and names the missing arrangement", async ({page, sharedSessions}) => {
 await seedSession(page, await sharedSessions("event_coordinator"));
 await page.goto("/coordinator/events/e0000000-0000-4000-8000-000000000202");
 await expect(page.getByRole("button", {name: "Send for safety check"})).toBeDisabled();
 await expect(page.locator("#safety-missing")).toContainText("A venue booking is awaiting venue staff approval.");
});
