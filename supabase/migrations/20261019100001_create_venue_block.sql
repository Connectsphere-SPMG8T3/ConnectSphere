-- =============================================================================
-- ConnectSphere - SCRUM-51 Venue Staff block a venue
--
-- venue_blocks has existed since Sprint 1 and already counts as a conflict in
-- SCRUM-21's venue_conflicts, so search, requests and approval refuse a
-- blocked time (AC2-AC4), and CR-95's trigger already flags the bookings a
-- block overlaps (AC5). This adds the way to create one:
--   - who made it, and the detail rules (AC1, AC9);
--   - venue_block_bookings: every booking a block affects, so a booking under
--     two blocks is flagged once but recorded against both (AC10), for 54;
--   - the trigger links through venue_conflicts (AC7, AC11) and no longer
--     tells the organiser the reason (AC13);
--   - create_venue_block: lock, insert, history row, in one transaction.
-- Blocks are never deleted (AC9): nothing deletes them and API roles can't.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Who made the block, and the detail rules (AC1).
-- -----------------------------------------------------------------------------
alter table public.venue_blocks
    add column created_by uuid null references public.profiles (id) on delete set null,
    add constraint venue_blocks_notes_length check (notes is null or char_length(btrim(notes)) <= 1000),
    add constraint venue_blocks_other_needs_notes check (reason <> 'other' or nullif(btrim(notes), '') is not null);

comment on column public.venue_blocks.created_by is
    'The Venue Staff member who created the block (SCRUM-51 AC9). Null for blocks created before SCRUM-51.';

create index venue_blocks_created_by_idx on public.venue_blocks (created_by);

-- -----------------------------------------------------------------------------
-- 2. Every booking a block affects (AC10). The booking's flag says it needs a
--    follow-up; these rows say which blocks caused it, so ending one block
--    early (54) can tell whether another still covers the booking.
-- -----------------------------------------------------------------------------
create table public.venue_block_bookings (
    block_id uuid not null references public.venue_blocks (id) on delete cascade,
    booking_id uuid not null references public.venue_bookings (id) on delete cascade,
    linked_at timestamptz not null default now(),
    primary key (block_id, booking_id)
);

comment on table public.venue_block_bookings is
    'SCRUM-51 AC10: each held or approved booking a venue block overlapped when it was saved. Written by the venue_blocks trigger only. API-only.';

create index venue_block_bookings_booking_idx on public.venue_block_bookings (booking_id);

alter table public.venue_block_bookings enable row level security;
revoke all on table public.venue_block_bookings from public, anon, authenticated;

-- -----------------------------------------------------------------------------
-- 3. A block reason as people read it. Compared as text, so it never casts a
--    value added in this release's other migration.
-- -----------------------------------------------------------------------------
create or replace function private.venue_block_reason_label(p_reason public.venue_block_reason)
returns text
language sql
immutable
set search_path = ''
as $$
    select case p_reason::text
        when 'maintenance' then 'Maintenance'
        when 'equipment_failure' then 'Equipment failure'
        when 'renovation' then 'Renovation'
        when 'safety' then 'Safety'
        when 'internal_activity' then 'Internal activity'
        when 'other' then 'Other'
        else replace(p_reason::text, '_', ' ')
    end;
$$;

revoke execute on function private.venue_block_reason_label(public.venue_block_reason) from public, anon, authenticated;

-- -----------------------------------------------------------------------------
-- 4. The block trigger (CR-95), now linking and with no reason for organisers.
-- -----------------------------------------------------------------------------
create or replace function private.flag_bookings_under_block()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_venue_name text;
    v_label text;
    v_event_id uuid;
