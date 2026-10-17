-- SCRUM-21 booking conflict detection: the occupied window, public.venue_conflicts
-- and the two request functions that use it (REQUIREMENTS §6.14, one block per
-- row of its table). Run with `supabase db query --linked -f` or
-- `psql "$DATABASE_URL" -f`. Raises on the first failure and prints
-- BOOKING CONFLICT CHECKS PASSED otherwise. Everything runs inside
-- `begin; ... rollback;`, so the throwaway events, bookings and blocks leave no
-- trace. Uses the seeded organiser (…0001), coordinator (…0002), Innovation Lab
-- (…0006) and Heritage Hall (…0007), in April 2031 so nothing real is booked.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-0000000021a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Conflict check A (rolled back)',
     '2031-04-07 10:00+08', '2031-04-07 12:00+08'),
    ('e0000000-0000-4000-8000-0000000021a2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Conflict check, starts in two days (rolled back)',
     date_trunc('hour', now()) + interval '2 days', date_trunc('hour', now()) + interval '2 days 2 hours');

do $$
declare
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_lab uuid := 'b0000000-0000-4000-8000-000000000006';
    v_result record;
    v_booking public.venue_bookings;
begin
    -- AC1: A's own window is 10:00-12:00. With 30 min setup and 45 min
    -- turnaround it occupies the venue 09:30-12:45.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000021a1', v_lab, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'CONFLICT FAIL: A could not hold a free venue (outcome %)', v_result.outcome;
    end if;
    select * into v_booking from public.venue_bookings where id = v_result.booking_id;
    if v_booking.setup_minutes <> 0 or v_booking.turnaround_minutes <> 0
       or v_booking.booked_period <> tstzrange('2031-04-07 10:00+08', '2031-04-07 12:00+08', '[)')
       or v_booking.occupied_period <> v_booking.booked_period then
        raise exception 'CONFLICT FAIL: a new booking does not start with zero setup and turnaround';
    end if;

    update public.venue_bookings set setup_minutes = 30, turnaround_minutes = 45 where id = v_result.booking_id;
    select * into v_booking from public.venue_bookings where id = v_result.booking_id;
    if v_booking.occupied_period <> tstzrange('2031-04-07 09:30+08', '2031-04-07 12:45+08', '[)')
       or v_booking.booked_period <> tstzrange('2031-04-07 10:00+08', '2031-04-07 12:00+08', '[)') then
        raise exception 'CONFLICT FAIL: AC1 occupied window is %, want 09:30-12:45', v_booking.occupied_period;
    end if;

    -- CR-99 AC1 counts to the event's start, not the start of setup: a hold
    -- written with 60 min setup (as CR-100 will) for an event two days away
    -- still expires when the event starts.
    insert into public.venue_bookings (event_id, venue_id, booked_period, setup_minutes, status, requested_by)
    values ('e0000000-0000-4000-8000-0000000021a2', 'b0000000-0000-4000-8000-000000000007',
            tstzrange(date_trunc('hour', now()) + interval '2 days', date_trunc('hour', now()) + interval '2 days 2 hours', '[)'),
            60, 'held', v_coordinator)
    returning * into v_booking;
    if v_booking.expires_at <> date_trunc('hour', now()) + interval '2 days'
       or lower(v_booking.occupied_period) <> date_trunc('hour', now()) + interval '2 days' - interval '1 hour' then
        raise exception 'CONFLICT FAIL: a hold with setup expires at %, want the event start', v_booking.expires_at;
    end if;
end;
$$;

-- Heritage Hall is closed for maintenance 10:00-12:00 on 8 Apr 2031.
insert into public.venue_blocks (venue_id, blocked_period, reason, notes) values
    ('b0000000-0000-4000-8000-000000000007',
     tstzrange('2031-04-08 10:00+08', '2031-04-08 12:00+08', '[)'), 'maintenance', 'Conflict check (rolled back)');

-- public.venue_conflicts against A, which occupies Innovation Lab 09:30-12:45.
do $$
declare
    v_lab uuid := 'b0000000-0000-4000-8000-000000000006';
    v_hall uuid := 'b0000000-0000-4000-8000-000000000007';
    v_a uuid;
    v_row record;
    v_status public.venue_booking_status;
    v_count integer;
