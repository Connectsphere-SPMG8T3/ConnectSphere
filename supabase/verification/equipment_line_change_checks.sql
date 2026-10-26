-- SCRUM-44 modify or remove equipment requirements: the real functions, triggers,
-- history and notices. Run with `supabase db query --linked -f` (verify_live.py
-- does). Raises on the first failure and prints EQUIPMENT LINE CHANGE CHECKS
-- PASSED otherwise. Everything runs inside `begin; ... rollback;`, so the
-- throwaway events, equipment, lines, reservations and notices leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002) and tech support
-- (…0004). Every throwaway event is dated 2033-05 so it overlaps nothing seeded
-- or left by a live check.
-- The race in AC6 needs two connections; here each function is shown to refuse
-- a line whose status moved since the coordinator saw it, which is what settles
-- the race once the lock is released (verify_live.py's TC-EQR-050).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-0000000009a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Line change check E1 (rolled back)',
     '2033-05-01 09:00+08', '2033-05-01 12:00+08'),
    -- E2 overlaps E1, to see a removed reservation's units come back.
    ('e0000000-0000-4000-8000-0000000009a2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Line change check E2 (rolled back)',
     '2033-05-01 10:00+08', '2033-05-01 13:00+08'),
    -- E3 leaves Planning later.
    ('e0000000-0000-4000-8000-0000000009a3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Line change check E3 (rolled back)',
     '2033-05-02 09:00+08', '2033-05-02 12:00+08');

insert into public.equipment (id, name, equipment_type, total_quantity, status) values
    ('b0000000-0000-4000-8000-0000000009f1', 'Line change check X (rolled back)', 'check', 5, 'active'),
    ('b0000000-0000-4000-8000-0000000009f2', 'Line change check Y (rolled back)', 'check', 5, 'active'),
    ('b0000000-0000-4000-8000-0000000009f3', 'Line change check R (rolled back)', 'check', 5, 'retired');

do $$
declare
    c_tech constant uuid := 'a0000000-0000-4000-8000-000000000004';
    c_coord constant uuid := 'a0000000-0000-4000-8000-000000000002';
    c_stranger constant uuid := 'a0000000-0000-4000-8000-0000000009ff';
    c_x constant uuid := 'b0000000-0000-4000-8000-0000000009f1';
    c_y constant uuid := 'b0000000-0000-4000-8000-0000000009f2';
    c_retired constant uuid := 'b0000000-0000-4000-8000-0000000009f3';
    c_e1 constant uuid := 'e0000000-0000-4000-8000-0000000009a1';
    c_e2 constant uuid := 'e0000000-0000-4000-8000-0000000009a2';
    c_e3 constant uuid := 'e0000000-0000-4000-8000-0000000009a3';
    v_pending uuid; v_reserved uuid; v_rejected uuid; v_e2 uuid; v_e3 uuid;
    v_outcome text;
    v_status text;
    v_free integer;
    v_left boolean;
    v_count integer;
    v_line public.equipment_requests;
    v_reservation public.equipment_reservations;
    v_history public.event_technical_history;
    v_tech public.technical_readiness;
