-- CR-98: verify the live event-space backfill and event-period sync trigger.
-- Run with: supabase db query --linked --file supabase/verification/event_space_checks.sql
-- All behavioral writes run inside a transaction that is rolled back below.

begin;

do $$
declare
    v_event public.events%rowtype;
    v_space public.event_space_requests%rowtype;
    v_fixture_count integer := 0;
    v_test_event_id uuid := gen_random_uuid();
    v_test_space_id uuid;
    v_initial_start timestamptz := '2030-03-01 01:00:00+00';
    v_initial_end timestamptz := '2030-03-01 03:00:00+00';
    v_updated_start timestamptz := '2030-04-01 02:00:00+00';
    v_updated_end timestamptz := '2030-04-01 05:00:00+00';
    v_space_start timestamptz;
    v_space_end timestamptz;
begin
    if has_function_privilege('anon', 'public.populate_booking_space_request()', 'EXECUTE')
       or has_function_privilege('authenticated', 'public.populate_booking_space_request()', 'EXECUTE') then
        raise exception 'CR-98 FAIL: untrusted roles can execute the booking-space trigger function';
    end if;

    if has_function_privilege('anon', 'public.sync_event_space_periods()', 'EXECUTE')
       or has_function_privilege('authenticated', 'public.sync_event_space_periods()', 'EXECUTE') then
        raise exception 'CR-98 FAIL: untrusted roles can execute the period-sync trigger function';
    end if;

    if not exists (
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
        raise exception 'CR-98 FAIL: event-space period sync trigger is missing';
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
        if v_space.starts_at is distinct from v_event.starts_at
           or v_space.ends_at is distinct from v_event.ends_at then
            raise exception 'CR-98 FAIL: legacy event % period was not preserved', v_event.id;
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

    insert into public.event_space_requests (
        event_id, label, expected_pax, starts_at, ends_at
    ) values (
        v_test_event_id, 'Trigger verification space', 1, v_initial_start, v_initial_end
    ) returning id into v_test_space_id;

    update public.events
    set starts_at = v_updated_start,
        ends_at = v_updated_end
    where id = v_test_event_id;

    select starts_at, ends_at into v_space_start, v_space_end
    from public.event_space_requests
    where id = v_test_space_id;

    if v_space_start is distinct from v_updated_start
       or v_space_end is distinct from v_updated_end then
        raise exception 'CR-98 FAIL: event schedule update did not sync to its space';
    end if;
end;
$$;

rollback;