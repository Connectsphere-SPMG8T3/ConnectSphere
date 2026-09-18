/**
 * iCalendar (RFC 5545) export for the venue-staff calendar (SCRUM-70).
 *
 * Pure string building, no DOM — the component handles the download. An .ics
 * file is the one calendar format every client reads, so a staff member can
 * carry their blocks and pending decisions into whatever they already use
 * rather than keeping this dashboard open.
 *
 * Everything is written in UTC (the `Z` form). Periods are stored in UTC and
 * only displayed in Singapore time (REQUIREMENTS §4), so emitting UTC avoids
 * shipping a VTIMEZONE block and cannot be misread by a client in another
 * zone.
 */

import { BOOKING_STATUS_LABELS, blockReasonLabel } from "@/features/venues/dashboard";

const CRLF = "\r\n";

/** `2026-10-10T05:00:00Z` -> `20261010T050000Z`. */
export function toIcsStamp(value) {
  const instant = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(instant.getTime())) return null;
  return `${instant.toISOString().replace(/[-:]/g, "").split(".")[0]}Z`;
}

/**
 * Escape a value for a text property: backslash first, or it would double-
 * escape the sequences the later replacements introduce (RFC 5545 §3.3.11).
 */
export function escapeIcsText(value) {
  return String(value ?? "")
    .replace(/\\/g, "\\\\")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,")
    .replace(/\r?\n/g, "\\n");
}

/**
 * Fold a content line to 75 octets, continuing with a leading space.
 *
 * The limit is octets, not characters, so a venue name with a multi-byte
 * character must not be split mid-sequence — hence measuring each character's
 * encoded length rather than slicing the string by index.
 */
export function foldIcsLine(line) {
  const encoder = new TextEncoder();
  const parts = [];
  let current = "";
  let bytes = 0;
  // Continuation lines carry a leading space, so they hold one octet less.
  let limit = 75;

  for (const char of line) {
    const size = encoder.encode(char).length;
    if (bytes + size > limit) {
      parts.push(current);
      current = "";
      bytes = 0;
      limit = 74;
    }
    current += char;
    bytes += size;
  }
  parts.push(current);

  return parts.join(`${CRLF} `);
}

function summaryFor(item) {
  if (item.kind === "block") {
    return `Blocked: ${item.venueName} (${blockReasonLabel(item.detail).toLowerCase()})`;
  }
  const label = BOOKING_STATUS_LABELS[item.kind] ?? item.kind;
  return `${label}: ${item.venueName}`;
}

function descriptionFor(item) {
  if (item.kind === "block") {
    return item.notes ? `${blockReasonLabel(item.detail)}. ${item.notes}` : blockReasonLabel(item.detail);
  }
  const event = item.detail ?? (item.eventId ? `Event ${String(item.eventId).slice(0, 8).toUpperCase()}` : null);
  const label = BOOKING_STATUS_LABELS[item.kind] ?? item.kind;
  return event ? `${label} awaiting your decision. ${event}` : `${label} awaiting your decision.`;
}

/**
 * Build a VCALENDAR from the dashboard's calendar items.
 *
 * `now` is injectable so DTSTAMP is deterministic in tests. Items whose period
 * cannot be read are skipped rather than emitted malformed — one bad row
 * should not make the whole file unreadable.
 */
export function toIcsCalendar(items = [], { now = new Date(), name = "ConnectSphere venues" } = {}) {
  const stamp = toIcsStamp(now);

  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//ConnectSphere//Venue Staff Calendar//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    `X-WR-CALNAME:${escapeIcsText(name)}`,
  ];

  for (const item of items) {
    const start = toIcsStamp(item.startsAt);
    const end = toIcsStamp(item.endsAt);
    if (!start || !end) continue;

    lines.push(
      "BEGIN:VEVENT",
      // Stable across exports, so re-importing updates the entry rather than
      // duplicating it.
      `UID:${escapeIcsText(`${item.kind}-${item.id}`)}@connectsphere`,
      `DTSTAMP:${stamp}`,
      `DTSTART:${start}`,
      // DTEND is exclusive in iCalendar, which is the same half-open reading
      // the database uses (§6.14) — so the stored end goes through unchanged.
      `DTEND:${end}`,
      `SUMMARY:${escapeIcsText(summaryFor(item))}`,
      `DESCRIPTION:${escapeIcsText(descriptionFor(item))}`,
      `LOCATION:${escapeIcsText(item.venueName)}`,
      // A block is settled; a pending request is not yet confirmed.
      `STATUS:${item.kind === "block" ? "CONFIRMED" : "TENTATIVE"}`,
      "END:VEVENT",
    );
  }

  lines.push("END:VCALENDAR");

  return lines.map(foldIcsLine).join(CRLF) + CRLF;
}

/** A filename that sorts and reads sensibly in a downloads folder. */
export function icsFilename(now = new Date()) {
  return `connectsphere-venues-${now.toISOString().slice(0, 10)}.ics`;
}
