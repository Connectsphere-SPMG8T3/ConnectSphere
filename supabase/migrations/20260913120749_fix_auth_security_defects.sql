-- =============================================================================
-- ConnectSphere — fix auth/profile security defects (docs/PROJECT_REVIEW.md D2, D3, D6)
-- Project: vuiryrzzyfecjqftwicj
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. D2: sign-up may only self-assign an external role.
--    raw_user_meta_data is supplied by whoever calls sign-up with the public
--    key, so the role is taken from an allow-list: Event Organisers and
--    Attendees sign up themselves (QA-3, QA-4); internal staff roles are
--    system defaults set by seed/migration, never by sign-up.
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_requested_role text := new.raw_user_meta_data ->> 'role';
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
        case
            when v_requested_role in ('event_organiser', 'attendee')
                then v_requested_role::public.user_role
            else 'attendee'::public.user_role
        end,
        new.raw_user_meta_data ->> 'organisation_name',
        new.raw_user_meta_data ->> 'department',
        new.raw_user_meta_data ->> 'phone_number'
    );
    return new;
end;
$$;

comment on function public.handle_new_user() is
    'Creates the profile for a new auth.users row. Security definer because the new user has no session yet. Only external roles are accepted from sign-up metadata.';

-- Trigger functions are never meant to be called through the REST RPC endpoint.
revoke execute on function public.handle_new_user() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 2. D3: RLS helper that reads the caller's role without re-entering the
--    profiles policies (a profiles policy that queries profiles recurses:
--    42P17). Lives in a schema the Data API does not expose, so it is not
--    callable as an RPC.
-- ---------------------------------------------------------------------------
create schema if not exists private;
revoke all on schema private from public;
grant usage on schema private to authenticated;

create or replace function private.current_user_role()
returns public.user_role
language sql
stable
security definer
set search_path = ''
as $$
    select p.role
    from public.profiles p
    where p.id = (select auth.uid());
$$;

comment on function private.current_user_role() is
    'Role of the calling user, for use inside RLS policies. Security definer so the lookup does not re-apply profiles RLS (which would recurse).';

revoke execute on function private.current_user_role() from public, anon;
grant execute on function private.current_user_role() to authenticated;

-- ---------------------------------------------------------------------------
-- 3. D3 + D6: profiles policies.
--    - one permissive SELECT policy instead of two overlapping ones (lint 0006)
--    - auth.uid() / role helper wrapped in (select ...) so they are evaluated
--      once per statement, not per row (lint 0003)
--    - scoped to `authenticated`; anon has no access
-- ---------------------------------------------------------------------------
drop policy if exists "profiles_select_own" on public.profiles;
drop policy if exists "profiles_select_internal_staff" on public.profiles;
drop policy if exists "profiles_update_own" on public.profiles;

-- Users read their own profile; internal staff read every profile to support
-- cross-role coordination.
create policy "profiles_select_own_or_internal_staff"
    on public.profiles
    for select
    to authenticated
    using (
        id = (select auth.uid())
        or (select private.current_user_role()) in ('event_coordinator', 'venue_staff', 'tech_support')
    );

-- Users update their own profile; prevent_self_role_change() still blocks
-- changing their own role.
create policy "profiles_update_own"
    on public.profiles
    for update
    to authenticated
    using (id = (select auth.uid()))
    with check (id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- 4. D6: pin search_path on the remaining trigger functions (lint 0011).
--    Their bodies only use pg_catalog functions and schema-qualified auth.uid().
-- ---------------------------------------------------------------------------
alter function public.set_updated_at() set search_path = '';
alter function public.prevent_self_role_change() set search_path = '';
