-- =============================================================================
-- ConnectSphere — active-role enforcement checks (SCRUM-76)
--
-- private.current_user_role() (which every RLS policy calls) must return the
-- role the caller's *session* is acting as (session_active_roles, keyed by the
-- JWT session_id claim), not the account's default profiles.role. Falls back to
-- profiles.role when the session never switched or the token has no session_id.
--
-- Runs inside one transaction and ROLLS BACK, so it changes nothing. Run after
-- migrations (psql "$DATABASE_URL" -f supabase/verification/active_role_checks.sql,
-- or paste into the Supabase MCP execute_sql tool). Any failed check raises an
-- exception starting "ACTIVE ROLE FAIL".
-- =============================================================================

begin;

-- An account whose default role is venue_staff that also holds attendee.
insert into auth.users (id, instance_id, aud, role, email, raw_user_meta_data, created_at, updated_at)
values
    ('c0000000-0000-4000-8000-0000000000b1', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
     'verify.multirole@connectsphere.dev', '{"full_name":"Verify Multi Role"}', now(), now());

insert into public.user_roles (profile_id, role)
values ('c0000000-0000-4000-8000-0000000000b1', 'venue_staff');
update public.profiles set role = 'venue_staff' where id = 'c0000000-0000-4000-8000-0000000000b1';

insert into auth.sessions (id, user_id, created_at, updated_at)
values
    ('c0000000-0000-4000-8000-0000000000c1', 'c0000000-0000-4000-8000-0000000000b1', now(), now()),
    ('c0000000-0000-4000-8000-0000000000c2', 'c0000000-0000-4000-8000-0000000000b1', now(), now());

-- Session c1 switched to attendee; session c2 never switched.
insert into public.session_active_roles (session_id, profile_id, role)
values ('c0000000-0000-4000-8000-0000000000c1', 'c0000000-0000-4000-8000-0000000000b1', 'attendee');

do $$
begin
    if not exists (select 1 from public.venues) then
        raise exception 'ACTIVE ROLE FAIL: this check needs at least one venue (run supabase/seed.sql)';
    end if;
end $$;

-- Session c1: acting as attendee, so the function says attendee and the
-- staff-only venue policies show nothing, even though the account holds venue_staff.
select set_config(
    'request.jwt.claims',
    '{"sub":"c0000000-0000-4000-8000-0000000000b1","role":"authenticated","session_id":"c0000000-0000-4000-8000-0000000000c1"}',
    true
);
set local role authenticated;

do $$
begin
    if (select private.current_user_role()) is distinct from 'attendee' then
        raise exception 'ACTIVE ROLE FAIL: switched session (attendee) resolved as %', (select private.current_user_role());
    end if;
    if exists (select 1 from public.venues) then
        raise exception 'ACTIVE ROLE FAIL: a session acting as attendee can read venues because the account also holds venue_staff';
    end if;
end $$;

reset role;

-- Session c2: never switched, falls back to the default role.
select set_config(
    'request.jwt.claims',
    '{"sub":"c0000000-0000-4000-8000-0000000000b1","role":"authenticated","session_id":"c0000000-0000-4000-8000-0000000000c2"}',
    true
);
set local role authenticated;

do $$
begin
    if (select private.current_user_role()) is distinct from 'venue_staff' then
        raise exception 'ACTIVE ROLE FAIL: un-switched session did not fall back to profiles.role, got %', (select private.current_user_role());
    end if;
end $$;

reset role;

-- A token with no session_id claim also falls back to the default role.
select set_config(
    'request.jwt.claims',
    '{"sub":"c0000000-0000-4000-8000-0000000000b1","role":"authenticated"}',
    true
);
set local role authenticated;

do $$
begin
    if (select private.current_user_role()) is distinct from 'venue_staff' then
        raise exception 'ACTIVE ROLE FAIL: token without session_id did not fall back to profiles.role, got %', (select private.current_user_role());
    end if;
end $$;

reset role;

-- Another account's session must never be honoured for this user.
insert into auth.users (id, instance_id, aud, role, email, raw_user_meta_data, created_at, updated_at)
values
    ('c0000000-0000-4000-8000-0000000000b2', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
     'verify.otheraccount@connectsphere.dev', '{"full_name":"Verify Other Account","role":"event_organiser"}', now(), now());

select set_config(
    'request.jwt.claims',
    '{"sub":"c0000000-0000-4000-8000-0000000000b2","role":"authenticated","session_id":"c0000000-0000-4000-8000-0000000000c1"}',
    true
);
set local role authenticated;

do $$
begin
    if (select private.current_user_role()) is distinct from 'event_organiser' then
        raise exception 'ACTIVE ROLE FAIL: a session belonging to another account changed this account''s role';
    end if;
end $$;

reset role;

select 'ACTIVE ROLE CHECKS PASSED' as result;

rollback;