begin
    select name into v_venue_name from public.venues where id = new.venue_id;
    v_label := private.venue_block_reason_label(new.reason);

    -- AC7, AC10, AC11: the bookings come from the shared conflict check, on
    -- their occupied windows. Held and approved ones that have not ended are
    -- recorded against this block, even when another block (or another
    -- story) flagged them first.
    insert into public.venue_block_bookings (block_id, booking_id)
    select new.id, c.booking_id
      from public.venue_conflicts(new.blocked_period, new.venue_id) c
     where c.kind = 'booking'
       and c.booking_status in ('held', 'approved')
       and upper(c.occupied_period) > now()
    on conflict do nothing;

    -- flag_venue_bookings returns only the events it flagged just now, so a
    -- booking flagged earlier is not announced again (CR-95 AC3, AC10).
    for v_event_id in
        select public.flag_venue_bookings(
            new.venue_id,
            new.blocked_period,
            'affected',
            'Venue unavailable: ' || v_label,
            'Venue "' || coalesce(v_venue_name, 'unknown') || '" is unavailable (' || v_label
                || ') during your event''s booking. Review it and arrange an alternative venue.'
        )
    loop
        -- AC13: the organiser learns the arrangement is affected and what
        -- happens next, but not why. Attendees are told nothing (CAL-R5).
        insert into public.notifications (recipient_id, event_id, type, message)
        select e.organiser_id, e.id, 'venue_unavailable_organiser',
               'The venue "' || coalesce(v_venue_name, 'unknown') || '" is unavailable during your event. '
                   || 'Your event is not cancelled: your coordinator will arrange an alternative venue and update you.'
          from public.events e
         where e.id = v_event_id;
    end loop;
    return new;
end;
$$;

comment on function private.flag_bookings_under_block() is
    'CR-95 AC1, SCRUM-51 AC5, AC10, AC13: records and flags the held and approved bookings a venue block overlaps, and tells their organisers without the reason. Trigger-only.';

revoke execute on function private.flag_bookings_under_block() from public, anon, authenticated;

-- -----------------------------------------------------------------------------
-- 5. create_venue_block (AC1, AC9). The venue lock serialises a block against
--    booking requests and approvals, which hold it `for share`: either the
--    request sees the block and is refused, or the block sees the hold and
--    flags it. Never returns the event to planning (CR-95 AC7).
--    Outcomes: ok, venue_not_found, invalid_period, ended, detail_too_long,
--    invalid_detail.
-- -----------------------------------------------------------------------------
create or replace function public.create_venue_block(
    p_venue_id uuid,
    p_actor_id uuid,
    p_starts_at timestamptz,
    p_ends_at timestamptz,
    p_reason public.venue_block_reason,
    p_notes text,
    p_history_after jsonb
) returns table (outcome text, block_id uuid)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_block_id uuid;
begin
    perform 1 from public.venues v where v.id = p_venue_id for update;
    if not found then
        return query select 'venue_not_found'::text, null::uuid;
        return;
    end if;

    if p_starts_at is null or p_ends_at is null or p_ends_at <= p_starts_at then
        return query select 'invalid_period'::text, null::uuid;
        return;
    end if;
    if p_ends_at <= now() then
        return query select 'ended'::text, null::uuid;
        return;
    end if;
    if char_length(btrim(coalesce(p_notes, ''))) > 1000 then
        return query select 'detail_too_long'::text, null::uuid;
        return;
    end if;
    if p_reason = 'other' and nullif(btrim(p_notes), '') is null then
        return query select 'invalid_detail'::text, null::uuid;
        return;
    end if;

    -- CR-99 AC5: an overdue hold is expired first, so it is neither flagged
    -- nor recorded against the block.
    perform public.expire_venue_holds(now());

    insert into public.venue_blocks (venue_id, blocked_period, reason, notes, created_by)
    values (p_venue_id, tstzrange(p_starts_at, p_ends_at, '[)'), p_reason, nullif(btrim(p_notes), ''), p_actor_id)
    returning id into v_block_id;

    insert into public.venue_edit_history (venue_id, actor_id, before, after)
    values (p_venue_id, p_actor_id, '{}'::jsonb, coalesce(p_history_after, '{}'::jsonb));

    return query select 'ok'::text, v_block_id;
end;
$$;

comment on function public.create_venue_block(uuid, uuid, timestamptz, timestamptz, public.venue_block_reason, text, jsonb) is
    'SCRUM-51: Venue Staff block a venue. Locks the venue, inserts the block (its trigger flags, links and notifies), and records the history row. Outcomes: ok, venue_not_found, invalid_period, ended, detail_too_long, invalid_detail. API-only.';

revoke execute on function public.create_venue_block(uuid, uuid, timestamptz, timestamptz, public.venue_block_reason, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.create_venue_block(uuid, uuid, timestamptz, timestamptz, public.venue_block_reason, text, jsonb)
    to service_role;

-- AC9: blocks are kept. The API roles could never write them (RLS has only a
-- select policy); this makes it explicit for delete.
revoke delete on table public.venue_blocks from anon, authenticated;
