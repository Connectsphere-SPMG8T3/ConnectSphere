// DEFECTS D86 in a real browser. The form stops the submission before anything is
// saved, so this creates no data. Case: docs/test-cases/events.md.
import { expect, seedSession, test } from "./support/fixtures.js";

test("TC-EVENT-046 TC-EVENT-049 the request form refuses to submit without total attendance", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_organiser"));
  await page.goto("/events/new");
  const writes = [];
  page.on("request", (request) => {
    if (request.method() !== "GET" && request.url().includes("/events")) writes.push(request.url());
  });

  await page.getByLabel("Event title").fill("live-check attendance");
  await page.getByLabel("Purpose").first().fill("live-check");
  await page.getByLabel("Proposed event date").fill("2031-12-01");
  await page.getByLabel("Proposed start time").fill("10:00");
  await page.getByLabel("Proposed end time").fill("12:00");
  await page.getByLabel("Purpose").last().selectOption("main_venue");
  await page.getByLabel("Expected pax").fill("20");
  await page.getByLabel("Preferred layout").selectOption("theatre");
  await page.getByRole("button", { name: "Submit request" }).click();

  await expect(page.getByText("Enter expected attendance of at least 1.")).toBeVisible();
  await expect(page.getByLabel("Total expected attendance")).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByText("Submit event request?")).toHaveCount(0);
  expect(writes).toEqual([]);
});
