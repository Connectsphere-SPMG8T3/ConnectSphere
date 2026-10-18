-- SCRUM-36 venue staff approve a booking request: the real approve_venue_booking
-- function, the booking's history, DB-1 after approval, and the shared lock with
-- reject_venue_booking and CR-95's restore_affected_booking, and the release of
-- the booking a replacement replaces. Needs CR-99, SCRUM-38, SCRUM-64, SCRUM-21
-- and CR-95 applied first.
-- Run with `supabase db query --linked -f` or `psql "$DATABASE_URL" -f`. Raises
-- on the first failure and prints BOOKING APPROVE CHECKS PASSED otherwise.
-- Everything runs inside `begin; ... rollback;`, so the throwaway events,
-- spaces, bookings, blocks, history, notifications and the venue deactivation
-- leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002, who also holds
-- venue_staff), venue staff (…0003) and venues Grand Ballroom (…0001),
-- Innovation Lab (…0006) and Heritage Hall (…0007), in May 2031, far enough
-- ahead that nothing real is booked.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    -- A: the booking that gets approved.
    ('e0000000-0000-4000-8000-0000000036a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Approve check A (rolled back)',
     '2031-05-10 14:00+08', '2031-05-10 17:00+08'),
    -- C: wants A's slot once A is approved (AC5).
    ('e0000000-0000-4000-8000-0000000036a3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Approve check C (rolled back)',
     '2031-05-10 16:00+08', '2031-05-10 18:00+08'),
    -- M: a multi-venue event with two spaces (AC7).
    ('e0000000-0000-4000-8000-0000000036a4', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Approve check M, two venues (rolled back)',
     '2031-05-11 09:00+08', '2031-05-11 10:00+08'),
    -- B: a block is saved over its hold (AC3).
    ('e0000000-0000-4000-8000-0000000036a5', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Approve check B (rolled back)',
     '2031-05-12 09:00+08', '2031-05-12 10:00+08'),
    -- D: its venue is deactivated (AC4).
    ('e0000000-0000-4000-8000-0000000036a6', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Approve check D (rolled back)',
     '2031-05-13 09:00+08', '2031-05-13 10:00+08'),
    -- R: rejected first, then approval is tried (AC9).
    ('e0000000-0000-4000-8000-0000000036a7', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Approve check R (rolled back)',
     '2031-05-14 09:00+08', '2031-05-14 10:00+08'),
    -- F and G: one booking in each status that can't be approved (AC6).
    ('e0000000-0000-4000-8000-0000000036a8', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Approve check F (rolled back)',
     '2031-05-15 09:00+08', '2031-05-15 10:00+08'),
    ('e0000000-0000-4000-8000-0000000036a9', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Approve check G (rolled back)',
     '2031-05-15 09:00+08', '2031-05-15 10:00+08'),
    -- H: a hold already past its expiry that the job hasn't reached yet (AC6).
    ('e0000000-0000-4000-8000-0000000036b1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Approve check H (rolled back)',
     '2031-05-16 09:00+08', '2031-05-16 10:00+08'),
    -- U: no assigned coordinator, so nobody is notified.
    ('e0000000-0000-4000-8000-0000000036b2', 'a0000000-0000-4000-8000-000000000001',
     null, 'planning', 'Approve check U, unassigned (rolled back)',
     '2031-05-17 09:00+08', '2031-05-17 10:00+08'),
    -- S: approved by its own coordinator acting as venue staff (NT-R1).
    ('e0000000-0000-4000-8000-0000000036b3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Approve check S (rolled back)',
     '2031-05-18 09:00+08', '2031-05-18 10:00+08'),
    -- P, Q, T: an affected original at Heritage Hall and its replacement at
    -- Innovation Lab (CR-95). P is approved; Q is restored first; T is
    -- approved, then restore is tried.
    ('e0000000-0000-4000-8000-0000000036b7', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Approve check P, replacement (rolled back)',
     '2031-05-27 09:00+08', '2031-05-27 10:00+08'),
    ('e0000000-0000-4000-8000-0000000036b8', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Approve check Q, restored first (rolled back)',
     '2031-05-28 09:00+08', '2031-05-28 10:00+08'),
    ('e0000000-0000-4000-8000-0000000036b9', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Approve check T, approved first (rolled back)',
     '2031-05-29 09:00+08', '2031-05-29 10:00+08');

