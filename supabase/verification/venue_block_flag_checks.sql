-- CR-95 (rearrange bookings affected by venue unavailability): a venue block
-- flags the held and approved bookings it overlaps as Affected, with the
-- block's reason, and leaves the booking and the event as they were (AC1,
-- AC2, AC6).
-- Run with the Supabase MCP execute_sql, `supabase db query --linked -f`, or
-- `psql "$DATABASE_URL" -f`. Raises on the first failure and prints
-- VENUE BLOCK FLAG CHECKS PASSED otherwise. Everything runs inside
-- `begin; ... rollback;`, so nothing here leaves a trace.
-- Uses the seeded organiser (…0001), coordinator (…0002), Seminar Room 1
-- (b0000000-…0003) and Innovation Lab (b0000000-…0001).

begin;

-- Throwaway events, all assigned to the seeded coordinator, each with one
-- booking at Seminar Room 1 in 2031 (or 2020 for the one that has ended).
insert into public.events (id, organiser_id, coordinator_id, status, name, expected_attendance, starts_at, ends_at)
values
    ('e0000000-0000-4000-8000-0000000095a1', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Block flag check held (rolled back)', 20, '2031-07-01 10:00+08', '2031-07-01 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095a2', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'confirmed', 'Block flag check approved (rolled back)', 20, '2031-07-02 10:00+08', '2031-07-02 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095a3', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Block flag check ended (rolled back)', 20, '2020-07-03 10:00+08', '2020-07-03 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095a4', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Block flag check touching (rolled back)', 20, '2031-07-04 10:00+08', '2031-07-04 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095a5', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Block flag check already flagged (rolled back)', 20, '2031-07-05 10:00+08', '2031-07-05 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095a6', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Block flag check other venue (rolled back)', 20, '2031-07-01 10:00+08', '2031-07-01 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095a7', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Block flag check released (rolled back)', 20, '2031-07-07 10:00+08', '2031-07-07 12:00+08');

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status)
values
    ('d0000000-0000-4000-8000-0000000095b1', 'e0000000-0000-4000-8000-0000000095a1', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-01 10:00+08', '2031-07-01 12:00+08', '[)'), 'held'),
    ('d0000000-0000-4000-8000-0000000095b2', 'e0000000-0000-4000-8000-0000000095a2', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-02 10:00+08', '2031-07-02 12:00+08', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000095b3', 'e0000000-0000-4000-8000-0000000095a3', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2020-07-03 10:00+08', '2020-07-03 12:00+08', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000095b4', 'e0000000-0000-4000-8000-0000000095a4', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-04 10:00+08', '2031-07-04 12:00+08', '[)'), 'held'),
    ('d0000000-0000-4000-8000-0000000095b5', 'e0000000-0000-4000-8000-0000000095a5', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-05 10:00+08', '2031-07-05 12:00+08', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000095b6', 'e0000000-0000-4000-8000-0000000095a6', 'b0000000-0000-4000-8000-000000000001',
     tstzrange('2031-07-01 10:00+08', '2031-07-01 12:00+08', '[)'), 'held'),
    ('d0000000-0000-4000-8000-0000000095b7', 'e0000000-0000-4000-8000-0000000095a7', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-07 10:00+08', '2031-07-07 12:00+08', '[)'), 'released');

-- Already flagged by another story (CR-94): must stay as it is.
update public.venue_bookings
   set flag = 'unsuitable', flag_reason = 'Capacity below attendance', flagged_at = now()
 where id = 'd0000000-0000-4000-8000-0000000095b5';

-- One block over the 1st, 2nd, 3rd (long ago) and 5th, and one that ends the
-- instant the 4th's booking starts. The block is the only thing this check
-- does; the flagging has to follow from the insert alone.
insert into public.venue_blocks (venue_id, blocked_period, reason)
values
    ('b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-01 00:00+08', '2031-07-03 23:59+08', '[)'), 'maintenance'),
    ('b0000000-0000-4000-8000-000000000003',
     tstzrange('2020-07-03 00:00+08', '2020-07-04 00:00+08', '[)'), 'maintenance'),
    ('b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-04 08:00+08', '2031-07-04 10:00+08', '[)'), 'maintenance'),
    ('b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-05 09:00+08', '2031-07-05 13:00+08', '[)'), 'safety'),
    ('b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-07-07 09:00+08', '2031-07-07 13:00+08', '[)'), 'maintenance');

do $$
declare
    v_flag text;
    v_reason text;
    v_status text;
    v_event_status text;
    v_rows integer;
