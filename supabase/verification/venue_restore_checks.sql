-- CR-95 AC9: when the original venue is free again for the booking's full
-- occupied window before a replacement is approved, venue staff can restore
-- the original booking. Its Affected flag is cleared and a pending replacement
-- request is cancelled. restore_affected_booking refuses while a block still
-- covers the window, while the venue is inactive, and once a replacement is
-- approved.
-- Run with the Supabase MCP execute_sql, `supabase db query --linked -f`, or
-- `psql "$DATABASE_URL" -f`. Raises on the first failure and prints
-- VENUE RESTORE CHECKS PASSED otherwise. Everything runs inside
-- `begin; ... rollback;`, so nothing here leaves a trace.
-- Uses the seeded organiser (…0001), coordinator (…0002), venue staff (…0003),
-- Seminar Room 1 (b0000000-…0003, the original venue) and Innovation Lab
-- (b0000000-…0001, the replacement venue).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, expected_attendance, starts_at, ends_at)
values
    ('e0000000-0000-4000-8000-0000000095c1', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Restore check pending (rolled back)', 20, '2031-11-01 10:00+08', '2031-11-01 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095c2', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Restore check approved replacement (rolled back)', 20, '2031-11-02 10:00+08', '2031-11-02 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095c3', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Restore check unflagged (rolled back)', 20, '2031-11-03 10:00+08', '2031-11-03 12:00+08');

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status)
values
    ('d0000000-0000-4000-8000-0000000095c1', 'e0000000-0000-4000-8000-0000000095c1', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-11-01 10:00+08', '2031-11-01 12:00+08', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000095c2', 'e0000000-0000-4000-8000-0000000095c2', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-11-02 10:00+08', '2031-11-02 12:00+08', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000095c3', 'e0000000-0000-4000-8000-0000000095c3', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-11-03 10:00+08', '2031-11-03 12:00+08', '[)'), 'approved');

-- A block over the first two days flags their bookings (the trigger), the way
-- it happens for real.
insert into public.venue_blocks (id, venue_id, blocked_period, reason)
values ('f0000000-0000-4000-8000-0000000095c1', 'b0000000-0000-4000-8000-000000000003',
        tstzrange('2031-11-01 00:00+08', '2031-11-02 23:00+08', '[)'), 'maintenance');

-- Replacements asked for beside them: one still a hold, one already approved.
insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, replaces_booking_id)
values
    ('d0000000-0000-4000-8000-0000000095d1', 'e0000000-0000-4000-8000-0000000095c1', 'b0000000-0000-4000-8000-000000000001',
     tstzrange('2031-11-01 10:00+08', '2031-11-01 12:00+08', '[)'), 'held', 'd0000000-0000-4000-8000-0000000095c1'),
    ('d0000000-0000-4000-8000-0000000095d2', 'e0000000-0000-4000-8000-0000000095c2', 'b0000000-0000-4000-8000-000000000001',
     tstzrange('2031-11-02 10:00+08', '2031-11-02 12:00+08', '[)'), 'approved', 'd0000000-0000-4000-8000-0000000095c2');

do $$
declare
    v_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_original uuid := 'd0000000-0000-4000-8000-0000000095c1';
    v_pending uuid := 'd0000000-0000-4000-8000-0000000095d1';
    v_outcome text;
    v_cancelled uuid[];
    v_rows integer;
