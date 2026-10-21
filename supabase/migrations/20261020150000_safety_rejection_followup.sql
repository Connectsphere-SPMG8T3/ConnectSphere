-- D51/D53: keep a response note and allow CR-95 replacement after Safety rejection.
drop index public.venue_bookings_one_active_per_space;
create unique index venue_bookings_one_active_per_space
on public.venue_bookings(event_space_request_id)
where status in ('held','approved','re_review')
  and (flag is null or flag not in ('affected','safety_rejected'));

CREATE OR REPLACE FUNCTION public.request_venue_booking(p_event_id uuid, p_venue_id uuid, p_actor_id uuid, p_note text, p_notify_message text, p_replaces_booking_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(outcome text, booking_id uuid, conflict jsonb)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_replaced public.venue_bookings;
    v_event public.events;
    v_booking_id uuid;
    v_venue_active boolean;
    v_occupied tstzrange;
    v_booked tstzrange;
    v_setup integer;
    v_turnaround integer;
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
    select v.is_active, v.setup_minutes, v.turnaround_minutes
      into v_venue_active, v_setup, v_turnaround
      from public.venues v where v.id = p_venue_id for share;
    if not found then
        return query select 'venue_not_found'::text, null::uuid, null::jsonb;
        return;
    end if;
    if not v_venue_active then
        return query select 'venue_inactive'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- CR-95 AC4: a replacement names the event's own affected or Safety-rejected booking, which is
    -- still live; the lock stops it being released or restored under us.
    if p_replaces_booking_id is not null then
        select * into v_replaced from public.venue_bookings vb where vb.id = p_replaces_booking_id for update;
        if not found
           or v_replaced.event_id <> v_event.id
           or (v_replaced.flag is null or v_replaced.flag not in ('affected','safety_rejected'))
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

    -- CR-100: snapshot defaults under the venue lock, before checking clashes.
    v_booked := tstzrange(v_event.starts_at, v_event.ends_at, '[)');
    v_occupied := tstzrange(v_event.starts_at - make_interval(mins => v_setup),
                           v_event.ends_at + make_interval(mins => v_turnaround), '[)');
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
        insert into public.venue_bookings (event_id, venue_id, booked_period, setup_minutes, turnaround_minutes, status, request_note, requested_by, replaces_booking_id)
        values (p_event_id, p_venue_id, v_booked, v_setup, v_turnaround, 'held', nullif(btrim(p_note), ''), p_actor_id, p_replaces_booking_id)
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
$function$
;

CREATE OR REPLACE FUNCTION public.request_venue_booking_for_space(p_event_space_request_id uuid, p_venue_id uuid, p_actor_id uuid, p_note text, p_notify_message text, p_replaces_booking_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(outcome text, booking_id uuid, conflict jsonb)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
    v_booked tstzrange;
    v_setup integer;
    v_turnaround integer;
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
    select v.is_active, v.setup_minutes, v.turnaround_minutes
      into v_venue_active, v_setup, v_turnaround
      from public.venues v where v.id = p_venue_id for share;
    if not found then
        return query select 'venue_not_found'::text, null::uuid, null::jsonb;
        return;
    end if;
    if not v_venue_active then
        return query select 'venue_inactive'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- CR-95 AC4: a replacement names the event's own affected or Safety-rejected booking, which is
    -- still live; the lock stops it being released or restored under us.
    if p_replaces_booking_id is not null then
        select * into v_replaced from public.venue_bookings vb where vb.id = p_replaces_booking_id for update;
        if not found
           or v_replaced.event_id <> v_event.id
           or v_replaced.event_space_request_id is distinct from p_event_space_request_id
           or (v_replaced.flag is null or v_replaced.flag not in ('affected','safety_rejected'))
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

    -- CR-100: each space keeps its own window and a snapshot of venue defaults.
    v_booked := tstzrange(v_starts_at, v_ends_at, '[)');
    v_occupied := tstzrange(v_starts_at - make_interval(mins => v_setup),
                           v_ends_at + make_interval(mins => v_turnaround), '[)');
    v_conflict := private.first_venue_conflict(v_occupied, p_venue_id);
    if v_conflict is not null then
        return query select
            case when v_conflict ->> 'kind' = 'block' then 'blocked' else 'held_by_other' end,
            null::uuid, v_conflict;
        return;
    end if;

    begin
        insert into public.venue_bookings (
            event_id, event_space_request_id, venue_id, booked_period, setup_minutes, turnaround_minutes,
            status, request_note, requested_by, replaces_booking_id
        )
        values (
            v_event.id, p_event_space_request_id, p_venue_id, v_booked, v_setup, v_turnaround,
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
$function$
;

drop function public.mark_safety_revision(uuid,uuid);
CREATE OR REPLACE FUNCTION public.mark_safety_revision(p_booking_id uuid, p_actor_id uuid, p_note text)
 RETURNS text
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_booking public.venue_bookings;
    v_event public.events;
begin
    -- Event before booking, the same order as safety_return_event, so the two never deadlock.
    select * into v_event from public.events
    where id=(select event_id from public.venue_bookings where id=p_booking_id) for update;
    select * into v_booking from public.venue_bookings where id=p_booking_id for update;
    if not found then return 'booking_not_found'; end if;
    if v_booking.flag is distinct from 'safety_rejected' then return 'not_safety_rejected'; end if;
    if v_event.coordinator_id is distinct from p_actor_id then return 'not_assigned'; end if;
    if v_event.status <> 'planning' then return 'not_planning'; end if;
    if p_note is null or btrim(p_note) = '' then return 'note_required'; end if;
    if exists(select 1 from public.venue_bookings
              where replaces_booking_id=p_booking_id and status in ('held','approved','re_review')) then
        return 'replacement_pending';
    end if;
    update public.venue_bookings set flag=null, flag_reason=null, flagged_at=null where id=p_booking_id;
    insert into public.venue_booking_history(booking_id,actor_id,action,from_status,to_status,reason)
    values(p_booking_id,p_actor_id,'safety_revised',v_booking.status,v_booking.status,btrim(p_note));
    -- [Assumption] Revision has no notification and does not bump the event version.
    return 'ok';
end $function$
;

comment on function public.mark_safety_revision(uuid,uuid,text) is
'D53/D51: assigned coordinator revises a Safety-rejected booking with a note in Planning, unless a replacement is pending. API-only.';
revoke execute on function public.mark_safety_revision(uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.mark_safety_revision(uuid,uuid,text) to service_role;
comment on column public.venue_bookings.flag is
'Open follow-up: affected (CR-95/SCRUM-64), conflict or unsuitable (CR-94), safety_rejected (CR-104: cleared by Mark as revised or the booking released when its replacement is approved). First flag wins. A flagged booking is not ready for safety check. Other flags are set by flag_venue_bookings.';
