-- SCRUM-85 the coordinator cancels a venue booking: the real cancel_venue_booking
-- function, the freed slot, the booking's history, venue staff's notices, the
-- event's return to Planning, and the refusals. Needs CR-99, CR-95, CR-104 and
-- story 37 applied first.
-- Run with `supabase db query --linked -f` or `psql "$DATABASE_URL" -f`. Raises
-- on the first failure and prints BOOKING CANCEL CHECKS PASSED otherwise.
-- Everything runs inside `begin; ... rollback;`, so the throwaway events,
-- spaces, bookings, history and notifications leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002, who also holds
-- venue_staff), venue staff (…0003), Safety Officer (…0006) and venues Grand
-- Ballroom (…0001), Innovation Lab (…0006) and Heritage Hall (…0007), 40 days
-- ahead so every event is upcoming whatever day this runs.

begin;

create temporary table cancel_check_times on commit drop as
select date_trunc('day', now()) + interval '40 days' as day0;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at)
select v.id::uuid, 'a0000000-0000-4000-8000-000000000001', v.coordinator::uuid, v.status::public.event_status,
       v.name, t.day0 + (v.day || ' days')::interval + interval '1 hour',
       t.day0 + (v.day || ' days')::interval + interval '3 hours'
from cancel_check_times t,
(values
    -- P: planning, held booking (AC1, AC8, AC9).
    ('e0000000-0000-4000-8000-0000000085a1', 'a0000000-0000-4000-8000-000000000002', 'planning', 'Cancel check P (rolled back)', 0),
    -- Q: wants P's slot once it is free (AC1, AC2).
    ('e0000000-0000-4000-8000-0000000085a2', 'a0000000-0000-4000-8000-000000000002', 'planning', 'Cancel check Q (rolled back)', 0),
    -- C: confirmed, two venues; one is cancelled (AC4, AC7, AC8).
    ('e0000000-0000-4000-8000-0000000085a3', 'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Cancel check C (rolled back)', 1),
    -- S: in Safety review (AC4).
    ('e0000000-0000-4000-8000-0000000085a4', 'a0000000-0000-4000-8000-000000000002', 'safety_review', 'Cancel check S (rolled back)', 2),
    -- R: a booking under re-review ([Assumption]).
    ('e0000000-0000-4000-8000-0000000085a5', 'a0000000-0000-4000-8000-000000000002', 'planning', 'Cancel check R (rolled back)', 3),
    -- F: bookings that can't be cancelled (AC3), and an expired hold (CR-99).
    ('e0000000-0000-4000-8000-0000000085a6', 'a0000000-0000-4000-8000-000000000002', 'planning', 'Cancel check F (rolled back)', 4),
    -- X: cancelled event (AC10).
    ('e0000000-0000-4000-8000-0000000085a7', 'a0000000-0000-4000-8000-000000000002', 'cancelled', 'Cancel check X (rolled back)', 5),
    -- N: assigned to nobody (AC5).
    ('e0000000-0000-4000-8000-0000000085a8', null, 'planning', 'Cancel check N (rolled back)', 6),
    -- A, B: an affected original and its pending replacement (CR-95).
    ('e0000000-0000-4000-8000-0000000085a9', 'a0000000-0000-4000-8000-000000000002', 'planning', 'Cancel check A (rolled back)', 7),
    ('e0000000-0000-4000-8000-0000000085b1', 'a0000000-0000-4000-8000-000000000002', 'planning', 'Cancel check B (rolled back)', 8),
    -- Z: in Preparation (AC4).
    ('e0000000-0000-4000-8000-0000000085b2', 'a0000000-0000-4000-8000-000000000002', 'preparation', 'Cancel check Z (rolled back)', 9)
) as v(id, coordinator, status, name, day);

insert into public.event_space_requests (id, event_id, label, expected_pax) values
    ('f0000000-0000-4000-8000-000000008501', 'e0000000-0000-4000-8000-0000000085a3', 'Plenary', 80),
    ('f0000000-0000-4000-8000-000000008502', 'e0000000-0000-4000-8000-0000000085a3', 'Breakout', 20);

insert into public.venue_bookings
    (id, event_id, event_space_request_id, venue_id, booked_period, setup_minutes, turnaround_minutes, status,
     expires_at, replaces_booking_id, flag, flag_reason, flagged_at)
