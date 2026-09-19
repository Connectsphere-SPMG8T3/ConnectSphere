function formatSingaporeDate(date) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "Asia/Singapore",
    year: "numeric",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export function getSingaporeDateString(date = new Date()) {
  return formatSingaporeDate(date);
}

export function getEarliestEventDate() {
  const [year, month, day] = getSingaporeDateString().split("-").map(Number);
  return formatSingaporeDate(new Date(Date.UTC(year, month - 1, day + 1)));
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
