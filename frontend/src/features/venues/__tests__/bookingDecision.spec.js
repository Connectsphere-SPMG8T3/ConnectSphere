import { describe, expect, it } from "vitest";

import {
  REJECTION_TEXT_MAX_LENGTH,
  canApproveBooking,
  canRejectBooking,
  canRestoreBooking,
  formatBookingPeriod,
  formatDecisionTime,
  historyActionLabel,
  rejectionErrors,
  rejectionPayload,
} from "@/features/venues/bookingDecision";
import { bookingStatusLabel } from "@/features/venues/dashboard";

describe("rejectionErrors (SCRUM-38 AC2, AC3)", () => {
  it("needs a reason that isn't blank", () => {
    expect(rejectionErrors({ reason: "", suggestion: "" })).toEqual({ reason: "Give a reason for rejecting this request." });
    expect(rejectionErrors({ reason: "  \n ", suggestion: "" })).toEqual({ reason: "Give a reason for rejecting this request." });
  });

  it("caps the reason and the suggestion at 1000 characters, counted after trimming", () => {
    expect(REJECTION_TEXT_MAX_LENGTH).toBe(1000);
    expect(rejectionErrors({ reason: ` ${"x".repeat(1000)} `, suggestion: "y".repeat(1000) })).toEqual({});
    expect(rejectionErrors({ reason: "x".repeat(1001), suggestion: "" })).toEqual({
      reason: "Keep the reason to 1000 characters.",
    });
    expect(rejectionErrors({ reason: "Closed", suggestion: "y".repeat(1001) })).toEqual({
      suggestion: "Keep the suggestion to 1000 characters.",
    });
  });

  it("accepts a reason with no suggestion", () => {
    expect(rejectionErrors({ reason: "Capacity exceeded" })).toEqual({});
  });
});

describe("rejectionPayload", () => {
  it("sends the trimmed reason, and no suggestion when it was left blank", () => {
    expect(rejectionPayload({ reason: "  Capacity exceeded ", suggestion: "  " })).toEqual({
      reason: "Capacity exceeded", suggestion: null,
    });
    expect(rejectionPayload({ reason: "Closed", suggestion: " Try Heritage Hall " })).toEqual({
      reason: "Closed", suggestion: "Try Heritage Hall",
    });
    expect(rejectionPayload({ reason: "Closed" })).toEqual({ reason: "Closed", suggestion: null });
  });
});

describe("canRejectBooking (AC9, AC11)", () => {
  it("offers Reject only to a session acting as venue staff, and only on a held booking", () => {
    expect(canRejectBooking({ status: "held" }, "venue_staff")).toBe(true);
    expect(canRejectBooking({ status: "held" }, "event_coordinator")).toBe(false);
    for (const status of ["approved", "re_review", "rejected", "cancelled", "released", "expired"]) {
      expect(canRejectBooking({ status }, "venue_staff")).toBe(false);
    }
    expect(canRejectBooking(null, "venue_staff")).toBe(false);
  });
});

describe("canApproveBooking (SCRUM-36 AC6, AC8)", () => {
  it("offers Approve only to a session acting as venue staff, and only on a held booking", () => {
    expect(canApproveBooking({ status: "held" }, "venue_staff")).toBe(true);
    for (const role of ["event_coordinator", "event_organiser", "event_coordinator_lead", "safety_officer"]) {
      expect(canApproveBooking({ status: "held" }, role)).toBe(false);
    }
    for (const status of ["approved", "re_review", "rejected", "cancelled", "released", "expired"]) {
      expect(canApproveBooking({ status }, "venue_staff")).toBe(false);
    }
    expect(canApproveBooking(null, "venue_staff")).toBe(false);
  });
});

describe("canRestoreBooking (CR-95 AC9)", () => {
  it("offers Restore to venue staff on a held or approved booking flagged affected", () => {
    for (const status of ["held", "approved"]) {
      expect(canRestoreBooking({ status, flag: "affected" }, "venue_staff")).toBe(true);
    }
  });

  it("offers nothing to another role, for another flag or flagless, or once the booking is no longer live", () => {
    expect(canRestoreBooking({ status: "approved", flag: "affected" }, "event_coordinator")).toBe(false);
    expect(canRestoreBooking({ status: "approved", flag: "unsuitable" }, "venue_staff")).toBe(false);
    expect(canRestoreBooking({ status: "approved", flag: null }, "venue_staff")).toBe(false);
    for (const status of ["re_review", "rejected", "cancelled", "released", "expired"]) {
      expect(canRestoreBooking({ status, flag: "affected" }, "venue_staff")).toBe(false);
    }
    expect(canRestoreBooking(null, "venue_staff")).toBe(false);
  });
});

describe("formatBookingPeriod", () => {
  it("shows the day and the time span in Singapore time", () => {
    expect(formatBookingPeriod({ starts_at: "2031-03-10T06:00:00Z", ends_at: "2031-03-10T09:00:00Z" }))
      .toBe("Mon, 10 Mar 2031, 14:00–17:00");
  });

  it("names both days when the booking crosses midnight in Singapore", () => {
    expect(formatBookingPeriod({ starts_at: "2031-03-10T14:00:00Z", ends_at: "2031-03-10T17:00:00Z" }))
      .toBe("Mon, 10 Mar 2031, 22:00 – Tue, 11 Mar 2031, 01:00");
  });

  it("says so when there is no period", () => {
    expect(formatBookingPeriod(null)).toBe("Timing to be confirmed");
  });
});

describe("venue staff booking status labels", () => {
  it("names an expired hold (AC9, CR-99)", () => {
    expect(bookingStatusLabel("expired")).toBe("Expired");
    expect(bookingStatusLabel("rejected")).toBe("Rejected");
  });
});

describe("booking history wording (AC12)", () => {
  it("labels CR-99's actions and this story's rejection", () => {
    expect(historyActionLabel("rejected")).toBe("Rejected");
    expect(historyActionLabel("expired")).toBe("Expired");
    expect(historyActionLabel("expiry_changed")).toBe("Expiry changed");
    expect(historyActionLabel("something_new")).toBe("Something new");
    expect(historyActionLabel(null)).toBe("Changed");
  });

  it("dates a decision in Singapore time", () => {
    expect(formatDecisionTime("2031-03-01T02:00:00Z")).toBe("1 Mar 2031, 10:00");
    expect(formatDecisionTime(null)).toBe("time not recorded");
  });
});
