// CR-111: how the organiser's event page words the coordinator and each venue's window.

// QA3-42: "Unassigned" until a coordinator is assigned, then their name.
export function coordinatorLabel(event) {
  return event?.coordinator?.full_name || (event?.coordinator_id || event?.coordinatorId ? "Assigned" : "Unassigned");
}

// Stored UTC, displayed in the event's timezone (REQUIREMENTS §4).
export function venueWindowLabel(startsAt, endsAt, timezone = "Asia/Singapore") {
  if (!startsAt || !endsAt) return "Time not provided";
  const start = new Date(startsAt);
  const end = new Date(endsAt);
  const date = new Intl.DateTimeFormat("en-SG", { day: "numeric", month: "short", year: "numeric", timeZone: timezone }).format(start);
  const time = new Intl.DateTimeFormat("en-SG", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: timezone });
  return `${date}, ${time.format(start)}–${time.format(end)}`;
}
