-- =============================================================================
-- ConnectSphere - event schema checks (SCRUM-8)
--
-- Runs inside one transaction and rolls back. Requires migrations and seed.sql.
-- =============================================================================

begin;

do $$
declare
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_event uuid := 'e0000000-0000-4000-8000-000000000901';
begin
    insert into public.events (
        id, organiser_id, name, status
    ) values (
        v_event, v_organiser, 'Schema verification draft', 'draft'
    );

    if not exists (
        select 1 from public.events where id = v_event and status = 'draft'
    ) then
        raise exception 'EVENTS FAIL: draft was not inserted';
    end if;

    begin
        insert into public.events (organiser_id, name, expected_attendance)
        values (v_organiser, 'Invalid attendance', 0);
        raise exception 'EVENTS FAIL: zero attendance was accepted';
    exception when check_violation then null;
    end;

    begin
        insert into public.events (organiser_id, name, starts_at, ends_at)
        values (
            v_organiser,
            'Invalid period',
            '2026-10-10 17:00+08',
            '2026-10-10 14:00+08'
        );
        raise exception 'EVENTS FAIL: inverted event period was accepted';
    exception when check_violation then null;
    end;

    if not exists (
        select 1
        from pg_constraint
        where conname = 'venue_bookings_event_id_fkey'
          and conrelid = 'public.venue_bookings'::regclass
    ) then
        raise exception 'EVENTS FAIL: venue booking event foreign key is missing';
    end if;
end $$;

select set_config(
    'request.jwt.claims',
    '{"sub":"a0000000-0000-0000-0000-000000000001","role":"authenticated"}',
    true
);
set local role authenticated;

do $$
declare
    v_count integer;
begin
    select count(*) into v_count
    from public.events
    where id = 'e0000000-0000-4000-8000-000000000901';
    if v_count <> 1 then
        raise exception 'RLS FAIL: organiser cannot read own event';
    end if;
end $$;

reset role;

select 'ALL EVENT SCHEMA CHECKS PASSED' as result;

rollback;
