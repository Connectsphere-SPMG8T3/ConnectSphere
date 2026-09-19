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
  return formatSingaporeDate(new Date(Date.now() + 24 * 60 * 60 * 1000));
}

export function isEventDateAfterToday(eventDate, today = getSingaporeDateString()) {
  return Boolean(eventDate) && eventDate > today;
}
