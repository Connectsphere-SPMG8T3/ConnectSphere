-- =============================================================================
-- ConnectSphere — SCRUM-48: initial auth & profiles schema
-- Project: vuiryrzzyfecjqftwicj
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Role enumeration
-- ---------------------------------------------------------------------------
create type public.user_role as enum (
    'event_organiser',
    'event_coordinator',
    'venue_staff',
    'tech_support',
    'attendee'
);

-- ---------------------------------------------------------------------------
-- 2. Profiles table (3NF: auth credentials stay in auth.users; domain
--    attributes describing a ConnectSphere user live here)
-- ---------------------------------------------------------------------------
create table public.profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    email varchar(255) not null unique,
    full_name varchar(150) not null,
    role public.user_role not null default 'attendee',
    organisation_name varchar(255) null,
    department varchar(100) null,
    phone_number varchar(30) null,
    created_at timestamptz not null default timezone('utc'::text, now()),
    updated_at timestamptz not null default timezone('utc'::text, now())
);

comment on table public.profiles is
    'Domain profile for a ConnectSphere user, one row per auth.users entry.';
comment on column public.profiles.organisation_name is
    'Populated for external Event Organisers.';
comment on column public.profiles.department is
    'Populated for internal staff (Event Coordinator, Venue Staff, Technical Support).';

-- ---------------------------------------------------------------------------
-- 3. Indexes
-- ---------------------------------------------------------------------------
create index profiles_role_idx on public.profiles using btree (role);
create index profiles_email_idx on public.profiles using btree (email);

-- ---------------------------------------------------------------------------
-- 4. updated_at maintenance trigger
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = timezone('utc'::text, now());
    return new;
end;
$$;

create trigger profiles_set_updated_at
    before update on public.profiles
    for each row
    execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 5. Automated profile creation on new auth.users row
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (
        id,
        email,
        full_name,
        role,
        organisation_name,
        department,
        phone_number
    )
    values (
        new.id,
        new.email,
        coalesce(new.raw_user_meta_data ->> 'full_name', new.email),
        coalesce((new.raw_user_meta_data ->> 'role')::public.user_role, 'attendee'),
        new.raw_user_meta_data ->> 'organisation_name',
        new.raw_user_meta_data ->> 'department',
        new.raw_user_meta_data ->> 'phone_number'
    );
    return new;
end;
$$;

create trigger on_auth_user_created
    after insert on auth.users
    for each row
    execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- 6. Row Level Security
-- ---------------------------------------------------------------------------
alter table public.profiles enable row level security;

-- Users can read their own profile.
create policy "profiles_select_own"
    on public.profiles
    for select
    using (id = auth.uid());

-- Internal staff can view every profile, to support cross-role coordination
-- (e.g. an Event Coordinator viewing an Event Organiser's contact details,
-- or Venue Staff / Technical Support viewing a Coordinator's profile).
create policy "profiles_select_internal_staff"
    on public.profiles
    for select
    using (
        exists (
            select 1
            from public.profiles staff
            where staff.id = auth.uid()
              and staff.role in ('event_coordinator', 'venue_staff', 'tech_support')
        )
    );

-- Users can update their own profile, but never their own role (role changes
-- must go through a privileged, staff-only path in a future story).
create policy "profiles_update_own"
    on public.profiles
    for update
    using (id = auth.uid())
    with check (id = auth.uid());

create or replace function public.prevent_self_role_change()
returns trigger
language plpgsql
as $$
begin
    if new.role is distinct from old.role and auth.uid() = old.id then
        raise exception 'Users may not change their own role.';
    end if;
    return new;
end;
$$;

create trigger profiles_prevent_self_role_change
    before update on public.profiles
    for each row
    execute function public.prevent_self_role_change();

-- No insert/delete policies are defined for regular users: profile rows are
-- created exclusively by the handle_new_user() trigger (security definer)
-- and removed via the auth.users cascade, so anon/authenticated roles have
-- no direct insert or delete access.
