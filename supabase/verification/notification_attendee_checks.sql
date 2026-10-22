-- SCRUM-53 public.notify_registered_attendees. Needs Dev 1's
-- public.event_registrations (SCRUM-43, migration 20261022100000) and migrations
-- 20261021110000 and 20261022120000. Run with the Supabase MCP execute_sql or
-- `psql "$DATABASE_URL" -f`. Raises on the first failure and returns
-- NOTIFICATION ATTENDEE CHECKS PASSED otherwise. Everything runs inside
-- `begin; ... rollback;`.
-- Seeded accounts: attendee …0005; …0004, …0003 and …0002 stand in for the other
-- registrations because the function filters on status, not on the account's role.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name) values
    ('e0000000-0000-4000-8000-0000000007b1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Attendee check (rolled back)');

insert into public.event_registrations (event_id, attendee_id, status, withdrawn_at) values
    ('e0000000-0000-4000-8000-0000000007b1', 'a0000000-0000-4000-8000-000000000005', 'registered', null),
    ('e0000000-0000-4000-8000-0000000007b1', 'a0000000-0000-4000-8000-000000000004', 'registered', null),
    ('e0000000-0000-4000-8000-0000000007b1', 'a0000000-0000-4000-8000-000000000003', 'cancelled', null),
    ('e0000000-0000-4000-8000-0000000007b1', 'a0000000-0000-4000-8000-000000000002', 'withdrawn', now());

do $$
declare
    v_event uuid := 'e0000000-0000-4000-8000-0000000007b1';
    v_attendee uuid := 'a0000000-0000-4000-8000-000000000005';
    v_actor uuid := 'a0000000-0000-4000-8000-000000000004';
    v_count integer;
begin
    -- Only Registered attendees, and not the actor who is also registered.
    v_count := public.notify_registered_attendees(v_event, 'attendee_event_changed', 'Date moved', v_actor);
    if v_count <> 1 then
        raise exception 'ATTENDEE FAIL: expected 1 notified (registered, not the actor), got %', v_count;
    end if;
    if (select count(*) from public.notifications where event_id = v_event) <> 1 then
        raise exception 'ATTENDEE FAIL: cancelled, withdrawn or actor rows were written';
    end if;
    if not exists (
        select 1 from public.notifications
         where event_id = v_event and recipient_id = v_attendee
           and type = 'attendee_event_changed' and recipient_role = 'attendee'
    ) then
        raise exception 'ATTENDEE FAIL: the registered attendee''s row is missing or has the wrong role';
    end if;

    -- Without an actor, every registered attendee is told.
    v_count := public.notify_registered_attendees(v_event, 'attendee_event_cancelled', 'Cancelled');
    if v_count <> 2 then
        raise exception 'ATTENDEE FAIL: expected 2 registered attendees without an actor, got %', v_count;
    end if;

    -- A dedupe key makes a re-run a no-op.
    perform public.notify_registered_attendees(v_event, 'attendee_event_reminder', 'Tomorrow', null, 'k-att');
    if public.notify_registered_attendees(v_event, 'attendee_event_reminder', 'Tomorrow', null, 'k-att') <> 0 then
        raise exception 'ATTENDEE FAIL: the same dedupe key notified twice';
    end if;

    -- An event nobody registered for.
    if public.notify_registered_attendees('e0000000-0000-4000-8000-0000000007ff', 'attendee_event_changed', 'x') <> 0 then
        raise exception 'ATTENDEE FAIL: an unknown event notified someone';
    end if;

    -- Grants: service_role only.
    if has_function_privilege('anon', 'public.notify_registered_attendees(uuid, text, text, uuid, text)', 'execute')
       or has_function_privilege('authenticated', 'public.notify_registered_attendees(uuid, text, text, uuid, text)', 'execute') then
        raise exception 'ATTENDEE FAIL: executable by anon or authenticated';
    end if;
end $$;

select 'NOTIFICATION ATTENDEE CHECKS PASSED' as result;

rollback;
