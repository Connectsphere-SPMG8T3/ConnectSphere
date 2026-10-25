alter type public.event_status add value if not exists 'preparation' after 'confirmed';

alter table public.events
    add column re_registration_allowed boolean not null default true,
    add column waitlist_enabled boolean not null default true;

create table public.event_registrations (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null references public.events (id) on delete cascade,
    attendee_id uuid not null references public.profiles (id) on delete restrict,
    status text not null default 'registered'
        check (status in ('registered', 'withdrawn', 'cancelled')),
    registered_at timestamptz not null default timezone('utc'::text, now()),
    withdrawn_at timestamptz null,
    constraint event_registrations_withdrawal_state check (
        (status = 'withdrawn' and withdrawn_at is not null)
        or (status <> 'withdrawn' and withdrawn_at is null)
    )
);

create unique index event_registrations_active_attendee_idx
    on public.event_registrations (event_id, attendee_id)
    where status = 'registered';
create index event_registrations_event_status_idx
    on public.event_registrations (event_id, status);

alter table public.event_registrations enable row level security;

create policy "attendees_read_own_event_registrations"
    on public.event_registrations for select to authenticated
    using (
        private.current_user_role() = 'attendee'
        and attendee_id = (select auth.uid())
    );

create function public.register_for_event(p_event_id uuid, p_attendee_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events%rowtype;
    v_existing public.event_registrations%rowtype;
    v_primary_capacity integer;
    v_venue_capacity integer;
    v_capacity integer;
    v_registered_count integer;
begin
    select * into v_event
    from public.events
    where id = p_event_id
    for update;

    if not found or v_event.status not in ('confirmed', 'preparation') then
        return jsonb_build_object('outcome', 'unavailable');
    end if;

    select * into v_existing
    from public.event_registrations
    where event_id = p_event_id and attendee_id = p_attendee_id
    order by registered_at desc
    limit 1;

    if v_existing.status = 'registered' then
        return jsonb_build_object('outcome', 'already_registered', 'registration_id', v_existing.id);
    end if;
    if v_existing.status = 'withdrawn' and not v_event.re_registration_allowed then
        return jsonb_build_object('outcome', 'reregistration_disabled');
    end if;

    if not v_event.registration_enabled or v_event.registration_opens_at is null
       or now() < v_event.registration_opens_at then
        return jsonb_build_object('outcome', 'not_open');
    end if;
    if v_event.registration_closes_at is not null and now() >= v_event.registration_closes_at then
        return jsonb_build_object('outcome', 'closed');
    end if;

    select venue.capacity into v_primary_capacity
    from public.event_space_requests as space
    join public.venue_bookings as booking
      on booking.event_space_request_id = space.id and booking.status = 'approved'
    join public.venues as venue on venue.id = booking.venue_id
    where space.event_id = p_event_id and space.is_primary
    order by space.created_at, space.id
    limit 1;

    if v_primary_capacity is null then
        select min(venue.capacity) into v_venue_capacity
        from public.event_space_requests as space
        join public.venue_bookings as booking
          on booking.event_space_request_id = space.id and booking.status = 'approved'
        join public.venues as venue on venue.id = booking.venue_id
        where space.event_id = p_event_id;
    else
        v_venue_capacity := v_primary_capacity;
    end if;

    select min(capacity) into v_capacity
    from unnest(array[v_event.registration_capacity, v_venue_capacity]) as capacities(capacity)
    where capacity is not null;

    select count(*) into v_registered_count
    from public.event_registrations
    where event_id = p_event_id and status = 'registered';

    if v_capacity is not null and v_registered_count >= v_capacity then
        return jsonb_build_object('outcome', 'full');
    end if;

    if v_existing.id is not null then
        update public.event_registrations
        set status = 'registered', registered_at = now(), withdrawn_at = null
        where id = v_existing.id
        returning * into v_existing;
    else
        insert into public.event_registrations (event_id, attendee_id)
        values (p_event_id, p_attendee_id)
        returning * into v_existing;
    end if;

    return jsonb_build_object(
        'outcome', 'registered',
        'registration_id', v_existing.id,
        'registered_at', v_existing.registered_at
    );
end;
$$;

revoke all on function public.register_for_event(uuid, uuid) from public, anon, authenticated;
grant execute on function public.register_for_event(uuid, uuid) to service_role;

comment on function public.register_for_event(uuid, uuid) is
    'Registers an active Attendee under an event-row lock so final-place races cannot exceed effective capacity. Story 43; waitlisting is handled separately.';