begin
    select id into v_a from public.venue_bookings where event_id = 'e0000000-0000-4000-8000-0000000021a1';

    -- AC3: windows that only touch don't conflict (B's setup starts as A's turnaround ends).
    if exists (select 1 from public.venue_conflicts(
            tstzrange('2031-04-07 12:45+08', '2031-04-07 14:00+08', '[)'), v_lab)) then
        raise exception 'CONFLICT FAIL: AC3 a window starting as A''s turnaround ends conflicts';
    end if;

    -- §6.14 row 2: B 13:30-15:00 with 30 min setup and 45 min turnaround occupies 13:00-15:45.
    if exists (select 1 from public.venue_conflicts(
            tstzrange('2031-04-07 13:00+08', '2031-04-07 15:45+08', '[)'), v_lab)) then
        raise exception 'CONFLICT FAIL: row 2 a window after A''s turnaround conflicts';
    end if;

    -- §6.14 row 3, AC2: B 13:00-15:00 occupies 12:30-15:45, so its setup overlaps
    -- A's turnaround. The conflict names A's event and its occupied window.
    select * into v_row from public.venue_conflicts(
        tstzrange('2031-04-07 12:30+08', '2031-04-07 15:45+08', '[)'), v_lab);
    if v_row.kind is distinct from 'booking' or v_row.booking_id is distinct from v_a
       or v_row.event_name is distinct from 'Conflict check A (rolled back)'
       or v_row.booking_status is distinct from 'held'
       or v_row.venue_id is distinct from v_lab
       or v_row.occupied_period is distinct from tstzrange('2031-04-07 09:30+08', '2031-04-07 12:45+08', '[)') then
        raise exception 'CONFLICT FAIL: row 3 setup overlapping A''s turnaround is not named as A (%)', v_row;
    end if;

    -- §6.14 row 4: an overlap of one minute is a conflict.
    if not exists (select 1 from public.venue_conflicts(
            tstzrange('2031-04-07 12:44+08', '2031-04-07 13:00+08', '[)'), v_lab)) then
        raise exception 'CONFLICT FAIL: row 4 a one-minute overlap is not a conflict';
    end if;

    -- AC2, §6.14 rows 5-6: held, approved and re-review bookings occupy the venue.
    foreach v_status in array array['approved', 're_review']::public.venue_booking_status[] loop
        update public.venue_bookings set status = v_status where id = v_a;
        if not exists (select 1 from public.venue_conflicts(
                tstzrange('2031-04-07 11:00+08', '2031-04-07 11:30+08', '[)'), v_lab)) then
            raise exception 'CONFLICT FAIL: AC2 a % booking does not conflict', v_status;
        end if;
    end loop;

    -- AC5, §6.14 row 7: rejected, cancelled, released and expired bookings are ignored.
    foreach v_status in array array['rejected', 'cancelled', 'released', 'expired']::public.venue_booking_status[] loop
        update public.venue_bookings set status = v_status where id = v_a;
        if exists (select 1 from public.venue_conflicts(
                tstzrange('2031-04-07 11:00+08', '2031-04-07 11:30+08', '[)'), v_lab)) then
            raise exception 'CONFLICT FAIL: AC5 a % booking still conflicts', v_status;
        end if;
    end loop;

    -- AC5 (CR-99): a hold past its expiry that the job hasn't marked yet is ignored.
    update public.venue_bookings set status = 'held', expires_at = now() - interval '1 minute' where id = v_a;
    if exists (select 1 from public.venue_conflicts(
            tstzrange('2031-04-07 11:00+08', '2031-04-07 11:30+08', '[)'), v_lab)) then
        raise exception 'CONFLICT FAIL: AC5 an overdue hold still conflicts';
    end if;
    update public.venue_bookings set expires_at = now() + interval '1 day' where id = v_a;

    -- AC7, §6.14 row 9: the same time at another venue is no conflict.
    if exists (select 1 from public.venue_conflicts(
            tstzrange('2031-04-07 11:00+08', '2031-04-07 11:30+08', '[)'), v_hall)) then
        raise exception 'CONFLICT FAIL: AC7 a booking at another venue conflicts';
    end if;

    -- §6.14 row 8: a block is a conflict, with its reason and period.
    select * into v_row from public.venue_conflicts(
        tstzrange('2031-04-08 11:00+08', '2031-04-08 13:00+08', '[)'), v_hall);
    if v_row.kind is distinct from 'block' or v_row.block_reason is distinct from 'maintenance'
       or v_row.event_name is not null or v_row.booking_id is not null
       or v_row.occupied_period is distinct from tstzrange('2031-04-08 10:00+08', '2031-04-08 12:00+08', '[)') then
        raise exception 'CONFLICT FAIL: row 8 a block is not reported with its reason (%)', v_row;
    end if;

    -- Search asks about every venue at once (no venue given).
    select count(*) into v_count from public.venue_conflicts(
        tstzrange('2031-04-07 11:00+08', '2031-04-08 11:00+08', '[)'));
    if v_count <> 2 then
        raise exception 'CONFLICT FAIL: an all-venue check found % conflicts, want A and the block', v_count;
    end if;

    -- Re-checking a booking (approval, re-review) leaves the booking itself out.
    if exists (select 1 from public.venue_conflicts(
            tstzrange('2031-04-07 11:00+08', '2031-04-07 11:30+08', '[)'), v_lab, v_a)) then
        raise exception 'CONFLICT FAIL: a booking conflicts with itself';
    end if;
