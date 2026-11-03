// D15 and D22 on the tech support dashboard: a failed load is never shown as
// empty data, and the inventory filters fit beside the sidebar at every width.
import { expect, seedSession, test } from "./support/fixtures.js";

for (const collapsed of [true, false]) {
  test(`TC-TSD-018 tech support inventory filters fit with the sidebar ${collapsed ? "collapsed" : "expanded"}`, async ({ page, sharedSessions }, testInfo) => {
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript((value) => window.localStorage.setItem("connectsphere.sidebarCollapsed", value), String(collapsed));
    await seedSession(page, await sharedSessions("tech_support"));
    await page.goto("/dashboard/tech-support");
    const search = page.getByLabel("Search equipment");
    const status = page.getByLabel("Status filter");
    await expect(status).toBeVisible();

    for (const width of [1440, 1024, 900, 768, 640, 375]) {
      await page.setViewportSize({ width, height: 900 });
      await page.evaluate(async () => {
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        await Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => {})));
      });
      const fit = await page.evaluate(() => {
        const main = document.querySelector("main") ?? document.body;
        const content = main.getBoundingClientRect();
        const controls = [...document.querySelectorAll("input[type=search], select")]
          .filter((element) => element.closest("label")?.textContent.match(/Search equipment|Status filter/));
        return {
          pageScrolls: document.documentElement.scrollWidth > window.innerWidth,
          overflowing: controls
            .map((element) => element.getBoundingClientRect())
            .filter((rect) => rect.left < content.left - 0.5 || rect.right > Math.min(content.right, window.innerWidth) + 0.5)
            .length,
        };
      });
      expect(fit.pageScrolls, `page scrolls sideways at ${width}px`).toBe(false);
      expect(fit.overflowing, `filter controls past the content edge at ${width}px`).toBe(0);
      await expect(search).toBeVisible();
      if (width === 768) await page.screenshot({ path: testInfo.outputPath(`filters-768-${collapsed ? "collapsed" : "expanded"}.png`), fullPage: true });
    }
    expect(errors).toEqual([]);
  });
}

test("TC-TSD-011 a failed inventory or maintenance load is reported, not shown as empty", async ({ page, sharedSessions }, testInfo) => {
  await seedSession(page, await sharedSessions("tech_support"));
  // Only these two reads fail; the session check and everything else still answer.
  await page.route(/\/equipment\/(inventory|maintenance)(\?|$)/, (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Service unavailable" }) }));
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/dashboard/tech-support");

  await expect(page.getByRole("alert").first()).toBeVisible();
  await expect(page.getByText("Inventory couldn't be loaded", { exact: true })).toBeVisible();
  await expect(page.getByText("Maintenance couldn't be loaded", { exact: true })).toBeVisible();
  await expect(page.getByText("No equipment matches this filter.")).toHaveCount(0);
  await expect(page.getByText("No maintenance scheduled")).toHaveCount(0);
  await expect(page.locator("table")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("load-failure.png"), fullPage: true });
});
