-- =============================================================================
-- ConnectSphere - SCRUM-21 booking conflict detection (W7 CR-01, REQUIREMENTS §6.14)
--
-- A booking now keeps its own time (`booked_period`) apart from the time it
-- occupies the venue (`occupied_period`): from the start of its setup to the
-- end of its turnaround (AC1, QA3-5). Each booking carries its own setup and
-- turnaround minutes (QA3-23); CR-100 copies a venue's defaults into them and
-- 36 AC5 lets Venue Staff adjust a held booking. Until then they are 0.
-- DB-1 (venue_bookings_no_overlap) is unchanged and still decides races, now
-- on the buffered window.
-- =============================================================================

alter table public.venue_bookings
    add column booked_period tstzrange null,
    add column setup_minutes integer not null default 0,
    add column turnaround_minutes integer not null default 0,
    add constraint venue_bookings_setup_not_negative check (setup_minutes >= 0),
    add constraint venue_bookings_turnaround_not_negative check (turnaround_minutes >= 0);

comment on column public.venue_bookings.booked_period is
    'The booking''s own time: its space''s window, or the event''s (CR-97). What screens show and what hold expiry counts to (SCRUM-21).';
comment on column public.venue_bookings.setup_minutes is
    'Setup before booked_period during which the venue is occupied (SCRUM-21 AC1). Per booking, never the venue''s current figure (QA3-23).';
comment on column public.venue_bookings.turnaround_minutes is
    'Turnaround after booked_period during which the venue is occupied (SCRUM-21 AC1). Per booking (QA3-23).';
comment on column public.venue_bookings.occupied_period is
    'Derived: booked_period widened by setup_minutes and turnaround_minutes. Maintained by a trigger; DB-1 excludes overlaps on it (SCRUM-21).';

-- Every booking so far was written with zero setup and turnaround, so its
-- occupied period is its own time.
update public.venue_bookings set booked_period = occupied_period;

alter table public.venue_bookings
    alter column booked_period set not null,
    add constraint venue_bookings_booked_period_is_bounded_half_open check (
        not isempty(booked_period)
        and lower_inc(booked_period)
        and not upper_inc(booked_period)
        and not lower_inf(booked_period)
        and not upper_inf(booked_period)
    );

-- A stored column, kept by a trigger: Postgres can't compute the window in the
-- exclusion constraint itself, because timestamptz +/- interval isn't
-- immutable. An insert that only names occupied_period (written before
-- SCRUM-21) is taken as the booking's own time.
create or replace function private.derive_occupied_period()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if tg_op = 'INSERT' and new.booked_period is null then
        new.booked_period := new.occupied_period;
    end if;
    new.occupied_period := tstzrange(
        lower(new.booked_period) - make_interval(mins => new.setup_minutes),
        upper(new.booked_period) + make_interval(mins => new.turnaround_minutes),
        '[)'
    );
    return new;
end;
$$;

revoke execute on function private.derive_occupied_period() from public, anon, authenticated;

-- Named to fire before venue_bookings_set_hold_default_expiry (triggers run in
-- name order), which reads booked_period.
create trigger venue_bookings_derive_occupied_period
    before insert or update of booked_period, setup_minutes, turnaround_minutes, occupied_period
    on public.venue_bookings
    for each row execute function private.derive_occupied_period();

-- CR-99 AC1: a hold expires 7 days after the request, or when its event
-- starts if sooner. The event starts at the booking's own time, not at the
-- start of its setup.
create or replace function private.set_hold_default_expiry()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if new.status = 'held' and new.expires_at is null then
        new.expires_at := least(now() + interval '7 days', lower(new.booked_period));
    end if;
    return new;
end;
$$;

revoke execute on function private.set_hold_default_expiry() from public, anon, authenticated;

