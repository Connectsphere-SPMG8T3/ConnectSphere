-- SCRUM-19 venue booking request: the real request_venue_booking function.
-- Run with `supabase db query --linked -f` or `psql "$DATABASE_URL" -f`. Raises
-- on the first failure and prints BOOKING REQUEST CHECKS PASSED otherwise.
-- Everything runs inside `begin; ... rollback;`, so the throwaway events,
-- bookings, blocks and notifications leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002, who also holds
-- venue_staff), venue staff (…0003) and venues Innovation Lab (…0006) and
-- Heritage Hall (…0007), on a date far enough ahead that nothing real is booked.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-0000000019a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Booking check X (rolled back)',
     '2031-03-10 14:00+08', '2031-03-10 17:00+08'),
    ('e0000000-0000-4000-8000-0000000019a2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Booking check Y, overlapping (rolled back)',
     '2031-03-10 16:00+08', '2031-03-10 18:00+08'),
    ('e0000000-0000-4000-8000-0000000019a3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Booking check Z, back-to-back (rolled back)',
     '2031-03-10 17:00+08', '2031-03-10 19:00+08'),
    ('e0000000-0000-4000-8000-0000000019a4', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Booking check W, during a block (rolled back)',
     '2031-03-11 11:00+08', '2031-03-11 13:00+08'),
    ('e0000000-0000-4000-8000-0000000019a5', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'returned', 'Booking check, returned (rolled back)',
     '2031-03-12 09:00+08', '2031-03-12 10:00+08'),
    ('e0000000-0000-4000-8000-0000000019a6', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'under_review', 'Booking check, under review (rolled back)',
     '2031-03-12 11:00+08', '2031-03-12 12:00+08'),
    ('e0000000-0000-4000-8000-0000000019a7', 'a0000000-0000-4000-8000-000000000001',
     null, 'planning', 'Booking check, not my event (rolled back)',
     '2031-03-12 13:00+08', '2031-03-12 14:00+08'),
    ('e0000000-0000-4000-8000-0000000019a8', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Booking check, no times (rolled back)',
     null, null);

-- Heritage Hall is closed for maintenance 10:00-12:00 on 11 Mar 2031.
insert into public.venue_blocks (venue_id, blocked_period, reason, notes) values
    ('b0000000-0000-4000-8000-000000000007',
     tstzrange('2031-03-11 10:00+08', '2031-03-11 12:00+08', '[)'), 'maintenance', 'Booking check (rolled back)');

do $$
declare
    v_event uuid := 'e0000000-0000-4000-8000-0000000019a1';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_lab uuid := 'b0000000-0000-4000-8000-000000000006';
    v_result record;
    v_booking public.venue_bookings;
