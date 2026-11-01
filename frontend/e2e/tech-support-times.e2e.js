// Tech support dashboard times in Singapore (D61) against real data. Case:
// docs/test-cases/dashboards.md. The outage is on throwaway equipment, deleted
// (with the outage) after the run.
import { expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayEquipment, createThrowawayOutage } from "./support/throwaway.js";

test.use({ timezoneId: "Asia/Singapore" });

test("TC-TSD-018 a maintenance outage shows its Singapore date and time", async ({ page, sharedSessions }, testInfo) => {
  const equipment = createThrowawayEquipment("TSD018", 2);
  // 25 Oct 2031 00:00 to 01:00 in Singapore: still 24 Oct in UTC.
  createThrowawayOutage(equipment, "2031-10-24 16:00+00", "2031-10-24 17:00+00", "live-check TSD018 outage");

  await seedSession(page, await sharedSessions("tech_support"));
  await page.goto("/dashboard/tech-support");
  const card = page.getByRole("region", { name: "Scheduled maintenance" }).getByRole("listitem").filter({ hasText: "live-check TSD018 outage" });
  await expect(card).toBeVisible();
  await card.screenshot({ path: testInfo.outputPath("maintenance-card.png") });
  await expect(card).toContainText("25 Oct 2031, 12:00 am – 25 Oct 2031, 1:00 am");
  await expect(card).not.toContainText("24 Oct 2031");
});
