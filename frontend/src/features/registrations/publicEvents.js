import { formatEventDateRange } from "@/features/registrations/eventDateRange";

export function formatPublicEventDate(event) {
  return formatEventDateRange(event, { compact: true });
}

export function publicEventAvailabilityLabel(availability) {
  return {
    open: "Registration open",
    not_open: "Registration not open",
    closed: "Registration closed",
    full: "Full",
  }[availability] ?? "Registration unavailable";
}

function eventStartTime(event) {
  if (!event.starts_at) return null;
  const start = Date.parse(event.starts_at);
  if (!Number.isFinite(start)) throw new TypeError(`Public event ${event.id} has an invalid start time.`);
  return start;
}

export function filterAndSortPublicEvents(events, { search = "", sortBy = "date", direction = "asc" } = {}) {
  if (!["date", "name"].includes(sortBy)) throw new TypeError(`Unsupported public event sort field: ${sortBy}.`);
  if (!["asc", "desc"].includes(direction)) throw new TypeError(`Unsupported public event sort direction: ${direction}.`);

  const query = search.trim().toLocaleLowerCase("en-SG");
  const sign = direction === "asc" ? 1 : -1;
  return events
    .filter((event) => event.name.toLocaleLowerCase("en-SG").includes(query))
    .slice()
    .sort((left, right) => {
      if (sortBy === "name") return sign * left.name.localeCompare(right.name, "en-SG");
      const leftStart = eventStartTime(left);
      const rightStart = eventStartTime(right);
      if (leftStart === null) return rightStart === null ? 0 : 1;
      if (rightStart === null) return -1;
      return sign * (leftStart - rightStart);
    });
}
