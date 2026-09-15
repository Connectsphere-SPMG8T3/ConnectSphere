-- =============================================================================
-- ConnectSphere — venue schema checks (SCRUM-39; DB-1, BR-R1, CAL-R1, VC-R1 RLS)
--
-- Runs every check inside one transaction and ROLLS BACK, so it changes nothing.
-- Any failed check raises an exception naming the rule. Run after migrations
-- (psql "$DATABASE_URL" -f supabase/verification/venue_schema_checks.sql, or
-- `supabase db query --linked -f ...`). Requires supabase/seed.sql for the
-- RLS checks (uses the seeded coordinator and organiser accounts).
-- =============================================================================

begin;

insert into public.events (id, organiser_id, status, name)
values
    ('e0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000001', 'planning', 'Venue check event 1'),
    ('e0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000001', 'planning', 'Venue check event 2'),
    ('e0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000001', 'planning', 'Venue check event 3'),
    ('e0000000-0000-4000-8000-000000000004', 'a0000000-0000-4000-8000-000000000001', 'planning', 'Venue check event 4');

insert into public.venues (id, name, location, capacity, opens_at, closes_at)
values ('d0000000-0000-4000-8000-0000000000a1', 'Verify Hall', 'Verification Campus', 100, '08:00', '22:00');

-- DB-1 / §6.14: back-to-back bookings are compatible (half-open ranges, zero turnaround).
insert into public.venue_bookings (event_id, venue_id, occupied_period, status)
values ('e0000000-0000-4000-8000-000000000001', 'd0000000-0000-4000-8000-0000000000a1',
        tstzrange('2026-10-10 09:00+08', '2026-10-10 12:00+08', '[)'), 'held');
insert into public.venue_bookings (event_id, venue_id, occupied_period, status)
values ('e0000000-0000-4000-8000-000000000002', 'd0000000-0000-4000-8000-0000000000a1',
        tstzrange('2026-10-10 12:00+08', '2026-10-10 15:00+08', '[)'), 'approved');

-- DB-1: an overlapping hold is refused under every occupying status.
do $$
begin
    begin
        insert into public.venue_bookings (event_id, venue_id, occupied_period, status)
        values ('e0000000-0000-4000-8000-000000000003', 'd0000000-0000-4000-8000-0000000000a1',
                tstzrange('2026-10-10 11:59+08', '2026-10-10 13:00+08', '[)'), 'held');
        raise exception 'DB-1 FAIL: overlapping hold 11:59–13:00 was accepted next to 09:00–12:00 / 12:00–15:00';
    exception
        when exclusion_violation then null;
    end;
end $$;

-- §6.14: rejected / cancelled / released bookings no longer occupy the venue.
insert into public.venue_bookings (event_id, venue_id, occupied_period, status)
values ('e0000000-0000-4000-8000-000000000004', 'd0000000-0000-4000-8000-0000000000a1',
        tstzrange('2026-10-10 10:00+08', '2026-10-10 11:00+08', '[)'), 'rejected');

-- BR-R1: an event has at most one occupying booking.
do $$
begin
    begin
        insert into public.venue_bookings (event_id, venue_id, occupied_period, status)
        values ('e0000000-0000-4000-8000-000000000001', 'd0000000-0000-4000-8000-0000000000a1',
                tstzrange('2026-10-11 09:00+08', '2026-10-11 12:00+08', '[)'), 'held');
        raise exception 'BR-R1 FAIL: a second occupying booking for the same event was accepted';
    exception
        when unique_violation then null;
    end;
end $$;

-- CAL-R1: a block may overlap an existing booking (emergencies happen).
insert into public.venue_blocks (venue_id, blocked_period, reason)
values ('d0000000-0000-4000-8000-0000000000a1',
        tstzrange('2026-10-10 08:00+08', '2026-10-11 08:00+08', '[)'), 'maintenance');

-- Periods must be bounded and half-open.
do $$
begin
    begin
        insert into public.venue_blocks (venue_id, blocked_period, reason)
        values ('d0000000-0000-4000-8000-0000000000a1',
                tstzrange('2026-10-12 08:00+08', '2026-10-12 10:00+08', '[]'), 'other');
        raise exception 'PERIOD FAIL: a closed-end block period was accepted';
    exception
        when check_violation then null;
    end;
end $$;

-- RLS: a coordinator can read the catalogue directly; an organiser sees nothing.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
declare
    v_count int;
begin
    select count(*) into v_count from public.venues where id = 'd0000000-0000-4000-8000-0000000000a1';
    if v_count <> 1 then
        raise exception 'RLS FAIL: coordinator cannot read venues directly';
    end if;
    select count(*) into v_count from public.venue_bookings where venue_id = 'd0000000-0000-4000-8000-0000000000a1';
    if v_count <> 3 then
        raise exception 'RLS FAIL: coordinator sees % bookings, expected 3', v_count;
    end if;
    begin
        insert into public.venue_blocks (venue_id, blocked_period, reason)
        values ('d0000000-0000-4000-8000-0000000000a1',
                tstzrange('2026-10-13 08:00+08', '2026-10-13 10:00+08', '[)'), 'other');
        raise exception 'RLS FAIL: coordinator inserted a block directly';
    exception
        when insufficient_privilege then null;
    end;
end $$;
reset role;

select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
declare
    v_count int;
begin
    select count(*) into v_count from public.venues;
    if v_count <> 0 then
        raise exception 'RLS FAIL: organiser sees % venues, expected 0', v_count;
    end if;
end $$;
reset role;

select 'ALL VENUE SCHEMA CHECKS PASSED' as result;

rollback;
