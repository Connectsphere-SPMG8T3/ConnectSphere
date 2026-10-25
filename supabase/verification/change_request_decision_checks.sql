-- Story 37 review and process event change requests: the real approve_event_change,
-- reject_event_change and re-review functions. Run with the Supabase MCP execute_sql
-- or `psql "$DATABASE_URL" -f`. Raises on the first failure and prints CHANGE
-- DECISION CHECKS PASSED otherwise. Everything runs inside `begin; ... rollback;`, so
-- the throwaway events, bookings and lines leave no trace. Uses the seeded organiser
-- (…0001), coordinator (…0002, who also holds venue_staff), venue staff (…0003) and
-- tech support (…0004), and the Grand Ballroom. Dates are in 2031 so no seeded
-- booking overlaps.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    -- Rejected change: the event keeps everything.
    ('e0000000-0000-4000-8000-000000003701', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Reject change check (rolled back)',
     '2031-04-15 10:00+08', '2031-04-15 12:00+08'),
    -- Started an hour ago: refused (Q5).
    ('e0000000-0000-4000-8000-000000003702', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Started change check (rolled back)',
     now() - interval '1 hour', now() + interval '1 hour'),
    -- A draft: not found to every coordinator.
    ('e0000000-0000-4000-8000-000000003703', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'draft', 'Draft change check (rolled back)',
     null, null),
    -- Ordinary change approved: values applied, nothing else moves (Q7).
    ('e0000000-0000-4000-8000-000000003704', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Ordinary change check (rolled back)',
     '2031-04-16 10:00+08', '2031-04-16 12:00+08');

-- Significant changes (AC7, Q6): back to Planning from Confirmed, Preparation and
-- Safety review; Planning stays Planning.
insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at,
                           expected_attendance) values
    ('e0000000-0000-4000-8000-000000003705', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Confirmed change check (rolled back)',
     '2031-04-17 10:00+08', '2031-04-17 12:00+08', 80),
    ('e0000000-0000-4000-8000-000000003706', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'preparation', 'Preparation change check (rolled back)',
     '2031-04-18 10:00+08', '2031-04-18 12:00+08', 80),
    ('e0000000-0000-4000-8000-000000003707', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'safety_review', 'Safety change check (rolled back)',
     '2031-04-19 10:00+08', '2031-04-19 12:00+08', 80),
    ('e0000000-0000-4000-8000-000000003708', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Planning change check (rolled back)',
     '2031-04-20 10:00+08', '2031-04-20 12:00+08', 80);

insert into public.event_change_requests (event_id, kind, reason, requested_by, changes, significant)
select id, 'change', 'More guests', 'a0000000-0000-4000-8000-000000000001',
       '{"event": [{"field": "expected_attendance", "before": 80, "after": 90}], "spaces": []}', true
  from public.events where id in ('e0000000-0000-4000-8000-000000003705', 'e0000000-0000-4000-8000-000000003706',
                                  'e0000000-0000-4000-8000-000000003707', 'e0000000-0000-4000-8000-000000003708');

insert into public.event_registrations (event_id, attendee_id) values
    ('e0000000-0000-4000-8000-000000003705', 'a0000000-0000-4000-8000-000000000005');

-- Bookings an approved change touches (AC3, AC5, Q11, Q15, Q17): a time change on
-- 2031-04-21 to 14:00-16:00, with another event's hold at 13:00-14:00 on Auditorium A.
insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-000000003709', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Booking moves check (rolled back)',
     '2031-04-21 10:00+08', '2031-04-21 12:00+08'),
    ('e0000000-0000-4000-8000-000000003710', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Blocking hold (rolled back)',
     '2031-04-21 13:00+08', '2031-04-21 14:00+08');

insert into public.event_space_requests (id, event_id, label, expected_pax) values
    ('f0000000-0000-4000-8000-000000003791', 'e0000000-0000-4000-8000-000000003709', 'Clash', 50),
    ('f0000000-0000-4000-8000-000000003792', 'e0000000-0000-4000-8000-000000003709', 'Mover', 50),
    ('f0000000-0000-4000-8000-000000003793', 'e0000000-0000-4000-8000-000000003709', 'Held', 50),
    ('f0000000-0000-4000-8000-000000003794', 'e0000000-0000-4000-8000-000000003709', 'Crowded', 50),
    ('f0000000-0000-4000-8000-000000003795', 'e0000000-0000-4000-8000-000000003709', 'Fits again', 50),
    ('f0000000-0000-4000-8000-000000003796', 'e0000000-0000-4000-8000-000000003710', 'Blocker', 50),
    ('f0000000-0000-4000-8000-000000003797', 'e0000000-0000-4000-8000-000000003709', 'Blocked', 50);

insert into public.venue_blocks (venue_id, blocked_period, reason, notes) values
    ('b0000000-0000-4000-8000-000000000001',
     tstzrange('2031-04-21 15:00+08', '2031-04-21 17:00+08', '[)'), 'maintenance', 'Change check (rolled back)');

