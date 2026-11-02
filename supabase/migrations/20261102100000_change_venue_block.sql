-- =============================================================================
-- ConnectSphere - SCRUM-54 Venue Staff end, shorten or remove a block early
--
-- SCRUM-51 made blocks and kept them (no delete). This lets Venue Staff:
--   - end a started block now, shorten it to an earlier end, or remove one
--     that hasn't started (AC2); never lengthen one or change one that ended;
--   - keep the row and its original period, who changed it, when and why,
--     with a venue_edit_history row (AC4);
--   - see which bookings the block flagged that no block covers any more, to
--     restore through CR-95's restore_affected_booking (AC5, AC6). Nothing
--     here clears a flag (QA3-9) or touches a replacement (AC7); the
--     coordinator of a freed booking with a pending replacement is told.
-- A removed block keeps its period and is left out of venue_conflicts, so
-- search, requests and approval stop seeing it (AC3).
-- Also D81: the restore notice registered only the coordinator's role, so the
-- organiser's copy (CR-95 AC9, SCRUM-54 AC6) was never shown.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. What a change records on the block (AC4). original_period is the period
--    before the first change; the current one stays in blocked_period.
-- -----------------------------------------------------------------------------
alter table public.venue_blocks
    add column original_period tstzrange null,
    add column changed_at timestamptz null,
    add column changed_by uuid null references public.profiles (id) on delete set null,
    add column change_note text null,
    add column removed_at timestamptz null,
    add constraint venue_blocks_change_note_length
        check (change_note is null or char_length(btrim(change_note)) <= 1000),
    add constraint venue_blocks_original_period_is_bounded_half_open check (
        original_period is null or (
            not isempty(original_period)
            and lower_inc(original_period)
            and not upper_inc(original_period)
            and not lower_inf(original_period)
            and not upper_inf(original_period)
        )
    ),
    add constraint venue_blocks_change_recorded check ((original_period is null) = (changed_at is null)),
    add constraint venue_blocks_removed_was_changed check (removed_at is null or changed_at is not null);

comment on column public.venue_blocks.original_period is
    'SCRUM-54 AC4: the block''s period before it was first ended early, shortened or removed. Null while unchanged.';
comment on column public.venue_blocks.changed_by is
    'SCRUM-54 AC4: the Venue Staff member who last changed the block.';
comment on column public.venue_blocks.change_note is
    'SCRUM-54 AC2: the optional note (at most 1000 characters) given with the last change.';
comment on column public.venue_blocks.removed_at is
    'SCRUM-54 AC2: when a block that had not started was removed. The row is kept (SCRUM-51 AC9) but no longer blocks anything.';

create index venue_blocks_changed_by_idx on public.venue_blocks (changed_by);

-- -----------------------------------------------------------------------------
-- 2. The single conflict check (SCRUM-21) ignores a removed block (AC3).
--    Same body as 20261017130000 plus `b.removed_at is null`.
-- -----------------------------------------------------------------------------
create or replace function public.venue_conflicts(
    p_period tstzrange,
    p_venue_id uuid default null,
    p_exclude_booking_id uuid default null
) returns table (
    venue_id uuid,
    kind text,
    booking_id uuid,
    event_id uuid,
    event_name text,
    booking_status text,
    block_reason text,
    occupied_period tstzrange
)
language sql
stable
security definer
set search_path = ''
as $$
    select vb.venue_id, 'booking', vb.id, vb.event_id, e.name, vb.status::text, null, vb.occupied_period
    from public.venue_bookings vb
    join public.events e on e.id = vb.event_id
    where vb.occupied_period && p_period
      and (p_venue_id is null or vb.venue_id = p_venue_id)
      and (p_exclude_booking_id is null or vb.id <> p_exclude_booking_id)
      and (vb.status in ('approved', 're_review')
           or (vb.status = 'held' and vb.expires_at > now()))
    union all
    select b.venue_id, 'block', null, null, null, null, b.reason::text, b.blocked_period
    from public.venue_blocks b
    where b.blocked_period && p_period
      and b.removed_at is null
      and (p_venue_id is null or b.venue_id = p_venue_id)
    order by 8, 1;
$$;

comment on function public.venue_conflicts(tstzrange, uuid, uuid) is
    'SCRUM-21: the bookings and blocks that clash with an occupied window, at one venue or all. A removed block (SCRUM-54) is not a clash. The single conflict check every booking path uses. API-only.';