select v.id::uuid, v.event_id::uuid, v.space::uuid, v.venue::uuid,
       tstzrange(t.day0 + (v.day || ' days')::interval + interval '1 hour',
                 t.day0 + (v.day || ' days')::interval + interval '3 hours', '[)'),
       v.setup, v.turnaround, v.status::public.venue_booking_status,
       case when v.status = 'held' then coalesce(v.expires_at::timestamptz, now() + interval '7 days') end,
       v.replaces::uuid, v.flag::public.venue_booking_flag,
       case when v.flag is not null then 'Venue unavailable: Maintenance' end,
       case when v.flag is not null then now() end
from cancel_check_times t,
(values
    ('d0000000-0000-4000-8000-0000000085d1', 'e0000000-0000-4000-8000-0000000085a1', null, 'b0000000-0000-4000-8000-000000000006', 0, 30, 45, 'held', null, null, null),
    ('d0000000-0000-4000-8000-0000000085d2', 'e0000000-0000-4000-8000-0000000085a3', 'f0000000-0000-4000-8000-000000008501', 'b0000000-0000-4000-8000-000000000006', 1, 0, 0, 'approved', null, null, null),
    ('d0000000-0000-4000-8000-0000000085d3', 'e0000000-0000-4000-8000-0000000085a3', 'f0000000-0000-4000-8000-000000008502', 'b0000000-0000-4000-8000-000000000007', 1, 0, 0, 'approved', null, null, null),
    ('d0000000-0000-4000-8000-0000000085d4', 'e0000000-0000-4000-8000-0000000085a4', null, 'b0000000-0000-4000-8000-000000000006', 2, 0, 0, 'approved', null, null, null),
    ('d0000000-0000-4000-8000-0000000085d5', 'e0000000-0000-4000-8000-0000000085a5', null, 'b0000000-0000-4000-8000-000000000006', 3, 0, 0, 're_review', null, null, null),
    ('d0000000-0000-4000-8000-0000000085e1', 'e0000000-0000-4000-8000-0000000085a6', null, 'b0000000-0000-4000-8000-000000000006', 4, 0, 0, 'rejected', null, null, null),
    ('d0000000-0000-4000-8000-0000000085e2', 'e0000000-0000-4000-8000-0000000085a6', null, 'b0000000-0000-4000-8000-000000000006', 4, 0, 0, 'cancelled', null, null, null),
    ('d0000000-0000-4000-8000-0000000085e3', 'e0000000-0000-4000-8000-0000000085a6', null, 'b0000000-0000-4000-8000-000000000006', 4, 0, 0, 'released', null, null, null),
    ('d0000000-0000-4000-8000-0000000085e4', 'e0000000-0000-4000-8000-0000000085a6', null, 'b0000000-0000-4000-8000-000000000006', 4, 0, 0, 'expired', null, null, null),
    ('d0000000-0000-4000-8000-0000000085e5', 'e0000000-0000-4000-8000-0000000085a6', null, 'b0000000-0000-4000-8000-000000000007', 4, 0, 0, 'held', (now() + interval '1 hour')::text, null, null),
    ('d0000000-0000-4000-8000-0000000085d7', 'e0000000-0000-4000-8000-0000000085a8', null, 'b0000000-0000-4000-8000-000000000006', 6, 0, 0, 'held', null, null, null),
    ('d0000000-0000-4000-8000-0000000085a1', 'e0000000-0000-4000-8000-0000000085a9', null, 'b0000000-0000-4000-8000-000000000007', 7, 0, 0, 'approved', null, null, 'affected'),
    ('d0000000-0000-4000-8000-0000000085b1', 'e0000000-0000-4000-8000-0000000085b1', null, 'b0000000-0000-4000-8000-000000000007', 8, 0, 0, 'approved', null, null, 'affected'),
    ('d0000000-0000-4000-8000-0000000085d9', 'e0000000-0000-4000-8000-0000000085b2', null, 'b0000000-0000-4000-8000-000000000006', 9, 0, 0, 'approved', null, null, null)
) as v(id, event_id, space, venue, day, setup, turnaround, status, expires_at, replaces, flag);

-- The replacements beside A's and B's affected originals, at Innovation Lab.
insert into public.venue_bookings (id, event_id, venue_id, booked_period, setup_minutes, status, expires_at, replaces_booking_id)
select v.id::uuid, v.event_id::uuid, 'b0000000-0000-4000-8000-000000000006',
       tstzrange(t.day0 + (v.day || ' days')::interval + interval '1 hour',
                 t.day0 + (v.day || ' days')::interval + interval '3 hours', '[)'),
       0, 'held', now() + interval '7 days', v.replaces::uuid
