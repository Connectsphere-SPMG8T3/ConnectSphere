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

test("TC-VSD-035 summary cards stay aligned when text wraps", async ({ page, sharedSessions }, testInfo) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await seedSession(page, await sharedSessions("venue_staff"));
  const response = page.waitForResponse((r) => r.url().endsWith("/venues/dashboard/venue-staff"));
  await page.goto("/dashboard/venue-staff");
  expect((await response).status()).toBe(200);
  await page.evaluate(() => document.fonts.ready);

  const grid = page.locator("main > div.grid").first();
  const cards = grid.locator(":scope > * > div");
  await expect(cards).toHaveCount(4);

  for (const width of [1440, 1280, 1100, 768, 640, 375, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await settleLayout(page);
    const boxes = await cards.evaluateAll((elements) => elements.map((card) => {
      const rect = card.getBoundingClientRect();
      const paragraphs = [...card.querySelectorAll("p")];
      return {
        top: rect.top,
        height: rect.height,
        valueTop: paragraphs[1].getBoundingClientRect().top,
        detailTop: paragraphs[2].getBoundingClientRect().top,
        clipped: paragraphs.some((paragraph) => {
          const text = paragraph.getBoundingClientRect();
          return text.left < rect.left || text.right > rect.right || text.bottom > rect.bottom;
        }),
      };
    }));
    for (const card of boxes) {
      expect(card.clipped, `text fits at ${width}px`).toBe(false);
      for (const sibling of boxes.filter((other) => Math.abs(other.top - card.top) < 1)) {
        expect(Math.abs(card.height - sibling.height), `card heights at ${width}px`).toBeLessThan(1);
        expect(Math.abs(card.valueTop - sibling.valueTop), `number alignment at ${width}px`).toBeLessThan(1);
        expect(Math.abs(card.detailTop - sibling.detailTop), `description alignment at ${width}px`).toBeLessThan(1);
      }
    }
    const columns = await grid.evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length);
    expect(columns).toBe(width >= 1280 ? 4 : width >= 768 ? 2 : 1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }

  // The existing cue must not resize the pending card when revealed.
  await page.setViewportSize({ width: 1440, height: 900 });
  await settleLayout(page);
  await page.screenshot({ path: testInfo.outputPath("dashboard-desktop.png") });
  const pending = page.getByRole("link", { name: /Pending requests.*See the list/ });
  const before = await pending.boundingBox();
  await pending.focus();
  await expect(pending.getByText("See the list ↓")).toHaveCSS("opacity", "1");
  const after = await pending.boundingBox();
  expect(after.height).toBe(before.height);
  await pending.press("Enter");
  await expect(page).toHaveURL(/\/dashboard\/venue-staff\/requests$/);
  expect(errors).toEqual([]);
});
