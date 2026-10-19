// Throwaway accounts for the sign-up specs, and throwaway events for the venue
// booking spec (SCRUM-19). They share one email pattern with
// backend/scripts/verify_live.py, and every account matching it is deleted,
// along with everything it owns, before and after a run.
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const PROJECT_REF = "vuiryrzzyfecjqftwicj";
const PREFIX = "live-check+";
const DOMAIN = "@connectsphere.dev";

const runId = new Date().toISOString().replace(/\D/g, "").slice(0, 14);

export const THROWAWAY_PASSWORD = "Cs1234" + "live";

export function throwawayEmail(tag) {
  return `${PREFIX}e2e-${runId}-${tag}${DOMAIN}`;
}

export function deleteThrowawayAccounts() {
  execFileSync(
    "supabase",
    [
      "db",
      "query",
      "--linked",
      "--project-ref",
      PROJECT_REF,
      `delete from auth.users where email like '${PREFIX}%${DOMAIN}'`,
    ],
    { cwd: REPO_ROOT, stdio: "pipe" },
  );
}

function query(sql) {
  const out = execFileSync(
    "supabase",
    ["db", "query", "--linked", "--project-ref", PROJECT_REF, "-o", "json", sql],
    { cwd: REPO_ROOT, stdio: "pipe", encoding: "utf8" },
  );
  return parseRows(out);
}

/**
 * The rows in the CLI's JSON. It prints `{"rows": [...]}` under an agent but a bare list in
 * a plain terminal (`[]` when nothing matched), with notices around either.
 */
export function parseRows(out) {
  const starts = [out.indexOf("{"), out.indexOf("[")].filter((i) => i !== -1);
  if (!starts.length) throw new Error(`database query printed no JSON: ${JSON.stringify(out.trim().slice(0, 200))}`);
  const text = out.slice(Math.min(...starts));
  const closer = text[0] === "[" ? "]" : "}";
  const payload = JSON.parse(text.slice(0, text.lastIndexOf(closer) + 1));
  return Array.isArray(payload) ? payload : (payload.rows ?? []);
}

// Same "live-check " name prefix as backend/scripts/verify_live.py, so either
// run's cleanup removes both runs' leftovers.
const EVENT_PREFIX = "live-check ";

/** A planning event owned by the seeded organiser and assigned to the seeded coordinator. */
export function createThrowawayEvent(tag, startsAt, endsAt) {
  const [row] = query(
    "insert into public.events (organiser_id, coordinator_id, status, name, starts_at, ends_at, expected_attendance) values " +
      "('a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002', 'planning', " +
      `'${EVENT_PREFIX}e2e-${runId} ${tag}', '${startsAt}', '${endsAt}', 20) returning id, name`,
  );
  return row;
}

/** A booking on a throwaway event with a chosen status and expiry (CR-99), for
 * states a request alone can't reach. Deleted with the event's bookings. */
export function createThrowawayHold(event, venueId, startsAt, endsAt, status, expiresAt, spaceId = null) {
  const space = spaceId ? `'${spaceId}'` : "null"; // null: the trigger links the event's first space
  const [row] = query(
    "insert into public.venue_bookings (event_id, event_space_request_id, venue_id, occupied_period, status, expires_at) values " +
      `('${event.id}', ${space}, '${venueId}', tstzrange('${startsAt}', '${endsAt}', '[)'), '${status}', '${expiresAt}') returning id`,
  );
  return row;
}

/** A booking on a throwaway event with a chosen status and no expiry, for an approved one (CR-95). */
export function createThrowawayBooking(event, venueId, startsAt, endsAt, status) {
  const [row] = query(
    "insert into public.venue_bookings (event_id, venue_id, occupied_period, status) values " +
      `('${event.id}', '${venueId}', tstzrange('${startsAt}', '${endsAt}', '[)'), '${status}') returning id`,
  );
  return row;
}

/** Moves a throwaway event to a status a request alone can't reach (CR-95: Confirmed). */
export function setThrowawayEventStatus(event, status) {
  query(`update public.events set status = '${status}' where id = '${event.id}'`);
}

// Same note as backend/scripts/verify_live.py's THROWAWAY_BLOCK_NOTE, so either
// run's cleanup removes both runs' leftovers.
const BLOCK_NOTE = "live-check";

/**
 * A block on a venue (CR-95). Inserting it flags the held and approved bookings it overlaps,
 * so create the booking first.
 */
