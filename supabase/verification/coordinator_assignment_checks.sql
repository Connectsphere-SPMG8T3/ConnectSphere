-- SCRUM-12: public.assign_event and the exclusive Lead role; every change rolls back.
-- Run with `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/verification/coordinator_assignment_checks.sql`.
-- Uses the seeded accounts: organiser ...01, coordinators ...02 and ...08, Lead ...07, venue staff ...03.
begin;

insert into public.events (id, organiser_id, coordinator_id, status, name)
values ('e0000000-0000-4000-8000-000000000501', 'a0000000-0000-4000-8000-000000000001', null,
        'submitted', 'Queued (rolled back)'),
       ('e0000000-0000-4000-8000-000000000502', 'a0000000-0000-4000-8000-000000000001', null,
        'draft', 'Draft (rolled back)');

do $$
declare
    q uuid := 'e0000000-0000-4000-8000-000000000501';
    d uuid := 'e0000000-0000-4000-8000-000000000502';
    organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    coordinator_a uuid := 'a0000000-0000-4000-8000-000000000002';
    coordinator_b uuid := 'a0000000-0000-4000-8000-000000000008';
    lead uuid := 'a0000000-0000-4000-8000-000000000007';
    venue_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    r public.events;
    n integer;
begin
    if to_regprocedure('public.assign_event(uuid, uuid, uuid, text[], text, text, text, text)') is null then
        raise exception 'SCRUM-12: assign_event missing';
    end if;

    -- A target without the coordinator role (the Lead, venue staff) is refused; nothing changes.
    select count(*) into n from public.assign_event(q, lead, lead, array['submitted'], 'under_review', 'r', 'a', 'o');
    if n <> 0 then raise exception 'SCRUM-12: a Lead was assigned as coordinator'; end if;
    select count(*) into n from public.assign_event(q, lead, venue_staff, array['submitted'], 'under_review', 'r', 'a', 'o');
    if n <> 0 then raise exception 'SCRUM-12: venue staff were assigned as coordinator'; end if;
    if (select status from public.events where id = q) <> 'submitted' then
        raise exception 'SCRUM-12: a refused assignment changed the event';
    end if;

    -- A draft is not in the queue.
    select count(*) into n from public.assign_event(d, lead, coordinator_a, array['submitted'], 'under_review', 'r', 'a', 'o');
    if n <> 0 then raise exception 'SCRUM-12: a draft was assigned'; end if;

    -- The assignment.
    select * into r from public.assign_event(q, lead, coordinator_a, array['submitted'], 'under_review',
                                              'Assigned to A', 'to A', 'to organiser');
    if r.coordinator_id is distinct from coordinator_a or r.assigned_by is distinct from lead
       or r.assigned_at is null or r.status <> 'under_review' then
        raise exception 'SCRUM-12: assignment did not set coordinator, assigner, time and status';
    end if;
    if not exists (select 1 from public.event_status_history
                    where event_id = q and from_status = 'submitted' and to_status = 'under_review'
                      and actor_id = lead and reason = 'Assigned to A') then
        raise exception 'SCRUM-12: history row (who, when, to whom) missing';
    end if;
    if (select count(*) from public.notifications where event_id = q and recipient_id = coordinator_a and message = 'to A') <> 1
       or (select count(*) from public.notifications where event_id = q and recipient_id = organiser and message = 'to organiser') <> 1 then
        raise exception 'SCRUM-12: coordinator and organiser notices';
    end if;
    if exists (select 1 from public.notifications where event_id = q and recipient_id = lead) then
        raise exception 'SCRUM-12: the Lead was notified of their own action';
    end if;

    -- Already assigned: a second assignment (another Lead, or a replay) changes nothing.
    select count(*) into n from public.assign_event(q, lead, coordinator_b, array['submitted'], 'under_review', 'r', 'a', 'o');
    if n <> 0 or (select coordinator_id from public.events where id = q) <> coordinator_a then
        raise exception 'SCRUM-12: an assigned event was assigned again';
    end if;

    -- The Lead role is exclusive.
    begin
        insert into public.user_roles (profile_id, role) values (lead, 'event_coordinator');
        raise exception 'SCRUM-12: a Lead was granted a second role';
    exception when check_violation then null;
    end;
    begin
        insert into public.user_roles (profile_id, role) values (coordinator_a, 'event_coordinator_lead');
        raise exception 'SCRUM-12: a coordinator was granted the Lead role';
    exception when check_violation then null;
    end;

    raise notice 'SCRUM-12 database checks passed';
end;
$$;

rollback;
