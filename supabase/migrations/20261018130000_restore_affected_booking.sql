-- =============================================================================
-- ConnectSphere - CR-95 AC9 restore the original booking
--
-- If the original venue is free again for the booking's full occupied window
-- before a replacement is approved, venue staff can confirm the original
-- booking is restored (QA3-9, CAL-R7). Its Affected flag is cleared and any
-- pending replacement request is cancelled, with history on both.
--
-- The affected booking was never cancelled, so it still occupies its slot and
-- nothing else can have taken it: what can still be in the way is a block or a
-- deactivated venue. venue_conflicts (SCRUM-21) names them. Refused once a
-- replacement is approved, because that releases the original (AC5).
-- =============================================================================

create function public.restore_affected_booking(p_booking_id uuid, p_actor_id uuid)
returns table (outcome text, cancelled_booking_ids uuid[])
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_booking public.venue_bookings;
    v_event public.events;
    v_venue public.venues;
    v_kind text;
    v_cancelled uuid[];
    v_message text;
begin
    select * into v_booking from public.venue_bookings where id = p_booking_id for update;
    if not found then
        return query select 'booking_not_found'::text, null::uuid[];
        return;
    end if;
    if v_booking.flag is distinct from 'affected' or v_booking.status not in ('held', 'approved') then
        return query select 'not_affected'::text, null::uuid[];
        return;
    end if;
    if exists (
        select 1 from public.venue_bookings r
        where r.replaces_booking_id = v_booking.id and r.status = 'approved'
    ) then
        return query select 'replacement_approved'::text, null::uuid[];
        return;
    end if;

    select * into v_venue from public.venues where id = v_booking.venue_id for share;
    if not v_venue.is_active then
        return query select 'venue_inactive'::text, null::uuid[];
        return;
    end if;

    select c.kind into v_kind
      from public.venue_conflicts(v_booking.occupied_period, v_booking.venue_id, v_booking.id) c
     limit 1;
    if v_kind is not null then
        return query select case when v_kind = 'block' then 'still_blocked' else 'held_by_other' end, null::uuid[];
        return;
    end if;

    -- Cancel the pending replacement first, so the space's single active slot
    -- is free when the original's flag is cleared.
    with cancelled as (
        update public.venue_bookings r
           set status = 'cancelled'
         where r.replaces_booking_id = v_booking.id and r.status in ('held', 're_review')
        returning r.id, r.status as new_status
    ), history as (
        insert into public.venue_booking_history (booking_id, actor_id, action, from_status, to_status)
        select r.id, p_actor_id, 'cancelled_for_restore', old.status, 'cancelled'
          from cancelled r
          join public.venue_bookings old on old.id = r.id
        returning booking_id
    )
    select coalesce(array_agg(id), '{}') into v_cancelled from cancelled;

    update public.venue_bookings
       set flag = null, flag_reason = null, flagged_at = null
     where id = v_booking.id;

    insert into public.venue_booking_history (booking_id, actor_id, action, from_status, to_status)
    values (v_booking.id, p_actor_id, 'restored', v_booking.status, v_booking.status);

    select * into v_event from public.events where id = v_booking.event_id;
    v_message := 'The venue booking at "' || v_venue.name || '" for "' || v_event.name
        || '" has been restored by venue staff. Any replacement request was cancelled.';
    insert into public.notifications (recipient_id, event_id, type, message)
    select recipient, v_event.id, 'venue_booking_restored', v_message
      from unnest(array[v_event.coordinator_id, v_event.organiser_id]) as recipient
     where recipient is not null;

    return query select 'ok'::text, v_cancelled;
end;
$$;

comment on function public.restore_affected_booking(uuid, uuid) is
    'CR-95 AC9: venue staff restore an affected booking once its venue is free for the full occupied window: clears the flag, cancels a pending replacement, history on both, tells the coordinator and organiser. Returns an outcome code, never raises. API-only.';

revoke execute on function public.restore_affected_booking(uuid, uuid) from public, anon, authenticated;
grant execute on function public.restore_affected_booking(uuid, uuid) to service_role;
