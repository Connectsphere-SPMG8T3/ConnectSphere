import { describe, expect, it } from "vitest";

import { BOOKING_STATUS_LABELS, criteriaFromSpace, describeConflict, venuePanelState } from "@/features/venues/bookingRequest";

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

  it("shows an expired hold only for its event space", () => {
    const expiredBooking = { ...booking("expired"), event_space_request_id: "space-1" };
    const event = { status: "planning", venue_booking: expiredBooking, venue_bookings: [] };

    expect(venuePanelState(event, { id: "space-1" })).toEqual({
      kind: "expired", booking: expiredBooking, canRequest: true,
    });
    expect(venuePanelState(event, { id: "space-2" })).toEqual({ kind: "can-request" });
  });

  it("labels the expired status for the coordinator", () => {
    expect(BOOKING_STATUS_LABELS.expired).toBe("Expired");
  });
});

describe("space booking criteria", () => {
  it("uses a space's own window instead of the event window", () => {
    const criteria = criteriaFromSpace({
      starts_at: "2026-10-20T09:00:00Z",
      ends_at: "2026-10-20T11:00:00Z",
    }, {
      starts_at: "2026-10-20T06:00:00Z",
      ends_at: "2026-10-20T12:00:00Z",
      expected_attendance: 100,
    });

    expect(criteria).toMatchObject({ date: "2026-10-20", startTime: "17:00", endTime: "19:00" });
  });

  it("inherits the event window when the space has no override", () => {
    const criteria = criteriaFromSpace({ starts_at: null, ends_at: null }, {
      starts_at: "2026-10-20T06:00:00Z",
      ends_at: "2026-10-20T12:00:00Z",
    });

    expect(criteria).toMatchObject({ date: "2026-10-20", startTime: "14:00", endTime: "20:00" });
  });
});

describe("describeConflict (SCRUM-21 AC2)", () => {
  it("names the other event and the window it occupies, in the event's timezone", () => {
    const conflict = {
      kind: "booking", event_name: "Alumni Night", block_reason: null,
      starts_at: "2031-04-07T01:30:00Z", ends_at: "2031-04-07T04:45:00Z",
    };
    expect(describeConflict(conflict, "Asia/Singapore")).toBe(
      "\"Alumni Night\" occupies it 7 Apr 2031, 9:30 am – 12:45 pm, including setup and turnaround.",
    );
    expect(describeConflict(conflict, "Europe/London")).toBe(
      "\"Alumni Night\" occupies it 7 Apr 2031, 2:30 am – 5:45 am, including setup and turnaround.",
    );
  });

  it("gives a block's reason instead of an event", () => {
    const conflict = {
      kind: "block", event_name: null, block_reason: "maintenance",
      starts_at: "2031-04-08T02:00:00Z", ends_at: "2031-04-08T04:00:00Z",
    };
    expect(describeConflict(conflict, "Asia/Singapore")).toBe(
      "Blocked for maintenance 8 Apr 2031, 10:00 am – 12:00 pm.",
    );
  });

  it("falls back to the reason as sent when it has no label", () => {
    const conflict = {
      kind: "block", event_name: null, block_reason: "Fire_Drill",
      starts_at: "2031-04-08T02:00:00Z", ends_at: "2031-04-08T04:00:00Z",
    };
    expect(describeConflict(conflict, "Asia/Singapore")).toBe("Blocked for fire_drill 8 Apr 2031, 10:00 am – 12:00 pm.");
  });

  it("writes out both dates when the window crosses midnight", () => {
    const conflict = {
      kind: "booking", event_name: "Night Market", block_reason: null,
      starts_at: "2031-04-07T14:00:00Z", ends_at: "2031-04-07T17:00:00Z",
    };
    expect(describeConflict(conflict, "Asia/Singapore")).toBe(
      "\"Night Market\" occupies it 7 Apr 2031, 10:00 pm – 8 Apr 2031, 1:00 am, including setup and turnaround.",
    );
  });

  it("says nothing when the API named nothing", () => {
    expect(describeConflict(null, "Asia/Singapore")).toBe("");
  });
});
