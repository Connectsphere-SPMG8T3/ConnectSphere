-- CR-99 tentative hold expiry: the real expiry functions, trigger and job.
-- Run with `supabase db query --linked -f` or `psql "$DATABASE_URL" -f`. Raises
-- on the first failure and prints HOLD EXPIRY CHECKS PASSED otherwise.
-- Everything runs inside `begin; ... rollback;`, so the throwaway events,
-- bookings, history and notifications leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002, who also holds
-- venue_staff), venue staff (…0003) and venues Innovation Lab (…0006) and
-- Heritage Hall (…0007), on dates far enough ahead that nothing real is booked.
-- The functions take `p_now`, so time is simulated rather than waited for.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    -- Far ahead: the default expiry is 7 days after the request.
    ('e0000000-0000-4000-8000-0000000099a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check far (rolled back)',
     '2031-05-10 14:00+08', '2031-05-10 17:00+08'),
    -- Starts in 3 days: the default expiry is the event start.
    ('e0000000-0000-4000-8000-0000000099a2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check soon (rolled back)',
     now() + interval '3 days', now() + interval '3 days 2 hours'),
    -- Written directly with no expiry, as a path that doesn't set one would.
    ('e0000000-0000-4000-8000-0000000099a3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check direct insert (rolled back)',
     '2031-10-01 09:00+08', '2031-10-01 10:00+08');

do $$
begin
    -- AC1: every hold has an expiry, including those made before CR-99 and
    -- any written by a path that doesn't set one. Checked first: the checks
    -- below run the job at simulated 2031 times, which expire every real hold.
    if exists (select 1 from public.venue_bookings where status = 'held' and expires_at is null) then
        raise exception 'EXPIRY FAIL: a held booking has no expiry';
    end if;
    begin
        insert into public.venue_bookings (event_id, venue_id, occupied_period, status, expires_at)
        values ('e0000000-0000-4000-8000-0000000099a3', 'b0000000-0000-4000-8000-000000000007',
                tstzrange('2031-10-01 09:00+08', '2031-10-01 10:00+08', '[)'), 'held', null);
        if exists (select 1 from public.venue_bookings
                    where event_id = 'e0000000-0000-4000-8000-0000000099a3'
                      and venue_id = 'b0000000-0000-4000-8000-000000000007' and expires_at is null) then
            raise exception 'EXPIRY FAIL: a hold was saved without an expiry';
        end if;
    end;

    -- AC5 needs no one to act: the job runs every minute.
    if not exists (select 1 from cron.job
                    where jobname = 'expire-venue-holds' and schedule = '* * * * *'
                      and command ilike '%public.expire_venue_holds()%' and active) then
        raise exception 'EXPIRY FAIL: the expiry job is not scheduled every minute';
    end if;
end;
$$;

do $$
declare
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_lab uuid := 'b0000000-0000-4000-8000-000000000006';
    v_hall uuid := 'b0000000-0000-4000-8000-000000000007';
    v_result record;
    v_booking public.venue_bookings;
begin
    -- AC1: every hold gets an expiry, 7 days after the request by default.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000099a1', v_lab, v_coordinator, null, 'A venue was requested.');
    select * into v_booking from public.venue_bookings where id = v_result.booking_id;
    if v_booking.expires_at is distinct from now() + interval '7 days' then
        raise exception 'EXPIRY FAIL: default expiry is % not request + 7 days', v_booking.expires_at;
    end if;

    -- AC1 [Assumption]: never after the event starts, so an event under 7
    -- days away is held until its start.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000099a2', v_hall, v_coordinator, null, 'A venue was requested.');
    select * into v_booking from public.venue_bookings where id = v_result.booking_id;
    if v_booking.expires_at is distinct from lower(v_booking.occupied_period) then
        raise exception 'EXPIRY FAIL: an event 3 days away is held until % not its start', v_booking.expires_at;
    end if;
end;
$$;

