-- SCRUM-53 AC4 and SCRUM-90: the scheduled reminders. Needs Dev 1's
-- public.event_registrations (SCRUM-43, migration 20261022100000) and migrations
-- 20261021100000 to 20261021120000 and 20261022120000. Run with the Supabase MCP execute_sql or
-- `psql "$DATABASE_URL" -f`. Raises on the first failure and returns
-- NOTIFICATION REMINDER CHECKS PASSED otherwise. Everything runs inside
-- `begin; ... rollback;`.
-- Seeded accounts: organiser …0001; coordinator …0002 (also venue staff);
-- venue staff …0003; tech support …0004; attendee …0005 (the other registration
-- rows use other accounts because the function filters on status only).
-- Reminders look at every event in the project, so each check counts only the
-- rows of its own throwaway event.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-0000000007c1', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'confirmed', 'Reminder due (rolled back)', now() + interval '23 hours', now() + interval '25 hours'),
    ('e0000000-0000-4000-8000-0000000007c2', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'confirmed', 'Reminder too far (rolled back)', now() + interval '25 hours', now() + interval '27 hours'),
    ('e0000000-0000-4000-8000-0000000007c3', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'cancelled', 'Reminder cancelled (rolled back)', now() + interval '20 hours', now() + interval '22 hours'),
    ('e0000000-0000-4000-8000-0000000007d1', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Staff incomplete (rolled back)', now() + interval '2 days', now() + interval '2 days 2 hours'),
    ('e0000000-0000-4000-8000-0000000007d2', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Staff too far (rolled back)', now() + interval '5 days', now() + interval '5 days 2 hours'),
    ('e0000000-0000-4000-8000-0000000007d3', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'confirmed', 'Staff complete (rolled back)', now() + interval '2 days', now() + interval '2 days 2 hours'),
    ('e0000000-0000-4000-8000-0000000007d4', 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
     'planning', 'Staff nothing waiting (rolled back)', now() + interval '2 days', now() + interval '2 days 2 hours');

insert into public.event_registrations (event_id, attendee_id, status, withdrawn_at)
select e.id, r.attendee_id, r.status, case when r.status = 'withdrawn' then now() end
  from (values ('e0000000-0000-4000-8000-0000000007c1'::uuid), ('e0000000-0000-4000-8000-0000000007c2'::uuid),
               ('e0000000-0000-4000-8000-0000000007c3'::uuid)) as e(id)
 cross join (values ('a0000000-0000-4000-8000-000000000005'::uuid, 'registered'),
                    ('a0000000-0000-4000-8000-000000000003'::uuid, 'cancelled'),
                    ('a0000000-0000-4000-8000-000000000002'::uuid, 'withdrawn')) as r(attendee_id, status);

-- Venue 6 is the one the other checks use. Its bookings are within the next two days only here.
insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status) values
    ('d0000000-0000-4000-8000-0000000007c1', 'e0000000-0000-4000-8000-0000000007c1', 'b0000000-0000-4000-8000-000000000006',
     tstzrange(now() + interval '23 hours', now() + interval '25 hours', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000007d1', 'e0000000-0000-4000-8000-0000000007d1', 'b0000000-0000-4000-8000-000000000006',
     tstzrange(now() + interval '2 days', now() + interval '2 days 2 hours', '[)'), 'held'),
    ('d0000000-0000-4000-8000-0000000007d3', 'e0000000-0000-4000-8000-0000000007d3', 'b0000000-0000-4000-8000-000000000007',
     tstzrange(now() + interval '2 days', now() + interval '2 days 2 hours', '[)'), 'approved'),
    ('d0000000-0000-4000-8000-0000000007d4', 'e0000000-0000-4000-8000-0000000007d4', 'b0000000-0000-4000-8000-000000000007',
     tstzrange(now() + interval '3 days', now() + interval '3 days 2 hours', '[)'), 'approved');

insert into public.equipment_requests (event_id, equipment_id, submission_id, quantity)
select 'e0000000-0000-4000-8000-0000000007d1', (select id from public.equipment order by id limit 1), gen_random_uuid(), 1;

do $$
declare
    v_att_event uuid := 'e0000000-0000-4000-8000-0000000007c1';
    v_staff_event uuid := 'e0000000-0000-4000-8000-0000000007d1';
    v_attendee uuid := 'a0000000-0000-4000-8000-000000000005';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_venue_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_tech uuid := 'a0000000-0000-4000-8000-000000000004';
    v_message text;
    v_rows integer;
begin
    -- 53 AC4: the attendee reminder.
    perform public.send_attendee_event_reminders();

    select count(*) into v_rows from public.notifications
     where event_id = v_att_event and type = 'attendee_event_reminder';
    if v_rows <> 1 then raise exception 'REMINDER FAIL: expected exactly one attendee reminder, got %', v_rows; end if;
    select message into v_message from public.notifications
     where event_id = v_att_event and type = 'attendee_event_reminder' and recipient_id = v_attendee and recipient_role = 'attendee';
    if v_message is null then raise exception 'REMINDER FAIL: the registered attendee has no reminder with role attendee'; end if;
    if v_message not like 'Reminder: "Reminder due (rolled back)" starts % at %.' then
        raise exception 'REMINDER FAIL: unexpected attendee message: %', v_message;
    end if;
    if v_message like '%a venue to be confirmed%' then
        raise exception 'REMINDER FAIL: the approved venue was not named: %', v_message;
    end if;
    if exists (select 1 from public.notifications
                where event_id in ('e0000000-0000-4000-8000-0000000007c2', 'e0000000-0000-4000-8000-0000000007c3')) then
        raise exception 'REMINDER FAIL: a reminder was sent for an event too far away or cancelled';
    end if;

    -- A re-run (cron overlap, restart) sends nothing new.
    perform public.send_attendee_event_reminders();
    select count(*) into v_rows from public.notifications where event_id = v_att_event and type = 'attendee_event_reminder';
    if v_rows <> 1 then raise exception 'REMINDER FAIL: a second run sent a duplicate (rows: %)', v_rows; end if;

    -- 90 AC1 and AC2: staff reminders.
    perform public.send_staff_arrangement_reminders();

    select message into v_message from public.notifications
     where event_id = v_staff_event and recipient_id = v_coordinator and recipient_role = 'event_coordinator'
       and type = 'staff_arrangement_reminder';
    if v_message is null then raise exception 'REMINDER FAIL: the coordinator was not reminded (AC1)'; end if;
    if v_message not like 'Arrangements for "Staff incomplete (rolled back)" are still incomplete and it starts %.' then
        raise exception 'REMINDER FAIL: unexpected coordinator message: %', v_message;
    end if;
    if (select count(*) from public.notifications
         where event_id = v_staff_event and recipient_id in (v_coordinator, v_venue_staff) and recipient_role = 'venue_staff') <> 2 then
        raise exception 'REMINDER FAIL: both venue staff (one of whom is also the coordinator) were not reminded under the venue_staff role (AC2)';
    end if;
    if (select count(*) from public.notifications
         where event_id = v_staff_event and recipient_id = v_tech and recipient_role = 'tech_support') <> 1 then
        raise exception 'REMINDER FAIL: tech support was not reminded about the waiting equipment line (AC2)';
    end if;
    select count(*) into v_rows from public.notifications where event_id = v_staff_event;
    if v_rows <> 4 then raise exception 'REMINDER FAIL: expected 4 staff reminders, got %', v_rows; end if;

    -- Too far away, complete, or nothing waiting on venue staff or tech support.
    if exists (select 1 from public.notifications
                where event_id in ('e0000000-0000-4000-8000-0000000007d2', 'e0000000-0000-4000-8000-0000000007d3')) then
        raise exception 'REMINDER FAIL: a reminder was sent for an event too far away or already confirmed';
    end if;
    select count(*) into v_rows from public.notifications where event_id = 'e0000000-0000-4000-8000-0000000007d4';
    if v_rows <> 1 then
        raise exception 'REMINDER FAIL: an incomplete event with nothing waiting on venue staff or tech support should remind only the coordinator, got % rows', v_rows;
    end if;

    -- Once a day: a re-run the same day adds nothing.
    perform public.send_staff_arrangement_reminders();
    select count(*) into v_rows from public.notifications where event_id = v_staff_event;
    if v_rows <> 4 then raise exception 'REMINDER FAIL: a second run the same day sent duplicates (rows: %)', v_rows; end if;

    -- The jobs are scheduled.
    if (select count(*) from cron.job where jobname in ('attendee-event-reminders', 'staff-arrangement-reminders')) <> 2 then
        raise exception 'REMINDER FAIL: the two cron jobs are not scheduled';
    end if;

    -- Grants: service_role only.
    if has_function_privilege('anon', 'public.send_attendee_event_reminders()', 'execute')
       or has_function_privilege('authenticated', 'public.send_attendee_event_reminders()', 'execute')
       or has_function_privilege('anon', 'public.send_staff_arrangement_reminders()', 'execute')
       or has_function_privilege('authenticated', 'public.send_staff_arrangement_reminders()', 'execute') then
        raise exception 'REMINDER FAIL: a reminder function is executable by anon or authenticated';
    end if;
end $$;

select 'NOTIFICATION REMINDER CHECKS PASSED' as result;

rollback;
