-- SCRUM-63 (update venue capacity and facilities information): the real
-- update_venue() function, the version-checked write, the venue_layouts and
-- venue_facilities replace, the venue_edit_history row, the notification for
-- an affected booking's coordinator, and venue_edit_history's RLS.
-- CR-94: the Unsuitable flags update_venue writes through flag_venue_bookings
-- (one booking per entry; first flag wins; re-review and inactive bookings get
-- the coordinator notification instead), and who may run the function.
-- Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`. Raises on
-- the first failure and prints VENUE EDIT CHECKS PASSED otherwise. Everything
-- runs inside `begin; ... rollback;`, so nothing here leaves a trace.
-- Run on the live project with `supabase db query --linked -f`.
-- Uses the seeded organiser (…0001), coordinator (…0002), venue staff
-- (…0003), and Seminar Room 1 (b0000000-…0003, capacity 60).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, expected_attendance)
values ('e0000000-0000-4000-8000-0000000003a2', 'a0000000-0000-4000-8000-000000000001',
        'a0000000-0000-4000-8000-000000000002', 'planning', 'Venue edit check (rolled back)', 55);

-- CR-94: throwaway events at Seminar Room 1 in July 2031, each with one booking.
insert into public.events (id, organiser_id, coordinator_id, status, name, expected_attendance, starts_at, ends_at)
values
    ('e0000000-0000-4000-8000-0000000094a1', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'CR-94 check held (rolled back)', 55, '2031-07-01 10:00+08', '2031-07-01 12:00+08'),
    ('e0000000-0000-4000-8000-0000000094a2', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'CR-94 check neighbour (rolled back)', 20, '2031-07-01 12:00+08', '2031-07-01 14:00+08'),
    ('e0000000-0000-4000-8000-0000000094a3', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'CR-94 check already flagged (rolled back)', 55, '2031-07-02 10:00+08', '2031-07-02 12:00+08'),
    ('e0000000-0000-4000-8000-0000000094a4', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'CR-94 check re-review (rolled back)', 55, '2031-07-03 10:00+08', '2031-07-03 12:00+08'),
    ('e0000000-0000-4000-8000-0000000094a5', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'CR-94 check stale (rolled back)', 55, '2031-07-04 10:00+08', '2031-07-04 12:00+08');

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status)
values
    ('d0000000-0000-4000-8000-0000000094b1', 'e0000000-0000-4000-8000-0000000094a1', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-01 10:00+08', '2031-07-01 12:00+08', '[)'), 'held'),
    -- Back to back with b1: flag_venue_bookings must not reach it.
    ('d0000000-0000-4000-8000-0000000094b2', 'e0000000-0000-4000-8000-0000000094a2', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-01 12:00+08', '2031-07-01 14:00+08', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000094b3', 'e0000000-0000-4000-8000-0000000094a3', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-02 10:00+08', '2031-07-02 12:00+08', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000094b4', 'e0000000-0000-4000-8000-0000000094a4', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-03 10:00+08', '2031-07-03 12:00+08', '[)'), 're_review'),
    ('d0000000-0000-4000-8000-0000000094b5', 'e0000000-0000-4000-8000-0000000094a5', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-04 10:00+08', '2031-07-04 12:00+08', '[)'), 'held');

update public.venue_bookings
   set flag = 'affected', flag_reason = 'Venue unavailable', flagged_at = now()
 where id = 'd0000000-0000-4000-8000-0000000094b3';

do $$
declare
    v_venue uuid := 'b0000000-0000-4000-8000-000000000003';
    v_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_event uuid := 'e0000000-0000-4000-8000-0000000003a2';
    v_before public.venues;
    v_after public.venues;
    v_rows integer;
    v_result jsonb;
begin
    select * into v_before from public.venues where id = v_venue;

    -- A stale version changes nothing, and flags nothing (CR-94).
    v_result := public.update_venue(
        v_venue, v_staff, v_before.version - 1,
        v_before.name, v_before.location, v_before.capacity, v_before.opens_at, v_before.closes_at, v_before.description,
        v_before.accessibility_features, '[]'::jsonb, array[]::public.facility[],
        '{}'::jsonb, '{}'::jsonb, '[]'::jsonb,
        jsonb_build_array(jsonb_build_object(
            'booking_id', 'd0000000-0000-4000-8000-0000000094b5', 'event_id', 'e0000000-0000-4000-8000-0000000094a5',
            'coordinator_id', v_coordinator, 'reason', 'stale', 'message', 'stale', 'unflagged_message', 'stale')));
    if v_result is not null then raise exception 'VENUE EDIT FAIL: a stale update_venue call returned a result'; end if;
    if (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000094b5') is not null then
        raise exception 'VENUE EDIT FAIL: a stale call flagged a booking';
    end if;
    if (select capacity from public.venues where id = v_venue) is distinct from v_before.capacity then
        raise exception 'VENUE EDIT FAIL: a stale call changed the venue';
    end if;

    -- Reduce capacity below the event's expected attendance, replace the
    -- layouts and facilities, and notify the event's coordinator (VC-R2).
    v_result := public.update_venue(
        v_venue, v_staff, v_before.version,
        v_before.name, v_before.location, 50, v_before.opens_at, v_before.closes_at, 'Edited by the check',
        v_before.accessibility_features,
        '[{"layout":"boardroom","capacity_for_layout":40}]'::jsonb,
        array['projector']::public.facility[],
        jsonb_build_object('capacity', v_before.capacity),
        jsonb_build_object('capacity', 50),
        jsonb_build_array(jsonb_build_object(
            'recipient_id', v_coordinator, 'event_id', v_event,
            'message', 'Venue "Seminar Room 1" changed in a way that may affect "Venue edit check (rolled back)": Capacity no longer covers this event''s expected attendance of 55.'
        )),
        -- CR-94: three Unsuitable bookings - one flaggable, one already
        -- flagged, one in re-review.
        (select jsonb_agg(jsonb_build_object(
            'booking_id', b, 'event_id', e, 'coordinator_id', v_coordinator,
            'reason', 'Venue "Seminar Room 1" was edited: Capacity 50 is below the expected attendance of 55.',
            'message', 'flagged ' || e, 'unflagged_message', 'unflagged ' || e))
           from (values
               ('d0000000-0000-4000-8000-0000000094b1'::uuid, 'e0000000-0000-4000-8000-0000000094a1'::uuid),
               ('d0000000-0000-4000-8000-0000000094b3', 'e0000000-0000-4000-8000-0000000094a3'),
               ('d0000000-0000-4000-8000-0000000094b4', 'e0000000-0000-4000-8000-0000000094a4')) as t(b, e)));
    select * into v_after from public.venues where id = v_venue;

    if v_result -> 'flagged_event_ids' <> '["e0000000-0000-4000-8000-0000000094a1"]'::jsonb then
        raise exception 'VENUE EDIT FAIL (CR-94): expected only the held booking''s event flagged, got %', v_result;
    end if;
    if v_result ->> 'venue_id' <> v_venue::text then
        raise exception 'VENUE EDIT FAIL: the result does not name the venue';
    end if;

    if v_after.capacity <> 50 or v_after.description <> 'Edited by the check' then
        raise exception 'VENUE EDIT FAIL: the update did not apply the submitted attributes';
    end if;
    if v_after.version <> v_before.version + 1 then
        raise exception 'VENUE EDIT FAIL: version did not advance by exactly one';
    end if;
    if v_after.updated_by is distinct from v_staff then
        raise exception 'VENUE EDIT FAIL: updated_by was not stamped with the actor';
    end if;

    select count(*) into v_rows from public.venue_layouts where venue_id = v_venue;
    if v_rows <> 1 then raise exception 'VENUE EDIT FAIL: layouts were not replaced (got % rows)', v_rows; end if;
    if not exists (
        select 1 from public.venue_layouts
         where venue_id = v_venue and layout = 'boardroom' and capacity_for_layout = 40
    ) then
        raise exception 'VENUE EDIT FAIL: the new layout was not written';
    end if;

    select count(*) into v_rows from public.venue_facilities where venue_id = v_venue;
    if v_rows <> 1 then raise exception 'VENUE EDIT FAIL: facilities were not replaced (got % rows)', v_rows; end if;
    if not exists (select 1 from public.venue_facilities where venue_id = v_venue and facility = 'projector') then
        raise exception 'VENUE EDIT FAIL: the new facility was not written';
    end if;

    select count(*) into v_rows from public.venue_edit_history
     where venue_id = v_venue and actor_id = v_staff
       and before = jsonb_build_object('capacity', v_before.capacity)
       and after = jsonb_build_object('capacity', 50)
       and created_at = now();  -- this run's row only (D39)
    if v_rows <> 1 then raise exception 'VENUE EDIT FAIL: the edit was not recorded in venue_edit_history (VC-R3)'; end if;

    select count(*) into v_rows from public.notifications
     where event_id = v_event and recipient_id = v_coordinator and type = 'venue_updated_affects_booking';
    if v_rows <> 1 then raise exception 'VENUE EDIT FAIL: the affected event''s coordinator was not notified'; end if;

    -- CR-94 AC3, AC5: the flaggable booking is flagged Unsuitable with its
    -- reason, and its coordinator gets flag_venue_bookings' notification only.
    if not exists (
        select 1 from public.venue_bookings
         where id = 'd0000000-0000-4000-8000-0000000094b1' and flag = 'unsuitable' and status = 'held'
           and flag_reason = 'Venue "Seminar Room 1" was edited: Capacity 50 is below the expected attendance of 55.'
    ) then
        raise exception 'VENUE EDIT FAIL (CR-94): the held booking was not flagged Unsuitable with its reason';
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = 'e0000000-0000-4000-8000-0000000094a1' and recipient_id = v_coordinator;
    if v_rows <> 1 or not exists (
        select 1 from public.notifications where event_id = 'e0000000-0000-4000-8000-0000000094a1'
           and type = 'venue_booking_affected' and message = 'flagged e0000000-0000-4000-8000-0000000094a1'
    ) then
        raise exception 'VENUE EDIT FAIL (CR-94): the flagged booking''s coordinator should get exactly the flag notification';
    end if;

    -- The neighbouring booking is untouched.
    if (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000094b2') is not null then
        raise exception 'VENUE EDIT FAIL (CR-94): a booking that was not listed got flagged';
    end if;

    -- First flag wins; re-review is not flagged. Both coordinators get the
    -- unflagged message instead.
    if (select (flag, flag_reason) from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000094b3')
       is distinct from ('affected'::public.venue_booking_flag, 'Venue unavailable'::text) then
        raise exception 'VENUE EDIT FAIL (CR-94): an existing flag was overwritten';
    end if;
    if (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000094b4') is not null then
        raise exception 'VENUE EDIT FAIL (CR-94): a re-review booking was flagged';
    end if;
    select count(*) into v_rows from public.notifications
     where event_id in ('e0000000-0000-4000-8000-0000000094a3', 'e0000000-0000-4000-8000-0000000094a4')
       and recipient_id = v_coordinator and type = 'venue_updated_affects_booking'
       and message = 'unflagged ' || event_id;
    if v_rows <> 2 then
        raise exception 'VENUE EDIT FAIL (CR-94): unflaggable bookings'' coordinators were not notified (got %)', v_rows;
    end if;
    select count(*) into v_rows from public.notifications
     where event_id in ('e0000000-0000-4000-8000-0000000094a3', 'e0000000-0000-4000-8000-0000000094a4');
    if v_rows <> 2 then
        raise exception 'VENUE EDIT FAIL (CR-94): unflaggable bookings got extra notifications (got %)', v_rows;
    end if;

    -- AC6: flagging changes no booking's status or period.
    if exists (
        select 1 from public.venue_bookings
         where id in ('d0000000-0000-4000-8000-0000000094b1', 'd0000000-0000-4000-8000-0000000094b4')
           and status not in ('held', 're_review')
    ) then
        raise exception 'VENUE EDIT FAIL (CR-94): flagging changed a booking''s status';
    end if;

    -- Facilities can be cleared back to none.
    v_result := public.update_venue(
        v_venue, v_staff, v_after.version,
        v_after.name, v_after.location, v_after.capacity, v_after.opens_at, v_after.closes_at, v_after.description,
        v_after.accessibility_features, '[]'::jsonb, array[]::public.facility[],
        '{}'::jsonb, '{}'::jsonb, '[]'::jsonb);
    if v_result -> 'flagged_event_ids' <> '[]'::jsonb then
        raise exception 'VENUE EDIT FAIL: an edit with no flags reported flagged events';
    end if;
    select count(*) into v_rows from public.venue_facilities where venue_id = v_venue;
    if v_rows <> 0 then raise exception 'VENUE EDIT FAIL: facilities were not cleared to none'; end if;
    select count(*) into v_rows from public.venue_layouts where venue_id = v_venue;
    if v_rows <> 0 then raise exception 'VENUE EDIT FAIL: layouts were not cleared to none'; end if;
end $$;

-- RLS: a coordinator or venue staff member can read the history directly; an
-- organiser sees nothing (same readers as the venue catalogue itself).
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
declare
    v_count int;
begin
    -- Only the two rows this run wrote: they share the transaction's now(),
    -- and any real edit to Seminar Room 1 is older (D39).
    select count(*) into v_count from public.venue_edit_history
     where venue_id = 'b0000000-0000-4000-8000-000000000003'
       and created_at = now();
    if v_count <> 2 then
        raise exception 'RLS FAIL: coordinator sees % history rows, expected 2', v_count;
    end if;
end $$;
reset role;

select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if exists (select 1 from public.venue_edit_history where venue_id = 'b0000000-0000-4000-8000-000000000003') then
        raise exception 'RLS FAIL: organiser can read venue edit history';
    end if;
end $$;
reset role;

set local role anon;
do $$
begin
    if exists (select 1 from public.venue_edit_history) then
        raise exception 'RLS FAIL: anon can read venue edit history';
    end if;
end $$;
reset role;

-- Only the service role may run update_venue; the old signature is gone.
do $$
declare
    v_sig text := 'public.update_venue(uuid, uuid, integer, varchar, varchar, integer, time, time, text, '
                  'public.accessibility_feature[], jsonb, public.facility[], jsonb, jsonb, jsonb, jsonb)';
begin
    if has_function_privilege('anon', v_sig, 'execute') or has_function_privilege('authenticated', v_sig, 'execute') then
        raise exception 'GRANT FAIL: anon or authenticated can run update_venue';
    end if;
    if not has_function_privilege('service_role', v_sig, 'execute') then
        raise exception 'GRANT FAIL: service_role cannot run update_venue';
    end if;
    if (select count(*) from pg_proc where proname = 'update_venue' and pronamespace = 'public'::regnamespace) <> 1 then
        raise exception 'VENUE EDIT FAIL: more than one update_venue exists';
    end if;
end $$;

select 'VENUE EDIT CHECKS PASSED' as result;

rollback;