-- Bookings for the job checks, written directly so each expiry is exact.
insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-0000000099b1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check due (rolled back)',
     '2031-06-01 09:00+08', '2031-06-01 10:00+08'),
    ('e0000000-0000-4000-8000-0000000099b2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check not yet due (rolled back)',
     '2031-06-01 11:00+08', '2031-06-01 12:00+08'),
    ('e0000000-0000-4000-8000-0000000099b3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check approved (rolled back)',
     '2031-06-01 13:00+08', '2031-06-01 14:00+08'),
    ('e0000000-0000-4000-8000-0000000099b4', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check event started (rolled back)',
     '2031-06-02 09:00+08', '2031-06-02 10:00+08');

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, expires_at) values
    ('d0000000-0000-4000-8000-0000000099b1', 'e0000000-0000-4000-8000-0000000099b1',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-06-01 09:00+08', '2031-06-01 10:00+08', '[)'),
     'held', '2031-05-20 12:00+08'),
    ('d0000000-0000-4000-8000-0000000099b2', 'e0000000-0000-4000-8000-0000000099b2',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-06-01 11:00+08', '2031-06-01 12:00+08', '[)'),
     'held', '2031-05-20 12:00:01+08'),
    ('d0000000-0000-4000-8000-0000000099b3', 'e0000000-0000-4000-8000-0000000099b3',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-06-01 13:00+08', '2031-06-01 14:00+08', '[)'),
     'approved', '2031-05-20 12:00+08'),
    -- An expiry left after the event start (the event moved earlier, AC1).
    ('d0000000-0000-4000-8000-0000000099b4', 'e0000000-0000-4000-8000-0000000099b4',
     'b0000000-0000-4000-8000-000000000007', tstzrange('2031-06-02 09:00+08', '2031-06-02 10:00+08', '[)'),
     'held', '2031-06-05 12:00+08');

do $$
declare
    v_status public.venue_booking_status;
begin
    -- AC5: at the expiry time an unapproved hold becomes Expired; a second
    -- before its own expiry another stays held. AC4: approved never expires.
    perform public.expire_venue_holds('2031-05-20 12:00+08');

    select status into v_status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000099b1';
    if v_status is distinct from 'expired' then
        raise exception 'EXPIRY FAIL: a hold at its expiry is % not expired', v_status;
    end if;
    select status into v_status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000099b2';
    if v_status is distinct from 'held' then
        raise exception 'EXPIRY FAIL: a hold a second before its expiry is %', v_status;
    end if;
    select status into v_status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000099b3';
    if v_status is distinct from 'approved' then
        raise exception 'EXPIRY FAIL: an approved booking became %', v_status;
    end if;

    -- A hold is never kept past its event's start, whatever its expiry says.
    perform public.expire_venue_holds('2031-06-02 09:00+08');
    select status into v_status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000099b4';
    if v_status is distinct from 'expired' then
        raise exception 'EXPIRY FAIL: a hold whose event started is % not expired', v_status;
    end if;
end;
$$;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-0000000099c1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check rival (rolled back)',
     '2031-06-02 09:30+08', '2031-06-02 11:00+08'),
    ('e0000000-0000-4000-8000-0000000099c2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check overdue, not yet swept (rolled back)',
     '2031-06-03 09:00+08', '2031-06-03 10:00+08'),
    ('e0000000-0000-4000-8000-0000000099c3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check rival of overdue (rolled back)',
     '2031-06-03 09:00+08', '2031-06-03 10:00+08');

-- Its expiry passed a minute ago (real time) and the job hasn't run since.
insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, expires_at) values
    ('d0000000-0000-4000-8000-0000000099c2', 'e0000000-0000-4000-8000-0000000099c2',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-06-03 09:00+08', '2031-06-03 10:00+08', '[)'),
     'held', now() - interval '1 minute');

do $$
declare
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_lab uuid := 'b0000000-0000-4000-8000-000000000006';
    v_hall uuid := 'b0000000-0000-4000-8000-000000000007';
    v_result record;
    v_status public.venue_booking_status;
begin
    -- AC7: after its hold expired, the coordinator requests the same venue again.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000099b1', v_lab, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'EXPIRY FAIL: re-requesting after expiry was refused (%)', v_result.outcome;
    end if;

    -- AC5: the expired hold no longer occupies the venue for anyone else.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000099c1', v_hall, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'EXPIRY FAIL: an expired hold still blocked another event (%)', v_result.outcome;
    end if;

    -- AC5 to the second: a request doesn't wait up to a minute for the job.
    -- The overdue hold is expired first, then the slot is free.
    select * into v_result from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000099c3', v_lab, v_coordinator, null, 'A venue was requested.');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'EXPIRY FAIL: an overdue hold the job had not reached blocked a request (%)', v_result.outcome;
    end if;
    select status into v_status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000099c2';
    if v_status is distinct from 'expired' then
        raise exception 'EXPIRY FAIL: the overdue hold was left %', v_status;
    end if;
