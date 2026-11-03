// SCRUM-85: which of a venue panel's bookings the assigned coordinator is offered
// to cancel. UX only: the API decides (AC3, AC5, AC10).
import { describe, expect, it } from "vitest";

import { historyActionLabel } from "@/features/venues/bookingDecision";
import { canCancelBooking, cancellableBookings } from "@/features/venues/bookingRequest";

const NOW = new Date("2031-03-01T00:00:00Z");
const EVENT = { id: "e1", status: "planning", starts_at: "2031-03-10T06:00:00Z" };
const booking = (status, extra = {}) => ({ id: `b-${status}`, venue_name: "Innovation Lab", status, ...extra });

describe("canCancelBooking", () => {
  it.each(["held", "approved", "re_review"])("offers a %s booking", (status) => {
    expect(canCancelBooking(booking(status), EVENT, NOW)).toBe(true);
  });

  it("offers an Affected booking (AC1)", () => {
    expect(canCancelBooking(booking("approved", { flag: "affected" }), EVENT, NOW)).toBe(true);
  });

  it.each(["rejected", "cancelled", "released", "expired"])("never offers a %s booking (AC3)", (status) => {
    expect(canCancelBooking(booking(status), EVENT, NOW)).toBe(false);
  });

  it.each(["safety_review", "confirmed", "preparation", "under_review"])("offers it while the event is %s (AC4, AC8)", (status) => {
    expect(canCancelBooking(booking("approved"), { ...EVENT, status }, NOW)).toBe(true);
  });

  it.each(["cancelled", "completed", "rejected"])("never once the event is %s (AC10)", (status) => {
    expect(canCancelBooking(booking("approved"), { ...EVENT, status }, NOW)).toBe(false);
  });

  it("stops the moment the event starts, not a second before (AC10)", () => {
    const starts = new Date(EVENT.starts_at);
    expect(canCancelBooking(booking("approved"), EVENT, new Date(starts.getTime() - 1000))).toBe(true);
    expect(canCancelBooking(booking("approved"), EVENT, starts)).toBe(false);
  });

  it("has nothing to offer without a booking or an event", () => {
    expect(canCancelBooking(null, EVENT, NOW)).toBe(false);
    expect(canCancelBooking(booking("held"), null, NOW)).toBe(false);
  });
});

describe("cancellableBookings", () => {
  it("lists the panel's booking", () => {
    const held = booking("held");
    expect(cancellableBookings({ kind: "booked", booking: held }, EVENT, NOW)).toEqual([
      { booking: held, label: "Cancel booking" },
    ]);
  });

  it("lists a pending replacement beside its original (AC1)", () => {
    const original = booking("approved", { flag: "affected" });
    const replacement = booking("held", { id: "b-replacement", venue_name: "Heritage Hall" });
    expect(cancellableBookings({ kind: "replacing", booking: original, replacement }, EVENT, NOW)).toEqual([
      { booking: original, label: "Cancel booking" },
      { booking: replacement, label: "Cancel replacement request" },
    ]);
  });

  it("lists nothing for an expired hold or an empty panel", () => {
    expect(cancellableBookings({ kind: "expired", booking: booking("expired") }, EVENT, NOW)).toEqual([]);
    expect(cancellableBookings({ kind: "can-request" }, EVENT, NOW)).toEqual([]);
    expect(cancellableBookings(null, EVENT, NOW)).toEqual([]);
  });
});

describe("historyActionLabel for a cancellation (AC6)", () => {
  it("says the coordinator cancelled it", () => {
    expect(historyActionLabel("cancelled")).toBe("Cancelled by the coordinator");
  });
});
