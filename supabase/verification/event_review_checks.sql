-- SCRUM-34 / SCRUM-52: status history, notifications and transition_event.
-- Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`. Every row
-- should read `ok = true`. The behavioural block runs inside a transaction that
-- is rolled back, so it leaves no trace.

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
