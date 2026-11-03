-- CR-106 reassignment requests: the real functions, the one-open-per-event index, the
-- Lead recipient rule, reassign_event closing the request, the closing trigger, privileges
-- and RLS. Run with `supabase db query --linked -f` or
-- `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f`. Raises on the first failure and prints
-- REASSIGNMENT REQUEST CHECKS PASSED otherwise. Everything runs inside `begin; ... rollback;`,
-- so the throwaway events leave no trace. Uses the seeded organiser (…0001), coordinators
-- (…0002, who also holds venue_staff, and …0008) and the Lead (…0007).

begin;

insert into public.events (id, organiser_id, coordinator_id, assigned_by, status, name) values
    -- Assigned by a Lead who is still a Lead: only that Lead is told.
    ('e0000000-0000-4000-8000-000000001061', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000007',
     'planning', 'Reassign check (rolled back)'),
    -- Assigned before Leads existed: every Lead is told.
    ('e0000000-0000-4000-8000-000000001062', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', null, 'planning', 'Reassign check, no Lead (rolled back)'),
    -- assigned_by is no longer a Lead (here the organiser, who holds no Lead role): every Lead is told.
    ('e0000000-0000-4000-8000-000000001063', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000001',
     'planning', 'Reassign check, former Lead (rolled back)'),
    -- Not an active status.
    ('e0000000-0000-4000-8000-000000001064', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000007',
     'submitted', 'Reassign check, submitted (rolled back)'),
    -- For reassign_event to close the request.
    ('e0000000-0000-4000-8000-000000001065', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000007',
     'planning', 'Reassign check, reassigned (rolled back)'),
    -- For the closing trigger.
    ('e0000000-0000-4000-8000-000000001066', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000007',
     'confirmed', 'Reassign check, cancelled (rolled back)'),
    ('e0000000-0000-4000-8000-000000001067', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000007',
     'confirmed', 'Reassign check, preparation (rolled back)'),
    ('e0000000-0000-4000-8000-000000001068', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000007',
     'planning', 'Reassign check, still reassignable (rolled back)'),
    -- Already in Preparation, which is reassignable (QA3-3, D73).
    ('e0000000-0000-4000-8000-000000001069', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000007',
     'preparation', 'Reassign check, already in preparation (rolled back)');

do $$
declare
    v_event uuid := 'e0000000-0000-4000-8000-000000001061';
    v_no_lead uuid := 'e0000000-0000-4000-8000-000000001062';
    v_former_lead uuid := 'e0000000-0000-4000-8000-000000001063';
    v_submitted uuid := 'e0000000-0000-4000-8000-000000001064';
    v_reassigned uuid := 'e0000000-0000-4000-8000-000000001065';
    v_cancelled uuid := 'e0000000-0000-4000-8000-000000001066';
    v_preparation uuid := 'e0000000-0000-4000-8000-000000001067';
    v_active uuid := 'e0000000-0000-4000-8000-000000001068';
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_other_coordinator uuid := 'a0000000-0000-4000-8000-000000000008';
    v_lead uuid := 'a0000000-0000-4000-8000-000000000007';
    v_prep_direct uuid := 'e0000000-0000-4000-8000-000000001069';
    v_statuses text[] := array['under_review', 'returned', 'planning', 'safety_review', 'confirmed', 'preparation'];
    v_result jsonb;
    v_rows integer;
    v_leads integer;
    v_request public.event_reassignment_requests;
    v_event_row public.events;
begin
    select count(*) into v_leads from public.user_roles where role = 'event_coordinator_lead';
    if v_leads = 0 then raise exception 'REASSIGN FAIL: no Lead is seeded, so the recipient rule cannot be checked'; end if;

    -- AC1, AC2, AC3: the assigned coordinator asks; one open request, reason trimmed; only the Lead
    -- whose scope holds the event is told, in the Lead role; the event is untouched.
    select * into v_event_row from public.events where id = v_event;
    v_result := public.request_reassignment(v_event, v_coordinator, '  On leave this month  ', v_statuses, 'to the lead');
    if v_result->>'outcome' is distinct from 'ok'
       or v_result->'request'->>'kind' is distinct from 'reassignment'
       or v_result->'request'->>'status' is distinct from 'open'
       or v_result->'request'->>'reason' is distinct from 'On leave this month'
       or v_result->'request'->'requested_by'->>'id' is distinct from v_coordinator::text then
        raise exception 'REASSIGN FAIL: the request was not recorded and returned as expected: %', v_result;
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'reassignment_requested' and recipient_id = v_lead
       and recipient_role = 'event_coordinator_lead' and message = 'to the lead';
    if v_rows <> 1 then raise exception 'REASSIGN FAIL: the Lead holding the scope was not notified exactly once, as a Lead'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'reassignment_requested' and recipient_id <> v_lead;
    if v_rows <> 0 then raise exception 'REASSIGN FAIL: someone other than the Lead holding the scope was notified'; end if;
    if (select status::text || ':' || version || ':' || coalesce(coordinator_id::text, '-') || ':' || coalesce(assigned_by::text, '-')
          from public.events where id = v_event)
       is distinct from (v_event_row.status::text || ':' || v_event_row.version || ':' || v_event_row.coordinator_id || ':' || v_event_row.assigned_by) then
        raise exception 'REASSIGN FAIL: requesting changed the event (AC3)';
    end if;

    -- AC5: a second request is refused while one is open, and nothing more is sent.
    v_result := public.request_reassignment(v_event, v_coordinator, 'again', v_statuses, 'x');
    if v_result->>'outcome' is distinct from 'already_open' then
        raise exception 'REASSIGN FAIL: a second open request was not refused: %', v_result;
    end if;
    select count(*) into v_rows from public.notifications where event_id = v_event and type = 'reassignment_requested';
    if v_rows <> 1 then raise exception 'REASSIGN FAIL: a refused request still notified'; end if;
    -- The index backs it up when the function is bypassed.
    begin
        insert into public.event_reassignment_requests (event_id, reason, requested_by) values (v_event, 'direct', v_coordinator);
        raise exception 'REASSIGN FAIL: the one-open-request index let a second open request in';
    exception when unique_violation then
        null;
    end;

    -- AC7: only the assigned coordinator; refused outcomes write nothing.
    v_result := public.request_reassignment(v_no_lead, v_organiser, 'not mine', v_statuses, 'x');
    if v_result->>'outcome' is distinct from 'not_assigned' then
        raise exception 'REASSIGN FAIL: a non-coordinator was not refused: %', v_result;
    end if;
    v_result := public.request_reassignment(v_no_lead, v_other_coordinator, 'not mine either', v_statuses, 'x');
    if v_result->>'outcome' is distinct from 'not_assigned' then
        raise exception 'REASSIGN FAIL: another coordinator was not refused: %', v_result;
    end if;
    v_result := public.request_reassignment('e0000000-0000-4000-8000-0000000010ff', v_coordinator, 'x', v_statuses, 'x');
    if v_result->>'outcome' is distinct from 'not_found' then
        raise exception 'REASSIGN FAIL: an unknown event was not refused: %', v_result;
    end if;
    v_result := public.request_reassignment(v_submitted, v_coordinator, 'x', v_statuses, 'x');
    if v_result->>'outcome' is distinct from 'status_changed' then
        raise exception 'REASSIGN FAIL: an event outside the active statuses was not refused: %', v_result;
    end if;
    select count(*) into v_rows from public.event_reassignment_requests where event_id in (v_no_lead, v_submitted);
    if v_rows <> 0 then raise exception 'REASSIGN FAIL: a refused request left a row'; end if;

    -- AC2: no Lead holds the scope (assigned before Leads existed, or by someone no longer a Lead):
    -- every Lead is told, each once, in the Lead role.
    v_result := public.request_reassignment(v_no_lead, v_coordinator, 'x', v_statuses, 'to every lead');
    if v_result->>'outcome' is distinct from 'ok' then raise exception 'REASSIGN FAIL: unscoped request failed: %', v_result; end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_no_lead and type = 'reassignment_requested' and recipient_role = 'event_coordinator_lead';
    if v_rows <> v_leads then raise exception 'REASSIGN FAIL: with no scope holder % of % Leads were notified', v_rows, v_leads; end if;
    v_result := public.request_reassignment(v_former_lead, v_coordinator, 'x', v_statuses, 'to every lead');
    if v_result->>'outcome' is distinct from 'ok' then raise exception 'REASSIGN FAIL: former-Lead request failed: %', v_result; end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_former_lead and type = 'reassignment_requested' and recipient_role = 'event_coordinator_lead';
    if v_rows <> v_leads then raise exception 'REASSIGN FAIL: with a former Lead as assigner % of % Leads were notified', v_rows, v_leads; end if;

    -- AC5: the Lead declines with a reason; the coordinator is told, in that role; the assignment is unchanged.
    v_result := public.decline_reassignment_request(v_event, v_lead, '  No cover this month  ', 'declined: no cover');
    if v_result->>'outcome' is distinct from 'ok'
       or v_result->'request'->>'status' is distinct from 'declined' then
        raise exception 'REASSIGN FAIL: the decline was not recorded: %', v_result;
    end if;
    select * into v_request from public.event_reassignment_requests where event_id = v_event;
    if v_request.decided_by is distinct from v_lead or v_request.decided_at is null
       or v_request.decision_reason is distinct from 'No cover this month' then
        raise exception 'REASSIGN FAIL: the decline did not record who, when and why (AC6)';
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'reassignment_declined' and recipient_id = v_coordinator
       and recipient_role = 'event_coordinator' and message = 'declined: no cover';
    if v_rows <> 1 then raise exception 'REASSIGN FAIL: the coordinator was not told of the decline, as coordinator'; end if;
    if (select coordinator_id from public.events where id = v_event) is distinct from v_coordinator then
        raise exception 'REASSIGN FAIL: declining changed the assignment';
    end if;
    v_result := public.decline_reassignment_request(v_event, v_lead, 'again', 'x');
    if v_result->>'outcome' is distinct from 'no_open_request' then
        raise exception 'REASSIGN FAIL: declining a closed request was not refused: %', v_result;
    end if;
    v_result := public.decline_reassignment_request('e0000000-0000-4000-8000-0000000010ff', v_lead, 'x', 'x');
    if v_result->>'outcome' is distinct from 'not_found' then
        raise exception 'REASSIGN FAIL: declining on an unknown event was not refused: %', v_result;
    end if;
    -- A decline needs a reason, whatever the caller.
    begin
        update public.event_reassignment_requests set decision_reason = null where id = v_request.id;
        raise exception 'REASSIGN FAIL: a declined request lost its reason';
    exception when check_violation then
        null;
    end;
    -- A closed request frees the slot: the coordinator may ask again.
    v_result := public.request_reassignment(v_event, v_coordinator, 'asking again', v_statuses, 'to the lead again');
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'REASSIGN FAIL: a new request after a decline was refused: %', v_result;
    end if;

    -- AC5, AC6: reassign_event answers the open request, in the same transaction as the move.
    v_result := public.request_reassignment(v_reassigned, v_coordinator, 'handing over', v_statuses, 'to the lead');
    if v_result->>'outcome' is distinct from 'ok' then raise exception 'REASSIGN FAIL: request failed: %', v_result; end if;
    select * into v_event_row from public.events where id = v_reassigned;
    select count(*) into v_rows from public.reassign_event(
        v_reassigned, v_lead, v_other_coordinator, v_event_row.version, v_statuses, 'to new', 'to previous', 'to organiser');
    if v_rows <> 1 then raise exception 'REASSIGN FAIL: the Lead could not reassign the event'; end if;
    select * into v_request from public.event_reassignment_requests where event_id = v_reassigned;
    if v_request.status <> 'reassigned' or v_request.decided_by is distinct from v_lead or v_request.decided_at is null then
        raise exception 'REASSIGN FAIL: reassigning did not close the request as reassigned by the Lead: %', v_request.status;
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_reassigned and type = 'event_reassigned' and recipient_id = v_coordinator;
    if v_rows <> 1 then raise exception 'REASSIGN FAIL: the coordinator who asked was not told the event was reassigned'; end if;
    select count(*) into v_rows from public.event_assignment_history
     where event_id = v_reassigned and from_coordinator_id = v_coordinator and to_coordinator_id = v_other_coordinator;
    if v_rows <> 1 then raise exception 'REASSIGN FAIL: the reassignment is not in the assignment history'; end if;

    -- [Team decision] An event no Lead can reassign closes its open request, whatever moved it.
    perform public.request_reassignment(v_cancelled, v_coordinator, 'x', v_statuses, 'x');
    update public.events set status = 'cancelled' where id = v_cancelled;
    select * into v_request from public.event_reassignment_requests where event_id = v_cancelled;
    if v_request.status <> 'superseded' or v_request.decided_at is null
       or v_request.decision_reason is distinct from 'Closed because the event was cancelled.' then
        raise exception 'REASSIGN FAIL: cancelling the event did not close its request: % / %', v_request.status, v_request.decision_reason;
    end if;
    -- Preparation is still reassignable (QA3-3, D73, migration 20261101130000): it keeps the request...
    perform public.request_reassignment(v_preparation, v_coordinator, 'x', v_statuses, 'x');
    update public.events set status = 'preparation' where id = v_preparation;
    if (select status from public.event_reassignment_requests where event_id = v_preparation) <> 'open' then
        raise exception 'REASSIGN FAIL: moving to Preparation closed the request, though a Lead can still reassign it';
    end if;
    -- ...and takes a new one, because the API sends Preparation among the active statuses.
    v_result := public.request_reassignment(v_prep_direct, v_coordinator, 'x', v_statuses, 'x');
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'REASSIGN FAIL: an event already in Preparation refused a request: %', v_result;
    end if;
    -- ...but a move between reassignable statuses leaves it open.
    perform public.request_reassignment(v_active, v_coordinator, 'x', v_statuses, 'x');
    update public.events set status = 'safety_review' where id = v_active;
    if (select status from public.event_reassignment_requests where event_id = v_active) <> 'open' then
        raise exception 'REASSIGN FAIL: a move between reassignable statuses closed the request';
    end if;

    -- API-only: not callable by signed-in or anonymous users; the trigger function by nobody directly.
    if has_function_privilege('authenticated', 'public.request_reassignment(uuid, uuid, text, text[], text)', 'execute')
       or has_function_privilege('anon', 'public.request_reassignment(uuid, uuid, text, text[], text)', 'execute')
       or has_function_privilege('authenticated', 'public.decline_reassignment_request(uuid, uuid, text, text)', 'execute')
       or has_function_privilege('anon', 'public.decline_reassignment_request(uuid, uuid, text, text)', 'execute')
       or has_function_privilege('authenticated', 'private.close_reassignment_request_on_unreassignable_event()', 'execute') then
        raise exception 'REASSIGN FAIL: a signed-in or anonymous user can execute a CR-106 function';
    end if;
    if has_function_privilege('authenticated',
            'public.reassign_event(uuid, uuid, uuid, integer, text[], text, text, text)', 'execute')
       or has_function_privilege('anon',
            'public.reassign_event(uuid, uuid, uuid, integer, text[], text, text, text)', 'execute') then
        raise exception 'REASSIGN FAIL: reassign_event became callable by signed-in or anonymous users';
    end if;
end $$;

-- RLS: the assigned coordinator, acting as coordinator, reads their request; cannot write it.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
declare v_rows integer;
begin
    if (select count(*) from public.event_reassignment_requests
         where event_id = 'e0000000-0000-4000-8000-000000001068') <> 1 then
        raise exception 'REASSIGN FAIL: the assigned coordinator cannot read their request';
    end if;
    update public.event_reassignment_requests set reason = 'edited'
     where event_id = 'e0000000-0000-4000-8000-000000001068';
    get diagnostics v_rows = row_count;
    if v_rows <> 0 then raise exception 'REASSIGN FAIL: the coordinator updated a request directly'; end if;
    begin
        insert into public.event_reassignment_requests (event_id, reason, requested_by)
        values ('e0000000-0000-4000-8000-000000001061', 'direct', 'a0000000-0000-4000-8000-000000000002');
        raise exception 'REASSIGN FAIL: the coordinator inserted a request directly';
    exception when insufficient_privilege then
        null;
    end;
end $$;
reset role;

-- RLS: the organiser sees none of it, because the request is internal.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_reassignment_requests) <> 0 then
        raise exception 'REASSIGN FAIL: the organiser can read reassignment requests';
    end if;
end $$;
reset role;

-- RLS: the same coordinator account, acting as venue staff, sees nothing (SCRUM-76).
insert into auth.sessions (id, user_id, created_at, updated_at)
values ('c0000000-0000-4000-8000-0000000010c1', 'a0000000-0000-4000-8000-000000000002', now(), now());
insert into public.session_active_roles (session_id, profile_id, role)
values ('c0000000-0000-4000-8000-0000000010c1', 'a0000000-0000-4000-8000-000000000002', 'venue_staff');
select set_config('request.jwt.claims',
    '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated","session_id":"c0000000-0000-4000-8000-0000000010c1"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_reassignment_requests) <> 0 then
        raise exception 'REASSIGN FAIL: the coordinator acting as venue staff can read reassignment requests';
    end if;
end $$;
reset role;

select 'REASSIGNMENT REQUEST CHECKS PASSED' as result;

rollback;
