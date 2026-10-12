import { describe, expect, it } from "vitest";

import { BOOKING_STATUS_LABELS, venuePanelState } from "@/features/venues/bookingRequest";

const booking = (status) => ({
  id: "b1", venue_id: "v1", venue_name: "Innovation Lab", status, expires_at: "2026-11-01T04:00:00Z",
});

describe("venuePanelState", () => {
  it("shows a held or approved venue as booked (SCRUM-19)", () => {
    const event = { status: "planning", venue_booking: booking("held") };
    expect(venuePanelState(event)).toEqual({ kind: "booked", booking: event.venue_booking });
  });

  it("offers a request for a planning event with no venue", () => {
    expect(venuePanelState({ status: "planning", venue_booking: null })).toEqual({ kind: "can-request" });
  });

  it("shows an expired hold and offers the venue again while planning (CR-99 AC7)", () => {
    const event = { status: "planning", venue_booking: booking("expired") };
    expect(venuePanelState(event)).toEqual({ kind: "expired", booking: event.venue_booking, canRequest: true });
  });

  it("shows an expired hold without offering a request outside planning", () => {
    const event = { status: "returned", venue_booking: booking("expired") };
    expect(venuePanelState(event)).toEqual({ kind: "expired", booking: event.venue_booking, canRequest: false });
  });

  it("labels the expired status for the coordinator", () => {
    expect(BOOKING_STATUS_LABELS.expired).toBe("Expired");
  });
});
