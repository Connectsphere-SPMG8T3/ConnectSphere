// Venue staff record preparation per venue booking (SCRUM-109) against real data, on
// throwaway venues and events in 2031. Cases: docs/test-cases/venues.md.
import { expect, seedSession, test } from "./support/fixtures.js";
import {
  createThrowawayBooking,
  createThrowawayEvent,
  createThrowawayVenue,
  readThrowawayEvent,
  setThrowawayEventStatus,
} from "./support/throwaway.js";

test("TC-VENUE-109-006 venue staff save a stage and note; the coordinator sees both, the organiser the stage only",
  async ({ page, browser, baseURL, sharedSessions }) => {
    const venue = createThrowawayVenue("VPREP-006");
    const event = createThrowawayEvent("VPREP-006", "2031-12-22 09:00+08", "2031-12-22 12:00+08");
    const booking = createThrowawayBooking(event, venue.id, "2031-12-22 09:00+08", "2031-12-22 12:00+08", "approved");
    setThrowawayEventStatus(event, "confirmed");

    await seedSession(page, await sharedSessions("venue_staff"));
    await page.goto(`/bookings/${booking.id}`);
    const panel = page.getByTestId("venue-preparation");
    await panel.getByLabel("Preparation stage").selectOption("in_progress");
    await panel.getByLabel("Internal note").fill("Stage rigging booked");
    const sent = page.waitForResponse((r) => r.url().endsWith(`/venue-bookings/${booking.id}/preparation`));
    await panel.getByRole("button", { name: "Save preparation progress" }).click();
    expect((await sent).status()).toBe(200);
    await expect(panel).toContainText("Progress: in progress");
    // AC3: the first update moved the Confirmed event to Preparation.
    expect(readThrowawayEvent(event.id).status).toBe("preparation");

    // Each viewer is a different session, so their own browser context.
    const viewer = async (role, path) => {
      const context = await browser.newContext({ baseURL });
      const viewerPage = await context.newPage();
      await seedSession(viewerPage, await sharedSessions(role));
      await viewerPage.goto(path);
      return { context, page: viewerPage };
    };

    // AC4: the coordinator sees the stage and the internal note.
    const coordinator = await viewer("event_coordinator", `/coordinator/events/${event.id}`);
    await expect(coordinator.page.getByText("Venue preparation: in progress").first()).toBeVisible();
    await expect(coordinator.page.getByText("Internal note: Stage rigging booked").first()).toBeVisible();
    await coordinator.context.close();

    // AC4, CR-111: the organiser sees the stage, never the note.
    const organiser = await viewer("event_organiser", `/events/${event.id}`);
    await expect(organiser.page.getByText(/Venue preparation: in progress/i).first()).toBeVisible();
    await expect(organiser.page.getByText("Stage rigging booked")).toHaveCount(0);
    await organiser.context.close();
  });

test("TC-VENUE-109-007 venue staff see a Planning event's progress but saving it is refused",
  async ({ page, sharedSessions }) => {
    const venue = createThrowawayVenue("VPREP-007");
    const event = createThrowawayEvent("VPREP-007", "2031-12-23 09:00+08", "2031-12-23 12:00+08");
    const booking = createThrowawayBooking(event, venue.id, "2031-12-23 09:00+08", "2031-12-23 12:00+08", "approved");

    await seedSession(page, await sharedSessions("venue_staff"));
    await page.goto(`/bookings/${booking.id}`);
    const panel = page.getByTestId("venue-preparation");
    await panel.getByLabel("Preparation stage").selectOption("completed");
    const sent = page.waitForResponse((r) => r.url().endsWith(`/venue-bookings/${booking.id}/preparation`));
    await panel.getByRole("button", { name: "Save preparation progress" }).click();
    // AC1: refused while the event is in Planning, and the event stays there.
    expect((await sent).status()).toBe(409);
    await expect(page.getByText("Venue preparation opens once the Safety Officer has confirmed the event."))
      .toBeVisible();
    expect(readThrowawayEvent(event.id).status).toBe("planning");
  });
