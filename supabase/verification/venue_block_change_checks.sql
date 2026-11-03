-- SCRUM-54 (Venue Staff end, shorten or remove a block early): the database half.
-- change_venue_block's refusals and changes, the block row and its history row
-- (AC2, AC4), what search and requests see afterwards (AC3), which bookings are
-- listed as restorable (AC5), that nothing clears a flag by itself (AC5), the
-- coordinator's notice for a pending replacement (AC7), restore after a block
-- ends: an expired hold refused, the organiser told (D83), the event's status
-- and other bookings unchanged (AC6, AC10), and the grants (AC9).
-- AC8 (restore racing a replacement's approval) needs two sessions; the lock
-- order it relies on is CR-95's, checked in venue_release_checks.sql.
-- Run with `supabase db query --linked -f`, or `psql "$DATABASE_URL" -f`.
-- Raises on the first failure and prints VENUE BLOCK CHANGE CHECKS PASSED
-- otherwise. Everything runs inside `begin; ... rollback;`, so nothing here
-- leaves a trace. now() is fixed for the transaction, so "ends now" is exact.
-- Uses the seeded organiser (…0001), coordinator (…0002), venue staff (…0003),
-- Seminar Room 1 (b…0003) and Innovation Lab (b…0001).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, expected_attendance, starts_at, ends_at)
select ('e0000000-0000-4000-8000-0000000054' || n)::uuid, 'a0000000-0000-4000-8000-000000000001',
       'a0000000-0000-4000-8000-000000000002', 'planning', 'Block change check ' || n || ' (rolled back)', 20,
       now() + interval '40 days', now() + interval '40 days 2 hours'
  from unnest(array['a1', 'a2', 'a3', 'a4', 'a5', 'b1']) n;

-- a2's event books two venues (CR-97), so it has a space for each (AC10).
insert into public.event_space_requests (id, event_id, label)
values ('c0000000-0000-4000-8000-0000000054c1', 'e0000000-0000-4000-8000-0000000054a2', 'Main hall'),
       ('c0000000-0000-4000-8000-0000000054c2', 'e0000000-0000-4000-8000-0000000054a2', 'Breakout');

-- At Seminar Room 1. Block X will be [+40d 00:00, +40d 10:00), block Y
-- [+40d 03:00, +40d 05:00), block S started an hour ago and ends in 2 hours.
--   a1 [01:00, 02:00) approved          under X only
--   a2 [03:00, 04:00) approved          under X and Y (its other booking a2b is at Innovation Lab)
--   a3 [06:00, 07:00) approved          under X; gets a pending replacement r3
--   a4 [08:00, 08:30) approved          flagged by a deactivation before X
--   a5 [08:30, 09:30) held              under X; its hold later passes its expiry
--   c3 [now+30m, now+90m) approved      under S (event b1)
insert into public.venue_bookings (id, event_id, venue_id, booked_period, status, setup_minutes, expires_at, event_space_request_id)
values
    ('d0000000-0000-4000-8000-0000000054a1', 'e0000000-0000-4000-8000-0000000054a1', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '40 days 1 hour', date_trunc('hour', now()) + interval '40 days 2 hours', '[)'), 'approved', 0, null, null),
    ('d0000000-0000-4000-8000-0000000054a2', 'e0000000-0000-4000-8000-0000000054a2', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '40 days 3 hours', date_trunc('hour', now()) + interval '40 days 4 hours', '[)'), 'approved', 0, null, 'c0000000-0000-4000-8000-0000000054c1'),
    ('d0000000-0000-4000-8000-0000000054b2', 'e0000000-0000-4000-8000-0000000054a2', 'b0000000-0000-4000-8000-000000000001',
     tstzrange(date_trunc('hour', now()) + interval '40 days 3 hours', date_trunc('hour', now()) + interval '40 days 4 hours', '[)'), 'approved', 0, null, 'c0000000-0000-4000-8000-0000000054c2'),
    ('d0000000-0000-4000-8000-0000000054a3', 'e0000000-0000-4000-8000-0000000054a3', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '40 days 6 hours', date_trunc('hour', now()) + interval '40 days 7 hours', '[)'), 'approved', 0, null, null),
    ('d0000000-0000-4000-8000-0000000054a4', 'e0000000-0000-4000-8000-0000000054a4', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '40 days 8 hours', date_trunc('hour', now()) + interval '40 days 8 hours 30 minutes', '[)'), 'approved', 0, null, null),
    ('d0000000-0000-4000-8000-0000000054a5', 'e0000000-0000-4000-8000-0000000054a5', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(date_trunc('hour', now()) + interval '40 days 8 hours 30 minutes', date_trunc('hour', now()) + interval '40 days 9 hours 30 minutes', '[)'), 'held', 0,
     now() + interval '7 days', null),
    ('d0000000-0000-4000-8000-0000000054c3', 'e0000000-0000-4000-8000-0000000054b1', 'b0000000-0000-4000-8000-000000000003',
     tstzrange(now() + interval '30 minutes', now() + interval '90 minutes', '[)'), 'approved', 0, null, null);

