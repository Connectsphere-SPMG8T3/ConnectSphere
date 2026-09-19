import { DEFAULT_EVENT_TIMEZONE, getDateString } from "@/features/events/timezones";

export function getSingaporeDateString(date = new Date(), timeZone = DEFAULT_EVENT_TIMEZONE) {
  return getDateString(date, timeZone);
}

export function getEarliestEventDate(timeZone = DEFAULT_EVENT_TIMEZONE) {
  const [year, month, day] = getSingaporeDateString(new Date(), timeZone).split("-").map(Number);
  return getDateString(new Date(Date.UTC(year, month - 1, day + 1)), timeZone);
}

export function isEventDateAfterToday(eventDate, today = getSingaporeDateString()) {
  return Boolean(eventDate) && eventDate > today;
}

export function getRegistrationOpeningError(opensAt, today = getSingaporeDateString()) {
  if (opensAt && opensAt.slice(0, 10) <= today) return "Registration opening date must be after today.";
  return "";
}

export function getRegistrationClosingError({ opensAt, closesAt, eventDate, eventEndTime }, today = getSingaporeDateString()) {
  if (!opensAt || !closesAt) return "";
  if (closesAt.slice(0, 10) <= today) return "Registration closing date must be after today.";
  if (closesAt <= opensAt) return "Registration closing time must be after opening time.";
  if (eventDate && eventEndTime && `${eventDate}T${eventEndTime}` < closesAt) {
    return "Registration closing time cannot be after the event end time.";
  }
  return "";
}
