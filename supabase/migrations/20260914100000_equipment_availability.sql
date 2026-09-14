-- ConnectSphere — equipment inventory and availability records

create type public.equipment_status as enum (
    'active',
    'maintenance',
    'retired'
);

create type public.equipment_reservation_status as enum (
    'confirmed',
    'cancelled',
    'completed'
);

create table public.equipment (
    id uuid primary key default gen_random_uuid(),
    name varchar(150) not null,
    equipment_type varchar(100) not null,
    description text,
    total_quantity integer not null check (total_quantity >= 0),
    status public.equipment_status not null default 'active',
    specifications jsonb,
    created_at timestamptz not null default timezone('utc'::text, now()),
    updated_at timestamptz not null default timezone('utc'::text, now())
);

create table public.equipment_unavailability (
    id uuid primary key default gen_random_uuid(),
    equipment_id uuid not null references public.equipment(id) on delete cascade,
    quantity integer not null check (quantity > 0),
    start_at timestamptz not null,
    end_at timestamptz not null,
    reason varchar(255),
    created_at timestamptz not null default timezone('utc'::text, now()),
    constraint equipment_unavailability_valid_period check (end_at > start_at)
);

create table public.equipment_reservations (
    id uuid primary key default gen_random_uuid(),
    equipment_id uuid not null references public.equipment(id) on delete cascade,
    -- Deliberately not a foreign key: the events module owns event records.
    event_id uuid not null,
    quantity integer not null check (quantity > 0),
    start_at timestamptz not null,
    end_at timestamptz not null,
    status public.equipment_reservation_status not null default 'confirmed',
    notes text,
    created_at timestamptz not null default timezone('utc'::text, now()),
    updated_at timestamptz not null default timezone('utc'::text, now()),
    constraint equipment_reservations_valid_period check (end_at > start_at)
);

create index equipment_unavailability_equipment_range_idx
    on public.equipment_unavailability (equipment_id, start_at, end_at);

create index equipment_reservations_equipment_range_idx
    on public.equipment_reservations (equipment_id, start_at, end_at);

create index equipment_type_idx on public.equipment (equipment_type);

create trigger equipment_set_updated_at
    before update on public.equipment
    for each row
    execute function public.set_updated_at();

create trigger equipment_reservations_set_updated_at
    before update on public.equipment_reservations
    for each row
    execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------
-- Equipment availability is readable by any authenticated user so coordinators
-- and other internal workflows can inspect current stock. Mutations are
-- restricted to the server-controlled app_metadata role claim; user_metadata
-- is intentionally not used because users can edit it themselves.
alter table public.equipment enable row level security;
alter table public.equipment_unavailability enable row level security;
alter table public.equipment_reservations enable row level security;

create policy "equipment_select_authenticated"
    on public.equipment
    for select
    to authenticated
    using (true);

create policy "equipment_insert_tech_support"
    on public.equipment
    for insert
    to authenticated
    with check ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'tech_support');

create policy "equipment_update_tech_support"
    on public.equipment
    for update
    to authenticated
    using ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'tech_support')
    with check ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'tech_support');

create policy "equipment_delete_tech_support"
    on public.equipment
    for delete
    to authenticated
    using ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'tech_support');

create policy "equipment_unavailability_select_authenticated"
    on public.equipment_unavailability
    for select
    to authenticated
    using (true);

create policy "equipment_unavailability_insert_tech_support"
    on public.equipment_unavailability
    for insert
    to authenticated
    with check ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'tech_support');

create policy "equipment_unavailability_update_tech_support"
    on public.equipment_unavailability
    for update
    to authenticated
    using ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'tech_support')
    with check ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'tech_support');

create policy "equipment_unavailability_delete_tech_support"
    on public.equipment_unavailability
    for delete
    to authenticated
    using ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'tech_support');

create policy "equipment_reservations_select_authenticated"
    on public.equipment_reservations
    for select
    to authenticated
    using (true);

create policy "equipment_reservations_insert_tech_support"
    on public.equipment_reservations
    for insert
    to authenticated
    with check ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'tech_support');

create policy "equipment_reservations_update_tech_support"
    on public.equipment_reservations
    for update
    to authenticated
    using ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'tech_support')
    with check ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'tech_support');

create policy "equipment_reservations_delete_tech_support"
    on public.equipment_reservations
    for delete
    to authenticated
    using ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'tech_support');