-- -----------------------------------------------------------------------------
-- The single conflict check (AC4). Every booking path asks it which bookings
-- and blocks clash with an occupied window: requests, venue search, and, as
-- they land, approval (36), re-review after a date change (37) and blocking
-- (51). DB-1 stays the guarantee against races; this names what is in the way.
--   p_period             the candidate's occupied window (setup to turnaround)
--   p_venue_id           one venue, or null for every venue (search)
--   p_exclude_booking_id a booking being re-checked, which never clashes with itself
-- Occupying: held (unless past its expiry, CR-99 AC5), approved and re_review
-- (AC2, AC5). Windows that only touch don't clash (AC3); other venues never
-- clash (AC7). API-only: it returns other events' names.
-- -----------------------------------------------------------------------------
create or replace function public.venue_conflicts(
    p_period tstzrange,
    p_venue_id uuid default null,
    p_exclude_booking_id uuid default null
)
returns table (
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
      and (p_venue_id is null or b.venue_id = p_venue_id)
    order by 8, 1;
$$;

comment on function public.venue_conflicts(tstzrange, uuid, uuid) is
    'SCRUM-21: the bookings and blocks that clash with an occupied window, at one venue or all. The single conflict check every booking path uses. API-only.';

revoke execute on function public.venue_conflicts(tstzrange, uuid, uuid) from public, anon, authenticated;
grant execute on function public.venue_conflicts(tstzrange, uuid, uuid) to service_role;

-- The first clash with an occupied window, as the request functions report it
-- (AC2): a block first, since it refuses whatever else is booked, then the
-- earliest booking. The event's name and the occupied window only; nothing
-- else about another coordinator's event. Null when nothing clashes.
create or replace function private.first_venue_conflict(p_period tstzrange, p_venue_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    select jsonb_build_object(
        'kind', c.kind,
        'event_name', c.event_name,
        'block_reason', c.block_reason,
        'starts_at', lower(c.occupied_period),
        'ends_at', upper(c.occupied_period)
    )
    from public.venue_conflicts(p_period, p_venue_id) c
    order by c.kind = 'block' desc, lower(c.occupied_period)
    limit 1;
$$;

revoke execute on function private.first_venue_conflict(tstzrange, uuid) from public, anon, authenticated;

-- -----------------------------------------------------------------------------
-- request_venue_booking: the event-scoped path, now refusing on the occupied
-- window with the clash named (AC2, AC4). The return type gains `conflict`,
-- so the function is dropped and recreated.
-- -----------------------------------------------------------------------------
drop function public.request_venue_booking(uuid, uuid, uuid, text, text);

create function public.request_venue_booking(
    p_event_id uuid, p_venue_id uuid, p_actor_id uuid, p_note text, p_notify_message text
) returns table (outcome text, booking_id uuid, conflict jsonb)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_booking_id uuid;
    v_venue_active boolean;
    v_occupied tstzrange;
    v_conflict jsonb;
begin
    -- Lock the event so a concurrent status change can't slip between the
    -- checks and the insert.
    select * into v_event from public.events where id = p_event_id for update;
    if not found then
        return query select 'event_not_found'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- BR-R6 (QA-22): planning only. A returned event is still having its
    -- requirements amended, which gets its own message.
    if v_event.status = 'returned' then
        return query select 'returned'::text, null::uuid, null::jsonb;
        return;
    end if;
    if v_event.status <> 'planning' then
        return query select 'not_planning'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- The API already checked this; re-checked under the lock in case the
    -- event was reassigned in between.
    if v_event.coordinator_id is distinct from p_actor_id then
        return query select 'not_assigned'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- Submission requires both times, so a planning event should always have
    -- them; without them the range below would be unbounded and overlap
    -- everything.
    if v_event.starts_at is null or v_event.ends_at is null then
        return query select 'no_period'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- SCRUM-64: a shared lock on the venue serialises this request against
    -- deactivate_venue's update lock, so there is never an unflagged hold at
    -- an inactive venue.
    select v.is_active into v_venue_active from public.venues v where v.id = p_venue_id for share;
    if not found then
        return query select 'venue_not_found'::text, null::uuid, null::jsonb;
        return;
    end if;
    if not v_venue_active then
        return query select 'venue_inactive'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- BR-R1: one venue per event. Checked before the insert because
    -- re-requesting the venue the event already holds would otherwise read as
    -- another event's hold. The event lock serialises requests for the same
    -- event; the unique index is the backstop.
    if exists (
        select 1
        from public.venue_bookings vb
        where vb.event_id = p_event_id
          and vb.status in ('held', 'approved', 're_review')
    ) then
        return query select 'already_booked'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- CR-99 AC5: expire overdue holds first, so DB-1 no longer counts them.
    perform public.expire_venue_holds(now());

    -- A new booking starts with zero setup and turnaround (CR-100 adds the
    -- venue's defaults), so it occupies its own time.
    v_occupied := tstzrange(v_event.starts_at, v_event.ends_at, '[)');
    v_conflict := private.first_venue_conflict(v_occupied, p_venue_id);
    if v_conflict is not null then
        return query select
            case when v_conflict ->> 'kind' = 'block' then 'blocked' else 'held_by_other' end,
            null::uuid, v_conflict;
        return;
    end if;

    -- DB-1 (venue_bookings_no_overlap) is the authority on overlaps, so two
    -- coordinators racing for the same slot resolve first-come-first-served
    -- (QA2-23): the loser's insert waits on the winner's and then violates it.
    begin
        insert into public.venue_bookings (event_id, venue_id, booked_period, status, request_note, requested_by)
        values (p_event_id, p_venue_id, v_occupied, 'held', nullif(btrim(p_note), ''), p_actor_id)
        returning id into v_booking_id;
    exception
        -- Two truly simultaneous overlapping inserts can each wait on the
        -- other; Postgres then aborts one with a deadlock. Either way this
        -- request lost; the winner is named if it is visible by now.
        when exclusion_violation or deadlock_detected then
            return query select 'held_by_other'::text, null::uuid,
                private.first_venue_conflict(v_occupied, p_venue_id);
            return;
        when unique_violation then
            return query select 'already_booked'::text, null::uuid, null::jsonb;
            return;
    end;

    -- Venue staff work as a pool (AUTH-R5), so every holder of the role is
    -- told, in this transaction (NT-R3). Never the actor (NT-R1).
    insert into public.notifications (recipient_id, event_id, type, message)
    select ur.profile_id, p_event_id, 'venue_booking_requested', p_notify_message
    from public.user_roles ur
    where ur.role = 'venue_staff'
      and ur.profile_id <> p_actor_id;

    return query select 'ok'::text, v_booking_id, null::jsonb;
end;
$$;

comment on function public.request_venue_booking is
    'Holds a venue for a planning event (SCRUM-19). Refuses on the occupied window with the clash named in `conflict` (SCRUM-21), an inactive venue (SCRUM-64) and a second venue for the event. API-only.';

revoke execute on function public.request_venue_booking(uuid, uuid, uuid, text, text) from public, anon, authenticated;
grant execute on function public.request_venue_booking(uuid, uuid, uuid, text, text) to service_role;

-- -----------------------------------------------------------------------------
-- request_venue_booking_for_space: the per-space path (CR-97), refusing on the
-- occupied window with the clash named (AC2, AC6), and an inactive venue (D33).
-- -----------------------------------------------------------------------------
drop function public.request_venue_booking_for_space(uuid, uuid, uuid, text, text);

create function public.request_venue_booking_for_space(
    p_event_space_request_id uuid,
    p_venue_id uuid,
    p_actor_id uuid,
    p_note text,
    p_notify_message text
)
returns table (outcome text, booking_id uuid, conflict jsonb)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_space public.event_space_requests;
    v_event public.events;
    v_starts_at timestamptz;
    v_ends_at timestamptz;
    v_booking_id uuid;
    v_capacity integer;
    v_venue_active boolean;
    v_occupied tstzrange;
    v_conflict jsonb;
begin
    select es.* into v_space
    from public.event_space_requests es
    where es.id = p_event_space_request_id
    for update;
    if not found then
        return query select 'event_not_found'::text, null::uuid, null::jsonb;
        return;
    end if;

    select e.* into v_event
    from public.events e
    where e.id = v_space.event_id
    for update;
    if not found then
        return query select 'event_not_found'::text, null::uuid, null::jsonb;
        return;
    end if;

    if v_event.status = 'returned' then
        return query select 'returned'::text, null::uuid, null::jsonb;
        return;
    end if;
    if v_event.status <> 'planning' then
        return query select 'not_planning'::text, null::uuid, null::jsonb;
        return;
    end if;
    if v_event.coordinator_id is distinct from p_actor_id then
        return query select 'not_assigned'::text, null::uuid, null::jsonb;
        return;
    end if;
    v_starts_at := coalesce(v_space.starts_at, v_event.starts_at);
    v_ends_at := coalesce(v_space.ends_at, v_event.ends_at);
    if v_starts_at is null or v_ends_at is null then
        return query select 'no_period'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- D33 / SCRUM-64 AC2: the same shared lock and refusal as the event path,
    -- so a request can't race a deactivation into an unflagged hold.
    select v.is_active into v_venue_active from public.venues v where v.id = p_venue_id for share;
    if not found then
        return query select 'venue_not_found'::text, null::uuid, null::jsonb;
        return;
    end if;
    if not v_venue_active then
        return query select 'venue_inactive'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- CR-97 AC10: the venue must seat the space's expected pax. The venue's
    -- figure for the space's layout wins when it has one (venue search's
    -- effective capacity); a space with no expected pax is not checked.
    if v_space.expected_pax is not null then
        select coalesce(
            (select l.capacity_for_layout from public.venue_layouts l
             where l.venue_id = p_venue_id and l.layout = v_space.layout_preference),
            v.capacity
        ) into v_capacity
        from public.venues v
        where v.id = p_venue_id;
        if v_capacity is not null and v_space.expected_pax > v_capacity then
            return query select 'over_capacity'::text, null::uuid, null::jsonb;
            return;
        end if;
    end if;

    perform public.expire_venue_holds(now());

    if exists (
        select 1 from public.venue_bookings vb
        where vb.event_space_request_id = p_event_space_request_id
          and vb.status in ('held', 'approved', 're_review')
    ) then
        return query select 'already_booked'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- AC6: each space is checked on its own window. A new booking starts with
    -- zero setup and turnaround, so it occupies its own time.
    v_occupied := tstzrange(v_starts_at, v_ends_at, '[)');
    v_conflict := private.first_venue_conflict(v_occupied, p_venue_id);
    if v_conflict is not null then
        return query select
            case when v_conflict ->> 'kind' = 'block' then 'blocked' else 'held_by_other' end,
            null::uuid, v_conflict;
        return;
    end if;

    begin
        insert into public.venue_bookings (
            event_id, event_space_request_id, venue_id, booked_period,
            status, request_note, requested_by
        )
        values (
            v_event.id, p_event_space_request_id, p_venue_id, v_occupied,
            'held', nullif(btrim(p_note), ''), p_actor_id
        )
        returning id into v_booking_id;
    exception
        when exclusion_violation or deadlock_detected then
            return query select 'held_by_other'::text, null::uuid,
                private.first_venue_conflict(v_occupied, p_venue_id);
            return;
        when unique_violation then
            return query select 'already_booked'::text, null::uuid, null::jsonb;
            return;
    end;

    insert into public.notifications (recipient_id, event_id, type, message)
    select ur.profile_id, v_event.id, 'venue_booking_requested', p_notify_message
    from public.user_roles ur
    where ur.role = 'venue_staff'
      and ur.profile_id <> p_actor_id;

    return query select 'ok'::text, v_booking_id, null::jsonb;
end;
$$;

comment on function public.request_venue_booking_for_space is
    'Requests a venue for one event space using its effective period (CR-97). Refuses on the occupied window with the clash named in `conflict` (SCRUM-21), an inactive venue (D33), and a venue that cannot seat the space''s expected pax. API-only.';

revoke execute on function public.request_venue_booking_for_space(uuid, uuid, uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.request_venue_booking_for_space(uuid, uuid, uuid, text, text)
    to service_role;
