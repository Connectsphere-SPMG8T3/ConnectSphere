import { describe, expect, it } from "vitest";

import {
  BOOKING_STATUS_LABELS,
  criteriaFromSpace,
  describeConflict,
  replacementSearchRoute,
  venuePanelState,
} from "@/features/venues/bookingRequest";

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

describe("venuePanelState for an affected booking (CR-95 AC3, AC4)", () => {
  const affected = (overrides = {}) => ({
    ...booking("approved"), id: "b-affected", flag: "affected", flag_reason: "Venue unavailable: Maintenance",
    event_space_request_id: null, ...overrides,
  });
  const replacement = (overrides = {}) => ({
    ...booking("held"), id: "b-new", venue_name: "Heritage Hall", flag: null, replaces_booking_id: "b-affected",
    event_space_request_id: null, ...overrides,
  });

  it.each(["planning", "safety_review", "confirmed"])(
    "says the venue is unavailable and offers a replacement on a %s event",
    (status) => {
      const event = { status, venue_booking: affected(), venue_bookings: [affected()] };

      expect(venuePanelState(event)).toEqual({
        kind: "affected", booking: affected(), reason: "Venue unavailable: Maintenance", canReplace: true,
      });
    },
  );

  it("does not offer a replacement on an event in any other status", () => {
    const event = { status: "returned", venue_bookings: [affected()] };

    expect(venuePanelState(event)).toMatchObject({ kind: "affected", canReplace: false });
  });

  it("shows the replacement being waited on instead of offering another", () => {
    const event = { status: "planning", venue_bookings: [affected(), replacement()] };

    expect(venuePanelState(event)).toEqual({ kind: "replacing", booking: affected(), replacement: replacement() });
  });

  it("looks at one space's bookings only", () => {
    const event = {
      status: "planning",
      venue_bookings: [
        affected({ event_space_request_id: "space-1" }),
        { ...booking("approved"), id: "b-ok", event_space_request_id: "space-2" },
      ],
    };

    expect(venuePanelState(event, { id: "space-1" }).kind).toBe("affected");
    expect(venuePanelState(event, { id: "space-2" })).toEqual({
      kind: "booked", booking: event.venue_bookings[1],
    });
  });

  it("ignores an affected booking that is no longer held or approved", () => {
    const event = { status: "planning", venue_booking: null, venue_bookings: [affected({ status: "released" })] };

    expect(venuePanelState(event)).toEqual({ kind: "can-request" });
  });
});

describe("replacementSearchRoute (CR-95 AC4)", () => {
  it("opens venue search for the event, naming the booking to replace", () => {
    expect(replacementSearchRoute({ id: "e1" }, null, { id: "b1" })).toEqual({
      name: "venue-search", query: { event: "e1", replaces: "b1" },
    });
  });

  it("names the space when the booking is a space's", () => {
    expect(replacementSearchRoute({ id: "e1" }, { id: "s1" }, { id: "b1" })).toEqual({
      name: "venue-search", query: { event: "e1", space: "s1", replaces: "b1" },
    });
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


describe('CR-104 Safety rejected panel', () => {
  const rejected = { ...booking('approved'), flag:'safety_rejected',flag_reason:'Exits blocked',event_space_request_id:'s1' };
  it.each(['planning','safety_review'])('names the booking and limits revision in %s', (status) => {
    expect(venuePanelState({status,venue_bookings:[rejected]})).toEqual({kind:'safety-rejected',booking:rejected,reason:'Exits blocked',canMarkRevised:status==='planning',canReplace:status==='planning'});
  });
  it('scopes the flag to its own space', () => {
    const other={...booking('approved'),id:'b2',event_space_request_id:'s2'};
    const event={status:'planning',venue_bookings:[rejected,other]};
    expect(venuePanelState(event,{id:'s1'}).kind).toBe('safety-rejected');
    expect(venuePanelState(event,{id:'s2'})).toEqual({kind:'booked',booking:other});
  });
  it('ignores a released flagged booking', () => {
    expect(venuePanelState({status:'planning',venue_bookings:[{...rejected,status:'released'}]}).kind).not.toBe('safety-rejected');
  });
  it('also supports the single-booking event contract', () => {
    expect(venuePanelState({status:'planning',venue_booking:rejected}).kind).toBe('safety-rejected');
  });
});

it("CR-100 labels an occupied window beyond supported dates without presenting clipped dates as exact", () => {
  expect(describeConflict({ kind: "booking", event_name: "Long setup",
    starts_at: "0001-01-01T00:00:00Z", ends_at: "9999-12-31T23:59:59Z" }, "Asia/Singapore"))
    .toBe('"Long setup" occupies it beyond supported dates, including setup and turnaround.');
});


describe("D52 Safety-rejected replacement", () => {
  const rejected = {...booking("approved"), id: "old", flag: "safety_rejected", flag_reason: "Exits blocked"};
  it.each(["held", "approved", "re_review"])("a %s replacement hides both actions and names it", (status) => {
    const replacement = {...booking(status), id: "r1", replaces_booking_id: rejected.id, venue_name: "Town Hall"};
    expect(venuePanelState({status: "planning", venue_bookings: [rejected, replacement]}))
      .toMatchObject({kind: "safety-rejected", replacement, canMarkRevised: false, canReplace: false});
  });
  it("a rejected replacement brings both actions back", () => {
    const replacement = {...booking("rejected"), id: "r1", replaces_booking_id: rejected.id};
    expect(venuePanelState({status: "planning", venue_bookings: [rejected, replacement]}))
      .toMatchObject({canMarkRevised: true, canReplace: true});
  });
});
