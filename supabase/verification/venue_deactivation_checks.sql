-- SCRUM-64 (deactivate a venue from the catalogue): the real deactivate_venue()
-- and reactivate_venue() functions, the shared flag_venue_bookings() that
-- CR-95 and CR-94 reuse, the reason and flag constraints, the inactive-venue
-- refusal in request_venue_booking(), the flagged-booking refusal in
-- safety_approve_event(), and that only the service role can run the new
-- functions.
-- Run with the Supabase MCP execute_sql, `supabase db query --linked -f`, or
-- `psql "$DATABASE_URL" -f`. Raises on the first failure and prints
-- VENUE DEACTIVATION CHECKS PASSED otherwise. Everything runs inside
-- `begin; ... rollback;`, so nothing here leaves a trace.
-- Uses the seeded organiser (…0001), coordinator (…0002), venue staff
-- (…0003), Seminar Room 1 (b0000000-…0003) and Innovation Lab is untouched.

begin;

-- Throwaway events, all assigned to the seeded coordinator, each with one
-- booking at Seminar Room 1 in 2031 (or 2020 for the one that has ended).
insert into public.events (id, organiser_id, coordinator_id, status, name, expected_attendance, starts_at, ends_at)
values
    ('e0000000-0000-4000-8000-0000000064a1', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Deactivation check held (rolled back)', 20, '2031-06-01 10:00+08', '2031-06-01 12:00+08'),
    ('e0000000-0000-4000-8000-0000000064a2', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Deactivation check approved (rolled back)', 20, '2031-06-02 10:00+08', '2031-06-02 12:00+08'),
    ('e0000000-0000-4000-8000-0000000064a3', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Deactivation check ended (rolled back)', 20, '2020-06-03 10:00+08', '2020-06-03 12:00+08'),
    ('e0000000-0000-4000-8000-0000000064a4', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Deactivation check re-review (rolled back)', 20, '2031-06-04 10:00+08', '2031-06-04 12:00+08'),
    ('e0000000-0000-4000-8000-0000000064a5', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Deactivation check released (rolled back)', 20, '2031-06-05 10:00+08', '2031-06-05 12:00+08'),
    ('e0000000-0000-4000-8000-0000000064a6', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Deactivation check already flagged (rolled back)', 20, '2031-06-06 10:00+08', '2031-06-06 12:00+08'),
    ('e0000000-0000-4000-8000-0000000064a7', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Deactivation check new request (rolled back)', 20, '2031-06-07 10:00+08', '2031-06-07 12:00+08'),
    ('e0000000-0000-4000-8000-0000000064a8', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'safety_review', 'Deactivation check approval (rolled back)', 20, '2031-06-08 10:00+08', '2031-06-08 12:00+08');

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status)
values
    ('d0000000-0000-4000-8000-0000000064b1', 'e0000000-0000-4000-8000-0000000064a1', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-06-01 10:00+08', '2031-06-01 12:00+08', '[)'), 'held'),
    ('d0000000-0000-4000-8000-0000000064b2', 'e0000000-0000-4000-8000-0000000064a2', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-06-02 10:00+08', '2031-06-02 12:00+08', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000064b3', 'e0000000-0000-4000-8000-0000000064a3', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2020-06-03 10:00+08', '2020-06-03 12:00+08', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000064b4', 'e0000000-0000-4000-8000-0000000064a4', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-06-04 10:00+08', '2031-06-04 12:00+08', '[)'), 're_review'),
    ('d0000000-0000-4000-8000-0000000064b5', 'e0000000-0000-4000-8000-0000000064a5', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-06-05 10:00+08', '2031-06-05 12:00+08', '[)'), 'released'),
    ('d0000000-0000-4000-8000-0000000064b6', 'e0000000-0000-4000-8000-0000000064a6', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-06-06 10:00+08', '2031-06-06 12:00+08', '[)'), 'approved'),
    -- The approval case: an approved, flagged booking at another venue.
    ('d0000000-0000-4000-8000-0000000064b8', 'e0000000-0000-4000-8000-0000000064a8', 'b0000000-0000-4000-8000-000000000001',
     tstzrange('2031-06-08 10:00+08', '2031-06-08 12:00+08', '[)'), 'approved');

-- Already flagged by another story (CR-94): must stay as it is.
update public.venue_bookings
   set flag = 'conflict', flag_reason = 'Conflict from a venue change', flagged_at = now()
 where id = 'd0000000-0000-4000-8000-0000000064b6';
update public.venue_bookings
   set flag = 'affected', flag_reason = 'Venue unavailable', flagged_at = now()
 where id = 'd0000000-0000-4000-8000-0000000064b8';

do $$
declare
    v_venue uuid := 'b0000000-0000-4000-8000-000000000003';
    v_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_before public.venues;
    v_after public.venues;
    v_outcome text;
    v_events uuid[];
    v_rows integer;
begin
    select * into v_before from public.venues where id = v_venue;
    if not v_before.is_active then raise exception 'SETUP FAIL: Seminar Room 1 should start active'; end if;

    -- Refusals change nothing.
    select outcome into v_outcome from public.deactivate_venue(
        v_venue, v_staff, v_before.version - 1, 'permanently_closed', null, '{}'::jsonb, '{}'::jsonb,
        'Venue deactivated: permanently closed', 'msg');
    if v_outcome <> 'stale' then raise exception 'DEACTIVATE FAIL: stale version gave %', v_outcome; end if;
    select outcome into v_outcome from public.deactivate_venue(
        'b0000000-0000-4000-8000-0000000000ff', v_staff, 0, 'permanently_closed', null, '{}'::jsonb, '{}'::jsonb,
        'Venue deactivated: permanently closed', 'msg');
    if v_outcome <> 'venue_not_found' then raise exception 'DEACTIVATE FAIL: unknown venue gave %', v_outcome; end if;
    if not (select is_active from public.venues where id = v_venue) then
        raise exception 'DEACTIVATE FAIL: a refused call changed the venue';
    end if;

    -- Deactivate (AC1, AC3).
    select outcome, event_ids into v_outcome, v_events from public.deactivate_venue(
        v_venue, v_staff, v_before.version, 'long_term_renovation', '  Roof works  ',
        jsonb_build_object('is_active', true), jsonb_build_object('is_active', false),
        'Venue deactivated: long-term renovation — Roof works',
        'Venue "Seminar Room 1" has been deactivated (Long-term renovation).');
    if v_outcome <> 'ok' then raise exception 'DEACTIVATE FAIL: outcome %', v_outcome; end if;
    if not (v_events @> array['e0000000-0000-4000-8000-0000000064a1', 'e0000000-0000-4000-8000-0000000064a2']::uuid[]) then
        raise exception 'DEACTIVATE FAIL: flagged events not returned: %', v_events;
    end if;
    if v_events && array['e0000000-0000-4000-8000-0000000064a3', 'e0000000-0000-4000-8000-0000000064a4',
                         'e0000000-0000-4000-8000-0000000064a5', 'e0000000-0000-4000-8000-0000000064a6']::uuid[] then
        raise exception 'DEACTIVATE FAIL: returned an event whose booking must not be flagged: %', v_events;
    end if;

    select * into v_after from public.venues where id = v_venue;
    if v_after.is_active or v_after.inactive_reason is distinct from 'long_term_renovation'
       or v_after.inactive_note is distinct from 'Roof works' then
        raise exception 'DEACTIVATE FAIL: venue not inactive with its reason and trimmed note';
    end if;
    if v_after.version <> v_before.version + 1 or v_after.updated_by is distinct from v_staff then
        raise exception 'DEACTIVATE FAIL: version or updated_by not stamped';
    end if;
    select count(*) into v_rows from public.venue_edit_history
     where venue_id = v_venue and actor_id = v_staff and after = jsonb_build_object('is_active', false);
    if v_rows <> 1 then raise exception 'DEACTIVATE FAIL: expected one history row, got %', v_rows; end if;

    select count(*) into v_rows from public.venue_bookings
     where id in ('d0000000-0000-4000-8000-0000000064b1', 'd0000000-0000-4000-8000-0000000064b2')
       and flag = 'affected' and flag_reason = 'Venue deactivated: long-term renovation — Roof works'
       and flagged_at is not null and status in ('held', 'approved');
    if v_rows <> 2 then raise exception 'DEACTIVATE FAIL: held/approved bookings not flagged (got %)', v_rows; end if;

    select count(*) into v_rows from public.venue_bookings
     where id in ('d0000000-0000-4000-8000-0000000064b3', 'd0000000-0000-4000-8000-0000000064b4',
                  'd0000000-0000-4000-8000-0000000064b5') and flag is not null;
    if v_rows <> 0 then raise exception 'DEACTIVATE FAIL: ended, re_review or released booking flagged'; end if;
    if (select flag::text || '|' || flag_reason from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000064b6')
       <> 'conflict|Conflict from a venue change' then
        raise exception 'DEACTIVATE FAIL: an existing flag was overwritten';
    end if;

    select count(*) into v_rows from public.notifications
     where type = 'venue_booking_affected' and recipient_id = v_coordinator
       and event_id in ('e0000000-0000-4000-8000-0000000064a1', 'e0000000-0000-4000-8000-0000000064a2');
    if v_rows <> 2 then raise exception 'DEACTIVATE FAIL: expected 2 coordinator notifications, got %', v_rows; end if;
    select count(*) into v_rows from public.notifications
     where type = 'venue_booking_affected'
       and event_id in ('e0000000-0000-4000-8000-0000000064a3', 'e0000000-0000-4000-8000-0000000064a4',
                        'e0000000-0000-4000-8000-0000000064a5', 'e0000000-0000-4000-8000-0000000064a6');
    if v_rows <> 0 then raise exception 'DEACTIVATE FAIL: notified an event whose booking was not flagged'; end if;

    -- A second deactivate is refused and changes nothing.
    select outcome into v_outcome from public.deactivate_venue(
        v_venue, v_staff, v_after.version, 'permanently_closed', null, '{}'::jsonb, '{}'::jsonb, 'x', 'msg');
    if v_outcome <> 'already_inactive' then raise exception 'DEACTIVATE FAIL: second call gave %', v_outcome; end if;

    -- AC2: no new requests for an inactive venue.
    select outcome into v_outcome from public.request_venue_booking(
        'e0000000-0000-4000-8000-0000000064a7', v_venue, v_coordinator, null, 'requested');
    if v_outcome <> 'venue_inactive' then raise exception 'REQUEST FAIL: inactive venue gave %', v_outcome; end if;

    -- AC4: reactivate; flags stay.
    select outcome into v_outcome from (select public.reactivate_venue(
        v_venue, v_staff, v_after.version - 1, '{}'::jsonb, '{}'::jsonb) as outcome) r;
    if v_outcome <> 'stale' then raise exception 'REACTIVATE FAIL: stale version gave %', v_outcome; end if;
    v_outcome := public.reactivate_venue(v_venue, v_staff, v_after.version,
        jsonb_build_object('is_active', false), jsonb_build_object('is_active', true));
    if v_outcome <> 'ok' then raise exception 'REACTIVATE FAIL: outcome %', v_outcome; end if;
    select * into v_after from public.venues where id = v_venue;
    if not v_after.is_active or v_after.inactive_reason is not null or v_after.inactive_note is not null then
        raise exception 'REACTIVATE FAIL: venue not active with reason and note cleared';
    end if;
    select count(*) into v_rows from public.venue_bookings
     where id in ('d0000000-0000-4000-8000-0000000064b1', 'd0000000-0000-4000-8000-0000000064b2') and flag = 'affected';
    if v_rows <> 2 then raise exception 'REACTIVATE FAIL: reactivation cleared flags'; end if;
    v_outcome := public.reactivate_venue(v_venue, v_staff, v_after.version, '{}'::jsonb, '{}'::jsonb);
    if v_outcome <> 'already_active' then raise exception 'REACTIVATE FAIL: second call gave %', v_outcome; end if;
    v_outcome := public.reactivate_venue('b0000000-0000-4000-8000-0000000000ff', v_staff, 0, '{}'::jsonb, '{}'::jsonb);
    if v_outcome <> 'venue_not_found' then raise exception 'REACTIVATE FAIL: unknown venue gave %', v_outcome; end if;

    -- The approval recheck refuses a flagged booking (82 AC10, CR-104 AC5).
    select count(*) into v_rows from public.safety_approve_event(
        'e0000000-0000-4000-8000-0000000064a8', v_staff,
        (select version from public.events where id = 'e0000000-0000-4000-8000-0000000064a8'), 'ok', 'o', 's');
    if v_rows <> 0 then raise exception 'APPROVE FAIL: approved an event with a flagged booking'; end if;
    if (select status::text from public.events where id = 'e0000000-0000-4000-8000-0000000064a8') <> 'safety_review' then
        raise exception 'APPROVE FAIL: event left safety review';
    end if;
end $$;

-- Constraints.
do $$
begin
    begin
        update public.venues set is_active = false where id = 'b0000000-0000-4000-8000-000000000001';
        raise exception 'CONSTRAINT FAIL: inactive venue without a reason accepted';
    exception when check_violation then null;
    end;
    begin
        update public.venues set is_active = false, inactive_reason = 'other', inactive_note = '   '
         where id = 'b0000000-0000-4000-8000-000000000001';
        raise exception 'CONSTRAINT FAIL: reason other with a blank note accepted';
    exception when check_violation then null;
    end;
    begin
        update public.venues set is_active = false, inactive_reason = 'other', inactive_note = null
         where id = 'b0000000-0000-4000-8000-000000000001';
        raise exception 'CONSTRAINT FAIL: reason other with no note accepted';
    exception when check_violation then null;
    end;
    begin
        update public.venues set inactive_reason = 'permanently_closed' where id = 'b0000000-0000-4000-8000-000000000001';
        raise exception 'CONSTRAINT FAIL: active venue with a reason accepted';
    exception when check_violation then null;
    end;
    begin
        update public.venue_bookings set flag = 'affected', flag_reason = null, flagged_at = now()
         where id = 'd0000000-0000-4000-8000-0000000064b1';
        raise exception 'CONSTRAINT FAIL: flag without a reason accepted';
    exception when check_violation then null;
    end;
end $$;

-- Only the service role may run the new functions.
set local role authenticated;
do $$
begin
    begin
        perform public.deactivate_venue('b0000000-0000-4000-8000-000000000003', null, 0, 'other', 'x', '{}', '{}', 'x', 'x');
        raise exception 'GRANT FAIL: authenticated can run deactivate_venue';
    exception when insufficient_privilege then null;
    end;
    begin
        perform public.reactivate_venue('b0000000-0000-4000-8000-000000000003', null, 0, '{}', '{}');
        raise exception 'GRANT FAIL: authenticated can run reactivate_venue';
    exception when insufficient_privilege then null;
    end;
    begin
        perform public.flag_venue_bookings('b0000000-0000-4000-8000-000000000003', tstzrange(now(), null), 'affected', 'x', 'x');
        raise exception 'GRANT FAIL: authenticated can run flag_venue_bookings';
    exception when insufficient_privilege then null;
    end;
end $$;
reset role;

set local role anon;
do $$
begin
    begin
        perform public.flag_venue_bookings('b0000000-0000-4000-8000-000000000003', tstzrange(now(), null), 'affected', 'x', 'x');
        raise exception 'GRANT FAIL: anon can run flag_venue_bookings';
    exception when insufficient_privilege then null;
    end;
    begin
        perform public.deactivate_venue('b0000000-0000-4000-8000-000000000003', null, 0, 'other', 'x', '{}', '{}', 'x', 'x');
        raise exception 'GRANT FAIL: anon can run deactivate_venue';
    exception when insufficient_privilege then null;
    end;
end $$;
reset role;

select 'VENUE DEACTIVATION CHECKS PASSED' as result;

rollback;