begin
    -- AC1: a held booking under the block is flagged Affected with the reason.
    select flag::text, flag_reason, status::text into v_flag, v_reason, v_status
      from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000095b1';
    if v_flag is distinct from 'affected' then
        raise exception 'BLOCK FLAG FAIL: held booking under a block has flag %', v_flag;
    end if;
    if v_reason is null or v_reason not ilike '%maintenance%' then
        raise exception 'BLOCK FLAG FAIL: flag reason does not carry the block reason: %', v_reason;
    end if;
    -- AC6: flagged, not cancelled or removed.
    if v_status <> 'held' then raise exception 'BLOCK FLAG FAIL: held booking became %', v_status; end if;

    -- AC1: an approved booking too, and AC2: its event keeps its status.
    select flag::text, status::text into v_flag, v_status
      from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000095b2';
    if v_flag is distinct from 'affected' or v_status <> 'approved' then
        raise exception 'BLOCK FLAG FAIL: approved booking is %/% (want affected/approved)', v_flag, v_status;
    end if;
    select status::text into v_event_status from public.events where id = 'e0000000-0000-4000-8000-0000000095a2';
    if v_event_status <> 'confirmed' then
        raise exception 'BLOCK FLAG FAIL: flagging moved the event to % (AC2, AC7 leave its status alone)', v_event_status;
    end if;

    -- A booking that has already ended is not flagged.
    if (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000095b3') is not null then
        raise exception 'BLOCK FLAG FAIL: an ended booking was flagged';
    end if;

    -- A block that ends the instant the booking starts only touches it (CAL-R2).
    if (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000095b4') is not null then
        raise exception 'BLOCK FLAG FAIL: a block that only touches the booking flagged it';
    end if;

    -- An existing flag from another story is never overwritten.
    if (select flag::text || '|' || flag_reason from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000095b5')
       <> 'unsuitable|Capacity below attendance' then
        raise exception 'BLOCK FLAG FAIL: an existing flag was overwritten';
    end if;

    -- Another venue is unaffected.
    if (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000095b6') is not null then
        raise exception 'BLOCK FLAG FAIL: a block flagged a booking at another venue';
    end if;

    -- A released booking is not live, so it is not flagged.
    if (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000095b7') is not null then
        raise exception 'BLOCK FLAG FAIL: a released booking was flagged';
    end if;

    select count(*) into v_rows from public.venue_bookings
     where id::text like 'd0000000-0000-4000-8000-0000000095b%' and flag = 'affected';
    if v_rows <> 2 then raise exception 'BLOCK FLAG FAIL: expected 2 affected bookings, got %', v_rows; end if;
end $$;

-- Editing and deleting a block (Q1, REQUIREMENTS §9): widening it flags the
-- bookings it newly overlaps and nothing it already flagged; shortening or
-- deleting it clears nothing, because only the coordinator's follow-up does.
insert into public.events (id, organiser_id, coordinator_id, status, name, expected_attendance, starts_at, ends_at)
values
    ('e0000000-0000-4000-8000-0000000095c1', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Block edit check first day (rolled back)', 20, '2031-08-01 10:00+08', '2031-08-01 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095c2', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Block edit check second day (rolled back)', 20, '2031-08-02 10:00+08', '2031-08-02 12:00+08'),
    ('e0000000-0000-4000-8000-0000000095c3', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Block edit check third day (rolled back)', 20, '2031-08-03 10:00+08', '2031-08-03 12:00+08');

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status)
values
    ('d0000000-0000-4000-8000-0000000095d1', 'e0000000-0000-4000-8000-0000000095c1', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-08-01 10:00+08', '2031-08-01 12:00+08', '[)'), 'held'),
    ('d0000000-0000-4000-8000-0000000095d2', 'e0000000-0000-4000-8000-0000000095c2', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-08-02 10:00+08', '2031-08-02 12:00+08', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000095d3', 'e0000000-0000-4000-8000-0000000095c3', 'b0000000-0000-4000-8000-000000000003',
     tstzrange('2031-08-03 10:00+08', '2031-08-03 12:00+08', '[)'), 'held');

insert into public.venue_blocks (id, venue_id, blocked_period, reason)
values ('f0000000-0000-4000-8000-0000000095e1', 'b0000000-0000-4000-8000-000000000003',
        tstzrange('2031-08-01 00:00+08', '2031-08-01 23:00+08', '[)'), 'renovation');

do $$
begin
    if (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000095d1') is distinct from 'affected'
       or (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000095d2') is not null then
        raise exception 'BLOCK EDIT FAIL: the new block should flag the first day only';
    end if;
end $$;

-- Widen the block over the second day.
update public.venue_blocks
   set blocked_period = tstzrange('2031-08-01 00:00+08', '2031-08-02 23:00+08', '[)')
 where id = 'f0000000-0000-4000-8000-0000000095e1';

do $$
declare
    v_notices integer;
begin
    if (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000095d2') is distinct from 'affected' then
        raise exception 'BLOCK EDIT FAIL: widening the block did not flag the newly overlapped booking';
    end if;
    if (select flag from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000095d3') is not null then
        raise exception 'BLOCK EDIT FAIL: widening the block flagged a booking it does not overlap';
    end if;
    -- The first day was flagged already: one flag, one notice, not a second.
    select count(*) into v_notices from public.notifications
     where type = 'venue_booking_affected' and event_id = 'e0000000-0000-4000-8000-0000000095c1';
    if v_notices <> 1 then
        raise exception 'BLOCK EDIT FAIL: widening re-notified an already flagged booking (% notices)', v_notices;
    end if;
end $$;

-- Shorten the block back to the first day, then delete it: no flag is cleared.
update public.venue_blocks
   set blocked_period = tstzrange('2031-08-01 00:00+08', '2031-08-01 23:00+08', '[)')
 where id = 'f0000000-0000-4000-8000-0000000095e1';
delete from public.venue_blocks where id = 'f0000000-0000-4000-8000-0000000095e1';

do $$
begin
    if (select count(*) from public.venue_bookings
         where id in ('d0000000-0000-4000-8000-0000000095d1', 'd0000000-0000-4000-8000-0000000095d2')
           and flag = 'affected' and status in ('held', 'approved')) <> 2 then
        raise exception 'BLOCK EDIT FAIL: shortening or deleting the block cleared or changed a flag';
    end if;
end $$;

select 'VENUE BLOCK FLAG CHECKS PASSED' as result;

rollback;