-- An hour's setup takes the moved Clash booking into the blocker's hold.
insert into public.venue_bookings (id, event_id, event_space_request_id, venue_id, booked_period, setup_minutes,
                                   status, flag, flag_reason, flagged_at) values
    ('d0000000-0000-4000-8000-000000003791', 'e0000000-0000-4000-8000-000000003709',
     'f0000000-0000-4000-8000-000000003791', 'b0000000-0000-4000-8000-000000000002',
     tstzrange('2031-04-21 10:00+08', '2031-04-21 12:00+08', '[)'), 60, 'approved', null, null, null),
    ('d0000000-0000-4000-8000-000000003792', 'e0000000-0000-4000-8000-000000003709',
     'f0000000-0000-4000-8000-000000003792', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-04-21 10:00+08', '2031-04-21 12:00+08', '[)'), 0, 'approved', null, null, null),
    ('d0000000-0000-4000-8000-000000003793', 'e0000000-0000-4000-8000-000000003709',
     'f0000000-0000-4000-8000-000000003793', 'b0000000-0000-4000-8000-000000000004',
     tstzrange('2031-04-21 10:00+08', '2031-04-21 12:00+08', '[)'), 0, 'held', null, null, null),
    ('d0000000-0000-4000-8000-000000003794', 'e0000000-0000-4000-8000-000000003709',
     'f0000000-0000-4000-8000-000000003794', 'b0000000-0000-4000-8000-000000000005',
     tstzrange('2031-04-21 10:00+08', '2031-04-21 12:00+08', '[)'), 0, 'approved', null, null, null),
    ('d0000000-0000-4000-8000-000000003795', 'e0000000-0000-4000-8000-000000003709',
     'f0000000-0000-4000-8000-000000003795', 'b0000000-0000-4000-8000-000000000006',
     tstzrange('2031-04-21 10:00+08', '2031-04-21 12:00+08', '[)'), 0, 'approved', 'unsuitable',
     'After an approved change: Fits again needs 90 people; Innovation Lab seats 80.', now()),
    ('d0000000-0000-4000-8000-000000003797', 'e0000000-0000-4000-8000-000000003709',
     'f0000000-0000-4000-8000-000000003797', 'b0000000-0000-4000-8000-000000000001',
     tstzrange('2031-04-21 10:00+08', '2031-04-21 12:00+08', '[)'), 0, 'approved', null, null, null),
    ('d0000000-0000-4000-8000-000000003796', 'e0000000-0000-4000-8000-000000003710',
     'f0000000-0000-4000-8000-000000003796', 'b0000000-0000-4000-8000-000000000002',
     tstzrange('2031-04-21 13:00+08', '2031-04-21 14:00+08', '[)'), 0, 'held', null, null, null);

-- Equipment on the moved event (Q14): 8 of 10 PA Systems, with 5 taken at the new time by
-- the blocker; 2 Wireless Mics, which still fit. Exits ticked, so it was Ready.
insert into public.equipment_requests (id, event_id, equipment_id, submission_id, quantity, status) values
    ('c0000000-0000-4000-8000-000000003791', 'e0000000-0000-4000-8000-000000003709',
     'b0000000-0000-4000-8000-000000000003', gen_random_uuid(), 8, 'reserved'),
    ('c0000000-0000-4000-8000-000000003792', 'e0000000-0000-4000-8000-000000003709',
     'b0000000-0000-4000-8000-000000000002', gen_random_uuid(), 2, 'reserved');
insert into public.equipment_reservations (equipment_id, event_id, quantity, start_at, end_at, request_line_id) values
    ('b0000000-0000-4000-8000-000000000003', 'e0000000-0000-4000-8000-000000003709', 8,
     '2031-04-21 10:00+08', '2031-04-21 12:00+08', 'c0000000-0000-4000-8000-000000003791'),
    ('b0000000-0000-4000-8000-000000000002', 'e0000000-0000-4000-8000-000000003709', 2,
     '2031-04-21 10:00+08', '2031-04-21 12:00+08', 'c0000000-0000-4000-8000-000000003792'),
    ('b0000000-0000-4000-8000-000000000003', 'e0000000-0000-4000-8000-000000003710', 5,
     '2031-04-21 14:00+08', '2031-04-21 16:00+08', null);
update public.events set exit_confirmed_at = now(), exit_confirmed_by = 'a0000000-0000-4000-8000-000000000004'
 where id = 'e0000000-0000-4000-8000-000000003709';
select private.refresh_technical_status('e0000000-0000-4000-8000-000000003709');

insert into public.event_change_requests (event_id, kind, reason, requested_by, changes, significant) values
    ('e0000000-0000-4000-8000-000000003709', 'change', 'Afternoon instead', 'a0000000-0000-4000-8000-000000000001',
     '{"event": [{"field": "starts_at", "before": "2031-04-21T02:00:00Z", "after": "2031-04-21T06:00:00Z"}], "spaces": []}',
     true);

-- Venue staff reject a booking under re-review (Q12, Q21): an approved booking already marked.
insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-000000003711', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Re-review reject check (rolled back)',
     '2031-04-22 10:00+08', '2031-04-22 12:00+08');
