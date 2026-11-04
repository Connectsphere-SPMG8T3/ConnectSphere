-- SCRUM-68 AC2: complete due Confirmed/Preparation events through the lifecycle
-- function, preserve other statuses, and register one hourly pg_cron job.
-- Run with `supabase db query --linked -f`. The transaction rolls back all
-- verification changes, including any pre-existing due events selected by the
-- function's global sweep.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-0000000009c1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Completion check C1 (rolled back)',
     '2033-05-01 09:00+08', '2033-05-01 12:00+08'),
    ('e0000000-0000-4000-8000-0000000009c2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'preparation', 'Completion check C2 (rolled back)',
     '2033-05-01 08:00+08', '2033-05-01 11:00+08'),
    ('e0000000-0000-4000-8000-0000000009c3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Completion check C3 (rolled back)',
     '2033-05-02 09:00+08', '2033-05-02 12:00+08'),
    ('e0000000-0000-4000-8000-0000000009c4', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'preparation', 'Completion check C4 (rolled back)',
     '2033-05-02 08:00+08', '2033-05-02 11:00+08'),
    ('e0000000-0000-4000-8000-0000000009c5', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Completion check C5 (rolled back)',
     '2033-05-01 07:00+08', '2033-05-01 10:00+08'),
    ('e0000000-0000-4000-8000-0000000009c6', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'draft', 'Completion check C6 (rolled back)',
     '2033-05-01 06:00+08', '2033-05-01 09:00+08'),
    ('e0000000-0000-4000-8000-0000000009c7', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'submitted', 'Completion check C7 (rolled back)',
     '2033-05-01 06:00+08', '2033-05-01 09:00+08'),
    ('e0000000-0000-4000-8000-0000000009c8', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'under_review', 'Completion check C8 (rolled back)',
     '2033-05-01 06:00+08', '2033-05-01 09:00+08'),
    ('e0000000-0000-4000-8000-0000000009c9', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'returned', 'Completion check C9 (rolled back)',
     '2033-05-01 06:00+08', '2033-05-01 09:00+08'),
    ('e0000000-0000-4000-8000-0000000009ca', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'safety_review', 'Completion check CA (rolled back)',
     '2033-05-01 06:00+08', '2033-05-01 09:00+08'),
    ('e0000000-0000-4000-8000-0000000009cb', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'rejected', 'Completion check CB (rolled back)',
     '2033-05-01 06:00+08', '2033-05-01 09:00+08'),
    ('e0000000-0000-4000-8000-0000000009cc', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'cancelled', 'Completion check CC (rolled back)',
     '2033-05-01 06:00+08', '2033-05-01 09:00+08'),
    ('e0000000-0000-4000-8000-0000000009cd', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'completed', 'Completion check CD (rolled back)',
     '2033-05-01 06:00+08', '2033-05-01 09:00+08');

do $$
declare
    c_now constant timestamptz := '2033-05-01 12:00:00+08';
    v_before integer;
    v_after integer;
    v_rows integer;
    v_schedule text;
    v_command text;
begin
    select version into v_before from public.events
     where id = 'e0000000-0000-4000-8000-0000000009c1';

    select public.complete_due_events(c_now) into v_rows;
    if v_rows < 2 then
        raise exception 'EVENT COMPLETION FAIL: the first run completed % events, expected at least the 2 test events', v_rows;
    end if;

    if (select count(*) from public.events
         where id in ('e0000000-0000-4000-8000-0000000009c1',
                      'e0000000-0000-4000-8000-0000000009c2')
           and status = 'completed') <> 2 then
        raise exception 'EVENT COMPLETION FAIL: due Confirmed/Preparation events were not completed';
    end if;
    select version into v_after from public.events
     where id = 'e0000000-0000-4000-8000-0000000009c1';
    if v_after <> v_before + 1 then
        raise exception 'EVENT COMPLETION FAIL: a completed event version did not increase once';
    end if;
    select count(*) into v_rows from public.event_status_history
     where event_id in ('e0000000-0000-4000-8000-0000000009c1',
                        'e0000000-0000-4000-8000-0000000009c2')
       and to_status = 'completed' and actor_id is null;
    if v_rows <> 2 then
        raise exception 'EVENT COMPLETION FAIL: expected one system completion history row per event, got %', v_rows;
    end if;

    if exists (
        select 1
          from (values
              ('e0000000-0000-4000-8000-0000000009c3'::uuid, 'confirmed'),
              ('e0000000-0000-4000-8000-0000000009c4'::uuid, 'preparation'),
              ('e0000000-0000-4000-8000-0000000009c5'::uuid, 'planning'),
              ('e0000000-0000-4000-8000-0000000009c6'::uuid, 'draft'),
              ('e0000000-0000-4000-8000-0000000009c7'::uuid, 'submitted'),
              ('e0000000-0000-4000-8000-0000000009c8'::uuid, 'under_review'),
              ('e0000000-0000-4000-8000-0000000009c9'::uuid, 'returned'),
              ('e0000000-0000-4000-8000-0000000009ca'::uuid, 'safety_review'),
              ('e0000000-0000-4000-8000-0000000009cb'::uuid, 'rejected'),
              ('e0000000-0000-4000-8000-0000000009cc'::uuid, 'cancelled'),
              ('e0000000-0000-4000-8000-0000000009cd'::uuid, 'completed')
          ) as expected(id, status)
          join public.events e using (id)
         where e.status::text <> expected.status or e.version <> 1
    ) then
        raise exception 'EVENT COMPLETION FAIL: a future or non-eligible event changed status or version';
    end if;

    select public.complete_due_events(c_now) into v_rows;
    if v_rows <> 0 then
        raise exception 'EVENT COMPLETION FAIL: a repeated run completed % events, expected 0', v_rows;
    end if;
    select count(*) into v_rows from public.event_status_history
     where event_id in ('e0000000-0000-4000-8000-0000000009c1',
                        'e0000000-0000-4000-8000-0000000009c2')
       and to_status = 'completed';
    if v_rows <> 2 then
        raise exception 'EVENT COMPLETION FAIL: a repeated run wrote duplicate completion history';
    end if;

    select schedule, command into v_schedule, v_command
      from cron.job where jobname = 'complete-due-events';
    if not found or v_schedule <> '0 * * * *'
       or v_command not like '%complete_due_events%' then
        raise exception 'EVENT COMPLETION FAIL: the hourly completion job is missing or misconfigured';
    end if;
    if (select count(*) from cron.job where jobname = 'complete-due-events') <> 1 then
        raise exception 'EVENT COMPLETION FAIL: expected exactly one completion cron job';
    end if;
    if has_function_privilege('anon', 'public.complete_due_events(timestamptz)', 'execute')
       or has_function_privilege('authenticated', 'public.complete_due_events(timestamptz)', 'execute')
       or not has_function_privilege('service_role', 'public.complete_due_events(timestamptz)', 'execute') then
        raise exception 'EVENT COMPLETION FAIL: completion function grants are incorrect';
    end if;
end
$$;

select 'EVENT COMPLETION CHECKS PASSED' as result;
rollback;
