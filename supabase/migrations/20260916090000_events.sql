-- =============================================================================
-- ConnectSphere - SCRUM-8: event requests and drafts
--
-- Draft completeness and lifecycle transitions are enforced by the API. This
-- migration provides the durable event record, structural constraints, and
-- the relationship needed by venue bookings.
-- =============================================================================

create type public.event_status as enum (
    'draft',
    'submitted',
    'under_review',
    'returned',
    'planning',
    'confirmed',
    'rejected',
    'cancelled',
    'completed'
);

create type public.technical_readiness as enum (
    'not_required',
    'pending',
    'ready',
    'issue'
);

create table public.events (
    id uuid primary key default gen_random_uuid(),
    organiser_id uuid not null references public.profiles (id) on delete restrict,
    coordinator_id uuid null references public.profiles (id) on delete restrict,
    status public.event_status not null default 'draft',
    name varchar(150) not null,
    purpose varchar(500) null,
    description varchar(5000) null,
    starts_at timestamptz null,
    ends_at timestamptz null,
    expected_attendance integer null,
    layout_preference public.venue_layout null,
    facilities_required public.facility[] not null default '{}',
    accessibility_needs text null,
    preliminary_equipment_needs text null,
    registration_enabled boolean not null default false,
    registration_capacity integer null,
    registration_opens_at timestamptz null,
    registration_closes_at timestamptz null,
    technical_readiness public.technical_readiness not null default 'not_required',
    submitted_at timestamptz null,
    version integer not null default 1,
    created_at timestamptz not null default timezone('utc'::text, now()),
    updated_at timestamptz not null default timezone('utc'::text, now()),
    constraint events_name_not_blank check (length(btrim(name)) > 0),
    constraint events_purpose_length check (purpose is null or length(purpose) <= 500),
    constraint events_description_length check (description is null or length(description) <= 5000),
    constraint events_time_bounds check (
        (starts_at is null and ends_at is null)
        or (starts_at is not null and ends_at is not null and ends_at > starts_at)
    ),
    constraint events_attendance_positive check (
        expected_attendance is null or expected_attendance >= 1
    ),
    constraint events_registration_capacity_positive check (
        registration_capacity is null or registration_capacity >= 1
    ),
    constraint events_registration_window_order check (
        registration_opens_at is null
        or registration_closes_at is null
        or registration_opens_at < registration_closes_at
    ),
    constraint events_registration_closes_before_event check (
        registration_closes_at is null
        or starts_at is null
        or registration_closes_at <= starts_at
    ),
    constraint events_version_positive check (version >= 1)
);

comment on table public.events is
    'Event requests owned by an organiser. Drafts may be incomplete; submission completeness is an API rule.';
comment on column public.events.id is
    'The unique event reference returned to the organiser until a human-readable reference is introduced.';
comment on column public.events.organiser_id is
    'The single organiser responsible for the request; ownership comes from the verified API identity.';
comment on column public.events.version is
    'Optimistic-lock version for concurrent event edits (DB-5).';

create index events_organiser_id_idx on public.events using btree (organiser_id);
create index events_coordinator_id_idx on public.events using btree (coordinator_id);
create index events_status_idx on public.events using btree (status);
create index events_starts_at_idx on public.events using btree (starts_at);

create trigger events_set_updated_at
    before update on public.events
    for each row execute function public.set_updated_at();

-- The venue migration intentionally left this relationship open until events
-- existed. Submitted bookings must now point at a real event record.
alter table public.venue_bookings
    add constraint venue_bookings_event_id_fkey
    foreign key (event_id) references public.events (id) on delete restrict;

alter table public.events enable row level security;

-- Drafts are private. Internal staff may search non-draft requests, while an
-- assigned coordinator also retains access to the request they own.
create policy "events_select_owner_or_internal_staff"
    on public.events
    for select
    to authenticated
    using (
        organiser_id = (select auth.uid())
        or (
            status <> 'draft'
            and (select private.current_user_role()) in (
                'event_coordinator', 'venue_staff', 'tech_support'
            )
        )
    );

create policy "events_insert_own_draft"
    on public.events
    for insert
    to authenticated
    with check (
        organiser_id = (select auth.uid())
        and (select private.current_user_role()) = 'event_organiser'
        and status = 'draft'
    );

create policy "events_update_own_draft_or_returned"
    on public.events
    for update
    to authenticated
    using (
        organiser_id = (select auth.uid())
        and status in ('draft', 'returned')
    )
    with check (
        organiser_id = (select auth.uid())
        and status in ('draft', 'returned')
    );

create policy "events_delete_own_draft"
    on public.events
    for delete
    to authenticated
    using (
        organiser_id = (select auth.uid())
        and status = 'draft'
    );