from cancel_check_times t,
(values
    ('d0000000-0000-4000-8000-0000000085a2', 'e0000000-0000-4000-8000-0000000085a9', 7, 'd0000000-0000-4000-8000-0000000085a1'),
    ('d0000000-0000-4000-8000-0000000085b2', 'e0000000-0000-4000-8000-0000000085b1', 8, 'd0000000-0000-4000-8000-0000000085b1')
) as v(id, event_id, day, replaces);

do $$
declare
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_lab uuid := 'b0000000-0000-4000-8000-000000000006';
    v_p uuid := 'e0000000-0000-4000-8000-0000000085a1';
    v_booking uuid := 'd0000000-0000-4000-8000-0000000085d1';
    v_result record;
    v_row public.venue_bookings;
    v_staff_count integer;
    v_history integer;
begin
    -- Creating the event wrote its own history row; AC8 compares against it.
    select count(*) into v_history from public.event_status_history where event_id = v_p;

    -- AC1: the held booking is cancelled.
    select * into v_result from public.cancel_venue_booking(v_booking, v_coordinator, 'Staff message.', 'Return message.');
    if v_result.outcome is distinct from 'ok' or v_result.event_id is distinct from v_p
       or v_result.from_status is distinct from 'held' then
        raise exception 'BOOKING CANCEL FAIL: a held booking was not cancelled (outcome %)', v_result.outcome;
    end if;
    select * into v_row from public.venue_bookings where id = v_booking;
    if v_row.status <> 'cancelled' then
        raise exception 'BOOKING CANCEL FAIL: the booking is % after cancelling', v_row.status;
    end if;

    -- AC1: its whole occupied window, setup and turnaround included, is free.
    if exists (select 1 from public.venue_conflicts(v_row.occupied_period, v_lab, null)) then
        raise exception 'BOOKING CANCEL FAIL: the cancelled booking still occupies its window';
    end if;
    if lower(v_row.occupied_period) >= lower(v_row.booked_period) then
        raise exception 'BOOKING CANCEL FAIL: the check booking has no setup buffer to free';
    end if;

    -- AC2: another event can now take the slot, and P can request again.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000085a2', v_lab, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'BOOKING CANCEL FAIL: the freed slot was refused to another event (outcome %)', v_result.outcome;
    end if;
    if exists (select 1 from public.venue_bookings
                where event_id = v_p and status in ('held', 'approved', 're_review')) then
        raise exception 'BOOKING CANCEL FAIL: the cancelled booking still counts as the event''s venue';
    end if;

    -- AC6: one history row with who and when.
    if (select count(*) from public.venue_booking_history
         where booking_id = v_booking and action = 'cancelled' and from_status = 'held'
           and to_status = 'cancelled' and actor_id = v_coordinator and created_at is not null) <> 1 then
        raise exception 'BOOKING CANCEL FAIL: the cancellation was not recorded once with its actor';
    end if;

    -- AC1: every venue staff account but the actor is told, once.
    select count(*) into v_staff_count from public.user_roles where role = 'venue_staff' and profile_id <> v_coordinator;
    if v_staff_count = 0
       or (select count(*) from public.notifications
            where event_id = v_p and type = 'venue_booking_cancelled' and message = 'Staff message.') <> v_staff_count
       or exists (select 1 from public.notifications
                   where event_id = v_p and type = 'venue_booking_cancelled' and recipient_id = v_coordinator) then
        raise exception 'BOOKING CANCEL FAIL: venue staff were not each told once, or the actor was told';
    end if;

    -- AC8: a planning event stays in planning, with no history row.
    if (select status from public.events where id = v_p) <> 'planning'
       or (select count(*) from public.event_status_history where event_id = v_p) <> v_history then
        raise exception 'BOOKING CANCEL FAIL: cancelling changed a planning event''s status';
    end if;

    -- AC9: a second cancel (a double-click) is refused; still one history row.
    select * into v_result from public.cancel_venue_booking(v_booking, v_coordinator, 'x', 'x');
    if v_result.outcome is distinct from 'not_cancellable' or v_result.from_status is distinct from 'cancelled' then
        raise exception 'BOOKING CANCEL FAIL: a second cancel was not refused (outcome %)', v_result.outcome;
    end if;
    if (select count(*) from public.venue_booking_history where booking_id = v_booking) <> 1 then
        raise exception 'BOOKING CANCEL FAIL: a second cancel wrote history';
    end if;
end;
$$;

