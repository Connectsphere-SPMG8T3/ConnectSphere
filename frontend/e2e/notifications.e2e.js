// The notification bell (SCRUM-113) against real data. Cases: docs/test-cases/notifications.md.
// Needs migration 20261021100000 applied to the project the backend talks to.
import { expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayEvent, createThrowawayNotification } from "./support/throwaway.js";

const COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002";

async function unreadCount(bell) {
  const label = await bell.getAttribute("aria-label");
  const match = /(\d+) unread/.exec(label ?? "");
  return match ? Number(match[1]) : 0;
}

test("TC-NOTIF-004 a new notification reaches the bell within 10 seconds and opens its event", async ({ page, sharedSessions }) => {
  const event = createThrowawayEvent("N004", "2031-09-03 10:00+08", "2031-09-03 12:00+08");
  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto("/dashboard/coordinator");
  const bell = page.getByRole("button", { name: /^Notifications/ });
  await expect(bell).toBeVisible();
  const before = await unreadCount(bell);

  createThrowawayNotification(event, COORDINATOR_ID, "event_assigned", "live-check bell notice");

  // The poll is every 10 seconds; the wait allows for one that was just missed.
  await expect(bell).toHaveAttribute("aria-label", `Notifications, ${before + 1} unread`, { timeout: 25_000 });
  await bell.click();
  const item = page.getByRole("link", { name: /live-check bell notice/ });
  await expect(item).toBeVisible();

  await item.click();
  await expect(page).toHaveURL(new RegExp(`/coordinator/events/${event.id}$`));
  // Opening it marked it read, so the count is back to what it was.
  const expected = before === 0 ? "Notifications" : `Notifications, ${before} unread`;
  await expect(page.getByRole("button", { name: /^Notifications/ })).toHaveAttribute("aria-label", expected);
});

test("TC-NOTIF-005 every role has the bell", async ({ page, sharedSessions }) => {
  for (const role of ["event_organiser", "event_coordinator", "venue_staff", "tech_support", "attendee"]) {
    await seedSession(page, await sharedSessions(role));
    await page.goto("/profile/me");
    await expect(page.getByRole("button", { name: /^Notifications/ })).toBeVisible();
  }
});
