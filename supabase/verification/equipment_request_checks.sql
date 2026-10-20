-- SCRUM-45 equipment request lines: the real function, table constraints and RLS.
-- Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`. Raises on
-- the first failure and prints EQUIPMENT REQUEST CHECKS PASSED otherwise.
-- Everything runs inside `begin; ... rollback;`, so the throwaway events,
-- equipment and lines leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002, who also holds
-- venue_staff), venue staff (…0003), tech support (…0004) and the seeded
-- 4K Projector (b…0001, 14 in total) and Wireless Mics (b…0002).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-0000000007a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Equipment check (rolled back)',
     now() + interval '30 days', now() + interval '30 days 3 hours'),
    ('e0000000-0000-4000-8000-0000000007a2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'returned', 'Equipment check, returned (rolled back)',
     now() + interval '30 days', now() + interval '30 days 3 hours'),
    ('e0000000-0000-4000-8000-0000000007a3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Equipment check, confirmed (rolled back)',
     now() + interval '30 days', now() + interval '30 days 3 hours'),
    ('e0000000-0000-4000-8000-0000000007a4', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'draft', 'Equipment check, draft (rolled back)',
     null, null);

insert into public.equipment (id, name, equipment_type, total_quantity, status) values
    ('b0000000-0000-4000-8000-0000000007f1', 'Retired check item (rolled back)', 'check', 1, 'retired');

do $$
declare
    v_event uuid := 'e0000000-0000-4000-8000-0000000007a1';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_projector uuid := 'b0000000-0000-4000-8000-000000000001';
    v_mics uuid := 'b0000000-0000-4000-8000-000000000002';
    v_outcome text;
    v_lines jsonb;
    v_rows integer;
begin
    -- TC-EQR-006: two lines saved together, pending, sharing one submission;
    -- 5 projectors is above the 4 that exist and is still accepted (EQ-R1).
    select outcome, lines into v_outcome, v_lines from public.submit_equipment_request(
        v_event, v_coordinator,
        jsonb_build_array(
            jsonb_build_object('equipment_id', v_projector, 'quantity', 5, 'technical_requirements', '  HDMI  '),
            jsonb_build_object('equipment_id', v_mics, 'quantity', 2, 'technical_requirements', '   ')
        ));
    if v_outcome is distinct from 'ok' or jsonb_array_length(v_lines) <> 2 then
        raise exception 'EQR FAIL: a valid submission returned % with % lines', v_outcome, jsonb_array_length(v_lines);
    end if;
    select count(*) into v_rows from public.equipment_requests
     where event_id = v_event and status = 'pending' and requested_by = v_coordinator;
    if v_rows <> 2 then raise exception 'EQR FAIL: the lines were not stored as pending with their requester'; end if;
    select count(distinct submission_id) into v_rows from public.equipment_requests where event_id = v_event;
    if v_rows <> 1 then raise exception 'EQR FAIL: one submission produced % submission ids', v_rows; end if;
    if (select technical_requirements from public.equipment_requests where event_id = v_event and equipment_id = v_projector)
       is distinct from 'HDMI' then
        raise exception 'EQR FAIL: technical requirements were not trimmed';
    end if;
    if (select technical_requirements from public.equipment_requests where event_id = v_event and equipment_id = v_mics)
       is not null then
        raise exception 'EQR FAIL: blank technical requirements were not stored as null';
    end if;

    -- TC-EQR-007: all or none. A batch with one bad line writes nothing.
    select outcome into v_outcome from public.submit_equipment_request(
        v_event, v_coordinator,
        jsonb_build_array(
            jsonb_build_object('equipment_id', v_projector, 'quantity', 1),
            jsonb_build_object('equipment_id', 'b0000000-0000-4000-8000-0000000007ff', 'quantity', 1)
        ));
    if v_outcome is distinct from 'unknown_equipment' then raise exception 'EQR FAIL: an unknown item gave %', v_outcome; end if;
    select outcome into v_outcome from public.submit_equipment_request(
        v_event, v_coordinator,
        jsonb_build_array(jsonb_build_object('equipment_id', 'b0000000-0000-4000-8000-0000000007f1', 'quantity', 1)));
    if v_outcome is distinct from 'unknown_equipment' then raise exception 'EQR FAIL: a retired item gave %', v_outcome; end if;
    begin
        perform public.submit_equipment_request(
            v_event, v_coordinator,
            jsonb_build_array(
                jsonb_build_object('equipment_id', v_projector, 'quantity', 1),
                jsonb_build_object('equipment_id', v_mics, 'quantity', 0)
            ));
        raise exception 'EQR FAIL: a quantity of 0 was accepted';
    exception when check_violation then null;
    end;
    select count(*) into v_rows from public.equipment_requests where event_id = v_event;
    if v_rows <> 2 then raise exception 'EQR FAIL: a refused batch left % extra lines', v_rows - 2; end if;

    -- TC-EQR-008: only the assigned coordinator, only in planning.
    select outcome into v_outcome from public.submit_equipment_request(
        v_event, 'a0000000-0000-4000-8000-000000000003',
        jsonb_build_array(jsonb_build_object('equipment_id', v_projector, 'quantity', 1)));
    if v_outcome is distinct from 'not_assigned' then raise exception 'EQR FAIL: another account gave %', v_outcome; end if;
    select outcome into v_outcome from public.submit_equipment_request(
        'e0000000-0000-4000-8000-0000000007a2', v_coordinator,
        jsonb_build_array(jsonb_build_object('equipment_id', v_projector, 'quantity', 1)));
    if v_outcome is distinct from 'returned' then raise exception 'EQR FAIL: a returned event gave %', v_outcome; end if;
    select outcome into v_outcome from public.submit_equipment_request(
        'e0000000-0000-4000-8000-0000000007a3', v_coordinator,
        jsonb_build_array(jsonb_build_object('equipment_id', v_projector, 'quantity', 1)));
    if v_outcome is distinct from 'not_planning' then raise exception 'EQR FAIL: a confirmed event gave %', v_outcome; end if;
    select outcome into v_outcome from public.submit_equipment_request(
        'e0000000-0000-4000-8000-0000000007a4', v_coordinator,
        jsonb_build_array(jsonb_build_object('equipment_id', v_projector, 'quantity', 1)));
    if v_outcome is distinct from 'event_not_found' then raise exception 'EQR FAIL: a draft gave %', v_outcome; end if;
    select outcome into v_outcome from public.submit_equipment_request(v_event, v_coordinator, '[]'::jsonb);
    if v_outcome is distinct from 'no_items' then raise exception 'EQR FAIL: an empty submission gave %', v_outcome; end if;
    select count(*) into v_rows from public.equipment_requests
     where event_id in ('e0000000-0000-4000-8000-0000000007a2', 'e0000000-0000-4000-8000-0000000007a3',
                        'e0000000-0000-4000-8000-0000000007a4');
    if v_rows <> 0 then raise exception 'EQR FAIL: a refused event stored lines'; end if;

    -- The table refuses an overlong technical requirement by itself.
    begin
        insert into public.equipment_requests (event_id, equipment_id, submission_id, quantity, technical_requirements)
        values (v_event, v_projector, gen_random_uuid(), 1, repeat('x', 1001));
        raise exception 'EQR FAIL: a 1001-character technical requirement was accepted';
    exception when check_violation then null;
    end;

    -- API-only: not callable by signed-in users.
    if has_function_privilege('authenticated', 'public.submit_equipment_request(uuid, uuid, jsonb)', 'execute') then
        raise exception 'EQR FAIL: authenticated can execute submit_equipment_request';
    end if;
end $$;

-- RLS: the assigned coordinator, acting as coordinator, reads the lines; cannot write.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
declare v_rows integer;
begin
    if (select count(*) from public.equipment_requests where event_id = 'e0000000-0000-4000-8000-0000000007a1') <> 2 then
        raise exception 'EQR FAIL: the assigned coordinator cannot read the lines';
    end if;
    update public.equipment_requests set quantity = 99 where event_id = 'e0000000-0000-4000-8000-0000000007a1';
    get diagnostics v_rows = row_count;
    if v_rows <> 0 then raise exception 'EQR FAIL: the coordinator edited a line directly'; end if;
end $$;
reset role;

-- RLS: tech support read every line (a pool, AUTH-R5).
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000004","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.equipment_requests where event_id = 'e0000000-0000-4000-8000-0000000007a1') <> 2 then
        raise exception 'EQR FAIL: tech support cannot read the lines';
    end if;
end $$;
reset role;

-- RLS: the same coordinator account, in a session acting as venue staff, sees nothing (SCRUM-76).
insert into auth.sessions (id, user_id, created_at, updated_at)
values ('c0000000-0000-4000-8000-0000000007c1', 'a0000000-0000-4000-8000-000000000002', now(), now());
insert into public.session_active_roles (session_id, profile_id, role)
values ('c0000000-0000-4000-8000-0000000007c1', 'a0000000-0000-4000-8000-000000000002', 'venue_staff');
select set_config('request.jwt.claims',
    '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated","session_id":"c0000000-0000-4000-8000-0000000007c1"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.equipment_requests where event_id = 'e0000000-0000-4000-8000-0000000007a1') <> 0 then
        raise exception 'EQR FAIL: the coordinator acting as venue staff can read the lines';
    end if;
end $$;
reset role;

-- RLS: the organiser sees nothing.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.equipment_requests where event_id = 'e0000000-0000-4000-8000-0000000007a1') <> 0 then
        raise exception 'EQR FAIL: the organiser can read the lines';
    end if;
end $$;
reset role;

select 'EQUIPMENT REQUEST CHECKS PASSED' as result;
rollback;
