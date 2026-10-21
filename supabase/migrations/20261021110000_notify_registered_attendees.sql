-- =============================================================================
-- ConnectSphere - SCRUM-53 Attendee notifications: the helper other stories call
--
-- 53 AC1: a registered attendee is told, in the app, when the event they are
-- registered for changes or is cancelled, and (AC5) when their own registration
-- changes. Whoever builds the change or cancel (37, 115), a confirmed
-- replacement venue (53 AC6) or a registration (43, 55, 86) calls these.
--
-- DEPENDS ON Dev 1's registrations table: public.registrations(event_id,
-- attendee_id, status) with status = 'registered' for a registered attendee.
-- If that table is named differently when it lands, change only the FROM clause
-- below. The function is plpgsql, so this migration can be pushed before the
-- table exists; calling it before then fails.
-- =============================================================================

insert into public.notification_types (type, recipient_roles) values
    ('attendee_event_changed',        '{attendee}'),
    ('attendee_event_cancelled',      '{attendee}'),
    ('attendee_registration_changed', '{attendee}'),
    ('attendee_event_reminder',       '{attendee}');

-- Waitlisted and withdrawn attendees get nothing (53 AC4), and the actor never
-- hears of their own action (NT-R1). The caller writes the message: it names the
-- event, says what changed, and for a multi-venue event names only the primary
-- venue (QA3-26). Returns how many attendees were notified.
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
          from public.registrations r
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
    'Notifies every Registered attendee of p_event (not waitlisted or withdrawn, never p_actor) and returns how many. Needs public.registrations(event_id, attendee_id, status). API-only.';

revoke execute on function public.notify_registered_attendees(uuid, text, text, uuid, text)
    from public, anon, authenticated;
grant execute on function public.notify_registered_attendees(uuid, text, text, uuid, text)
    to service_role;