-- -----------------------------------------------------------------------------
-- 3. Shortening a block covers nothing new, so it must not re-run CR-95's
--    flagging and linking. The trigger now fires on insert, and on an update
--    only when the period or venue reaches somewhere it didn't before. WHEN
--    can't read OLD on insert, hence two triggers on the same function.
-- -----------------------------------------------------------------------------
drop trigger venue_blocks_flag_bookings on public.venue_blocks;

create trigger venue_blocks_flag_bookings
    after insert
    on public.venue_blocks
    for each row execute function private.flag_bookings_under_block();

create trigger venue_blocks_flag_bookings_on_widen
    after update of blocked_period, venue_id
    on public.venue_blocks
    for each row
    when (new.removed_at is null
          and (old.venue_id is distinct from new.venue_id or not (old.blocked_period @> new.blocked_period)))
    execute function private.flag_bookings_under_block();

-- -----------------------------------------------------------------------------
-- 4. Restorable after a block (AC5). A booking qualifies when a block flagged
--    it (the flag came from a block and it is linked to one), it is still live
--    and has not ended, its venue is active, and no block covers any part of
--    its occupied window. That is what restore_affected_booking would accept,
--    except a booking taken by another (which an unreleased booking can't be).
--    Deactivation's flags ("Venue deactivated: ...") and CR-94's (conflict,
--    unsuitable) are excluded. Also served as the `restorable_after_block`
--    computed column on venue_bookings, so the venue-staff queue reads it in
--    the same query.
-- -----------------------------------------------------------------------------
create function public.restorable_after_block(p_booking public.venue_bookings)
returns boolean
language sql
stable
set search_path = ''
as $$
    select coalesce(p_booking.flag = 'affected', false)
       and coalesce(p_booking.flag_reason like 'Venue unavailable%', false)
       and (p_booking.status = 'approved' or (p_booking.status = 'held' and p_booking.expires_at > now()))
       and upper(p_booking.occupied_period) > now()
       and exists (select 1 from public.venue_block_bookings l where l.booking_id = p_booking.id)
       and exists (select 1 from public.venues v where v.id = p_booking.venue_id and v.is_active)
       and not exists (
           select 1
             from public.venue_conflicts(p_booking.occupied_period, p_booking.venue_id, p_booking.id) c
            where c.kind = 'block'
       );
$$;

comment on function public.restorable_after_block(public.venue_bookings) is
    'SCRUM-54 AC5: true when a block flagged this booking Affected and no block covers its occupied window any more, so venue staff can restore it. PostgREST computed column. API-only.';

revoke execute on function public.restorable_after_block(public.venue_bookings) from public, anon, authenticated;
grant execute on function public.restorable_after_block(public.venue_bookings) to service_role;

create function public.restorable_block_bookings(p_block_id uuid)
returns table (
    booking_id uuid,
    event_id uuid,
    status text,
    occupied_period tstzrange,
    has_pending_replacement boolean
)
language sql
stable
set search_path = ''
as $$
    select b.id, b.event_id, b.status::text, b.occupied_period,
           exists (
               select 1 from public.venue_bookings r
                where r.replaces_booking_id = b.id and r.status in ('held', 're_review')
           )
      from public.venue_block_bookings l
      join public.venue_bookings b on b.id = l.booking_id
     where l.block_id = p_block_id
       and public.restorable_after_block(b)
     order by lower(b.occupied_period), b.id;
$$;

comment on function public.restorable_block_bookings(uuid) is
    'SCRUM-54 AC5, AC7: the bookings this block flagged that no block covers any more, and whether each has a pending replacement (restoring would cancel it, CR-95 AC9). API-only.';

revoke execute on function public.restorable_block_bookings(uuid) from public, anon, authenticated;
grant execute on function public.restorable_block_bookings(uuid) to service_role;

-- -----------------------------------------------------------------------------
-- 5. The coordinator's notice when a freed booking has a pending replacement
--    (AC7), and D81: the restore notice goes to the organiser too.
-- -----------------------------------------------------------------------------
insert into public.notification_types (type, recipient_roles) values
    ('venue_free_replacement_pending', '{event_coordinator}');

update public.notification_types
   set recipient_roles = '{event_coordinator,event_organiser}'
 where type = 'venue_booking_restored';

-- The organisers' restore notices sent so far were stamped with no role and
-- never shown; stamp them now that the type names their role.
update public.notifications n
   set recipient_role = private.resolve_notification_role(n.recipient_id, n.event_id, n.type)
 where n.type = 'venue_booking_restored'
   and n.recipient_role is null;

-- -----------------------------------------------------------------------------
-- 6. change_venue_block (AC2, AC4, AC7). The venue lock serialises a change
--    against booking requests and approvals (which hold it `for share`) and
--    against restore, so what a request or restore sees is the block before
--    or after the change, never half of it (AC3). The block must belong to
--    the venue. Outcomes: ok, venue_not_found, block_not_found, removed,
--    ended, already_started, not_started, end_in_past, end_not_after_start,
--    end_not_before_current, note_too_long, invalid_action.
-- -----------------------------------------------------------------------------
create function public.change_venue_block(
    p_venue_id uuid,
    p_block_id uuid,
    p_actor_id uuid,
    p_action text,
    p_new_ends_at timestamptz,
    p_note text
) returns table (outcome text)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_block public.venue_blocks;
    v_venue_name text;
    v_now timestamptz := now();
    v_note text := nullif(btrim(coalesce(p_note, '')), '');
    v_start timestamptz;
    v_end timestamptz;
    v_new_end timestamptz;
    v_before jsonb;
    v_freed record;
begin
    select v.name into v_venue_name from public.venues v where v.id = p_venue_id for update;
    if not found then
        return query select 'venue_not_found'::text;
        return;
    end if;

    select * into v_block from public.venue_blocks b
     where b.id = p_block_id and b.venue_id = p_venue_id
       for update;
    if not found then
        return query select 'block_not_found'::text;
        return;
    end if;

    v_start := lower(v_block.blocked_period);
    v_end := upper(v_block.blocked_period);

    if v_block.removed_at is not null then
        return query select 'removed'::text;
        return;
    end if;
    if v_end <= v_now then
        return query select 'ended'::text;
        return;
    end if;
    if char_length(coalesce(v_note, '')) > 1000 then
        return query select 'note_too_long'::text;
        return;
    end if;

    if p_action = 'remove' then
        if v_start < v_now then
            return query select 'already_started'::text;
            return;
        end if;
    elsif p_action = 'end_now' then
        if v_start >= v_now then
            return query select 'not_started'::text;
            return;
        end if;
        v_new_end := v_now;
    elsif p_action = 'shorten' then
        if p_new_ends_at is null or p_new_ends_at <= v_now then
            return query select 'end_in_past'::text;
            return;
        end if;
        if p_new_ends_at <= v_start then
            return query select 'end_not_after_start'::text;
            return;
        end if;
        if p_new_ends_at >= v_end then
            return query select 'end_not_before_current'::text;
            return;
        end if;
        v_new_end := p_new_ends_at;
    else
        return query select 'invalid_action'::text;
        return;
    end if;

    update public.venue_blocks
       set original_period = coalesce(original_period, blocked_period),
           blocked_period = case when p_action = 'remove' then blocked_period
                                 else tstzrange(v_start, v_new_end, '[)') end,
           removed_at = case when p_action = 'remove' then v_now end,
           changed_at = v_now,
           changed_by = p_actor_id,
           change_note = v_note
     where id = p_block_id;

    -- AC4: the venue's history shows the period before and after, the reason,
    -- the note and that the block ended early or was removed; venue_edit_history
    -- adds who and when.
    v_before := jsonb_build_object('starts_at', v_start, 'ends_at', v_end,
                                   'reason', v_block.reason, 'notes', v_block.notes);
    insert into public.venue_edit_history (venue_id, actor_id, before, after)
    values (
        p_venue_id, p_actor_id,
        jsonb_build_object('block', v_before),
        jsonb_build_object('block', v_before || jsonb_build_object(
            'ends_at', case when p_action = 'remove' then null else v_new_end end,
            'status', case when p_action = 'remove' then 'removed' else 'ended_early' end,
            'note', v_note))
    );

    -- AC7: a replacement already requested is left alone. Its coordinator is
    -- told the original venue is free again, on each change that frees it.
    for v_freed in
        select r.booking_id, e.id as event_id, e.name as event_name, e.coordinator_id
          from public.restorable_block_bookings(p_block_id) r
          join public.events e on e.id = r.event_id
         where r.has_pending_replacement
    loop
        perform public.add_notification(
            v_freed.coordinator_id, v_freed.event_id, 'venue_free_replacement_pending',
            'The venue "' || v_venue_name || '" is available again for "' || v_freed.event_name
                || '". Your replacement venue request is still pending. If venue staff restore the original '
                || 'booking, the replacement request is cancelled.',
            p_actor_id
        );
    end loop;

    return query select 'ok'::text;
end;
$$;

comment on function public.change_venue_block(uuid, uuid, uuid, text, timestamptz, text) is
    'SCRUM-54: Venue Staff end a block now, shorten it or remove one that has not started, under the venue lock. Keeps the row with its original period, writes the venue history row, and tells the coordinator of a freed booking with a pending replacement. Never clears a flag. API-only.';

revoke execute on function public.change_venue_block(uuid, uuid, uuid, text, timestamptz, text)
    from public, anon, authenticated;
grant execute on function public.change_venue_block(uuid, uuid, uuid, text, timestamptz, text)
    to service_role;

-- -----------------------------------------------------------------------------
-- 7. restore_affected_booking refuses a hold past its expiry (AC6, CR-99),
--    which the minute job may not have marked yet. Otherwise the same body as
--    20261018130000.
-- -----------------------------------------------------------------------------
create or replace function public.restore_affected_booking(p_booking_id uuid, p_actor_id uuid)
returns table (outcome text, cancelled_booking_ids uuid[])
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_booking public.venue_bookings;
    v_event public.events;
    v_venue public.venues;
    v_kind text;
    v_cancelled uuid[];
    v_message text;
begin
    select * into v_booking from public.venue_bookings where id = p_booking_id for update;
    if not found then
        return query select 'booking_not_found'::text, null::uuid[];
        return;
    end if;
    if v_booking.flag is distinct from 'affected' or v_booking.status not in ('held', 'approved') then
        return query select 'not_affected'::text, null::uuid[];
        return;
    end if;
    if v_booking.status = 'held' and v_booking.expires_at <= now() then
        return query select 'hold_expired'::text, null::uuid[];
        return;
    end if;
    if exists (
        select 1 from public.venue_bookings r
        where r.replaces_booking_id = v_booking.id and r.status = 'approved'
    ) then
        return query select 'replacement_approved'::text, null::uuid[];
        return;
    end if;

    select * into v_venue from public.venues where id = v_booking.venue_id for share;
    if not v_venue.is_active then
        return query select 'venue_inactive'::text, null::uuid[];
        return;
    end if;

    select c.kind into v_kind
      from public.venue_conflicts(v_booking.occupied_period, v_booking.venue_id, v_booking.id) c
     limit 1;
    if v_kind is not null then
        return query select case when v_kind = 'block' then 'still_blocked' else 'held_by_other' end, null::uuid[];
        return;
    end if;

    -- Cancel the pending replacement first, so the space's single active slot
    -- is free when the original's flag is cleared.
    with cancelled as (
        update public.venue_bookings r
           set status = 'cancelled'
         where r.replaces_booking_id = v_booking.id and r.status in ('held', 're_review')
        returning r.id, r.status as new_status
    ), history as (
        insert into public.venue_booking_history (booking_id, actor_id, action, from_status, to_status)
        select r.id, p_actor_id, 'cancelled_for_restore', old.status, 'cancelled'
          from cancelled r
          join public.venue_bookings old on old.id = r.id
        returning booking_id
    )
    select coalesce(array_agg(id), '{}') into v_cancelled from cancelled;

    update public.venue_bookings
       set flag = null, flag_reason = null, flagged_at = null
     where id = v_booking.id;

    insert into public.venue_booking_history (booking_id, actor_id, action, from_status, to_status)
    values (v_booking.id, p_actor_id, 'restored', v_booking.status, v_booking.status);

    select * into v_event from public.events where id = v_booking.event_id;
    v_message := 'The venue booking at "' || v_venue.name || '" for "' || v_event.name
        || '" has been restored by venue staff. Any replacement request was cancelled.';
    insert into public.notifications (recipient_id, event_id, type, message)
    select recipient, v_event.id, 'venue_booking_restored', v_message
      from unnest(array[v_event.coordinator_id, v_event.organiser_id]) as recipient
     where recipient is not null;

    return query select 'ok'::text, v_cancelled;
end;
$$;

comment on function public.restore_affected_booking(uuid, uuid) is
    'CR-95 AC9, SCRUM-54 AC6: venue staff restore an affected booking once its venue is free for the full occupied window: clears the flag, cancels a pending replacement, history on both, tells the coordinator and organiser. Refuses an expired hold. Returns an outcome code, never raises. API-only.';
