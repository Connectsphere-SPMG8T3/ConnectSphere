-- CR-101: assignment tracking and public.reassign_event; every change rolls back.
-- Run with `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/verification/lead_assignment_checks.sql`.
-- Uses the seeded accounts: organiser ...01, coordinators ...02 and ...08, Lead ...07.
begin;

insert into public.events (id, organiser_id, coordinator_id, status, name)
values ('e0000000-0000-4000-8000-000000000401', 'a0000000-0000-4000-8000-000000000001', null,
        'under_review', 'Lead assignment (rolled back)'),
       ('e0000000-0000-4000-8000-000000000402', 'a0000000-0000-4000-8000-000000000001',
        'a0000000-0000-4000-8000-000000000002', 'completed', 'Lead assignment, completed (rolled back)');

do $$
declare
    e uuid := 'e0000000-0000-4000-8000-000000000401';
    done_event uuid := 'e0000000-0000-4000-8000-000000000402';
    organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    coordinator_a uuid := 'a0000000-0000-4000-8000-000000000002';
    coordinator_b uuid := 'a0000000-0000-4000-8000-000000000008';
    lead uuid := 'a0000000-0000-4000-8000-000000000007';
    active text[] := array['under_review','returned','planning','safety_review','confirmed'];
    v integer;
    r public.events;
    n integer;
    history_count integer;
    notification_count integer;
begin
    if to_regprocedure('public.reassign_event(uuid, uuid, uuid, integer, text[], text, text, text)') is null then
        raise exception 'CR-101: reassign_event missing';
    end if;
    if not exists (select 1 from information_schema.columns
                   where table_schema = 'public' and table_name = 'events' and column_name = 'assigned_by')
       or not exists (select 1 from information_schema.columns
                   where table_schema = 'public' and table_name = 'events' and column_name = 'assigned_at') then
        raise exception 'CR-101: events.assigned_by / assigned_at missing';
    end if;

    -- First assignment of an unassigned event.
    select version into v from public.events where id = e;
    select * into r from public.reassign_event(e, lead, coordinator_a, v, active, 'to A', 'prev', 'to organiser');
    if r.coordinator_id is distinct from coordinator_a or r.assigned_by is distinct from lead
       or r.assigned_at is null or r.version <> v + 1 or r.status is distinct from 'under_review' then
        raise exception 'CR-101: assign did not set coordinator/assigned_by/assigned_at/version';
    end if;
    -- A reassignment is not a status change: it must leave no history row, or the
    -- Safety Officer's queue order and the organiser's history would be corrupted.
    if exists (select 1 from public.event_status_history where event_id = e and from_status = to_status) then
        raise exception 'CR-101: reassign wrote a same-status history row';
    end if;
    if (select count(*) from public.notifications where event_id = e and recipient_id = coordinator_a and message = 'to A') <> 1
       or (select count(*) from public.notifications where event_id = e and recipient_id = organiser and message = 'to organiser') <> 1 then
        raise exception 'CR-101: assignee/organiser notices';
    end if;
    if exists (select 1 from public.notifications where event_id = e and recipient_id = lead) then
        raise exception 'CR-101: the Lead was notified of their own action';
    end if;
    if exists (select 1 from public.notifications where event_id = e and message = 'prev') then
        raise exception 'CR-101: an unassigned event has no previous coordinator to notify';
    end if;

    -- Reassignment notifies the previous coordinator too.
    select * into r from public.reassign_event(e, lead, coordinator_b, r.version, active, 'to B', 'prev', 'to organiser 2');
    if r.coordinator_id is distinct from coordinator_b then raise exception 'CR-101: reassign'; end if;
    if (select count(*) from public.notifications where event_id = e and recipient_id = coordinator_a and message = 'prev') <> 1 then
        raise exception 'CR-101: previous coordinator notice';
    end if;

    select count(*) into history_count from public.event_status_history where event_id = e;
    select count(*) into notification_count from public.notifications where event_id = e;

    -- A stale version changes nothing.
    select count(*) into n from public.reassign_event(e, lead, coordinator_a, r.version - 1, active, 'x', 'x', 'x');
    if n <> 0 or (select version from public.events where id = e) <> r.version
       or (select coordinator_id from public.events where id = e) <> coordinator_b
       or (select count(*) from public.event_status_history where event_id = e) <> history_count
       or (select count(*) from public.notifications where event_id = e) <> notification_count then
        raise exception 'CR-101: stale version changed data';
    end if;

    -- A target who is not a coordinator is refused (the organiser holds no coordinator role).
    select count(*) into n from public.reassign_event(e, lead, organiser, r.version, active, 'x', 'x', 'x');
    if n <> 0 or (select coordinator_id from public.events where id = e) <> coordinator_b then
        raise exception 'CR-101: non-coordinator target accepted';
    end if;

    -- A terminal event is refused.
    select version into v from public.events where id = done_event;
    select count(*) into n from public.reassign_event(done_event, lead, coordinator_b, v, active, 'x', 'x', 'x');
    if n <> 0 or (select coordinator_id from public.events where id = done_event) <> coordinator_a then
        raise exception 'CR-101: completed event reassigned';
    end if;
end $$;

-- Only the API's service role may call it.
set local role anon;
do $$ begin
    begin
        perform public.reassign_event(null, null, null, 0, array['planning'], 'x', 'x', 'x');
        raise exception 'CR-101: anon execute permitted';
    exception when insufficient_privilege then null; end;
end $$;
reset role;
set local role authenticated;
do $$ begin
    begin
        perform public.reassign_event(null, null, null, 0, array['planning'], 'x', 'x', 'x');
        raise exception 'CR-101: authenticated execute permitted';
    exception when insufficient_privilege then null; end;
end $$;
reset role;

select 'CR-101 LEAD ASSIGNMENT CHECKS PASSED' as result;
rollback;
