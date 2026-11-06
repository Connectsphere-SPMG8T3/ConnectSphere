-- CR-94 AC8: bookings made before setup and turnaround existed are re-checked
-- once with their venue's current figures, and flagged Conflict if they would
-- then overlap another booking.
-- Run with `supabase db query --linked -f`, or `psql "$DATABASE_URL" -f`. Raises
-- on the first failure and prints BOOKING BUFFER RECHECK CHECKS PASSED otherwise.
-- Everything runs inside `begin; ... rollback;`, so nothing here leaves a trace.

begin;

do $$
declare
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_old timestamptz := '2026-10-01 09:00+08';
    v_venue uuid;
    v_other_venue uuid;
    v_flagged public.venue_bookings;
    v_event uuid;
    v_count integer;
    v_staff integer;
    function_exists boolean;
begin
    select to_regprocedure('private.flag_bookings_predating_buffers()') is not null into function_exists;
    if not function_exists then
        raise exception 'CR-94 AC8 FAIL: private.flag_bookings_predating_buffers() does not exist';
    end if;

    insert into public.venues (name, location, capacity, opens_at, closes_at, setup_minutes, turnaround_minutes)
    values ('CR-94 AC8 check (rolled back)', 'Test', 100, '00:00', '23:59', 30, 45) returning id into v_venue;
    insert into public.venues (name, location, capacity, opens_at, closes_at)
    values ('CR-94 AC8 no buffers (rolled back)', 'Test', 100, '00:00', '23:59') returning id into v_other_venue;

    -- One event per booking, each on its own day unless a pair is meant to clash.
    create temporary table recheck_case (
        label text primary key, venue_id uuid, status public.event_status,
        period tstzrange, booking_status public.venue_booking_status, created timestamptz, booking_id uuid
    ) on commit drop;
    insert into recheck_case (label, venue_id, status, period, booking_status, created) values
        ('flagged', v_venue, 'planning', '[2031-08-01 10:00+08,2031-08-01 12:00+08)', 'held', v_old),
        ('named', v_venue, 'planning', '[2031-08-01 12:30+08,2031-08-01 14:00+08)', 'approved', v_old),
        ('quiet', v_venue, 'planning', '[2031-08-02 10:00+08,2031-08-02 12:00+08)', 'approved', v_old),
        ('recent', v_venue, 'planning', '[2031-08-03 10:00+08,2031-08-03 12:00+08)', 'held', now()),
        ('recent next', v_venue, 'planning', '[2031-08-03 12:30+08,2031-08-03 14:00+08)', 'held', now()),
        ('ended', v_venue, 'planning', '[2020-08-01 10:00+08,2020-08-01 12:00+08)', 'approved', v_old),
        ('ended next', v_venue, 'planning', '[2020-08-01 12:30+08,2020-08-01 14:00+08)', 'approved', v_old),
        ('closed', v_venue, 'completed', '[2031-08-04 10:00+08,2031-08-04 12:00+08)', 'approved', v_old),
        ('closed next', v_venue, 'planning', '[2031-08-04 12:30+08,2031-08-04 14:00+08)', 'released', v_old),
        ('already', v_venue, 'planning', '[2031-08-05 10:00+08,2031-08-05 12:00+08)', 'approved', v_old),
        ('already next', v_venue, 'planning', '[2031-08-05 12:30+08,2031-08-05 14:00+08)', 'approved', v_old),
        ('no buffers', v_other_venue, 'planning', '[2031-08-06 10:00+08,2031-08-06 12:00+08)', 'approved', v_old),
        ('no buffers next', v_other_venue, 'planning', '[2031-08-06 12:05+08,2031-08-06 14:00+08)', 'approved', v_old);

    declare
        v_row record;
        v_booking uuid;
    begin
        for v_row in select * from recheck_case loop
            insert into public.events (organiser_id, coordinator_id, status, name, starts_at, ends_at)
            values (v_organiser, v_coordinator, v_row.status, 'AC8 ' || v_row.label || ' (rolled back)',
                    lower(v_row.period), upper(v_row.period))
            returning id into v_event;
            insert into public.venue_bookings (event_id, venue_id, booked_period, status, requested_by, created_at)
            values (v_event, v_row.venue_id, v_row.period, v_row.booking_status, v_coordinator, v_row.created)
            returning id into v_booking;
            update recheck_case set booking_id = v_booking where label = v_row.label;
        end loop;
    end;

    update public.venue_bookings
       set flag = 'affected', flag_reason = 'Venue unavailable: Maintenance', flagged_at = now()
     where id = (select booking_id from recheck_case where label = 'already');

    select count(*) into v_staff from public.user_roles where role = 'venue_staff';

    perform private.flag_bookings_predating_buffers();

    select b.* into v_flagged from public.venue_bookings b
      join recheck_case c on c.booking_id = b.id where c.label = 'flagged';
    if v_flagged.flag is distinct from 'conflict'
       or v_flagged.flag_reason not like '%AC8 named (rolled back)%' then
        raise exception 'CR-94 AC8 FAIL: an overlapping legacy booking was not flagged Conflict, naming the other: %',
            v_flagged.flag_reason;
    end if;
    if v_flagged.status <> 'held' or v_flagged.setup_minutes <> 0 or v_flagged.turnaround_minutes <> 0
       or v_flagged.booked_period <> '[2031-08-01 10:00+08,2031-08-01 12:00+08)'::tstzrange then
        raise exception 'CR-94 AC8 FAIL: the flagged booking changed';
    end if;

    select count(*) into v_count from public.venue_bookings b
      join recheck_case c on c.booking_id = b.id
     where b.flag = 'conflict' and c.label <> 'flagged';
    if v_count <> 0 then
        raise exception 'CR-94 AC8 FAIL: % other bookings were flagged Conflict', v_count;
    end if;
    if (select b.flag from public.venue_bookings b join recheck_case c on c.booking_id = b.id
         where c.label = 'already') is distinct from 'affected' then
        raise exception 'CR-94 AC8 FAIL: an existing flag was replaced';
    end if;

    select count(*) into v_count from public.notifications
     where event_id = v_flagged.event_id and type = 'venue_booking_affected' and recipient_id = v_coordinator;
    if v_count <> 1 then
        raise exception 'CR-94 AC8 FAIL: the coordinator got % notices, expected 1', v_count;
    end if;
    select count(*) into v_count from public.notifications
     where event_id = v_flagged.event_id and type = 'venue_updated_affects_booking'
       and recipient_id in (select profile_id from public.user_roles where role = 'venue_staff');
    if v_count <> v_staff then
        raise exception 'CR-94 AC8 FAIL: % venue staff notices, expected %', v_count, v_staff;
    end if;

    -- Running it again finds nothing new.
    perform private.flag_bookings_predating_buffers();
    select count(*) into v_count from public.notifications
     where event_id = v_flagged.event_id and type = 'venue_booking_affected';
    if v_count <> 1 then
        raise exception 'CR-94 AC8 FAIL: a second run notified again';
    end if;

    if has_function_privilege('authenticated', 'private.flag_bookings_predating_buffers()', 'execute')
       or has_function_privilege('anon', 'private.flag_bookings_predating_buffers()', 'execute') then
        raise exception 'CR-94 AC8 FAIL: signed-in or anonymous users can run the re-check';
    end if;

    raise notice 'BOOKING BUFFER RECHECK CHECKS PASSED';
end;
$$;

select 'BOOKING BUFFER RECHECK CHECKS PASSED' as result;

rollback;
