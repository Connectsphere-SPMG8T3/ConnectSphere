// D21: all role summary rows must align even when their longest labels wrap.
// The coordinator Overview has no summary row since 2026-10-21 (TC-DASH-025 superseded),
// nor the organiser's since 2026-10-22 (TC-ORG-010 superseded).
import { expect, seedSession, test } from "./support/fixtures.js";

const dashboards = [
  { role: "attendee", caseId: "TC-ATT-001", label: "Upcoming registrations", count: 3 },
  { role: "tech_support", caseId: "TC-TSD-017", label: "Maintenance scheduled", count: 4 },
];

for (const dashboard of dashboards) {
  test(`${dashboard.caseId} ${dashboard.role} summary figures align when labels wrap`, async ({ page, sharedSessions }, testInfo) => {
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await seedSession(page, await sharedSessions(dashboard.role));
    const routeRole = dashboard.role.replace("event_", "").replaceAll("_", "-");
    await page.goto(`/dashboard/${routeRole}`);
    const label = page.getByText(dashboard.label, { exact: true });
    await expect(label).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    // A summary label lives inside the card's slot container. Select the
    // grid around that card; this also catches an unintended extra wrapper.
    const grid = label.locator("..").locator("..").locator("..");
    const cards = grid.locator(":scope > div");
    await expect(cards).toHaveCount(dashboard.count);

    for (const width of [1440, 1280, 1100, 768, 640, 375, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await page.evaluate(async () => {
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        await Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => {})));
      });
      const boxes = await cards.evaluateAll((elements) => elements.map((card) => {
        const rect = card.getBoundingClientRect();
        const paragraphs = [...card.querySelectorAll("p")];
        return {
          top: rect.top, height: rect.height,
          valueTop: paragraphs[1].getBoundingClientRect().top,
          detailTop: paragraphs[2]?.getBoundingClientRect().top,
          clipped: paragraphs.some((paragraph) => {
            const text = paragraph.getBoundingClientRect();
            return text.left < rect.left || text.right > rect.right || text.bottom > rect.bottom;
          }),
        };
      }));
      for (const card of boxes) {
        expect(card.clipped, `content fits at ${width}px`).toBe(false);
        for (const sibling of boxes.filter((other) => Math.abs(other.top - card.top) < 1)) {
          expect(Math.abs(card.height - sibling.height), `card heights at ${width}px`).toBeLessThan(1);
          expect(Math.abs(card.valueTop - sibling.valueTop), `number alignment at ${width}px`).toBeLessThan(1);
          if (card.detailTop !== undefined) {
            expect(Math.abs(card.detailTop - sibling.detailTop), `detail alignment at ${width}px`).toBeLessThan(1);
          }
        }
      }
      expect(await grid.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        return rect.left >= 0 && rect.right <= innerWidth && element.scrollWidth <= element.clientWidth;
      }), `summary row fits at ${width}px`).toBe(true);
    }
    expect(errors).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath("dashboard-phone.png") });

  });
}
