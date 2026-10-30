import { describe, expect, it } from "vitest";

import {
  filterAndSortRegistrations,
  formatRegistrationPeriod,
  registrationStatusLabel,
  splitRegistrationsByEndTime,
} from "@/features/registrations/registeredEvents";
import * as registrationPresentation from "@/features/registrations/registeredEvents";

describe("registered event presentation", () => {
  it("moves an event to Past when its end time is exactly now", () => {
    const now = Date.parse("2026-10-24T08:00:00Z");
    const registration = { id: "registration-1", event: { ends_at: "2026-10-24T08:00:00Z" } };
    const result = splitRegistrationsByEndTime([registration], now);

    expect(result).toEqual({ upcoming: [], past: [registration] });
  });

  it("keeps an in-progress event under Upcoming until its end time", () => {
    const registration = { id: "registration-1", event: { ends_at: "2026-10-24T08:00:01Z" } };
    const result = splitRegistrationsByEndTime(
      [registration],
      Date.parse("2026-10-24T08:00:00Z"),
    );

    expect(result.upcoming).toEqual([registration]);
    expect(result.past).toEqual([]);
  });

  it("rejects an invalid event end time instead of silently grouping it", () => {
    expect(() =>
      splitRegistrationsByEndTime(
        [{ id: "registration-1", event: { ends_at: "invalid" } }],
        0,
      ),
    ).toThrow("Registration registration-1 has an invalid event end time.");
  });

  it("formats the schedule in the event timezone", () => {
    expect(
      formatRegistrationPeriod({
        starts_at: "2026-10-24T01:00:00Z",
        ends_at: "2026-10-24T03:00:00Z",
        event_timezone: "Asia/Singapore",
      }),
    ).toBe("24 Oct 2026 9:00am - 11:00am");
  });

  it("labels supported statuses and preserves an unfamiliar status", () => {
    expect(registrationStatusLabel("registered")).toBe("Registered");
    expect(registrationStatusLabel("waitlisted")).toBe("Waitlisted");
    expect(registrationStatusLabel("invited")).toBe("Invitation pending");
    expect(registrationStatusLabel("cancelled")).toBe("cancelled");
  });

  it("allows withdrawal only for registered events before the configured cutoff or event start", () => {
    const canWithdraw = registrationPresentation.canWithdrawRegistration;
    expect(canWithdraw).toBeTypeOf("function");
    if (typeof canWithdraw !== "function") return;

    const now = Date.parse("2026-10-24T08:00:00Z");
    const registration = {
      status: "registered",
      event: {
        starts_at: "2026-10-24T09:00:00Z",
        withdrawal_closes_at: null,
      },
    };

    expect(canWithdraw(registration, now)).toBe(true);
    expect(canWithdraw({
      ...registration,
      event: { ...registration.event, withdrawal_closes_at: "2026-10-24T08:00:00Z" },
    }, now)).toBe(false);
    expect(canWithdraw({
      ...registration,
      status: "waitlisted",
    }, now)).toBe(false);
    expect(canWithdraw({
      ...registration,
      event: { ...registration.event, withdrawal_closes_at: "2026-10-24T07:59:59Z" },
    }, now)).toBe(false);
  });

  it("filters registrations by name, status, and period, then sorts by event name or date", () => {
    const filter = registrationPresentation.filterAndSortRegistrations;
    expect(filter).toBeTypeOf("function");
    if (!filter) return;

    const registrations = [
      {
        id: "registration-b",
        status: "waitlisted",
        event: {
          id: "event-b",
          name: "Blue Forum",
          starts_at: "2026-10-26T09:00:00Z",
          ends_at: "2026-10-26T10:00:00Z",
        },
      },
      {
        id: "registration-a",
        status: "registered",
        event: {
          id: "event-a",
          name: "Amber Forum",
          starts_at: "2026-10-25T09:00:00Z",
          ends_at: "2026-10-25T10:00:00Z",
        },
      },
      {
        id: "registration-invited",
        status: "invited",
        event: {
          id: "event-invited",
          name: "Invitation Forum",
          starts_at: "2026-10-25T10:00:00Z",
          ends_at: "2026-10-25T11:00:00Z",
        },
      },
      {
        id: "registration-past",
        status: "registered",
        event: {
          id: "event-past",
          name: "Past Forum",
          starts_at: "2026-10-20T09:00:00Z",
          ends_at: "2026-10-20T10:00:00Z",
        },
      },
    ];
    const now = Date.parse("2026-10-24T08:00:00Z");

    expect(filter(registrations, {
      search: "BLUE",
      statuses: ["waitlisted"],
      period: "upcoming",
      now,
    })).toEqual([registrations[0]]);
    expect(filter(registrations, {
      statuses: ["invited"],
      period: "upcoming",
      now,
    })).toEqual([registrations[2]]);
    expect(filter(registrations, {
      sortBy: "name",
      direction: "asc",
      period: "all",
      now,
    }).map(({ id }) => id)).toEqual([
      "registration-a",
      "registration-b",
      "registration-invited",
      "registration-past",
    ]);
    expect(filter(registrations, {
      sortBy: "date",
      direction: "desc",
      period: "all",
      now,
    }).map(({ id }) => id)).toEqual([
      "registration-b",
      "registration-invited",
      "registration-a",
      "registration-past",
    ]);
  });

  it.each([
    ["unsupported status", { statuses: ["cancelled"] }, [], "unsupported status"],
    ["unsupported period", { period: "future" }, [], "Unsupported registration period"],
    ["unsupported sort field", { sortBy: "venue" }, [], "Unsupported registration sort field"],
    ["unsupported sort direction", { direction: "sideways" }, [], "Unsupported registration sort direction"],
    [
      "invalid event start time",
      {},
      [{ id: "invalid-start", status: "registered", event: { name: "Invalid", starts_at: "invalid", ends_at: "2026-10-25T10:00:00Z" } }],
      "invalid event start time",
    ],
    [
      "invalid event end time",
      { period: "past" },
      [{ id: "invalid-end", status: "registered", event: { name: "Invalid", starts_at: "2026-10-25T09:00:00Z", ends_at: "invalid" } }],
      "invalid event end time",
    ],
  ])("rejects %s", (_description, filters, registrations, message) => {
    expect(() => filterAndSortRegistrations(registrations, filters)).toThrow(message);
  });

  it("summarizes upcoming registrations and distinct past registrations from live data", () => {
    const summarize = registrationPresentation.summarizeAttendeeDashboard;
    expect(summarize).toBeTypeOf("function");
    if (!summarize) return;

    const now = Date.parse("2026-10-24T08:00:00Z");
    const registrations = [
      { id: "past-1", status: "registered", event: { id: "past", ends_at: "2026-10-24T08:00:00Z" } },
      { id: "past-2", status: "registered", event: { id: "past", ends_at: "2026-10-24T08:00:00Z" } },
      { id: "past-waitlist", status: "waitlisted", event: { id: "past-waitlist", ends_at: "2026-10-23T08:00:00Z" } },
      { id: "upcoming-1", status: "registered", event: { id: "upcoming", ends_at: "2026-10-24T08:00:01Z" } },
      { id: "upcoming-2", status: "waitlisted", event: { id: "in-progress", ends_at: "2026-10-24T09:00:00Z" } },
      { id: "upcoming-invited", status: "invited", event: { id: "invited", ends_at: "2026-10-24T10:00:00Z" } },
    ];

    expect(summarize(registrations, [
      { id: "open", availability: "open" },
      { id: "full", availability: "full" },
      { id: "closed", availability: "closed" },
    ], now)).toEqual({
      upcomingRegistrations: 3,
      openEvents: 1,
      pastRegistrations: 1,
    });
  });
});
