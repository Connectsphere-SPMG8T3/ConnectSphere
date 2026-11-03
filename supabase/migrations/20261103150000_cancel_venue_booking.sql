-- =============================================================================
-- ConnectSphere - SCRUM-85 the coordinator cancels a venue booking
--
-- The assigned coordinator cancels one of their event's held, approved or
-- re-review bookings (BR-R5, QA2-13), Affected or not, including a pending
-- replacement. `cancelled` doesn't occupy, so the whole occupied window,
-- setup and turnaround included, is free at once unless something else
-- covers it (AC1). Every venue staff account is told (AC1), the cancellation
-- is recorded in the booking's history (AC6), and an event in Safety review,
-- Confirmed or Preparation goes back to Planning in the same transaction
-- through CR-104's return_event_to_planning (AC4, AC8). The event's other
-- bookings are left alone (AC7, QA3-27).
-- =============================================================================

insert into public.notification_types (type, recipient_roles) values
    ('venue_booking_cancelled', '{venue_staff}');

-- AC9: the event row is locked first, the order cancel_event and
-- transition_event take, then a replacement's original, the order approve and
-- restore take, then the booking itself through CR-99's guard. An approval,
-- restore or expiry of the same booking either finishes first, and this sees
-- its result, or waits; a second cancel sees `cancelled` and is refused, so a
-- double-click records one cancellation. event_id and replaces_booking_id
-- never change after the request, so reading them unlocked is safe.
create function public.cancel_venue_booking(
    p_booking_id uuid,
    p_actor_id uuid,
    p_staff_message text,
    p_return_message text,
    p_now timestamptz default now()
)
returns table (outcome text, event_id uuid, from_status public.venue_booking_status)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event_id uuid;
    v_replaces uuid;
    v_event public.events;
    v_lock text;
    v_booking public.venue_bookings;
begin
    select vb.event_id, vb.replaces_booking_id into v_event_id, v_replaces
      from public.venue_bookings vb where vb.id = p_booking_id;
    if not found then
        return query select 'booking_not_found'::text, null::uuid, null::public.venue_booking_status;
        return;
    end if;

    select * into v_event from public.events e where e.id = v_event_id for update;

    -- AC5: the API checked this; re-checked under the lock in case the event
    -- was reassigned in between.
    if v_event.coordinator_id is distinct from p_actor_id then
        return query select 'not_assigned'::text, v_event_id, null::public.venue_booking_status;
        return;
    end if;

    -- AC10: not once the event has started, ended or been cancelled. A
    -- rejected event's bookings are already released, so it is closed too.
    if v_event.status in ('cancelled', 'completed', 'rejected')
       or (v_event.starts_at is not null and v_event.starts_at <= p_now) then
        return query select 'event_closed'::text, v_event_id, null::public.venue_booking_status;
        return;
    end if;

    if v_replaces is not null then
        perform 1 from public.venue_bookings vb where vb.id = v_replaces for update;
    end if;

    -- CR-99: a hold already past its expiry is expired, not cancelled.
    v_lock := public.lock_hold_for_approval(p_booking_id, p_now);
    select * into v_booking from public.venue_bookings vb where vb.id = p_booking_id;
    if v_lock = 'hold_expired' then
        return query select 'hold_expired'::text, v_event_id, 'expired'::public.venue_booking_status;
        return;
    end if;
    -- AC3 and [Assumption] REQUIREMENTS §9: held, approved and re_review can be
    -- cancelled; rejected, cancelled, released and expired can't.
    if v_booking.status not in ('held', 'approved', 're_review') then
        return query select 'not_cancellable'::text, v_event_id, v_booking.status;
        return;
    end if;

    -- AC1: no longer occupying, so venue_conflicts and search see it free.
    update public.venue_bookings vb
       set status = 'cancelled', updated_at = p_now
     where vb.id = p_booking_id;

    -- AC6: who cancelled it and when.
    insert into public.venue_booking_history
        (booking_id, actor_id, action, from_status, to_status, old_expires_at, new_expires_at, created_at)
    values (p_booking_id, p_actor_id, 'cancelled', v_booking.status, 'cancelled',
            v_booking.expires_at, v_booking.expires_at, p_now);

    -- AC1: venue staff work as a pool (AUTH-R5), so every holder of the role is
    -- told (§9 item 92), never the actor (NT-R1), who may also hold venue_staff.
    insert into public.notifications (recipient_id, event_id, type, message)
    select ur.profile_id, v_event_id, 'venue_booking_cancelled', p_staff_message
      from public.user_roles ur
     where ur.role = 'venue_staff'
       and ur.profile_id <> p_actor_id;

    -- AC4, AC8: the venue is no longer ready, so an event past Planning goes
    -- back to it (its history row is the event's record, AC6), taking it out of
    -- the safety queue with the Safety Officers told. Planning and review are
    -- left as they are.
    if v_event.status in ('safety_review', 'confirmed', 'preparation') then
        perform public.return_event_to_planning(
            v_event_id, v_event.version, v_event.status::text, 'booking_cancelled',
            p_return_message,
            case when v_event.status = 'safety_review' then p_return_message end);
    end if;

    return query select 'ok'::text, v_event_id, v_booking.status;
end;
$$;

comment on function public.cancel_venue_booking(uuid, uuid, text, text, timestamptz) is
    'SCRUM-85: the assigned coordinator cancels a held, approved or re-review booking: frees its occupied window, records history, tells venue staff, and returns a Safety review, Confirmed or Preparation event to Planning, in one transaction. Returns an outcome code, never raises. API-only.';

revoke execute on function public.cancel_venue_booking(uuid, uuid, text, text, timestamptz) from public, anon, authenticated;
grant execute on function public.cancel_venue_booking(uuid, uuid, text, text, timestamptz) to service_role;
