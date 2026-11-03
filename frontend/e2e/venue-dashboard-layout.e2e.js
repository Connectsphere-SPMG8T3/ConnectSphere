// D20: measure rendered boxes, not Tailwind classes, so wrapping regressions
// are caught even when the markup or styling approach changes.
import { expect, seedSession, test } from "./support/fixtures.js";

// Resizing also animates the app's sidebar gutter; measure the settled layout.
async function settleLayout(page) {
  await page.evaluate(async () => {
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    await Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => {})));
  });
}

test("TC-VSD-035 the booking status board keeps its columns and headers aligned at every width", async ({ page, sharedSessions }, testInfo) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await seedSession(page, await sharedSessions("venue_staff"));
  const response = page.waitForResponse((r) => r.url().endsWith("/venues/dashboard/venue-staff"));
  await page.goto("/dashboard/venue-staff");
  expect((await response).status()).toBe(200);
  await page.evaluate(() => document.fonts.ready);

  const columns = page.locator("[data-status-group]");
  await expect(columns).toHaveCount(3);
  const headers = page.locator("[data-status-group] [data-column-header]");

  for (const width of [1440, 1280, 1100, 768, 640, 375, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await settleLayout(page);
    // The headers share one grid row, so a long description wraps without making the columns uneven.
    const heights = await headers.evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().height));
    for (const height of heights) expect(Math.abs(height - heights[0]), `header heights at ${width}px`).toBeLessThan(1);
    // The board scrolls sideways inside itself; the page must not.
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `no page overflow at ${width}px`).toBe(true);
  }

  await page.setViewportSize({ width: 1440, height: 900 });
  await settleLayout(page);
  await page.screenshot({ path: testInfo.outputPath("dashboard-desktop.png") });
  await page.getByRole("button", { name: "View all Pending requests bookings" }).click();
  await expect(page).toHaveURL(/\/dashboard\/venue-staff\/requests$/);
  expect(errors).toEqual([]);
});
