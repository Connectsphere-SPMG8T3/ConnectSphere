// SCRUM-35 manager registration report and refresh behavior.
// Cases: TC-REG-031, TC-REG-033 and TC-REG-034 in docs/test-cases/events.md.
import { readFile } from "node:fs/promises";

import { API_URL, expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayRegistrationEvent } from "./support/throwaway.js";

test("TC-REG-031 organisers and coordinators see the scoped registration report and refreshed state", async ({
  page,
  sharedSessions,
}) => {
  const event = createThrowawayRegistrationEvent(
    "REG031-manager-report",
    "2031-09-10 09:00+08",
    "2031-09-10 12:00+08",
  );
  const attendee = await sharedSessions("attendee");
  const registration = await page.request.post(`${API_URL}/public/events/${event.id}/registrations`, {
    headers: { Authorization: ["Bearer", attendee.token].join(" ") },
  });
  expect(registration.status()).toBe(201);

  await seedSession(page, await sharedSessions("event_organiser"));
  const organiserReportResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith(`/events/${event.id}/registrations`),
  );
  await page.goto(`/events/${event.id}`);
  const organiserReport = await organiserReportResponse;
  expect(organiserReport.status()).toBe(200);
  const initialReport = await organiserReport.json();
  expect(initialReport).toMatchObject({
    effective_capacity: 1,
    registered_count: 1,
    remaining_places: 0,
    waitlist_count: 0,
  });
  expect(initialReport.registrations.map((row) => row.status)).toEqual(["registered"]);
  await expect(page.getByRole("heading", { name: "Registrations" })).toBeVisible();
  await expect(page.getByLabel("Filter registration status").locator("option")).toHaveText([
    "All statuses",
    "Registered",
    "Waitlisted",
    "Invited",
    "Withdrawn",
  ]);
  await expect(page.getByText("Siti Rahman")).toBeVisible();
  await expect(page.getByText("attendee@connectsphere.dev")).toHaveCount(0);

  await page.getByLabel("Search attendee name").fill("SITI");
  await page.getByLabel("Filter registration status").selectOption("registered");
  await expect(page.getByText("Siti Rahman")).toBeVisible();

  const coordinatorPage = await page.context().newPage();
  await seedSession(coordinatorPage, await sharedSessions("event_coordinator"));
  const coordinatorReportResponse = coordinatorPage.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith(`/events/${event.id}/registrations`),
  );
  await coordinatorPage.goto(`/coordinator/events/${event.id}`);
  const coordinatorReport = await coordinatorReportResponse;
  expect(coordinatorReport.status()).toBe(200);
  await expect(coordinatorPage.getByText("attendee@connectsphere.dev")).toBeVisible();
  await coordinatorPage.close();

  const withdrawal = await page.request.post(`${API_URL}/registrations/${event.id}/withdraw`, {
    headers: { Authorization: ["Bearer", attendee.token].join(" ") },
  });
  expect(withdrawal.status()).toBe(200);
  const refreshedReportResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith(`/events/${event.id}/registrations`),
  );
  await page.getByRole("button", { name: "Refresh" }).click();
  const refreshedReport = await refreshedReportResponse;
  expect(refreshedReport.status()).toBe(200);
  expect((await refreshedReport.json()).registered_count).toBe(0);
  await expect(page.getByText("No registrations match the selected filters.")).toBeVisible();

  await page.getByLabel("Filter registration status").selectOption("");
  const withdrawnStatus = page.locator('[data-testid="managed-registrations"] li span[aria-label]');
  await expect(withdrawnStatus).toHaveAttribute("aria-label", "Withdrawn");
  await expect(withdrawnStatus).toBeVisible();
  await expect(page.getByText("Siti Rahman")).toBeVisible();
});

