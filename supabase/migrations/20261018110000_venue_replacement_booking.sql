-- =============================================================================
-- ConnectSphere - CR-95 AC4 request a replacement for an affected booking
--
-- A booking flagged Affected (a venue block or deactivation, CR-95/SCRUM-64) is
-- never cancelled or removed. The coordinator requests a replacement venue,
-- which goes through the full request and approval process (QA3-30) and is
-- linked to the booking it replaces (replaces_booking_id), so approving it can
-- release the original (AC5).
--
-- Both request functions take the booking being replaced. Only the event's own
-- affected, still-live booking can be named, and then it no longer counts as
-- the event's venue, so the replacement sits beside it until it is released.
-- A request with no link is still refused while the event has a venue. The
-- functions only accept an event in planning: the caller returns a Confirmed
-- or Safety-review event to planning first (AC7).
-- =============================================================================

alter table public.venue_bookings
    add column replaces_booking_id uuid null references public.venue_bookings (id) on delete set null,
    add constraint venue_bookings_replaces_not_self check (replaces_booking_id is distinct from id);

comment on column public.venue_bookings.replaces_booking_id is
    'The affected booking this one replaces (CR-95 AC4). Approving this booking releases that one (AC5).';

create index venue_bookings_replaces_booking_id_idx on public.venue_bookings (replaces_booking_id);

-- An affected booking is waiting to be replaced, so it no longer holds the
-- space's single active slot. Its replacement takes it; two replacements still
-- cannot coexist, because the replacement itself is unflagged.
drop index public.venue_bookings_one_active_per_space;
create unique index venue_bookings_one_active_per_space
    on public.venue_bookings (event_space_request_id)
    where status in ('held', 'approved', 're_review') and flag is distinct from 'affected';

drop function public.request_venue_booking(uuid, uuid, uuid, text, text);
drop function public.request_venue_booking_for_space(uuid, uuid, uuid, text, text);

create function public.request_venue_booking(p_event_id uuid, p_venue_id uuid, p_actor_id uuid, p_note text, p_notify_message text, p_replaces_booking_id uuid default null)
 RETURNS TABLE(outcome text, booking_id uuid, conflict jsonb)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $$
declare
    v_replaced public.venue_bookings;
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

    -- CR-95 AC4: a replacement names the event's own affected booking, which is
    -- still live; the lock stops it being released or restored under us.
    if p_replaces_booking_id is not null then
        select * into v_replaced from public.venue_bookings vb where vb.id = p_replaces_booking_id for update;
        if not found
           or v_replaced.event_id <> v_event.id
           or v_replaced.flag is distinct from 'affected'
           or v_replaced.status not in ('held', 'approved') then
            return query select 'replaced_booking_invalid'::text, null::uuid, null::jsonb;
            return;
        end if;
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
          and (p_replaces_booking_id is null or vb.id <> p_replaces_booking_id)
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
        insert into public.venue_bookings (event_id, venue_id, booked_period, status, request_note, requested_by, replaces_booking_id)
        values (p_event_id, p_venue_id, v_occupied, 'held', nullif(btrim(p_note), ''), p_actor_id, p_replaces_booking_id)
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

create function public.request_venue_booking_for_space(p_event_space_request_id uuid, p_venue_id uuid, p_actor_id uuid, p_note text, p_notify_message text, p_replaces_booking_id uuid default null)
 RETURNS TABLE(outcome text, booking_id uuid, conflict jsonb)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $$
declare
    v_replaced public.venue_bookings;
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

    -- CR-95 AC4: a replacement names the event's own affected booking, which is
    -- still live; the lock stops it being released or restored under us.
    if p_replaces_booking_id is not null then
        select * into v_replaced from public.venue_bookings vb where vb.id = p_replaces_booking_id for update;
        if not found
           or v_replaced.event_id <> v_event.id
           or v_replaced.event_space_request_id is distinct from p_event_space_request_id
           or v_replaced.flag is distinct from 'affected'
           or v_replaced.status not in ('held', 'approved') then
            return query select 'replaced_booking_invalid'::text, null::uuid, null::jsonb;
            return;
        end if;
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
          and (p_replaces_booking_id is null or vb.id <> p_replaces_booking_id)
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
            status, request_note, requested_by, replaces_booking_id
        )
        values (
            v_event.id, p_event_space_request_id, p_venue_id, v_occupied,
            'held', nullif(btrim(p_note), ''), p_actor_id, p_replaces_booking_id
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

comment on function public.request_venue_booking is
    'Holds a venue for a planning event (SCRUM-19). Refuses on the occupied window with the clash named in `conflict` (SCRUM-21), an inactive venue (SCRUM-64) and a second venue for the event. With p_replaces_booking_id it replaces that affected booking (CR-95 AC4). API-only.';
comment on function public.request_venue_booking_for_space is
    'Requests a venue for one event space using its effective period (CR-97). Refuses on the occupied window (SCRUM-21), an inactive venue (D33) and a venue that cannot seat the space''s expected pax. With p_replaces_booking_id it replaces that space''s affected booking (CR-95 AC4). API-only.';

revoke execute on function public.request_venue_booking(uuid, uuid, uuid, text, text, uuid)
    from public, anon, authenticated;
grant execute on function public.request_venue_booking(uuid, uuid, uuid, text, text, uuid)
    to service_role;
revoke execute on function public.request_venue_booking_for_space(uuid, uuid, uuid, text, text, uuid)
    from public, anon, authenticated;
grant execute on function public.request_venue_booking_for_space(uuid, uuid, uuid, text, text, uuid)
    to service_role;
