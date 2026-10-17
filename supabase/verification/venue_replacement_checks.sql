-- CR-95 AC4 (request a replacement venue): request_venue_booking and
-- request_venue_booking_for_space take the booking being replaced. Only the
-- event's own affected, live booking can be named; the replacement is linked
-- to it, sits beside it until the original is released, and a plain request
-- with no link is still refused while the event has a venue.
-- Run with the Supabase MCP execute_sql, `supabase db query --linked -f`, or
-- `psql "$DATABASE_URL" -f`. Raises on the first failure and prints
-- VENUE REPLACEMENT CHECKS PASSED otherwise. Everything runs inside
-- `begin; ... rollback;`, so nothing here leaves a trace.
-- Uses the seeded organiser (…0001), coordinator (…0002), Seminar Room 1
-- (b0000000-…0003, where the affected bookings are) and Innovation Lab
-- (b0000000-…0001, the replacement venue).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, expected_attendance, starts_at, ends_at)
values
    ('e0000000-0000-4000-8000-0000000095f1', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Replacement check affected (rolled back)', 20, '2031-09-01 10:00+08', '2031-09-01 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095f2', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Replacement check unflagged (rolled back)', 20, '2031-09-02 10:00+08', '2031-09-02 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095f3', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Replacement check someone else (rolled back)', 20, '2031-09-03 10:00+08', '2031-09-03 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095f4', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Replacement check released (rolled back)', 20, '2031-09-04 10:00+08', '2031-09-04 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095f5', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Replacement check space (rolled back)', 20, '2031-09-05 10:00+08', '2031-09-05 12:00+08');

insert into public.event_space_requests (id, event_id, label, starts_at, ends_at)
values ('c0000000-0000-4000-8000-0000000095a5', 'e0000000-0000-4000-8000-0000000095f5', 'Breakout room',
        '2031-09-05 10:00+08', '2031-09-05 12:00+08');

insert into public.venue_bookings (id, event_id, event_space_request_id, venue_id, occupied_period, status)
values
    ('d0000000-0000-4000-8000-0000000095c1', 'e0000000-0000-4000-8000-0000000095f1', null, 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-09-01 10:00+08', '2031-09-01 12:00+08', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000095c2', 'e0000000-0000-4000-8000-0000000095f2', null, 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-09-02 10:00+08', '2031-09-02 12:00+08', '[)'), 'held'),
    ('d0000000-0000-4000-8000-0000000095c4', 'e0000000-0000-4000-8000-0000000095f4', null, 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-09-04 10:00+08', '2031-09-04 12:00+08', '[)'), 'released'),
    ('d0000000-0000-4000-8000-0000000095c5', 'e0000000-0000-4000-8000-0000000095f5', 'c0000000-0000-4000-8000-0000000095a5',
     'b0000000-0000-4000-8000-000000000003', tstzrange('2031-09-05 10:00+08', '2031-09-05 12:00+08', '[)'), 'approved');

update public.venue_bookings
   set flag = 'affected', flag_reason = 'Venue unavailable: maintenance', flagged_at = now()
 where id in ('d0000000-0000-4000-8000-0000000095c1', 'd0000000-0000-4000-8000-0000000095c4',
              'd0000000-0000-4000-8000-0000000095c5');

do $$
declare
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_lab uuid := 'b0000000-0000-4000-8000-000000000001';
    v_outcome text;
    v_booking uuid;
    v_replaces uuid;
    v_rows integer;
begin
    -- Without the link, the event still has a venue.
    select outcome into v_outcome from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000095f1', v_lab, v_coordinator, null, 'msg');
    if v_outcome <> 'already_booked' then
        raise exception 'REPLACEMENT FAIL: an unlinked request beside an affected booking gave %', v_outcome;
    end if;

    -- Naming the affected booking: a held replacement, linked, original untouched.
    select outcome, booking_id into v_outcome, v_booking from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000095f1', v_lab, v_coordinator, 'Replacement', 'msg',
        'd0000000-0000-4000-8000-0000000095c1');
    if v_outcome <> 'ok' or v_booking is null then
        raise exception 'REPLACEMENT FAIL: replacing the affected booking gave %', v_outcome;
    end if;
    select replaces_booking_id into v_replaces from public.venue_bookings where id = v_booking;
    if v_replaces is distinct from 'd0000000-0000-4000-8000-0000000095c1'::uuid then
        raise exception 'REPLACEMENT FAIL: the replacement is not linked to the original (%)', v_replaces;
    end if;
    if (select status::text || '|' || flag::text from public.venue_bookings
         where id = 'd0000000-0000-4000-8000-0000000095c1') <> 'approved|affected' then
        raise exception 'REPLACEMENT FAIL: requesting a replacement changed the original booking';
    end if;
    if (select status::text from public.venue_bookings where id = v_booking) <> 'held' then
        raise exception 'REPLACEMENT FAIL: the replacement is not a hold';
    end if;

    -- One replacement at a time.
    select outcome into v_outcome from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000095f1', v_lab, v_coordinator, null, 'msg',
        'd0000000-0000-4000-8000-0000000095c1');
    if v_outcome <> 'already_booked' then
        raise exception 'REPLACEMENT FAIL: a second replacement gave %', v_outcome;
    end if;

    -- Only an affected, live booking of this event can be replaced.
    select outcome into v_outcome from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000095f2', v_lab, v_coordinator, null, 'msg',
        'd0000000-0000-4000-8000-0000000095c2');
    if v_outcome <> 'replaced_booking_invalid' then
        raise exception 'REPLACEMENT FAIL: replacing an unflagged booking gave %', v_outcome;
    end if;
    select outcome into v_outcome from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000095f3', v_lab, v_coordinator, null, 'msg',
        'd0000000-0000-4000-8000-0000000095c1');
    if v_outcome <> 'replaced_booking_invalid' then
        raise exception 'REPLACEMENT FAIL: replacing another event''s booking gave %', v_outcome;
    end if;
    select outcome into v_outcome from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000095f4', v_lab, v_coordinator, null, 'msg',
        'd0000000-0000-4000-8000-0000000095c4');
    if v_outcome <> 'replaced_booking_invalid' then
        raise exception 'REPLACEMENT FAIL: replacing a released booking gave %', v_outcome;
    end if;
    select count(*) into v_rows from public.venue_bookings
     where event_id in ('e0000000-0000-4000-8000-0000000095f2', 'e0000000-0000-4000-8000-0000000095f3',
                        'e0000000-0000-4000-8000-0000000095f4') and replaces_booking_id is not null;
    if v_rows <> 0 then raise exception 'REPLACEMENT FAIL: a refused replacement left a booking behind'; end if;

    -- The per-space path: the same rules, and the one-active-booking-per-space
    -- index lets the replacement sit beside the affected original.
    select outcome into v_outcome from public.request_venue_booking_for_space(
        'c0000000-0000-4000-8000-0000000095a5', v_lab, v_coordinator, null, 'msg');
    if v_outcome <> 'already_booked' then
        raise exception 'REPLACEMENT FAIL: an unlinked space request beside an affected booking gave %', v_outcome;
    end if;
    select outcome, booking_id into v_outcome, v_booking from public.request_venue_booking_for_space(
        'c0000000-0000-4000-8000-0000000095a5', v_lab, v_coordinator, null, 'msg',
        'd0000000-0000-4000-8000-0000000095c5');
    if v_outcome <> 'ok' then
        raise exception 'REPLACEMENT FAIL: replacing a space booking gave %', v_outcome;
    end if;
    select outcome into v_outcome from public.request_venue_booking_for_space(
        'c0000000-0000-4000-8000-0000000095a5', v_lab, v_coordinator, null, 'msg',
        'd0000000-0000-4000-8000-0000000095c5');
    if v_outcome <> 'already_booked' then
        raise exception 'REPLACEMENT FAIL: a second space replacement gave %', v_outcome;
    end if;
end $$;

select 'VENUE REPLACEMENT CHECKS PASSED' as result;

rollback;
