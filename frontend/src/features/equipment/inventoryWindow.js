// The window tech support's Inventory & status table counts (D46). Reserved and
// maintenance figures are the busiest moment inside it (§6.16 AV-R2), so a
// reservation for another day only shows once the window covers that day.
// Values are datetime-local strings, read and described as entered.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LOCAL = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/;

const pad = (n) => String(n).padStart(2, "0");

function dayAt(now, hour) {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(hour)}:00`;
}

export function defaultInventoryWindow(now = new Date()) {
  return { startAt: dayAt(now, 9), endAt: dayAt(now, 17) };
}

export function inventoryWindowError(startAt, endAt) {
  if (!startAt || !endAt) return "Choose a start and an end for the inventory window.";
  if (new Date(endAt) <= new Date(startAt)) return "End time must be later than the start time.";
  return null;
}

function parts(value) {
  const match = LOCAL.exec(value ?? "");
  if (!match) return null;
  const [, year, month, day, hour, minute] = match.map(Number);
  const time = `${hour % 12 || 12}:${pad(minute)} ${hour < 12 ? "am" : "pm"}`;
  return { date: `${day} ${MONTHS[month - 1]} ${year}`, time };
}

export function describeInventoryWindow(startAt, endAt) {
  const start = parts(startAt);
  const end = parts(endAt);
  if (!start || !end) return "";
  const until = start.date === end.date ? end.time : `${end.date}, ${end.time}`;
  return `${start.date}, ${start.time} – ${until}`;
}
