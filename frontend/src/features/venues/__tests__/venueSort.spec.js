import { describe, expect, it } from "vitest";

import { sortVenueResults, VENUE_SORT_OPTIONS } from "@/features/venues/venueSort";

const result = (name, capacity) => ({ venue: { name, capacity } });
const RESULTS = [result("Hall B", 100), result("auditorium A", 200), result("Boardroom", 100), result("Atrium", 30)];
const names = (sorted) => sorted.map((entry) => entry.venue.name);

describe("sortVenueResults", () => {
  it("sorts by name, ignoring case", () => {
    expect(names(sortVenueResults(RESULTS, "name"))).toEqual(["Atrium", "auditorium A", "Boardroom", "Hall B"]);
  });

  it("sorts largest capacity first, breaking ties by name", () => {
    expect(names(sortVenueResults(RESULTS, "capacity-desc"))).toEqual(["auditorium A", "Boardroom", "Hall B", "Atrium"]);
  });

  it("sorts smallest capacity first, breaking ties by name", () => {
    expect(names(sortVenueResults(RESULTS, "capacity-asc"))).toEqual(["Atrium", "Boardroom", "Hall B", "auditorium A"]);
  });

  it("sorts by name for an unknown key and never changes the list it was given", () => {
    const original = [...RESULTS];

    expect(names(sortVenueResults(RESULTS, "nonsense"))).toEqual(["Atrium", "auditorium A", "Boardroom", "Hall B"]);
    expect(RESULTS).toEqual(original);
  });

  it("returns an empty list for no results", () => {
    expect(sortVenueResults([], "capacity-desc")).toEqual([]);
  });

  it("offers each sort the function understands, name first", () => {
    expect(VENUE_SORT_OPTIONS.map((option) => option.value)).toEqual(["name", "capacity-desc", "capacity-asc"]);
  });
});