end;
$$;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-0000000099d1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check notices (rolled back)',
     '2031-07-05 09:00+08', '2031-07-05 10:00+08');

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, expires_at) values
    ('d0000000-0000-4000-8000-0000000099d1', 'e0000000-0000-4000-8000-0000000099d1',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-07-05 09:00+08', '2031-07-05 10:00+08', '[)'),
     'held', '2031-07-01 12:00+08');

do $$
declare
    v_booking uuid := 'd0000000-0000-4000-8000-0000000099d1';
    v_event uuid := 'e0000000-0000-4000-8000-0000000099d1';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_count integer;
    v_message text;
    v_history public.venue_booking_history;
begin
    -- AC3: nothing more than 24 hours ahead.
    perform public.expire_venue_holds('2031-06-30 11:59+08');
    select count(*) into v_count from public.notifications where event_id = v_event;
    if v_count <> 0 then
        raise exception 'EXPIRY FAIL: % notices sent more than 24 hours before expiry', v_count;
    end if;

    -- AC3: the coordinator is warned 24 hours before expiry, once.
    perform public.expire_venue_holds('2031-06-30 12:00+08');
    perform public.expire_venue_holds('2031-06-30 12:30+08');
    select count(*), min(message) into v_count, v_message from public.notifications
     where event_id = v_event and type = 'venue_hold_expiring' and recipient_id = v_coordinator;
    if v_count <> 1 then
        raise exception 'EXPIRY FAIL: the 24-hour warning was sent % times', v_count;
    end if;
    if v_message is distinct from
       'Your hold on Innovation Lab for "Expiry check notices (rolled back)" expires on 1 Jul 2031, 12:00 unless Venue Staff approve it.' then
        raise exception 'EXPIRY FAIL: warning reads %', v_message;
    end if;

    -- AC3: and again when it expires, once.
    perform public.expire_venue_holds('2031-07-01 12:00+08');
    perform public.expire_venue_holds('2031-07-01 12:01+08');
    select count(*), min(message) into v_count, v_message from public.notifications
     where event_id = v_event and type = 'venue_hold_expired' and recipient_id = v_coordinator;
    if v_count <> 1 then
        raise exception 'EXPIRY FAIL: the expired notice was sent % times', v_count;
    end if;
    if v_message is distinct from
       'Your hold on Innovation Lab for "Expiry check notices (rolled back)" has expired. You can request the venue again if it''s still free.' then
        raise exception 'EXPIRY FAIL: expired notice reads %', v_message;
    end if;

    -- The coordinator only (AC3): venue staff are not told.
    select count(*) into v_count from public.notifications
     where event_id = v_event and recipient_id <> v_coordinator;
    if v_count <> 0 then
        raise exception 'EXPIRY FAIL: % notices went to someone other than the coordinator', v_count;
    end if;

    -- The expiry is in the booking history, made by the system (no actor).
    select * into v_history from public.venue_booking_history where booking_id = v_booking and action = 'expired';
    if not found or v_history.actor_id is not null or v_history.from_status <> 'held'
       or v_history.to_status <> 'expired' or v_history.created_at <> '2031-07-01 12:00+08' then
        raise exception 'EXPIRY FAIL: expiry not recorded as a system history entry';
    end if;
end;
$$;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-0000000099e1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check change (rolled back)',
     '2031-08-10 09:00+08', '2031-08-10 10:00+08'),
    ('e0000000-0000-4000-8000-0000000099e2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check change approved (rolled back)',
     '2031-08-11 09:00+08', '2031-08-11 10:00+08'),
    ('e0000000-0000-4000-8000-0000000099e3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check change overdue (rolled back)',
     '2031-08-12 09:00+08', '2031-08-12 10:00+08');

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, expires_at, expiry_warned_at) values
    ('d0000000-0000-4000-8000-0000000099e1', 'e0000000-0000-4000-8000-0000000099e1',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-08-10 09:00+08', '2031-08-10 10:00+08', '[)'),
     'held', '2031-08-01 12:00+08', '2031-07-31 12:00+08'),
    ('d0000000-0000-4000-8000-0000000099e2', 'e0000000-0000-4000-8000-0000000099e2',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-08-11 09:00+08', '2031-08-11 10:00+08', '[)'),
     'approved', '2031-08-01 12:00+08', null),
    ('d0000000-0000-4000-8000-0000000099e3', 'e0000000-0000-4000-8000-0000000099e3',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2031-08-12 09:00+08', '2031-08-12 10:00+08', '[)'),
     'held', '2031-08-01 12:00+08', null);

