-- =============================================================================
-- ConnectSphere — SCRUM-39: venue catalogue, blocks and bookings
-- Project: vuiryrzzyfecjqftwicj
--
-- Creates the venue side of the domain model (docs/REQUIREMENTS.md §4):
--   venues, venue_layouts, venue_facilities, venue_blocks, venue_bookings.
-- Bookings get the DB-1 exclusion constraint now, while the table is empty,
-- so SCRUM-19/20/21 build on a guarantee that already holds.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. btree_gist lets a GiST exclusion constraint combine `venue_id WITH =`
--    with `occupied_period WITH &&` (DB-1).
-- ---------------------------------------------------------------------------
create extension if not exists btree_gist with schema extensions;

-- ---------------------------------------------------------------------------
-- 2. Controlled lists. The customer requires layouts and facilities to come
--    from a controlled list (QA-24, W4) but never enumerated them; the values
--    are a [Team decision] recorded in REQUIREMENTS §6.8. Adding a value is a
--    one-line `alter type ... add value` migration.
-- ---------------------------------------------------------------------------
create type public.venue_layout as enum (
    'theatre',
    'classroom',
    'boardroom',
    'banquet',
    'u_shape',
    'reception'
);

create type public.facility as enum (
    'projector',
    'sound_system',
    'microphone',
    'video_conferencing',
    'whiteboard',
    'stage',
    'wifi',
    'catering_space'
);

create type public.accessibility_feature as enum (
    'wheelchair_access',
    'step_free_entry',
    'accessible_toilet',
    'hearing_loop',
    'lift_access'
);

-- Only held / approved / re_review occupy the venue (§6.14).
create type public.venue_booking_status as enum (
    'held',
    'approved',
    're_review',
    'rejected',
    'cancelled',
    'released'
);

-- Any block, whatever its reason, makes the venue unavailable (CAL-R3).
create type public.venue_block_reason as enum (
    'maintenance',
    'renovation',
    'safety',
    'internal_activity',
    'other'
);

-- ---------------------------------------------------------------------------
-- 3. Venue catalogue
-- ---------------------------------------------------------------------------
create table public.venues (
    id uuid primary key default gen_random_uuid(),
    name varchar(150) not null unique,
    location varchar(255) not null,
    capacity integer not null check (capacity > 0),
    accessibility_features public.accessibility_feature[] not null default '{}',
    opens_at time not null,
    closes_at time not null,
    is_active boolean not null default true,
    description text null,
    created_at timestamptz not null default timezone('utc'::text, now()),
    updated_at timestamptz not null default timezone('utc'::text, now()),
    constraint venues_operating_hours_check check (closes_at > opens_at)
);

comment on table public.venues is
    'A single bookable space. One venue hosts one event at a time (QA-116); no sub-rooms (QA-130).';
comment on column public.venues.capacity is
    'Maximum attendance regardless of layout; venue_layouts may record a lower per-layout figure.';
comment on column public.venues.is_active is
    'Inactive venues are excluded from search but remain on historic bookings (VC-R1).';

create table public.venue_layouts (
    venue_id uuid not null references public.venues (id) on delete cascade,
    layout public.venue_layout not null,
    capacity_for_layout integer null check (capacity_for_layout > 0),
    primary key (venue_id, layout)
);

comment on column public.venue_layouts.capacity_for_layout is
    'Capacity in this layout when it differs from venues.capacity; null means the venue figure applies.';

create table public.venue_facilities (
    venue_id uuid not null references public.venues (id) on delete cascade,
    facility public.facility not null,
    primary key (venue_id, facility)
);

-- ---------------------------------------------------------------------------
-- 4. Blocks: venue staff make a venue unbookable for a period (§6.9).
--    Periods are half-open [start, end): a block ending at 12:00 leaves the
--    venue available from 12:00 (CAL-R2). Blocks may overlap bookings
--    (CAL-R1), so there is deliberately no exclusion constraint here.
-- ---------------------------------------------------------------------------
create table public.venue_blocks (
    id uuid primary key default gen_random_uuid(),
    venue_id uuid not null references public.venues (id) on delete cascade,
    blocked_period tstzrange not null,
    reason public.venue_block_reason not null,
    notes text null,
    created_at timestamptz not null default timezone('utc'::text, now()),
    updated_at timestamptz not null default timezone('utc'::text, now()),
    constraint venue_blocks_period_is_bounded_half_open check (
        not isempty(blocked_period)
        and lower_inc(blocked_period)
        and not upper_inc(blocked_period)
        and not lower_inf(blocked_period)
        and not upper_inf(blocked_period)
    )
);

