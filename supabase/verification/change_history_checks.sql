-- Story 62 change history: field edits recorded with the change (AC1), every
-- history table refusing edits and deletes (AC6), and who can read the edits
-- directly (AC3, AC4). Run with `supabase db query --linked -f` (verify_live.py
-- does). Raises on the first failure and prints CHANGE HISTORY CHECKS PASSED
-- otherwise. Everything runs inside `begin; ... rollback;`, so the throwaway
-- events, account and history leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002), tech support (…0004)
-- and a second coordinator not assigned to the events (…0008).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, description, starts_at, ends_at,
                           expected_attendance) values
    ('e0000000-0000-4000-8000-0000000062a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'returned', 'History check H1 (rolled back)', 'Before',
     '2033-06-01 09:00+08', '2033-06-01 12:00+08', 30),
    ('e0000000-0000-4000-8000-0000000062a2', 'a0000000-0000-4000-8000-000000000001',
     null, 'draft', 'History check H2 (rolled back)', null,
     '2033-06-02 09:00+08', '2033-06-02 12:00+08', 30);

-- A throwaway account, to prove a deleted profile still nulls out its history.
insert into auth.users (id, instance_id, aud, role, email, raw_user_meta_data, created_at, updated_at)
values ('c0000000-0000-4000-8000-0000000062b1', '00000000-0000-0000-0000-000000000000', 'authenticated',
        'authenticated', 'verify.history@connectsphere.dev', '{"full_name":"Verify History"}', now(), now());

do $$
declare
    c_org constant uuid := 'a0000000-0000-4000-8000-000000000001';
    c_e1 constant uuid := 'e0000000-0000-4000-8000-0000000062a1';
    c_e2 constant uuid := 'e0000000-0000-4000-8000-0000000062a2';
    c_temp constant uuid := 'c0000000-0000-4000-8000-0000000062b1';
    v_version integer;
    v_event public.events;
    v_rows integer;
    v_table text;
    v_refused boolean;
