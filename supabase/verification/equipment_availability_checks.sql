-- 23-R AC1-AC3: real availability function, reference-only location and event bounds.
-- Throwaway stock only, with no reservations required. Always rolled back.
begin;
do $$
declare
    v_id uuid := gen_random_uuid();
    v_free integer;
    v_location text;
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
end $$;
rollback;
