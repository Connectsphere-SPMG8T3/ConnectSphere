-- SCRUM-53 AC4: the attendee reminder job is scheduled every 15 minutes, so it
-- runs from the moment migration 20261021120000 is pushed, even before SCRUM-43's
-- public.event_registrations exists. It must then do nothing instead of failing (a
-- failed run is logged in cron.job_run_details every 15 minutes, 96 a day).
-- Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`; returns
-- NOTIFICATION REMINDER GUARD CHECKS PASSED. Rolled back, changes nothing.
-- When the registrations table exists this only proves the call succeeds.

begin;

do $$
declare
    v_sent integer;
begin
    v_sent := public.send_attendee_event_reminders();
    if to_regclass('public.event_registrations') is null and v_sent <> 0 then
        raise exception 'GUARD FAIL: without a registrations table the reminder sent % notifications', v_sent;
    end if;
end $$;

select 'NOTIFICATION REMINDER GUARD CHECKS PASSED' as result;

rollback;
