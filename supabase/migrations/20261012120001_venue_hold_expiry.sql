-- =============================================================================
-- ConnectSphere - CR-99 tentative venue holds expire (W7 CR-04)
--
-- Every hold carries an expiry (AC1). A BEFORE INSERT trigger sets the
-- default, so every path that writes a hold gets one without each insert
-- function repeating the rule.
-- =============================================================================

alter table public.venue_bookings
    add column expires_at timestamptz null,
    add column expiry_warned_at timestamptz null;

comment on column public.venue_bookings.expires_at is
    'When a held booking expires unless venue staff approve it first (CR-99). Kept on an approved booking as a record; only held bookings expire.';
comment on column public.venue_bookings.expiry_warned_at is
    'When the coordinator was warned the hold expires within 24 hours (CR-99 AC3). Cleared when the expiry changes, so the new expiry gets its own warning.';

-- The history of each booking: who changed it, when, and from what (CR-99
-- AC2; the approve, reject, cancel and replacement stories record here too).
-- actor_id is null for the system, i.e. the expiry job.
create table public.venue_booking_history (
    id uuid primary key default gen_random_uuid(),
    booking_id uuid not null references public.venue_bookings (id) on delete cascade,
    actor_id uuid null references public.profiles (id) on delete set null,
    action text not null,
    from_status public.venue_booking_status null,
    to_status public.venue_booking_status null,
    old_expires_at timestamptz null,
    new_expires_at timestamptz null,
    created_at timestamptz not null default now(),
    constraint venue_booking_history_action_not_blank check (length(btrim(action)) > 0)
);

comment on table public.venue_booking_history is
    'Append-only record of changes to a venue booking (CR-99). Written only by security-definer functions.';

create index venue_booking_history_booking_created_idx on public.venue_booking_history (booking_id, created_at desc);
create index venue_booking_history_actor_id_idx on public.venue_booking_history (actor_id);

alter table public.venue_booking_history enable row level security;

-- Safety net only: the API uses the secret key. Same readers as the bookings
-- themselves on the venue-staff and coordinator screens.
create policy "venue_booking_history_select_internal_staff"
    on public.venue_booking_history for select to authenticated
    using ((select private.current_user_role()) in ('event_coordinator', 'venue_staff'));

-- AC1: 7 days after the request, but never after the event starts.
-- [Assumption] REQUIREMENTS 9: an event under 7 days away is held until its
-- start. The event's start is the lower bound of the occupied period (BR-R7).
create or replace function private.set_hold_default_expiry()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if new.status = 'held' and new.expires_at is null then
        new.expires_at := least(now() + interval '7 days', lower(new.occupied_period));
    end if;
    return new;
end;
$$;

revoke execute on function private.set_hold_default_expiry() from public, anon, authenticated;

create trigger venue_bookings_set_hold_default_expiry
    before insert on public.venue_bookings
    for each row execute function private.set_hold_default_expiry();

-- Holds made before CR-99 get a fresh 7 days from now, not from their request,
-- so existing holds aren't all expired the minute the job first runs. A hold
-- whose event has already started still expires then, as any hold would.
update public.venue_bookings
set expires_at = least(now() + interval '7 days', lower(occupied_period))
where status = 'held' and expires_at is null;

alter table public.venue_bookings
    add constraint venue_bookings_hold_has_expiry check (status <> 'held' or expires_at is not null);

