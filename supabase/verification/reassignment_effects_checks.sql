-- SCRUM-81 what a reassignment does, against the real functions: the status is unchanged and no
-- status-history row is written (AC9), a returned request that is reassigned and then resubmitted
-- stays with the coordinator assigned at that time, whose notice it is (AC12, QA3-15), an event
-- assigned before the Lead role existed can be reassigned and then belongs to that Lead (AC13),
-- the previous coordinator is told and the new one is not told twice (AC2), and of two
-- reassignments of the same version only one succeeds (AC11). Run with
-- `supabase db query --linked -f` or `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f`. Raises on the
-- first failure and prints REASSIGNMENT EFFECTS CHECKS PASSED otherwise. Everything runs inside
-- `begin; ... rollback;`, so the throwaway events leave no trace. Uses the seeded organiser
-- (…0001), coordinators (…0002 and …0008) and the Lead (…0007).

begin;

insert into public.events (id, organiser_id, coordinator_id, assigned_by, status, name) values
    ('e0000000-0000-4000-8000-000000008101', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000007',
     'returned', 'Effects check, returned (rolled back)'),
    ('e0000000-0000-4000-8000-000000008102', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', null,
     'planning', 'Effects check, assigned before Leads (rolled back)'),
    ('e0000000-0000-4000-8000-000000008103', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000007',
     'planning', 'Effects check, concurrent (rolled back)');

do $$
declare
    v_returned uuid := 'e0000000-0000-4000-8000-000000008101';
    v_legacy uuid := 'e0000000-0000-4000-8000-000000008102';
    v_race uuid := 'e0000000-0000-4000-8000-000000008103';
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_old uuid := 'a0000000-0000-4000-8000-000000000002';
    v_new uuid := 'a0000000-0000-4000-8000-000000000008';
    v_lead uuid := 'a0000000-0000-4000-8000-000000000007';
    v_statuses text[] := array['under_review', 'returned', 'planning', 'safety_review', 'confirmed', 'preparation'];
    v_row public.events;
    v_version integer;
    v_status_rows_before integer;
    v_count integer;
begin
    -- AC9: status unchanged, version moved on, assignment history written, status history untouched.
    select version into v_version from public.events where id = v_returned;
    select count(*) into v_status_rows_before from public.event_status_history where event_id = v_returned;

    select * into v_row from public.reassign_event(
        v_returned, v_lead, v_new, v_version, v_statuses, 'assigned', 'previous', 'organiser');
    if not found then raise exception 'EFFECTS FAIL: the returned event was not reassigned'; end if;
    if v_row.status::text <> 'returned' then raise exception 'EFFECTS FAIL AC9: status changed to %', v_row.status; end if;
    if v_row.coordinator_id <> v_new or v_row.assigned_by <> v_lead or v_row.version <> v_version + 1 then
        raise exception 'EFFECTS FAIL AC9: coordinator, assigner or version wrong: %', row_to_json(v_row);
    end if;
    select count(*) into v_count from public.event_status_history where event_id = v_returned;
    if v_count <> v_status_rows_before then
        raise exception 'EFFECTS FAIL AC9: a reassignment wrote a status-history row';
    end if;
    select count(*) into v_count from public.event_assignment_history
     where event_id = v_returned and from_coordinator_id = v_old and to_coordinator_id = v_new and actor_id = v_lead;
    if v_count <> 1 then raise exception 'EFFECTS FAIL AC4: expected one assignment-history row, found %', v_count; end if;

    -- AC2: new coordinator, previous coordinator and organiser are each told once.
    select count(*) into v_count from public.notifications
     where event_id = v_returned and recipient_id = v_new and type = 'event_assigned';
    if v_count <> 1 then raise exception 'EFFECTS FAIL AC2: the new coordinator was told % times', v_count; end if;
    select count(*) into v_count from public.notifications
     where event_id = v_returned and recipient_id = v_old and type = 'event_reassigned';
    if v_count <> 1 then raise exception 'EFFECTS FAIL AC2: the previous coordinator was told % times', v_count; end if;
    select count(*) into v_count from public.notifications
     where event_id = v_returned and recipient_id = v_organiser and type = 'event_coordinator_changed';
    if v_count <> 1 then raise exception 'EFFECTS FAIL AC2: the organiser was told % times', v_count; end if;

    -- AC11: a second reassignment of the version the first one used loses and writes nothing.
    select count(*) into v_count from public.reassign_event(
        v_returned, v_lead, v_old, v_version, v_statuses, 'assigned', 'previous', 'organiser');
    if v_count <> 0 then raise exception 'EFFECTS FAIL AC11: a stale reassignment succeeded'; end if;
    if (select coordinator_id from public.events where id = v_returned) <> v_new then
        raise exception 'EFFECTS FAIL AC11: the stale reassignment changed the coordinator';
    end if;

    -- AC12: the organiser resubmits; it goes to the coordinator assigned now, not the queue.
    select version into v_version from public.events where id = v_returned;
    select * into v_row from public.resubmit_event(
        v_returned, v_organiser, array['returned'], 'under_review', v_version, 'Attendance is now 40', 'resubmitted');
    if not found then raise exception 'EFFECTS FAIL AC12: the returned event was not resubmitted'; end if;
    if v_row.status::text <> 'under_review' or v_row.coordinator_id <> v_new then
        raise exception 'EFFECTS FAIL AC12: resubmitted to % in % instead of % in under_review',
            v_row.coordinator_id, v_row.status, v_new;
    end if;
    select count(*) into v_count from public.notifications
     where event_id = v_returned and recipient_id = v_new and type = 'event_resubmitted';
    if v_count <> 1 then raise exception 'EFFECTS FAIL AC12: the new coordinator was told % times of the resubmission', v_count; end if;
    select count(*) into v_count from public.notifications
     where event_id = v_returned and recipient_id = v_old and type = 'event_resubmitted';
    if v_count <> 0 then raise exception 'EFFECTS FAIL AC12: the previous coordinator was told of the resubmission'; end if;

    -- AC13: assigned before the Lead role existed (assigned_by null); reassigning makes it this Lead's.
    select version into v_version from public.events where id = v_legacy;
    select * into v_row from public.reassign_event(
        v_legacy, v_lead, v_new, v_version, v_statuses, 'assigned', 'previous', 'organiser');
    if not found then raise exception 'EFFECTS FAIL AC13: the event assigned before Leads was not reassigned'; end if;
    if v_row.assigned_by <> v_lead or v_row.coordinator_id <> v_new or v_row.status::text <> 'planning' then
        raise exception 'EFFECTS FAIL AC13: assigner, coordinator or status wrong: %', row_to_json(v_row);
    end if;

    -- AC1/AC5/AC6 at the database: one coordinator column, and only a coordinator can be the target.
    select version into v_version from public.events where id = v_race;
    select count(*) into v_count from public.reassign_event(
        v_race, v_lead, v_organiser, v_version, v_statuses, 'assigned', 'previous', 'organiser');
    if v_count <> 0 then raise exception 'EFFECTS FAIL AC5: an account without the coordinator role was assigned'; end if;
    if (select coordinator_id from public.events where id = v_race) <> v_old then
        raise exception 'EFFECTS FAIL AC5/AC6: the event lost its coordinator on a refused reassignment';
    end if;

    raise notice 'REASSIGNMENT EFFECTS CHECKS PASSED';
end;
$$;

rollback;
