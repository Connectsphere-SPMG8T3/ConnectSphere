import { describe, expect, it } from "vitest";

import {
  EVENT_TEXT_LIMITS,
  eventDescriptionError,
  eventNameError,
  eventPurposeError,
} from "@/features/events/eventTextRules";

// The organiser's form and the coordinator's edit dialog (story 112) both use these, so the
// two say the same thing. The bounds are the API's `EventName`, `EventPurpose` and
// `EventDescription`.
describe("EVENT_TEXT_LIMITS", () => {
  it("mirrors the API's bounds", () => {
    expect(EVENT_TEXT_LIMITS).toEqual({ nameMin: 3, nameMax: 150, purposeMax: 500, descriptionMax: 5000 });
  });
});

describe("eventNameError", () => {
  it.each([
    ["", "Enter an event title."],
    ["   ", "Enter an event title."],
    [undefined, "Enter an event title."],
    ["ab", "Use at least 3 characters."],
    ["  ab  ", "Use at least 3 characters."],
    ["abc", ""],
    ["  abc  ", ""],
    ["a".repeat(150), ""],
    ["a".repeat(151), "Use at most 150 characters."],
  ])("%j -> %j", (value, expected) => {
    expect(eventNameError(value)).toBe(expected);
  });
});

describe("eventPurposeError", () => {
  it.each([
    ["", "Enter the event purpose."],
    ["   ", "Enter the event purpose."],
    [null, "Enter the event purpose."],
    ["x", ""],
    ["p".repeat(500), ""],
    ["p".repeat(501), "Use at most 500 characters."],
  ])("%j -> %j", (value, expected) => {
    expect(eventPurposeError(value)).toBe(expected);
  });
});

describe("eventDescriptionError", () => {
  it.each([
    ["", ""],
    [null, ""],
    ["d".repeat(5000), ""],
    ["d".repeat(5001), "Use at most 5000 characters."],
  ])("%j -> %j", (value, expected) => {
    expect(eventDescriptionError(value)).toBe(expected);
  });
});
