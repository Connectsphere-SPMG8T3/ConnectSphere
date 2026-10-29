import { formatEventDateRange } from "@/features/registrations/eventDateRange";

export function splitRegistrationsByEndTime(registrations, now = Date.now()) {
  return registrations.reduce(
    (groups, registration) => {
      const endsAt = Date.parse(registration.event.ends_at);
      if (!Number.isFinite(endsAt)) {
        throw new TypeError(`Registration ${registration.id} has an invalid event end time.`);
      }
      groups[endsAt <= now ? "past" : "upcoming"].push(registration);
      return groups;
    },
    { upcoming: [], past: [] },
  );
}

export function summarizeAttendeeDashboard(registrations, publicEvents, now = Date.now()) {
  const currentRegistrations = registrations.filter(({ status }) =>
    ["registered", "waitlisted"].includes(status),
  );
  const groups = splitRegistrationsByEndTime(currentRegistrations, now);
  const uniqueEventCount = (items) => {
    const eventIds = items.map(({ id, event }) => {
      if (!event?.id) throw new TypeError(`Registration ${id} has no event ID.`);
      return event.id;
    });
    return new Set(eventIds).size;
  };

  return {
    upcomingRegistrations: uniqueEventCount(groups.upcoming),
    openEvents: publicEvents.filter(({ availability }) => availability === "open").length,
    pastRegistrations: uniqueEventCount(groups.past.filter(({ status }) => status === "registered")),
  };
}

export function formatRegistrationPeriod(event) {
  return formatEventDateRange(event, { compact: true });
}

export function registrationStatusLabel(status) {
  const labels = {
    registered: "Registered",
    waitlisted: "Waitlisted",
  };
  return labels[status] ?? status;
}

export function canWithdrawRegistration(registration, now = Date.now()) {
  if (registration?.status !== "registered" || !registration.event) return false;
  const cutoff = registration.event.withdrawal_closes_at ?? registration.event.starts_at;
  const cutoffTime = Date.parse(cutoff);
  return Number.isFinite(cutoffTime) && now < cutoffTime;
}

function registrationStartTime(registration) {
  const startsAt = Date.parse(registration.event.starts_at);
  if (!Number.isFinite(startsAt)) {
    throw new TypeError(`Registration ${registration.id} has an invalid event start time.`);
  }
  return startsAt;
}

export function filterAndSortRegistrations(
  registrations,
  { search = "", statuses = [], period = "all", sortBy = "date", direction = "asc", now = Date.now() } = {},
) {
  if (!Array.isArray(statuses) || statuses.some((status) => !["registered", "waitlisted"].includes(status))) {
    throw new TypeError("Registration filters contain an unsupported status.");
  }
  if (!["all", "upcoming", "past"].includes(period)) {
    throw new TypeError(`Unsupported registration period: ${period}.`);
  }
  if (!["date", "name"].includes(sortBy)) {
    throw new TypeError(`Unsupported registration sort field: ${sortBy}.`);
  }
  if (!["asc", "desc"].includes(direction)) {
    throw new TypeError(`Unsupported registration sort direction: ${direction}.`);
  }

  const query = search.trim().toLocaleLowerCase("en-SG");
  const sign = direction === "asc" ? 1 : -1;

  const filteredRegistrations = registrations
    .filter(({ status, event }) =>
      (!statuses.length || statuses.includes(status)) &&
      event.name.toLocaleLowerCase("en-SG").includes(query),
    )
    .filter((registration) => {
      if (period === "all") return true;
      const endsAt = Date.parse(registration.event.ends_at);
      if (!Number.isFinite(endsAt)) {
        throw new TypeError(`Registration ${registration.id} has an invalid event end time.`);
      }
      return period === "past" ? endsAt <= now : endsAt > now;
    })
    .slice();
  if (sortBy === "date") filteredRegistrations.forEach(registrationStartTime);

  return filteredRegistrations.sort((left, right) => {
    if (sortBy === "name") {
      return sign * left.event.name.localeCompare(right.event.name, "en-SG");
    }
    return sign * (registrationStartTime(left) - registrationStartTime(right));
  });
}
