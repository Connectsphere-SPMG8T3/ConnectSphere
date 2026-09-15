-- =============================================================================
-- PROPOSAL — NOT A MIGRATION. NOT APPLIED TO ANY DATABASE.
--
-- Deliberately lives in docs/proposals/ rather than supabase/migrations/ so
-- `supabase db push` cannot pick it up. PROJECT_REVIEW.md §C3.5 requires the
-- shared core schema to be reviewed by the whole team at stand-up before it is
-- merged, and §B4 records "three people will invent three incompatible schemas"
-- as an active Sprint 1 risk.
--
-- Scope: the events side only — what SCRUM-72's coordinator dashboard reads.
-- Venues, bookings, blocks, equipment, reservations, registrations,
-- notifications and change_history are NOT drafted here. The full core-schema
-- migration (PROJECT_REVIEW §C3.5) should absorb this file rather than sit
-- alongside it.
--
-- Written against: docs/REQUIREMENTS.md §4 (domain model), §5 (lifecycle).
-- Review notes and open questions: docs/proposals/core-events-schema.md
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Enums. Postgres enums rather than free text, matching `user_role`
--    (SCENARIO.md §7). Note that adding a value to an enum cannot run inside a
--    transaction block in older Postgres — see the open question in the .md
--    about whether the lifecycle's volatility makes a lookup table safer.
-- ---------------------------------------------------------------------------
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

create type public.layout_preference as enum (
    'theatre',
    'classroom',
    'banquet',
    'boardroom',
    'u_shape',
    'cocktail',
    'exhibition'
);

create type public.technical_readiness as enum ('not_started', 'in_progress', 'ready', 'not_required');

create type public.change_request_kind as enum ('change', 'cancellation');

create type public.change_request_status as enum ('open', 'approved', 'rejected', 'superseded');