insert into public.event_space_requests (id, event_id, label, expected_pax) values
    ('f0000000-0000-4000-8000-000000003601', 'e0000000-0000-4000-8000-0000000036a4', 'Plenary', 80),
    ('f0000000-0000-4000-8000-000000003602', 'e0000000-0000-4000-8000-0000000036a4', 'Breakout', 20);

insert into public.venue_bookings (id, event_id, event_space_request_id, venue_id, occupied_period, status, requested_by) values
    ('d0000000-0000-4000-8000-0000000036d1', 'e0000000-0000-4000-8000-0000000036a1', null,
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-05-10 14:00+08', '2031-05-10 17:00+08', '[)'),
     'held', 'a0000000-0000-4000-8000-000000000002'),
    ('d0000000-0000-4000-8000-0000000036c4', 'e0000000-0000-4000-8000-0000000036a4', 'f0000000-0000-4000-8000-000000003601',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-05-11 09:00+08', '2031-05-11 10:00+08', '[)'),
     'held', 'a0000000-0000-4000-8000-000000000002'),
    ('d0000000-0000-4000-8000-0000000036c5', 'e0000000-0000-4000-8000-0000000036a4', 'f0000000-0000-4000-8000-000000003602',
     'b0000000-0000-4000-8000-000000000007', tstzrange('2031-05-11 09:00+08', '2031-05-11 10:00+08', '[)'),
     'held', 'a0000000-0000-4000-8000-000000000002'),
    ('d0000000-0000-4000-8000-0000000036b5', 'e0000000-0000-4000-8000-0000000036a5', null,
     'b0000000-0000-4000-8000-000000000007', tstzrange('2031-05-12 09:00+08', '2031-05-12 10:00+08', '[)'),
     'held', 'a0000000-0000-4000-8000-000000000002'),
    ('d0000000-0000-4000-8000-0000000036b6', 'e0000000-0000-4000-8000-0000000036a6', null,
     'b0000000-0000-4000-8000-000000000001', tstzrange('2031-05-13 09:00+08', '2031-05-13 10:00+08', '[)'),
     'held', 'a0000000-0000-4000-8000-000000000002'),
    ('d0000000-0000-4000-8000-0000000036b7', 'e0000000-0000-4000-8000-0000000036a7', null,
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-05-14 09:00+08', '2031-05-14 10:00+08', '[)'),
     'held', 'a0000000-0000-4000-8000-000000000002'),
    ('d0000000-0000-4000-8000-0000000036c2', 'e0000000-0000-4000-8000-0000000036b2', null,
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-05-17 09:00+08', '2031-05-17 10:00+08', '[)'),
     'held', null),
    ('d0000000-0000-4000-8000-0000000036c3', 'e0000000-0000-4000-8000-0000000036b3', null,
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-05-18 09:00+08', '2031-05-18 10:00+08', '[)'),
     'held', 'a0000000-0000-4000-8000-000000000002'),
    -- Different venues so the two occupying ones don't trip DB-1; the rest don't occupy.
    ('d0000000-0000-4000-8000-0000000036e1', 'e0000000-0000-4000-8000-0000000036a8', null,
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-05-15 09:00+08', '2031-05-15 10:00+08', '[)'), 'approved', null),
    ('d0000000-0000-4000-8000-0000000036e2', 'e0000000-0000-4000-8000-0000000036a9', null,
     'b0000000-0000-4000-8000-000000000007', tstzrange('2031-05-15 09:00+08', '2031-05-15 10:00+08', '[)'), 're_review', null),
    ('d0000000-0000-4000-8000-0000000036e3', 'e0000000-0000-4000-8000-0000000036a8', null,
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-05-15 09:00+08', '2031-05-15 10:00+08', '[)'), 'rejected', null),
    ('d0000000-0000-4000-8000-0000000036e4', 'e0000000-0000-4000-8000-0000000036a8', null,
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-05-15 09:00+08', '2031-05-15 10:00+08', '[)'), 'cancelled', null),
    ('d0000000-0000-4000-8000-0000000036e5', 'e0000000-0000-4000-8000-0000000036a8', null,
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-05-15 09:00+08', '2031-05-15 10:00+08', '[)'), 'released', null),
    ('d0000000-0000-4000-8000-0000000036e6', 'e0000000-0000-4000-8000-0000000036a8', null,
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-05-15 09:00+08', '2031-05-15 10:00+08', '[)'), 'expired', null);

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, flag, flag_reason, flagged_at) values
    ('d0000000-0000-4000-8000-0000000036a7', 'e0000000-0000-4000-8000-0000000036b7', 'b0000000-0000-4000-8000-000000000007',
     tstzrange('2031-05-27 09:00+08', '2031-05-27 10:00+08', '[)'), 'approved', 'affected', 'Approve check', now()),
    ('d0000000-0000-4000-8000-0000000036a8', 'e0000000-0000-4000-8000-0000000036b8', 'b0000000-0000-4000-8000-000000000007',
     tstzrange('2031-05-28 09:00+08', '2031-05-28 10:00+08', '[)'), 'approved', 'affected', 'Approve check', now()),
    ('d0000000-0000-4000-8000-0000000036a9', 'e0000000-0000-4000-8000-0000000036b9', 'b0000000-0000-4000-8000-000000000007',
     tstzrange('2031-05-29 09:00+08', '2031-05-29 10:00+08', '[)'), 'approved', 'affected', 'Approve check', now());

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, replaces_booking_id) values
    ('d0000000-0000-4000-8000-0000000036f7', 'e0000000-0000-4000-8000-0000000036b7', 'b0000000-0000-4000-8000-000000000006',
     tstzrange('2031-05-27 09:00+08', '2031-05-27 10:00+08', '[)'), 'held', 'd0000000-0000-4000-8000-0000000036a7'),
    ('d0000000-0000-4000-8000-0000000036f8', 'e0000000-0000-4000-8000-0000000036b8', 'b0000000-0000-4000-8000-000000000006',
     tstzrange('2031-05-28 09:00+08', '2031-05-28 10:00+08', '[)'), 'held', 'd0000000-0000-4000-8000-0000000036a8'),
    ('d0000000-0000-4000-8000-0000000036f9', 'e0000000-0000-4000-8000-0000000036b9', 'b0000000-0000-4000-8000-000000000006',
     tstzrange('2031-05-29 09:00+08', '2031-05-29 10:00+08', '[)'), 'held', 'd0000000-0000-4000-8000-0000000036a9');

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, expires_at) values
    ('d0000000-0000-4000-8000-0000000036f1', 'e0000000-0000-4000-8000-0000000036b1',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-05-16 09:00+08', '2031-05-16 10:00+08', '[)'),
     'held', now() - interval '1 minute');

do $$
declare
    v_a uuid := 'e0000000-0000-4000-8000-0000000036a1';
    v_booking uuid := 'd0000000-0000-4000-8000-0000000036d1';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_lab uuid := 'b0000000-0000-4000-8000-000000000006';
    v_result record;
    v_row public.venue_bookings;
    v_status public.venue_booking_status;
    v_refused boolean;
begin
    -- AC2: venue staff approve a held booking, and the decision is recorded on it.
    select * into v_result from public.approve_venue_booking(v_booking, v_staff, 'A booking was approved.');
    if v_result.outcome is distinct from 'ok' or v_result.event_id is distinct from v_a
       or v_result.from_status is distinct from 'held' then
        raise exception 'BOOKING APPROVE FAIL: a held booking was not approved (outcome %)', v_result.outcome;
    end if;
    select * into v_row from public.venue_bookings where id = v_booking;
    if v_row.status <> 'approved' or v_row.decided_by is distinct from v_staff or v_row.decided_at is null
       or v_row.decision_reason is not null or v_row.suggestion_note is not null then
        raise exception 'BOOKING APPROVE FAIL: the booking does not carry the approval, decider and time alone';
    end if;

    -- AC10: one history row, with who and when.
    if (select count(*) from public.venue_booking_history
         where booking_id = v_booking and action = 'approved' and from_status = 'held' and to_status = 'approved'
           and actor_id = v_staff and created_at is not null) <> 1
       or (select count(*) from public.venue_booking_history where booking_id = v_booking) <> 1 then
        raise exception 'BOOKING APPROVE FAIL: the approval did not write exactly one history row';
    end if;

    -- AC2: the assigned coordinator is told, once; the venue staff actor isn't.
    if (select count(*) from public.notifications
         where event_id = v_a and type = 'venue_booking_approved'
           and recipient_id = v_coordinator and message = 'A booking was approved.') <> 1
       or (select count(*) from public.notifications where event_id = v_a and type = 'venue_booking_approved') <> 1 then
        raise exception 'BOOKING APPROVE FAIL: the assigned coordinator was not the only one notified, exactly once';
    end if;

    -- AC5: the approved booking still occupies the venue. Another event's
    -- request for an overlapping time is refused, and so is a direct insert
    -- (DB-1); one starting when the booking ends is fine (half-open).
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000036a3', v_lab, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is not distinct from 'ok' then
        raise exception 'BOOKING APPROVE FAIL: an approved booking''s slot was given to another event';
    end if;
    v_refused := false;
    begin
        insert into public.venue_bookings (event_id, venue_id, occupied_period, status)
        values ('e0000000-0000-4000-8000-0000000036a3', v_lab,
                tstzrange('2031-05-10 16:59+08', '2031-05-10 18:00+08', '[)'), 'held');
    exception when exclusion_violation then
        v_refused := true;
    end;
    if not v_refused then
        raise exception 'BOOKING APPROVE FAIL: DB-1 let a hold overlap an approved booking by one minute';
    end if;
    insert into public.venue_bookings (event_id, venue_id, occupied_period, status)
    values ('e0000000-0000-4000-8000-0000000036a3', v_lab,
            tstzrange('2031-05-10 17:00+08', '2031-05-10 18:00+08', '[)'), 'held');

    -- AC7: approving one of a multi-venue event's bookings leaves the other as it was.
    select * into v_result from public.approve_venue_booking(
        'd0000000-0000-4000-8000-0000000036c4', v_staff, 'x');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'BOOKING APPROVE FAIL: the plenary booking was not approved (outcome %)', v_result.outcome;
    end if;
    select * into v_row from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000036c5';
    if v_row.status <> 'held' or v_row.decided_by is not null or v_row.decided_at is not null
       or exists (select 1 from public.venue_booking_history where booking_id = v_row.id) then
        raise exception 'BOOKING APPROVE FAIL: approving one booking changed the event''s other booking';
    end if;
    if (select status from public.events where id = 'e0000000-0000-4000-8000-0000000036a4') <> 'planning' then
        raise exception 'BOOKING APPROVE FAIL: approving a booking changed the event status';
    end if;

    -- AC3: a block saved over a hold (CAL-R1) refuses its approval.
    insert into public.venue_blocks (venue_id, blocked_period, reason, notes)
    values ('b0000000-0000-4000-8000-000000000007',
            tstzrange('2031-05-12 09:30+08', '2031-05-12 11:00+08', '[)'), 'maintenance', 'Approve check (rolled back)');
    select * into v_result from public.approve_venue_booking('d0000000-0000-4000-8000-0000000036b5', v_staff, 'x');
    if v_result.outcome is distinct from 'venue_blocked' or v_result.from_status is distinct from 'held' then
        raise exception 'BOOKING APPROVE FAIL: a hold under a block was not refused as venue_blocked (outcome %)', v_result.outcome;
    end if;
    if (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000036b5') <> 'held'
       or exists (select 1 from public.venue_booking_history where booking_id = 'd0000000-0000-4000-8000-0000000036b5')
       or exists (select 1 from public.notifications
                   where event_id = 'e0000000-0000-4000-8000-0000000036a5' and type = 'venue_booking_approved') then
        raise exception 'BOOKING APPROVE FAIL: a refused approval under a block changed something';
    end if;

    -- AC4: a deactivated venue refuses approval of its holds.
    update public.venues
    set is_active = false, inactive_reason = 'other', inactive_note = 'Approve check (rolled back)'
    where id = 'b0000000-0000-4000-8000-000000000001';
    select * into v_result from public.approve_venue_booking('d0000000-0000-4000-8000-0000000036b6', v_staff, 'x');
    if v_result.outcome is distinct from 'venue_inactive' or v_result.from_status is distinct from 'held' then
        raise exception 'BOOKING APPROVE FAIL: a hold at an inactive venue was not refused as venue_inactive (outcome %)', v_result.outcome;
    end if;
    if (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000036b6') <> 'held'
       or exists (select 1 from public.venue_booking_history where booking_id = 'd0000000-0000-4000-8000-0000000036b6') then
        raise exception 'BOOKING APPROVE FAIL: a refused approval at an inactive venue changed the booking';
    end if;

    -- AC6 (CR-99): a hold past its expiry is expired, not approved.
    select * into v_result from public.approve_venue_booking('d0000000-0000-4000-8000-0000000036f1', v_staff, 'x');
    if v_result.outcome is distinct from 'hold_expired' or v_result.from_status is distinct from 'expired' then
        raise exception 'BOOKING APPROVE FAIL: a hold past its expiry was not refused as hold_expired (outcome %)', v_result.outcome;
    end if;
    if (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000036f1') <> 'expired'
       or exists (select 1 from public.venue_booking_history
                   where booking_id = 'd0000000-0000-4000-8000-0000000036f1' and action = 'approved')
       or (select decided_by from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000036f1') is not null then
        raise exception 'BOOKING APPROVE FAIL: an expired hold carries an approval';
    end if;

    -- AC6: every other status is refused and left as it is.
    foreach v_status in array array['approved', 're_review', 'rejected', 'cancelled', 'released', 'expired']::public.venue_booking_status[] loop
        select * into v_result from public.approve_venue_booking(
            (select id from public.venue_bookings
              where event_id in ('e0000000-0000-4000-8000-0000000036a8', 'e0000000-0000-4000-8000-0000000036a9')
                and status = v_status),
            v_staff, 'x');
        if v_result.outcome is distinct from (case when v_status = 'expired' then 'hold_expired' else 'not_held' end)
           or v_result.from_status is distinct from v_status then
            raise exception 'BOOKING APPROVE FAIL: a % booking was not refused (outcome %)', v_status, v_result.outcome;
        end if;
    end loop;
    if exists (select 1 from public.venue_booking_history h
                join public.venue_bookings vb on vb.id = h.booking_id
                where vb.event_id in ('e0000000-0000-4000-8000-0000000036a8', 'e0000000-0000-4000-8000-0000000036a9'))
       or (select count(*) from public.venue_bookings
            where event_id in ('e0000000-0000-4000-8000-0000000036a8', 'e0000000-0000-4000-8000-0000000036a9')
              and decided_by is not null) <> 0 then
        raise exception 'BOOKING APPROVE FAIL: a refused approval left a decision or history behind';
    end if;

    -- AC9: approval and rejection take the same lock, so whichever decides
    -- first wins and the other is refused. Approved, then rejected:
    select * into v_result from public.reject_venue_booking(v_booking, v_staff, 'Too late', null, 'x');
    if v_result.outcome is distinct from 'not_held' or v_result.from_status is distinct from 'approved' then
        raise exception 'BOOKING APPROVE FAIL: rejecting an approved booking was not refused (outcome %)', v_result.outcome;
    end if;
    -- Rejected, then approved:
    select * into v_result from public.reject_venue_booking(
        'd0000000-0000-4000-8000-0000000036b7', v_staff, 'Closed that day', null, 'x');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'BOOKING APPROVE FAIL: booking R was not rejected (outcome %)', v_result.outcome;
    end if;
    select * into v_result from public.approve_venue_booking('d0000000-0000-4000-8000-0000000036b7', v_staff, 'x');
    if v_result.outcome is distinct from 'not_held' or v_result.from_status is distinct from 'rejected' then
        raise exception 'BOOKING APPROVE FAIL: approving a rejected booking was not refused (outcome %)', v_result.outcome;
    end if;
    -- Approved twice: the second is refused and adds no history.
    select * into v_result from public.approve_venue_booking(v_booking, v_staff, 'x');
    if v_result.outcome is distinct from 'not_held'
       or (select count(*) from public.venue_booking_history where booking_id = v_booking) <> 1
       or (select status from public.venue_bookings where id = v_booking) <> 'approved'
       or (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000036b7') <> 'rejected' then
        raise exception 'BOOKING APPROVE FAIL: a decision was overwritten by a later one';
    end if;

    -- CR-95 AC5: approving a replacement releases the affected original in the
    -- same step. The original keeps its Affected flag as the record of why.
    select * into v_result from public.approve_venue_booking('d0000000-0000-4000-8000-0000000036f7', v_staff, 'x');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'BOOKING APPROVE FAIL: the replacement was not approved (outcome %)', v_result.outcome;
    end if;
    select * into v_row from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000036a7';
    if v_row.status <> 'released' or v_row.flag is distinct from 'affected' then
        raise exception 'BOOKING APPROVE FAIL: approving a replacement left its original % (flag %)', v_row.status, v_row.flag;
    end if;
    if (select array_agg(action order by action) from public.venue_booking_history
         where booking_id = 'd0000000-0000-4000-8000-0000000036f7') is distinct from array['approved', 'replacement_approved']
       or (select count(*) from public.venue_booking_history
            where booking_id = 'd0000000-0000-4000-8000-0000000036a7' and action = 'released_for_replacement'
              and actor_id = v_staff and from_status = 'approved' and to_status = 'released') <> 1 then
        raise exception 'BOOKING APPROVE FAIL: the replacement and its original do not each record the release';
    end if;
    -- Approving a booking that replaces nothing releases nothing.
    if exists (select 1 from public.venue_booking_history
                where booking_id = v_booking and action in ('replacement_approved', 'released_for_replacement')) then
        raise exception 'BOOKING APPROVE FAIL: approving a plain booking wrote replacement history';
    end if;

    -- Restored first: restore cancels the pending replacement, so approval is refused.
    if (select outcome from public.restore_affected_booking('d0000000-0000-4000-8000-0000000036a8', v_staff)) <> 'ok' then
        raise exception 'BOOKING APPROVE FAIL: setup, the original Q could not be restored';
    end if;
    select * into v_result from public.approve_venue_booking('d0000000-0000-4000-8000-0000000036f8', v_staff, 'x');
    if v_result.outcome is distinct from 'not_held' or v_result.from_status is distinct from 'cancelled'
       or (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000036a8') <> 'approved' then
        raise exception 'BOOKING APPROVE FAIL: a replacement cancelled by restore was approved, or its original released (outcome %)', v_result.outcome;
    end if;

    -- Approved first: the original is released, so restore is refused.
    select * into v_result from public.approve_venue_booking('d0000000-0000-4000-8000-0000000036f9', v_staff, 'x');
    if v_result.outcome is distinct from 'ok'
       or (select outcome from public.restore_affected_booking('d0000000-0000-4000-8000-0000000036a9', v_staff)) = 'ok'
       or (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000036f9') <> 'approved' then
        raise exception 'BOOKING APPROVE FAIL: restore undid an approved replacement';
    end if;

    -- Unknown ids come back as an outcome, not an error.
    select * into v_result from public.approve_venue_booking('d0000000-0000-4000-8000-0000000036ff', v_staff, 'x');
    if v_result.outcome is distinct from 'booking_not_found' then
        raise exception 'BOOKING APPROVE FAIL: an unknown booking was not reported as booking_not_found (outcome %)', v_result.outcome;
    end if;

    -- An event with no coordinator: the approval stands and nobody is notified.
    select * into v_result from public.approve_venue_booking('d0000000-0000-4000-8000-0000000036c2', v_staff, 'x');
    if v_result.outcome is distinct from 'ok'
       or exists (select 1 from public.notifications where event_id = 'e0000000-0000-4000-8000-0000000036b2') then
        raise exception 'BOOKING APPROVE FAIL: an unassigned event''s approval failed or notified someone';
    end if;

    -- The coordinator who also holds venue_staff approves a booking on their
    -- own event: they are not notified of their own action (NT-R1).
    select * into v_result from public.approve_venue_booking('d0000000-0000-4000-8000-0000000036c3', v_coordinator, 'x');
    if v_result.outcome is distinct from 'ok'
       or exists (select 1 from public.notifications
                   where event_id = 'e0000000-0000-4000-8000-0000000036b3' and type = 'venue_booking_approved') then
        raise exception 'BOOKING APPROVE FAIL: the actor was notified of their own approval';
    end if;

    -- API-only (ADR-0002): browsers and the publishable key can't call it (AC8).
    if has_function_privilege('anon', 'public.approve_venue_booking(uuid, uuid, text)', 'execute')
       or has_function_privilege('authenticated', 'public.approve_venue_booking(uuid, uuid, text)', 'execute')
       or not has_function_privilege('service_role', 'public.approve_venue_booking(uuid, uuid, text)', 'execute') then
        raise exception 'BOOKING APPROVE FAIL: approve_venue_booking is callable by a role other than service_role';
    end if;
end;
$$;

-- Reached only if every block above passed (a failed assertion aborts the run).
select 'BOOKING APPROVE CHECKS PASSED' as result;

rollback;
