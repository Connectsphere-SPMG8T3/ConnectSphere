-- =============================================================================
-- ConnectSphere — equipment table write policies follow the active role (DEFECTS D19)
--
-- The write policies on equipment, equipment_unavailability and
-- equipment_reservations must gate on private.current_user_role() (the role the
-- session is acting as, SCRUM-76), not on the JWT's app_metadata role claim.
--
-- Runs inside one transaction and ROLLS BACK, so it changes nothing. Run after
-- migrations (supabase db query --linked -f supabase/verification/equipment_rls_checks.sql,
-- or psql "$DATABASE_URL" -f ...). Any failed check raises an exception
-- starting "EQUIPMENT RLS FAIL".
-- =============================================================================

begin;

-- d1: default role event_coordinator, also holds tech_support.
-- d2: default role tech_support, also holds attendee, and its token still
--     carries a tech_support app_metadata claim.
insert into auth.users (id, instance_id, aud, role, email, raw_user_meta_data, created_at, updated_at)
values
    ('d0000000-0000-4000-8000-0000000000d1', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
     'verify.eqrls.coordinator@connectsphere.dev', '{"full_name":"Verify Equipment RLS Coordinator"}', now(), now()),
    ('d0000000-0000-4000-8000-0000000000d2', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
     'verify.eqrls.tech@connectsphere.dev', '{"full_name":"Verify Equipment RLS Tech"}', now(), now());

insert into public.user_roles (profile_id, role)
values
    ('d0000000-0000-4000-8000-0000000000d1', 'event_coordinator'),
    ('d0000000-0000-4000-8000-0000000000d1', 'tech_support'),
    ('d0000000-0000-4000-8000-0000000000d2', 'tech_support')
on conflict do nothing;
update public.profiles set role = 'event_coordinator' where id = 'd0000000-0000-4000-8000-0000000000d1';
update public.profiles set role = 'tech_support' where id = 'd0000000-0000-4000-8000-0000000000d2';

insert into auth.sessions (id, user_id, created_at, updated_at)
values
    ('d0000000-0000-4000-8000-0000000000e1', 'd0000000-0000-4000-8000-0000000000d1', now(), now()),
    ('d0000000-0000-4000-8000-0000000000e2', 'd0000000-0000-4000-8000-0000000000d2', now(), now());

insert into public.session_active_roles (session_id, profile_id, role)
values
    ('d0000000-0000-4000-8000-0000000000e1', 'd0000000-0000-4000-8000-0000000000d1', 'tech_support'),
    ('d0000000-0000-4000-8000-0000000000e2', 'd0000000-0000-4000-8000-0000000000d2', 'attendee');

-- Rows the update and delete checks act on.
insert into public.equipment (id, name, equipment_type, total_quantity, status)
values ('b0000000-0000-4000-8000-0000000009f1', 'RLS check item (rolled back)', 'check', 2, 'active');
insert into public.equipment_unavailability (id, equipment_id, quantity, start_at, end_at, reason)
values ('b0000000-0000-4000-8000-0000000009f2', 'b0000000-0000-4000-8000-0000000009f1', 1,
        now() + interval '40 days', now() + interval '41 days', 'RLS check (rolled back)');
insert into public.equipment_reservations (id, equipment_id, event_id, quantity, start_at, end_at)
values ('b0000000-0000-4000-8000-0000000009f3', 'b0000000-0000-4000-8000-0000000009f1',
        'e0000000-0000-4000-8000-0000000009a1', 1,
        now() + interval '42 days', now() + interval '43 days');

-- d1 acting as tech_support (no app_metadata role claim, like every real token):
-- may insert, update and delete on all three tables.
select set_config(
    'request.jwt.claims',
    '{"sub":"d0000000-0000-4000-8000-0000000000d1","role":"authenticated","session_id":"d0000000-0000-4000-8000-0000000000e1","app_metadata":{"provider":"email"}}',
    true
);
set local role authenticated;

do $$
declare
    v_rows integer;
begin
    begin
        insert into public.equipment (name, equipment_type, total_quantity, status)
        values ('RLS insert (rolled back)', 'check', 1, 'active');
    exception when insufficient_privilege then
        raise exception 'EQUIPMENT RLS FAIL: a session acting as tech_support cannot insert equipment';
    end;
    update public.equipment set total_quantity = 3 where id = 'b0000000-0000-4000-8000-0000000009f1';
    get diagnostics v_rows = row_count;
    if v_rows <> 1 then
        raise exception 'EQUIPMENT RLS FAIL: a session acting as tech_support cannot update equipment';
    end if;

    begin
        insert into public.equipment_unavailability (equipment_id, quantity, start_at, end_at, reason)
        values ('b0000000-0000-4000-8000-0000000009f1', 1,
                now() + interval '44 days', now() + interval '45 days', 'RLS insert (rolled back)');
    exception when insufficient_privilege then
        raise exception 'EQUIPMENT RLS FAIL: a session acting as tech_support cannot insert equipment_unavailability';
    end;
    update public.equipment_unavailability set quantity = 2 where id = 'b0000000-0000-4000-8000-0000000009f2';
    get diagnostics v_rows = row_count;
    if v_rows <> 1 then
        raise exception 'EQUIPMENT RLS FAIL: a session acting as tech_support cannot update equipment_unavailability';
    end if;

    begin
        insert into public.equipment_reservations (equipment_id, event_id, quantity, start_at, end_at)
        values ('b0000000-0000-4000-8000-0000000009f1', 'e0000000-0000-4000-8000-0000000009a2', 1,
                now() + interval '46 days', now() + interval '47 days');
    exception when insufficient_privilege then
        raise exception 'EQUIPMENT RLS FAIL: a session acting as tech_support cannot insert equipment_reservations';
    end;
    update public.equipment_reservations set quantity = 2 where id = 'b0000000-0000-4000-8000-0000000009f3';
    get diagnostics v_rows = row_count;
    if v_rows <> 1 then
        raise exception 'EQUIPMENT RLS FAIL: a session acting as tech_support cannot update equipment_reservations';
    end if;