test("TC-REG-033 exports every report row to CSV with role-appropriate fields", async ({
  page,
  sharedSessions,
}) => {
  const event = createThrowawayRegistrationEvent(
    "REG033-manager-csv",
    "2031-09-11 09:00+08",
    "2031-09-11 12:00+08",
  );
  const attendee = await sharedSessions("attendee");
  const registration = await page.request.post(`${API_URL}/public/events/${event.id}/registrations`, {
    headers: { Authorization: ["Bearer", attendee.token].join(" ") },
  });
  expect(registration.status()).toBe(201);
  const withdrawal = await page.request.post(`${API_URL}/registrations/${event.id}/withdraw`, {
    headers: { Authorization: ["Bearer", attendee.token].join(" ") },
  });
  expect(withdrawal.status()).toBe(200);

  await seedSession(page, await sharedSessions("event_organiser"));
  const organiserReportResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith(`/events/${event.id}/registrations`),
  );
  await page.goto(`/events/${event.id}`);
  expect((await organiserReportResponse).status()).toBe(200);
  await page.getByLabel("Filter registration status").selectOption("registered");
  await expect(page.getByText("No registrations match the selected filters.")).toBeVisible();

  const organiserDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  const organiserCsv = await readFile(await (await organiserDownloadPromise).path(), "utf8");
  expect(organiserCsv).toContain("Siti Rahman");
  expect(organiserCsv).toContain("Withdrawn");
  expect(organiserCsv).not.toContain("attendee@connectsphere.dev");

  const coordinatorPage = await page.context().newPage();
  await seedSession(coordinatorPage, await sharedSessions("event_coordinator"));
  const coordinatorReportResponse = coordinatorPage.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith(`/events/${event.id}/registrations`),
  );
  await coordinatorPage.goto(`/coordinator/events/${event.id}`);
  expect((await coordinatorReportResponse).status()).toBe(200);

  const coordinatorDownloadPromise = coordinatorPage.waitForEvent("download");
  await coordinatorPage.getByRole("button", { name: "Export CSV" }).click();
  const coordinatorCsv = await readFile(await (await coordinatorDownloadPromise).path(), "utf8");
  expect(coordinatorCsv).toContain("Siti Rahman");
  expect(coordinatorCsv).toContain("Withdrawn");
  expect(coordinatorCsv).toContain("attendee@connectsphere.dev");
  await coordinatorPage.close();
});

test("TC-REG-034 keeps manager-facing registration statuses readable beside attendee names at 375px", async ({
  page,
  sharedSessions,
}) => {
  const event = createThrowawayRegistrationEvent(
    "REG034-manager-mobile-status",
    "2031-09-12 09:00+08",
    "2031-09-12 12:00+08",
  );
  await seedSession(page, await sharedSessions("event_organiser"));
  await page.route(`**/api/v1/events/${event.id}/registrations`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        event_id: event.id,
        effective_capacity: 6,
        registered_count: 1,
        remaining_places: 5,
        waitlist_count: 1,
        registrations: [
          { id: "registration-1", full_name: "Alexandra Cho", status: "waitlisted" },
        ],
      }),
    }),
  );
  await page.setViewportSize({ width: 375, height: 812 });

  const reportResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith(`/events/${event.id}/registrations`),
  );
  await page.goto(`/events/${event.id}`);
  expect((await reportResponse).status()).toBe(200);

  const row = page.locator('[data-testid="managed-registrations"] li');
  const status = row.locator("span[aria-label]");
  await expect(status).toBeVisible();
  await expect(status).toHaveAttribute("aria-label", "Waitlisted");
  await expect(status.locator("span").first()).toHaveText("Waitlisted");
  await expect(status.locator("span").nth(1)).toBeHidden();
  const nameBox = await row.getByText("Alexandra Cho", { exact: true }).boundingBox();
  const statusBox = await status.boundingBox();
  expect(Math.abs(nameBox.y - statusBox.y)).toBeLessThanOrEqual(2);
  expect(statusBox.height).toBeLessThanOrEqual(32);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});
