-- =============================================================================
-- ConnectSphere — auth/profile security checks (regression for DEFECTS D2, D3, D6)
--
-- Runs every check inside one transaction and ROLLS BACK, so it changes nothing.
-- Any failed check raises an exception naming the defect. Run after migrations
-- (psql "$DATABASE_URL" -f supabase/verification/auth_security_checks.sql, or
-- paste into the Supabase MCP execute_sql tool). Requires supabase/seed.sql.
-- =============================================================================

begin;

-- D2: sign-up cannot self-assign a staff role. Inserts run as the connecting
-- (migration) role; the Supabase Auth path itself is checked live through the
-- Auth admin API, since hosted projects don't allow SET ROLE supabase_auth_admin.
insert into auth.users (id, instance_id, aud, role, email, raw_user_meta_data, created_at, updated_at)
values
    ('c0000000-0000-4000-8000-0000000000a1', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
     'verify.escalation@connectsphere.dev', '{"full_name":"Verify Escalation","role":"event_coordinator"}', now(), now()),
    ('c0000000-0000-4000-8000-0000000000a2', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
     'verify.organiser@connectsphere.dev', '{"full_name":"Verify Organiser","role":"event_organiser"}', now(), now()),
    ('c0000000-0000-4000-8000-0000000000a3', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
     'verify.norole@connectsphere.dev', '{"full_name":"Verify No Role"}', now(), now()),
    -- 12 AC12 / CR-103 AC5: the two later staff roles are no more claimable at sign-up.
    ('c0000000-0000-4000-8000-0000000000a4', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
     'verify.lead@connectsphere.dev', '{"full_name":"Verify Lead","role":"event_coordinator_lead"}', now(), now()),
    ('c0000000-0000-4000-8000-0000000000a5', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
     'verify.safety@connectsphere.dev', '{"full_name":"Verify Safety","role":"safety_officer"}', now(), now());

do $$
begin
    if (select role from public.profiles where id = 'c0000000-0000-4000-8000-0000000000a1') <> 'attendee' then
        raise exception 'D2 FAIL: sign-up requesting event_coordinator was granted a staff role';
    end if;
    if (select role from public.profiles where id = 'c0000000-0000-4000-8000-0000000000a2') <> 'event_organiser' then
        raise exception 'D2 FAIL: sign-up requesting event_organiser did not get event_organiser';
    end if;
    if (select role from public.profiles where id = 'c0000000-0000-4000-8000-0000000000a3') <> 'attendee' then
        raise exception 'D2 FAIL: sign-up without a role did not default to attendee';
    end if;
    if (select role from public.profiles where id = 'c0000000-0000-4000-8000-0000000000a4') <> 'attendee' then
        raise exception 'D2 FAIL: sign-up requesting event_coordinator_lead was granted a staff role';
    end if;
    if (select role from public.profiles where id = 'c0000000-0000-4000-8000-0000000000a5') <> 'attendee' then
        raise exception 'D2 FAIL: sign-up requesting safety_officer was granted a staff role';
    end if;
    if not exists (select 1 from pg_enum where enumtypid = 'public.user_role'::regtype and enumlabel = 'event_coordinator_lead')
       or not exists (select 1 from pg_enum where enumtypid = 'public.user_role'::regtype and enumlabel = 'safety_officer') then
        raise exception '12 AC12 / CR-103 AC5 FAIL: public.user_role is missing event_coordinator_lead or safety_officer';
    end if;
    if has_function_privilege('anon', 'public.handle_new_user()', 'execute')
       or has_function_privilege('authenticated', 'public.handle_new_user()', 'execute') then
        raise exception 'D2 FAIL: handle_new_user() is executable by anon/authenticated via RPC';
    end if;
end $$;

select set_config('verify.total_profiles', (select count(*) from public.profiles)::text, true);

-- D3: RLS as an attendee returns only their own row, without recursion.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000005","role":"authenticated"}', true);
set local role authenticated;
do $$
declare
    v_visible int;
    v_updated int;
begin
    select count(*) into v_visible from public.profiles;
    if v_visible <> 1 then
        raise exception 'D3 FAIL: attendee sees % profiles, expected only their own', v_visible;
    end if;

    update public.profiles set full_name = 'tampered' where id = 'a0000000-0000-4000-8000-000000000002';
    get diagnostics v_updated = row_count;
    if v_updated <> 0 then
        raise exception 'D3 FAIL: attendee updated another user''s profile';
    end if;

    begin
        update public.profiles set role = 'venue_staff' where id = 'a0000000-0000-4000-8000-000000000005';
        raise exception 'D3 FAIL: attendee changed their own role';
    exception when raise_exception then
        if sqlerrm like 'D3 FAIL%' then
            raise;
        end if;
    end;
end $$;
reset role;

-- D3: RLS as internal staff returns every profile.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
declare
    v_visible int;
begin
    select count(*) into v_visible from public.profiles;
    if v_visible <> current_setting('verify.total_profiles')::int then
        raise exception 'D3 FAIL: coordinator sees % of % profiles', v_visible, current_setting('verify.total_profiles');
    end if;
end $$;
reset role;

-- D3: anonymous callers see nothing.
select set_config('request.jwt.claims', '', true);
set local role anon;
do $$
begin
    if (select count(*) from public.profiles) <> 0 then
        raise exception 'D3 FAIL: anon can read profiles';
    end if;
end $$;
reset role;

-- D6: every function touched by these policies/triggers pins its search_path.
do $$
declare
    v_unpinned text;
begin
    select string_agg(n.nspname || '.' || p.proname, ', ') into v_unpinned
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where (n.nspname, p.proname) in (
        ('public', 'handle_new_user'), ('public', 'set_updated_at'),
        ('public', 'prevent_self_role_change'), ('private', 'current_user_role')
    )
      and not exists (select 1 from unnest(coalesce(p.proconfig, '{}')) c where c like 'search_path=%');
    if v_unpinned is not null then
        raise exception 'D6 FAIL: search_path not pinned on %', v_unpinned;
    end if;
end $$;

select 'ALL AUTH SECURITY CHECKS PASSED' as result;

rollback;
