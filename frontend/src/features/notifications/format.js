const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** "just now", "5 min ago", "3 h ago", then the date ("18 Oct"). */
export function formatNotificationTime(iso, now = new Date()) {
  const then = new Date(iso);
  if (!iso || Number.isNaN(then.getTime())) return "";
  const age = now.getTime() - then.getTime();
  if (age < MINUTE) return "just now";
  if (age < HOUR) return `${Math.floor(age / MINUTE)} min ago`;
  if (age < DAY) return `${Math.floor(age / HOUR)} h ago`;
  return then.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
