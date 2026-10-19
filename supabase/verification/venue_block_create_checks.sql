-- SCRUM-51 (Venue Staff block a venue): the database half.
-- create_venue_block's refusals, the block row, its history row, and what the
-- block trigger does to the bookings it overlaps: which are flagged and
-- recorded against it (AC5, AC7, AC10-AC12), who is told what (AC13), and
-- that API roles can neither delete a block nor read the links (AC9).
-- Run with `supabase db query --linked -f`, or `psql "$DATABASE_URL" -f`.
-- Raises on the first failure and prints VENUE BLOCK CREATE CHECKS PASSED
-- otherwise. Everything runs inside `begin; ... rollback;`, so nothing here
-- leaves a trace. Uses the seeded organiser (…0001), coordinator (…0002),
-- venue staff (…0003), Seminar Room 1 (b…0003) and Innovation Lab (b…0001).

begin;

-- Throwaway events, all assigned to the seeded coordinator. Bookings at Seminar
-- Room 1 unless named otherwise; periods are relative to now so the "ended"
-- and "overdue hold" cases are real.
insert into public.events (id, organiser_id, coordinator_id, status, name, expected_attendance, starts_at, ends_at)
select ('e0000000-0000-4000-8000-0000000051' || n)::uuid, 'a0000000-0000-4000-8000-000000000001',
       'a0000000-0000-4000-8000-000000000002', 'planning', 'Block create check ' || n || ' (rolled back)', 20,
       now() + interval '30 days', now() + interval '30 days 2 hours'
  from unnest(array['a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7', 'a8', 'a9', 'b1', 'b2']) n;

-- a2's event books two venues (CR-97), so it has a space for each; a booking
-- with no space would be linked to the event's first one.
insert into public.event_space_requests (id, event_id, label)
values ('c0000000-0000-4000-8000-0000000051c1', 'e0000000-0000-4000-8000-0000000051a2', 'Main hall'),
       ('c0000000-0000-4000-8000-0000000051c2', 'e0000000-0000-4000-8000-0000000051a2', 'Breakout');

-- Inside the first block, [+30d 00:00, +30d 12:00):
--   a1 held, a2 approved                        -> flagged and linked
--   a3 rejected, a4 cancelled, a5 released       -> neither
--   a6 held but overdue (expires_at passed)      -> expired first, neither
--   a7 approved at the second venue, same event as a2 -> untouched (AC12)
-- a8: booked time starts 1h after the block ends, 2h setup -> found by its occupied window (AC7)
-- a9: ends exactly when the block starts, no turnaround -> only touches it, untouched
-- b1: approved, ended an hour ago, under the emergency block -> not flagged (AC11)
-- b2: held under both the first and the second block -> flagged once, linked twice (AC10)
insert into public.venue_bookings (id, event_id, venue_id, booked_period, status, setup_minutes, expires_at, event_space_request_id)
values
    ('d0000000-0000-4000-8000-0000000051a1', 'e0000000-0000-4000-8000-0000000051a1', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '30 days 1 hour', date_trunc('hour', now()) + interval '30 days 2 hours', '[)'), 'held', 0, null, null),
    ('d0000000-0000-4000-8000-0000000051a2', 'e0000000-0000-4000-8000-0000000051a2', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '30 days 3 hours', date_trunc('hour', now()) + interval '30 days 4 hours', '[)'), 'approved', 0, null, 'c0000000-0000-4000-8000-0000000051c1'),
    ('d0000000-0000-4000-8000-0000000051a3', 'e0000000-0000-4000-8000-0000000051a3', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '30 days 5 hours', date_trunc('hour', now()) + interval '30 days 6 hours', '[)'), 'rejected', 0, null, null),
    ('d0000000-0000-4000-8000-0000000051a4', 'e0000000-0000-4000-8000-0000000051a4', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '30 days 5 hours', date_trunc('hour', now()) + interval '30 days 6 hours', '[)'), 'cancelled', 0, null, null),
    ('d0000000-0000-4000-8000-0000000051a5', 'e0000000-0000-4000-8000-0000000051a5', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '30 days 5 hours', date_trunc('hour', now()) + interval '30 days 6 hours', '[)'), 'released', 0, null, null),
    ('d0000000-0000-4000-8000-0000000051a6', 'e0000000-0000-4000-8000-0000000051a6', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '30 days 7 hours', date_trunc('hour', now()) + interval '30 days 8 hours', '[)'), 'held', 0,
     now() - interval '1 minute', null),
    ('d0000000-0000-4000-8000-0000000051a7', 'e0000000-0000-4000-8000-0000000051a2', 'b0000000-0000-4000-8000-000000000001',
     tstzrange(date_trunc('hour', now()) + interval '30 days 3 hours', date_trunc('hour', now()) + interval '30 days 4 hours', '[)'), 'approved', 0, null, 'c0000000-0000-4000-8000-0000000051c2'),
    ('d0000000-0000-4000-8000-0000000051a8', 'e0000000-0000-4000-8000-0000000051a8', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '30 days 13 hours', date_trunc('hour', now()) + interval '30 days 14 hours', '[)'), 'approved', 120, null, null),
    ('d0000000-0000-4000-8000-0000000051a9', 'e0000000-0000-4000-8000-0000000051a9', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '29 days 18 hours', date_trunc('hour', now()) + interval '30 days', '[)'), 'held', 0, null, null),
    ('d0000000-0000-4000-8000-0000000051b1', 'e0000000-0000-4000-8000-0000000051b1', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(now() - interval '3 hours', now() - interval '1 hour', '[)'), 'approved', 0, null, null),
    ('d0000000-0000-4000-8000-0000000051b2', 'e0000000-0000-4000-8000-0000000051b2', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '30 days 9 hours', date_trunc('hour', now()) + interval '30 days 10 hours', '[)'), 'held', 0, null, null);

