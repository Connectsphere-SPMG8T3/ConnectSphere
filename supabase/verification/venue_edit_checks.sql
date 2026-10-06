-- SCRUM-63 (update venue capacity and facilities information): the real
-- update_venue() function, the version-checked write, the venue_layouts and
-- venue_facilities replace, the venue_edit_history row, the notification for
-- an affected booking's coordinator, and venue_edit_history's RLS.
-- Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`. Raises on
-- the first failure and prints VENUE EDIT CHECKS PASSED otherwise. Everything
-- runs inside `begin; ... rollback;`, so nothing here leaves a trace.
-- Uses the seeded organiser (…0001), coordinator (…0002), venue staff
-- (…0003), and Seminar Room 1 (b0000000-…0003, capacity 60).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, expected_attendance)
values ('e0000000-0000-4000-8000-0000000003a2', 'a0000000-0000-4000-8000-000000000001',
        'a0000000-0000-4000-8000-000000000002', 'planning', 'Venue edit check (rolled back)', 55);

do $$
declare
    v_venue uuid := 'b0000000-0000-4000-8000-000000000003';
    v_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_event uuid := 'e0000000-0000-4000-8000-0000000003a2';
    v_before public.venues;
    v_after public.venues;
    v_rows integer;
begin
    select * into v_before from public.venues where id = v_venue;

    -- A stale version changes nothing.
    select count(*) into v_rows from public.update_venue(
        v_venue, v_staff, v_before.version - 1,
        v_before.name, v_before.location, v_before.capacity, v_before.opens_at, v_before.closes_at, v_before.description,
        v_before.accessibility_features, '[]'::jsonb, array[]::public.facility[],
        '{}'::jsonb, '{}'::jsonb, '[]'::jsonb);
    if v_rows <> 0 then raise exception 'VENUE EDIT FAIL: a stale update_venue call returned a row'; end if;
    if (select capacity from public.venues where id = v_venue) is distinct from v_before.capacity then
        raise exception 'VENUE EDIT FAIL: a stale call changed the venue';
    end if;

    -- Reduce capacity below the event's expected attendance, replace the
    -- layouts and facilities, and notify the event's coordinator (VC-R2).
    select * into v_after from public.update_venue(
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
        )));

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
       and after = jsonb_build_object('capacity', 50);
    if v_rows <> 1 then raise exception 'VENUE EDIT FAIL: the edit was not recorded in venue_edit_history (VC-R3)'; end if;

    select count(*) into v_rows from public.notifications
     where event_id = v_event and recipient_id = v_coordinator and type = 'venue_updated_affects_booking';
    if v_rows <> 1 then raise exception 'VENUE EDIT FAIL: the affected event''s coordinator was not notified'; end if;

    -- Facilities can be cleared back to none.
    select * into v_after from public.update_venue(
        v_venue, v_staff, v_after.version,
        v_after.name, v_after.location, v_after.capacity, v_after.opens_at, v_after.closes_at, v_after.description,
        v_after.accessibility_features, '[]'::jsonb, array[]::public.facility[],
        '{}'::jsonb, '{}'::jsonb, '[]'::jsonb);
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
    select count(*) into v_count from public.venue_edit_history
     where venue_id = 'b0000000-0000-4000-8000-000000000003';
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

select 'VENUE EDIT CHECKS PASSED' as result;

rollback;
