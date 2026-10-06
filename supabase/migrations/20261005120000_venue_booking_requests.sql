-- =============================================================================
-- ConnectSphere - SCRUM-19 venue booking request and tentative hold
--
-- A coordinator's booking request is a `held` venue_bookings row for the
-- event's own [starts_at, ends_at) (REQUIREMENTS 6.12; QA-6). The period is
-- never taken from the client. request_venue_booking writes the hold in one
-- transaction. API-only (ADR-0002): the API checks role and relationship
-- before calling, and the function re-checks under the event lock.
-- =============================================================================

alter table public.venue_bookings
    add column request_note text null,
    add column requested_by uuid null,
    add constraint venue_bookings_requested_by_fkey
        foreign key (requested_by) references public.profiles (id) on delete set null,
    -- [Assumption] REQUIREMENTS 9: the note is capped like the other free-text fields.
    add constraint venue_bookings_request_note_length
        check (request_note is null or length(btrim(request_note)) between 1 and 1000);

create index venue_bookings_requested_by_idx on public.venue_bookings (requested_by);

comment on column public.venue_bookings.request_note is
    'Optional note from the coordinator to venue staff, written with the request (SCRUM-19).';
comment on column public.venue_bookings.requested_by is
    'The coordinator who requested the booking (SCRUM-19).';

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
