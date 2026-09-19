export const DEFAULT_EVENT_TIMEZONE = "Asia/Singapore";

export const EVENT_TIMEZONES = [
  { value: "Asia/Singapore", label: "Singapore (UTC+08:00)" },
  { value: "Asia/Kuala_Lumpur", label: "Kuala Lumpur (UTC+08:00)" },
  { value: "Asia/Brunei", label: "Brunei (UTC+08:00)" },
  { value: "Asia/Manila", label: "Manila (UTC+08:00)" },
  { value: "Asia/Bangkok", label: "Bangkok (UTC+07:00)" },
  { value: "Asia/Ho_Chi_Minh", label: "Ho Chi Minh City (UTC+07:00)" },
  { value: "Asia/Phnom_Penh", label: "Phnom Penh (UTC+07:00)" },
  { value: "Asia/Vientiane", label: "Vientiane (UTC+07:00)" },
  { value: "Asia/Jakarta", label: "Jakarta (UTC+07:00)" },
  { value: "Asia/Yangon", label: "Yangon (UTC+06:30)" },
];

function getParts(date, timeZone) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  return Object.fromEntries(parts.map(({ type, value }) => [type, value]));
}

export function getDateString(date = new Date(), timeZone = DEFAULT_EVENT_TIMEZONE) {
  const parts = getParts(date, timeZone);
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function getEarliestEventDate(timeZone = DEFAULT_EVENT_TIMEZONE) {
  const today = getDateString(new Date(), timeZone);
  const [year, month, day] = today.split("-").map(Number);
  return getDateString(new Date(Date.UTC(year, month - 1, day + 1)), timeZone);
}

export function toZonedIso(date, time, timeZone = DEFAULT_EVENT_TIMEZONE) {
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  const requestedWallTime = Date.UTC(year, month - 1, day, hour, minute);
  const representedParts = getParts(new Date(requestedWallTime), timeZone);
  const representedWallTime = Date.UTC(
    Number(representedParts.year),
    Number(representedParts.month) - 1,
    Number(representedParts.day),
    Number(representedParts.hour),
    Number(representedParts.minute),
  );
  return new Date(requestedWallTime - (representedWallTime - requestedWallTime)).toISOString();
}

export function fromZonedDateTime(value, timeZone = DEFAULT_EVENT_TIMEZONE) {
  if (!value) return { date: "", time: "" };
  const parts = getParts(new Date(value), timeZone);
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
}