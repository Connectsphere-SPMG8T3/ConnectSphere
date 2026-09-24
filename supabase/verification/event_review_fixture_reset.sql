-- =============================================================================
-- ConnectSphere - Event review fixture reset (SCRUM-34, SCRUM-52)
--
-- What this is for: manual TC-REV-* runs (docs/test-cases/events.md, "Event review — approve and reject") and the
-- verification in supabase/verification/event_review_checks.sql both assume
-- the two SCRUM-34/52 fixture events start from a known status. Real
-- approve/reject calls (through transition_event) move them away from that
-- status, so Task 9's real-system verification reset them back afterwards
-- with raw `update`s on `events`/`venue_bookings`. A raw update doesn't call
-- transition_event, so it left behind the *side effects* of the real
-- transitions it was undoing: event_status_history rows (e.g. a
-- "planning -> rejected" entry on an event that this reset put back in
-- "planning") and notifications rows for the organiser. `supabase/seed.sql`
-- cannot repair this — its inserts use `on conflict do nothing`, so they
-- never touch a row that already exists.
--
-- This script repairs that drift. It touches ONLY:
--   - event e0000000-0000-4000-8000-000000000201 (reset to under_review)
--   - event e0000000-0000-4000-8000-000000000202 (reset to planning)
--   - venue booking d0000000-0000-4000-8000-000000000201 (reset to held)
--   - event_status_history rows (other than creation and submission) and
--     notifications rows whose event_id is one of the two fixture events above
--
-- Idempotent: safe to run with nothing to clean up (the deletes and updates
-- are no-ops), and safe to run more than once in a row.
--
-- Run this as an OPERATOR ONLY — the Supabase MCP `execute_sql`, or
-- `psql "$DATABASE_URL" -f supabase/verification/event_review_fixture_reset.sql`.
-- Never call this from application code: app code only ever writes these
-- tables through `public.transition_event` (migration
-- `20260923120000_event_review_history_and_notifications.sql`), and this
-- script deliberately bypasses that to undo drift the RPC didn't cause.
-- =============================================================================

begin;

delete from public.notifications
 where event_id in (
     'e0000000-0000-4000-8000-000000000201',
     'e0000000-0000-4000-8000-000000000202'
 );

-- Keep each fixture's creation and submission rows (the events_record_created
-- trigger and the backfill in 20260924120000); only review decisions are drift.
delete from public.event_status_history
 where event_id in (
     'e0000000-0000-4000-8000-000000000201',
     'e0000000-0000-4000-8000-000000000202'
 )
   and from_status is not null
   and from_status <> 'draft';

update public.events
   set status = 'under_review'
 where id = 'e0000000-0000-4000-8000-000000000201';

update public.events
   set status = 'planning'
 where id = 'e0000000-0000-4000-8000-000000000202';

update public.venue_bookings
   set status = 'held'
 where id = 'd0000000-0000-4000-8000-000000000201';

-- Resulting statuses and counts, so the operator can confirm the reset
-- worked before relying on it for the next manual run.
select 'event ...0201 status' as check, status::text as value
  from public.events where id = 'e0000000-0000-4000-8000-000000000201'
union all
select 'event ...0202 status', status::text
  from public.events where id = 'e0000000-0000-4000-8000-000000000202'
union all
select 'booking ...0201 status', status::text
  from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000000201'
union all
-- How many creation/submission rows remain depends on how the database was
-- built (the live backfill gave each fixture two; seeding after the migrations
-- gives one), so only the review-decision rows have a fixed expectation.
select 'event_status_history review-decision rows left for the fixtures (expect 0)', count(*)::text
  from public.event_status_history
 where event_id in ('e0000000-0000-4000-8000-000000000201', 'e0000000-0000-4000-8000-000000000202')
   and from_status is not null
   and from_status <> 'draft'
union all
select 'notifications rows left for the fixtures', count(*)::text
  from public.notifications
 where event_id in ('e0000000-0000-4000-8000-000000000201', 'e0000000-0000-4000-8000-000000000202');

commit;