do $$
declare
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_c uuid := 'e0000000-0000-4000-8000-0000000085a3';
    v_s uuid := 'e0000000-0000-4000-8000-0000000085a4';
    v_z uuid := 'e0000000-0000-4000-8000-0000000085b2';
    v_version integer;
    v_result record;
begin
    -- AC4, AC7, AC8: a Confirmed event goes back to Planning when one of its
    -- two bookings is cancelled; the other is untouched.
    select version into v_version from public.events where id = v_c;
    select * into v_result from public.cancel_venue_booking(
        'd0000000-0000-4000-8000-0000000085d2', v_coordinator, 'x', 'C returned to planning.');
    if v_result.outcome is distinct from 'ok' or v_result.from_status is distinct from 'approved' then
        raise exception 'BOOKING CANCEL FAIL: an approved booking was not cancelled (outcome %)', v_result.outcome;
    end if;
    if (select status from public.events where id = v_c) <> 'planning'
       or (select version from public.events where id = v_c) <> v_version + 1 then
        raise exception 'BOOKING CANCEL FAIL: the Confirmed event did not return to Planning';
    end if;
    -- AC6: the return is in the event's history.
    if (select count(*) from public.event_status_history
         where event_id = v_c and from_status = 'confirmed' and to_status = 'planning') <> 1 then
        raise exception 'BOOKING CANCEL FAIL: the return to Planning was not recorded in the event history';
    end if;
    if (select count(*) from public.notifications
         where event_id = v_c and type = 'event_returned_to_planning' and recipient_id = v_coordinator
           and message = 'C returned to planning.') <> 1 then
        raise exception 'BOOKING CANCEL FAIL: the coordinator was not told the event returned to Planning';
    end if;
    if (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000085d3') <> 'approved'
       or exists (select 1 from public.venue_booking_history where booking_id = 'd0000000-0000-4000-8000-0000000085d3') then
        raise exception 'BOOKING CANCEL FAIL: cancelling one booking changed the event''s other booking';
    end if;

    -- AC4: an event in Safety review returns to Planning and the officers are told.
    select * into v_result from public.cancel_venue_booking(
        'd0000000-0000-4000-8000-0000000085d4', v_coordinator, 'x', 'S returned to planning.');
    if v_result.outcome is distinct from 'ok' or (select status from public.events where id = v_s) <> 'planning' then
        raise exception 'BOOKING CANCEL FAIL: the Safety review event did not return to Planning';
    end if;
    if exists (select 1 from public.user_roles ur
                where ur.role = 'safety_officer' and ur.profile_id <> v_coordinator
                  and not exists (select 1 from public.notifications n
                                   where n.event_id = v_s and n.recipient_id = ur.profile_id
                                     and n.type = 'event_returned_to_planning')) then
        raise exception 'BOOKING CANCEL FAIL: a Safety Officer was not told the event left review';
    end if;

    -- AC4: Preparation returns to Planning too.
    select * into v_result from public.cancel_venue_booking(
        'd0000000-0000-4000-8000-0000000085d9', v_coordinator, 'x', 'Z returned to planning.');
    if v_result.outcome is distinct from 'ok' or (select status from public.events where id = v_z) <> 'planning' then
        raise exception 'BOOKING CANCEL FAIL: the Preparation event did not return to Planning';
    end if;

    -- [Assumption]: a booking under re-review can be cancelled.
    select * into v_result from public.cancel_venue_booking(
        'd0000000-0000-4000-8000-0000000085d5', v_coordinator, 'x', 'x');
    if v_result.outcome is distinct from 'ok' or v_result.from_status is distinct from 're_review' then
        raise exception 'BOOKING CANCEL FAIL: a re-review booking was not cancelled (outcome %)', v_result.outcome;
    end if;
end;
$$;

do $$
declare
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_id uuid;
    v_result record;
    v_starts timestamptz;
begin
    -- AC3: rejected, cancelled, released and expired can't be cancelled.
    foreach v_id in array array['d0000000-0000-4000-8000-0000000085e1', 'd0000000-0000-4000-8000-0000000085e2',
                                'd0000000-0000-4000-8000-0000000085e3', 'd0000000-0000-4000-8000-0000000085e4']::uuid[] loop
        select * into v_result from public.cancel_venue_booking(v_id, v_coordinator, 'x', 'x');
        if v_result.outcome is distinct from 'not_cancellable' then
            raise exception 'BOOKING CANCEL FAIL: booking % was not refused (outcome %)', v_id, v_result.outcome;
        end if;
    end loop;

    -- CR-99: a hold past its expiry is expired, not cancelled. Its clock is only
    -- two hours on, since the guard expires every hold due by then.
    select * into v_result from public.cancel_venue_booking(
        'd0000000-0000-4000-8000-0000000085e5', v_coordinator, 'x', 'x', now() + interval '2 hours');
    if v_result.outcome is distinct from 'hold_expired'
       or (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000085e5') <> 'expired' then
        raise exception 'BOOKING CANCEL FAIL: a hold past its expiry was not refused as expired (outcome %)', v_result.outcome;
    end if;

    -- AC10: not once the event has started (to the second), nor once it is cancelled.
    select starts_at into v_starts from public.events where id = 'e0000000-0000-4000-8000-0000000085a3';
    select * into v_result from public.cancel_venue_booking(
        'd0000000-0000-4000-8000-0000000085d3', v_coordinator, 'x', 'x', v_starts);
    if v_result.outcome is distinct from 'event_closed' then
        raise exception 'BOOKING CANCEL FAIL: a booking was cancelled at its event''s start (outcome %)', v_result.outcome;
    end if;
    select * into v_result from public.cancel_venue_booking(
        'd0000000-0000-4000-8000-0000000085d3', v_coordinator, 'x', 'x', v_starts - interval '1 second');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'BOOKING CANCEL FAIL: a booking a second before its event started was refused (outcome %)', v_result.outcome;
    end if;
    update public.venue_bookings set status = 'approved' where id = 'd0000000-0000-4000-8000-0000000085e5';
    update public.events set status = 'cancelled' where id = 'e0000000-0000-4000-8000-0000000085a6';
    select * into v_result from public.cancel_venue_booking(
        'd0000000-0000-4000-8000-0000000085e5', v_coordinator, 'x', 'x');
    if v_result.outcome is distinct from 'event_closed' then
        raise exception 'BOOKING CANCEL FAIL: a cancelled event''s booking was cancelled (outcome %)', v_result.outcome;
    end if;

    -- AC5: only the assigned coordinator.
    select * into v_result from public.cancel_venue_booking(
        'd0000000-0000-4000-8000-0000000085d7', v_coordinator, 'x', 'x');
    if v_result.outcome is distinct from 'not_assigned'
       or (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000085d7') <> 'held' then
        raise exception 'BOOKING CANCEL FAIL: a coordinator cancelled another''s booking (outcome %)', v_result.outcome;
    end if;

    select * into v_result from public.cancel_venue_booking(
        'd0000000-0000-4000-8000-0000000085ff', v_coordinator, 'x', 'x');
    if v_result.outcome is distinct from 'booking_not_found' then
        raise exception 'BOOKING CANCEL FAIL: an unknown booking was not reported (outcome %)', v_result.outcome;
    end if;

    -- CR-95: cancelling a pending replacement leaves the affected original as it was.
    select * into v_result from public.cancel_venue_booking(
        'd0000000-0000-4000-8000-0000000085a2', v_coordinator, 'x', 'x');
    if v_result.outcome is distinct from 'ok'
       or (select (status, flag)::text from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000085a1')
          <> '(approved,affected)' then
        raise exception 'BOOKING CANCEL FAIL: cancelling a replacement changed its original (outcome %)', v_result.outcome;
    end if;

    -- AC1: cancelling the affected original leaves its pending replacement standing.
    select * into v_result from public.cancel_venue_booking(
        'd0000000-0000-4000-8000-0000000085b1', v_coordinator, 'x', 'x');
    if v_result.outcome is distinct from 'ok'
       or (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000085b2') <> 'held' then
        raise exception 'BOOKING CANCEL FAIL: cancelling an original changed its replacement (outcome %)', v_result.outcome;
    end if;

    -- API-only (ADR-0002).
    if has_function_privilege('anon', 'public.cancel_venue_booking(uuid, uuid, text, text, timestamptz)', 'execute')
       or has_function_privilege('authenticated', 'public.cancel_venue_booking(uuid, uuid, text, text, timestamptz)', 'execute')
       or not has_function_privilege('service_role', 'public.cancel_venue_booking(uuid, uuid, text, text, timestamptz)', 'execute') then
        raise exception 'BOOKING CANCEL FAIL: cancel_venue_booking is callable by a role other than service_role';
    end if;
end;
$$;

-- Reached only if every block above passed (a failed assertion aborts the run).
select 'BOOKING CANCEL CHECKS PASSED' as result;

rollback;
