-- =============================================================================
-- ConnectSphere - SCRUM-53 AC4 and SCRUM-90: scheduled in-app reminders
--
-- Two functions, run by pg_cron like expire-venue-holds, insert ordinary
-- notifications. A dedupe key makes a re-run (cron overlap, restart, a manual
-- run) a no-op, so nobody is reminded twice.
--
-- Rows name their role explicitly: a person can be both the event's coordinator
-- and venue staff (the seeded coordinator is), and each reminder must land in the
-- role it is for.
--
-- 53 AC4: 24 hours before an event starts, each Registered attendee. Needs Dev 1's
--   public.registrations(event_id, attendee_id, status). The job runs from the
--   day this is pushed, so until the table exists the function returns 0.
-- 90 AC1 and AC2: staff, about events still in Planning or Safety review (any
--   other status has its arrangements done or the event is over).
-- [Assumption] 90 AC3 leaves "a set time" open and the customer set no timing
--   (Session 1): remind once a day, from 3 days before the event starts, while it
--   is still in Planning or Safety review. Confirm in planning poker.
-- =============================================================================

insert into public.notification_types (type, recipient_roles) values
    ('staff_arrangement_reminder', '{event_coordinator,venue_staff,tech_support}')
on conflict (type) do nothing;

-- 53 AC4 ---------------------------------------------------------------------------
-- Waitlisted and withdrawn attendees get nothing; neither does a draft, rejected,
-- cancelled or completed event. For a multi-venue event the primary venue is named
-- (QA3-26). One reminder per attendee per event, whenever the job first sees the
-- event inside its 24 hours.
create or replace function public.send_attendee_event_reminders()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_count integer;
begin
    -- The job is scheduled below and runs every 15 minutes, possibly before Dev 1's
    -- table exists: do nothing then, rather than fail and log 96 errors a day.
    if to_regclass('public.registrations') is null then
        return 0;
    end if;

    with due as (
        select e.id,
               coalesce(e.name, 'Your event') as name,
               e.starts_at,
               e.event_timezone,
               (select v.name
                  from public.venue_bookings vb
                  join public.venues v on v.id = vb.venue_id
                  left join public.event_space_requests es on es.id = vb.event_space_request_id
                 where vb.event_id = e.id and vb.status = 'approved'
                 order by coalesce(es.is_primary, false) desc, vb.created_at
                 limit 1) as venue_name
          from public.events e
         where e.starts_at > now()
           and e.starts_at <= now() + interval '24 hours'
           and e.status not in ('draft', 'rejected', 'cancelled', 'completed')
    ), inserted as (
        insert into public.notifications (recipient_id, event_id, type, message, recipient_role, dedupe_key)
        select r.attendee_id,
               d.id,
               'attendee_event_reminder',
               'Reminder: "' || d.name || '" starts '
                   || to_char(d.starts_at at time zone d.event_timezone, 'DD Mon YYYY, HH12:MI AM')
                   || ' at ' || coalesce(d.venue_name, 'a venue to be confirmed') || '.',
               'attendee',
               'reminder-24h:' || d.id
          from due d
          join public.registrations r on r.event_id = d.id and r.status = 'registered'
        on conflict (recipient_id, dedupe_key) where dedupe_key is not null do nothing
        returning 1
    )
    select count(*) into v_count from inserted;
    return v_count;
end;
$$;

comment on function public.send_attendee_event_reminders is
    '53 AC4: a reminder notification for each Registered attendee of an event starting within 24 hours, once per attendee and event. Returns how many were inserted. Run by pg_cron every 15 minutes. API-only.';

-- 90 AC1 and AC2 -------------------------------------------------------------------
-- The assigned coordinator for every such event; every venue staff member when a
-- venue booking is waiting on them (held or under re-review); every technical
-- support member when an equipment line is waiting on them (pending or under
-- re-review). The text names the event and its date only: nothing internal.
create or replace function public.send_staff_arrangement_reminders()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_today text := to_char(now() at time zone 'Asia/Singapore', 'YYYY-MM-DD');
    v_count integer;
begin
    with due as (
        select e.id,
               coalesce(e.name, 'Your event') as name,
               e.coordinator_id,
               to_char(e.starts_at at time zone e.event_timezone, 'DD Mon YYYY') as starts_on,
               exists (select 1 from public.venue_bookings vb
                        where vb.event_id = e.id and vb.status in ('held', 're_review')) as venue_waiting,
               exists (select 1 from public.equipment_requests q
                        where q.event_id = e.id and q.status in ('pending', 're_review')) as tech_waiting
          from public.events e
         where e.status in ('planning', 'safety_review')
           and e.starts_at > now()
           and e.starts_at <= now() + interval '3 days'
    ), to_coordinator as (
        insert into public.notifications (recipient_id, event_id, type, message, recipient_role, dedupe_key)
        select d.coordinator_id, d.id, 'staff_arrangement_reminder',
               'Arrangements for "' || d.name || '" are still incomplete and it starts ' || d.starts_on || '.',
               'event_coordinator',
               'staff-reminder:coordinator:' || d.id || ':' || v_today
          from due d
         where d.coordinator_id is not null
        on conflict (recipient_id, dedupe_key) where dedupe_key is not null do nothing
        returning 1
    ), to_venue_staff as (
        insert into public.notifications (recipient_id, event_id, type, message, recipient_role, dedupe_key)
        select ur.profile_id, d.id, 'staff_arrangement_reminder',
               '"' || d.name || '" starts ' || d.starts_on || ' and is waiting on a venue booking decision.',
               'venue_staff',
               'staff-reminder:venue:' || d.id || ':' || v_today
          from due d
          join public.user_roles ur on ur.role = 'venue_staff'
         where d.venue_waiting
        on conflict (recipient_id, dedupe_key) where dedupe_key is not null do nothing
        returning 1
    ), to_tech_support as (
        insert into public.notifications (recipient_id, event_id, type, message, recipient_role, dedupe_key)
        select ur.profile_id, d.id, 'staff_arrangement_reminder',
               '"' || d.name || '" starts ' || d.starts_on || ' and has equipment requests waiting on Technical Support.',
               'tech_support',
               'staff-reminder:tech:' || d.id || ':' || v_today
          from due d
          join public.user_roles ur on ur.role = 'tech_support'
         where d.tech_waiting
        on conflict (recipient_id, dedupe_key) where dedupe_key is not null do nothing
        returning 1
    )
    select (select count(*) from to_coordinator)
         + (select count(*) from to_venue_staff)
         + (select count(*) from to_tech_support)
      into v_count;
    return v_count;
end;
$$;

comment on function public.send_staff_arrangement_reminders is
    '90 AC1/AC2: once a day, a reminder to the coordinator of each Planning or Safety review event starting within 3 days, and to venue staff and technical support when a request is waiting on them. Returns how many were inserted. Run by pg_cron at 01:00 UTC (09:00 Singapore). API-only.';

revoke execute on function public.send_attendee_event_reminders() from public, anon, authenticated;
grant execute on function public.send_attendee_event_reminders() to service_role;
revoke execute on function public.send_staff_arrangement_reminders() from public, anon, authenticated;
grant execute on function public.send_staff_arrangement_reminders() to service_role;

-- The schedule lives in the database beside the data it reads, as for hold expiry.
-- cron.schedule replaces a job of the same name, so this can be re-run.
create extension if not exists pg_cron with schema pg_catalog;

select cron.schedule('attendee-event-reminders', '*/15 * * * *', 'select public.send_attendee_event_reminders()');
select cron.schedule('staff-arrangement-reminders', '0 1 * * *', 'select public.send_staff_arrangement_reminders()');