-- a4 was flagged by a venue deactivation (SCRUM-64) before the block.
update public.venue_bookings
   set flag = 'affected', flag_reason = 'Venue deactivated: long-term renovation', flagged_at = now()
 where id = 'd0000000-0000-4000-8000-0000000054a4';

create temporary table scrum54_blocks (label text primary key, block_id uuid) on commit drop;
insert into scrum54_blocks
select 'X', r.block_id from public.create_venue_block(
    'b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000003',
    date_trunc('hour', now()) + interval '40 days', date_trunc('hour', now()) + interval '40 days 10 hours',
    'maintenance', 'Aircon overhaul', '{}') r;
insert into scrum54_blocks
select 'Y', r.block_id from public.create_venue_block(
    'b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000003',
    date_trunc('hour', now()) + interval '40 days 3 hours', date_trunc('hour', now()) + interval '40 days 5 hours',
    'safety', null, '{}') r;
insert into scrum54_blocks
select 'S', r.block_id from public.create_venue_block(
    'b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000003',
    now() - interval '1 hour', now() + interval '2 hours', 'equipment_failure', null, '{}') r;

-- a3's coordinator has already asked for a replacement at Innovation Lab (CR-95).
insert into public.venue_bookings (id, event_id, venue_id, booked_period, status, setup_minutes, expires_at, replaces_booking_id)
values ('d0000000-0000-4000-8000-0000000054d3', 'e0000000-0000-4000-8000-0000000054a3', 'b0000000-0000-4000-8000-000000000001',
        tstzrange(date_trunc('hour', now()) + interval '40 days 6 hours', date_trunc('hour', now()) + interval '40 days 7 hours', '[)'),
        'held', 0, now() + interval '7 days', 'd0000000-0000-4000-8000-0000000054a3');

create temporary table scrum54_results (label text primary key, outcome text) on commit drop;
create temporary table scrum54_counts (label text primary key, n bigint) on commit drop;
insert into scrum54_counts
select 'links_x', count(*) from public.venue_block_bookings where block_id = (select block_id from scrum54_blocks where label = 'X');
insert into scrum54_counts
select 'affected_notices', count(*) from public.notifications
 where type = 'venue_booking_affected' and event_id::text like 'e0000000-0000-4000-8000-0000000054%';

-- AC2: the refusals, each before anything is written.
insert into scrum54_results
select v.label, (select r.outcome from public.change_venue_block(v.venue, v.block, 'a0000000-0000-4000-8000-000000000003',
                                                                 v.action, v.new_end, v.note) r)
  from (values
      ('x_end_now_not_started', 'b0000000-0000-4000-8000-000000000003'::uuid, (select block_id from scrum54_blocks where label = 'X'),
       'end_now', null::timestamptz, null::text),
      ('x_lengthen', 'b0000000-0000-4000-8000-000000000003', (select block_id from scrum54_blocks where label = 'X'),
       'shorten', date_trunc('hour', now()) + interval '40 days 11 hours', null),
      ('x_same_end', 'b0000000-0000-4000-8000-000000000003', (select block_id from scrum54_blocks where label = 'X'),
       'shorten', date_trunc('hour', now()) + interval '40 days 10 hours', null),
      ('x_end_at_start', 'b0000000-0000-4000-8000-000000000003', (select block_id from scrum54_blocks where label = 'X'),
       'shorten', date_trunc('hour', now()) + interval '40 days', null),
      ('x_end_in_past', 'b0000000-0000-4000-8000-000000000003', (select block_id from scrum54_blocks where label = 'X'),
       'shorten', now() - interval '1 minute', null),
      ('x_note_too_long', 'b0000000-0000-4000-8000-000000000003', (select block_id from scrum54_blocks where label = 'X'),
       'remove', null, repeat('n', 1001)),
      ('x_bad_action', 'b0000000-0000-4000-8000-000000000003', (select block_id from scrum54_blocks where label = 'X'),
       'extend', null, null),
      ('x_wrong_venue', 'b0000000-0000-4000-8000-000000000001', (select block_id from scrum54_blocks where label = 'X'),
       'remove', null, null),
      ('no_venue', 'b0000000-0000-4000-8000-0000000000ff', (select block_id from scrum54_blocks where label = 'X'),
       'remove', null, null),
      ('s_remove_started', 'b0000000-0000-4000-8000-000000000003', (select block_id from scrum54_blocks where label = 'S'),
       'remove', null, null)
  ) v(label, venue, block, action, new_end, note);

