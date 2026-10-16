-- CR-98 / QA3-23 / D32: verify legacy backfill, inherited and explicit space
-- windows, booking linkage, removed period synchronization, and trigger grants.
-- Run with: supabase db query --linked --file supabase/verification/event_space_checks.sql
-- All behavioral writes run inside a transaction that is rolled back below.

begin;

do $$
declare
    v_event public.events%rowtype;
    v_space public.event_space_requests%rowtype;
    v_fixture_count integer := 0;
    v_test_event_id uuid := gen_random_uuid();
    v_inherited_space_id uuid;
    v_override_space_id uuid;
    v_initial_start timestamptz := '2030-03-01 00:00:00+00';
    v_initial_end timestamptz := '2030-03-01 08:00:00+00';
    v_override_start timestamptz := '2030-03-01 02:00:00+00';
    v_override_end timestamptz := '2030-03-01 04:00:00+00';
    v_inherited_start timestamptz;
    v_inherited_end timestamptz;
    v_stored_override_start timestamptz;
    v_stored_override_end timestamptz;
    v_effective_start timestamptz;
    v_effective_end timestamptz;
begin
    if has_function_privilege('anon', 'public.populate_booking_space_request()', 'EXECUTE')
       or has_function_privilege('authenticated', 'public.populate_booking_space_request()', 'EXECUTE') then
        raise exception 'CR-98 FAIL: untrusted roles can execute the booking-space trigger function';
    end if;

    if has_function_privilege('anon', 'public.sync_event_space_periods()', 'EXECUTE')
       or has_function_privilege('authenticated', 'public.sync_event_space_periods()', 'EXECUTE') then
        raise exception 'CR-98 FAIL: untrusted roles can execute the period-sync trigger function';
    end if;

    if exists (
        select 1
        from pg_trigger t
        join pg_class c on c.oid = t.tgrelid
        join pg_namespace n on n.oid = c.relnamespace
        join pg_proc p on p.oid = t.tgfoid
        where n.nspname = 'public'
          and c.relname = 'events'
          and t.tgname = 'events_sync_space_periods'
          and p.proname = 'sync_event_space_periods'
          and not t.tgisinternal
    ) then
        raise exception 'CR-98 FAIL: event-space period sync trigger still overwrites individual schedules';
    end if;

    for v_event in
        select *
        from public.events
        where id in (
            'e0000000-0000-4000-8000-000000000201',
            'e0000000-0000-4000-8000-000000000202'
        )
    loop
        v_fixture_count := v_fixture_count + 1;
        select * into v_space
        from public.event_space_requests
        where event_id = v_event.id
        order by created_at, id
        limit 1;

        if not found then
            raise exception 'CR-98 FAIL: legacy event % has no backfilled space', v_event.id;
        end if;
        if v_space.label <> 'Main space'
           or v_space.expected_pax is distinct from v_event.expected_attendance
           or v_space.layout_preference is distinct from v_event.layout_preference
           or v_space.facilities_required is distinct from v_event.facilities_required then
            raise exception 'CR-98 FAIL: legacy event % requirements were not preserved', v_event.id;
        end if;
        if (v_space.starts_at is null) is distinct from (v_space.ends_at is null) then
            raise exception 'CR-98 FAIL: legacy event % has only one space schedule bound', v_event.id;
        end if;
        if v_space.starts_at is null or v_space.ends_at is null then
            if v_space.starts_at is not null or v_space.ends_at is not null then
                raise exception 'CR-98 FAIL: legacy event % does not consistently inherit its event period', v_event.id;
            end if;
        elsif v_space.starts_at < v_event.starts_at or v_space.ends_at > v_event.ends_at then
            raise exception 'CR-98 FAIL: legacy event % space period falls outside its event period', v_event.id;
        end if;
    end loop;

    if v_fixture_count <> 2 then
        raise exception 'CR-98 FAIL: expected both seeded legacy events, found %', v_fixture_count;
    end if;

    if not exists (
        select 1
        from public.venue_bookings vb
        join public.event_space_requests es
          on es.id = vb.event_space_request_id
         and es.event_id = vb.event_id
        where vb.id = 'd0000000-0000-4000-8000-000000000201'
          and vb.event_id = 'e0000000-0000-4000-8000-000000000202'
          and es.label = 'Main space'
    ) then
        raise exception 'CR-98 FAIL: legacy booking was not linked to its backfilled Main space';
    end if;

    insert into public.events (id, organiser_id, name, starts_at, ends_at)
    values (
        v_test_event_id,
        'a0000000-0000-4000-8000-000000000001',
        'CR-98 period trigger verification',
        v_initial_start,
        v_initial_end
    );

    insert into public.event_space_requests (event_id, label, expected_pax)
    values (v_test_event_id, 'Inherited schedule verification', 1)
    returning id into v_inherited_space_id;

    insert into public.event_space_requests (
        event_id, label, expected_pax, starts_at, ends_at
    ) values (
        v_test_event_id, 'Individual schedule verification', 1, v_override_start, v_override_end
    ) returning id into v_override_space_id;

    update public.events
    set starts_at = '2030-03-01 01:00:00+00',
        ends_at = '2030-03-01 07:00:00+00'
    where id = v_test_event_id;

    select starts_at, ends_at into v_inherited_start, v_inherited_end
    from public.event_space_requests
    where id = v_inherited_space_id;

    select starts_at, ends_at into v_stored_override_start, v_stored_override_end
    from public.event_space_requests
    where id = v_override_space_id;

    if v_inherited_start is not null or v_inherited_end is not null then
        raise exception 'CR-98 FAIL: an inherited space should store no override period';
    end if;
    if v_stored_override_start is distinct from v_override_start
       or v_stored_override_end is distinct from v_override_end then
        raise exception 'CR-98 FAIL: event schedule update overwrote an individual space period';
    end if;
    select coalesce(es.starts_at, e.starts_at), coalesce(es.ends_at, e.ends_at)
      into v_effective_start, v_effective_end
      from public.event_space_requests es
      join public.events e on e.id = es.event_id
     where es.id = v_inherited_space_id;
     if v_effective_start is distinct from '2030-03-01 01:00:00+00'::timestamptz
         or v_effective_end is distinct from '2030-03-01 07:00:00+00'::timestamptz then
        raise exception 'CR-98 FAIL: inherited period did not resolve to the updated event schedule';
    end if;