begin
    -- Three lines on E1, one each on E2 and E3, through SCRUM-45's submit.
    select (r.lines -> 0 ->> 'id')::uuid, (r.lines -> 1 ->> 'id')::uuid
      into v_pending, v_reserved
      from public.submit_equipment_request(c_e1, c_coord, jsonb_build_array(
          jsonb_build_object('equipment_id', c_x, 'quantity', 1, 'technical_requirements', 'HDMI'),
          jsonb_build_object('equipment_id', c_y, 'quantity', 3))) r;
    -- A later submission, as the coordinator would add it.
    select (r.lines -> 0 ->> 'id')::uuid into v_rejected from public.submit_equipment_request(
        c_e1, c_coord, jsonb_build_array(jsonb_build_object('equipment_id', c_x, 'quantity', 2))) r;
    select (r.lines -> 0 ->> 'id')::uuid into v_e2 from public.submit_equipment_request(
        c_e2, c_coord, jsonb_build_array(jsonb_build_object('equipment_id', c_y, 'quantity', 2))) r;
    select (r.lines -> 0 ->> 'id')::uuid into v_e3 from public.submit_equipment_request(
        c_e3, c_coord, jsonb_build_array(jsonb_build_object('equipment_id', c_x, 'quantity', 1))) r;
    if v_pending is null or v_reserved is null or v_rejected is null or v_e2 is null or v_e3 is null then
        raise exception 'EQLC FAIL: setup could not submit the lines';
    end if;
    select r.outcome into v_outcome from public.reserve_equipment_line(v_reserved, c_tech) r;
    if v_outcome <> 'ok' then raise exception 'EQLC FAIL: setup reserve gave %', v_outcome; end if;
    select r.outcome into v_outcome from public.mark_equipment_line_not_available(v_rejected, c_tech, 'Lent out') r;
    if v_outcome <> 'ok' then raise exception 'EQLC FAIL: setup not-available gave %', v_outcome; end if;

    -- ---- TC-EQR-044 (AC2, AC3, AC8): a Pending line stays Pending; nobody is told
    delete from public.notifications where event_id = c_e1;
    select r.outcome, r.line_status into v_outcome, v_status
      from public.update_equipment_line(v_pending, c_coord, c_x, 2, '  HDMI and VGA  ', 'pending') r;
    if v_outcome <> 'ok' or v_status <> 'pending' then
        raise exception 'EQLC FAIL: editing a pending line gave % / %', v_outcome, v_status;
    end if;
    select * into v_line from public.equipment_requests where id = v_pending;
    if v_line.quantity <> 2 or v_line.technical_requirements <> 'HDMI and VGA' then
        raise exception 'EQLC FAIL: the edit was not saved trimmed (%, %)', v_line.quantity, v_line.technical_requirements;
    end if;
    select * into v_history from public.event_technical_history
     where request_id = v_pending and action = 'edited' order by created_at desc limit 1;
    if v_history.id is null or v_history.actor_id <> c_coord
       or v_history.from_status <> 'pending' or v_history.to_status <> 'pending'
       or v_history.detail not like '%Quantity: 1 → 2%'
       or v_history.detail not like '%Technical requirements: "HDMI" → "HDMI and VGA"%' then
        raise exception 'EQLC FAIL: the edit history is wrong: %', row_to_json(v_history);
    end if;
    if exists (select 1 from public.notifications where event_id = c_e1) then
        raise exception 'EQLC FAIL: editing a pending line told someone';
    end if;

    -- Nothing changed: no write, no history.
    select count(*) into v_count from public.event_technical_history where request_id = v_pending;
    select r.outcome into v_outcome
      from public.update_equipment_line(v_pending, c_coord, c_x, 2, 'HDMI and VGA', 'pending') r;
    if v_outcome <> 'unchanged'
       or (select count(*) from public.event_technical_history where request_id = v_pending) <> v_count then
        raise exception 'EQLC FAIL: an edit with no change gave % or wrote history', v_outcome;
    end if;

    -- ---- TC-EQR-045 (AC3, AC5): a Reserved line goes to re-review and keeps its reservation
    update public.events set exit_confirmed_by = c_tech, exit_confirmed_at = now() where id = c_e1;
    select r.outcome, r.line_status into v_outcome, v_status
      from public.update_equipment_line(v_reserved, c_coord, c_y, 4, null, 'reserved') r;
    if v_outcome <> 'ok' or v_status <> 're_review' then
        raise exception 'EQLC FAIL: editing a reserved line gave % / %', v_outcome, v_status;
    end if;
    select * into v_reservation from public.equipment_reservations
     where request_line_id = v_reserved and status = 'confirmed';
    if v_reservation.id is null or v_reservation.quantity <> 3 then
        raise exception 'EQLC FAIL: the reservation did not keep its old quantity (%)', v_reservation.quantity;
    end if;
    if (select exit_confirmed_at from public.events where id = c_e1) is not null then
        raise exception 'EQLC FAIL: changing a quantity did not clear the exit tick';
    end if;
    if not exists (select 1 from public.notifications n join public.user_roles ur on ur.profile_id = n.recipient_id
                    where n.event_id = c_e1 and n.type = 'equipment_line_changed' and ur.role = 'tech_support') then
        raise exception 'EQLC FAIL: tech support were not told of the change to a reserved line';
    end if;
    if exists (select 1 from public.notifications where event_id = c_e1 and recipient_id = c_coord) then
        raise exception 'EQLC FAIL: the coordinator was told of their own change';
    end if;
    -- Only the changed line moved.
    if (select status from public.equipment_requests where id = v_pending) <> 'pending'
       or (select status from public.equipment_requests where id = v_e2) <> 'pending' then
        raise exception 'EQLC FAIL: other lines changed status';
    end if;

    -- ---- TC-EQR-053 (AC3): re-reserving a line whose item changed moves the reservation
    select r.outcome, r.line_status into v_outcome, v_status
      from public.update_equipment_line(v_reserved, c_coord, c_x, 2, null, 're_review') r;
    if v_outcome <> 'ok' or v_status <> 're_review' then
        raise exception 'EQLC FAIL: editing a re-review line gave % / %', v_outcome, v_status;
    end if;
    if (select equipment_id from public.equipment_reservations
         where request_line_id = v_reserved and status = 'confirmed') <> c_y then
        raise exception 'EQLC FAIL: changing the item moved the reservation before tech support decided';
    end if;
    select r.outcome into v_outcome from public.reserve_equipment_line(v_reserved, c_tech) r;
    select * into v_reservation from public.equipment_reservations
     where request_line_id = v_reserved and status = 'confirmed';
    if v_outcome <> 'ok' or v_reservation.equipment_id <> c_x or v_reservation.quantity <> 2 then
        raise exception 'EQLC FAIL: re-reserving gave % holding % × %', v_outcome, v_reservation.quantity, v_reservation.equipment_id;
    end if;
    if (select count(*) from public.equipment_reservations where request_line_id = v_reserved and status = 'confirmed') <> 1 then
        raise exception 'EQLC FAIL: a line holds more than one reservation';
    end if;

    -- ---- TC-EQR-046 (AC3): a Not available line returns to Pending, its reason cleared
    delete from public.notifications where event_id = c_e1;
    select r.outcome, r.line_status into v_outcome, v_status
      from public.update_equipment_line(v_rejected, c_coord, c_x, 1, null, 'rejected') r;
    if v_outcome <> 'ok' or v_status <> 'pending'
       or (select not_available_reason from public.equipment_requests where id = v_rejected) is not null then
        raise exception 'EQLC FAIL: editing a not-available line gave % / % or kept its reason', v_outcome, v_status;
    end if;
    if not exists (select 1 from public.notifications where event_id = c_e1 and type = 'equipment_line_changed') then
        raise exception 'EQLC FAIL: tech support were not told a not-available line changed';
    end if;

    -- ---- TC-EQR-050 (AC6): a status that moved since the coordinator saw it refuses both
    select r.outcome into v_outcome
      from public.update_equipment_line(v_reserved, c_coord, c_x, 1, null, 'pending') r;
    if v_outcome <> 'stale' then raise exception 'EQLC FAIL: a stale edit gave %', v_outcome; end if;
    if public.remove_equipment_line(v_reserved, c_coord, 'pending') <> 'stale' then
        raise exception 'EQLC FAIL: a stale removal was not refused';
    end if;

    -- ---- TC-EQR-051 (AC7): only the assigned coordinator
    select r.outcome into v_outcome
      from public.update_equipment_line(v_pending, c_stranger, c_x, 3, null, 'pending') r;
    if v_outcome <> 'not_assigned' or public.remove_equipment_line(v_pending, c_tech, 'pending') <> 'not_assigned' then
        raise exception 'EQLC FAIL: someone other than the assigned coordinator could change a line';
    end if;

    -- AC2: a retired item can't be chosen.
    select r.outcome into v_outcome
      from public.update_equipment_line(v_pending, c_coord, c_retired, 1, null, 'pending') r;
    if v_outcome <> 'unknown_equipment' then raise exception 'EQLC FAIL: a retired item gave %', v_outcome; end if;

    -- ---- TC-EQR-048 (AC1, AC5): removing a reserved line frees its units and tells tech support
    select a.free_quantity into v_free
      from public.equipment_availability(array[c_x], '2033-05-01 10:00+08', '2033-05-01 13:00+08') a;
    update public.events set exit_confirmed_by = c_tech, exit_confirmed_at = now() where id = c_e1;
    delete from public.notifications where event_id = c_e1;
    if public.remove_equipment_line(v_reserved, c_coord, 'reserved') <> 'ok' then
        raise exception 'EQLC FAIL: removing a reserved line was refused';
    end if;
    if (select status from public.equipment_requests where id = v_reserved) <> 'released' then
        raise exception 'EQLC FAIL: a removed line is not released';
    end if;
    if exists (select 1 from public.equipment_reservations where request_line_id = v_reserved and status = 'confirmed') then
        raise exception 'EQLC FAIL: a removed line still holds its reservation';
    end if;
    if (select a.free_quantity from public.equipment_availability(array[c_x], '2033-05-01 10:00+08', '2033-05-01 13:00+08') a)
       <> v_free + 2 then
        raise exception 'EQLC FAIL: the removed line''s 2 units did not return to availability';
    end if;
    if (select exit_confirmed_at from public.events where id = c_e1) is not null then
        raise exception 'EQLC FAIL: removing a line did not clear the exit tick';
    end if;
    if not exists (select 1 from public.notifications where event_id = c_e1 and type = 'equipment_line_removed') then
        raise exception 'EQLC FAIL: tech support were not told a reserved line was removed';
    end if;
    select * into v_history from public.event_technical_history
     where request_id = v_reserved and action = 'removed';
    if v_history.id is null or v_history.from_status <> 'reserved' or v_history.to_status <> 'released'
       or v_history.actor_id <> c_coord or v_history.detail not like 'Removed 2 × Line change check X%' then
        raise exception 'EQLC FAIL: the removal history is wrong: %', row_to_json(v_history);
    end if;

    -- AC6: reserving a removed line is refused; it can't be changed or removed again.
    select r.outcome into v_outcome from public.reserve_equipment_line(v_reserved, c_tech) r;
    if v_outcome <> 'not_reservable' then raise exception 'EQLC FAIL: reserving a removed line gave %', v_outcome; end if;
    select r.outcome into v_outcome
      from public.update_equipment_line(v_reserved, c_coord, c_x, 1, null, 'released') r;
    if v_outcome <> 'stale' or public.remove_equipment_line(v_reserved, c_coord, 'released') <> 'stale' then
        raise exception 'EQLC FAIL: a removed line could be changed or removed again';
    end if;

    -- ---- TC-EQR-047 (AC1, AC5): pending lines are simply removed; the last one makes it Not required
    delete from public.notifications where event_id = c_e1;
    if public.remove_equipment_line(v_pending, c_coord, 'pending') <> 'ok'
       or public.remove_equipment_line(v_rejected, c_coord, 'pending') <> 'ok' then
        raise exception 'EQLC FAIL: removing pending lines was refused';
    end if;
    if exists (select 1 from public.notifications where event_id = c_e1) then
        raise exception 'EQLC FAIL: removing a pending line told someone';
    end if;
    select technical_readiness into v_tech from public.events where id = c_e1;
    if v_tech <> 'not_required' then
        raise exception 'EQLC FAIL: removing the last line left technical status %', v_tech;
    end if;
    -- E2's line was never touched.
    if (select status from public.equipment_requests where id = v_e2) <> 'pending' then
        raise exception 'EQLC FAIL: another event''s line changed';
    end if;

    -- A Not available line can be removed (AC1).
    select r.outcome into v_outcome from public.mark_equipment_line_not_available(v_e2, c_tech, 'None left') r;
    if public.remove_equipment_line(v_e2, c_coord, 'rejected') <> 'ok' then
        raise exception 'EQLC FAIL: removing a not-available line was refused';
    end if;

    -- ---- TC-EQR-049 (AC4): only while the event is in Planning
    update public.events set status = 'safety_review' where id = c_e3;
    select r.outcome into v_outcome
      from public.update_equipment_line(v_e3, c_coord, c_x, 2, null, 'pending') r;
    if v_outcome <> 'not_planning' or public.remove_equipment_line(v_e3, c_coord, 'pending') <> 'not_planning' then
        raise exception 'EQLC FAIL: a line outside Planning could be changed (%)', v_outcome;
    end if;
    if (select quantity from public.equipment_requests where id = v_e3) <> 1 then
        raise exception 'EQLC FAIL: a refused edit still wrote the line';
    end if;

    -- An unknown line.
    select r.outcome into v_outcome
      from public.update_equipment_line(gen_random_uuid(), c_coord, c_x, 1, null, 'pending') r;
    if v_outcome <> 'line_not_found' or public.remove_equipment_line(gen_random_uuid(), c_coord, 'pending') <> 'line_not_found' then
        raise exception 'EQLC FAIL: an unknown line gave %', v_outcome;
    end if;
end $$;

-- ---- TC-EQR-051 (AC7): the functions are API-only
do $$
begin
    if has_function_privilege('authenticated', 'public.update_equipment_line(uuid, uuid, uuid, integer, text, text)', 'execute')
       or has_function_privilege('authenticated', 'public.remove_equipment_line(uuid, uuid, text)', 'execute')
       or has_function_privilege('anon', 'public.remove_equipment_line(uuid, uuid, text)', 'execute') then
        raise exception 'EQLC FAIL: a signed-in or anonymous client can call the line change functions';
    end if;
end $$;

-- ---- TC-EQR-052 (AC8): the assigned coordinator, acting as coordinator, reads the
-- history, where the removed line is still named.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if not exists (select 1 from public.event_technical_history h
                     join public.equipment_requests r on r.id = h.request_id
                    where h.event_id = 'e0000000-0000-4000-8000-0000000009a1' and h.action = 'removed') then
        raise exception 'EQLC FAIL: the coordinator cannot read a removed line in the history';
    end if;
end $$;
reset role;

select 'EQUIPMENT LINE CHANGE CHECKS PASSED' as result;
rollback;
