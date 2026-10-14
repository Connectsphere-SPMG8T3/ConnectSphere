-- ConnectSphere - CR-98 flexible event-space requests
-- Organiser requirements are separate from coordinator venue allocations.

create table public.event_space_requests (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null references public.events (id) on delete cascade,
    label varchar(150) not null,
    expected_pax integer null,
    layout_preference public.venue_layout null,
    facilities_required public.facility[] not null default '{}',
    starts_at timestamptz null,
    ends_at timestamptz null,
    version integer not null default 1,
    created_at timestamptz not null default timezone('utc'::text, now()),
    updated_at timestamptz not null default timezone('utc'::text, now()),
    constraint event_space_requests_label_not_blank check (length(btrim(label)) > 0),
    constraint event_space_requests_pax_positive check (expected_pax is null or expected_pax >= 1),
    constraint event_space_requests_time_bounds check (
        (starts_at is null and ends_at is null)
        or (starts_at is not null and ends_at is not null and ends_at > starts_at)
    ),
    constraint event_space_requests_version_positive check (version >= 1)
);

comment on table public.event_space_requests is
    'Organiser-proposed space requirements. A coordinator''s venue booking is the operational allocation.';
comment on column public.event_space_requests.starts_at is
    'Requested period for this space; initially copied from the event, but independently changeable.';
comment on column public.event_space_requests.ends_at is
    'Requested period for this space; the booking copies this period into occupied_period.';

create index event_space_requests_event_id_idx on public.event_space_requests (event_id);
create index event_space_requests_event_created_idx on public.event_space_requests (event_id, created_at);
create trigger event_space_requests_set_updated_at
    before update on public.event_space_requests
    for each row execute function public.set_updated_at();

alter table public.event_space_requests enable row level security;

create policy "event_space_requests_select_owner_or_internal_staff"
    on public.event_space_requests for select to authenticated
    using (
        exists (
            select 1 from public.events e
            where e.id = event_space_requests.event_id
              and (
                  e.organiser_id = (select auth.uid())
                  or (
                      e.status <> 'draft'
                      and (select private.current_user_role()) in (
                          'event_coordinator', 'venue_staff', 'tech_support'
                      )
                  )
              )
        )
    );

create policy "event_space_requests_insert_owner_draft_or_returned"
    on public.event_space_requests for insert to authenticated
    with check (
        exists (
            select 1 from public.events e
            where e.id = event_space_requests.event_id
              and e.organiser_id = (select auth.uid())
              and e.status in ('draft', 'returned')
        )
    );

create policy "event_space_requests_update_owner_draft_or_returned"
    on public.event_space_requests for update to authenticated
    using (
        exists (
            select 1 from public.events e
            where e.id = event_space_requests.event_id
              and e.organiser_id = (select auth.uid())
              and e.status in ('draft', 'returned')
        )
    )
    with check (
        exists (
            select 1 from public.events e
            where e.id = event_space_requests.event_id
              and e.organiser_id = (select auth.uid())
              and e.status in ('draft', 'returned')
        )
    );

create policy "event_space_requests_delete_owner_draft_or_returned"
    on public.event_space_requests for delete to authenticated
    using (
        exists (
            select 1 from public.events e
            where e.id = event_space_requests.event_id
              and e.organiser_id = (select auth.uid())
              and e.status in ('draft', 'returned')
        )
    );

-- Existing events remain usable. Complete requests receive their old event
-- requirements; incomplete drafts receive an intentionally incomplete legacy
-- row and must be completed before submission.
insert into public.event_space_requests (
    event_id, label, expected_pax, layout_preference, facilities_required, starts_at, ends_at
)
select e.id, 'Main space', e.expected_attendance, e.layout_preference,
       e.facilities_required, e.starts_at, e.ends_at
from public.events e
where not exists (
    select 1 from public.event_space_requests es where es.event_id = e.id
);

alter table public.venue_bookings
    add column event_space_request_id uuid null;

update public.venue_bookings vb
set event_space_request_id = (
    select es.id
    from public.event_space_requests es
    where es.event_id = vb.event_id
    order by es.created_at, es.id
    limit 1
)
where vb.event_space_request_id is null;

alter table public.venue_bookings
    add constraint venue_bookings_event_space_request_id_fkey
    foreign key (event_space_request_id)
    references public.event_space_requests (id)
    on delete restrict;

alter table public.venue_bookings
    alter column event_space_request_id set not null;

create index venue_bookings_event_space_request_id_idx
    on public.venue_bookings (event_space_request_id);

drop index public.venue_bookings_one_active_per_event;
create unique index venue_bookings_one_active_per_space
    on public.venue_bookings (event_space_request_id)
    where status in ('held', 'approved', 're_review');

-- Preserve the old event_id booking RPC during rollout. Legacy callers are
-- linked to the first request for the event; new callers use the RPC below.
create or replace function public.populate_booking_space_request()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_space_id uuid;
begin
    if new.event_space_request_id is not null then
        return new;
    end if;

    select id into v_space_id
    from public.event_space_requests
    where event_id = new.event_id
    order by created_at, id
    limit 1;

    if v_space_id is null then
        insert into public.event_space_requests (event_id, label)
        values (new.event_id, 'Main space')
        returning id into v_space_id;
    end if;

    new.event_space_request_id := v_space_id;
    return new;
end;
$$;

create trigger venue_bookings_populate_space_request
    before insert on public.venue_bookings
    for each row execute function public.populate_booking_space_request();

create or replace function public.request_venue_booking_for_space(
    p_event_space_request_id uuid,
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
    v_space public.event_space_requests;
    v_event public.events;
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
    if v_space.starts_at is null or v_space.ends_at is null then
        return query select 'no_period'::text, null::uuid;
        return;
    end if;
    if not exists (select 1 from public.venues v where v.id = p_venue_id) then
        return query select 'venue_not_found'::text, null::uuid;
        return;
    end if;
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
          and b.blocked_period && tstzrange(v_space.starts_at, v_space.ends_at, '[)')
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
            tstzrange(v_space.starts_at, v_space.ends_at, '[)'),
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
    'Requests a venue for one organiser-proposed space and copies its period into the actual booking.';

revoke execute on function public.request_venue_booking_for_space(uuid, uuid, uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.request_venue_booking_for_space(uuid, uuid, uuid, text, text)
    to service_role;