end;
$$;

do $$
declare
    v_owner uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_other_actor uuid := 'a0000000-0000-4000-8000-000000000003';
    v_venue uuid := 'b0000000-0000-4000-8000-000000000006';
    v_event_id uuid;
    v_rival_event_id uuid;
    v_space_id uuid;
    v_rival_space_id uuid;
    v_old_booking_id uuid;
    v_start timestamptz;
    v_result record;
    v_scenario integer;
begin
    for v_scenario in 1..2 loop
        v_event_id := gen_random_uuid();
        v_rival_event_id := gen_random_uuid();
        v_start := '2090-03-01 02:00+00'::timestamptz + v_scenario * interval '1 day';
        insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at)
        values
            (v_event_id, v_owner, v_coordinator, 'planning', 'Space hold expiry check (rolled back)', v_start, v_start + interval '2 hours'),
            (v_rival_event_id, v_owner, v_coordinator, 'planning', 'Space hold rival check (rolled back)', v_start, v_start + interval '2 hours');
        insert into public.event_space_requests (event_id, label, expected_pax, layout_preference)
        values (v_event_id, 'Requested space', 10, 'classroom') returning id into v_space_id;
        insert into public.event_space_requests (event_id, label, expected_pax, layout_preference)
        values (v_rival_event_id, 'Rival space', 10, 'classroom') returning id into v_rival_space_id;
        insert into public.venue_bookings (event_id, event_space_request_id, venue_id, occupied_period, status, expires_at)
        values (
            case when v_scenario = 1 then v_event_id else v_rival_event_id end,
            case when v_scenario = 1 then v_space_id else v_rival_space_id end,
            v_venue, tstzrange(v_start, v_start + interval '2 hours', '[)'), 'held', now() - interval '1 second'
        ) returning id into v_old_booking_id;

        select * into v_result from public.request_venue_booking_for_space(
            v_space_id, v_venue, v_other_actor, null, 'Space expiry check');
        if v_result.outcome is distinct from 'not_assigned'
           or (select status from public.venue_bookings where id = v_old_booking_id) is distinct from 'held' then
            raise exception 'SPACE EXPIRY FAIL: denied request changed booking state';
        end if;

        select * into v_result from public.request_venue_booking_for_space(
            v_space_id, v_venue, v_coordinator, null, 'Space expiry check');
        if v_result.outcome is distinct from 'ok' then
            raise exception 'SPACE EXPIRY FAIL: scenario % returned %, expected ok before cron', v_scenario, v_result.outcome;
        end if;
        if (select status from public.venue_bookings where id = v_old_booking_id) is distinct from 'expired' then
            raise exception 'SPACE EXPIRY FAIL: overdue hold was not expired';
        end if;
        if (select count(*) from public.venue_booking_history
            where booking_id = v_old_booking_id and action = 'expired') <> 1 then
            raise exception 'SPACE EXPIRY FAIL: expiry history must be written exactly once';
        end if;
        if not exists (
            select 1 from public.venue_bookings
            where id = v_result.booking_id and event_space_request_id = v_space_id
              and status = 'held' and expires_at = now() + interval '7 days'
              and occupied_period = tstzrange(v_start, v_start + interval '2 hours', '[)')
        ) then
            raise exception 'SPACE EXPIRY FAIL: new hold lost its space, period or trigger default expiry';
        end if;

        select * into v_result from public.request_venue_booking_for_space(
            v_space_id, v_venue, v_coordinator, null, 'Space expiry check');
        if v_result.outcome is distinct from 'already_booked' then
            raise exception 'SPACE EXPIRY FAIL: an unexpired same-space hold was not refused';
        end if;
        select * into v_result from public.request_venue_booking_for_space(
            v_rival_space_id, v_venue, v_coordinator, null, 'Space expiry check');
        if v_result.outcome is distinct from 'held_by_other' then
            raise exception 'SPACE EXPIRY FAIL: an unexpired overlapping hold was not refused';
        end if;
    end loop;
    if has_function_privilege('anon', 'public.request_venue_booking_for_space(uuid,uuid,uuid,text,text)', 'EXECUTE')
       or has_function_privilege('authenticated', 'public.request_venue_booking_for_space(uuid,uuid,uuid,text,text)', 'EXECUTE')
       or not has_function_privilege('service_role', 'public.request_venue_booking_for_space(uuid,uuid,uuid,text,text)', 'EXECUTE') then
        raise exception 'SPACE EXPIRY FAIL: booking RPC grants changed';
    end if;