-- AC5: an unapproved hold becomes `expired` at its expiry, or when its event
-- starts if that is sooner (an event moved earlier keeps its old expiry).
-- `expired` is not an occupying status, so DB-1 frees the venue at once.
-- SKIP LOCKED leaves a hold that an approval has locked to the approval
-- (AC8): whichever takes the row lock first decides, and the other sees the
-- result. `p_now` is a parameter so checks can simulate the clock.
--
-- AC3: the assigned coordinator, and only them, is warned once when a hold
-- comes within 24 hours of expiry and told once when it expires. A hold that
-- starts out under 24 hours from expiry is warned on the next run.
create or replace function public.expire_venue_holds(p_now timestamptz default now())
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    with due as (
        select vb.id
        from public.venue_bookings vb
        join public.events e on e.id = vb.event_id
        where vb.status = 'held'
          and (vb.expires_at <= p_now or e.starts_at <= p_now)
        for update of vb skip locked
    ),
    expired as (
        update public.venue_bookings vb
        set status = 'expired'
        from due
        where vb.id = due.id
        returning vb.id, vb.event_id, vb.venue_id, vb.expires_at
    ),
    history as (
        insert into public.venue_booking_history
            (booking_id, actor_id, action, from_status, to_status, old_expires_at, new_expires_at, created_at)
        select x.id, null, 'expired', 'held', 'expired', x.expires_at, x.expires_at, p_now
        from expired x
    )
    insert into public.notifications (recipient_id, event_id, type, message)
    select e.coordinator_id, x.event_id, 'venue_hold_expired',
           format('Your hold on %s for "%s" has expired. You can request the venue again if it''s still free.',
                  v.name, e.name)
    from expired x
    join public.events e on e.id = x.event_id
    join public.venues v on v.id = x.venue_id
    where e.coordinator_id is not null;

    with due as (
        select vb.id
        from public.venue_bookings vb
        where vb.status = 'held'
          and vb.expiry_warned_at is null
          and vb.expires_at <= p_now + interval '24 hours'
        for update of vb skip locked
    ),
    warned as (
        update public.venue_bookings vb
        set expiry_warned_at = p_now
        from due
        where vb.id = due.id
        returning vb.event_id, vb.venue_id, vb.expires_at
    )
    insert into public.notifications (recipient_id, event_id, type, message)
    select e.coordinator_id, w.event_id, 'venue_hold_expiring',
           format('Your hold on %s for "%s" expires on %s unless Venue Staff approve it.',
                  v.name, e.name,
                  to_char(w.expires_at at time zone coalesce(e.event_timezone, 'Asia/Singapore'),
                          'FMDD Mon YYYY, HH24:MI'))
    from warned w
    join public.events e on e.id = w.event_id
    join public.venues v on v.id = w.venue_id
    where e.coordinator_id is not null;
end;
$$;

comment on function public.expire_venue_holds is
    'Expires every held booking past its expiry or its event start (CR-99). Run every minute by pg_cron; API-only otherwise.';

revoke execute on function public.expire_venue_holds(timestamptz) from public, anon, authenticated;
grant execute on function public.expire_venue_holds(timestamptz) to service_role;

-- AC2: venue staff change or extend a hold's expiry before it passes. The new
-- expiry must be after `p_now` and no later than the event start (AC1). Each
-- change is recorded, and the warning marker is cleared so the coordinator is
-- warned about the new expiry in turn (AC3). The row lock orders a change
-- against an approval or the job on the same hold. API-only: the API has
-- already checked the caller is venue staff.
create or replace function public.set_venue_hold_expiry(
    p_booking_id uuid,
    p_actor_id uuid,
    p_expires_at timestamptz,
    p_now timestamptz default now()
)
returns table (outcome text, expires_at timestamptz)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_booking public.venue_bookings;
    v_starts_at timestamptz;
begin
    select * into v_booking from public.venue_bookings vb where vb.id = p_booking_id for update;
    if not found then
        return query select 'booking_not_found'::text, null::timestamptz;
        return;
    end if;
    select e.starts_at into v_starts_at from public.events e where e.id = v_booking.event_id;

    -- Past its expiry already: it expires now rather than being revived.
    if v_booking.status = 'held' and (v_booking.expires_at <= p_now or v_starts_at <= p_now) then
        perform public.expire_venue_holds(p_now);
        v_booking.status := 'expired';
    end if;
    if v_booking.status = 'expired' then
        return query select 'hold_expired'::text, v_booking.expires_at;
        return;
    end if;
    if v_booking.status <> 'held' then
        return query select 'not_held'::text, v_booking.expires_at;
        return;
    end if;

    if p_expires_at <= p_now then
        return query select 'not_in_future'::text, v_booking.expires_at;
        return;
    end if;
    if p_expires_at > v_starts_at then
        return query select 'after_event_start'::text, v_booking.expires_at;
        return;
    end if;

    update public.venue_bookings vb
    set expires_at = p_expires_at, expiry_warned_at = null
    where vb.id = p_booking_id;

    insert into public.venue_booking_history
        (booking_id, actor_id, action, from_status, to_status, old_expires_at, new_expires_at, created_at)
    values (p_booking_id, p_actor_id, 'expiry_changed', 'held', 'held', v_booking.expires_at, p_expires_at, p_now);

    return query select 'ok'::text, p_expires_at;
