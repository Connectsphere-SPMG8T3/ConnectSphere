-- SCRUM-33 return for amendment: the real functions, table constraints and RLS.
-- Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`. Raises on
-- the first failure and prints AMENDMENT CHECKS PASSED otherwise. Everything
-- runs inside `begin; ... rollback;`, so the throwaway event leaves no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002) and venue staff (…0003).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name)
values ('e0000000-0000-4000-8000-0000000003a1', 'a0000000-0000-4000-8000-000000000001',
        'a0000000-0000-4000-8000-000000000002', 'under_review', 'Amendment check (rolled back)');

do $$
declare
    v_event uuid := 'e0000000-0000-4000-8000-0000000003a1';
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_row public.events;
    v_rows integer;
begin
    select * into v_row from public.events where id = v_event;

    -- Return.
    select * into v_row from public.return_event_for_amendment(
        v_event, v_coordinator, array['under_review'], 'returned', v_row.version,
        '  Please confirm the attendance  ', array['expected_attendance'],
        'Your event "Amendment check (rolled back)" was returned for amendment: Please confirm the attendance');
    if v_row.status is distinct from 'returned' then
        raise exception 'AMENDMENT FAIL: return did not move the event to returned (got %)', v_row.status;
    end if;

    select count(*) into v_rows from public.amendment_requests
     where event_id = v_event and resubmitted_at is null
       and message = 'Please confirm the attendance' and flagged_fields = array['expected_attendance'];
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: return did not open one trimmed amendment row'; end if;

    select count(*) into v_rows from public.event_status_history
     where event_id = v_event and from_status = 'under_review' and to_status = 'returned'
       and actor_id = v_coordinator and reason = 'Please confirm the attendance';
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: return is not in history with its message'; end if;

    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'event_returned' and recipient_id = v_organiser;
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: the organiser was not notified of the return'; end if;

    -- A second open amendment for the same event is refused.
    begin
        insert into public.amendment_requests (event_id, message) values (v_event, 'second open row');
        raise exception 'AMENDMENT FAIL: a second open amendment was accepted';
    exception when unique_violation then null;
    end;

    -- A blank message is refused by the table itself.
    begin
        update public.amendment_requests set message = '   ' where event_id = v_event;
        raise exception 'AMENDMENT FAIL: a blank message was accepted';
    exception when check_violation then null;
    end;

    -- A stale version changes nothing.
    select count(*) into v_rows from public.resubmit_event(
        v_event, v_organiser, array['returned'], 'under_review', v_row.version - 1, 'note', 'msg');
    if v_rows <> 0 then raise exception 'AMENDMENT FAIL: a stale resubmit returned a row'; end if;
    if (select status from public.events where id = v_event) is distinct from 'returned' then
        raise exception 'AMENDMENT FAIL: a stale resubmit changed the status';
    end if;

    -- Resubmit.
    select * into v_row from public.resubmit_event(
        v_event, v_organiser, array['returned'], 'under_review', v_row.version,
        '  Attendance is now 40  ', '"Amendment check (rolled back)" was amended and resubmitted: Attendance is now 40');
    if v_row.status is distinct from 'under_review' or v_row.coordinator_id is distinct from v_coordinator then
        raise exception 'AMENDMENT FAIL: resubmit did not return the event to the same coordinator';
    end if;

    select count(*) into v_rows from public.amendment_requests
     where event_id = v_event and resubmitted_at is not null and resubmission_note = 'Attendance is now 40';
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: resubmit did not close the amendment with its note'; end if;

    select count(*) into v_rows from public.event_status_history
     where event_id = v_event and from_status = 'returned' and to_status = 'under_review'
       and actor_id = v_organiser and reason = 'Attendance is now 40';
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: resubmission is not in history with its note'; end if;

    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'event_resubmitted' and recipient_id = v_coordinator;
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: the coordinator was not notified of the resubmission'; end if;

    select count(*) into v_rows from public.notifications
     where event_id = v_event and recipient_id = v_organiser and type = 'event_resubmitted';
    if v_rows <> 0 then raise exception 'AMENDMENT FAIL: the organiser was notified of their own resubmission'; end if;

    -- Return again: a second round, one open.
    select * into v_row from public.return_event_for_amendment(
        v_event, v_coordinator, array['under_review'], 'returned', v_row.version,
        'Also add the timezone', array[]::text[], 'msg');
    select count(*) into v_rows from public.amendment_requests where event_id = v_event;
    if v_rows <> 2 then raise exception 'AMENDMENT FAIL: a second return did not add a second row'; end if;
    select count(*) into v_rows from public.amendment_requests where event_id = v_event and resubmitted_at is null;
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: more than one amendment is open'; end if;

    -- API-only: not callable by signed-in users.
    if has_function_privilege('authenticated', 'public.return_event_for_amendment(uuid, uuid, text[], text, integer, text, text[], text)', 'execute')
       or has_function_privilege('authenticated', 'public.resubmit_event(uuid, uuid, text[], text, integer, text, text)', 'execute') then
        raise exception 'AMENDMENT FAIL: authenticated can execute the amendment functions';
    end if;
end $$;

-- RLS: the owning organiser, acting as organiser, sees both rounds.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.amendment_requests where event_id = 'e0000000-0000-4000-8000-0000000003a1') <> 2 then
        raise exception 'AMENDMENT FAIL: the owning organiser cannot read the amendments';
    end if;
end $$;
reset role;

-- RLS: the assigned coordinator, acting as coordinator, sees both rounds.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.amendment_requests where event_id = 'e0000000-0000-4000-8000-0000000003a1') <> 2 then
        raise exception 'AMENDMENT FAIL: the assigned coordinator cannot read the amendments';
    end if;
end $$;
reset role;

-- RLS: an unrelated staff member sees nothing.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000003","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if exists (select 1 from public.amendment_requests) then
        raise exception 'AMENDMENT FAIL: venue staff can read amendment requests';
    end if;
end $$;
reset role;

-- RLS: anonymous callers see nothing.
set local role anon;
do $$
begin
    if exists (select 1 from public.amendment_requests) then
        raise exception 'AMENDMENT FAIL: anon can read amendment requests';
    end if;
end $$;
reset role;

select 'AMENDMENT CHECKS PASSED' as result;

rollback;
