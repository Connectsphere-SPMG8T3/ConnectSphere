-- 23-R AC1-AC3: real availability function, reference-only location and event bounds.
-- Own throwaway stock, event and reservation only. Always rolled back.
begin;
do $$
declare
    v_id uuid := gen_random_uuid();
    v_free integer;
    v_location text;
    v_row record;
    v_event uuid := gen_random_uuid();
    v_reservation uuid;
    v_line uuid;
begin
    insert into public.equipment (id, name, equipment_type, total_quantity, storage_location)
    values (v_id, '23-R availability check (rolled back)', 'check', 7, 'Store A');
    insert into public.equipment_unavailability (equipment_id, quantity, start_at, end_at, reason)
    values
        (v_id, 2, '2034-01-01 09:00+08', '2034-01-01 12:00+08', 'Faulty units'),
        (v_id, 3, '2034-01-01 07:00+08', '2034-01-01 09:00+08', 'Maintenance before event'),
        (v_id, 4, '2034-01-01 12:00+08', '2034-01-01 14:00+08', 'Maintenance after event');
    select free_quantity into v_free from public.equipment_availability(
        array[v_id], '2034-01-01 09:00+08', '2034-01-01 12:00+08');
    if v_free is distinct from 5 then
        raise exception '23-R FAIL: expected 5 usable during event, got %', v_free;
    end if;
    update public.equipment set storage_location = 'Different venue store' where id = v_id;
    select free_quantity into v_free from public.equipment_availability(
        array[v_id], '2034-01-01 09:00+08', '2034-01-01 12:00+08');
    if v_free is distinct from 5 then
        raise exception '23-R FAIL: changing location changed availability to %', v_free;
    end if;
    update public.equipment set storage_location = null where id = v_id;
    select storage_location into v_location from public.equipment where id = v_id;
    select free_quantity into v_free from public.equipment_availability(
        array[v_id], '2034-01-01 09:00+08', '2034-01-01 12:00+08');
    if v_location is not null or v_free is distinct from 5 then
        raise exception '23-R FAIL: a missing location must be allowed without changing availability';
    end if;
    select free_quantity into v_free from public.equipment_availability(
        array[v_id], '2034-01-02 09:00+08', '2034-01-02 12:00+08');
    if v_free is distinct from 7 then
        raise exception '23-R FAIL: ended condition records still reduce availability';
    end if;
    insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at)
    values (v_event, 'a0000000-0000-4000-8000-000000000001',
            'a0000000-0000-4000-8000-000000000002', 'planning',
            '23-R reservation check (rolled back)', '2034-01-01 09:00+08', '2034-01-01 12:00+08');
    insert into public.equipment_requests (event_id, equipment_id, submission_id, quantity, requested_by)
    values (v_event, v_id, gen_random_uuid(), 3, 'a0000000-0000-4000-8000-000000000002')
    returning id into v_line;
    select * into v_row from public.reserve_equipment_line(v_line, 'a0000000-0000-4000-8000-000000000004');
    if v_row.outcome is distinct from 'ok' then
        raise exception 'D57 FAIL: active stock reservation setup failed: %', v_row;
    end if;
    select id into v_reservation from public.equipment_reservations where request_line_id = v_line;
    update public.equipment set status = 'retired' where id = v_id;
    select * into v_row from public.equipment_availability(
        array[v_id], '2034-01-01 09:00+08', '2034-01-01 12:00+08');
    if v_row.free_quantity is distinct from 0 then
        raise exception 'D57 FAIL: retired stock must have 0 free units, got %', v_row.free_quantity;
    end if;
    if v_row.total_quantity is distinct from 7 or v_row.outage_quantity is distinct from 2
        or v_row.reserved_quantity is distinct from 3 then
        raise exception 'D57 FAIL: retirement must preserve stock and commitment counters';
    end if;
    if not exists (select 1 from public.equipment_reservations
                   where id = v_reservation and status = 'confirmed' and quantity = 3) then
        raise exception 'D57 FAIL: retirement must not release the existing reservation';
    end if;
    select * into v_row from public.equipment_availability(
        array[v_id], '2034-01-01 09:00+08', '2034-01-01 12:00+08', v_reservation);
    if v_row.free_quantity is distinct from 0 or v_row.reserved_quantity is distinct from 0 then
        raise exception 'D57 FAIL: excluding a reservation must not make retired stock usable';
    end if;
    update public.events set starts_at = '2034-01-01 09:30+08', ends_at = '2034-01-01 12:30+08'
    where id = v_event;
    select * into v_row from public.recheck_event_reservations(v_event, 'a0000000-0000-4000-8000-000000000002');
    if v_row.outcome is distinct from 'ok' or v_row.flagged is distinct from 1
        or (select status::text from public.equipment_requests where id = v_line) is distinct from 're_review'
        or not exists (select 1 from public.equipment_reservations where id = v_reservation
                       and status = 'confirmed' and quantity = 3 and start_at = '2034-01-01 09:30+08') then
        raise exception 'D57 FAIL: time change must flag retired stock for re-review while retaining the hold';
    end if;
    select * into v_row from public.reserve_equipment_line(v_line, 'a0000000-0000-4000-8000-000000000004');
    if v_row.outcome is distinct from 'insufficient' or v_row.free_quantity is distinct from 0 then
        raise exception 'D57 FAIL: retired stock cannot be re-reserved: %', v_row;
    end if;
    delete from public.equipment_reservations where id = v_reservation;
    update public.equipment set status = 'maintenance' where id = v_id;
    select free_quantity into v_free from public.equipment_availability(
        array[v_id], '2034-01-01 09:00+08', '2034-01-01 12:00+08');
    if v_free is distinct from 5 then
        raise exception 'D57 FAIL: partial maintenance must still use timed outage quantities';
    end if;
    update public.equipment set status = 'active' where id = v_id;
    select free_quantity into v_free from public.equipment_availability(
        array[v_id], '2034-01-02 09:00+08', '2034-01-02 12:00+08');
    if v_free is distinct from 7 then
        raise exception 'D57 FAIL: restored active stock must have 7 free units';
    end if;
end $$;
rollback;
