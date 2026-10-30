// SCRUM-86 attendee actions and SCRUM-55 withdrawal integration in a real browser.
// Cases: TC-REG-027 in docs/test-cases/events.md.
import { API_URL, expect, signInThroughForm, skipIfSignInRefused, test } from "./support/fixtures.js";
import {
  createThrowawayRegistrationEvent,
  THROWAWAY_PASSWORD,
  throwawayEmail,
} from "./support/throwaway.js";

const EVENT_STARTS = "2031-09-10 09:00+08";
const EVENT_ENDS = "2031-09-10 12:00+08";

test.setTimeout(90_000);

async function createAttendeeAccount(page, email) {
  const response = await page.request.post(`${API_URL}/auth/signup`, {
    data: {
      role: "attendee",
      full_name: "Waitlist E2E Attendee",
      email,
      password: THROWAWAY_PASSWORD,
    },
  });
  expect(response.status()).toBe(201);
}

async function registerOccupant(page, session, event) {
  const response = await page.request.post(`${API_URL}/public/events/${event.id}/registrations`, {
    headers: { Authorization: `Bearer ${session.token}` },
  });
  expect(response.status()).toBe(201);
  expect((await response.json()).status).toBe("registered");
}

async function withdrawOccupant(page, session, event) {
  const response = await page.request.post(`${API_URL}/registrations/${event.id}/withdraw`, {
    headers: { Authorization: `Bearer ${session.token}` },
  });
  expect(response.status()).toBe(200);
  expect((await response.json()).status).toBe("withdrawn");
}

async function joinWaitlist(page, event) {
  await page.goto(`/attendee/events/${event.id}`);
  const join = page.getByRole("button", { name: "Join waitlist" });
  await expect(join).toBeVisible();
  await join.click();
  await expect(page.getByRole("button", { name: "Waitlisted" })).toBeVisible();
  await expect(page.getByText("You joined the waitlist.")).toBeVisible();
}

async function followInvitationNotification(page, event) {
  await page.goto("/dashboard/attendee");
  const bell = page.getByRole("button", { name: /^Notifications/ });
  await expect(bell).toBeVisible();
  await bell.click();
  const invitation = page.getByRole("link", { name: new RegExp(event.name) });
  await expect(invitation).toBeVisible();
  await invitation.click();
  await expect(page).toHaveURL(/\/dashboard\/attendee\/?$/);
}

async function openMyEvent(page, event) {
  await page.goto("/dashboard/attendee?tab=events");
  const eventRow = page.locator(`[data-event-row="${event.id}"]`);
  await expect(eventRow).toBeVisible();
  await eventRow.click();
  await expect(page).toHaveURL(`/dashboard/attendee/events/${event.id}`);
  await expect(page.getByRole("heading", { name: event.name })).toBeVisible();
}

test("TC-REG-027 Attendee joins, accepts, leaves and declines through the UI", async ({
  page,
  sharedSessions,
}) => {
  skipIfSignInRefused();
  const attendeeEmail = throwawayEmail("REG027-ui");
  await createAttendeeAccount(page, attendeeEmail);

  const events = {
    accept: createThrowawayRegistrationEvent("REG027-accept", EVENT_STARTS, EVENT_ENDS),
    leave: createThrowawayRegistrationEvent("REG027-leave", EVENT_STARTS, EVENT_ENDS),
    decline: createThrowawayRegistrationEvent("REG027-decline", EVENT_STARTS, EVENT_ENDS),
  };
  const occupant = await sharedSessions("attendee");
  for (const event of Object.values(events)) await registerOccupant(page, occupant, event);

  await page.goto("/login");
  await signInThroughForm(page, attendeeEmail, THROWAWAY_PASSWORD);
  await expect(page).toHaveURL("/dashboard/attendee");

  await joinWaitlist(page, events.accept);
  await withdrawOccupant(page, occupant, events.accept);
  await followInvitationNotification(page, events.accept);
  await openMyEvent(page, events.accept);
  await expect(page.getByRole("button", { name: "Accept invitation" })).toBeVisible();
  await page.getByRole("button", { name: "Accept invitation" }).click();
  await expect(page.getByText("Registration status: Registered")).toBeVisible();
  await expect(page.getByText("You are registered for this event.")).toBeVisible();

  await joinWaitlist(page, events.leave);
  await openMyEvent(page, events.leave);
  await page.getByRole("button", { name: "Leave waitlist" }).click();
  await expect(page).toHaveURL("/dashboard/attendee?tab=events");
  await expect(page.locator(`[data-event-row="${events.leave.id}"]`)).toHaveCount(0);

  await joinWaitlist(page, events.decline);
  await withdrawOccupant(page, occupant, events.decline);
  await followInvitationNotification(page, events.decline);
  await openMyEvent(page, events.decline);
  await expect(page.getByRole("button", { name: "Decline invitation" })).toBeVisible();
  await page.getByRole("button", { name: "Decline invitation" }).click();
  await expect(page).toHaveURL("/dashboard/attendee?tab=events");
  await expect(page.locator(`[data-event-row="${events.decline.id}"]`)).toHaveCount(0);
  await expect(page.getByText("You declined the invitation.")).toBeVisible();
});