end;
$$;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-0000000021c1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Conflict check C, in A''s turnaround (rolled back)',
     '2031-04-07 12:30+08', '2031-04-07 14:00+08'),
    ('e0000000-0000-4000-8000-0000000021c2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Conflict check S, spaces (rolled back)',
     '2031-04-07 08:00+08', '2031-04-09 18:00+08');

insert into public.event_space_requests (id, event_id, label, starts_at, ends_at) values
    -- In A's turnaround at Innovation Lab.
    ('f0000000-0000-4000-8000-0000000021d1', 'e0000000-0000-4000-8000-0000000021c2', 'Turnaround space',
     '2031-04-07 12:30+08', '2031-04-07 13:30+08'),
    -- During Heritage Hall's maintenance block.
    ('f0000000-0000-4000-8000-0000000021d2', 'e0000000-0000-4000-8000-0000000021c2', 'Blocked space',
     '2031-04-08 11:00+08', '2031-04-08 13:00+08'),
    -- A free time.
    ('f0000000-0000-4000-8000-0000000021d3', 'e0000000-0000-4000-8000-0000000021c2', 'Free space',
     '2031-04-09 10:00+08', '2031-04-09 11:00+08');

-- AC2: both request paths refuse on the occupied window and name what is in the way.
do $$
declare
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_lab uuid := 'b0000000-0000-4000-8000-000000000006';
    v_hall uuid := 'b0000000-0000-4000-8000-000000000007';
    v_result record;
begin
    -- C's own time (12:30-14:00) misses A's (10:00-12:00) but overlaps A's turnaround.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000021c1', v_lab, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'held_by_other'
       or v_result.conflict ->> 'kind' is distinct from 'booking'
       or v_result.conflict ->> 'event_name' is distinct from 'Conflict check A (rolled back)'
       or (v_result.conflict ->> 'starts_at')::timestamptz <> '2031-04-07 09:30+08'
       or (v_result.conflict ->> 'ends_at')::timestamptz <> '2031-04-07 12:45+08' then
        raise exception 'CONFLICT FAIL: AC2 request in A''s turnaround was not refused naming A (% %)',
            v_result.outcome, v_result.conflict;
    end if;

    select * into v_result from public.request_venue_booking_for_space(
        'f0000000-0000-4000-8000-0000000021d1', v_lab, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'held_by_other'
       or v_result.conflict ->> 'event_name' is distinct from 'Conflict check A (rolled back)' then
        raise exception 'CONFLICT FAIL: AC2 space request in A''s turnaround was not refused naming A (% %)',
            v_result.outcome, v_result.conflict;
    end if;

    -- §6.14 row 8: a block refuses with its reason and period, never an event name.
    select * into v_result from public.request_venue_booking_for_space(
        'f0000000-0000-4000-8000-0000000021d2', v_hall, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'blocked'
       or v_result.conflict ->> 'kind' is distinct from 'block'
       or v_result.conflict ->> 'block_reason' is distinct from 'maintenance'
       or v_result.conflict ? 'event_name' and v_result.conflict ->> 'event_name' is not null
       or (v_result.conflict ->> 'starts_at')::timestamptz <> '2031-04-08 10:00+08' then
        raise exception 'CONFLICT FAIL: a space request during a block was not refused with its reason (% %)',
            v_result.outcome, v_result.conflict;
    end if;

    if exists (select 1 from public.venue_bookings
               where event_id in ('e0000000-0000-4000-8000-0000000021c1', 'e0000000-0000-4000-8000-0000000021c2')) then
        raise exception 'CONFLICT FAIL: a refused request left a booking behind';
    end if;

    -- A successful request carries no conflict.
    select * into v_result from public.request_venue_booking_for_space(
        'f0000000-0000-4000-8000-0000000021d3', v_lab, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'ok' or v_result.conflict is not null then
        raise exception 'CONFLICT FAIL: a free space request was not held cleanly (% %)', v_result.outcome, v_result.conflict;
    end if;
end;
$$;

-- The check returns other events' names, so only the API may call it.
do $$
begin
    if has_function_privilege('authenticated', 'public.venue_conflicts(tstzrange, uuid, uuid)', 'execute')
       or has_function_privilege('anon', 'public.venue_conflicts(tstzrange, uuid, uuid)', 'execute') then
        raise exception 'CONFLICT FAIL: venue_conflicts is executable by a signed-in or anonymous user';
    end if;
end;
$$;

select 'BOOKING CONFLICT CHECKS PASSED' as result;

rollback;
