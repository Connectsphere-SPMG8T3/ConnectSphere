-- SCRUM-113 notifications RLS safety net: a signed-in user reads only their own
-- notifications addressed to the role their session is ACTING as, the same rule
-- as the API (AGENTS.md security baseline; SCRUM-76). Run after migration
-- 20261021100000 with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`.
-- Raises on the first failure and returns NOTIFICATION RLS CHECKS PASSED
-- otherwise. Everything runs inside `begin; ... rollback;`.
-- Seeded coordinator …0002 holds event_coordinator (default) and venue_staff;
-- …0003 is venue staff.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name) values
    ('e0000000-0000-4000-8000-0000000007e1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'RLS check (rolled back)');

-- Session d1 switched to venue_staff; session d2 never switched.
insert into auth.sessions (id, user_id, created_at, updated_at) values
    ('d0000000-0000-4000-8000-0000000007d1', 'a0000000-0000-4000-8000-000000000002', now(), now()),
    ('d0000000-0000-4000-8000-0000000007d2', 'a0000000-0000-4000-8000-000000000002', now(), now());
insert into public.session_active_roles (session_id, profile_id, role) values
    ('d0000000-0000-4000-8000-0000000007d1', 'a0000000-0000-4000-8000-000000000002', 'venue_staff');

insert into public.notifications (recipient_id, event_id, type, message, recipient_role) values
    ('a0000000-0000-4000-8000-000000000002', 'e0000000-0000-4000-8000-0000000007e1', 'event_assigned',
     'rls-coordinator', 'event_coordinator'),
    ('a0000000-0000-4000-8000-000000000002', 'e0000000-0000-4000-8000-0000000007e1', 'venue_booking_requested',
     'rls-venue-staff', 'venue_staff');

-- Acting as venue staff (session d1): only the venue-staff notice.
select set_config('request.jwt.claims',
    '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated","session_id":"d0000000-0000-4000-8000-0000000007d1"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.notifications where message like 'rls-%') <> 1
       or not exists (select 1 from public.notifications where message = 'rls-venue-staff') then
        raise exception 'RLS FAIL: acting as venue_staff must read exactly the venue-staff notice';
    end if;
end $$;
reset role;

-- Never switched (session d2): the default role, coordinator.
select set_config('request.jwt.claims',
    '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated","session_id":"d0000000-0000-4000-8000-0000000007d2"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.notifications where message like 'rls-%') <> 1
       or not exists (select 1 from public.notifications where message = 'rls-coordinator') then
        raise exception 'RLS FAIL: acting as event_coordinator must read exactly the coordinator notice';
    end if;
end $$;
reset role;

-- Someone else reads none of them.
select set_config('request.jwt.claims',
    '{"sub":"a0000000-0000-4000-8000-000000000003","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if exists (select 1 from public.notifications where message like 'rls-%') then
        raise exception 'RLS FAIL: another user can read someone else''s notifications';
    end if;
end $$;
reset role;

select 'NOTIFICATION RLS CHECKS PASSED' as result;

rollback;
