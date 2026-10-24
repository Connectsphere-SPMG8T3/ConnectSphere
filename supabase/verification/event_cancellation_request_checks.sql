-- Story 84 cancellation requests: the real function, table constraints and RLS.
-- Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`. Raises on
-- the first failure and prints CANCELLATION REQUEST CHECKS PASSED otherwise.
-- Everything runs inside `begin; ... rollback;`, so the throwaway events leave no
-- trace. Uses the seeded organiser (…0001), coordinator (…0002, who also holds
-- venue_staff), venue staff (…0003) and the two Leads (…0007, …0009).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name) values
    ('e0000000-0000-4000-8000-0000000008a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Cancellation check (rolled back)'),
    ('e0000000-0000-4000-8000-0000000008a2', 'a0000000-0000-4000-8000-000000000001',
     null, 'submitted', 'Cancellation check, unassigned (rolled back)'),
    ('e0000000-0000-4000-8000-0000000008a3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Cancellation check, open change (rolled back)'),
    ('e0000000-0000-4000-8000-0000000008a4', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'rejected', 'Cancellation check, closed (rolled back)');

do $$
declare
    v_event uuid := 'e0000000-0000-4000-8000-0000000008a1';
    v_unassigned uuid := 'e0000000-0000-4000-8000-0000000008a2';
    v_with_change uuid := 'e0000000-0000-4000-8000-0000000008a3';
    v_closed uuid := 'e0000000-0000-4000-8000-0000000008a4';
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_statuses text[] := array['submitted', 'under_review', 'returned', 'planning', 'safety_review', 'confirmed'];
    v_result jsonb;
    v_rows integer;
    v_change public.event_change_requests;
begin
    -- The owner asks: one open request, trimmed, the coordinator notified in that role.
    v_result := public.request_event_cancellation(
        v_event, v_organiser, '  Keynote speaker withdrew  ', v_statuses, 'to coordinator', 'to leads');
    if v_result->>'outcome' is distinct from 'ok'
       or v_result->'request'->>'reason' is distinct from 'Keynote speaker withdrew'
       or v_result->'request'->>'status' is distinct from 'open'
       or v_result->'request'->'requested_by'->>'id' is distinct from v_organiser::text
       or v_result->'request'->'requested_by'->>'full_name' is null then
        raise exception 'CANCEL FAIL: the request was not recorded and returned as expected: %', v_result;
    end if;
    select count(*) into v_rows from public.event_change_requests
     where event_id = v_event and kind = 'cancellation' and status = 'open' and requested_by = v_organiser;
    if v_rows <> 1 then raise exception 'CANCEL FAIL: expected one open cancellation request'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'event_cancellation_requested' and recipient_id = v_coordinator
       and recipient_role = 'event_coordinator' and message = 'to coordinator';
    if v_rows <> 1 then raise exception 'CANCEL FAIL: the coordinator was not notified exactly once, as coordinator'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'event_cancellation_requested' and recipient_id <> v_coordinator;
    if v_rows <> 0 then raise exception 'CANCEL FAIL: someone other than the coordinator was notified'; end if;
    if (select status from public.events where id = v_event) <> 'planning' then
        raise exception 'CANCEL FAIL: requesting changed the event status';
    end if;

    -- CR-R1: a second request is refused and nothing more is written.
    v_result := public.request_event_cancellation(v_event, v_organiser, 'Again', v_statuses, 'x', 'y');
    if v_result->>'outcome' is distinct from 'already_open' then
        raise exception 'CANCEL FAIL: a second open request was not refused: %', v_result;
    end if;
    select count(*) into v_rows from public.event_change_requests where event_id = v_event;
    if v_rows <> 1 then raise exception 'CANCEL FAIL: the refused request was stored'; end if;

    -- The index backs CR-R1 up even if a writer skips the check.
    begin
        insert into public.event_change_requests (event_id, kind, reason, requested_by)
        values (v_event, 'cancellation', 'Direct insert', v_organiser);
        raise exception 'CANCEL FAIL: the index allowed a second open cancellation request';
    exception when unique_violation then null;
    end;

    -- Unassigned: each Lead is notified, in the Lead role.
    v_result := public.request_event_cancellation(v_unassigned, v_organiser, 'Budget cut', v_statuses, 'x', 'to leads');
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'CANCEL FAIL: an unassigned submitted event refused the request: %', v_result;
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_unassigned and type = 'event_cancellation_requested'
       and recipient_role = 'event_coordinator_lead' and message = 'to leads';
    if v_rows <> (select count(*) from public.user_roles where role = 'event_coordinator_lead') or v_rows = 0 then
        raise exception 'CANCEL FAIL: the Leads were not each notified once (% rows)', v_rows;
    end if;

    -- AC4: an open change request is superseded, with when and by whom.
    insert into public.event_change_requests (event_id, kind, reason, requested_by, changes, significant)
    values (v_with_change, 'change', 'Move to the afternoon', v_organiser, '{"event": [], "spaces": []}', true);
    v_result := public.request_event_cancellation(v_with_change, v_organiser, 'Venue too far', v_statuses, 'x', 'y');
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'CANCEL FAIL: an event with an open change request refused cancellation: %', v_result;
    end if;
    select * into v_change from public.event_change_requests where event_id = v_with_change and kind = 'change';
    if v_change.status <> 'superseded' or v_change.decided_at is null or v_change.decided_by is distinct from v_organiser then
        raise exception 'CANCEL FAIL: the open change request was not superseded';
    end if;

    -- Refusals write nothing.
    v_result := public.request_event_cancellation(v_closed, v_organiser, 'x', v_statuses, 'x', 'y');
    if v_result->>'outcome' is distinct from 'status_changed' then
        raise exception 'CANCEL FAIL: a rejected event was not refused: %', v_result;
    end if;
    v_result := public.request_event_cancellation(v_event, v_coordinator, 'x', v_statuses, 'x', 'y');
    if v_result->>'outcome' is distinct from 'not_owner' then
        raise exception 'CANCEL FAIL: a non-owner was not refused: %', v_result;
    end if;
    v_result := public.request_event_cancellation(
        'e0000000-0000-4000-8000-0000000008ff', v_organiser, 'x', v_statuses, 'x', 'y');
    if v_result->>'outcome' is distinct from 'not_found' then
        raise exception 'CANCEL FAIL: a missing event was not refused: %', v_result;
    end if;
    select count(*) into v_rows from public.event_change_requests where event_id = v_closed;
    if v_rows <> 0 then raise exception 'CANCEL FAIL: a refused request was stored'; end if;

    -- The table refuses a blank reason, an unknown kind and a decided-but-open row.
    begin
        insert into public.event_change_requests (event_id, kind, reason) values (v_closed, 'cancellation', '   ');
        raise exception 'CANCEL FAIL: a blank reason was accepted';
    exception when check_violation then null;
    end;
    begin
        insert into public.event_change_requests (event_id, kind, reason) values (v_closed, 'refund', 'x');
        raise exception 'CANCEL FAIL: an unknown kind was accepted';
    exception when check_violation then null;
    end;
    begin
        insert into public.event_change_requests (event_id, kind, reason, decided_at)
        values (v_closed, 'cancellation', 'x', now());
        raise exception 'CANCEL FAIL: an open request with a decision time was accepted';
    exception when check_violation then null;
    end;

    -- API-only: not callable by signed-in users.
    if has_function_privilege('authenticated',
            'public.request_event_cancellation(uuid, uuid, text, text[], text, text)', 'execute')
       or has_function_privilege('anon',
            'public.request_event_cancellation(uuid, uuid, text, text[], text, text)', 'execute') then
        raise exception 'CANCEL FAIL: a signed-in or anonymous user can execute request_event_cancellation';
    end if;
end $$;

-- RLS: the owning organiser, acting as organiser, reads the request; cannot write.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
declare v_rows integer;
begin
    if (select count(*) from public.event_change_requests where event_id = 'e0000000-0000-4000-8000-0000000008a1') <> 1 then
        raise exception 'CANCEL FAIL: the owning organiser cannot read the request';
    end if;
    update public.event_change_requests set status = 'approved', decided_at = now()
     where event_id = 'e0000000-0000-4000-8000-0000000008a1';
    get diagnostics v_rows = row_count;
    if v_rows <> 0 then raise exception 'CANCEL FAIL: the organiser updated a request'; end if;
    begin
        insert into public.event_change_requests (event_id, kind, reason)
        values ('e0000000-0000-4000-8000-0000000008a4', 'cancellation', 'x');
        raise exception 'CANCEL FAIL: the organiser inserted a request directly';
    exception when insufficient_privilege then null;
    end;
end $$;
reset role;

-- RLS: the assigned coordinator, acting as coordinator, reads it.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_change_requests where event_id = 'e0000000-0000-4000-8000-0000000008a1') <> 1 then
        raise exception 'CANCEL FAIL: the assigned coordinator cannot read the request';
    end if;
end $$;
reset role;

-- RLS: the same coordinator account, in a session acting as venue staff, sees nothing (SCRUM-76).
insert into auth.sessions (id, user_id, created_at, updated_at)
values ('c0000000-0000-4000-8000-0000000008c1', 'a0000000-0000-4000-8000-000000000002', now(), now());
insert into public.session_active_roles (session_id, profile_id, role)
values ('c0000000-0000-4000-8000-0000000008c1', 'a0000000-0000-4000-8000-000000000002', 'venue_staff');
select set_config('request.jwt.claims',
    '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated","session_id":"c0000000-0000-4000-8000-0000000008c1"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_change_requests where event_id = 'e0000000-0000-4000-8000-0000000008a1') <> 0 then
        raise exception 'CANCEL FAIL: the coordinator acting as venue staff can read the request';
    end if;
end $$;
reset role;

-- RLS: an unrelated staff member and a Lead see nothing.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000003","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_change_requests) <> 0 then
        raise exception 'CANCEL FAIL: venue staff can read cancellation requests';
    end if;
end $$;
reset role;
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000007","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_change_requests) <> 0 then
        raise exception 'CANCEL FAIL: a Lead can read cancellation requests';
    end if;
end $$;
reset role;

select 'CANCELLATION REQUEST CHECKS PASSED' as result;
rollback;
