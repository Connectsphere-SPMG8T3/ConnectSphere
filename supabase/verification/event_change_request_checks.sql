-- Story 32 change requests: the real function, the one-open-per-event index, the
-- closing trigger and RLS. Run with the Supabase MCP execute_sql or
-- `psql "$DATABASE_URL" -f`. Raises on the first failure and prints CHANGE REQUEST
-- CHECKS PASSED otherwise. Everything runs inside `begin; ... rollback;`, so the
-- throwaway events leave no trace. Uses the seeded organiser (…0001), coordinator
-- (…0002, who also holds venue_staff), venue staff (…0003) and the Leads.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name) values
    ('e0000000-0000-4000-8000-0000000003a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Change check (rolled back)'),
    ('e0000000-0000-4000-8000-0000000003a2', 'a0000000-0000-4000-8000-000000000001',
     null, 'submitted', 'Change check, unassigned (rolled back)'),
    ('e0000000-0000-4000-8000-0000000003a3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Change check, cancellation open (rolled back)'),
    ('e0000000-0000-4000-8000-0000000003a4', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'cancelled', 'Change check, closed (rolled back)'),
    ('e0000000-0000-4000-8000-0000000003a5', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Change check, closing (rolled back)');

do $$
declare
    v_event uuid := 'e0000000-0000-4000-8000-0000000003a1';
    v_unassigned uuid := 'e0000000-0000-4000-8000-0000000003a2';
    v_with_cancellation uuid := 'e0000000-0000-4000-8000-0000000003a3';
    v_closed uuid := 'e0000000-0000-4000-8000-0000000003a4';
    v_closing uuid := 'e0000000-0000-4000-8000-0000000003a5';
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_statuses text[] := array['submitted', 'under_review', 'planning', 'safety_review', 'confirmed', 'preparation'];
    v_changes jsonb := '{"event": [{"field": "expected_attendance", "before": 80, "after": 120}], "spaces": []}';
    v_result jsonb;
    v_rows integer;
    v_change public.event_change_requests;
begin
    -- The owner asks at the current version: one open request with its changes,
    -- the coordinator notified in that role, the event untouched.
    v_result := public.request_event_change(
        v_event, v_organiser, '  Sponsor wants more seats  ', v_changes, true, v_statuses, 1,
        'to coordinator', 'to leads');
    if v_result->>'outcome' is distinct from 'ok'
       or v_result->'request'->>'kind' is distinct from 'change'
       or v_result->'request'->>'reason' is distinct from 'Sponsor wants more seats'
       or v_result->'request'->'changes' is distinct from v_changes
       or (v_result->'request'->>'significant')::boolean is distinct from true
       or v_result->'request'->'requested_by'->>'id' is distinct from v_organiser::text then
        raise exception 'CHANGE FAIL: the request was not recorded and returned as expected: %', v_result;
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'event_change_requested' and recipient_id = v_coordinator
       and recipient_role = 'event_coordinator' and message = 'to coordinator';
    if v_rows <> 1 then raise exception 'CHANGE FAIL: the coordinator was not notified exactly once, as coordinator'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'event_change_requested' and recipient_id <> v_coordinator;
    if v_rows <> 0 then raise exception 'CHANGE FAIL: someone other than the coordinator was notified'; end if;
    if (select status::text || ':' || version from public.events where id = v_event) <> 'planning:1' then
        raise exception 'CHANGE FAIL: requesting changed the event';
    end if;

    -- A second change request is refused and nothing more is written.
    v_result := public.request_event_change(v_event, v_organiser, 'Again', v_changes, true, v_statuses, 1, 'x', 'y');
    if v_result->>'outcome' is distinct from 'already_open' then
        raise exception 'CHANGE FAIL: a second open change request was not refused: %', v_result;
    end if;

    -- CR-R14: the index allows one open request per event, of either kind.
    begin
        insert into public.event_change_requests (event_id, kind, reason, requested_by)
        values (v_event, 'cancellation', 'Direct insert', v_organiser);
        raise exception 'CHANGE FAIL: the index allowed a cancellation beside an open change request';
    exception when unique_violation then null;
    end;

    -- Story 84 still supersedes the open change request when a cancellation is asked.
    v_result := public.request_event_cancellation(v_event, v_organiser, 'Venue too far',
        array['planning'], 'x', 'y');
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'CHANGE FAIL: a cancellation request was refused beside an open change: %', v_result;
    end if;
    select * into v_change from public.event_change_requests where event_id = v_event and kind = 'change';
    if v_change.status <> 'superseded' then
        raise exception 'CHANGE FAIL: the cancellation request did not supersede the change request';
    end if;

    -- CR-R14: an open cancellation request blocks a change request.
    insert into public.event_change_requests (event_id, kind, reason, requested_by)
    values (v_with_cancellation, 'cancellation', 'Budget cut', v_organiser);
    v_result := public.request_event_change(v_with_cancellation, v_organiser, 'x', v_changes, true, v_statuses, 1,
        'x', 'y');
    if v_result->>'outcome' is distinct from 'cancellation_open' then
        raise exception 'CHANGE FAIL: a change request was not refused beside an open cancellation: %', v_result;
    end if;

    -- Unassigned: each Lead is notified, in the Lead role.
    v_result := public.request_event_change(v_unassigned, v_organiser, 'x', v_changes, true, v_statuses, 1,
        'x', 'to leads');
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'CHANGE FAIL: an unassigned submitted event refused the request: %', v_result;
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_unassigned and type = 'event_change_requested'
       and recipient_role = 'event_coordinator_lead' and message = 'to leads';
    if v_rows <> (select count(*) from public.user_roles where role = 'event_coordinator_lead') or v_rows = 0 then
        raise exception 'CHANGE FAIL: the Leads were not each notified once (% rows)', v_rows;
    end if;

    -- Refusals write nothing: AC4 (closed), a stale version, a non-owner, a missing event.
    v_result := public.request_event_change(v_closed, v_organiser, 'x', v_changes, true, v_statuses, 1, 'x', 'y');
    if v_result->>'outcome' is distinct from 'status_changed' then
        raise exception 'CHANGE FAIL: a cancelled event was not refused: %', v_result;
    end if;
    v_result := public.request_event_change(v_closing, v_organiser, 'x', v_changes, true, v_statuses, 7, 'x', 'y');
    if v_result->>'outcome' is distinct from 'stale' then
        raise exception 'CHANGE FAIL: a stale version was not refused: %', v_result;
    end if;
    v_result := public.request_event_change(v_closing, v_coordinator, 'x', v_changes, true, v_statuses, 1, 'x', 'y');
    if v_result->>'outcome' is distinct from 'not_owner' then
        raise exception 'CHANGE FAIL: a non-owner was not refused: %', v_result;
    end if;
    v_result := public.request_event_change('e0000000-0000-4000-8000-0000000003ff', v_organiser, 'x', v_changes,
        true, v_statuses, 1, 'x', 'y');
    if v_result->>'outcome' is distinct from 'not_found' then
        raise exception 'CHANGE FAIL: a missing event was not refused: %', v_result;
    end if;
    select count(*) into v_rows from public.event_change_requests where event_id in (v_closed, v_closing);
    if v_rows <> 0 then raise exception 'CHANGE FAIL: a refused request was stored'; end if;

    -- CR-R18: closing the event closes its open change request.
    v_result := public.request_event_change(v_closing, v_organiser, 'x', v_changes, true, v_statuses, 1, 'x', 'y');
    update public.events set status = 'cancelled' where id = v_closing;
    select * into v_change from public.event_change_requests where event_id = v_closing;
    if v_change.status <> 'superseded' or v_change.decided_at is null
       or v_change.decision_reason <> 'Closed because the event was cancelled.' then
        raise exception 'CHANGE FAIL: closing the event did not close its change request: %', row_to_json(v_change);
    end if;

    -- The table refuses a change row without changes and a cancellation row with them.
    begin
        insert into public.event_change_requests (event_id, kind, reason) values (v_closed, 'change', 'x');
        raise exception 'CHANGE FAIL: a change request without changes was accepted';
    exception when check_violation then null;
    end;
    begin
        insert into public.event_change_requests (event_id, kind, reason, changes, significant)
        values (v_closed, 'cancellation', 'x', v_changes, false);
        raise exception 'CHANGE FAIL: a cancellation request with changes was accepted';
    exception when check_violation then null;
    end;

    -- API-only: not callable by signed-in users; the trigger function by nobody directly.
    if has_function_privilege('authenticated',
            'public.request_event_change(uuid, uuid, text, jsonb, boolean, text[], integer, text, text)', 'execute')
       or has_function_privilege('anon',
            'public.request_event_change(uuid, uuid, text, jsonb, boolean, text[], integer, text, text)', 'execute')
       or has_function_privilege('authenticated', 'private.close_change_request_on_closed_event()', 'execute') then
        raise exception 'CHANGE FAIL: a signed-in or anonymous user can execute a story 32 function';
    end if;
end $$;

-- RLS: the owning organiser, acting as organiser, reads the change request; cannot write.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
declare v_rows integer;
begin
    if (select count(*) from public.event_change_requests
         where event_id = 'e0000000-0000-4000-8000-0000000003a2' and kind = 'change') <> 1 then
        raise exception 'CHANGE FAIL: the owning organiser cannot read the change request';
    end if;
    update public.event_change_requests set status = 'approved', decided_at = now()
     where event_id = 'e0000000-0000-4000-8000-0000000003a2';
    get diagnostics v_rows = row_count;
    if v_rows <> 0 then raise exception 'CHANGE FAIL: the organiser updated a change request'; end if;
end $$;
reset role;

-- RLS: the same coordinator account, acting as venue staff, sees nothing (SCRUM-76).
insert into auth.sessions (id, user_id, created_at, updated_at)
values ('c0000000-0000-4000-8000-0000000003c1', 'a0000000-0000-4000-8000-000000000002', now(), now());
insert into public.session_active_roles (session_id, profile_id, role)
values ('c0000000-0000-4000-8000-0000000003c1', 'a0000000-0000-4000-8000-000000000002', 'venue_staff');
select set_config('request.jwt.claims',
    '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated","session_id":"c0000000-0000-4000-8000-0000000003c1"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_change_requests where event_id = 'e0000000-0000-4000-8000-0000000003a1') <> 0 then
        raise exception 'CHANGE FAIL: the coordinator acting as venue staff can read change requests';
    end if;
end $$;
reset role;

-- RLS: the assigned coordinator, acting as coordinator, reads them.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_change_requests
         where event_id = 'e0000000-0000-4000-8000-0000000003a1' and kind = 'change') <> 1 then
        raise exception 'CHANGE FAIL: the assigned coordinator cannot read the change request';
    end if;
end $$;
reset role;

select 'CHANGE REQUEST CHECKS PASSED' as result;

rollback;
