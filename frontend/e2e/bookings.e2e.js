// Venue booking request (SCRUM-19) and rejection (SCRUM-38) against real data.
// Cases: docs/test-cases/venues.md.
import { API_URL, expect, seedSession, test } from "./support/fixtures.js";
import { createThrowawayEvent, createThrowawayRequest } from "./support/throwaway.js";

const INNOVATION_LAB = "b0000000-0000-4000-8000-000000000006";

test("TC-BOOK-008 a coordinator finds a venue from the event and requests it", async ({ page, sharedSessions }) => {
  // 26 May 2031, 10:00–12:00 Singapore time: far enough ahead that nothing real is booked.
  const event = createThrowawayEvent("008", "2031-05-26 10:00+08", "2031-05-26 12:00+08");
  await seedSession(page, await sharedSessions("event_coordinator"));

  await page.goto(`/coordinator/events/${event.id}`);
  const panel = page.getByTestId("venue-panel");
  await expect(panel).toContainText("No venue requested yet");
  await panel.getByRole("button", { name: "Find a venue" }).click();

  // The search opens pre-filled with the event's date and times.
  await expect(page).toHaveURL(new RegExp(`/venues\\?event=${event.id}`));
  await expect(page.getByTestId("booking-event-context")).toContainText(event.name);
  await page.getByRole("button", { name: "Request Innovation Lab" }).click();

  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Note for venue staff (optional)").fill("Early access at 09:30 please");
  await dialog.getByRole("button", { name: "Request venue" }).click();

  // Back on the event, which now shows the tentative hold.
  await expect(page).toHaveURL(`/coordinator/events/${event.id}`);
  await expect(page.getByTestId("venue-panel")).toContainText("Innovation Lab");
  await expect(page.getByTestId("venue-panel")).toContainText("Tentative hold");
});

test("TC-BOOK-021 venue staff read a held request and reject it with a reason", async ({ page, sharedSessions }) => {
  // 9 Jun 2031, 14:00–17:00 Singapore time, on a throwaway event and booking.
  const { event, bookingId } = createThrowawayRequest("021", "2031-06-09 14:00+08", "2031-06-09 17:00+08", INNOVATION_LAB);
  await seedSession(page, await sharedSessions("venue_staff"));

  await page.goto(`/bookings/${bookingId}`);
  // AC1: the event's date, time, capacity, layout and other requirements.
  for (const text of [event.name, "Innovation Lab", "9 Jun 2031, 14:00–17:00", "20", "Classroom", "Step-free access",
    "Early access please", "Pending hold"]) {
    await expect(page.getByRole("main")).toContainText(text);
  }

  await page.getByRole("button", { name: "Reject request" }).click();
  const dialog = page.getByRole("dialog");
  const confirm = dialog.getByRole("button", { name: "Reject booking request" });
  // AC2: a blank reason can't be sent.
  await dialog.getByLabel("Reason (required)").fill("   ");
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel("Reason (required)").fill("Capacity exceeded for this layout");
  await dialog.getByLabel("Suggested alternative (optional)").fill("Heritage Hall has a larger classroom setup");
  await confirm.click();

  // AC4, AC12: rejected, with the reason and the history shown.
  await expect(page.getByTestId("booking-decision")).toContainText("Capacity exceeded for this layout");
  await expect(page.getByTestId("booking-history")).toContainText("Rejected");
  await expect(page.getByRole("button", { name: "Reject request" })).toHaveCount(0);

  // AC5: the hold has left the venue-staff queue.
  await page.goto("/dashboard/venue-staff");
  await expect(page.locator(`a[href="/bookings/${bookingId}"]`)).toHaveCount(0);
});

// A throwaway request that venue staff have already rejected, through the API.
async function rejectedRequest(page, sharedSessions, tag, startsAt, endsAt) {
  const { event, bookingId } = createThrowawayRequest(tag, startsAt, endsAt, INNOVATION_LAB);
  const staff = await sharedSessions("venue_staff");
  const rejected = await page.request.post(`${API_URL}/venue-bookings/${bookingId}/reject`, {
    headers: { Authorization: `Bearer ${staff.token}` },
    data: { reason: "Closed for maintenance that week", suggestion: "Try the week after" },
  });
  expect(rejected.status()).toBe(200);
  return event;
}

// One role per test: seedSession signs a tab in once, so a role switch needs its own test.
test("TC-BOOK-022 the coordinator sees why a booking was rejected and can look again", async ({ page, sharedSessions }) => {
  const event = await rejectedRequest(page, sharedSessions, "022-c", "2031-06-10 14:00+08", "2031-06-10 17:00+08");

  await seedSession(page, await sharedSessions("event_coordinator"));
  await page.goto(`/coordinator/events/${event.id}`);
  const panel = page.getByTestId("venue-panel");
  await expect(panel).toContainText("Rejected by venue staff");
  await expect(panel).toContainText("Closed for maintenance that week");
  await expect(panel).toContainText("Try the week after");
  // AC7: they can still look for another venue.
  await expect(panel.getByRole("button", { name: "Find a venue" })).toBeVisible();
});

test("TC-BOOK-022 the organiser's event page never shows the rejection", async ({ page, sharedSessions }) => {
  const event = await rejectedRequest(page, sharedSessions, "022-o", "2031-06-11 14:00+08", "2031-06-11 17:00+08");

  await seedSession(page, await sharedSessions("event_organiser"));
  await page.goto(`/events/${event.id}`);
  await expect(page.getByRole("main")).toContainText(event.name);
  await expect(page.getByRole("main")).not.toContainText("Closed for maintenance that week");
  await expect(page.getByRole("main")).not.toContainText("Try the week after");
});