begin
    if (select flag from public.venue_bookings where id = v_original) is distinct from 'affected' then
        raise exception 'SETUP FAIL: the block did not flag the original';
    end if;

    -- The block still covers the window: nothing changes.
    select outcome into v_outcome from public.restore_affected_booking(v_original, v_staff);
    if v_outcome <> 'still_blocked' then raise exception 'RESTORE FAIL: under a block gave %', v_outcome; end if;
    if (select flag from public.venue_bookings where id = v_original) is distinct from 'affected'
       or (select status::text from public.venue_bookings where id = v_pending) <> 'held' then
        raise exception 'RESTORE FAIL: a refused restore changed something';
    end if;

    -- A booking that is not affected, an approved replacement, and an unknown booking.
    select outcome into v_outcome from public.restore_affected_booking('d0000000-0000-4000-8000-0000000095c3', v_staff);
    if v_outcome <> 'not_affected' then raise exception 'RESTORE FAIL: an unflagged booking gave %', v_outcome; end if;
    select outcome into v_outcome from public.restore_affected_booking('d0000000-0000-4000-8000-0000000095c2', v_staff);
    if v_outcome <> 'replacement_approved' then raise exception 'RESTORE FAIL: past an approved replacement gave %', v_outcome; end if;
    select outcome into v_outcome from public.restore_affected_booking('d0000000-0000-4000-8000-0000000095ff', v_staff);
    if v_outcome <> 'booking_not_found' then raise exception 'RESTORE FAIL: an unknown booking gave %', v_outcome; end if;

    -- The block ends; the venue is deactivated, so it is not free.
    delete from public.venue_blocks where id = 'f0000000-0000-4000-8000-0000000095c1';
    update public.venues set is_active = false, inactive_reason = 'other', inactive_note = 'check'
     where id = 'b0000000-0000-4000-8000-000000000003';
    select outcome into v_outcome from public.restore_affected_booking(v_original, v_staff);
    if v_outcome <> 'venue_inactive' then raise exception 'RESTORE FAIL: an inactive venue gave %', v_outcome; end if;
    update public.venues set is_active = true, inactive_reason = null, inactive_note = null
     where id = 'b0000000-0000-4000-8000-000000000003';

    -- Free again: restored, flag cleared, the pending replacement cancelled.
    select outcome, cancelled_booking_ids into v_outcome, v_cancelled from public.restore_affected_booking(v_original, v_staff);
    if v_outcome <> 'ok' then raise exception 'RESTORE FAIL: a free venue gave %', v_outcome; end if;
    if v_cancelled is distinct from array[v_pending] then
        raise exception 'RESTORE FAIL: cancelled % (want the pending replacement)', v_cancelled;
    end if;
    if (select status::text || '|' || coalesce(flag::text, 'none') || '|' || coalesce(flag_reason, 'none') from public.venue_bookings
         where id = v_original) <> 'approved|none|none' then
        raise exception 'RESTORE FAIL: the original is not an approved, unflagged booking again';
    end if;
    if (select status::text from public.venue_bookings where id = v_pending) <> 'cancelled' then
        raise exception 'RESTORE FAIL: the pending replacement is not cancelled';
    end if;

    -- History on both, and the coordinator and organiser are told.
    select count(*) into v_rows from public.venue_booking_history
     where booking_id = v_original and action = 'restored' and actor_id = v_staff;
    if v_rows <> 1 then raise exception 'RESTORE FAIL: expected one restored row, got %', v_rows; end if;
    select count(*) into v_rows from public.venue_booking_history
     where booking_id = v_pending and action = 'cancelled_for_restore' and from_status = 'held' and to_status = 'cancelled'
       and actor_id = v_staff;
    if v_rows <> 1 then raise exception 'RESTORE FAIL: expected one cancelled row, got %', v_rows; end if;
    select count(*) into v_rows from public.notifications
     where type = 'venue_booking_restored' and event_id = 'e0000000-0000-4000-8000-0000000095c1'
       and recipient_id in ('a0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000001');
    if v_rows <> 2 then raise exception 'RESTORE FAIL: expected 2 notices, got %', v_rows; end if;

    -- Restoring again is refused and writes nothing.
    select outcome into v_outcome from public.restore_affected_booking(v_original, v_staff);
    if v_outcome <> 'not_affected' then raise exception 'RESTORE FAIL: a second restore gave %', v_outcome; end if;
    select count(*) into v_rows from public.venue_booking_history where booking_id = v_original and action = 'restored';
    if v_rows <> 1 then raise exception 'RESTORE FAIL: a refused restore wrote history'; end if;

    -- Only the service role can run it.
    if has_function_privilege('anon', 'public.restore_affected_booking(uuid, uuid)', 'execute')
       or has_function_privilege('authenticated', 'public.restore_affected_booking(uuid, uuid)', 'execute')
       or not has_function_privilege('service_role', 'public.restore_affected_booking(uuid, uuid)', 'execute') then
        raise exception 'RESTORE FAIL: restore_affected_booking is callable by a role other than service_role';
    end if;
end $$;

select 'VENUE RESTORE CHECKS PASSED' as result;

rollback;
