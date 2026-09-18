/**
 * Singapore time helpers, shared by the venue search store and the venue-staff
 * calendar (SCRUM-39, SCRUM-70).
 *
 * Every venue is in Singapore, which has never observed daylight saving, so a
 * fixed +08:00 offset is exact rather than an approximation. That is what makes
 * the arithmetic below safe: shifting an instant by +8h and then reading its
 * UTC fields yields the Singapore wall-clock fields, with no zone database and
 * no locale in the way (REQUIREMENTS §4: stored UTC, displayed Asia/Singapore).
 *
 * This module is for *deciding which day something falls on*. Formatting a date
 * for a person still goes through `Intl.DateTimeFormat` with
 * `timeZone: "Asia/Singapore"`, as the coordinator dashboard does — an Intl
 * format string is the right tool for display and the wrong one for a key.
 */

export const SINGAPORE_OFFSET = "+08:00";
export const SINGAPORE_OFFSET_MS = 8 * 60 * 60 * 1000;

/** Build an ISO instant from a date and time the user typed, read as SGT. */
export function toSingaporeIso(date, time) {
  return `${date}T${time}:00${SINGAPORE_OFFSET}`;
}

/** Coerce a Date, an ISO string, or an epoch number to a Date. */
export function toInstant(value) {
  return value instanceof Date ? value : new Date(value);
}

/**
 * The Singapore calendar date an instant falls on, as `"YYYY-MM-DD"`.
 *
 * Never slice a raw ISO string to get this. `"2026-10-10T16:00:00Z"` and
 * `"2026-10-11T00:00:00+08:00"` are the *same instant*, but slicing them gives
 * different days — which day you got would depend on how the backend happened
 * to serialise the value. Working from the instant removes that entirely.
 */
export function singaporeDayKey(value) {
  const instant = toInstant(value);
  return new Date(instant.getTime() + SINGAPORE_OFFSET_MS).toISOString().slice(0, 10);
}

/** The instant at which a `"YYYY-MM-DD"` Singapore day begins. */
export function startOfSingaporeDayUtc(dayKey) {
  return new Date(`${dayKey}T00:00:00${SINGAPORE_OFFSET}`);
}
