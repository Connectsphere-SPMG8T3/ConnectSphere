import { describe, expect, it } from "vitest";

import { escapeIcsText, foldIcsLine, icsFilename, toIcsCalendar, toIcsStamp } from "@/features/venues/ics";

const NOW = new Date("2026-09-19T04:00:00Z");

const blockItem = {
  kind: "block",
  id: "c-3",
  venueId: "b-5",
  venueName: "Rooftop Terrace",
  startsAt: "2026-10-19T16:00:00Z",
  endsAt: "2026-10-21T16:00:00Z",
  detail: "safety",
  notes: "Railing inspection.",
};

const holdItem = {
  kind: "held",
  id: "d-2",
  venueId: "b-3",
  venueName: "Seminar Room 1",
  startsAt: "2026-10-10T05:00:00Z",
  endsAt: "2026-10-10T08:00:00Z",
  detail: null,
  eventId: "e0000000-0000-4000-8000-000000000102",
};

const lines = (ics) => ics.split("\r\n");

describe("toIcsStamp", () => {
  it("writes a UTC basic-format stamp", () => {
    expect(toIcsStamp("2026-10-10T05:00:00Z")).toBe("20261010T050000Z");
  });

  it("normalises an offset to UTC", () => {
    expect(toIcsStamp("2026-10-10T13:00:00+08:00")).toBe("20261010T050000Z");
  });

  it("drops milliseconds", () => {
    expect(toIcsStamp("2026-10-10T05:00:00.123Z")).toBe("20261010T050000Z");
  });

  it("returns null for something unreadable", () => {
    expect(toIcsStamp("not a date")).toBeNull();
  });
});

describe("escapeIcsText", () => {
  it("escapes the separators that would otherwise end the property", () => {
    expect(escapeIcsText("Hall A; Level 3, West")).toBe("Hall A\\; Level 3\\, West");
  });

  it("escapes a backslash without double-escaping what it then introduces", () => {
    expect(escapeIcsText("a\\b;c")).toBe("a\\\\b\\;c");
  });

  it("turns a newline into its literal escape", () => {
    expect(escapeIcsText("line one\nline two")).toBe("line one\\nline two");
  });

  it("copes with null", () => {
    expect(escapeIcsText(null)).toBe("");
  });
});

describe("foldIcsLine", () => {
  it("leaves a short line alone", () => {
    expect(foldIcsLine("SUMMARY:Short")).toBe("SUMMARY:Short");
  });

  it("folds a long line with a leading space on the continuation", () => {
    const folded = foldIcsLine(`SUMMARY:${"a".repeat(200)}`);
    const parts = folded.split("\r\n");
    expect(parts.length).toBeGreaterThan(1);
    expect(parts[0]).toHaveLength(75);
    expect(parts.slice(1).every((part) => part.startsWith(" "))).toBe(true);
    // Folding must be reversible: dropping each continuation's leading space
    // restores the original, which is exactly how a client unfolds it.
    const unfolded = parts[0] + parts.slice(1).map((part) => part.slice(1)).join("");
    expect(unfolded).toBe(`SUMMARY:${"a".repeat(200)}`);
  });

  it("counts octets, not characters, and never splits a multi-byte character", () => {
    const folded = foldIcsLine(`SUMMARY:${"é".repeat(80)}`);
    for (const part of folded.split("\r\n")) {
      expect(new TextEncoder().encode(part).length).toBeLessThanOrEqual(75);
      expect(part).not.toContain("�");
    }
  });
});

describe("toIcsCalendar", () => {
  it("wraps the events in a well-formed VCALENDAR", () => {
    const ics = toIcsCalendar([blockItem], { now: NOW });
    const rows = lines(ics);

    expect(rows[0]).toBe("BEGIN:VCALENDAR");
    expect(rows).toContain("VERSION:2.0");
    expect(rows).toContain("BEGIN:VEVENT");
    expect(rows).toContain("END:VEVENT");
    expect(rows.filter(Boolean).at(-1)).toBe("END:VCALENDAR");
  });

  it("ends every line with CRLF, as the spec requires", () => {
    const ics = toIcsCalendar([blockItem, holdItem], { now: NOW });
    expect(ics.endsWith("\r\n")).toBe(true);
    expect(ics.replace(/\r\n/g, "")).not.toContain("\n");
  });

  it("carries a block through with its period unchanged", () => {
    const rows = lines(toIcsCalendar([blockItem], { now: NOW }));

    expect(rows).toContain("DTSTART:20261019T160000Z");
    // DTEND is exclusive in iCalendar, matching the half-open period we store,
    // so the stored end goes through as-is.
    expect(rows).toContain("DTEND:20261021T160000Z");
    expect(rows).toContain("DTSTAMP:20260919T040000Z");
    expect(rows).toContain("SUMMARY:Blocked: Rooftop Terrace (safety)");
    expect(rows).toContain("LOCATION:Rooftop Terrace");
    expect(rows).toContain("STATUS:CONFIRMED");
  });

  it("marks a pending request tentative, since nothing is decided yet", () => {
    const rows = lines(toIcsCalendar([holdItem], { now: NOW }));

    expect(rows).toContain("SUMMARY:Pending hold: Seminar Room 1");
    expect(rows).toContain("STATUS:TENTATIVE");
    expect(rows.some((row) => row.startsWith("DESCRIPTION:") && row.includes("Event E0000000"))).toBe(true);
  });

  it("gives each item a stable uid, so re-importing updates rather than duplicates", () => {
    const first = lines(toIcsCalendar([blockItem], { now: NOW })).find((row) => row.startsWith("UID:"));
    const later = lines(toIcsCalendar([blockItem], { now: new Date("2026-10-01T00:00:00Z") })).find((row) =>
      row.startsWith("UID:"),
    );
    expect(first).toBe(later);
    expect(first).toBe("UID:block-c-3@connectsphere");
  });

  it("writes one event per item", () => {
    const rows = lines(toIcsCalendar([blockItem, holdItem], { now: NOW }));
    expect(rows.filter((row) => row === "BEGIN:VEVENT")).toHaveLength(2);
  });

  it("skips an item whose period cannot be read rather than emitting it malformed", () => {
    const rows = lines(toIcsCalendar([blockItem, { ...holdItem, startsAt: "nonsense" }], { now: NOW }));
    expect(rows.filter((row) => row === "BEGIN:VEVENT")).toHaveLength(1);
  });

  it("produces a valid empty calendar when there is nothing to export", () => {
    const rows = lines(toIcsCalendar([], { now: NOW }));
    expect(rows).toContain("BEGIN:VCALENDAR");
    expect(rows).not.toContain("BEGIN:VEVENT");
  });

  it("escapes a venue name that would otherwise break the property", () => {
    const rows = lines(toIcsCalendar([{ ...blockItem, venueName: "Hall A; Level 3, West" }], { now: NOW }));
    expect(rows).toContain("LOCATION:Hall A\\; Level 3\\, West");
  });
});

describe("icsFilename", () => {
  it("dates the file so downloads sort sensibly", () => {
    expect(icsFilename(NOW)).toBe("connectsphere-venues-2026-09-19.ics");
  });
});