do $$
declare
    v_row record;
    v_got text;
begin
    for v_row in
        select * from (values ('x_end_now_not_started', 'not_started'), ('x_lengthen', 'end_not_before_current'),
                              ('x_same_end', 'end_not_before_current'), ('x_end_at_start', 'end_not_after_start'),
                              ('x_end_in_past', 'end_in_past'), ('x_note_too_long', 'note_too_long'),
                              ('x_bad_action', 'invalid_action'), ('x_wrong_venue', 'block_not_found'),
                              ('no_venue', 'venue_not_found'), ('s_remove_started', 'already_started')) t(label, want)
    loop
        select outcome into v_got from scrum54_results where label = v_row.label;
        if v_got is distinct from v_row.want then
            raise exception 'BLOCK CHANGE FAIL: % returned % (want %)', v_row.label, v_got, v_row.want;
        end if;
    end loop;
    if exists (select 1 from public.venue_blocks where id in (select block_id from scrum54_blocks) and changed_at is not null) then
        raise exception 'BLOCK CHANGE FAIL: a refused change wrote to a block';
    end if;
end $$;

-- AC2: end S now (it has started), shorten X to end at +40d 03:00 with a
-- note, remove Y (it hasn't started), then try S and Y again.
insert into scrum54_results
select 's_end_now', r.outcome from public.change_venue_block('b0000000-0000-4000-8000-000000000003',
    (select block_id from scrum54_blocks where label = 'S'), 'a0000000-0000-4000-8000-000000000003', 'end_now', null, '  Projector fixed  ') r;
insert into scrum54_results
select 'x_shorten', r.outcome from public.change_venue_block('b0000000-0000-4000-8000-000000000003',
    (select block_id from scrum54_blocks where label = 'X'), 'a0000000-0000-4000-8000-000000000003', 'shorten',
    date_trunc('hour', now()) + interval '40 days 3 hours', repeat('n', 1000)) r;
insert into scrum54_results
select 'y_remove', r.outcome from public.change_venue_block('b0000000-0000-4000-8000-000000000003',
    (select block_id from scrum54_blocks where label = 'Y'), 'a0000000-0000-4000-8000-000000000003', 'remove', null, null) r;
insert into scrum54_results
select 's_again', r.outcome from public.change_venue_block('b0000000-0000-4000-8000-000000000003',
    (select block_id from scrum54_blocks where label = 'S'), 'a0000000-0000-4000-8000-000000000003', 'end_now', null, null) r;
insert into scrum54_results
select 'y_again', r.outcome from public.change_venue_block('b0000000-0000-4000-8000-000000000003',
    (select block_id from scrum54_blocks where label = 'Y'), 'a0000000-0000-4000-8000-000000000003', 'remove', null, null) r;

do $$
declare
    v_x uuid := (select block_id from scrum54_blocks where label = 'X');
    v_y uuid := (select block_id from scrum54_blocks where label = 'Y');
    v_s uuid := (select block_id from scrum54_blocks where label = 'S');
    v_row record;
    v_got text;
    v_base timestamptz := date_trunc('hour', now()) + interval '40 days';
begin
    for v_row in
        select * from (values ('s_end_now', 'ok'), ('x_shorten', 'ok'), ('y_remove', 'ok'),
                              ('s_again', 'ended'), ('y_again', 'removed')) t(label, want)
    loop
        select outcome into v_got from scrum54_results where label = v_row.label;
        if v_got is distinct from v_row.want then
            raise exception 'BLOCK CHANGE FAIL: % returned % (want %)', v_row.label, v_got, v_row.want;
        end if;
    end loop;

    -- AC4: the rows are kept, with the original period, who, when and the note.
    select * into v_row from public.venue_blocks where id = v_s;
    if upper(v_row.blocked_period) <> now() or upper(v_row.original_period) <> now() + interval '2 hours'
       or v_row.changed_by <> 'a0000000-0000-4000-8000-000000000003' or v_row.changed_at <> now()
       or v_row.change_note <> 'Projector fixed' or v_row.removed_at is not null then
        raise exception 'BLOCK CHANGE FAIL: ended block S is %', v_row;
    end if;
    select * into v_row from public.venue_blocks where id = v_x;
    if v_row.blocked_period <> tstzrange(v_base, v_base + interval '3 hours', '[)')
       or v_row.original_period <> tstzrange(v_base, v_base + interval '10 hours', '[)')
       or char_length(v_row.change_note) <> 1000 or v_row.notes <> 'Aircon overhaul' then
        raise exception 'BLOCK CHANGE FAIL: shortened block X is %', v_row;
    end if;
    select * into v_row from public.venue_blocks where id = v_y;
    if v_row.removed_at <> now() or v_row.blocked_period <> tstzrange(v_base + interval '3 hours', v_base + interval '5 hours', '[)')
       or v_row.original_period <> v_row.blocked_period then
        raise exception 'BLOCK CHANGE FAIL: removed block Y is %', v_row;
    end if;

    -- AC4: one history row per change, before and after, with the status and note.
    if (select count(*) from public.venue_edit_history
         where venue_id = 'b0000000-0000-4000-8000-000000000003' and created_at >= now()
           and after -> 'block' ? 'status') <> 3 then
        raise exception 'BLOCK CHANGE FAIL: expected 3 change history rows (refusals write none)';
    end if;
    if not exists (select 1 from public.venue_edit_history
                    where venue_id = 'b0000000-0000-4000-8000-000000000003' and created_at >= now()
                      and actor_id = 'a0000000-0000-4000-8000-000000000003'
                      and before -> 'block' ->> 'reason' = 'equipment_failure'
                      and (before -> 'block' ->> 'ends_at')::timestamptz = now() + interval '2 hours'
                      and (after -> 'block' ->> 'ends_at')::timestamptz = now()
                      and after -> 'block' ->> 'status' = 'ended_early'
                      and after -> 'block' ->> 'note' = 'Projector fixed') then
        raise exception 'BLOCK CHANGE FAIL: S''s history row is missing its before, after, status or note';
    end if;
    if not exists (select 1 from public.venue_edit_history
                    where venue_id = 'b0000000-0000-4000-8000-000000000003' and created_at >= now()
                      and before -> 'block' ->> 'reason' = 'safety'
                      and after -> 'block' ->> 'status' = 'removed' and after -> 'block' -> 'ends_at' = 'null'::jsonb) then
        raise exception 'BLOCK CHANGE FAIL: Y''s history row does not say it was removed';
    end if;

    -- Shortening covers nothing new: no new links, no new notices.
    if (select count(*) from public.venue_block_bookings where block_id = v_x)
       <> (select n from scrum54_counts where label = 'links_x') then
        raise exception 'BLOCK CHANGE FAIL: shortening X changed its links';
    end if;
    if (select count(*) from public.notifications
         where type = 'venue_booking_affected' and event_id::text like 'e0000000-0000-4000-8000-0000000054%')
       <> (select n from scrum54_counts where label = 'affected_notices') then
        raise exception 'BLOCK CHANGE FAIL: a change sent another Affected notice';
    end if;

    -- AC3: the freed time is searchable and bookable; what is still blocked is
    -- not; a removed block is no conflict; an Affected booking still occupies.
    if exists (select 1 from public.venue_conflicts(tstzrange(v_base + interval '9 hours 30 minutes', v_base + interval '10 hours', '[)'),
                                                    'b0000000-0000-4000-8000-000000000003')) then
        raise exception 'BLOCK CHANGE FAIL: the freed end of X still clashes';
    end if;
    if not exists (select 1 from public.venue_conflicts(tstzrange(v_base + interval '2 hours', v_base + interval '2 hours 30 minutes', '[)'),
                                                        'b0000000-0000-4000-8000-000000000003') c where c.kind = 'block') then
        raise exception 'BLOCK CHANGE FAIL: the shortened X no longer blocks its remaining period';
    end if;
    if exists (select 1 from public.venue_conflicts(tstzrange(v_base + interval '4 hours', v_base + interval '5 hours', '[)'),
                                                    'b0000000-0000-4000-8000-000000000003') c where c.kind = 'block') then
        raise exception 'BLOCK CHANGE FAIL: removed block Y still clashes';
    end if;
    if exists (select 1 from public.venue_conflicts(tstzrange(now() + interval '95 minutes', now() + interval '2 hours', '[)'),
                                                    'b0000000-0000-4000-8000-000000000003')) then
        raise exception 'BLOCK CHANGE FAIL: the time freed by ending S still clashes';
    end if;
    if not exists (select 1 from public.venue_conflicts(tstzrange(v_base + interval '6 hours', v_base + interval '7 hours', '[)'),
                                                        'b0000000-0000-4000-8000-000000000003') c
                    where c.booking_id = 'd0000000-0000-4000-8000-0000000054a3') then
        raise exception 'BLOCK CHANGE FAIL: an Affected booking stopped occupying its slot';
    end if;

    -- AC5: no flag is cleared by the change.
    if exists (select 1 from public.venue_bookings
                where id in ('d0000000-0000-4000-8000-0000000054a1', 'd0000000-0000-4000-8000-0000000054a2',
                             'd0000000-0000-4000-8000-0000000054a3', 'd0000000-0000-4000-8000-0000000054a5',
                             'd0000000-0000-4000-8000-0000000054c3')
                  and flag is distinct from 'affected') then
        raise exception 'BLOCK CHANGE FAIL: ending or shortening a block cleared a flag';
    end if;

    -- AC5: X lists a2 (Y, which also covered it, was removed), a3 and a5. Not
    -- a1 (X still covers it) nor a4 (a deactivation flagged it). S lists c3.
    if (select array_agg(right(booking_id::text, 2) order by booking_id) from public.restorable_block_bookings(v_x))
       <> array['a2', 'a3', 'a5'] then
        raise exception 'BLOCK CHANGE FAIL: X lists %',
            (select array_agg(right(booking_id::text, 2) order by booking_id) from public.restorable_block_bookings(v_x));
    end if;
    if (select array_agg(right(booking_id::text, 2)) from public.restorable_block_bookings(v_s)) <> array['c3'] then
        raise exception 'BLOCK CHANGE FAIL: S does not list c3 alone';
    end if;
    if (select array_agg(right(booking_id::text, 2) order by booking_id) from public.restorable_block_bookings(v_x)
         where has_pending_replacement) <> array['a3'] then
        raise exception 'BLOCK CHANGE FAIL: the pending replacement is not marked on a3 alone';
    end if;
    if (select count(*) from public.venue_bookings vb
         where vb.id::text like 'd0000000-0000-4000-8000-0000000054%' and public.restorable_after_block(vb)) <> 4 then
        raise exception 'BLOCK CHANGE FAIL: the computed column disagrees with the lists';
    end if;

    -- AC7: the replacement is untouched and a3's coordinator is told, once.
    if (select status::text from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000054d3') <> 'held' then
        raise exception 'BLOCK CHANGE FAIL: changing the block changed the replacement';
    end if;
    if (select count(*) from public.notifications
         where event_id = 'e0000000-0000-4000-8000-0000000054a3' and type = 'venue_free_replacement_pending'
           and recipient_id = 'a0000000-0000-4000-8000-000000000002' and recipient_role = 'event_coordinator') <> 1 then
        raise exception 'BLOCK CHANGE FAIL: a3''s coordinator was not told once about the pending replacement';
    end if;
    if exists (select 1 from public.notifications
                where type = 'venue_free_replacement_pending'
                  and event_id::text like 'e0000000-0000-4000-8000-0000000054%'
                  and event_id <> 'e0000000-0000-4000-8000-0000000054a3') then
        raise exception 'BLOCK CHANGE FAIL: an event with no replacement was told about one';
    end if;
end $$;

-- AC6: a hold that passes its expiry before the minute job runs can't be restored.
update public.venue_bookings set expires_at = now() - interval '1 minute'
 where id = 'd0000000-0000-4000-8000-0000000054a5';

insert into scrum54_results
select 'restore_a5_expired', r.outcome from public.restore_affected_booking(
    'd0000000-0000-4000-8000-0000000054a5', 'a0000000-0000-4000-8000-000000000003') r;
insert into scrum54_results
select 'restore_a1_blocked', r.outcome from public.restore_affected_booking(
    'd0000000-0000-4000-8000-0000000054a1', 'a0000000-0000-4000-8000-000000000003') r;
insert into scrum54_results
select 'restore_a3', r.outcome from public.restore_affected_booking(
    'd0000000-0000-4000-8000-0000000054a3', 'a0000000-0000-4000-8000-000000000003') r;
insert into scrum54_results
select 'restore_a2', r.outcome from public.restore_affected_booking(
    'd0000000-0000-4000-8000-0000000054a2', 'a0000000-0000-4000-8000-000000000003') r;

do $$
declare
    v_row record;
    v_got text;
begin
    for v_row in
        select * from (values ('restore_a5_expired', 'hold_expired'), ('restore_a1_blocked', 'still_blocked'),
                              ('restore_a3', 'ok'), ('restore_a2', 'ok')) t(label, want)
    loop
        select outcome into v_got from scrum54_results where label = v_row.label;
        if v_got is distinct from v_row.want then
            raise exception 'BLOCK RESTORE FAIL: % returned % (want %)', v_row.label, v_got, v_row.want;
        end if;
    end loop;
    if (select flag::text from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000054a5') <> 'affected' then
        raise exception 'BLOCK RESTORE FAIL: the expired hold lost its flag';
    end if;

    -- AC6: restored as before, the event untouched; CR-95 cancels the pending replacement.
    if (select (status::text, flag) from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000054a3')
       is distinct from ('approved'::text, null::public.venue_booking_flag) then
        raise exception 'BLOCK RESTORE FAIL: a3 is not approved and unflagged';
    end if;
    if (select status::text from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000054d3') <> 'cancelled' then
        raise exception 'BLOCK RESTORE FAIL: a3''s pending replacement was not cancelled';
    end if;
    if exists (select 1 from public.events where id::text like 'e0000000-0000-4000-8000-0000000054%' and status <> 'planning') then
        raise exception 'BLOCK RESTORE FAIL: an event''s status changed';
    end if;

    -- AC10: a2's other booking, at Innovation Lab, is unchanged.
    if (select (status::text, flag) from public.venue_bookings where id = 'd0000000-0000-4000-8000-0000000054b2')
       is distinct from ('approved'::text, null::public.venue_booking_flag) then
        raise exception 'BLOCK RESTORE FAIL: restoring a2 changed the event''s other booking';
    end if;

    -- AC6, D83: the coordinator and the organiser are told, each in their role.
    if (select array_agg(recipient_role::text order by recipient_role::text) from public.notifications
         where event_id = 'e0000000-0000-4000-8000-0000000054a3' and type = 'venue_booking_restored')
       <> array['event_coordinator', 'event_organiser'] then
        raise exception 'BLOCK RESTORE FAIL: restore notices are addressed to %',
            (select array_agg(recipient_role::text) from public.notifications
              where event_id = 'e0000000-0000-4000-8000-0000000054a3' and type = 'venue_booking_restored');
    end if;
end $$;

-- AC9: the API roles can't change a block or ask what it freed. The block id
-- goes through a setting: the temporary table isn't readable as authenticated,
-- and a refusal to read it would pass for the refusal being checked.
select set_config('scrum54.block_x', block_id::text, true) from scrum54_blocks where label = 'X';
set local role authenticated;
do $$
begin
    begin
        perform public.change_venue_block('b0000000-0000-4000-8000-000000000003',
            current_setting('scrum54.block_x')::uuid, 'a0000000-0000-4000-8000-000000000003', 'end_now', null, null);
        raise exception 'BLOCK RLS FAIL: authenticated could call change_venue_block';
    exception when insufficient_privilege then null;
    end;
    begin
        perform 1 from public.restorable_block_bookings(current_setting('scrum54.block_x')::uuid);
        raise exception 'BLOCK RLS FAIL: authenticated could call restorable_block_bookings';
    exception when insufficient_privilege then null;
    end;
end $$;
reset role;

select 'VENUE BLOCK CHANGE CHECKS PASSED' as result;

rollback;