-- ---------------------------------------------------------------------------
-- 5. Bookings: an event's claim on a venue (§6.12–6.14).
--    event_id is deliberately not a foreign key yet: the events module owns
--    event records and its table has not landed. Add the constraint with it.
-- ---------------------------------------------------------------------------
create table public.venue_bookings (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null,
    venue_id uuid not null references public.venues (id) on delete restrict,
    occupied_period tstzrange not null,
    status public.venue_booking_status not null default 'held',
    decision_reason text null,
    suggested_venue_id uuid null references public.venues (id) on delete set null,
    created_at timestamptz not null default timezone('utc'::text, now()),
    updated_at timestamptz not null default timezone('utc'::text, now()),
    constraint venue_bookings_period_is_bounded_half_open check (
        not isempty(occupied_period)
        and lower_inc(occupied_period)
        and not upper_inc(occupied_period)
        and not lower_inf(occupied_period)
        and not upper_inf(occupied_period)
    ),
    -- DB-1: no two events hold or book the same venue for overlapping
    -- periods. First-come-first-served, no override (QA-6, QA-10, QA-113).
    -- Half-open ranges with zero turnaround (QA-28) allow back-to-back use.
    constraint venue_bookings_no_overlap exclude using gist (
        venue_id with =,
        occupied_period with &&
    ) where (status in ('held', 'approved', 're_review'))
);

comment on column public.venue_bookings.event_id is
    'Owned by the events module; becomes a foreign key once public.events exists.';

-- BR-R1: one venue per event — at most one occupying booking per event.
create unique index venue_bookings_one_active_per_event
    on public.venue_bookings (event_id)
    where status in ('held', 'approved', 're_review');

-- ---------------------------------------------------------------------------
-- 6. Indexes. The exclusion constraint already indexes bookings by
--    (venue_id, occupied_period); blocks get the equivalent, and the
--    child tables get their foreign-key indexes (lint 0001).
-- ---------------------------------------------------------------------------
create index venue_blocks_venue_period_gist
    on public.venue_blocks using gist (venue_id, blocked_period);
create index venue_layouts_venue_id_idx on public.venue_layouts using btree (venue_id);
create index venue_facilities_venue_id_idx on public.venue_facilities using btree (venue_id);
create index venue_bookings_event_id_idx on public.venue_bookings using btree (event_id);
create index venue_bookings_suggested_venue_id_idx
    on public.venue_bookings using btree (suggested_venue_id);
create index venues_is_active_idx on public.venues using btree (is_active);

-- ---------------------------------------------------------------------------
-- 7. updated_at maintenance (reuses the trigger function from SCRUM-48)
-- ---------------------------------------------------------------------------
create trigger venues_set_updated_at
    before update on public.venues
    for each row execute function public.set_updated_at();
create trigger venue_blocks_set_updated_at
    before update on public.venue_blocks
    for each row execute function public.set_updated_at();
create trigger venue_bookings_set_updated_at
    before update on public.venue_bookings
    for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 8. Row Level Security. The API reads with the secret key, so these
--    policies only guard direct PostgREST access: internal staff may read,
--    nobody may write directly (holds must go through the API for BR-R1 and
--    BR-R3). Organisers and attendees see nothing (AUTH-R2).
-- ---------------------------------------------------------------------------
alter table public.venues enable row level security;
alter table public.venue_layouts enable row level security;
alter table public.venue_facilities enable row level security;
alter table public.venue_blocks enable row level security;
alter table public.venue_bookings enable row level security;

create policy "venues_select_internal_staff"
    on public.venues for select to authenticated
    using ((select private.current_user_role()) in ('event_coordinator', 'venue_staff', 'tech_support'));

create policy "venue_layouts_select_internal_staff"
    on public.venue_layouts for select to authenticated
    using ((select private.current_user_role()) in ('event_coordinator', 'venue_staff', 'tech_support'));

create policy "venue_facilities_select_internal_staff"
    on public.venue_facilities for select to authenticated
    using ((select private.current_user_role()) in ('event_coordinator', 'venue_staff', 'tech_support'));

create policy "venue_blocks_select_internal_staff"
    on public.venue_blocks for select to authenticated
    using ((select private.current_user_role()) in ('event_coordinator', 'venue_staff', 'tech_support'));

create policy "venue_bookings_select_internal_staff"
    on public.venue_bookings for select to authenticated
    using ((select private.current_user_role()) in ('event_coordinator', 'venue_staff', 'tech_support'));
