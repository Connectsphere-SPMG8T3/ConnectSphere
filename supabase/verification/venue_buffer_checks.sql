-- CR-100 AC1, AC2, AC5, AC6: exercise the real edit and both booking RPCs.
-- Only throwaway rows; all changes are rolled back. No shared venue is edited.
begin;

do $$
declare
    v_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_venue public.venues;
    v_other uuid;
    v_event uuid;
    v_space uuid;
    v_booking public.venue_bookings;
    v_old public.venue_bookings;
    v_result record;
    v_edited jsonb;
    v_before jsonb;
    v_after jsonb;
    v_path integer;
    v_index integer;
    v_base timestamptz;
begin
    insert into public.venues (name, location, capacity, opens_at, closes_at)
    values ('CR-100 buffer check (rolled back)', 'Test', 100, '00:00', '23:59') returning * into v_venue;
    insert into public.venues (name, location, capacity, opens_at, closes_at)
    values ('CR-100 independent venue (rolled back)', 'Test', 100, '00:00', '23:59') returning id into v_other;
    if v_venue.setup_minutes <> 0 or v_venue.turnaround_minutes <> 0 then
        raise exception 'CR-100 FAIL: defaults must be zero';
    end if;

    -- No business maximum; negative and null values remain invalid.
    update public.venues set setup_minutes = 1000000, turnaround_minutes = 1000000 where id = v_venue.id;
    begin
        update public.venues set setup_minutes = -1 where id = v_venue.id;
        raise exception 'CR-100 FAIL: negative setup accepted';
    exception when check_violation then null; end;
    begin
        update public.venues set turnaround_minutes = -1 where id = v_venue.id;
        raise exception 'CR-100 FAIL: negative turnaround accepted';
    exception when check_violation then null; end;
    begin
        update public.venues set setup_minutes = null where id = v_venue.id;
        raise exception 'CR-100 FAIL: null setup accepted';
    exception when not_null_violation then null; end;

    -- The public edit RPC keeps its interface: the new values are in p_after.
    v_before := jsonb_build_object('setup_minutes', 1000000, 'turnaround_minutes', 1000000);
    v_after := jsonb_build_object('setup_minutes', 30, 'turnaround_minutes', 45,
                                 'emergency_access', 'East exit', 'restrictions', 'No flames');
    select * into v_venue from public.venues where id = v_venue.id;
    v_edited := public.update_venue(v_venue.id, v_staff, v_venue.version,
        v_venue.name, v_venue.location, v_venue.capacity, v_venue.opens_at, v_venue.closes_at,
        v_venue.description, v_venue.accessibility_features, '[]', array[]::public.facility[], v_before, v_after);
    select * into v_venue from public.venues where id = v_venue.id;
    if v_edited is null or v_venue.setup_minutes <> 30 or v_venue.turnaround_minutes <> 45
       or v_venue.emergency_access is distinct from 'East exit' or v_venue.restrictions is distinct from 'No flames' then
        raise exception 'CR-100 FAIL: edit did not persist buffer/safety fields';
    end if;
    if not exists (select 1 from public.venue_edit_history where venue_id = v_venue.id
                   and actor_id = v_staff and before = v_before and after = v_after and created_at = now()) then
        raise exception 'CR-100 FAIL: history missing actor/time/before/after';
    end if;
    if exists (select 1 from public.venues where id = v_other and (setup_minutes <> 0 or turnaround_minutes <> 0)) then
        raise exception 'CR-100 FAIL: edit changed another venue';
    end if;

    for v_path in 1..2 loop
        v_base := '2035-01-10 10:00+00'::timestamptz + make_interval(days => v_path);
        update public.venues set setup_minutes = 30, turnaround_minutes = 45 where id = v_venue.id;
        for v_index in 1..3 loop
            insert into public.events (organiser_id, coordinator_id, status, name, starts_at, ends_at)
            values (v_organiser, v_coordinator, 'planning', 'CR-100 request check (rolled back)',
                    v_base, v_base + interval '2 hours') returning id into v_event;
            if v_path = 2 then
                -- Own space window wins over the event window.
                insert into public.event_space_requests (event_id, label, starts_at, ends_at)
                values (v_event, 'CR-100 space', v_base, v_base + interval '2 hours') returning id into v_space;
                update public.events set starts_at = v_base - interval '1 day', ends_at = v_base + interval '1 day' where id = v_event;
                select * into v_result from public.request_venue_booking_for_space(v_space, v_venue.id, v_coordinator, null, 'test');
            else
                select * into v_result from public.request_venue_booking(v_event, v_venue.id, v_coordinator, null, 'test');
            end if;
            if v_index = 2 then
                -- First booking ends 12:00, with old turnaround to 12:45.
                -- New request starts 13:00 but setup now starts 12:00: conflict.
                if v_result.outcome is distinct from 'held_by_other' or v_result.conflict is null then
                    raise exception 'CR-100 FAIL: path % ignored setup-only clash: %', v_path, v_result.outcome;
                end if;
                v_base := v_base + interval '45 minutes';
                continue;
            end if;
            if v_result.outcome is distinct from 'ok' then
                raise exception 'CR-100 FAIL: path % request % refused: %', v_path, v_index, v_result.outcome;
            end if;
            select * into v_booking from public.venue_bookings where id = v_result.booking_id;
            if v_index = 1 then
                if v_booking.setup_minutes <> 30 or v_booking.turnaround_minutes <> 45
                   or v_booking.booked_period <> tstzrange(v_base, v_base + interval '2 hours', '[)')
                   or v_booking.occupied_period <> tstzrange(v_base - interval '30 minutes', v_base + interval '2 hours 45 minutes', '[)') then
                    raise exception 'CR-100 FAIL: path % did not snapshot defaults/window', v_path;
                end if;
                v_old := v_booking;
                update public.venues set setup_minutes = 60, turnaround_minutes = 15 where id = v_venue.id;
                select * into v_booking from public.venue_bookings where id = v_old.id;
                if v_booking is distinct from v_old then
                    raise exception 'CR-100 FAIL: default change modified existing booking';
                end if;
                v_base := v_base + interval '3 hours';
            elsif v_booking.setup_minutes <> 60 or v_booking.turnaround_minutes <> 15
               or lower(v_booking.occupied_period) <> upper(v_old.occupied_period) then
                raise exception 'CR-100 FAIL: new defaults or half-open touching boundary wrong';
            end if;
        end loop;
    end loop;

    -- The largest supported integer is not a business limit. PostgreSQL
    -- preserves its exact buffer and BCE occupied endpoint; the application
    -- bounds only comparison/display endpoints, never the stored booking.
    update public.venues set setup_minutes = 2147483647 where id = v_other;
    insert into public.events (organiser_id, coordinator_id, status, name, starts_at, ends_at)
    values (v_organiser, v_coordinator, 'planning', 'CR-100 large default (rolled back)',
            '2035-03-10 10:00+00', '2035-03-10 12:00+00') returning id into v_event;
    select * into v_result from public.request_venue_booking(v_event, v_other, v_coordinator, null, 'test');
    if v_result.outcome is distinct from 'ok' then
        raise exception 'CR-100 FAIL: large valid default refused: %', v_result.outcome;
    end if;
    select * into v_booking from public.venue_bookings where id = v_result.booking_id;
    if v_booking.setup_minutes <> 2147483647
       or lower(v_booking.occupied_period) >= '0001-01-01'::timestamptz
       or lower(v_booking.booked_period) <> '2035-03-10 10:00+00'::timestamptz then
        raise exception 'CR-100 FAIL: large buffer was capped or booked window changed';
    end if;
end $$;

select 'VENUE BUFFER CHECKS PASSED' as result;
rollback;
