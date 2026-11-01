-- =============================================================================
-- ConnectSphere - SCRUM-53 AC5, AC1/AC3/AC6: attendee notices for their own
-- registration status, and for an approved replacement venue
--
-- Two triggers, so every path that changes a status or approves a replacement
-- sends the notice in its own transaction (NT-R3) without redefining the
-- functions that make the change.
--
-- Registration status (AC5): register_for_event, accept_waitlist_invitation,
-- leave_waitlist, withdraw_registration and the invitation expiry all change
-- event_registrations.status. Each change sends the attendee a short
-- confirmation. [Team decision] this is an exception to NT-R1: the attendee is
-- often the actor, and add_notification is called without one so the notice
-- isn't dropped. `invited` keeps SCRUM-86's own invitation notice, and
-- `cancelled` story 115's cancellation notice, so neither sends a second one.
--
-- Replacement venue (AC1, AC6, QA3-7): attendees hear nothing while a booking
-- is only flagged. When venue staff approve a CR-95 replacement in another
-- venue, Registered attendees are told the new venue. For a multi-venue event
-- they see only the primary venue (AC3, QA3-26, CR-97 AC9), so replacing a
-- secondary space while a primary is set tells them nothing.
-- =============================================================================

create function private.notify_registration_status_change()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_name text;
    v_position integer;
    v_message text;
begin
    if tg_op = 'UPDATE' and old.status is not distinct from new.status then
        return new;
    end if;

    select e.name into v_name from public.events e where e.id = new.event_id;

    if new.status = 'registered' then
        v_message := 'You''re registered for "' || v_name || '".';
    elsif new.status = 'waitlisted' then
        select count(*) into v_position
          from public.event_registrations r
         where r.event_id = new.event_id and r.status = 'waitlisted'
           and r.waitlist_order <= new.waitlist_order;
        v_message := '"' || v_name || '" is full. You''re number ' || v_position || ' on the waiting list.';
    elsif new.status = 'withdrawn' then
        v_message := 'You''ve withdrawn from "' || v_name || '".';
    elsif new.status = 'left' then
        v_message := 'You''ve left the waiting list for "' || v_name || '".';
    elsif new.status = 'invitation_expired' then
        v_message := 'Your reserved place for "' || v_name || '" has expired.';
    else
        return new;
    end if;

    perform public.add_notification(new.attendee_id, new.event_id, 'attendee_registration_changed', v_message);
    return new;
end;
$$;

create trigger event_registrations_notify_status_change
    after insert or update of status on public.event_registrations
    for each row
    execute function private.notify_registration_status_change();

create function private.notify_attendees_of_replacement_venue()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_original_venue uuid;
    v_name text;
    v_venue text;
begin
    select vb.venue_id into v_original_venue from public.venue_bookings vb where vb.id = new.replaces_booking_id;
    if v_original_venue is not distinct from new.venue_id then
        return new;
    end if;

    if new.event_space_request_id is not null
       and exists (select 1 from public.event_space_requests s where s.event_id = new.event_id and s.is_primary)
       and not exists (select 1 from public.event_space_requests s
                        where s.id = new.event_space_request_id and s.is_primary) then
        return new;
    end if;

    select e.name into v_name from public.events e where e.id = new.event_id;
    select v.name into v_venue from public.venues v where v.id = new.venue_id;
    perform public.notify_registered_attendees(
        new.event_id, 'attendee_event_changed',
        'The venue for "' || v_name || '" has changed to ' || v_venue || '.',
        null, 'venue-replaced:' || new.id::text);
    return new;
end;
$$;

create trigger venue_bookings_notify_attendees_of_replacement
    after update of status on public.venue_bookings
    for each row
    when (old.status = 'held' and new.status = 'approved' and new.replaces_booking_id is not null)
    execute function private.notify_attendees_of_replacement_venue();

revoke all on function private.notify_registration_status_change() from public, anon, authenticated;
revoke all on function private.notify_attendees_of_replacement_venue() from public, anon, authenticated;

comment on function private.notify_registration_status_change() is
    'SCRUM-53 AC5: sends the attendee a confirmation when their registration becomes registered, waitlisted (with their position), withdrawn, left or invitation_expired. Invited and cancelled have their own notices.';
comment on function private.notify_attendees_of_replacement_venue() is
    'SCRUM-53 AC1/AC3/AC6: when a CR-95 replacement in another venue is approved, tells Registered attendees the new venue, unless it replaces a secondary space while a primary is set.';
