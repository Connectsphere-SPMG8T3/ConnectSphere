-- =============================================================================
-- ConnectSphere - SCRUM-109 record preparation progress per venue booking
--
-- Preparation belongs to a booking, not to the event: multi-venue events can
-- be ready at different rates. The API is the policy-enforcement point; this
-- table's RLS policy is the deny-by-default safety net for direct access.
-- =============================================================================

create table public.event_venue_preparation (
    booking_id uuid primary key references public.venue_bookings (id) on delete cascade,
    stage public.preparation_stage not null,
    note text null,
    updated_by uuid null references public.profiles (id) on delete set null,
    updated_at timestamptz not null default now(),
    constraint event_venue_preparation_note_length
        check (note is null or length(btrim(note)) between 1 and 2000)
);

create index event_venue_preparation_updated_by_idx
    on public.event_venue_preparation (updated_by);

comment on table public.event_venue_preparation is
    'SCRUM-109 AC2: venue staff preparation stage and internal note per booking. Rows remain when an event returns to Planning, but updates are locked until it is Confirmed or in Preparation.';

alter table public.event_venue_preparation enable row level security;

create policy "event_venue_preparation_select_staff_or_assigned_coordinator"
    on public.event_venue_preparation
    for select
    to authenticated
    using (
        (select private.current_user_role()) = 'venue_staff'
        or (
            (select private.current_user_role()) = 'event_coordinator'
            and exists (
                select 1
                from public.venue_bookings vb
                join public.events e on e.id = vb.event_id
                where vb.id = event_venue_preparation.booking_id
                  and e.coordinator_id = (select auth.uid())
            )
        )
    );

alter table public.venue_booking_history
    add column old_preparation_stage text null,
    add column new_preparation_stage text null;

comment on column public.venue_booking_history.old_preparation_stage is
    'SCRUM-109 AC5: previous preparation stage for a preparation action.';
comment on column public.venue_booking_history.new_preparation_stage is
    'SCRUM-109 AC5: new preparation stage for a preparation action.';

create or replace function public.set_venue_preparation(
    p_booking_id uuid,
    p_actor_id uuid,
    p_stage text,
    p_note text
)
returns table (outcome text, stage text, note text, updated_at timestamptz, event_status text)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_booking public.venue_bookings;
    v_event public.events;
    v_current public.event_venue_preparation;
    v_stage public.preparation_stage := p_stage::public.preparation_stage;
    v_note text := nullif(btrim(p_note), '');
    v_old_stage public.preparation_stage;
    v_changed boolean := false;
begin
    perform private.set_actor(p_actor_id);

    select * into v_booking
    from public.venue_bookings
    where id = p_booking_id
    for update;
    if not found then
        return query select 'booking_not_found', null::text, null::text, null::timestamptz, null::text;
        return;
    end if;

    select * into v_event
    from public.events
    where id = v_booking.event_id
    for update;
    if not found or v_event.status = 'draft' then
        return query select 'event_not_found', null::text, null::text, null::timestamptz, null::text;
        return;
    end if;

    if v_event.status not in ('confirmed', 'preparation') then
        return query select 'not_confirmed', null::text, null::text, null::timestamptz, v_event.status::text;
        return;
    end if;

    select * into v_current
    from public.event_venue_preparation
    where booking_id = p_booking_id;

    v_old_stage := coalesce(v_current.stage, 'not_started');
    if v_stage is distinct from v_old_stage then
        insert into public.venue_booking_history (
            booking_id, actor_id, action, old_preparation_stage, new_preparation_stage
        )
        values (p_booking_id, p_actor_id, 'preparation', v_old_stage::text, v_stage::text);
        v_changed := true;
    end if;
    if v_note is distinct from v_current.note then
        insert into public.venue_booking_history (
            booking_id, actor_id, action, old_preparation_stage, new_preparation_stage
        )
        values (p_booking_id, p_actor_id, 'preparation_note_updated', null, null);
        v_changed := true;
    end if;

    if v_changed then
        insert into public.event_venue_preparation (booking_id, stage, note, updated_by, updated_at)
        values (p_booking_id, v_stage, v_note, p_actor_id, now())
        on conflict (booking_id) do update
            set stage = excluded.stage, note = excluded.note,
                updated_by = excluded.updated_by, updated_at = excluded.updated_at;
        perform private.start_preparation(v_event.id, p_actor_id);
    end if;

    return query
    select 'ok', v_stage::text, v_note, coalesce(
        (select updated_at from public.event_venue_preparation where booking_id = p_booking_id),
        v_current.updated_at
    ), (select status::text from public.events where id = v_event.id);
end;
$$;

comment on function public.set_venue_preparation(uuid, uuid, text, text) is
    'SCRUM-109 AC1-AC3: records one venue booking preparation update, starts Preparation on the first changed update from Confirmed, and keeps progress locked while the event is in Planning.';

revoke execute on function public.set_venue_preparation(uuid, uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.set_venue_preparation(uuid, uuid, text, text)
    to service_role;
