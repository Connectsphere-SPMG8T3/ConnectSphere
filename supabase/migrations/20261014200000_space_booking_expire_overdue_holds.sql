create or replace function public.request_venue_booking_for_space(
    p_event_space_request_id uuid,
    p_venue_id uuid,
    p_actor_id uuid,
    p_note text,
    p_notify_message text
)
returns table(outcome text, booking_id uuid)
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
begin
    select es.* into v_space
    from public.event_space_requests es
    where es.id = p_event_space_request_id
    for update;
    if not found then
        return query select 'event_not_found'::text, null::uuid;
        return;
    end if;

    select e.* into v_event
    from public.events e
    where e.id = v_space.event_id
    for update;
    if not found then
        return query select 'event_not_found'::text, null::uuid;
        return;
    end if;

    if v_event.status = 'returned' then
        return query select 'returned'::text, null::uuid;
        return;
    end if;
    if v_event.status <> 'planning' then
        return query select 'not_planning'::text, null::uuid;
        return;
    end if;
    if v_event.coordinator_id is distinct from p_actor_id then
        return query select 'not_assigned'::text, null::uuid;
        return;
    end if;
    v_starts_at := coalesce(v_space.starts_at, v_event.starts_at);
    v_ends_at := coalesce(v_space.ends_at, v_event.ends_at);
    if v_starts_at is null or v_ends_at is null then
        return query select 'no_period'::text, null::uuid;
        return;
    end if;
    if not exists (select 1 from public.venues v where v.id = p_venue_id) then
        return query select 'venue_not_found'::text, null::uuid;
        return;
    end if;

    perform public.expire_venue_holds(now());

    if exists (
        select 1 from public.venue_bookings vb
        where vb.event_space_request_id = p_event_space_request_id
          and vb.status in ('held', 'approved', 're_review')
    ) then
        return query select 'already_booked'::text, null::uuid;
        return;
    end if;
    if exists (
        select 1 from public.venue_blocks b
        where b.venue_id = p_venue_id
          and b.blocked_period && tstzrange(v_starts_at, v_ends_at, '[)')
    ) then
        return query select 'blocked'::text, null::uuid;
        return;
    end if;

    begin
        insert into public.venue_bookings (
            event_id, event_space_request_id, venue_id, occupied_period,
            status, request_note, requested_by
        )
        values (
            v_event.id, p_event_space_request_id, p_venue_id,
            tstzrange(v_starts_at, v_ends_at, '[)'),
            'held', nullif(btrim(p_note), ''), p_actor_id
        )
        returning id into v_booking_id;
    exception
        when exclusion_violation or deadlock_detected then
            return query select 'held_by_other'::text, null::uuid;
            return;
        when unique_violation then
            return query select 'already_booked'::text, null::uuid;
            return;
    end;

    insert into public.notifications (recipient_id, event_id, type, message)
    select ur.profile_id, v_event.id, 'venue_booking_requested', p_notify_message
    from public.user_roles ur
    where ur.role = 'venue_staff'
      and ur.profile_id <> p_actor_id;

    return query select 'ok'::text, v_booking_id;
end;
$$;

comment on function public.request_venue_booking_for_space is
    'Requests a venue for one event space using its effective period; expires overdue holds before checking active bookings and overlaps.';

revoke execute on function public.request_venue_booking_for_space(uuid, uuid, uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.request_venue_booking_for_space(uuid, uuid, uuid, text, text)
    to service_role;