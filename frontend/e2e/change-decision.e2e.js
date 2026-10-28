// Story 37 in a real browser, on throwaway confirmed events: the assigned coordinator reads
// the preview, approves one change request and rejects another. Cases: docs/test-cases/events.md.
import {
  createThrowawayChangeRequest, createThrowawayEvent, readThrowawayEvent, setThrowawayEventStatus,
} from "./support/throwaway.js";
import { expect, seedSession, test } from "./support/fixtures.js";

const REASON = "live-check: sponsor wants more seats";

test("TC-CHANGE-025 the coordinator previews, approves one change and rejects another", async ({ page, sharedSessions }) => {
  const approved = createThrowawayEvent("37-025a", "2031-12-20 09:00+08", "2031-12-20 12:00+08");
  setThrowawayEventStatus(approved, "confirmed");
  createThrowawayChangeRequest(approved, 30, REASON);
  const rejected = createThrowawayEvent("37-025b", "2031-12-21 09:00+08", "2031-12-21 12:00+08");
  setThrowawayEventStatus(rejected, "confirmed");
  createThrowawayChangeRequest(rejected, 40, REASON);
  await seedSession(page, await sharedSessions("event_coordinator"));

  await page.goto(`/coordinator/events/${approved.id}`);
  const banner = page.getByTestId("change-request-banner");
  await expect(banner).toContainText("Expected attendance: 20 → 30");
  await expect(banner).toContainText(REASON);
  await expect(page.getByTestId("change-impact")).toContainText("If you approve");
  await banner.getByRole("button", { name: "Approve changes" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("The event goes back to Planning and needs a new safety check.");
  const decided = page.waitForResponse((r) => r.url().endsWith(`/events/${approved.id}/change-request/approve`));
  await dialog.getByRole("button", { name: "Approve changes" }).click();
  expect((await decided).status()).toBe(200);
  await expect(page.getByTestId("change-request-banner")).toHaveCount(0);
  expect(readThrowawayEvent(approved.id).status).toBe("planning");

  await page.goto(`/coordinator/events/${rejected.id}`);
  await page.getByTestId("change-request-banner").getByRole("button", { name: "Reject changes" }).click();
  const reject = page.getByRole("dialog");
  const confirm = reject.getByRole("button", { name: "Reject change request" });
  await expect(confirm).toBeDisabled();
  await reject.locator("textarea").fill("live-check: no room for more");
  const refused = page.waitForResponse((r) => r.url().endsWith(`/events/${rejected.id}/change-request/reject`));
  await confirm.click();
  expect((await refused).status()).toBe(200);
  await expect(page.getByTestId("change-request-banner")).toHaveCount(0);
  expect(readThrowawayEvent(rejected.id).status).toBe("confirmed");
});