end $$;

reset role;

-- d2 acting as attendee, though the account holds tech_support and its token
-- carries a tech_support app_metadata claim: every write is refused.
select set_config(
    'request.jwt.claims',
    '{"sub":"d0000000-0000-4000-8000-0000000000d2","role":"authenticated","session_id":"d0000000-0000-4000-8000-0000000000e2","app_metadata":{"provider":"email","role":"tech_support"}}',
    true
);
set local role authenticated;

do $$
declare
    v_rows integer;
begin
    begin
        insert into public.equipment (name, equipment_type, total_quantity, status)
        values ('RLS insert as attendee (rolled back)', 'check', 1, 'active');
        raise exception 'EQUIPMENT RLS FAIL: a tech_support account acting as attendee can insert equipment';
    exception when insufficient_privilege then null;
    end;
    update public.equipment set total_quantity = 9 where id = 'b0000000-0000-4000-8000-0000000009f1';
    get diagnostics v_rows = row_count;
    if v_rows <> 0 then
        raise exception 'EQUIPMENT RLS FAIL: a tech_support account acting as attendee can update equipment';
    end if;
    delete from public.equipment_reservations where id = 'b0000000-0000-4000-8000-0000000009f3';
    get diagnostics v_rows = row_count;
    if v_rows <> 0 then
        raise exception 'EQUIPMENT RLS FAIL: a tech_support account acting as attendee can delete equipment_reservations';
    end if;

    begin
        insert into public.equipment_unavailability (equipment_id, quantity, start_at, end_at, reason)
        values ('b0000000-0000-4000-8000-0000000009f1', 1,
                now() + interval '48 days', now() + interval '49 days', 'RLS insert as attendee (rolled back)');
        raise exception 'EQUIPMENT RLS FAIL: a tech_support account acting as attendee can insert equipment_unavailability';
    exception when insufficient_privilege then null;
    end;
    delete from public.equipment_unavailability where id = 'b0000000-0000-4000-8000-0000000009f2';
    get diagnostics v_rows = row_count;
    if v_rows <> 0 then
        raise exception 'EQUIPMENT RLS FAIL: a tech_support account acting as attendee can delete equipment_unavailability';
    end if;

    begin
        insert into public.equipment_reservations (equipment_id, event_id, quantity, start_at, end_at)
        values ('b0000000-0000-4000-8000-0000000009f1', 'e0000000-0000-4000-8000-0000000009a3', 1,
                now() + interval '50 days', now() + interval '51 days');
        raise exception 'EQUIPMENT RLS FAIL: a tech_support account acting as attendee can insert equipment_reservations';
    exception when insufficient_privilege then null;
    end;
    delete from public.equipment where id = 'b0000000-0000-4000-8000-0000000009f1';
    get diagnostics v_rows = row_count;
    if v_rows <> 0 then
        raise exception 'EQUIPMENT RLS FAIL: a tech_support account acting as attendee can delete equipment';
    end if;
end $$;

reset role;

-- d1 acting as tech_support may also delete (run last: it removes the fixtures).
select set_config(
    'request.jwt.claims',
    '{"sub":"d0000000-0000-4000-8000-0000000000d1","role":"authenticated","session_id":"d0000000-0000-4000-8000-0000000000e1","app_metadata":{"provider":"email"}}',
    true
);
set local role authenticated;

do $$
declare
    v_rows integer;
begin
    delete from public.equipment_reservations where id = 'b0000000-0000-4000-8000-0000000009f3';
    get diagnostics v_rows = row_count;
    if v_rows <> 1 then
        raise exception 'EQUIPMENT RLS FAIL: a session acting as tech_support cannot delete equipment_reservations';
    end if;
    delete from public.equipment_unavailability where id = 'b0000000-0000-4000-8000-0000000009f2';
    get diagnostics v_rows = row_count;
    if v_rows <> 1 then
        raise exception 'EQUIPMENT RLS FAIL: a session acting as tech_support cannot delete equipment_unavailability';
    end if;
    delete from public.equipment where name = 'RLS insert (rolled back)';
    get diagnostics v_rows = row_count;
    if v_rows <> 1 then
        raise exception 'EQUIPMENT RLS FAIL: a session acting as tech_support cannot delete equipment';
    end if;
end $$;

reset role;

select 'EQUIPMENT RLS CHECKS PASSED' as result;

rollback;
