// D41: read-only layout checks; never submit or clean up shared equipment data.
import { expect, seedSession, test } from "./support/fixtures.js";

// supabase/seed.sql: planning event assigned to coordinator@connectsphere.dev.
const PLANNING_FIXTURE_ID = "e0000000-0000-4000-8000-000000000202";

for (const viewport of [{ width: 1280, height: 900 }, { width: 375, height: 800 }]) {
  test(`TC-EQR-014 equipment request controls stay inside their card at ${viewport.width}x${viewport.height}`, async ({ page, sharedSessions }) => {
    await page.setViewportSize(viewport);
    await seedSession(page, await sharedSessions("event_coordinator"));
    await page.goto(`/coordinator/events/${PLANNING_FIXTURE_ID}`);

    const panel = page.locator('section[aria-labelledby="equipment-request-title"]');
    const select = panel.locator("form select").first();
    await expect(select.locator('option[value="b0000000-0000-4000-8000-000000000001"]')).toHaveCount(1);
    // Exercise the longest real catalogue label without changing shared data.
    const longestOption = await select.locator('option:not([value=""])').evaluateAll((options) =>
      options.reduce((longest, option) => option.textContent.length > longest.textContent.length ? option : longest).value,
    );
    await select.selectOption(longestOption);
    await panel.locator('form input[type="number"]').first().fill("5");
    await panel.locator("form textarea").first().fill("HDMI to the lectern");
    await panel.getByRole("button", { name: "Add another item" }).click();

    for (const tag of ["fieldset", "select", "input", "textarea"]) {
      await expect(panel.locator(`form ${tag}`)).toHaveCount(2);
    }
    await page.evaluate(() => document.fonts.ready);
    const geometry = await panel.evaluate((section) => {
      // BauhausCard's bordered root surrounds its slot wrapper and this panel.
      const card = section.closest(".border-2.border-ink").getBoundingClientRect();
      return {
        cardRight: card.right,
        controls: [...section.querySelectorAll("fieldset, select, input, textarea")].map((element) => ({
          tag: element.tagName,
          right: element.getBoundingClientRect().right,
          width: element.getBoundingClientRect().width,
        })),
        scrollWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
      };
    });

    for (const [index, control] of geometry.controls.entries()) {
      expect(control.width, `${control.tag} ${index} has a rendered box`).toBeGreaterThan(0);
      expect.soft(control.right, `${control.tag} ${index} stays inside the card`).toBeLessThanOrEqual(geometry.cardRight + 1);
    }
    expect.soft(geometry.scrollWidth, "page has no horizontal scroll").toBeLessThanOrEqual(geometry.viewportWidth);
  });
}
