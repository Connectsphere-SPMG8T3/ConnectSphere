-- =============================================================================
-- ConnectSphere — SCRUM-76: RLS acts on the session's active role
-- =============================================================================

-- private.current_user_role() is what every RLS policy calls, and it read
-- profiles.role, the account's *default* role. Once an account can hold several
-- roles and switch between them (SCRUM-74/75), a session acting as one role kept
-- the access of its default role at the database layer, so the API and RLS
-- disagreed. This repoints the function at the role the caller's session is
-- acting as: the session_active_roles row for the JWT's session_id claim, which
-- the API writes only after checking user_roles. The signature is unchanged, so
-- no policy needs editing.
--
-- Falls back to profiles.role when the session never switched or the token has
-- no session_id claim, the same fallback the API uses (resolve_active_role).
-- Rows are matched on profile_id as well as session_id, so a session id that
-- belongs to another account is never honoured.
create or replace function private.current_user_role()
returns public.user_role
language sql
stable
security definer
set search_path = ''
as $$
    select coalesce(
        (
            select sar.role
            from public.session_active_roles sar
            where sar.session_id = nullif((select auth.jwt()) ->> 'session_id', '')::uuid
              and sar.profile_id = (select auth.uid())
        ),
        (
            select p.role
            from public.profiles p
            where p.id = (select auth.uid())
        )
    );
$$;

comment on function private.current_user_role() is
    'Role the calling session is acting as, for use inside RLS policies: the session_active_roles row for the JWT session_id claim (SCRUM-76), else the account''s default profiles.role. Security definer so the lookups do not re-apply RLS (which would recurse).';
