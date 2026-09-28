-- SCRUM-34 / SCRUM-52: status history, notifications and transition_event.
-- Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`. Every row
-- should read `ok = true`. This script only checks that the objects and grants
-- exist — it makes no calls to transition_event, so it never touches fixture
-- data. For a behavioural check that actually calls transition_event, see the
-- SCRUM-34/52 plan's Task 1 Step 6 query (the plan left docs/ on 2026-09-28:
-- `git show 36aa9a7:docs/superpowers/plans/2026-09-23-approve-reject-event.md`),
-- which wraps the call in `begin; ... rollback;` so it leaves no trace; to
-- repair drift a real (non-rolled-back) approve/reject already left behind,
-- run `supabase/verification/event_review_fixture_reset.sql` instead.

select 'event_status_history exists' as check, to_regclass('public.event_status_history') is not null as ok
union all
select 'notifications exists', to_regclass('public.notifications') is not null
union all
select 'RLS on event_status_history', relrowsecurity from pg_class where oid = 'public.event_status_history'::regclass
union all
select 'RLS on notifications', relrowsecurity from pg_class where oid = 'public.notifications'::regclass
union all
select 'transition_event exists', to_regprocedure(
    'public.transition_event(uuid, uuid, text[], text, integer, text, text, text)') is not null
union all
select 'authenticated cannot execute transition_event', not has_function_privilege(
    'authenticated', 'public.transition_event(uuid, uuid, text[], text, integer, text, text, text)', 'execute')
union all
select 'anon cannot execute transition_event', not has_function_privilege(
    'anon', 'public.transition_event(uuid, uuid, text[], text, integer, text, text, text)', 'execute')
union all
select 'service_role can execute transition_event', has_function_privilege(
    'service_role', 'public.transition_event(uuid, uuid, text[], text, integer, text, text, text)', 'execute');
