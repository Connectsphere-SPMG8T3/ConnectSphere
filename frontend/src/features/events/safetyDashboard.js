// CR-103 AC7: the Safety Officer dashboard's figures. The API returns complete
// lists, so the page counts them rather than trusting a separate counts field.
const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

function plural(count, unit) {
  return `${count} ${unit}${count === 1 ? "" : "s"}`;
}

function waitLabel(milliseconds) {
  if (milliseconds >= DAY) return plural(Math.floor(milliseconds / DAY), "day");
  if (milliseconds >= HOUR) return plural(Math.floor(milliseconds / HOUR), "hour");
  return "Under an hour";
}

export function queueSummary(queue, now = new Date()) {
  if (!queue.length) return { waiting: 0, oldestWaitLabel: "—" };
  const oldest = Math.min(...queue.map((item) => new Date(item.entered_review_at).getTime()));
  return { waiting: queue.length, oldestWaitLabel: waitLabel(now.getTime() - oldest) };
}

export function outcomeCounts(history) {
  const count = (decision) => history.filter((item) => item.decision === decision).length;
  return {
    approved: count("approved"),
    changesRequested: count("changes_requested"),
    arrangementRejected: count("arrangement_rejected"),
  };
}
