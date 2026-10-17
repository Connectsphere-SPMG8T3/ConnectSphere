-- CR-95 AC5: when a replacement booking is approved, the booking it replaces
-- is released and the history records both. release_replaced_booking is what
-- story 36's approve calls once it exists; here it is called directly.
-- Run with the Supabase MCP execute_sql, `supabase db query --linked -f`, or
-- `psql "$DATABASE_URL" -f`. Raises on the first failure and prints
-- VENUE RELEASE CHECKS PASSED otherwise. Everything runs inside
-- `begin; ... rollback;`, so nothing here leaves a trace.
-- Uses the seeded organiser (…0001), coordinator (…0002), venue staff (…0003),
-- Seminar Room 1 (b0000000-…0003, the affected venue) and Grand Ballroom
-- (b0000000-…0001, the replacement).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, expected_attendance, starts_at, ends_at)
values
    ('e0000000-0000-4000-8000-0000000095b1', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Release check (rolled back)', 20, '2031-10-01 10:00+08', '2031-10-01 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095b2', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Release check plain (rolled back)', 20, '2031-10-02 10:00+08', '2031-10-02 12:00+08');

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status)
values
    ('d0000000-0000-4000-8000-0000000095a1', 'e0000000-0000-4000-8000-0000000095b1', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-10-01 10:00+08', '2031-10-01 12:00+08', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000095a3', 'e0000000-0000-4000-8000-0000000095b2', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-10-02 10:00+08', '2031-10-02 12:00+08', '[)'), 'approved');

update public.venue_bookings
   set flag = 'affected', flag_reason = 'Venue unavailable: maintenance', flagged_at = now()
 where id = 'd0000000-0000-4000-8000-0000000095a1';

-- The replacement, held first and approved later by staff.
insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, replaces_booking_id)
values ('d0000000-0000-4000-8000-0000000095a2', 'e0000000-0000-4000-8000-0000000095b1', 'b0000000-0000-4000-8000-000000000001',
        tstzrange('2031-10-01 10:00+08', '2031-10-01 12:00+08', '[)'), 'held',
        'd0000000-0000-4000-8000-0000000095a1');

do $$
declare
    v_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_original uuid := 'd0000000-0000-4000-8000-0000000095a1';
    v_replacement uuid := 'd0000000-0000-4000-8000-0000000095a2';
    v_outcome text;
    v_released uuid;
    v_rows integer;
begin
    -- A replacement that is still a hold releases nothing.
    select outcome into v_outcome from public.release_replaced_booking(v_replacement, v_staff);
    if v_outcome <> 'not_approved' then raise exception 'RELEASE FAIL: a held replacement gave %', v_outcome; end if;
    if (select status::text from public.venue_bookings where id = v_original) <> 'approved' then
        raise exception 'RELEASE FAIL: a held replacement released the original';
    end if;

    -- A booking that replaces nothing, and one that does not exist.
    select outcome into v_outcome from public.release_replaced_booking('d0000000-0000-4000-8000-0000000095a3', v_staff);
    if v_outcome <> 'not_a_replacement' then raise exception 'RELEASE FAIL: a plain booking gave %', v_outcome; end if;
    select outcome into v_outcome from public.release_replaced_booking('d0000000-0000-4000-8000-0000000095ff', v_staff);
    if v_outcome <> 'booking_not_found' then raise exception 'RELEASE FAIL: an unknown booking gave %', v_outcome; end if;

    -- Approved: the original is released.
    update public.venue_bookings set status = 'approved' where id = v_replacement;
    select outcome, released_booking_id into v_outcome, v_released from public.release_replaced_booking(v_replacement, v_staff);
    if v_outcome <> 'ok' or v_released is distinct from v_original then
        raise exception 'RELEASE FAIL: approving the replacement gave % / %', v_outcome, v_released;
    end if;
    if (select status::text from public.venue_bookings where id = v_original) <> 'released' then
        raise exception 'RELEASE FAIL: the original is not released';
    end if;
    if (select status::text from public.venue_bookings where id = v_replacement) <> 'approved' then
        raise exception 'RELEASE FAIL: releasing the original changed the replacement';
    end if;

    -- The history records both, with who did it.
    select count(*) into v_rows from public.venue_booking_history
     where booking_id = v_original and action = 'released_for_replacement'
       and from_status = 'approved' and to_status = 'released' and actor_id = v_staff;
    if v_rows <> 1 then raise exception 'RELEASE FAIL: expected one release row on the original, got %', v_rows; end if;
    select count(*) into v_rows from public.venue_booking_history
     where booking_id = v_replacement and action = 'replacement_approved' and actor_id = v_staff;
    if v_rows <> 1 then raise exception 'RELEASE FAIL: expected one row on the replacement, got %', v_rows; end if;

    -- Asking again changes nothing.
    select outcome into v_outcome from public.release_replaced_booking(v_replacement, v_staff);
    if v_outcome <> 'already_released' then raise exception 'RELEASE FAIL: a second release gave %', v_outcome; end if;
    select count(*) into v_rows from public.venue_booking_history where booking_id in (v_original, v_replacement);
    if v_rows <> 2 then raise exception 'RELEASE FAIL: a second release wrote history (% rows)', v_rows; end if;

    -- Only the service role can run it.
    if has_function_privilege('anon', 'public.release_replaced_booking(uuid, uuid)', 'execute')
       or has_function_privilege('authenticated', 'public.release_replaced_booking(uuid, uuid)', 'execute')
       or not has_function_privilege('service_role', 'public.release_replaced_booking(uuid, uuid)', 'execute') then
        raise exception 'RELEASE FAIL: release_replaced_booking is callable by a role other than service_role';
    end if;
end $$;

select 'VENUE RELEASE CHECKS PASSED' as result;

rollback;
