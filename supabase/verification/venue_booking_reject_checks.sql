-- SCRUM-38 venue staff reject a booking request: the real reject_venue_booking
-- function, the booking's history and its row-level security. Needs CR-99
-- (hold expiry, venue_booking_history) applied first.
-- Run with `supabase db query --linked -f` or `psql "$DATABASE_URL" -f`. Raises
-- on the first failure and prints BOOKING REJECT CHECKS PASSED otherwise.
-- Everything runs inside `begin; ... rollback;`, so the throwaway events,
-- bookings, history, notifications and account leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002, who also holds
-- venue_staff), venue staff (…0003) and venues Grand Ballroom (…0001),
-- Innovation Lab (…0006) and Heritage Hall (…0007), in April 2031, far enough
-- ahead that nothing real is booked.

begin;

-- A throwaway coordinator who also holds attendee, to prove the history
-- policy follows the session's active role (SCRUM-76).
insert into auth.users (id, instance_id, aud, role, email, raw_user_meta_data, created_at, updated_at)
values ('c0000000-0000-4000-8000-0000000038b1', '00000000-0000-0000-0000-000000000000', 'authenticated',
        'authenticated', 'verify.reject.coordinator@connectsphere.dev', '{"full_name":"Verify Reject Coordinator"}',
        now(), now());
insert into public.user_roles (profile_id, role) values
    ('c0000000-0000-4000-8000-0000000038b1', 'event_coordinator'),
    ('c0000000-0000-4000-8000-0000000038b1', 'attendee')
on conflict do nothing;
update public.profiles set role = 'event_coordinator' where id = 'c0000000-0000-4000-8000-0000000038b1';
insert into auth.sessions (id, user_id, created_at, updated_at) values
    ('c0000000-0000-4000-8000-0000000038c1', 'c0000000-0000-4000-8000-0000000038b1', now(), now());