-- ---------------------------------------------------------------------------
-- 2. Client organisations (PROJECT_REVIEW §A3.11 — cheap now, a migration plus
--    backfill later). ACC-R5: an organiser records an organisation at sign-up.
-- ---------------------------------------------------------------------------
create table public.client_organisations (
    id          uuid primary key default gen_random_uuid(),
    name        text not null unique,
    is_active   boolean not null default true,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- profiles.organisation_name is free text today. Linking it to a real row is a
-- separate backfill story; the FK is added here so `events` can be scoped by
-- client without another schema change.
alter table public.profiles
    add column organisation_id uuid references public.client_organisations(id) on delete set null;

create index idx_profiles_organisation_id on public.profiles(organisation_id);

-- ---------------------------------------------------------------------------
-- 3. Events. Field list and validation come from REQUIREMENTS §6.2.
-- ---------------------------------------------------------------------------
create table public.events (
    id                          uuid primary key default gen_random_uuid(),
    organiser_id                uuid not null references public.profiles(id) on delete restrict,
    coordinator_id              uuid references public.profiles(id) on delete set null,
    status                      public.event_status not null default 'draft',

    name                        text not null,
    purpose                     text,
    description                 text,

    starts_at                   timestamptz,
    ends_at                     timestamptz,
    expected_attendance         integer,
    layout_preference           public.layout_preference,
    facilities_required         text[] not null default '{}',
    location_preference         text,
    accessibility_needs         text,
    preliminary_equipment_needs text,

    registration_enabled        boolean not null default false,
    registration_capacity       integer,
    registration_opens_at       timestamptz,
    registration_closes_at      timestamptz,

    technical_readiness         public.technical_readiness not null default 'not_started',
    venue_prep_notes            text,
    technical_prep_notes        text,

    submitted_at                timestamptz,
    -- DB-5: optimistic lock. Bumped by the application on every update.
    version                     integer not null default 1,
    created_at                  timestamptz not null default now(),
    updated_at                  timestamptz not null default now(),

    -- DR-R1: only `name` is required to save a draft; everything else may be
    -- partial. The full §6.2 required-field set is enforced at submit time, in
    -- the service layer, so a draft can be saved in any state.
    constraint events_name_length check (char_length(name) between 3 and 150),
    constraint events_purpose_length check (purpose is null or char_length(purpose) between 1 and 500),
    constraint events_description_length check (description is null or char_length(description) <= 5000),
    constraint events_accessibility_length check (accessibility_needs is null or char_length(accessibility_needs) <= 1000),
    constraint events_attendance_positive check (expected_attendance is null or expected_attendance >= 1),
    constraint events_ends_after_starts check (ends_at is null or starts_at is null or ends_at > starts_at),
    constraint events_registration_capacity_positive
        check (registration_capacity is null or registration_capacity >= 1),
    constraint events_registration_window
        check (
            registration_opens_at is null
            or registration_closes_at is null
            or registration_opens_at < registration_closes_at
        ),
    -- AS-R2: strictly at most one coordinator per event is structural (a single
    -- column). This check keeps a non-draft event from losing its organiser.
    constraint events_submitted_has_timestamp
        check (status = 'draft' or submitted_at is not null)
);

-- Indexes chosen for the queries the coordinator dashboard actually runs:
-- "my active events" and "unassigned submissions" (AS-R5).
create index idx_events_coordinator_status on public.events(coordinator_id, status);
create index idx_events_organiser_status on public.events(organiser_id, status);
create index idx_events_starts_at on public.events(starts_at);
-- Partial index for the awaiting-assignment alert: the set is normally empty.
create index idx_events_awaiting_assignment on public.events(created_at)
    where status = 'submitted' and coordinator_id is null;

create trigger events_set_updated_at
    before update on public.events
    for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 4. Status history (LC-R2: every transition is recorded and visible in the UI).
-- ---------------------------------------------------------------------------
create table public.event_status_history (
    id          uuid primary key default gen_random_uuid(),
    event_id    uuid not null references public.events(id) on delete cascade,
    from_status public.event_status,
    to_status   public.event_status not null,
    actor_id    uuid references public.profiles(id) on delete set null,
    reason      text,
    at          timestamptz not null default now()
);

create index idx_event_status_history_event_at on public.event_status_history(event_id, at desc);

-- ---------------------------------------------------------------------------
-- 5. Amendment requests — the return/resubmit cycle (REQUIREMENTS §6.4,
--    QA-22, QA-77). `resubmitted_at` is what the dashboard's "clarification
--    responses" widget counts (SCRUM-72 AC1).
-- ---------------------------------------------------------------------------
create table public.amendment_requests (
    id                uuid primary key default gen_random_uuid(),
    event_id          uuid not null references public.events(id) on delete cascade,
    returned_by       uuid references public.profiles(id) on delete set null,
    message           text not null,
    flagged_fields    text[] not null default '{}',
    returned_at       timestamptz not null default now(),
    resubmission_note text,
    resubmitted_at    timestamptz,

    constraint amendment_message_not_blank check (btrim(message) <> '')
);

-- A request can be returned more than once (§6.4), so this indexes the open one.
create index idx_amendment_requests_open on public.amendment_requests(event_id)
    where resubmitted_at is null;
create index idx_amendment_requests_resubmitted on public.amendment_requests(resubmitted_at desc)
    where resubmitted_at is not null;

-- ---------------------------------------------------------------------------
-- 6. Change and cancellation requests (REQUIREMENTS §6.19).
-- ---------------------------------------------------------------------------
create table public.change_requests (
    id                uuid primary key default gen_random_uuid(),
    event_id          uuid not null references public.events(id) on delete cascade,
    requested_by      uuid references public.profiles(id) on delete set null,
    kind              public.change_request_kind not null,
    proposed_changes  jsonb not null default '{}'::jsonb,
    impact_summary    jsonb,
    status            public.change_request_status not null default 'open',
    reason            text not null,
    decision_reason   text,
    decided_by        uuid references public.profiles(id) on delete set null,
    decided_at        timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    constraint change_request_reason_not_blank check (btrim(reason) <> ''),
    -- CR-R3: a rejection must carry a reason.
    constraint change_request_decision_has_reason
        check (status <> 'rejected' or btrim(coalesce(decision_reason, '')) <> '')
);

-- CR-R1: at most one open request of each kind per event.
create unique index uq_change_requests_one_open_per_kind
    on public.change_requests(event_id, kind)
    where status = 'open';

create index idx_change_requests_event on public.change_requests(event_id, created_at desc);

create trigger change_requests_set_updated_at
    before update on public.change_requests
    for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 7. Row Level Security.
--
--    The API is the policy-enforcement point and uses the secret key, which
--    bypasses RLS (REQUIREMENTS §2, AGENTS.md). These policies are the
--    deny-by-default safety net for any direct database access, and they must
--    never query their own table — role lookups go through
--    private.current_user_role() (D3), and auth.uid() is wrapped in
--    (select ...) so it is evaluated once per statement, not per row (lint 0003).
-- ---------------------------------------------------------------------------
alter table public.client_organisations enable row level security;
alter table public.events enable row level security;
alter table public.event_status_history enable row level security;
alter table public.amendment_requests enable row level security;
alter table public.change_requests enable row level security;

-- One permissive SELECT policy per table (lint 0006), scoped to `authenticated`.

create policy "events_select_related"
    on public.events
    for select
    to authenticated
    using (
        organiser_id = (select auth.uid())
        or coordinator_id = (select auth.uid())
        -- AUTH-R5: staff operate as pools. Drafts are never visible to staff
        -- (DR-R2), which is why the draft exclusion sits inside the policy.
        or (
            status <> 'draft'
            and (select private.current_user_role())
                in ('event_coordinator', 'venue_staff', 'tech_support')
        )
    );

create policy "client_organisations_select_authenticated"
    on public.client_organisations
    for select
    to authenticated
    using (true);

-- The three policies below look like `where true`, but are not: the subquery on
-- public.events is itself filtered by events_select_related, so each resolves to
-- "the caller can see the parent event". Keeping the rule in one place means a
-- change to event visibility cannot leave a child table behind. Reviewers: this
-- is the part most worth a second opinion — an explicit repeat of the
-- organiser/coordinator/staff predicate would be more obvious but would need
-- updating in four places.
create policy "event_status_history_select_via_event"
    on public.event_status_history
    for select
    to authenticated
    using (
        exists (
            select 1 from public.events e
            where e.id = event_status_history.event_id
        )
    );

create policy "amendment_requests_select_via_event"
    on public.amendment_requests
    for select
    to authenticated
    using (
        exists (
            select 1 from public.events e
            where e.id = amendment_requests.event_id
        )
    );

create policy "change_requests_select_via_event"
    on public.change_requests
    for select
    to authenticated
    using (
        exists (
            select 1 from public.events e
            where e.id = change_requests.event_id
        )
    );

-- No INSERT/UPDATE/DELETE policies are defined: every write goes through the
-- API with the secret key. DB-6 (records are never hard-deleted once submitted)
-- is enforced in the service layer; add a delete-blocking trigger here if the
-- team would rather have it structural.

comment on table public.events is
    'Event requests and their planning state. Lifecycle and guards: docs/REQUIREMENTS.md §5.';
comment on column public.events.version is
    'DB-5 optimistic lock. A stale write returns 409 (IM-R3).';
comment on table public.amendment_requests is
    'Return-for-amendment cycle (§6.4). resubmitted_at is the "client clarification response" the coordinator dashboard counts.';