do $$
declare
    v_booking uuid := 'd0000000-0000-4000-8000-0000000099e1';
    v_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_now timestamptz := '2031-07-31 18:00+08';
    v_result record;
    v_row public.venue_bookings;
    v_history public.venue_booking_history;
begin
    -- AC2: extend before it passes. Recorded with who, from and to; the
    -- warning marker is cleared so the new expiry is warned about in turn.
    select * into v_result from public.set_venue_hold_expiry(v_booking, v_staff, '2031-08-05 12:00+08', v_now);
    if v_result.outcome <> 'ok' or v_result.expires_at <> '2031-08-05 12:00+08' then
        raise exception 'EXPIRY FAIL: extending was % %', v_result.outcome, v_result.expires_at;
    end if;
    select * into v_row from public.venue_bookings where id = v_booking;
    if v_row.expires_at <> '2031-08-05 12:00+08' or v_row.expiry_warned_at is not null then
        raise exception 'EXPIRY FAIL: extension saved % with marker %', v_row.expires_at, v_row.expiry_warned_at;
    end if;
    select * into v_history from public.venue_booking_history where booking_id = v_booking and action = 'expiry_changed';
    if not found or v_history.actor_id <> v_staff or v_history.old_expires_at <> '2031-08-01 12:00+08'
       or v_history.new_expires_at <> '2031-08-05 12:00+08' or v_history.created_at <> v_now then
        raise exception 'EXPIRY FAIL: the change was not recorded with actor, old and new expiry';
    end if;

    -- AC2 "change": shortening is allowed, and up to the event start exactly.
    select * into v_result from public.set_venue_hold_expiry(v_booking, v_staff, '2031-08-02 09:00+08', v_now);
    if v_result.outcome <> 'ok' then
        raise exception 'EXPIRY FAIL: shortening was refused (%)', v_result.outcome;
    end if;
    select * into v_result from public.set_venue_hold_expiry(v_booking, v_staff, '2031-08-10 09:00+08', v_now);
    if v_result.outcome <> 'ok' then
        raise exception 'EXPIRY FAIL: expiry at the event start was refused (%)', v_result.outcome;
    end if;

    -- AC1: in the future and not after the event starts.
    select * into v_result from public.set_venue_hold_expiry(v_booking, v_staff, v_now, v_now);
    if v_result.outcome <> 'not_in_future' then
        raise exception 'EXPIRY FAIL: an expiry of now gave %', v_result.outcome;
    end if;
    select * into v_result from public.set_venue_hold_expiry(v_booking, v_staff, '2031-08-10 09:00:01+08', v_now);
    if v_result.outcome <> 'after_event_start' then
        raise exception 'EXPIRY FAIL: an expiry after the event start gave %', v_result.outcome;
    end if;
    if (select count(*) from public.venue_booking_history where booking_id = v_booking) <> 3 then
        raise exception 'EXPIRY FAIL: a refused change was recorded';
    end if;

    -- Only a hold expires: an approved booking's expiry can't be changed (AC4).
    select * into v_result from public.set_venue_hold_expiry(
        'd0000000-0000-4000-8000-0000000099e2', v_staff, '2031-08-05 12:00+08', v_now);
    if v_result.outcome <> 'not_held' then
        raise exception 'EXPIRY FAIL: changing an approved booking gave %', v_result.outcome;
    end if;

    -- AC2 "before it passes": a hold past its expiry is expired, not extended,
    -- even if the job hasn't reached it yet.
    select * into v_result from public.set_venue_hold_expiry(
        'd0000000-0000-4000-8000-0000000099e3', v_staff, '2031-08-11 12:00+08', '2031-08-01 12:00+08');
    if v_result.outcome <> 'hold_expired' then
        raise exception 'EXPIRY FAIL: extending an overdue hold gave %', v_result.outcome;
    end if;
    if (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000099e3') <> 'expired' then
        raise exception 'EXPIRY FAIL: the overdue hold was not expired';
    end if;

    select * into v_result from public.set_venue_hold_expiry(
        'd0000000-0000-4000-8000-0000000099ff', v_staff, '2031-08-05 12:00+08', v_now);
    if v_result.outcome <> 'booking_not_found' then
        raise exception 'EXPIRY FAIL: an unknown booking gave %', v_result.outcome;
    end if;
end;
$$;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-0000000099f1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check approve in time (rolled back)',
     '2031-09-10 09:00+08', '2031-09-10 10:00+08'),
    ('e0000000-0000-4000-8000-0000000099f2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Expiry check approve too late (rolled back)',
     '2031-09-11 09:00+08', '2031-09-11 10:00+08');

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, expires_at) values
    ('d0000000-0000-4000-8000-0000000099f1', 'e0000000-0000-4000-8000-0000000099f1',
     'b0000000-0000-4000-8000-000000000007', tstzrange('2031-09-10 09:00+08', '2031-09-10 10:00+08', '[)'),
     'held', '2031-09-01 12:00+08'),
    ('d0000000-0000-4000-8000-0000000099f2', 'e0000000-0000-4000-8000-0000000099f2',
     'b0000000-0000-4000-8000-000000000007', tstzrange('2031-09-11 09:00+08', '2031-09-11 10:00+08', '[)'),
     'held', '2031-09-01 12:00+08');