end;
$$;

comment on function public.set_venue_hold_expiry is
    'Changes a held booking''s expiry (CR-99 AC2). Returns an outcome code instead of raising. API-only.';

revoke execute on function public.set_venue_hold_expiry(uuid, uuid, timestamptz, timestamptz) from public, anon, authenticated;
grant execute on function public.set_venue_hold_expiry(uuid, uuid, timestamptz, timestamptz) to service_role;

-- AC4, AC8: the guard an approval calls first, inside its own transaction.
-- It locks the hold, so the job (SKIP LOCKED) and a concurrent approval wait
-- or pass it by; whichever locks the row first decides. A hold at or past its
-- expiry, or whose event has started, is expired here and the approval is
-- refused with 'hold_expired', so only one outcome is ever saved. On 'ok' the
-- caller still holds the lock and sets the booking approved.
create or replace function public.lock_hold_for_approval(
    p_booking_id uuid,
    p_now timestamptz default now()
)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_booking public.venue_bookings;
    v_starts_at timestamptz;
begin
    select * into v_booking from public.venue_bookings vb where vb.id = p_booking_id for update;
    if not found then
        return 'booking_not_found';
    end if;
    select e.starts_at into v_starts_at from public.events e where e.id = v_booking.event_id;

    if v_booking.status = 'held' and (v_booking.expires_at <= p_now or v_starts_at <= p_now) then
        perform public.expire_venue_holds(p_now);
        return 'hold_expired';
    end if;
    if v_booking.status = 'expired' then
        return 'hold_expired';
    end if;
    if v_booking.status <> 'held' then
        return 'not_held';
    end if;
    return 'ok';
end;
$$;

comment on function public.lock_hold_for_approval is
    'Locks a held booking for approval, refusing one that has expired (CR-99 AC8). For SCRUM-36''s approve function. API-only.';

revoke execute on function public.lock_hold_for_approval(uuid, timestamptz) from public, anon, authenticated;
grant execute on function public.lock_hold_for_approval(uuid, timestamptz) to service_role;

-- AC5 to the second: a request first expires any hold already past its expiry,
-- so a slot the job hasn't reached yet isn't refused as held. Otherwise the
-- SCRUM-19 function unchanged.
create or replace function public.request_venue_booking(
    p_event_id uuid,
    p_venue_id uuid,
    p_actor_id uuid,
    p_note text,
    p_notify_message text
)
returns table (outcome text, booking_id uuid)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_booking_id uuid;
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

    if not exists (select 1 from public.venues v where v.id = p_venue_id) then
        return query select 'venue_not_found'::text, null::uuid;
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

comment on function public.request_venue_booking is
    'Requests a venue for a planning event: a held booking for the event''s period. Returns an outcome code instead of raising. API-only.';

revoke execute on function public.request_venue_booking(uuid, uuid, uuid, text, text) from public, anon, authenticated;
grant execute on function public.request_venue_booking(uuid, uuid, uuid, text, text) to service_role;

-- AC5 without anyone acting: the job runs every minute. [Team decision]
-- pg_cron, so the schedule lives in the database beside the data it changes
-- and needs no backend worker. cron.schedule replaces a job of the same name.
create extension if not exists pg_cron with schema pg_catalog;

select cron.schedule('expire-venue-holds', '* * * * *', 'select public.expire_venue_holds()');
