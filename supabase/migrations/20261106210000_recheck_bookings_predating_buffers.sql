-- CR-94 AC8 (W7 CR-01): bookings made before setup and turnaround existed are
-- re-checked once, using their venue's current figures. A booking whose occupied
-- window would then overlap another booking at the venue is flagged Conflict,
-- naming that booking, and the coordinator and venue staff are told. The booking's
-- stored times and status stay as they are (CR-100 AC5, CR-94 AC6), and so does the
-- event's status.
--
-- A booking predates the rule when it was created before CR-100 started copying
-- each venue's figures into new bookings, and it stores no setup or turnaround.

create function private.flag_bookings_predating_buffers()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_booking record;
    v_clash record;
    v_flagged integer := 0;
    v_reason text;
begin
    for v_booking in
        select b.id, b.event_id, b.venue_id, b.booked_period, e.name as event_name, e.coordinator_id,
               v.name as venue_name, v.setup_minutes, v.turnaround_minutes
          from public.venue_bookings b
          join public.venues v on v.id = b.venue_id
          join public.events e on e.id = b.event_id
         where (b.status = 'approved' or (b.status = 'held' and b.expires_at > now()))
           and b.flag is null
           and b.setup_minutes = 0
           and b.turnaround_minutes = 0
           and b.created_at < timestamptz '2026-10-19 00:00+08'
           and lower(b.booked_period) > now()
           and e.status not in ('completed', 'cancelled', 'rejected')
           and (v.setup_minutes > 0 or v.turnaround_minutes > 0)
         order by lower(b.booked_period), b.id
           for update of b
    loop
        select c.event_name into v_clash
          from public.venue_conflicts(
              tstzrange(lower(v_booking.booked_period) - make_interval(mins => v_booking.setup_minutes),
                        upper(v_booking.booked_period) + make_interval(mins => v_booking.turnaround_minutes), '[)'),
              v_booking.venue_id, v_booking.id) c
         where c.kind = 'booking'
         order by lower(c.occupied_period)
         limit 1;
        continue when not found;

        v_reason := format('With the setup and turnaround at "%s", this booking would overlap "%s".',
                           v_booking.venue_name, v_clash.event_name);
        update public.venue_bookings
           set flag = 'conflict', flag_reason = v_reason, flagged_at = now()
         where id = v_booking.id;

        if v_booking.coordinator_id is not null then
            insert into public.notifications (recipient_id, event_id, type, message)
            values (v_booking.coordinator_id, v_booking.event_id, 'venue_booking_affected',
                    format('The booking for "%s" is flagged Conflict. %s', v_booking.event_name, v_reason));
        end if;
        insert into public.notifications (recipient_id, event_id, type, message)
        select ur.profile_id, v_booking.event_id, 'venue_updated_affects_booking',
               format('The booking for "%s" is flagged Conflict. %s', v_booking.event_name, v_reason)
          from public.user_roles ur
         where ur.role = 'venue_staff';

        v_flagged := v_flagged + 1;
    end loop;

    return v_flagged;
end;
$$;

revoke execute on function private.flag_bookings_predating_buffers() from public, anon, authenticated;

comment on function private.flag_bookings_predating_buffers() is
    'CR-94 AC8: flags Conflict each future booking from before setup and turnaround existed that would overlap another booking under its venue''s current figures. Returns how many it flagged.';

select private.flag_bookings_predating_buffers();