insert into public.venue_bookings (id, event_id, venue_id, booked_period, status, needs_re_review_since,
                                   needs_re_review_reason) values
    ('d0000000-0000-4000-8000-000000003711', 'e0000000-0000-4000-8000-000000003711',
     'b0000000-0000-4000-8000-000000000003', tstzrange('2031-04-22 10:00+08', '2031-04-22 12:00+08', '[)'),
     'approved', now(), 'Layout changed.');

-- Q22: a second change while a booking is already under re-review.
insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-000000003712', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Second change check (rolled back)',
     '2031-04-23 10:00+08', '2031-04-23 12:00+08');
insert into public.venue_bookings (id, event_id, venue_id, booked_period, status) values
    ('d0000000-0000-4000-8000-000000003712', 'e0000000-0000-4000-8000-000000003712',
     'b0000000-0000-4000-8000-000000000003', tstzrange('2031-04-23 10:00+08', '2031-04-23 12:00+08', '[)'),
     're_review');
insert into public.event_change_requests (event_id, kind, reason, requested_by, changes, significant) values
    ('e0000000-0000-4000-8000-000000003712', 'change', 'Later again', 'a0000000-0000-4000-8000-000000000001',
     '{"event": [{"field": "ends_at", "before": "2031-04-23T04:00:00Z", "after": "2031-04-23T05:00:00Z"}], "spaces": []}',
     true);

insert into public.event_space_requests (id, event_id, label, expected_pax) values
    ('f0000000-0000-4000-8000-000000003704', 'e0000000-0000-4000-8000-000000003704', 'Main hall', 80);

insert into public.venue_bookings (event_id, venue_id, occupied_period, status) values
    ('e0000000-0000-4000-8000-000000003701', 'b0000000-0000-4000-8000-000000000001',
     tstzrange('2031-04-15 09:00+08', '2031-04-15 13:00+08', '[)'), 'approved');

insert into public.event_change_requests (event_id, kind, reason, requested_by, changes, significant) values
    ('e0000000-0000-4000-8000-000000003701', 'change', 'More guests', 'a0000000-0000-4000-8000-000000000001',
     '{"event": [{"field": "expected_attendance", "before": 80, "after": 150}], "spaces": []}', true),
    ('e0000000-0000-4000-8000-000000003702', 'change', 'Later start', 'a0000000-0000-4000-8000-000000000001',
     '{"event": [{"field": "name", "before": "a", "after": "b"}], "spaces": []}', false),
    ('e0000000-0000-4000-8000-000000003704', 'change', 'New title', 'a0000000-0000-4000-8000-000000000001',
     '{"event": [{"field": "name", "before": "Ordinary change check (rolled back)", "after": "Renamed (rolled back)"}], "spaces": [{"space_id": "f0000000-0000-4000-8000-000000003704", "label": "Main hall", "fields": [{"field": "label", "before": "Main hall", "after": "Great hall"}]}]}',
     false);

insert into public.venue_bookings (event_id, event_space_request_id, venue_id, occupied_period, status) values
    ('e0000000-0000-4000-8000-000000003704', 'f0000000-0000-4000-8000-000000003704',
     'b0000000-0000-4000-8000-000000000001',
     tstzrange('2031-04-16 09:00+08', '2031-04-16 13:00+08', '[)'), 'approved');

do $$
declare
    v_reject uuid := 'e0000000-0000-4000-8000-000000003701';
    v_started uuid := 'e0000000-0000-4000-8000-000000003702';
    v_draft uuid := 'e0000000-0000-4000-8000-000000003703';
    v_ordinary uuid := 'e0000000-0000-4000-8000-000000003704';
    v_ordinary_space uuid := 'f0000000-0000-4000-8000-000000003704';
    v_event public.events;
    v_version integer;
    v_replacement record;
    v_decision record;
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_venue_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_decidable text[] := array['submitted', 'under_review', 'planning', 'safety_review',
                                'confirmed', 'preparation'];
    v_result jsonb;
    v_rows integer;
    v_request public.event_change_requests;
