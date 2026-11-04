// How the venue search results can be ordered. Names compare as plain text
// (case-insensitive), so "auditorium a" sits with "Auditorium A".
export const VENUE_SORT_OPTIONS = [
  { value: "name", label: "Name (A to Z)" },
  { value: "capacity-desc", label: "Capacity (largest first)" },
  { value: "capacity-asc", label: "Capacity (smallest first)" },
];

const byName = (a, b) => a.venue.name.localeCompare(b.venue.name, undefined, { sensitivity: "base" });

const COMPARATORS = {
  name: byName,
  // A tie on capacity falls back to the name, so the order never depends on the API's.
  "capacity-desc": (a, b) => b.venue.capacity - a.venue.capacity || byName(a, b),
  "capacity-asc": (a, b) => a.venue.capacity - b.venue.capacity || byName(a, b),
};

/** A sorted copy of the search results; an unknown key sorts by name. */
export function sortVenueResults(results, key) {
  return [...results].sort(COMPARATORS[key] ?? COMPARATORS.name);
}
