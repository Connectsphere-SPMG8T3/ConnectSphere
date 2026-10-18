-- =============================================================================
-- ConnectSphere - SCRUM-36 venue staff approve a booking request
--
-- Venue staff approve a `held` booking (REQUIREMENTS 6.13). The approved
-- booking keeps occupying the venue: DB-1 (venue_bookings_no_overlap) counts
-- held, approved and re_review alike, so approval can't double-book (AC5,
-- BA-R1). Until CR-100/21 add setup and turnaround, the occupied window is the
-- booking's own period.
--
-- Depends on CR-99 (20261012120001: venue_booking_history and
-- lock_hold_for_approval), SCRUM-38 (20261012140000: decided_by, decided_at)
-- and SCRUM-64 (20261016130000: venues.is_active).
--
-- approve_venue_booking is API-only (ADR-0002): the API checks the active role
-- (AC8), and the function decides under CR-99's lock on the booking row, the
-- same lock reject_venue_booking and the expiry job take, so an approval
-- racing either of them is refused rather than overwritten (AC9).
-- =============================================================================

create or replace function public.approve_venue_booking(
    p_booking_id uuid,
    p_actor_id uuid,
    p_notify_message text
)
returns table (outcome text, event_id uuid, from_status public.venue_booking_status)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_lock text;
    v_booking public.venue_bookings;
    v_venue_active boolean;
    v_coordinator uuid;
begin
    -- AC6, AC9: CR-99's guard locks the booking row for the rest of this
    -- transaction, and expires a hold already past its expiry instead of
    -- letting the approval through.
    v_lock := public.lock_hold_for_approval(p_booking_id);
    if v_lock = 'booking_not_found' then
        return query select 'booking_not_found'::text, null::uuid, null::public.venue_booking_status;
        return;
    end if;

    select * into v_booking from public.venue_bookings vb where vb.id = p_booking_id;
    if v_lock = 'hold_expired' then
        return query select 'hold_expired'::text, v_booking.event_id, 'expired'::public.venue_booking_status;
        return;
    end if;
    if v_lock <> 'ok' then
        return query select 'not_held'::text, v_booking.event_id, v_booking.status;
        return;
    end if;

    -- AC4: SCRUM-64 leaves a deactivated venue's holds held (and flagged), so
    -- approval re-checks it. The shared lock serialises this against
    -- deactivate_venue's update, as in request_venue_booking.
    select v.is_active into v_venue_active from public.venues v where v.id = v_booking.venue_id for share;
    if not coalesce(v_venue_active, false) then
        return query select 'venue_inactive'::text, v_booking.event_id, v_booking.status;
        return;
    end if;

    -- AC3: a block may be saved over an existing hold (CAL-R1), and DB-1 can't
    -- see blocks, so approval checks for one here.
    if exists (
        select 1
        from public.venue_blocks b
        where b.venue_id = v_booking.venue_id
          and b.blocked_period && v_booking.occupied_period
    ) then
        return query select 'venue_blocked'::text, v_booking.event_id, v_booking.status;
        return;
    end if;

    -- AC2, AC5, AC7: only this booking changes, and it keeps its slot.
    update public.venue_bookings vb
    set status = 'approved',
        decided_by = p_actor_id,
        decided_at = now(),
        updated_at = now()
    where vb.id = p_booking_id;

    -- AC10.
    insert into public.venue_booking_history
        (booking_id, actor_id, action, from_status, to_status, old_expires_at, new_expires_at)
    values (p_booking_id, p_actor_id, 'approved', 'held', 'approved', v_booking.expires_at, v_booking.expires_at);

    -- AC2: the event's assigned coordinator is told, in this transaction
    -- (NT-R3), never the actor (NT-R1).
    select e.coordinator_id into v_coordinator from public.events e where e.id = v_booking.event_id;
    if v_coordinator is not null and v_coordinator <> p_actor_id then
        insert into public.notifications (recipient_id, event_id, type, message)
        values (v_coordinator, v_booking.event_id, 'venue_booking_approved', p_notify_message);
    end if;

    return query select 'ok'::text, v_booking.event_id, 'held'::public.venue_booking_status;
end;
$$;

comment on function public.approve_venue_booking is
    'Venue staff approve a held booking (SCRUM-36); refuses an expired hold, a deactivated venue or an overlapping block, records history and notifies the assigned coordinator. Returns an outcome code instead of raising. API-only.';

revoke execute on function public.approve_venue_booking(uuid, uuid, text) from public, anon, authenticated;
grant execute on function public.approve_venue_booking(uuid, uuid, text) to service_role;