export function createThrowawayBlock(venueId, startsAt, endsAt, reason = "maintenance") {
  const [row] = query(
    "insert into public.venue_blocks (venue_id, blocked_period, reason, notes) values " +
      `('${venueId}', tstzrange('${startsAt}', '${endsAt}', '[)'), '${reason}', '${BLOCK_NOTE}') returning id`,
  );
  return row;
}

/** Removes the throwaway blocks, which is how a venue becomes free again for a restore (CR-95 AC9). */
export function deleteThrowawayBlocks() {
  query(`delete from public.venue_blocks where notes = '${BLOCK_NOTE}'`);
}

/** The booking's flag and status, read straight from the database. */
export function readThrowawayBooking(bookingId) {
  const [row] = query(`select status, flag from public.venue_bookings where id = '${bookingId}'`);
  return row;
}

/** A space on a throwaway event (CR-97); it goes when the event is deleted (cascade). */
export function createThrowawaySpace(event, label, expectedPax) {
  const [row] = query(
    "insert into public.event_space_requests (event_id, label, expected_pax) values " +
      `('${event.id}', '${label}', ${expectedPax}) returning id`,
  );
  return row;
}

/**
 * A throwaway planning event with a held booking request on `venueId` for its own
 * period, with a coordinator's note and the event's requirements filled in
 * (SCRUM-38), so the reject spec doesn't depend on the request flow. For a hold
 * in a chosen status or expiry, use createThrowawayHold (CR-99).
 * The booking and its history go with deleteThrowawayEvents.
 */
export function createThrowawayRequest(tag, startsAt, endsAt, venueId) {
  const event = createThrowawayEvent(tag, startsAt, endsAt);
  query(`update public.events set layout_preference = 'classroom', accessibility_needs = 'Step-free access' where id = '${event.id}'`);
  const [booking] = query(
    "insert into public.venue_bookings (event_id, venue_id, occupied_period, status, request_note, requested_by) values " +
      `('${event.id}', '${venueId}', tstzrange('${startsAt}', '${endsAt}', '[)'), 'held', 'Early access please', ` +
      "'a0000000-0000-4000-8000-000000000002') returning id",
  );
  return { event, bookingId: booking.id };
}

/** Gives a throwaway booking its own setup and turnaround (SCRUM-21), as CR-100
 * will copy them in from the venue; its occupied window widens to match. */
export function setThrowawayBookingBuffers(bookingId, setupMinutes, turnaroundMinutes) {
  query(
    `update public.venue_bookings set setup_minutes = ${setupMinutes}, turnaround_minutes = ${turnaroundMinutes} ` +
      `where id = '${bookingId}'`,
  );
}

/** Deletes the throwaway events and their bookings (that foreign key restricts). */
export function deleteThrowawayEvents() {
  query(`delete from public.venue_bookings where event_id in (select id from public.events where name like '${EVENT_PREFIX}%')`);
  query(`delete from public.events where name like '${EVENT_PREFIX}%'`);
}

// Same "live-check venue " prefix as backend/scripts/verify_live.py (SCRUM-64).
const VENUE_PREFIX = "live-check venue ";

/** An active venue for the deactivation spec; seeded venues are never changed. */
export function createThrowawayVenue(tag) {
  const [row] = query(
    "insert into public.venues (name, location, capacity, opens_at, closes_at, is_active) values " +
      `('${VENUE_PREFIX}e2e-${runId} ${tag}', 'Live check', 50, '08:00', '22:00', true) returning id, name`,
  );
  query(`insert into public.venue_layouts (venue_id, layout) values ('${row.id}', 'theatre')`);
  return row;
}

/** Deletes the throwaway venues, their bookings first (that foreign key restricts). */
export function deleteThrowawayVenues() {
  query(`delete from public.venue_bookings where venue_id in (select id from public.venues where name like '${VENUE_PREFIX}%')`);
  query(`delete from public.venues where name like '${VENUE_PREFIX}%'`);
}

/** CR-100's schema is a deployment prerequisite for its live browser cases. */
export function venueBufferMigrationPresent() {
  return query("select count(*) = 4 as present from information_schema.columns where table_schema = 'public' " +
    "and table_name = 'venues' and column_name in ('setup_minutes', 'turnaround_minutes', 'emergency_access', 'restrictions')")[0].present;
}
