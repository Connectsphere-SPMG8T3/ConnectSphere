// 23-R: real API and throwaway stock; never change seeded inventory.
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayEquipment, parseRows } from "./support/throwaway.js";

function query(sql) {
  return parseRows(execFileSync("supabase", ["db", "query", "--linked", "--project-ref",
    "vuiryrzzyfecjqftwicj", "-o", "json", sql], {
    cwd: fileURLToPath(new URL("../..", import.meta.url)), encoding: "utf8", stdio: "pipe",
  }));
}

for (const width of [1280, 768, 375]) {
  test(`TC-EQR-040 availability shows usable quantity, shortage and location at ${width}px`, async ({ page, sharedSessions }) => {
    const [schema] = query("select exists (select 1 from information_schema.columns where table_schema='public' and table_name='equipment' and column_name='storage_location') as present");
    test.skip(!schema.present, "Blocked: 23-R storage_location migration has not been deployed.");
    const item = createThrowawayEquipment(`040-${width}`, 7);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
    try {
      query(`update public.equipment set storage_location = 'Store A' where id = '${item.id}'`);
      query("insert into public.equipment_unavailability (equipment_id, quantity, start_at, end_at, reason) values " +
        `('${item.id}', 2, '2034-01-01 09:00+08', '2034-01-01 12:00+08', 'Faulty units')`);
      await page.setViewportSize({ width, height: 900 });
      await seedSession(page, await sharedSessions("tech_support"));
      const catalogueResponse = page.waitForResponse((response) => response.url().endsWith("/equipment/catalogue"));
      await page.goto("/dashboard/tech-support?tab=availability");
      const catalogue = await catalogueResponse;
      expect(catalogue.status()).toBe(200);
      const listed = (await catalogue.json()).items.map((row) => row.equipment_id);
      if (!listed.includes(item.id)) {
        const stored = query(`select id, status from public.equipment where id = '${item.id}'`);
        throw new Error(`Test equipment missing from catalogue; current database row: ${JSON.stringify(stored)}`);
      }
      await page.getByLabel("Equipment ID / type").first().selectOption(item.id);
      // Browser-local input is converted to UTC by the actual form.
      const local = await page.evaluate(() => {
        const format = (iso) => {
          const date = new Date(iso);
          return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
        };
        return [format("2034-01-01T09:00:00+08:00"), format("2034-01-01T12:00:00+08:00")];
      });
      await page.getByLabel("Start date and time").fill(local[0]);
      await page.getByLabel("End date and time").fill(local[1]);
      await page.getByLabel("Needed", { exact: true }).fill("6");
      await page.getByRole("button", { name: "Check real-time availability" }).click();
      const row = page.locator("tbody tr").filter({ hasText: item.name });
      await expect(row.locator("td")).toHaveText([item.name, "Store A", "6", "5", "1", "Insufficient"]);
      query(`update public.equipment set storage_location = null where id = '${item.id}'`);
      await page.getByLabel("Needed", { exact: true }).fill("5");
      await page.getByRole("button", { name: "Check real-time availability" }).click();
      await expect(row.locator("td")).toHaveText([item.name, "Not recorded", "5", "5", "0", "Sufficient"]);
      const geometry = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: innerWidth }));
      expect(geometry.scroll).toBeLessThanOrEqual(geometry.width);
      expect(errors).toEqual([]);
    } finally {
      query(`delete from public.equipment where id = '${item.id}'`);
    }
  });
}


test("TC-EQR-043 duplicate selections explain combined quantities without sending an availability request", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("tech_support"));
  await page.goto("/dashboard/tech-support?tab=availability");
  const picker = page.getByLabel("Equipment ID / type");
  await expect(picker.first().locator("option")).not.toHaveCount(0);
  await page.getByRole("button", { name: "Add item", exact: true }).click();
  await page.getByLabel("Needed", { exact: true }).nth(0).fill("5");
  await page.getByLabel("Needed", { exact: true }).nth(1).fill("5");
  const requests = [];
  page.on("request", (request) => {
    if (request.url().includes("/equipment/availability/check")) requests.push(request.url());
  });
  await page.getByRole("button", { name: "Check real-time availability" }).click();
  await expect(page.getByText("Choose each item once; combine the quantities for the same equipment.")).toBeVisible();
  expect(requests).toEqual([]);
});
