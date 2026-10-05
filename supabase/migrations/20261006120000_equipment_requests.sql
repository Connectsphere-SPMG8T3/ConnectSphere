-- =============================================================================
-- ConnectSphere - SCRUM-45 record and submit an event equipment request
--
-- equipment_requests: one row per request line (REQUIREMENTS 6.15): a catalogue
-- item, a quantity and optional technical requirements for one event. Lines
-- submitted together share a submission_id. submit_equipment_request writes a
-- whole submission in one statement, so it is saved together or not at all.
-- API-only (ADR-0002): the API checks role and relationship before calling, and
-- the function re-checks under the event lock.
-- =============================================================================

-- The full 6.15 line lifecycle, so SCRUM-24 (reserve/reject) needs no enum
-- change. SCRUM-45 only ever writes `pending`.
create type public.equipment_request_status as enum (
    'pending',
    'reserved',
    'rejected',
    're_review',
    'released'
);

create table public.equipment_requests (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null,
    equipment_id uuid not null,
    submission_id uuid not null,
    quantity integer not null,
    technical_requirements text null,
    status public.equipment_request_status not null default 'pending',
    requested_by uuid null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint equipment_requests_event_id_fkey
        foreign key (event_id) references public.events (id) on delete cascade,
    -- Restrict: a catalogue item that has been requested is retired, not deleted.
    constraint equipment_requests_equipment_id_fkey
        foreign key (equipment_id) references public.equipment (id) on delete restrict,
    constraint equipment_requests_requested_by_fkey
        foreign key (requested_by) references public.profiles (id) on delete set null,
    -- EQ-R1: above total inventory is allowed (warned in the UI); below 1 never is.
    constraint equipment_requests_quantity_positive check (quantity >= 1),
    constraint equipment_requests_technical_requirements_length
        check (technical_requirements is null or length(btrim(technical_requirements)) between 1 and 1000)
);

comment on table public.equipment_requests is
    'Equipment request lines for an event (SCRUM-45, REQUIREMENTS 6.15). Written only by submit_equipment_request.';
comment on column public.equipment_requests.submission_id is
    'Groups the lines a coordinator submitted together in one request.';

create index equipment_requests_event_created_at_idx on public.equipment_requests (event_id, created_at);
create index equipment_requests_status_created_at_idx on public.equipment_requests (status, created_at);
create index equipment_requests_equipment_id_idx on public.equipment_requests (equipment_id);
create index equipment_requests_requested_by_idx on public.equipment_requests (requested_by);

create trigger equipment_requests_set_updated_at
    before update on public.equipment_requests
    for each row
    execute function public.set_updated_at();

alter table public.equipment_requests enable row level security;

-- Safety net only: the API uses the secret key. Gated on the session's active
-- role (SCRUM-76): tech support work as a pool across all requests (AUTH-R5);
-- a coordinator sees only the events they are assigned to.
create policy "equipment_requests_select_tech_support_or_assigned_coordinator"
    on public.equipment_requests
    for select
    to authenticated
    using (
        (select private.current_user_role()) = 'tech_support'
        or (
            (select private.current_user_role()) = 'event_coordinator'
            and exists (
                select 1
                from public.events e
                where e.id = equipment_requests.event_id
                  and e.coordinator_id = (select auth.uid())
            )
        )
    );

create or replace function public.submit_equipment_request(
    p_event_id uuid,
    p_actor_id uuid,
    p_items jsonb
)
returns table (outcome text, lines jsonb)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_submission_id uuid := gen_random_uuid();
    v_lines jsonb;
begin
    -- Lock the event so a concurrent status change or reassignment can't slip
    -- between the checks and the insert.
    select * into v_event from public.events where id = p_event_id for update;
    if not found or v_event.status = 'draft' then
        return query select 'event_not_found'::text, null::jsonb;
        return;
    end if;

    -- The API already checked these; re-checked under the lock.
    if v_event.coordinator_id is distinct from p_actor_id then
        return query select 'not_assigned'::text, null::jsonb;
        return;
    end if;
    -- QA-22: requirements are still being amended while returned.
    if v_event.status = 'returned' then
        return query select 'returned'::text, null::jsonb;
        return;
    end if;
    if v_event.status <> 'planning' then
        return query select 'not_planning'::text, null::jsonb;
        return;
    end if;

    if p_items is null or jsonb_typeof(p_items) <> 'array' or jsonb_array_length(p_items) = 0 then
        return query select 'no_items'::text, null::jsonb;
        return;
    end if;

    -- A retired item is no longer in the catalogue, so it can't be requested.
    if exists (
        select 1
        from jsonb_to_recordset(p_items) as i (equipment_id uuid)
        left join public.equipment e on e.id = i.equipment_id
        where e.id is null or e.status = 'retired'
    ) then
        return query select 'unknown_equipment'::text, null::jsonb;
        return;
    end if;

    -- One statement: every line is written, or (on any constraint failure) none.
    with inserted as (
        insert into public.equipment_requests (
            event_id, equipment_id, submission_id, quantity, technical_requirements, requested_by
        )
        select
            p_event_id,
            i.equipment_id,
            v_submission_id,
            i.quantity,
            nullif(btrim(i.technical_requirements), ''),
            p_actor_id
        from jsonb_to_recordset(p_items) as i (equipment_id uuid, quantity integer, technical_requirements text)
        returning *
    )
    select jsonb_agg(to_jsonb(inserted)) into v_lines from inserted;

    return query select 'ok'::text, v_lines;
end;
$$;

comment on function public.submit_equipment_request is
    'Submits equipment request lines for a planning event as pending, all or none. Returns an outcome code instead of raising. API-only.';

revoke execute on function public.submit_equipment_request(uuid, uuid, jsonb) from public, anon, authenticated;
grant execute on function public.submit_equipment_request(uuid, uuid, jsonb) to service_role;
