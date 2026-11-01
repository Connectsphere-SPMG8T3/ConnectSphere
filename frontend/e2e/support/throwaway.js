// Throwaway accounts for the sign-up specs, and throwaway events for the venue
// booking spec (SCRUM-19). They share their name patterns with
// backend/scripts/verify_live.py. A run deletes only its own throwaway rows,
// before and after it, plus any an earlier run left more than STALE_AFTER ago,
// so it can't delete the rows of a run going at the same time.
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const PROJECT_REF = "vuiryrzzyfecjqftwicj";
const PREFIX = "live-check+";
const DOMAIN = "@connectsphere.dev";

// In every throwaway name and note this run writes, so its cleanup can find only its own.
// Playwright's global setup (which cleans up) and its workers (which create rows) are
// separate processes: the first to load this module publishes the id in the environment,
// which the processes it starts inherit.
process.env.E2E_RUN_ID ||= `e2e-${new Date().toISOString().replace(/\D/g, "").slice(0, 14)}`;
export const RUN_ID = process.env.E2E_RUN_ID;
// Longer than any run, so a concurrent run's rows are never treated as left over.
export const STALE_AFTER = "6 hours";

// This run's rows (`mine`), or another run's (`anyone`) left over for longer than STALE_AFTER.
function mineOrStale(column, mine, anyone) {
  return `(${column} like '${mine}' or (${column} like '${anyone}' and created_at < now() - interval '${STALE_AFTER}'))`;
}

export const THROWAWAY_PASSWORD = "Cs1234" + "live";