begin
    -- Reject (AC2, AC4, CR-R3): refusals first, so nothing they touch has moved yet.
    v_result := public.reject_event_change(v_reject, v_venue_staff, 'x', v_decidable, 'o');
    if v_result->>'outcome' is distinct from 'not_assigned' then
        raise exception 'CHANGE FAIL: a rejection by someone not assigned was not refused: %', v_result;
    end if;
    v_result := public.reject_event_change(v_draft, v_coordinator, 'x', v_decidable, 'o');
    if v_result->>'outcome' is distinct from 'not_found' then
        raise exception 'CHANGE FAIL: rejecting on a draft was not refused as not found: %', v_result;
    end if;
    v_result := public.reject_event_change(v_started, v_coordinator, 'x', v_decidable, 'o');
    if v_result->>'outcome' is distinct from 'started' then
        raise exception 'CHANGE FAIL: rejecting on a started event was not refused: %', v_result;
    end if;
    -- AC8: a status the API no longer allows (the event moved on under the lock).
    v_result := public.reject_event_change(v_reject, v_coordinator, 'x', array['planning'], 'o');
    if v_result->>'outcome' is distinct from 'status_changed' then
        raise exception 'CHANGE FAIL: rejecting in a refused status was not refused: %', v_result;
    end if;

    v_result := public.reject_event_change(v_reject, v_coordinator, '  Venue is fixed  ', v_decidable,
        'to organiser');
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'CHANGE FAIL: the rejection was refused: %', v_result;
    end if;
    select * into v_request from public.event_change_requests where event_id = v_reject;
    if v_request.status <> 'rejected' or v_request.decision_reason <> 'Venue is fixed'
       or v_request.decided_by is distinct from v_coordinator or v_request.decided_at is null then
        raise exception 'CHANGE FAIL: the request was not closed as rejected with the trimmed reason';
    end if;
    if (select status from public.events where id = v_reject) <> 'confirmed'
       or not exists (select 1 from public.venue_bookings where event_id = v_reject and status = 'approved') then
        raise exception 'CHANGE FAIL: rejecting changed the event or its venue';
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_reject and type = 'event_change_rejected' and recipient_id = v_organiser
       and recipient_role = 'event_organiser' and message = 'to organiser';
    if v_rows <> 1 then raise exception 'CHANGE FAIL: the organiser was not told of the rejection once'; end if;
    select count(*) into v_rows from public.notifications where event_id = v_reject and recipient_id = v_coordinator;
    if v_rows <> 0 then raise exception 'CHANGE FAIL: the coordinator was notified of their own action (NT-R1)'; end if;
    v_result := public.reject_event_change(v_reject, v_coordinator, 'Again', v_decidable, 'o');
    if v_result->>'outcome' is distinct from 'no_open_request' then
        raise exception 'CHANGE FAIL: a second rejection was not refused: %', v_result;
    end if;

    -- Approve an ordinary change (AC2, AC4, Q7): refusals first.
    select version into v_version from public.events where id = v_ordinary;
    v_result := public.approve_event_change(v_ordinary, v_venue_staff, v_version, v_decidable,
        '{"name": "x"}', '{}', 'o');
    if v_result->>'outcome' is distinct from 'not_assigned' then
        raise exception 'CHANGE FAIL: an approval by someone not assigned was not refused: %', v_result;
    end if;
    v_result := public.approve_event_change(v_ordinary, v_coordinator, v_version + 1, v_decidable,
        '{"name": "x"}', '{}', 'o');
    if v_result->>'outcome' is distinct from 'stale'
       or (select name from public.events where id = v_ordinary) <> 'Ordinary change check (rolled back)' then
        raise exception 'CHANGE FAIL: a stale version was not refused, or it changed the event: %', v_result;
    end if;
    v_result := public.approve_event_change(v_started, v_coordinator, 1, v_decidable, '{"name": "b"}', '{}', 'o');
    if v_result->>'outcome' is distinct from 'started' then
        raise exception 'CHANGE FAIL: approving on a started event was not refused: %', v_result;
    end if;
    v_result := public.approve_event_change(v_ordinary, v_coordinator, v_version, array['planning'],
        '{"name": "x"}', '{}', 'o');
    if v_result->>'outcome' is distinct from 'status_changed' then
        raise exception 'CHANGE FAIL: approving in a refused status was not refused: %', v_result;
    end if;

    v_result := public.approve_event_change(v_ordinary, v_coordinator, v_version, v_decidable,
        '{"name": "Renamed (rolled back)"}',
        jsonb_build_object(v_ordinary_space::text, '{"label": "Great hall"}'::jsonb), 'to organiser');
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'CHANGE FAIL: the ordinary approval was refused: %', v_result;
    end if;
    select * into v_event from public.events where id = v_ordinary;
    if v_event.name <> 'Renamed (rolled back)' or v_event.version <> v_version + 1
       or v_event.status <> 'confirmed' or v_result->'event'->>'name' <> 'Renamed (rolled back)' then
        raise exception 'CHANGE FAIL: the ordinary change was not applied once, or it moved the status: %', v_result;
    end if;
    if (select label from public.event_space_requests where id = v_ordinary_space) <> 'Great hall' then
        raise exception 'CHANGE FAIL: the space change was not applied';
    end if;
    if not exists (select 1 from public.venue_bookings where event_id = v_ordinary and status = 'approved') then
        raise exception 'CHANGE FAIL: an ordinary change touched the venue booking';
    end if;
    select * into v_request from public.event_change_requests where event_id = v_ordinary;
    if v_request.status <> 'approved' or v_request.decided_by is distinct from v_coordinator
       or v_request.decided_at is null or v_request.decision_reason is not null then
        raise exception 'CHANGE FAIL: the approved request was not closed as approved by the coordinator';
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_ordinary and type = 'event_change_approved' and recipient_id = v_organiser
       and recipient_role = 'event_organiser' and message = 'to organiser';
    if v_rows <> 1 then raise exception 'CHANGE FAIL: the organiser was not told of the approval once'; end if;
    v_result := public.approve_event_change(v_ordinary, v_coordinator, v_version + 1, v_decidable,
        '{"name": "Again"}', '{}', 'o');
    if v_result->>'outcome' is distinct from 'no_open_request' then
        raise exception 'CHANGE FAIL: a second approval was not refused: %', v_result;
    end if;

    -- AC7: a significant change on a Confirmed event sends it back to Planning, recorded
    -- as the coordinator's, with attendees told of it when the API asks (Q9).
    select version into v_version from public.events where id = 'e0000000-0000-4000-8000-000000003705';
    v_result := public.approve_event_change('e0000000-0000-4000-8000-000000003705', v_coordinator, v_version,
        v_decidable, '{"expected_attendance": 90}', '{}', 'to organiser',
        'Change approved: expected attendance', 'to officers', 'to attendees');
    if v_result->>'outcome' is distinct from 'ok' or v_result->'event'->>'status' <> 'planning' then
        raise exception 'CHANGE FAIL: a significant change left a Confirmed event confirmed: %', v_result;
    end if;
    select count(*) into v_rows from public.event_status_history
     where event_id = 'e0000000-0000-4000-8000-000000003705' and from_status = 'confirmed'
       and to_status = 'planning' and actor_id = v_coordinator and reason = 'Change approved: expected attendance';
    if v_rows <> 1 then raise exception 'CHANGE FAIL: the return to Planning has no history row'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = 'e0000000-0000-4000-8000-000000003705' and type = 'attendee_event_changed'
       and recipient_id = 'a0000000-0000-4000-8000-000000000005' and message = 'to attendees';
    if v_rows <> 1 then raise exception 'CHANGE FAIL: the registered attendee was not told once'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = 'e0000000-0000-4000-8000-000000003705' and recipient_role = 'safety_officer';
    if v_rows <> 0 then raise exception 'CHANGE FAIL: Safety Officers heard of an event not in safety review'; end if;

    select version into v_version from public.events where id = 'e0000000-0000-4000-8000-000000003706';
    v_result := public.approve_event_change('e0000000-0000-4000-8000-000000003706', v_coordinator, v_version,
        v_decidable, '{"expected_attendance": 90}', '{}', 'o', 'r', 'f', null);
    if v_result->'event'->>'status' is distinct from 'planning' then
        raise exception 'CHANGE FAIL: a significant change left a Preparation event in preparation: %', v_result;
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = 'e0000000-0000-4000-8000-000000003706' and type = 'attendee_event_changed';
    if v_rows <> 0 then raise exception 'CHANGE FAIL: attendees were told when the API said not to'; end if;

    -- Q6: from Safety review it also leaves the officers' queue, as a withdrawal.
    select version into v_version from public.events where id = 'e0000000-0000-4000-8000-000000003707';
    v_result := public.approve_event_change('e0000000-0000-4000-8000-000000003707', v_coordinator, v_version,
        v_decidable, '{"expected_attendance": 90}', '{}', 'o', 'r', 'to officers', null);
    if v_result->'event'->>'status' is distinct from 'planning' then
        raise exception 'CHANGE FAIL: a significant change left the event in safety review: %', v_result;
    end if;
    if not exists (select 1 from public.event_safety_decisions
                    where event_id = 'e0000000-0000-4000-8000-000000003707' and decision = 'withdrawn'
                      and reason_code = 'approved_details_changed') then
        raise exception 'CHANGE FAIL: leaving safety review recorded no withdrawal';
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = 'e0000000-0000-4000-8000-000000003707' and type = 'event_returned_to_planning'
       and recipient_id = 'a0000000-0000-4000-8000-000000000006' and recipient_role = 'safety_officer'
       and message = 'to officers';
    if v_rows <> 1 then raise exception 'CHANGE FAIL: the Safety Officer was not told once'; end if;

    select version into v_version from public.events where id = 'e0000000-0000-4000-8000-000000003708';
    v_result := public.approve_event_change('e0000000-0000-4000-8000-000000003708', v_coordinator, v_version,
        v_decidable, '{"expected_attendance": 90}', '{}', 'o', 'r', 'f', null);
    if v_result->'event'->>'status' is distinct from 'planning'
       or exists (select 1 from public.event_status_history
                   where event_id = 'e0000000-0000-4000-8000-000000003708' and from_status is not null) then
        raise exception 'CHANGE FAIL: a Planning event moved or got a status row: %', v_result;
    end if;

    -- AC3, AC5: each planned booking is moved, marked or flagged under the lock.
    select version into v_version from public.events where id = 'e0000000-0000-4000-8000-000000003709';
    v_result := public.approve_event_change('e0000000-0000-4000-8000-000000003709', v_coordinator, v_version,
        v_decidable, '{"starts_at": "2031-04-21T06:00:00Z", "ends_at": "2031-04-21T08:00:00Z"}', '{}', 'o', 'r',
        'f', null, jsonb_build_array(
            jsonb_build_object('booking_id', 'd0000000-0000-4000-8000-000000003791',
                'period', jsonb_build_array('2031-04-21T06:00:00Z', '2031-04-21T08:00:00Z'),
                'mark', 'Date or time changed.'),
            jsonb_build_object('booking_id', 'd0000000-0000-4000-8000-000000003792',
                'period', jsonb_build_array('2031-04-21T06:00:00Z', '2031-04-21T08:00:00Z'),
                'mark', 'Date or time changed.'),
            jsonb_build_object('booking_id', 'd0000000-0000-4000-8000-000000003793',
                'period', jsonb_build_array('2031-04-21T06:00:00Z', '2031-04-21T08:00:00Z')),
            jsonb_build_object('booking_id', 'd0000000-0000-4000-8000-000000003794',
                'unsuitable', 'After an approved change: Crowded needs 150 people; Rooftop Terrace seats 120.'),
            jsonb_build_object('booking_id', 'd0000000-0000-4000-8000-000000003795', 'clear_unsuitable', true),
            jsonb_build_object('booking_id', 'd0000000-0000-4000-8000-000000003797',
                'period', jsonb_build_array('2031-04-21T06:00:00Z', '2031-04-21T08:00:00Z'),
                'mark', 'Date or time changed.')));
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'CHANGE FAIL: the approval with booking plans was refused: %', v_result;
    end if;

    -- Q14: every reservation moves; a line still in stock stays Reserved, a short one keeps its
    -- units and is marked Needs re-review, and the event is no longer technically Ready.
    if exists (select 1 from public.equipment_reservations
                where event_id = 'e0000000-0000-4000-8000-000000003709'
                  and (start_at, end_at) <> ('2031-04-21 14:00+08'::timestamptz, '2031-04-21 16:00+08'::timestamptz)) then
        raise exception 'CHANGE FAIL: a reservation did not move to the new time';
    end if;
    if (select status from public.equipment_requests where id = 'c0000000-0000-4000-8000-000000003791') <> 'reserved'
       or (select needs_re_review_reason from public.equipment_requests where id = 'c0000000-0000-4000-8000-000000003791')
         is distinct from 'Event time changed; 5 free for 8.'
       or (select status from public.equipment_reservations
            where request_line_id = 'c0000000-0000-4000-8000-000000003791') <> 'confirmed' then
        raise exception 'CHANGE FAIL: a short line was not marked, or lost its reservation';
    end if;
    if (select needs_re_review_since from public.equipment_requests where id = 'c0000000-0000-4000-8000-000000003792')
         is not null then
        raise exception 'CHANGE FAIL: a line still in stock was marked';
    end if;
    if (select technical_readiness from public.events where id = 'e0000000-0000-4000-8000-000000003709') <> 'pending' then
        raise exception 'CHANGE FAIL: a marked line left the event technically Ready';
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = 'e0000000-0000-4000-8000-000000003709' and recipient_id = v_coordinator;
    if v_rows <> 0 then raise exception 'CHANGE FAIL: the coordinator was notified of their own approval (NT-R1)'; end if;

    -- A clash (setup included) keeps the old window and is flagged Conflict, not marked (Q11, Q16).
    if (select booked_period from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003791')
         <> tstzrange('2031-04-21 10:00+08', '2031-04-21 12:00+08', '[)')
       or (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003791')
         is distinct from 'conflict'
       or (select flag_reason from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003791')
         <> 'The new time clashes with "Blocking hold (rolled back)".'
       or (select needs_re_review_since from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003791')
         is not null then
        raise exception 'CHANGE FAIL: a clashing booking moved, was marked, or was not flagged Conflict';
    end if;
    if (select flag_reason from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003797')
         is distinct from 'The new time clashes with a venue block (Maintenance).' then
        raise exception 'CHANGE FAIL: a clash with a block was not named: %',
            (select flag_reason from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003797');
    end if;
    -- A clear approved booking moves and is marked; it keeps its approval and its hold.
    if (select booked_period from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003792')
         <> tstzrange('2031-04-21 14:00+08', '2031-04-21 16:00+08', '[)')
       or (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003792') <> 'approved'
       or (select needs_re_review_reason from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003792')
         is distinct from 'Date or time changed.'
       or (select needs_re_review_since from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003792')
         is null then
        raise exception 'CHANGE FAIL: a clear approved booking was not moved and marked';
    end if;
    select count(*) into v_rows from public.venue_booking_history
     where booking_id = 'd0000000-0000-4000-8000-000000003792' and action = 'moved_by_change'
       and old_period = tstzrange('2031-04-21 10:00+08', '2031-04-21 12:00+08', '[)')
       and new_period = tstzrange('2031-04-21 14:00+08', '2031-04-21 16:00+08', '[)')
       and actor_id = v_coordinator;
    if v_rows <> 1 then raise exception 'CHANGE FAIL: the move has no history row with both periods (Q19)'; end if;
    -- A held booking moves without a marker (Q15).
    if (select booked_period from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003793')
         <> tstzrange('2031-04-21 14:00+08', '2031-04-21 16:00+08', '[)')
       or (select needs_re_review_since from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003793')
         is not null then
        raise exception 'CHANGE FAIL: a held booking was not moved, or was marked';
    end if;
    -- Over capacity: flagged Unsuitable; a flag 37 set clears once it fits (Q17).
    if (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003794')
         is distinct from 'unsuitable'
       or (select flag_reason from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003794')
         <> 'After an approved change: Crowded needs 150 people; Rooftop Terrace seats 120.' then
        raise exception 'CHANGE FAIL: an over-capacity booking was not flagged Unsuitable';
    end if;
    if (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003795') is not null
       or (select flagged_at from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003795') is not null then
        raise exception 'CHANGE FAIL: an Unsuitable flag 37 set was not cleared';
    end if;

    -- AC6, Q20: the coordinator sends a marked booking to venue staff; it keeps its hold.
    v_result := public.send_booking_for_re_review('d0000000-0000-4000-8000-000000003792', v_venue_staff, null, 's');
    if v_result->>'outcome' is distinct from 'not_assigned' then
        raise exception 'CHANGE FAIL: someone not assigned sent a booking: %', v_result;
    end if;
    v_result := public.send_booking_for_re_review('d0000000-0000-4000-8000-000000003793', v_coordinator, null, 's');
    if v_result->>'outcome' is distinct from 'not_marked' then
        raise exception 'CHANGE FAIL: an unmarked booking was sent: %', v_result;
    end if;
    v_result := public.send_booking_for_re_review('d0000000-0000-4000-8000-000000003792', v_coordinator,
        '  Please re-check the afternoon  ', 'to venue staff');
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'CHANGE FAIL: sending a marked booking was refused: %', v_result;
    end if;
    if (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003792') <> 're_review'
       or (select needs_re_review_since from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003792')
         is not null then
        raise exception 'CHANGE FAIL: a sent booking is not under re-review, or is still marked';
    end if;
    select count(*) into v_rows from public.venue_booking_history
     where booking_id = 'd0000000-0000-4000-8000-000000003792' and action = 'sent_for_re_review'
       and from_status = 'approved' and to_status = 're_review' and actor_id = v_coordinator
       and reason = 'Please re-check the afternoon';
    if v_rows <> 1 then raise exception 'CHANGE FAIL: sending has no history row with the trimmed note'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = 'e0000000-0000-4000-8000-000000003709' and type = 'venue_booking_re_review'
       and recipient_id = v_venue_staff and recipient_role = 'venue_staff' and message = 'to venue staff';
    if v_rows <> 1 then raise exception 'CHANGE FAIL: venue staff were not told once, as venue staff'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = 'e0000000-0000-4000-8000-000000003709' and type = 'venue_booking_re_review'
       and recipient_id = v_coordinator;
    if v_rows <> 0 then raise exception 'CHANGE FAIL: the coordinator was told of their own send (NT-R1)'; end if;
    v_result := public.send_booking_for_re_review('d0000000-0000-4000-8000-000000003792', v_coordinator, null, 's');
    if v_result->>'outcome' is distinct from 'not_marked' then
        raise exception 'CHANGE FAIL: a booking was sent twice: %', v_result;
    end if;

    -- Q12, Q21: venue staff decide a booking under re-review with the same Approve and Reject.
    select * into v_decision from public.approve_venue_booking('d0000000-0000-4000-8000-000000003792', v_venue_staff,
        'to coordinator');
    if v_decision.outcome is distinct from 'ok' or v_decision.from_status is distinct from 're_review'
       or (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003792') <> 'approved' then
        raise exception 'CHANGE FAIL: venue staff could not re-approve a booking under re-review: %', v_decision;
    end if;
    select count(*) into v_rows from public.venue_booking_history
     where booking_id = 'd0000000-0000-4000-8000-000000003792' and action = 're_review_approved'
       and from_status = 're_review' and to_status = 'approved' and actor_id = v_venue_staff;
    if v_rows <> 1 then raise exception 'CHANGE FAIL: the re-approval is not in the booking history'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = 'e0000000-0000-4000-8000-000000003709' and type = 'venue_booking_approved'
       and recipient_id = v_coordinator and message = 'to coordinator';
    if v_rows <> 1 then raise exception 'CHANGE FAIL: the coordinator was not told of the re-approval'; end if;
    -- An approved booking is decided; re-approving it is refused as before.
    select * into v_decision from public.approve_venue_booking('d0000000-0000-4000-8000-000000003792', v_venue_staff, 'x');
    if v_decision.outcome is distinct from 'not_held' then
        raise exception 'CHANGE FAIL: an approved booking was approved again: %', v_decision;
    end if;

    v_result := public.send_booking_for_re_review('d0000000-0000-4000-8000-000000003711', v_coordinator, null, 's');
    select * into v_decision from public.reject_venue_booking('d0000000-0000-4000-8000-000000003711', v_venue_staff,
        'Banquet doesn''t fit this room', null, 'to coordinator');
    if v_decision.outcome is distinct from 'ok'
       or (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003711') <> 'rejected'
       or (select decision_reason from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003711')
         <> 'Banquet doesn''t fit this room' then
        raise exception 'CHANGE FAIL: venue staff could not reject a booking under re-review: %', v_decision;
    end if;
    if not exists (select 1 from public.venue_booking_history
                    where booking_id = 'd0000000-0000-4000-8000-000000003711' and action = 're_review_rejected'
                      and from_status = 're_review' and to_status = 'rejected') then
        raise exception 'CHANGE FAIL: the re-review rejection is not in the booking history';
    end if;

    -- And a marked equipment line to technical support; it keeps its units.
    v_result := public.send_equipment_line_for_re_review('c0000000-0000-4000-8000-000000003792', v_coordinator,
        null, 't');
    if v_result->>'outcome' is distinct from 'not_marked' then
        raise exception 'CHANGE FAIL: an unmarked line was sent: %', v_result;
    end if;
    v_result := public.send_equipment_line_for_re_review('c0000000-0000-4000-8000-000000003791', v_venue_staff,
        null, 't');
    if v_result->>'outcome' is distinct from 'not_assigned' then
        raise exception 'CHANGE FAIL: someone not assigned sent a line: %', v_result;
    end if;
    v_result := public.send_equipment_line_for_re_review('c0000000-0000-4000-8000-000000003791', v_coordinator,
        '   ', 'to tech support');
    if v_result->>'outcome' is distinct from 'ok'
       or (select status from public.equipment_requests where id = 'c0000000-0000-4000-8000-000000003791') <> 're_review'
       or (select needs_re_review_since from public.equipment_requests where id = 'c0000000-0000-4000-8000-000000003791')
         is not null
       or (select status from public.equipment_reservations
            where request_line_id = 'c0000000-0000-4000-8000-000000003791') <> 'confirmed' then
        raise exception 'CHANGE FAIL: a sent line is not under re-review with its units: %', v_result;
    end if;
    if not exists (select 1 from public.event_technical_history
                    where request_id = 'c0000000-0000-4000-8000-000000003791' and action = 'sent_for_re_review'
                      and from_status = 'reserved' and to_status = 're_review' and actor_id = v_coordinator) then
        raise exception 'CHANGE FAIL: sending the line is not in the technical history';
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = 'e0000000-0000-4000-8000-000000003709' and type = 'equipment_line_re_review'
       and recipient_id = 'a0000000-0000-4000-8000-000000000004' and recipient_role = 'tech_support'
       and message = 'to tech support';
    if v_rows <> 1 then raise exception 'CHANGE FAIL: technical support were not told once'; end if;

    -- Q22: it stays under re-review, takes the new time, and venue staff hear the details changed again.
    select version into v_version from public.events where id = 'e0000000-0000-4000-8000-000000003712';
    v_result := public.approve_event_change('e0000000-0000-4000-8000-000000003712', v_coordinator, v_version,
        v_decidable, '{"ends_at": "2031-04-23T05:00:00Z"}', '{}', 'o', 'r', 'f', null,
        jsonb_build_array(jsonb_build_object('booking_id', 'd0000000-0000-4000-8000-000000003712',
            'period', jsonb_build_array('2031-04-23T02:00:00Z', '2031-04-23T05:00:00Z'),
            'mark', 'Date or time changed.')),
        'details changed again');
    if v_result->>'outcome' is distinct from 'ok'
       or (select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003712') <> 're_review'
       or (select booked_period from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003712')
         <> tstzrange('2031-04-23 10:00+08', '2031-04-23 13:00+08', '[)')
       or (select needs_re_review_since from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000003712')
         is not null then
        raise exception 'CHANGE FAIL: a booking under re-review did not keep its status and take the new time: %', v_result;
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = 'e0000000-0000-4000-8000-000000003712' and type = 'venue_booking_re_review'
       and recipient_id = v_venue_staff and recipient_role = 'venue_staff' and message = 'details changed again';
    if v_rows <> 1 then raise exception 'CHANGE FAIL: venue staff were not told the details changed again'; end if;

    -- Q16, Q17: a Conflict or Unsuitable booking can be replaced (CR-95's path), the
    -- replacement sitting beside it until it is approved.
    select * into v_replacement from public.request_venue_booking_for_space(
        'f0000000-0000-4000-8000-000000003791', 'b0000000-0000-4000-8000-000000000005', v_coordinator,
        null, 'n', 'd0000000-0000-4000-8000-000000003791');
    if v_replacement.outcome is distinct from 'ok' then
        raise exception 'CHANGE FAIL: a Conflict booking could not be replaced: %', v_replacement.outcome;
    end if;
    select * into v_replacement from public.request_venue_booking_for_space(
        'f0000000-0000-4000-8000-000000003794', 'b0000000-0000-4000-8000-000000000002', v_coordinator,
        null, 'n', 'd0000000-0000-4000-8000-000000003794');
    if v_replacement.outcome is distinct from 'ok' then
        raise exception 'CHANGE FAIL: an Unsuitable booking could not be replaced: %', v_replacement.outcome;
    end if;

    raise notice 'CHANGE DECISION CHECKS PASSED';
end;
$$;

rollback;