create temporary table scrum51_results (label text primary key, outcome text, block_id uuid) on commit drop;

-- AC1: the refusals, each before anything is written.
insert into scrum51_results
select 'reversed', r.outcome, r.block_id from public.create_venue_block(
    'b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000003',
    now() + interval '2 days', now() + interval '1 day', 'maintenance', null, '{}') r;
insert into scrum51_results
select 'ended', r.outcome, r.block_id from public.create_venue_block(
    'b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000003',
    now() - interval '2 days', now() - interval '1 day', 'maintenance', null, '{}') r;
insert into scrum51_results
select 'other_blank', r.outcome, r.block_id from public.create_venue_block(
    'b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000003',
    now() + interval '1 day', now() + interval '2 days', 'other', '   ', '{}') r;
insert into scrum51_results
select 'too_long', r.outcome, r.block_id from public.create_venue_block(
    'b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000003',
    now() + interval '1 day', now() + interval '2 days', 'maintenance', repeat('x', 1001), '{}') r;
insert into scrum51_results
select 'no_venue', r.outcome, r.block_id from public.create_venue_block(
    'b0000000-0000-4000-8000-0000000000ff', 'a0000000-0000-4000-8000-000000000003',
    now() + interval '1 day', now() + interval '2 days', 'maintenance', null, '{}') r;

-- The first block, then a second one that overlaps only b2, then an emergency
-- block that started yesterday and covers b1 (which has ended).
insert into scrum51_results
select 'first', r.outcome, r.block_id from public.create_venue_block(
    'b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000003',
    date_trunc('hour', now()) + interval '30 days', date_trunc('hour', now()) + interval '30 days 12 hours',
    'equipment_failure', '  Projector rig down  ', '{"block": {"reason": "equipment_failure"}}') r;
insert into scrum51_results
select 'second', r.outcome, r.block_id from public.create_venue_block(
    'b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000003',
    date_trunc('hour', now()) + interval '30 days 9 hours', date_trunc('hour', now()) + interval '30 days 11 hours',
    'safety', null, '{"block": {"reason": "safety"}}') r;
insert into scrum51_results
select 'emergency', r.outcome, r.block_id from public.create_venue_block(
    'b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000003',
    now() - interval '1 day', now() + interval '1 hour', 'safety', null, '{}') r;

do $$
declare
    v_first uuid := (select block_id from scrum51_results where label = 'first');
    v_second uuid := (select block_id from scrum51_results where label = 'second');
    v_row record;
    v_got text;