begin
    -- ---- TC-HIST-001 (AC1): an edit to a returned request saves and records each changed field
    select version into v_version from public.events where id = c_e1;
    select * into v_event from public.edit_event(c_e1, c_org,
        '{"name": "History check H1 (rolled back)", "description": "After", "expected_attendance": 40}'::jsonb,
        v_version, array['returned']);
    if v_event.id is null or v_event.description <> 'After' or v_event.expected_attendance <> 40
       or v_event.version <> v_version + 1 then
        raise exception 'HIST FAIL: the edit was not saved with a new version';
    end if;
    select count(*) into v_rows from public.event_edit_history where event_id = c_e1;
    if v_rows <> 2 then
        raise exception 'HIST FAIL: % edit rows, expected 2 (the unchanged name is not recorded)', v_rows;
    end if;
    perform 1 from public.event_edit_history
     where event_id = c_e1 and field = 'description' and old_value = '"Before"'::jsonb
       and new_value = '"After"'::jsonb and actor_id = c_org;
    if not found then raise exception 'HIST FAIL: the description edit lost its old value, new value or actor'; end if;
    perform 1 from public.event_edit_history
     where event_id = c_e1 and field = 'expected_attendance' and old_value = '30'::jsonb and new_value = '40'::jsonb;
    if not found then raise exception 'HIST FAIL: the attendance edit was not recorded'; end if;

    -- ---- TC-HIST-002 (AC1, DB-5): a stale version or another status changes and records nothing
    select * into v_event from public.edit_event(c_e1, c_org, '{"description": "Stale"}'::jsonb,
        v_version, array['returned']);
    if v_event.id is not null then raise exception 'HIST FAIL: a stale version was saved'; end if;
    select * into v_event from public.edit_event(c_e1, c_org, '{"description": "Wrong status"}'::jsonb,
        v_version + 1, array['planning']);
    if v_event.id is not null then raise exception 'HIST FAIL: an edit outside its statuses was saved'; end if;
    if (select description from public.events where id = c_e1) <> 'After'
       or (select count(*) from public.event_edit_history where event_id = c_e1) <> 2 then
        raise exception 'HIST FAIL: a refused edit changed the event or wrote history';
    end if;

    -- A field the organiser can't edit is refused outright.
    begin
        perform public.edit_event(c_e1, c_org, '{"status": "planning"}'::jsonb, v_version + 1, array['returned']);
        raise exception 'HIST FAIL: an edit to status was accepted';
    exception when sqlstate '22023' then null;
    end;

    -- ---- TC-HIST-003 (IM-R1 assumption): a draft's edits are saved but not recorded
    select version into v_version from public.events where id = c_e2;
    select * into v_event from public.edit_event(c_e2, c_org, '{"description": "Draft text"}'::jsonb,
        v_version, array['draft']);
    if v_event.id is null then raise exception 'HIST FAIL: the draft edit was not saved'; end if;
    if exists (select 1 from public.event_edit_history where event_id = c_e2) then
        raise exception 'HIST FAIL: a draft edit was recorded';
    end if;

    -- ---- TC-HIST-004 (AC6): no history row can be changed or deleted directly
    insert into public.event_technical_history (event_id, action) values (c_e1, 'note_updated');
    insert into public.event_safety_decisions (event_id, decision) values (c_e1, 'approved');
    insert into public.event_assignment_history (event_id, to_coordinator_id) values
        (c_e1, 'a0000000-0000-4000-8000-000000000002');
    foreach v_table in array array['event_status_history', 'event_assignment_history', 'event_edit_history',
                                    'event_technical_history', 'event_safety_decisions'] loop
        v_refused := false;
        begin
            execute format('update public.%I set event_id = event_id where event_id = $1', v_table) using c_e1;
        exception when sqlstate '55000' then v_refused := true;
        end;
        if not v_refused then raise exception 'HIST FAIL: a row of % was updated', v_table; end if;
        v_refused := false;
        begin
            execute format('delete from public.%I where event_id = $1', v_table) using c_e1;
        exception when sqlstate '55000' then v_refused := true;
        end;
        if not v_refused then raise exception 'HIST FAIL: a row of % was deleted', v_table; end if;
    end loop;
    -- A request is history once decided; an open one still changes when it is decided.
    insert into public.event_change_requests (event_id, kind, reason, status, decided_at)
    values (c_e1, 'cancellation', 'Open request', 'open', null),
           (c_e1, 'cancellation', 'Decided request', 'rejected', now());
    update public.event_change_requests set decision_reason = 'Still open'
     where event_id = c_e1 and status = 'open';
    if not found then raise exception 'HIST FAIL: an open request could not be updated'; end if;
    v_refused := false;
    begin
        update public.event_change_requests set decision_reason = 'Rewritten'
         where event_id = c_e1 and status = 'rejected';
    exception when sqlstate '55000' then v_refused := true;
    end;
    if not v_refused then raise exception 'HIST FAIL: a decided request was updated'; end if;
    v_refused := false;
    begin
        delete from public.event_change_requests where event_id = c_e1 and status = 'rejected';
    exception when sqlstate '55000' then v_refused := true;
    end;
    if not v_refused then raise exception 'HIST FAIL: a decided request was deleted'; end if;

    -- Venue edits belong to a venue, not an event.
    insert into public.venue_edit_history (venue_id, before, after)
    values ('b0000000-0000-4000-8000-000000000001', '{}'::jsonb, '{}'::jsonb);
    v_refused := false;
    begin
        update public.venue_edit_history set after = after where venue_id = 'b0000000-0000-4000-8000-000000000001';
    exception when sqlstate '55000' then v_refused := true;
    end;
    if not v_refused then raise exception 'HIST FAIL: a venue edit was updated'; end if;
    -- A booking's history needs a booking, so check the same trigger is attached;
    -- the behaviour is the trigger function's, proved on the tables above.
    foreach v_table in array array['event_status_history', 'event_assignment_history', 'event_edit_history',
                                    'event_technical_history', 'event_safety_decisions',
                                    'venue_booking_history', 'venue_edit_history'] loop
        if not exists (select 1 from pg_catalog.pg_trigger t
                        where t.tgrelid = format('public.%I', v_table)::regclass
                          and t.tgname = v_table || '_append_only') then
            raise exception 'HIST FAIL: % has no append-only trigger', v_table;
        end if;
    end loop;

    -- ---- TC-HIST-005 (AC6): foreign keys still work: a deleted account nulls out
    -- its actor, and a deleted event takes its own history with it
    insert into public.event_edit_history (event_id, actor_id, field, old_value, new_value)
    values (c_e1, c_temp, 'name', '"A"'::jsonb, '"B"'::jsonb);
    delete from auth.users where id = c_temp;
    perform 1 from public.event_edit_history where event_id = c_e1 and field = 'name' and actor_id is null;
    if not found then raise exception 'HIST FAIL: deleting an account did not null out its history'; end if;

    delete from public.events where id = c_e2;
    if exists (select 1 from public.event_status_history where event_id = c_e2) then
        raise exception 'HIST FAIL: deleting an event left its history behind';
    end if;

    -- ---- TC-HIST-006: the fixture reset's maintenance switch, local to its transaction
    perform set_config('connectsphere.history_maintenance', 'on', true);
    delete from public.event_technical_history where event_id = c_e1;
    perform set_config('connectsphere.history_maintenance', '', true);
    if exists (select 1 from public.event_technical_history where event_id = c_e1) then
        raise exception 'HIST FAIL: the maintenance switch did not allow a delete';
    end if;

    -- Grants (ADR-0006): no signed-in or anonymous user can change history or call the functions.
    foreach v_table in array array['event_status_history', 'event_assignment_history', 'event_edit_history',
                                    'event_technical_history', 'event_safety_decisions',
                                    'venue_booking_history', 'venue_edit_history'] loop
        if has_table_privilege('authenticated', format('public.%I', v_table), 'update, delete')
           or has_table_privilege('anon', format('public.%I', v_table), 'update, delete') then
            raise exception 'HIST FAIL: a signed-in or anonymous user can update or delete %', v_table;
        end if;
    end loop;
    if has_function_privilege('authenticated', 'public.edit_event(uuid, uuid, jsonb, integer, text[])', 'execute')
       or has_function_privilege('anon', 'public.edit_event(uuid, uuid, jsonb, integer, text[])', 'execute')
       or has_function_privilege('authenticated', 'private.record_event_edits(uuid, uuid, jsonb, jsonb)', 'execute') then
        raise exception 'HIST FAIL: a signed-in or anonymous user can execute an edit function';
    end if;
end $$;

-- ---- TC-HIST-007 (AC3, AC4): RLS as a safety net. The owner and the assigned
-- coordinator can read the event's edits directly; another coordinator and
-- tech support can't.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_edit_history where event_id = 'e0000000-0000-4000-8000-0000000062a1') = 0 then
        raise exception 'HIST FAIL: the organiser cannot read their own event''s edits';
    end if;
end $$;
reset role;

select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_edit_history where event_id = 'e0000000-0000-4000-8000-0000000062a1') = 0 then
        raise exception 'HIST FAIL: the assigned coordinator cannot read the edits';
    end if;
end $$;
reset role;

select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000008","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_edit_history where event_id = 'e0000000-0000-4000-8000-0000000062a1') <> 0 then
        raise exception 'HIST FAIL: an unassigned coordinator can read the edits';
    end if;
end $$;
reset role;

select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000004","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_edit_history where event_id = 'e0000000-0000-4000-8000-0000000062a1') <> 0 then
        raise exception 'HIST FAIL: tech support can read the edits';
    end if;
end $$;
reset role;

select 'CHANGE HISTORY CHECKS PASSED' as result;
rollback;