end;
$$;

-- CR-97 AC10 / BR-R16: a space is refused a venue too small for its expected
-- pax. Capacity is the venue's figure for the space's layout when it has one,
-- else the venue's overall capacity (the same rule as venue search).
do $$
declare
    v_owner uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_venue uuid := 'b0000000-0000-4000-8000-000000000006'; -- 80 seats; classroom 60, reception no layout figure
    v_case record;
    v_event_id uuid;
    v_space_id uuid;
    v_start timestamptz;
    v_result record;
    v_day integer := 0;
begin
    for v_case in
        select * from (values
            (61, 'classroom'::public.venue_layout, 'over_capacity'),  -- layout figure used, though under 80
            (60, 'classroom'::public.venue_layout, 'ok'),             -- exactly the layout capacity
            (81, 'reception'::public.venue_layout, 'over_capacity'),  -- no layout figure: venue capacity
            (80, null::public.venue_layout, 'ok'),                    -- no layout preference: venue capacity
            (null, 'classroom'::public.venue_layout, 'ok')            -- no expected pax: not checked
        ) as t(pax, layout, expected)
    loop
        v_day := v_day + 1;
        v_event_id := gen_random_uuid();
        v_start := '2091-03-01 02:00+00'::timestamptz + v_day * interval '1 day';
        insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at)
        values (v_event_id, v_owner, v_coordinator, 'planning', 'CR-97 capacity check (rolled back)', v_start, v_start + interval '2 hours');
        insert into public.event_space_requests (event_id, label, expected_pax, layout_preference)
        values (v_event_id, 'Capacity space', v_case.pax, v_case.layout) returning id into v_space_id;

        select * into v_result from public.request_venue_booking_for_space(
            v_space_id, v_venue, v_coordinator, null, 'CR-97 capacity check');
        if v_result.outcome is distinct from v_case.expected then
            raise exception 'CR-97 CAPACITY FAIL: % pax, layout %: got %, expected %',
                v_case.pax, v_case.layout, v_result.outcome, v_case.expected;
        end if;
        if v_case.expected = 'over_capacity' and exists (
            select 1 from public.venue_bookings where event_space_request_id = v_space_id
        ) then
            raise exception 'CR-97 CAPACITY FAIL: a refused request still created a booking';
        end if;
    end loop;
end;
$$;

rollback;