do $$
declare
    v_outcome text;
begin
    -- AC4/AC8: approval a moment before expiry gets the hold, locked for the
    -- approving transaction (approval itself is SCRUM-36's).
    v_outcome := public.lock_hold_for_approval('d0000000-0000-4000-8000-0000000099f1', '2031-09-01 11:59:59+08');
    if v_outcome <> 'ok' then
        raise exception 'EXPIRY FAIL: approval before expiry gave %', v_outcome;
    end if;

    -- AC8: at or after the expiry the approval is refused, and only the
    -- expiry is saved, even if the job hasn't run yet.
    v_outcome := public.lock_hold_for_approval('d0000000-0000-4000-8000-0000000099f2', '2031-09-01 12:00+08');
    if v_outcome <> 'hold_expired' then
        raise exception 'EXPIRY FAIL: approval at expiry gave %', v_outcome;
    end if;
    if (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000099f2') <> 'expired' then
        raise exception 'EXPIRY FAIL: the hold refused at expiry was not expired';
    end if;
    v_outcome := public.lock_hold_for_approval('d0000000-0000-4000-8000-0000000099f2', '2031-09-01 12:05+08');
    if v_outcome <> 'hold_expired' then
        raise exception 'EXPIRY FAIL: approval of an expired hold gave %', v_outcome;
    end if;

    -- An approved booking isn't a hold any more.
    update public.venue_bookings set status = 'approved' where id = 'd0000000-0000-4000-8000-0000000099f1';
    v_outcome := public.lock_hold_for_approval('d0000000-0000-4000-8000-0000000099f1', '2031-09-01 11:59:59+08');
    if v_outcome <> 'not_held' then
        raise exception 'EXPIRY FAIL: approving an approved booking gave %', v_outcome;
    end if;
    v_outcome := public.lock_hold_for_approval('d0000000-0000-4000-8000-0000000099ff', '2031-09-01 11:59:59+08');
    if v_outcome <> 'booking_not_found' then
        raise exception 'EXPIRY FAIL: an unknown booking gave %', v_outcome;
    end if;
end;
$$;

do $$
declare
    v_fn text;
begin
    -- API-only (ADR-0002): browsers and the publishable key can't call them.
    foreach v_fn in array array[
        'public.expire_venue_holds(timestamptz)',
        'public.set_venue_hold_expiry(uuid, uuid, timestamptz, timestamptz)',
        'public.lock_hold_for_approval(uuid, timestamptz)'
    ] loop
        if has_function_privilege('anon', v_fn, 'execute')
           or has_function_privilege('authenticated', v_fn, 'execute')
           or not has_function_privilege('service_role', v_fn, 'execute') then
            raise exception 'EXPIRY FAIL: % is callable by a role other than service_role', v_fn;
        end if;
    end loop;
    if has_function_privilege('authenticated', 'private.set_hold_default_expiry()', 'execute') then
        raise exception 'EXPIRY FAIL: the trigger function is callable by authenticated';
    end if;
end;
$$;

-- Reached only if every block above passed (a failed assertion aborts the run).
select 'HOLD EXPIRY CHECKS PASSED' as result;

rollback;