export function throwawayEmail(tag) {
  return `${PREFIX}${RUN_ID}-${tag}${DOMAIN}`;
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
      `delete from auth.users where ${mineOrStale("email", `${PREFIX}${RUN_ID}-%${DOMAIN}`, `${PREFIX}%${DOMAIN}`)}`,
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
// suite's cleanup removes the other's long-left-over rows.
const EVENT_PREFIX = "live-check ";

/** A planning event owned by the seeded organiser and assigned to the seeded coordinator. */
export function createThrowawayEvent(tag, startsAt, endsAt) {
  const [row] = query(
    "insert into public.events (organiser_id, coordinator_id, status, name, starts_at, ends_at, expected_attendance) values " +
      "('a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002', 'planning', " +
      `'${EVENT_PREFIX}${RUN_ID} ${tag}', '${startsAt}', '${endsAt}', 20) returning id, name`,
  );
  return row;
}

/** A confirmed, full event for attendee registration and waitlist browser checks. */
export function createThrowawayRegistrationEvent(tag, startsAt, endsAt) {
  const event = createThrowawayEvent(tag, startsAt, endsAt);
  query(
    `update public.events set status = 'confirmed', registration_enabled = true, registration_capacity = 1, ` +
      `registration_opens_at = now() - interval '1 day', registration_closes_at = '${startsAt}', ` +
      `withdrawal_closes_at = '${startsAt}', waitlist_enabled = true where id = '${event.id}'`,
  );
  return event;
}

/** A notification for `recipientId` about a throwaway event (SCRUM-113). It is deleted with the event
 * when the run ends (notifications cascade). Needs migration 20261021100000. */
export function createThrowawayNotification(event, recipientId, type, message) {
  const [row] = query(
    `select public.add_notification('${recipientId}', '${event.id}', '${type}', '${message}') as id`,
  );
  return row;
}

/** A submitted event waiting in the Lead's unassigned queue (SCRUM-12): no coordinator. */
export function createQueuedThrowawayEvent(tag, startsAt, endsAt) {
  const [row] = query(
    "insert into public.events (organiser_id, coordinator_id, status, name, starts_at, ends_at, expected_attendance, layout_preference, facilities_required, submitted_at) values " +
      "('a0000000-0000-4000-8000-000000000001', null, 'submitted', " +
      `'${EVENT_PREFIX}${RUN_ID} ${tag}', '${startsAt}', '${endsAt}', 64, 'theatre', '{projector}', now()) returning id, name`,
  );
  return row;
}

/** The event's status and coordinator, read straight from the database. */
export function readThrowawayEvent(eventId) {
  const [row] = query(`select status, coordinator_id from public.events where id = '${eventId}'`);
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

/** The organiser's open cancellation request on a throwaway event (story 115). It is
 * deleted with the event when the run ends (requests cascade). */
export function createThrowawayCancellationRequest(event, reason) {
  query(
    "insert into public.event_change_requests (event_id, kind, reason, requested_by) values " +
      `('${event.id}', 'cancellation', '${reason}', 'a0000000-0000-4000-8000-000000000001')`,
  );
}

/** The organiser's open change request on a throwaway event (story 37), raising its attendance
 * from 20. It is deleted with the event when the run ends (requests cascade). */
export function createThrowawayChangeRequest(event, after, reason) {
  query(
    "insert into public.event_change_requests (event_id, kind, reason, requested_by, changes, significant) values " +
      `('${event.id}', 'change', '${reason}', 'a0000000-0000-4000-8000-000000000001', ` +
      `'{"event": [{"field": "expected_attendance", "before": 20, "after": ${after}}], "spaces": []}', true)`,
  );
}

/** A recorded edit by the organiser on a throwaway event (story 62). It is deleted with
 * the event when the run ends (history cascades). */
export function createThrowawayEdit(event, field, oldValue, newValue) {
  query(
    "insert into public.event_edit_history (event_id, actor_id, field, old_value, new_value) values " +
      `('${event.id}', 'a0000000-0000-4000-8000-000000000001', '${field}', ` +
      `'${JSON.stringify(oldValue)}', '${JSON.stringify(newValue)}')`,
  );
}

/** A technical history entry by tech support on a throwaway event (story 62). It is
 * deleted with the event when the run ends (history cascades). */
export function createThrowawayTechnicalEntry(event, action) {
  query(
    "insert into public.event_technical_history (event_id, action, actor_id) values " +
      `('${event.id}', '${action}', 'a0000000-0000-4000-8000-000000000004')`,
  );
}

/** Free-text accessibility needs on a throwaway event (SCRUM-18). */
export function setThrowawayEventAccessibilityNeeds(event, needs) {
  query(`update public.events set accessibility_needs = '${needs}' where id = '${event.id}'`);
}

// Same note as backend/scripts/verify_live.py's THROWAWAY_BLOCK_NOTE, followed by the run.
const BLOCK_NOTE = "live-check";

/**
 * A block on a venue (CR-95). Inserting it flags the held and approved bookings it overlaps,
 * so create the booking first.
 */
export function createThrowawayBlock(venueId, startsAt, endsAt, reason = "maintenance") {
  const [row] = query(
    "insert into public.venue_blocks (venue_id, blocked_period, reason, notes) values " +
      `('${venueId}', tstzrange('${startsAt}', '${endsAt}', '[)'), '${reason}', '${BLOCK_NOTE} ${RUN_ID}') returning id`,
  );
  return row;
}

/** Removes this run's throwaway blocks, which is how a venue becomes free again for a restore (CR-95 AC9). */
export function deleteThrowawayBlocks() {
  query(`delete from public.venue_blocks where ${mineOrStale("notes", `${BLOCK_NOTE} ${RUN_ID}`, `${BLOCK_NOTE}%`)}`);
}

/** The booking's flag and status, read straight from the database. */
export function readThrowawayBooking(bookingId) {
  const [row] = query(`select status, flag from public.venue_bookings where id = '${bookingId}'`);
  return row;
}

/** A space on a throwaway event (CR-97); it goes when the event is deleted (cascade). */
export function createThrowawaySpace(event, label, expectedPax, layout = null) {
  const [row] = query(
    "insert into public.event_space_requests (event_id, label, expected_pax, layout_preference) values " +
      `('${event.id}', '${label}', ${expectedPax}, ${layout ? `'${layout}'` : "null"}) returning id`,
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
  const events = mineOrStale("name", `${EVENT_PREFIX}${RUN_ID} %`, `${EVENT_PREFIX}%`);
  query(`delete from public.venue_bookings where event_id in (select id from public.events where ${events})`);
  query(`delete from public.events where ${events}`);
  // SCRUM-24's throwaway equipment, after its events' lines (that foreign key
  // restricts); its reservations cascade.
  query(`delete from public.equipment where ${mineOrStale("name", `${EVENT_PREFIX}equipment ${RUN_ID} %`, `${EVENT_PREFIX}%`)}`);
}

/** A throwaway catalogue item (SCRUM-24), so seeded stock is never reserved.
 * Deleted by deleteThrowawayEvents. */
export function createThrowawayEquipment(tag, quantity) {
  const [row] = query(
    "insert into public.equipment (name, equipment_type, total_quantity, status) values " +
      `('${EVENT_PREFIX}equipment ${RUN_ID} ${tag}', 'live-check', ${quantity}, 'active') returning id, name`,
  );
  return row;
}

/** A pending request line on a throwaway event, requested by the seeded coordinator. */
export function createThrowawayLine(event, equipment, quantity) {
  const [row] = query(
    "insert into public.equipment_requests (event_id, equipment_id, submission_id, quantity, requested_by) values " +
      `('${event.id}', '${equipment.id}', gen_random_uuid(), ${quantity}, 'a0000000-0000-4000-8000-000000000002') returning id`,
  );
  return row;
}

/** A maintenance outage on throwaway equipment (D61). Deleted with the equipment,
 * which cascades to its unavailability rows. */
export function createThrowawayOutage(equipment, startAt, endAt, reason) {
  const [row] = query(
    "insert into public.equipment_unavailability (equipment_id, quantity, start_at, end_at, reason) values " +
      `('${equipment.id}', 1, '${startAt}', '${endAt}', '${reason}') returning id`,
  );
  return row;
}

/** Sets a throwaway line's status directly, as if tech support had acted on it (D70). */
export function setThrowawayLineStatus(line, status) {
  query(`update public.equipment_requests set status = '${status}' where id = '${line.id}'`);
}

// Same "live-check venue " prefix as backend/scripts/verify_live.py (SCRUM-64).
const VENUE_PREFIX = "live-check venue ";

/** An active venue for the deactivation spec; seeded venues are never changed. */
export function createThrowawayVenue(tag) {
  const [row] = query(
    "insert into public.venues (name, location, capacity, opens_at, closes_at, is_active) values " +
      `('${VENUE_PREFIX}${RUN_ID} ${tag}', 'Live check', 50, '08:00', '22:00', true) returning id, name`,
  );
  query(`insert into public.venue_layouts (venue_id, layout) values ('${row.id}', 'theatre')`);
  return row;
}

/** Deletes the throwaway venues, their bookings first (that foreign key restricts). */
export function deleteThrowawayVenues() {
  const venues = mineOrStale("name", `${VENUE_PREFIX}${RUN_ID} %`, `${VENUE_PREFIX}%`);
  query(`delete from public.venue_bookings where venue_id in (select id from public.venues where ${venues})`);
  query(`delete from public.venues where ${venues}`);
}

/** CR-100's schema is a deployment prerequisite for its live browser cases. */
export function venueBufferMigrationPresent() {
  return query("select count(*) = 4 as present from information_schema.columns where table_schema = 'public' " +
    "and table_name = 'venues' and column_name in ('setup_minutes', 'turnaround_minutes', 'emergency_access', 'restrictions')")[0].present;
}

/** D52: a rejected arrangement for TC-SDEC-033; never flags shared events. */
export function setThrowawayBookingSafetyRejected(bookingId) {
  query(`update public.venue_bookings set flag = 'safety_rejected', flag_reason = 'live check exits', flagged_at = now() ` +
    `where id = '${bookingId}' and event_id in (select id from public.events where name like '${EVENT_PREFIX}%')`);
}

// SCRUM-45: the lines the equipment spec adds to a seeded planning event carry this note,
// so only those lines, and only this run's, are deleted.
const LIVE_CHECK_LINE_NOTE = "live-check SCRUM-45";

export function liveCheckLineNote(text) {
  return `${LIVE_CHECK_LINE_NOTE} ${RUN_ID}: ${text}`;
}

export function deleteLiveCheckLines(eventId) {
  query(`delete from public.equipment_requests where event_id = '${eventId}' and ` +
    mineOrStale("technical_requirements", `${LIVE_CHECK_LINE_NOTE} ${RUN_ID}%`, `${LIVE_CHECK_LINE_NOTE}%`));
}
