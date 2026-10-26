function formatDate(value, timeZone, compact) {
  return new Intl.DateTimeFormat("en-SG", {
    ...(compact ? {} : { weekday: "long" }),
    day: "numeric",
    month: compact ? "short" : "long",
    year: "numeric",
    timeZone,
  }).format(value).replace(",", "");
}

function formatTime(value, timeZone) {
  return new Intl.DateTimeFormat("en-SG", {
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  }).format(value).replace(/\s/g, "");
}

export function formatEventDateRange(event, { compact = false } = {}) {
  if (!event?.starts_at) return "Date to be announced";

  const startsAt = new Date(event.starts_at);
  const startDate = formatDate(startsAt, event.event_timezone, compact);
  const startTime = formatTime(startsAt, event.event_timezone);
  if (!event.ends_at) return `${startDate} ${startTime}`;

  const endsAt = new Date(event.ends_at);
  const endDate = formatDate(endsAt, event.event_timezone, compact);
  const endTime = formatTime(endsAt, event.event_timezone);

  return startDate === endDate
    ? `${startDate} ${startTime} - ${endTime}`
    : `${startDate} ${startTime} - ${endDate} ${endTime}`;
}