begin
    -- AC1: a planning event's assigned coordinator holds a free venue for the
    -- event's own [starts_at, ends_at).
    select * into v_result from public.request_venue_booking(
        v_event, v_lab, v_coordinator, '  Need early access at 13:00  ', 'A venue was requested.');
    if v_result.outcome is distinct from 'ok' or v_result.booking_id is null then
        raise exception 'BOOKING FAIL: a free venue was not held (outcome %)', v_result.outcome;
    end if;
    select * into v_booking from public.venue_bookings where id = v_result.booking_id;
    if v_booking.status <> 'held'
       or v_booking.event_id <> v_event
       or v_booking.venue_id <> v_lab
       or v_booking.occupied_period <> tstzrange('2031-03-10 14:00+08', '2031-03-10 17:00+08', '[)')
       or v_booking.requested_by is distinct from v_coordinator
       or v_booking.request_note is distinct from 'Need early access at 13:00' then
        raise exception 'BOOKING FAIL: the hold does not match the event period, requester and trimmed note';
    end if;

    -- AC2: event Y overlaps X's hold by an hour, so it is refused and nothing is held.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000019a2', v_lab, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'held_by_other' or v_result.booking_id is not null then
        raise exception 'BOOKING FAIL: an overlapping request was not refused as held_by_other (outcome %)', v_result.outcome;
    end if;
    if exists (select 1 from public.venue_bookings where event_id = 'e0000000-0000-4000-8000-0000000019a2') then
        raise exception 'BOOKING FAIL: the refused request left a booking behind';
    end if;

    -- AC2 / QA-28: event Z starts as X ends; half-open periods with zero turnaround allow it.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000019a3', v_lab, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'BOOKING FAIL: a back-to-back request was refused (outcome %)', v_result.outcome;
    end if;

    -- AC2 / 6.14: a block is not a booking, so DB-1 doesn't see it; the function must.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000019a4', 'b0000000-0000-4000-8000-000000000007', v_coordinator, null,
        'A venue was requested.');
    if v_result.outcome is distinct from 'blocked' or v_result.booking_id is not null then
        raise exception 'BOOKING FAIL: a request overlapping a block was not refused as blocked (outcome %)', v_result.outcome;
    end if;
    if exists (select 1 from public.venue_bookings where event_id = 'e0000000-0000-4000-8000-0000000019a4') then
        raise exception 'BOOKING FAIL: the blocked request left a booking behind';
    end if;

    -- AC4 / BR-R1: X already holds Innovation Lab, so neither a second venue
    -- nor the same venue again is accepted.
    select * into v_result from public.request_venue_booking(
        v_event, 'b0000000-0000-4000-8000-000000000007', v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'already_booked' or v_result.booking_id is not null then
        raise exception 'BOOKING FAIL: a second venue for one event was not refused as already_booked (outcome %)', v_result.outcome;
    end if;
    select * into v_result from public.request_venue_booking(
        v_event, v_lab, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'already_booked' then
        raise exception 'BOOKING FAIL: re-requesting the held venue was not refused as already_booked (outcome %)', v_result.outcome;
    end if;
    if (select count(*) from public.venue_bookings where event_id = v_event) <> 1 then
        raise exception 'BOOKING FAIL: event X does not have exactly one booking';
    end if;

    -- AC5 / BR-R6 (QA-22): only a planning event can hold a venue; a returned
    -- one is still having its requirements amended.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000019a5', 'b0000000-0000-4000-8000-000000000007', v_coordinator, null, 'x');
    if v_result.outcome is distinct from 'returned' then
        raise exception 'BOOKING FAIL: a returned event was not refused as returned (outcome %)', v_result.outcome;
    end if;
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000019a6', 'b0000000-0000-4000-8000-000000000007', v_coordinator, null, 'x');
    if v_result.outcome is distinct from 'not_planning' then
        raise exception 'BOOKING FAIL: an under-review event was not refused as not_planning (outcome %)', v_result.outcome;
    end if;

    -- AC6: re-checked under the lock, in case the event was reassigned after the API's check.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000019a7', 'b0000000-0000-4000-8000-000000000007', v_coordinator, null, 'x');
    if v_result.outcome is distinct from 'not_assigned' then
        raise exception 'BOOKING FAIL: another coordinator''s event was not refused as not_assigned (outcome %)', v_result.outcome;
    end if;

    -- A planning event without times has no period to hold: an outcome, not a
    -- check-constraint error from an unbounded range.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000019a8', 'b0000000-0000-4000-8000-000000000007', v_coordinator, null, 'x');
    if v_result.outcome is distinct from 'no_period' then
        raise exception 'BOOKING FAIL: an event without times was not refused as no_period (outcome %)', v_result.outcome;
    end if;

    -- Unknown ids come back as outcomes, not as a foreign-key error.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000019ff', 'b0000000-0000-4000-8000-000000000007', v_coordinator, null, 'x');
    if v_result.outcome is distinct from 'event_not_found' then
        raise exception 'BOOKING FAIL: an unknown event was not reported as event_not_found (outcome %)', v_result.outcome;
    end if;
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000019a3', 'b0000000-0000-4000-8000-0000000000ff', v_coordinator, null, 'x');
    if v_result.outcome is distinct from 'venue_not_found' then
        raise exception 'BOOKING FAIL: an unknown venue was not reported as venue_not_found (outcome %)', v_result.outcome;
    end if;
    if exists (select 1 from public.venue_bookings
               where event_id in ('e0000000-0000-4000-8000-0000000019a5', 'e0000000-0000-4000-8000-0000000019a6',
                                  'e0000000-0000-4000-8000-0000000019a7')) then
        raise exception 'BOOKING FAIL: a refused request left a booking behind';
    end if;

    -- AC1 / NT-R1 / NT-R3: X's request notified the venue-staff pool once each,
    -- but not the requesting coordinator, even though that account also holds
    -- venue_staff. Refused requests (Y, W) notified nobody.
    if (select count(*) from public.notifications
         where event_id = v_event and type = 'venue_booking_requested'
           and recipient_id = 'a0000000-0000-4000-8000-000000000003'
           and message = 'A venue was requested.') <> 1 then
        raise exception 'BOOKING FAIL: venue staff were not notified exactly once of the request';
    end if;
    if exists (select 1 from public.notifications
                where event_id = v_event and type = 'venue_booking_requested' and recipient_id = v_coordinator) then
        raise exception 'BOOKING FAIL: the requesting coordinator was notified of their own request';
    end if;
    if exists (select 1 from public.notifications
                where type = 'venue_booking_requested'
                  and event_id in ('e0000000-0000-4000-8000-0000000019a2', 'e0000000-0000-4000-8000-0000000019a4')) then
        raise exception 'BOOKING FAIL: a refused request sent notifications';
    end if;

    -- API-only (ADR-0002): browsers and the publishable key can't call it.
    if has_function_privilege('anon', 'public.request_venue_booking(uuid, uuid, uuid, text, text)', 'execute')
       or has_function_privilege('authenticated', 'public.request_venue_booking(uuid, uuid, uuid, text, text)', 'execute')
       or not has_function_privilege('service_role', 'public.request_venue_booking(uuid, uuid, uuid, text, text)', 'execute') then
        raise exception 'BOOKING FAIL: request_venue_booking is callable by a role other than service_role';
    end if;
end;
$$;

-- Reached only if every block above passed (a failed assertion aborts the run).
select 'BOOKING REQUEST CHECKS PASSED' as result;

rollback;
