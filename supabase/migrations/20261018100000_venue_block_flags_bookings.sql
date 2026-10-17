-- =============================================================================
-- ConnectSphere - CR-95 a venue block flags the bookings it overlaps
--
-- A block may overlap an existing hold or booking (CAL-R1), and the booking is
-- not cancelled. Saving a block now flags every held or approved booking its
-- period overlaps as Affected, with the block's reason, through SCRUM-64's
-- flag_venue_bookings (which notifies each event's coordinator once, skips
-- bookings that have ended, and never overwrites a flag another story set).
-- Done in a trigger so it holds for whichever path writes the block, in the
-- same transaction as the block itself. The event's status is not touched
-- (CR-95 AC7); the flag is never cleared here (REQUIREMENTS §9).
-- =============================================================================

create or replace function private.flag_bookings_under_block()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_venue_name text;
    v_event_id uuid;
begin
    select name into v_venue_name from public.venues where id = new.venue_id;

    -- flag_venue_bookings returns only the events it flagged just now, so a
    -- booking flagged earlier is not announced again (CR-95 AC3).
    for v_event_id in
        select public.flag_venue_bookings(
            new.venue_id,
            new.blocked_period,
            'affected',
            'Venue unavailable: ' || new.reason::text,
            'Venue "' || coalesce(v_venue_name, 'unknown') || '" is unavailable (' || new.reason::text
                || ') during your event''s booking. Review it and arrange an alternative venue.'
        )
    loop
        insert into public.notifications (recipient_id, event_id, type, message)
        select e.organiser_id, e.id, 'venue_unavailable_organiser',
               'The venue "' || coalesce(v_venue_name, 'unknown') || '" is unavailable (' || new.reason::text
                   || ') during your event. Your event is not cancelled: your coordinator will arrange an alternative venue and update you.'
          from public.events e
         where e.id = v_event_id;
    end loop;
    return new;
end;
$$;

comment on function private.flag_bookings_under_block() is
    'CR-95 AC1: flags the held and approved bookings a venue block overlaps as Affected. Trigger-only.';

revoke execute on function private.flag_bookings_under_block() from public, anon, authenticated;

create trigger venue_blocks_flag_bookings
    after insert or update of blocked_period, venue_id
    on public.venue_blocks
    for each row execute function private.flag_bookings_under_block();
