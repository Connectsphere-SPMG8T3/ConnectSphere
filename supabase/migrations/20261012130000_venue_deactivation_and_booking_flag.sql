-- =============================================================================
-- ConnectSphere - SCRUM-64 deactivate a venue, and the booking flag (W7 CR-02)
--
-- Venues: an inactive venue records why (AC1). deactivate_venue and
-- reactivate_venue are the only writers of is_active, each with a version
-- check and a venue_edit_history row, the same shape as update_venue
-- (SCRUM-63).
--
-- Bookings: venue_bookings.flag is the shared "this arrangement needs
-- follow-up" marker. SCRUM-64 sets `affected` when a venue is deactivated;
-- CR-95 sets `affected` when a block overlaps a booking and CR-94 sets
-- `conflict` / `unsuitable`, all through flag_venue_bookings. One open flag
-- per booking: a new flag never overwrites an existing one. Clearing a flag is
-- the coordinator's follow-up (CR-95, CR-94), never this migration's.
-- A flagged booking is not ready for the safety check (82 AC10), so
-- safety_approve_event refuses it under its lock.
--
-- request_venue_booking and safety_approve_event are recreated from their live
-- definitions (the former includes CR-99's expiry call), changed only where
-- marked SCRUM-64.
-- =============================================================================

create type public.venue_inactive_reason as enum ('permanently_closed', 'long_term_renovation', 'other');

alter table public.venues
    add column inactive_reason public.venue_inactive_reason null,
    add column inactive_note varchar(500) null;

comment on column public.venues.inactive_reason is
    'Why venue staff deactivated the venue (SCRUM-64 AC1). Set exactly when is_active is false.';
comment on column public.venues.inactive_note is
    'Free-text detail for inactive_reason; required when the reason is other (SCRUM-64).';

-- Venues made inactive before reasons existed get a neutral reason, so the
-- constraint below can hold for every row.
update public.venues
   set inactive_reason = 'other', inactive_note = 'Deactivated before reasons were recorded'
 where not is_active and inactive_reason is null;

alter table public.venues add constraint venues_inactive_reason_consistent check (
    (is_active and inactive_reason is null and inactive_note is null)
    or (not is_active and inactive_reason is not null
        and (inactive_reason <> 'other' or length(btrim(coalesce(inactive_note, ''))) > 0))
);

create type public.venue_booking_flag as enum ('affected', 'conflict', 'unsuitable');

alter table public.venue_bookings
    add column flag public.venue_booking_flag null,
    add column flag_reason text null,
    add column flagged_at timestamptz null;

comment on column public.venue_bookings.flag is
    'Open follow-up on this booking: affected (venue unavailable or deactivated: CR-95, SCRUM-64), conflict or unsuitable (after a venue change: CR-94). A flagged booking is not ready for the safety check (82 AC10). Set only through flag_venue_bookings; cleared by the coordinator''s follow-up.';
comment on column public.venue_bookings.flag_reason is 'Why the booking was flagged, as the coordinator reads it.';
comment on column public.venue_bookings.flagged_at is 'When the booking was flagged.';

alter table public.venue_bookings add constraint venue_bookings_flag_consistent check (
    (flag is null and flag_reason is null and flagged_at is null)
    or (flag is not null and flagged_at is not null and length(btrim(coalesce(flag_reason, ''))) > 0)
);

-- -----------------------------------------------------------------------------
-- flag_venue_bookings: the shared flagging step (SCRUM-64 AC3, CR-95, CR-94).
-- -----------------------------------------------------------------------------
create function public.flag_venue_bookings(
    p_venue_id uuid,
    p_period tstzrange,
    p_flag public.venue_booking_flag,
    p_reason text,
    p_message text
) returns setof uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_events uuid[];
begin
    with flagged as (
        update public.venue_bookings
           set flag = p_flag, flag_reason = btrim(p_reason), flagged_at = now()
         where venue_id = p_venue_id
           and status in ('held', 'approved')
           and occupied_period && p_period
           and upper(occupied_period) > now()
           and flag is null
        returning event_id
    )
    select coalesce(array_agg(distinct event_id), '{}') into v_events from flagged;

    insert into public.notifications (recipient_id, event_id, type, message)
    select e.coordinator_id, e.id, 'venue_booking_affected', p_message
      from public.events e
     where e.id = any (v_events)
       and e.coordinator_id is not null;

    return query select unnest(v_events);
end;
$$;

comment on function public.flag_venue_bookings(uuid, tstzrange, public.venue_booking_flag, text, text) is
    'Flags every held or approved booking at the venue that overlaps p_period, has not ended and has no flag yet; notifies each event''s coordinator once (type venue_booking_affected). Returns the flagged event ids. Shared by SCRUM-64, CR-95 and CR-94. API-only.';

-- -----------------------------------------------------------------------------
-- deactivate_venue / reactivate_venue (SCRUM-64 AC1, AC3, AC4)
-- -----------------------------------------------------------------------------
create function public.deactivate_venue(
    p_venue_id uuid,
    p_actor_id uuid,
    p_expected_version integer,
    p_reason public.venue_inactive_reason,
    p_note text,
    p_before jsonb,
    p_after jsonb,
    p_flag_reason text,
    p_message text
) returns table (outcome text, event_ids uuid[])
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_venue public.venues;
    v_events uuid[];
begin
    select * into v_venue from public.venues where id = p_venue_id for update;
    if not found then
        return query select 'venue_not_found'::text, '{}'::uuid[];
        return;
    end if;
    if not v_venue.is_active then
        return query select 'already_inactive'::text, '{}'::uuid[];
        return;
    end if;
    if v_venue.version <> p_expected_version then
        return query select 'stale'::text, '{}'::uuid[];
        return;
    end if;

    update public.venues
       set is_active = false,
           inactive_reason = p_reason,
           inactive_note = nullif(btrim(p_note), ''),
           updated_by = p_actor_id,
           version = version + 1
     where id = p_venue_id;

    insert into public.venue_edit_history (venue_id, actor_id, before, after)
    values (p_venue_id, p_actor_id, p_before, p_after);

    select coalesce(array_agg(f), '{}') into v_events
      from public.flag_venue_bookings(p_venue_id, tstzrange(now(), null), 'affected', p_flag_reason, p_message) f;

    return query select 'ok'::text, v_events;
end;
$$;

comment on function public.deactivate_venue(uuid, uuid, integer, public.venue_inactive_reason, text, jsonb, jsonb, text, text) is
    'SCRUM-64: marks the venue inactive with its reason, records the history row and flags its future held/approved bookings affected, in one transaction. Outcomes: ok, venue_not_found, already_inactive, stale. API-only.';

create function public.reactivate_venue(
    p_venue_id uuid,
    p_actor_id uuid,
    p_expected_version integer,
    p_before jsonb,
    p_after jsonb
) returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_venue public.venues;
begin
    select * into v_venue from public.venues where id = p_venue_id for update;
    if not found then return 'venue_not_found'; end if;
    if v_venue.is_active then return 'already_active'; end if;
    if v_venue.version <> p_expected_version then return 'stale'; end if;

    update public.venues
       set is_active = true,
           inactive_reason = null,
           inactive_note = null,
           updated_by = p_actor_id,
           version = version + 1
     where id = p_venue_id;

    insert into public.venue_edit_history (venue_id, actor_id, before, after)
    values (p_venue_id, p_actor_id, p_before, p_after);

    return 'ok';
end;
$$;

comment on function public.reactivate_venue(uuid, uuid, integer, jsonb, jsonb) is
    'SCRUM-64 AC4: makes the venue active again and records the history row. Booking flags are left for the coordinator. Outcomes: ok, venue_not_found, already_active, stale. API-only.';

revoke execute on function public.flag_venue_bookings(uuid, tstzrange, public.venue_booking_flag, text, text) from public, anon, authenticated;
grant execute on function public.flag_venue_bookings(uuid, tstzrange, public.venue_booking_flag, text, text) to service_role;
revoke execute on function public.deactivate_venue(uuid, uuid, integer, public.venue_inactive_reason, text, jsonb, jsonb, text, text) from public, anon, authenticated;
grant execute on function public.deactivate_venue(uuid, uuid, integer, public.venue_inactive_reason, text, jsonb, jsonb, text, text) to service_role;
revoke execute on function public.reactivate_venue(uuid, uuid, integer, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.reactivate_venue(uuid, uuid, integer, jsonb, jsonb) to service_role;

-- -----------------------------------------------------------------------------
-- request_venue_booking: an inactive venue takes no new requests (SCRUM-64 AC2)
-- -----------------------------------------------------------------------------
create or replace function public.request_venue_booking(
    p_event_id uuid, p_venue_id uuid, p_actor_id uuid, p_note text, p_notify_message text
) returns table (outcome text, booking_id uuid)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_booking_id uuid;
    v_venue_active boolean;
begin
    -- Lock the event so a concurrent status change can't slip between the
    -- checks and the insert.
    select * into v_event from public.events where id = p_event_id for update;
    if not found then
        return query select 'event_not_found'::text, null::uuid;
        return;
    end if;

    -- BR-R6 (QA-22): planning only. A returned event is still having its
    -- requirements amended, which gets its own message.
    if v_event.status = 'returned' then
        return query select 'returned'::text, null::uuid;
        return;
    end if;
    if v_event.status <> 'planning' then
        return query select 'not_planning'::text, null::uuid;
        return;
    end if;

    -- The API already checked this; re-checked under the lock in case the
    -- event was reassigned in between.
    if v_event.coordinator_id is distinct from p_actor_id then
        return query select 'not_assigned'::text, null::uuid;
        return;
    end if;

    -- Submission requires both times, so a planning event should always have
    -- them; without them the range below would be unbounded and overlap
    -- everything.
    if v_event.starts_at is null or v_event.ends_at is null then
        return query select 'no_period'::text, null::uuid;
        return;
    end if;

    -- SCRUM-64: a shared lock on the venue serialises this request against
    -- deactivate_venue's update lock. Either the request commits first and
    -- deactivation then flags its new hold, or deactivation commits first and
    -- this sees the venue inactive; never an unflagged hold at an inactive venue.
    select v.is_active into v_venue_active from public.venues v where v.id = p_venue_id for share;
    if not found then
        return query select 'venue_not_found'::text, null::uuid;
        return;
    end if;

    -- SCRUM-64 AC2: venue staff no longer receive requests for a venue they
    -- deactivated. Search already hides it; this covers a direct API call.
    if not v_venue_active then
        return query select 'venue_inactive'::text, null::uuid;
        return;
    end if;

    -- BR-R1: one venue per event. Checked before the insert because
    -- re-requesting the venue the event already holds would otherwise trip
    -- DB-1 and read as another event's hold. The event lock serialises
    -- requests for the same event; the unique index is the backstop.
    if exists (
        select 1
        from public.venue_bookings vb
        where vb.event_id = p_event_id
          and vb.status in ('held', 'approved', 're_review')
    ) then
        return query select 'already_booked'::text, null::uuid;
        return;
    end if;

    -- A block makes the venue unavailable (6.14) but isn't a booking, so DB-1
    -- can't see it. No lock needed: a block may overlap a hold anyway (CAL-R1).
    if exists (
        select 1
        from public.venue_blocks b
        where b.venue_id = p_venue_id
          and b.blocked_period && tstzrange(v_event.starts_at, v_event.ends_at, '[)')
    ) then
        return query select 'blocked'::text, null::uuid;
        return;
    end if;

    -- CR-99 AC5: a hold past its expiry no longer occupies the venue, even if
    -- the minute job hasn't reached it yet.
    perform public.expire_venue_holds(now());

    -- DB-1 (venue_bookings_no_overlap) is the authority on overlaps, so two
    -- coordinators racing for the same slot resolve first-come-first-served
    -- (QA2-23): the loser's insert waits on the winner's and then violates it.
    begin
        insert into public.venue_bookings (event_id, venue_id, occupied_period, status, request_note, requested_by)
        values (
            p_event_id,
            p_venue_id,
            tstzrange(v_event.starts_at, v_event.ends_at, '[)'),
            'held',
            nullif(btrim(p_note), ''),
            p_actor_id
        )
        returning id into v_booking_id;
    exception
        -- An exclusion constraint is checked after the row is inserted, so two
        -- truly simultaneous overlapping inserts can each wait on the other;
        -- Postgres then aborts one with a deadlock. Either way that request
        -- lost the race, and only this block's insert is rolled back.
        when exclusion_violation or deadlock_detected then
            return query select 'held_by_other'::text, null::uuid;
            return;
        when unique_violation then
            return query select 'already_booked'::text, null::uuid;
            return;
    end;

    -- Venue staff work as a pool (AUTH-R5), so every holder of the role is
    -- told, in this transaction (NT-R3). Held roles, not the active one: a
    -- notification grants no access. Never the actor (NT-R1), who may also
    -- hold venue_staff.
    insert into public.notifications (recipient_id, event_id, type, message)
    select ur.profile_id, p_event_id, 'venue_booking_requested', p_notify_message
    from public.user_roles ur
    where ur.role = 'venue_staff'
      and ur.profile_id <> p_actor_id;

    return query select 'ok'::text, v_booking_id;
end;
$$;

-- -----------------------------------------------------------------------------
-- safety_approve_event: a flagged booking is not ready (82 AC10, SCRUM-64)
-- -----------------------------------------------------------------------------
create or replace function public.safety_approve_event(
    p_event_id uuid, p_actor_id uuid, p_expected_version integer,
    p_comment text, p_organiser_message text, p_staff_message text
) returns setof public.events
language plpgsql security definer set search_path = '' as $$
declare v_after public.events;
begin
    -- Serialise decisions before inspecting arrangements. Lock booking rows too,
    -- so an existing booking cannot change while approval commits.
    perform 1 from public.events where id=p_event_id
        and version=p_expected_version and status='safety_review' for update;
    if not found then return; end if;
    perform 1 from public.venue_bookings where event_id=p_event_id order by id for update;
    if not exists (select 1 from public.venue_bookings where event_id=p_event_id and status in ('held','approved','re_review'))
       or exists (select 1 from public.venue_bookings where event_id=p_event_id and status in ('held','re_review'))
       -- SCRUM-64: a flagged arrangement needs follow-up before approval.
       or exists (select 1 from public.venue_bookings where event_id=p_event_id
                  and status in ('held','approved','re_review') and flag is not null) then
        return;
    end if;
    select * into v_after from public.transition_event(
        p_event_id,p_actor_id,array['safety_review'],'confirmed',p_expected_version,
        null,'event_safety_approved',p_organiser_message);
    if not found then return; end if;
    insert into public.event_safety_decisions(event_id,decision,comment,decided_by)
    values(p_event_id,'approved',btrim(p_comment),p_actor_id);
    -- Held roles are notification recipients, never an authorisation test.
    insert into public.notifications(recipient_id,event_id,type,message)
    select recipient,p_event_id,'event_safety_approved',p_staff_message from (
        select v_after.coordinator_id recipient
        union select ur.profile_id from public.user_roles ur where ur.role in ('venue_staff','tech_support')
    ) recipients
    where recipient is not null and recipient is distinct from p_actor_id
        and recipient is distinct from v_after.organiser_id;
    return next v_after;
end $$;

revoke execute on function public.request_venue_booking(uuid, uuid, uuid, text, text) from public, anon, authenticated;
grant execute on function public.request_venue_booking(uuid, uuid, uuid, text, text) to service_role;
revoke execute on function public.safety_approve_event(uuid,uuid,integer,text,text,text) from public,anon,authenticated;
grant execute on function public.safety_approve_event(uuid,uuid,integer,text,text,text) to service_role;
