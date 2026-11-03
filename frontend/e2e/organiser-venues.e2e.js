// CR-111: the organiser sees each venue on their event and who their coordinator is, against
// real data on a throwaway Confirmed event. Cases: docs/test-cases/events.md (TC-ORGV-001 to 004).
import { API_URL, expect, seedSession, test } from "./support/fixtures.js";
import {
  createThrowawayBlock,
  createThrowawayBooking,
  createThrowawayEvent,
  deleteThrowawayBlocks,
  setThrowawayEventStatus,
} from "./support/throwaway.js";

const SEMINAR_ROOM_1 = "b0000000-0000-4000-8000-000000000003";
const STARTS = "2031-12-08 10:00+08";
const ENDS = "2031-12-08 12:00+08";
// The second case books the same room on another day, so the two throwaway bookings can't overlap.
const DENIED_STARTS = "2031-12-10 10:00+08";
const DENIED_ENDS = "2031-12-10 12:00+08";

test.afterEach(() => deleteThrowawayBlocks());

test("TC-ORGV-001/002/003 the organiser sees an affected venue and its next action, never the internal reason", async ({
  page,
  sharedSessions,
}) => {
  const event = createThrowawayEvent("cr111", STARTS, ENDS);
  setThrowawayEventStatus(event, "confirmed");
  createThrowawayBooking(event, SEMINAR_ROOM_1, STARTS, ENDS, "approved");
  createThrowawayBlock(SEMINAR_ROOM_1, "2031-12-08 00:00+08", "2031-12-09 00:00+08");

  await seedSession(page, await sharedSessions("event_organiser"));
  await page.goto(`/events/${event.id}`);

  // AC2, AC3: the venue is listed with its status and what happens next.
  const venue = page.getByTestId("organiser-venue").first();
  await expect(venue).toContainText("Seminar Room 1");
  await expect(venue).toContainText("Affected");
  await expect(venue).toContainText("no longer available");
  await expect(venue).toContainText("Your coordinator will contact you");
  // AC1: the assigned coordinator is named, not "Unassigned".
  await expect(page.getByText(/Coordinator: (?!Unassigned)\S+/)).toBeVisible();
  // AC6: the coordinator's flag reason ("Venue unavailable: Maintenance") never reaches the page.
  await expect(page.getByText("Venue unavailable")).toHaveCount(0);
  await expect(page.getByText("Maintenance")).toHaveCount(0);
});

test("TC-ORGV-004 only the owning organiser, acting as organiser, can read the venue list", async ({ sharedSessions, request }) => {
  const event = createThrowawayEvent("cr111-denied", DENIED_STARTS, DENIED_ENDS);
  setThrowawayEventStatus(event, "confirmed");
  createThrowawayBooking(event, SEMINAR_ROOM_1, DENIED_STARTS, DENIED_ENDS, "approved");

  const attendee = await sharedSessions("attendee");
  const wrongRole = await request.get(`${API_URL}/events/${event.id}`, { headers: { Authorization: `Bearer ${attendee.token}` } });
  expect(wrongRole.status()).toBe(403);

  const organiser = await sharedSessions("event_organiser");
  const owner = await request.get(`${API_URL}/events/${event.id}`, { headers: { Authorization: `Bearer ${organiser.token}` } });
  expect(owner.status()).toBe(200);
  expect((await owner.json()).organiser_venues[0].venue_name).toBe("Seminar Room 1");
});