begin
    -- AC1 refusals.
    for v_row in
        select * from (values ('reversed', 'invalid_period'), ('ended', 'ended'), ('other_blank', 'invalid_detail'),
                              ('too_long', 'detail_too_long'), ('no_venue', 'venue_not_found'),
                              ('first', 'ok'), ('second', 'ok'), ('emergency', 'ok')) t(label, want)
    loop
        select outcome into v_got from scrum51_results where label = v_row.label;
        if v_got is distinct from v_row.want then
            raise exception 'BLOCK CREATE FAIL: % returned % (want %)', v_row.label, v_got, v_row.want;
        end if;
    end loop;
    -- created_by is new in this release, so only this script's blocks carry it.
    if (select count(*) from public.venue_blocks where created_by = 'a0000000-0000-4000-8000-000000000003') <> 3 then
        raise exception 'BLOCK CREATE FAIL: a refused call wrote a block, or a saved one is missing created_by';
    end if;

    -- AC1, AC9: the block keeps its trimmed detail, reason, creator and period.
    select reason::text as reason, notes, created_by, blocked_period into v_row from public.venue_blocks where id = v_first;
    if v_row.reason <> 'equipment_failure' or v_row.notes <> 'Projector rig down'
       or v_row.created_by <> 'a0000000-0000-4000-8000-000000000003' then
        raise exception 'BLOCK CREATE FAIL: stored block is %', v_row;
    end if;

    -- AC9: one history row per saved block, with the actor and its payload.
    if (select count(*) from public.venue_edit_history
         where venue_id = 'b0000000-0000-4000-8000-000000000003' and created_at >= now()) <> 3 then
        raise exception 'BLOCK CREATE FAIL: expected 3 history rows (refusals write none)';
    end if;
    if not exists (select 1 from public.venue_edit_history
                    where venue_id = 'b0000000-0000-4000-8000-000000000003' and created_at >= now()
                      and actor_id = 'a0000000-0000-4000-8000-000000000003'
                      and before = '{}'::jsonb and after -> 'block' ->> 'reason' = 'equipment_failure') then
        raise exception 'BLOCK CREATE FAIL: the first block''s history row is missing its actor or payload';
    end if;

    -- AC5, AC11: held and approved overlapping bookings are Affected with the
    -- reason label, and keep their status; the others are untouched.
    for v_row in
        select id, flag::text as flag, flag_reason, status::text as status from public.venue_bookings
         where id::text like 'd0000000-0000-4000-8000-000000005%' order by id
    loop
        if right(v_row.id::text, 2) in ('a1', 'a2', 'a8', 'b2') then
            if v_row.flag is distinct from 'affected' or v_row.flag_reason not like 'Venue unavailable: %' then
                raise exception 'BLOCK CREATE FAIL: booking % is %/% (want affected)', v_row.id, v_row.flag, v_row.flag_reason;
            end if;
        elsif v_row.flag is not null then
            raise exception 'BLOCK CREATE FAIL: booking % (status %) was flagged %', v_row.id, v_row.status, v_row.flag;
        end if;
    end loop;
    if (select flag_reason from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000051a1')
       <> 'Venue unavailable: Equipment failure' then
        raise exception 'BLOCK CREATE FAIL: the flag reason is not the readable label';
    end if;
    if (select status::text from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000051a1') <> 'held'
       or (select status::text from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000051a2') <> 'approved' then
        raise exception 'BLOCK CREATE FAIL: a flagged booking changed status';
    end if;
    if (select status::text from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000051a6') <> 'expired' then
        raise exception 'BLOCK CREATE FAIL: the overdue hold was not expired before the block was saved';
    end if;
    if exists (select 1 from public.events where id::text like 'e0000000-0000-4000-8000-0000000051%' and status <> 'planning') then
        raise exception 'BLOCK CREATE FAIL: a block changed an event''s status (CR-95 AC7)';
    end if;

    -- AC10: the links. b2 is under both blocks; nothing else under the second.
    if (select array_agg(right(booking_id::text, 2) order by booking_id) from public.venue_block_bookings where block_id = v_first)
       <> array['a1', 'a2', 'a8', 'b2'] then
        raise exception 'BLOCK CREATE FAIL: first block linked %',
            (select array_agg(right(booking_id::text, 2) order by booking_id) from public.venue_block_bookings where block_id = v_first);
    end if;
    if (select array_agg(right(booking_id::text, 2)) from public.venue_block_bookings where block_id = v_second)
       <> array['b2'] then
        raise exception 'BLOCK CREATE FAIL: second block did not link b2 alone';
    end if;
end $$;

-- AC5, AC10, AC13: who is told what.
do $$
declare
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_message text;
begin
    -- b2 is under two blocks: one notice each, not two.
    if (select count(*) from public.notifications where event_id = 'e0000000-0000-4000-8000-0000000051b2'
         and recipient_id = v_coordinator and type = 'venue_booking_affected') <> 1 then
        raise exception 'BLOCK NOTICE FAIL: the coordinator was not told exactly once for a booking under two blocks';
    end if;
    if (select count(*) from public.notifications where event_id = 'e0000000-0000-4000-8000-0000000051b2'
         and recipient_id = v_organiser and type = 'venue_unavailable_organiser') <> 1 then
        raise exception 'BLOCK NOTICE FAIL: the organiser was not told exactly once for a booking under two blocks';
    end if;

    -- The coordinator's notice names the reason; the organiser's does not, but
    -- says the event isn't cancelled and what happens next.
    select message into v_message from public.notifications
     where event_id = 'e0000000-0000-4000-8000-0000000051a1' and type = 'venue_booking_affected';
    if v_message not like '%Equipment failure%' then
        raise exception 'BLOCK NOTICE FAIL: the coordinator notice does not name the reason: %', v_message;
    end if;
    select message into v_message from public.notifications
     where event_id = 'e0000000-0000-4000-8000-0000000051a1' and type = 'venue_unavailable_organiser';
    if v_message is null or v_message ilike '%equipment%' or v_message ilike '%projector%'
       or v_message not ilike '%not cancelled%' or v_message not ilike '%coordinator%' then
        raise exception 'BLOCK NOTICE FAIL: the organiser notice is %', v_message;
    end if;

    -- Nobody but the organiser and coordinator hears about it (attendees, AC13).
    if exists (select 1 from public.notifications
                where event_id::text like 'e0000000-0000-4000-8000-0000000051%'
                  and recipient_id not in (v_organiser, v_coordinator)) then
        raise exception 'BLOCK NOTICE FAIL: someone other than the organiser and coordinator was notified';
    end if;
    -- Events with nothing flagged hear nothing about the block (a6's
    -- coordinator is told its hold expired, which is CR-99's notice).
    if exists (select 1 from public.notifications
                where type in ('venue_booking_affected', 'venue_unavailable_organiser')
                  and event_id in ('e0000000-0000-4000-8000-0000000051a3', 'e0000000-0000-4000-8000-0000000051a4',
                                   'e0000000-0000-4000-8000-0000000051a5', 'e0000000-0000-4000-8000-0000000051a6',
                                   'e0000000-0000-4000-8000-0000000051a9', 'e0000000-0000-4000-8000-0000000051b1')) then
        raise exception 'BLOCK NOTICE FAIL: an event whose booking was not flagged was notified';
    end if;
end $$;

-- AC12: the event's booking at the other venue is unchanged.
do $$
begin
    if (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000051a7') is not null then
        raise exception 'BLOCK CREATE FAIL: the booking at the other venue was flagged';
    end if;
    if exists (select 1 from public.venue_block_bookings where booking_id = 'd0000000-0000-4000-8000-0000000051a7') then
        raise exception 'BLOCK CREATE FAIL: the booking at the other venue was linked';
    end if;
end $$;

-- AC9, RLS: the API roles can neither delete a block, nor read or write the links,
-- nor call create_venue_block themselves.
set local role authenticated;
do $$
begin
    begin
        delete from public.venue_blocks where reason = 'equipment_failure';
        raise exception 'BLOCK RLS FAIL: authenticated could delete a block';
    exception when insufficient_privilege then null;
    end;
    begin
        perform 1 from public.venue_block_bookings;
        raise exception 'BLOCK RLS FAIL: authenticated could read venue_block_bookings';
    exception when insufficient_privilege then null;
    end;
    begin
        perform public.create_venue_block('b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000003',
            now() + interval '1 day', now() + interval '2 days', 'maintenance', null, '{}');
        raise exception 'BLOCK RLS FAIL: authenticated could call create_venue_block';
    exception when insufficient_privilege then null;
    end;
end $$;
reset role;

select 'VENUE BLOCK CREATE CHECKS PASSED' as result;

rollback;
