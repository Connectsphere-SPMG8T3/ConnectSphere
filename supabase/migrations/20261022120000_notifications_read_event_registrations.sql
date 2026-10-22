-- =============================================================================
-- ConnectSphere - D56: attendee notifications read SCRUM-43's registrations table
--
-- 20261021110000 and 20261021120000 were written before SCRUM-43 and assumed the
-- table would be public.registrations. SCRUM-43 named it public.event_registrations
-- (migration 20261022100000), with the same event_id, attendee_id and status
-- columns and status = 'registered' for a registered attendee. These two functions
-- are redefined to read it; their signatures, behaviour and grants are unchanged.
-- Its other statuses (withdrawn, cancelled) are never notified.
-- =============================================================================

create or replace function public.notify_registered_attendees(
    p_event uuid,
    p_type text,
    p_message text,
    p_actor uuid default null,
    p_dedupe_key text default null
)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_attendee uuid;
    v_count integer := 0;
begin
    for v_attendee in
        select r.attendee_id
          from public.event_registrations r
         where r.event_id = p_event
           and r.status = 'registered'
    loop
        if public.add_notification(v_attendee, p_event, p_type, p_message, p_actor, p_dedupe_key) is not null then
            v_count := v_count + 1;
        end if;
    end loop;
    return v_count;
end;
$$;

comment on function public.notify_registered_attendees is
    'Notifies every Registered attendee of p_event (not withdrawn or cancelled, never p_actor) and returns how many. Reads public.event_registrations. API-only.';

create or replace function public.send_attendee_event_reminders()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_count integer;
begin
    -- The cron job runs every 15 minutes, including on a database built from a
    -- branch that does not have SCRUM-43's table yet: do nothing then, rather than
    -- fail and log 96 errors a day.
    if to_regclass('public.event_registrations') is null then
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
          join public.event_registrations r on r.event_id = d.id and r.status = 'registered'
        on conflict (recipient_id, dedupe_key) where dedupe_key is not null do nothing
        returning 1
    )
    select count(*) into v_count from inserted;
    return v_count;
end;
$$;