insert into public.session_active_roles (session_id, profile_id, role) values
    ('c0000000-0000-4000-8000-0000000038c1', 'c0000000-0000-4000-8000-0000000038b1', 'attendee');

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    -- A: the booking that gets rejected.
    ('e0000000-0000-4000-8000-0000000038a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Reject check A (rolled back)',
     '2031-04-10 14:00+08', '2031-04-10 17:00+08'),
    -- B: another event's hold, which must not change (AC8).
    ('e0000000-0000-4000-8000-0000000038a2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Reject check B (rolled back)',
     '2031-04-10 14:00+08', '2031-04-10 17:00+08'),
    -- C: wants A's slot once it is freed (AC5).
    ('e0000000-0000-4000-8000-0000000038a3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Reject check C (rolled back)',
     '2031-04-10 15:00+08', '2031-04-10 16:00+08'),
    -- D: no assigned coordinator, so nobody is notified.
    ('e0000000-0000-4000-8000-0000000038a4', 'a0000000-0000-4000-8000-000000000001',
     null, 'planning', 'Reject check D, unassigned (rolled back)',
     '2031-04-11 09:00+08', '2031-04-11 10:00+08'),
    -- E: coordinated by the throwaway account (history RLS).
    ('e0000000-0000-4000-8000-0000000038a5', 'a0000000-0000-4000-8000-000000000001',
     'c0000000-0000-4000-8000-0000000038b1', 'planning', 'Reject check E (rolled back)',
     '2031-04-11 11:00+08', '2031-04-11 12:00+08'),
    -- F and G: one booking in each status that can't be rejected (AC9). The two
    -- occupying ones sit on different events, because CR-98 allows one active
    -- booking per event space.
    ('e0000000-0000-4000-8000-0000000038a6', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Reject check F (rolled back)',
     '2031-04-12 09:00+08', '2031-04-12 10:00+08'),
    ('e0000000-0000-4000-8000-0000000038a7', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Reject check G (rolled back)',
     '2031-04-12 09:00+08', '2031-04-12 10:00+08'),
    -- H: a hold already past its expiry that the job hasn't reached yet (CR-99).
    ('e0000000-0000-4000-8000-0000000038a8', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Reject check H (rolled back)',
     '2031-04-13 09:00+08', '2031-04-13 10:00+08');

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, requested_by) values
    ('d0000000-0000-4000-8000-0000000038d1', 'e0000000-0000-4000-8000-0000000038a1',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-04-10 14:00+08', '2031-04-10 17:00+08', '[)'),
     'held', 'a0000000-0000-4000-8000-000000000002'),
    ('d0000000-0000-4000-8000-0000000038d2', 'e0000000-0000-4000-8000-0000000038a2',
     'b0000000-0000-4000-8000-000000000007', tstzrange('2031-04-10 14:00+08', '2031-04-10 17:00+08', '[)'),
     'held', 'a0000000-0000-4000-8000-000000000002'),
    ('d0000000-0000-4000-8000-0000000038d4', 'e0000000-0000-4000-8000-0000000038a4',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-04-11 09:00+08', '2031-04-11 10:00+08', '[)'),
     'held', null),
    ('d0000000-0000-4000-8000-0000000038d5', 'e0000000-0000-4000-8000-0000000038a5',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-04-11 11:00+08', '2031-04-11 12:00+08', '[)'),
     'held', 'c0000000-0000-4000-8000-0000000038b1'),
    -- Different venues and hours so the occupying ones don't trip DB-1.
    ('d0000000-0000-4000-8000-0000000038e1', 'e0000000-0000-4000-8000-0000000038a6',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-04-12 09:00+08', '2031-04-12 10:00+08', '[)'), 'approved', null),
    ('d0000000-0000-4000-8000-0000000038e2', 'e0000000-0000-4000-8000-0000000038a7',
     'b0000000-0000-4000-8000-000000000007', tstzrange('2031-04-12 09:00+08', '2031-04-12 10:00+08', '[)'), 're_review', null),
    ('d0000000-0000-4000-8000-0000000038e3', 'e0000000-0000-4000-8000-0000000038a6',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-04-12 09:00+08', '2031-04-12 10:00+08', '[)'), 'rejected', null),
    ('d0000000-0000-4000-8000-0000000038e4', 'e0000000-0000-4000-8000-0000000038a6',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-04-12 09:00+08', '2031-04-12 10:00+08', '[)'), 'cancelled', null),
    ('d0000000-0000-4000-8000-0000000038e5', 'e0000000-0000-4000-8000-0000000038a6',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-04-12 09:00+08', '2031-04-12 10:00+08', '[)'), 'released', null),
    ('d0000000-0000-4000-8000-0000000038e6', 'e0000000-0000-4000-8000-0000000038a6',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-04-12 09:00+08', '2031-04-12 10:00+08', '[)'), 'expired', null);

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, expires_at) values
    ('d0000000-0000-4000-8000-0000000038f1', 'e0000000-0000-4000-8000-0000000038a8',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-04-13 09:00+08', '2031-04-13 10:00+08', '[)'),
     'held', now() - interval '1 minute');

do $$
declare
    v_a uuid := 'e0000000-0000-4000-8000-0000000038a1';
    v_booking uuid := 'd0000000-0000-4000-8000-0000000038d1';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_lab uuid := 'b0000000-0000-4000-8000-000000000006';
    v_result record;
    v_row public.venue_bookings;
    v_status public.venue_booking_status;
begin
    -- AC2, AC3, AC4: venue staff reject a held booking with a reason and a
    -- suggestion, both trimmed, and the decision is recorded on the booking.
    select * into v_result from public.reject_venue_booking(
        v_booking, v_staff, '  Capacity exceeded  ', '  Try Heritage Hall  ', 'A booking was rejected.');
    if v_result.outcome is distinct from 'ok' or v_result.event_id is distinct from v_a
       or v_result.from_status is distinct from 'held' then
        raise exception 'BOOKING REJECT FAIL: a held booking was not rejected (outcome %)', v_result.outcome;
    end if;
    select * into v_row from public.venue_bookings where id = v_booking;
    if v_row.status <> 'rejected'
       or v_row.decision_reason is distinct from 'Capacity exceeded'
       or v_row.suggestion_note is distinct from 'Try Heritage Hall'
       or v_row.decided_by is distinct from v_staff
       or v_row.decided_at is null then
        raise exception 'BOOKING REJECT FAIL: the booking does not carry the trimmed decision, decider and time';
    end if;

    -- AC12: one history row, with who, when, the reason and the suggestion.
    if (select count(*) from public.venue_booking_history
         where booking_id = v_booking and action = 'rejected' and from_status = 'held' and to_status = 'rejected'
           and actor_id = v_staff and reason = 'Capacity exceeded' and suggestion_note = 'Try Heritage Hall'
           and created_at is not null) <> 1
       or (select count(*) from public.venue_booking_history where booking_id = v_booking) <> 1 then
        raise exception 'BOOKING REJECT FAIL: the rejection did not write exactly one history row';
    end if;

    -- AC4: the assigned coordinator is told, once; the venue staff actor isn't.
    if (select count(*) from public.notifications
         where event_id = v_a and type = 'venue_booking_rejected'
           and recipient_id = v_coordinator and message = 'A booking was rejected.') <> 1
       or (select count(*) from public.notifications where event_id = v_a and type = 'venue_booking_rejected') <> 1 then
        raise exception 'BOOKING REJECT FAIL: the assigned coordinator was not the only one notified, exactly once';
    end if;

    -- AC8: event B's booking is untouched.
    if (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000038d2') <> 'held' then
        raise exception 'BOOKING REJECT FAIL: rejecting one booking changed another';
    end if;

    -- AC5: the slot is free, so event C can now hold Innovation Lab for an overlapping time.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000038a3', v_lab, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'BOOKING REJECT FAIL: the rejected slot is still occupied (outcome %)', v_result.outcome;
    end if;

    -- AC7: event A stays in planning and can request another venue.
    if (select status from public.events where id = v_a) <> 'planning' then
        raise exception 'BOOKING REJECT FAIL: rejecting the booking changed the event status';
    end if;
    select * into v_result from public.request_venue_booking(
        v_a, 'b0000000-0000-4000-8000-000000000001', v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'BOOKING REJECT FAIL: the event cannot request another venue after a rejection (outcome %)', v_result.outcome;
    end if;

    -- AC9 (CR-99): a hold past its expiry is expired, not rejected. The
    -- expiry is what is saved, by the system, and the rejection is refused.
    select * into v_result from public.reject_venue_booking(
        'd0000000-0000-4000-8000-0000000038f1', v_staff, 'Not suitable', null, 'x');
    if v_result.outcome is distinct from 'hold_expired' or v_result.from_status is distinct from 'expired' then
        raise exception 'BOOKING REJECT FAIL: a hold past its expiry was not refused as hold_expired (outcome %)', v_result.outcome;
    end if;
    if (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000038f1') <> 'expired'
       or exists (select 1 from public.venue_booking_history
                   where booking_id = 'd0000000-0000-4000-8000-0000000038f1' and action = 'rejected')
       or (select decided_by from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000038f1') is not null then
        raise exception 'BOOKING REJECT FAIL: an expired hold carries a rejection';
    end if;

    -- AC9, AC10: a booking that is no longer held is refused and left as it is,
    -- including one rejected a moment ago.
    select * into v_result from public.reject_venue_booking(v_booking, v_staff, 'Again', null, 'x');
    if v_result.outcome is distinct from 'not_held' or v_result.from_status is distinct from 'rejected' then
        raise exception 'BOOKING REJECT FAIL: a second rejection was not refused as not_held (outcome %)', v_result.outcome;
    end if;
    if (select count(*) from public.venue_booking_history where booking_id = v_booking and action = 'rejected') <> 1
       or (select decision_reason from public.venue_bookings where id = v_booking) <> 'Capacity exceeded' then
        raise exception 'BOOKING REJECT FAIL: a refused rejection changed the booking or its history';
    end if;
    foreach v_status in array array['approved', 're_review', 'rejected', 'cancelled', 'released', 'expired']::public.venue_booking_status[] loop
        select * into v_result from public.reject_venue_booking(
            (select id from public.venue_bookings
              where event_id in ('e0000000-0000-4000-8000-0000000038a6', 'e0000000-0000-4000-8000-0000000038a7')
                and status = v_status),
            v_staff, 'Not suitable', null, 'x');
        if v_result.outcome is distinct from (case when v_status = 'expired' then 'hold_expired' else 'not_held' end)
           or v_result.from_status is distinct from v_status then
            raise exception 'BOOKING REJECT FAIL: a % booking was not refused as not_held (outcome %)', v_status, v_result.outcome;
        end if;
    end loop;
    if exists (select 1 from public.venue_booking_history h
                join public.venue_bookings vb on vb.id = h.booking_id
                where vb.event_id in ('e0000000-0000-4000-8000-0000000038a6', 'e0000000-0000-4000-8000-0000000038a7'))
       or (select count(*) from public.venue_bookings
            where event_id in ('e0000000-0000-4000-8000-0000000038a6', 'e0000000-0000-4000-8000-0000000038a7')
              and decided_by is not null) <> 0 then
        raise exception 'BOOKING REJECT FAIL: a refused rejection left a decision or history behind';
    end if;

    -- AC2: a blank or over-long reason, or an over-long suggestion, is refused
    -- by the function as well as the API, and changes nothing.
    select * into v_result from public.reject_venue_booking(
        'd0000000-0000-4000-8000-0000000038d2', v_staff, '   ', null, 'x');
    if v_result.outcome is distinct from 'invalid_reason' then
        raise exception 'BOOKING REJECT FAIL: a blank reason was not refused (outcome %)', v_result.outcome;
    end if;
    select * into v_result from public.reject_venue_booking(
        'd0000000-0000-4000-8000-0000000038d2', v_staff, repeat('x', 1001), null, 'x');
    if v_result.outcome is distinct from 'invalid_reason' then
        raise exception 'BOOKING REJECT FAIL: a 1001-character reason was not refused (outcome %)', v_result.outcome;
    end if;
    select * into v_result from public.reject_venue_booking(
        'd0000000-0000-4000-8000-0000000038d2', v_staff, 'Fine', repeat('x', 1001), 'x');
    if v_result.outcome is distinct from 'invalid_suggestion' then
        raise exception 'BOOKING REJECT FAIL: a 1001-character suggestion was not refused (outcome %)', v_result.outcome;
    end if;
    if (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000038d2') <> 'held' then
        raise exception 'BOOKING REJECT FAIL: an invalid rejection changed the booking';
    end if;

    -- Unknown ids come back as an outcome, not an error.
    select * into v_result from public.reject_venue_booking(
        'd0000000-0000-4000-8000-0000000038ff', v_staff, 'Fine', null, 'x');
    if v_result.outcome is distinct from 'booking_not_found' then
        raise exception 'BOOKING REJECT FAIL: an unknown booking was not reported as booking_not_found (outcome %)', v_result.outcome;
    end if;

    -- An event with no coordinator: the rejection stands and nobody is notified.
    select * into v_result from public.reject_venue_booking(
        'd0000000-0000-4000-8000-0000000038d4', v_staff, 'Closed that morning', null, 'x');
    if v_result.outcome is distinct from 'ok'
       or exists (select 1 from public.notifications where event_id = 'e0000000-0000-4000-8000-0000000038a4') then
        raise exception 'BOOKING REJECT FAIL: an unassigned event''s rejection failed or notified someone';
    end if;

    -- The coordinator who also holds venue_staff rejects a booking on their
    -- own event: they are not notified of their own action (NT-R1).
    select * into v_result from public.reject_venue_booking(
        'd0000000-0000-4000-8000-0000000038d2', v_coordinator, 'Clash with setup', null, 'x');
    if v_result.outcome is distinct from 'ok'
       or exists (select 1 from public.notifications
                   where event_id = 'e0000000-0000-4000-8000-0000000038a2' and type = 'venue_booking_rejected') then
        raise exception 'BOOKING REJECT FAIL: the actor was notified of their own rejection';
    end if;

    -- E's booking is rejected so the history policy below has a row to show.
    select * into v_result from public.reject_venue_booking(
        'd0000000-0000-4000-8000-0000000038d5', v_staff, 'Under repair', null, 'x');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'BOOKING REJECT FAIL: event E''s booking was not rejected (outcome %)', v_result.outcome;
    end if;

    -- API-only (ADR-0002): browsers and the publishable key can't call it.
    if has_function_privilege('anon', 'public.reject_venue_booking(uuid, uuid, text, text, text)', 'execute')
       or has_function_privilege('authenticated', 'public.reject_venue_booking(uuid, uuid, text, text, text)', 'execute')
       or not has_function_privilege('service_role', 'public.reject_venue_booking(uuid, uuid, text, text, text)', 'execute') then
        raise exception 'BOOKING REJECT FAIL: reject_venue_booking is callable by a role other than service_role';
    end if;
end;
$$;

-- History RLS (CR-99's policy; a safety net, since the API uses the secret key).
-- Internal staff acting as venue staff or coordinator read it; the organiser
-- reads none (AC6); a coordinator acting as attendee reads none (SCRUM-76).
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000003","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.venue_booking_history
         where booking_id in ('d0000000-0000-4000-8000-0000000038d1', 'd0000000-0000-4000-8000-0000000038d5')) <> 2 then
        raise exception 'BOOKING REJECT FAIL: venue staff cannot read booking history';
    end if;
end $$;
reset role;

select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if exists (select 1 from public.venue_booking_history
                where booking_id in ('d0000000-0000-4000-8000-0000000038d1', 'd0000000-0000-4000-8000-0000000038d5')) then
        raise exception 'BOOKING REJECT FAIL: the organiser can read booking history (AC6)';
    end if;
end $$;
reset role;

-- The throwaway coordinator, un-switched: reads event E's history.
select set_config('request.jwt.claims', '{"sub":"c0000000-0000-4000-8000-0000000038b1","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.venue_booking_history where booking_id = 'd0000000-0000-4000-8000-0000000038d5') <> 1 then
        raise exception 'BOOKING REJECT FAIL: a coordinator acting as coordinator cannot read booking history';
    end if;
end $$;
reset role;

-- The same coordinator with a session acting as attendee: reads nothing (SCRUM-76).
select set_config('request.jwt.claims',
    '{"sub":"c0000000-0000-4000-8000-0000000038b1","role":"authenticated","session_id":"c0000000-0000-4000-8000-0000000038c1"}', true);
set local role authenticated;
do $$
begin
    if exists (select 1 from public.venue_booking_history where booking_id = 'd0000000-0000-4000-8000-0000000038d5') then
        raise exception 'BOOKING REJECT FAIL: a coordinator acting as attendee can read booking history';
    end if;
end $$;
reset role;

-- Reached only if every block above passed (a failed assertion aborts the run).
select 'BOOKING REJECT CHECKS PASSED' as result;

rollback;
