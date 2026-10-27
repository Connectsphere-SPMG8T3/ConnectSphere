-- SCRUM-55: atomic withdrawal, cutoff enforcement, re-registration and grants.
-- Run against the migrated Supabase schema. The seeded organiser and attendee are
-- used only as foreign keys; all events and registrations roll back.
begin;

insert into public.events (
    id, organiser_id, coordinator_id, status, name, starts_at, ends_at,
    registration_enabled, registration_capacity, registration_opens_at,
    registration_closes_at, re_registration_allowed, withdrawal_closes_at
) values
    ('e0000000-0000-4000-8000-000000005501', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Withdrawal check (rolled back)',
     '2031-08-12 09:00+08', '2031-08-12 17:00+08', true, 1,
     now() - interval '1 day', '2031-08-12 17:00+08', true, null),
    ('e0000000-0000-4000-8000-000000005502', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Cutoff check (rolled back)',
     '2031-08-13 09:00+08', '2031-08-13 17:00+08', true, 1,
     now() - interval '1 day', '2031-08-13 17:00+08', true, now() - interval '1 minute'),
    ('e0000000-0000-4000-8000-000000005503', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Started event check (rolled back)',
     now() - interval '1 hour', now() + interval '1 hour', true, 1,
     now() - interval '1 day', now() + interval '30 minutes', true, now() - interval '1 hour');

insert into public.event_registrations (event_id, attendee_id) values
    ('e0000000-0000-4000-8000-000000005501', 'a0000000-0000-4000-8000-000000000005'),
    ('e0000000-0000-4000-8000-000000005502', 'a0000000-0000-4000-8000-000000000005'),
    ('e0000000-0000-4000-8000-000000005503', 'a0000000-0000-4000-8000-000000000005');

set local role service_role;

do $$
declare
    v_event uuid := 'e0000000-0000-4000-8000-000000005501';
    v_cutoff uuid := 'e0000000-0000-4000-8000-000000005502';
    v_started uuid := 'e0000000-0000-4000-8000-000000005503';
    v_attendee uuid := 'a0000000-0000-4000-8000-000000000005';
    v_result jsonb;
    v_registration public.event_registrations%rowtype;
    v_count integer;
    v_cutoff_valid boolean;
begin
    if not has_function_privilege('service_role', 'public.withdraw_registration(uuid,uuid)', 'EXECUTE')
       or has_function_privilege('authenticated', 'public.withdraw_registration(uuid,uuid)', 'EXECUTE')
       or has_function_privilege('anon', 'public.withdraw_registration(uuid,uuid)', 'EXECUTE') then
        raise exception 'WITHDRAWAL CHECK FAIL: withdraw_registration grants are not service_role-only';
    end if;

    select (withdrawal_closes_at is null or withdrawal_closes_at <= starts_at)
      into v_cutoff_valid
      from public.events
     where id = v_event;
    if v_cutoff_valid is distinct from true then
        raise exception 'WITHDRAWAL CHECK FAIL: null cutoff did not default to event start';
    end if;
    begin
        update public.events
           set withdrawal_closes_at = starts_at + interval '1 second'
         where id = v_event;
        raise exception 'WITHDRAWAL CHECK FAIL: cutoff after event start was accepted';
    exception when check_violation then
        null;
    end;

    v_result := public.withdraw_registration(v_event, v_attendee);
    if v_result->>'outcome' is distinct from 'withdrawn' then
        raise exception 'WITHDRAWAL CHECK FAIL: eligible withdrawal failed: %', v_result;
    end if;
    select * into v_registration from public.event_registrations
     where event_id = v_event and attendee_id = v_attendee;
    if v_registration.status <> 'withdrawn' or v_registration.withdrawn_at is null then
        raise exception 'WITHDRAWAL CHECK FAIL: status or withdrawn_at was not saved';
    end if;
    select count(*) into v_count from public.event_registrations
     where event_id = v_event and status = 'registered';
    if v_count <> 0 then
        raise exception 'WITHDRAWAL CHECK FAIL: withdrawn registration still occupies capacity';
    end if;

    v_result := public.withdraw_registration(v_event, v_attendee);
    select count(*) into v_count from public.event_registrations
     where event_id = v_event and status = 'registered';
    if v_result->>'outcome' is distinct from 'already_withdrawn' or v_count <> 0 then
        raise exception 'WITHDRAWAL CHECK FAIL: repeated withdrawal changed the released place: %, count %',
            v_result, v_count;
    end if;

    v_result := public.register_for_event(v_event, v_attendee);
    if v_result->>'outcome' is distinct from 'registered' then
        raise exception 'WITHDRAWAL CHECK FAIL: permitted re-registration failed: %', v_result;
    end if;
    select * into v_registration from public.event_registrations
     where event_id = v_event and attendee_id = v_attendee;
    if v_registration.status <> 'registered' or v_registration.withdrawn_at is not null then
        raise exception 'WITHDRAWAL CHECK FAIL: re-registration did not restore the active row';
    end if;

    v_result := public.withdraw_registration(v_cutoff, v_attendee);
    select count(*) into v_count from public.event_registrations
     where event_id = v_cutoff and status = 'registered';
    if v_result->>'outcome' is distinct from 'cutoff_passed' or v_count <> 1 then
        raise exception 'WITHDRAWAL CHECK FAIL: passed cutoff changed the registration: %, count %',
            v_result, v_count;
    end if;

    v_result := public.withdraw_registration(v_started, v_attendee);
    select count(*) into v_count from public.event_registrations
     where event_id = v_started and status = 'registered';
    if v_result->>'outcome' is distinct from 'event_started' or v_count <> 1 then
        raise exception 'WITHDRAWAL CHECK FAIL: started event changed the registration: %, count %',
            v_result, v_count;
    end if;

    update public.events set re_registration_allowed = false where id = v_event;
    v_result := public.withdraw_registration(v_event, v_attendee);
    if v_result->>'outcome' is distinct from 'withdrawn' then
        raise exception 'WITHDRAWAL CHECK FAIL: second eligible withdrawal failed: %', v_result;
    end if;
    v_result := public.register_for_event(v_event, v_attendee);
    if v_result->>'outcome' is distinct from 'reregistration_disabled' then
        raise exception 'WITHDRAWAL CHECK FAIL: disabled re-registration was allowed: %', v_result;
    end if;
    select * into v_registration from public.event_registrations
     where event_id = v_event and attendee_id = v_attendee;
    if v_registration.status <> 'withdrawn' or v_registration.withdrawn_at is null then
        raise exception 'WITHDRAWAL CHECK FAIL: refused re-registration changed the withdrawn row';
    end if;
end;
$$;

select 'REGISTRATION WITHDRAWAL CHECKS PASSED' as result;
rollback;
