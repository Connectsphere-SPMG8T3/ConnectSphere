-- =============================================================================
-- ConnectSphere — SCRUM-74/75: multi-role accounts and session-scoped active role
-- Implements docs/REQUIREMENTS.md ACC-R4: an account may hold two roles.
-- profiles.role remains that account's default/home role (unchanged meaning);
-- this migration adds the set of roles an account holds, and the role a given
-- login session is currently acting as. Granting additional roles is done by a
-- system admin directly via SQL — there is no in-app grant endpoint.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Roles an account holds.
-- ---------------------------------------------------------------------------
create table public.user_roles (
    profile_id uuid not null references public.profiles (id) on delete cascade,
    role public.user_role not null,
    created_at timestamptz not null default timezone('utc'::text, now()),
    primary key (profile_id, role)
);

comment on table public.user_roles is
    'Roles an account is allowed to act as (ACC-R4). profiles.role is that account''s default role for a brand-new session; user_roles is the full set it may switch into. Granted only via direct SQL by a system admin.';

create index user_roles_profile_id_idx on public.user_roles using btree (profile_id);

alter table public.user_roles enable row level security;

create policy "user_roles_select_own_or_internal_staff"
    on public.user_roles
    for select
    to authenticated
    using (
        profile_id = (select auth.uid())
        or (select private.current_user_role()) in ('event_coordinator', 'venue_staff', 'tech_support')
    );

-- No insert/update/delete policies: additional roles are granted by a system
-- admin directly via SQL (service role or the SQL editor), never by the app.

-- Every existing account holds (at least) its current default role.
insert into public.user_roles (profile_id, role)
select id, role from public.profiles
on conflict do nothing;

-- ---------------------------------------------------------------------------
-- 2. Keep new signups consistent with the backfill above.
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_requested_role text := new.raw_user_meta_data ->> 'role';
    v_role public.user_role;
begin
    v_role := case
        when v_requested_role in ('event_organiser', 'attendee')
            then v_requested_role::public.user_role
        else 'attendee'::public.user_role
    end;

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
        v_role,
        new.raw_user_meta_data ->> 'organisation_name',
        new.raw_user_meta_data ->> 'department',
        new.raw_user_meta_data ->> 'phone_number'
    );

    insert into public.user_roles (profile_id, role) values (new.id, v_role);

    return new;
end;
$$;

comment on function public.handle_new_user() is
    'Creates the profile and its initial user_roles row for a new auth.users row. Security definer because the new user has no session yet. Only external roles are accepted from sign-up metadata.';

-- ---------------------------------------------------------------------------
-- 3. The role a specific login session is currently acting as (SCRUM-75).
--    Keyed by the session_id claim every Supabase access token carries, so
--    switching roles in one session never affects another concurrent login.
--    Absent a row, the account's default role (profiles.role) applies.
-- ---------------------------------------------------------------------------
create table public.session_active_roles (
    session_id uuid primary key references auth.sessions (id) on delete cascade,
    profile_id uuid not null references public.profiles (id) on delete cascade,
    role public.user_role not null,
    updated_at timestamptz not null default timezone('utc'::text, now())
);

comment on table public.session_active_roles is
    'The role a specific login session is currently acting as (SCRUM-75). One row per session; written only by the backend, after verifying the role is in user_roles for that account.';

create index session_active_roles_profile_id_idx on public.session_active_roles using btree (profile_id);

alter table public.session_active_roles enable row level security;

create policy "session_active_roles_select_own"
    on public.session_active_roles
    for select
    to authenticated
    using (profile_id = (select auth.uid()));

-- No insert/update/delete policies: only the backend's service-role client
-- writes this table, after validating role membership in user_roles.

create trigger session_active_roles_set_updated_at
    before update on public.session_active_roles
    for each row
    execute function public.set_updated_at();
