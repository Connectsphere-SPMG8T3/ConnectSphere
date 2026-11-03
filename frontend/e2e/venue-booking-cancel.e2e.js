// The coordinator cancels a venue booking (SCRUM-85) against real data, on throwaway
// venues and events in 2031. Cases: docs/test-cases/venues.md.
import { API_URL, expect, seedSession, test } from "./support/fixtures.js";
import {
  createThrowawayBooking,
  createThrowawayEvent,
  createThrowawayVenue,
  readThrowawayBooking,
  readThrowawayEvent,
  setThrowawayEventStatus,
} from "./support/throwaway.js";

test("TC-BCAN-007 the coordinator cancels a Confirmed event's booking from the event page and can request another",
  async ({ page, sharedSessions }) => {
    const venue = createThrowawayVenue("BCAN-007");
    const event = createThrowawayEvent("BCAN-007", "2031-10-13 10:00+08", "2031-10-13 12:00+08");
    const booking = createThrowawayBooking(event, venue.id, "2031-10-13 10:00+08", "2031-10-13 12:00+08", "approved");
    setThrowawayEventStatus(event, "confirmed");
    await seedSession(page, await sharedSessions("event_coordinator"));
    await page.goto(`/coordinator/events/${event.id}`);

    await page.getByRole("button", { name: `Cancel booking: ${venue.name}` }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("Cancel this venue booking?");
    await expect(dialog).toContainText("goes back to Planning");
    const sent = page.waitForResponse((r) => r.url().endsWith(`/venue-bookings/${booking.id}/cancel`));
    await dialog.getByRole("button", { name: "Cancel booking", exact: true }).click();

    expect((await sent).status()).toBe(200);
    // AC2: the event's space offers a venue search again; AC4: the event is back in Planning.
    await expect(page.getByRole("link", { name: "Find venue" })).toBeVisible();
    await expect(page.getByRole("button", { name: `Cancel booking: ${venue.name}` })).toHaveCount(0);
    expect(readThrowawayBooking(booking.id).status).toBe("cancelled");
    expect(readThrowawayEvent(event.id).status).toBe("planning");
  });

test("TC-BCAN-008 venue staff read who cancelled the booking in its history", async ({ page, sharedSessions }) => {
  const venue = createThrowawayVenue("BCAN-008");
  const event = createThrowawayEvent("BCAN-008", "2031-10-14 10:00+08", "2031-10-14 12:00+08");
  const booking = createThrowawayBooking(event, venue.id, "2031-10-14 10:00+08", "2031-10-14 12:00+08", "approved");
  const coordinator = await sharedSessions("event_coordinator");
  const cancelled = await page.request.post(`${API_URL}/venue-bookings/${booking.id}/cancel`, {
    headers: { Authorization: `Bearer ${coordinator.token}` },
  });
  expect(cancelled.status()).toBe(200);

  await seedSession(page, await sharedSessions("venue_staff"));
  await page.goto(`/bookings/${booking.id}`);

  // AC6: who cancelled it and when, on the booking's own page.
  await expect(page.getByTestId("booking-history")).toContainText("Cancelled by the coordinator");
  await expect(page.getByTestId("booking-history")).toContainText(coordinator.profile.full_name);
});
