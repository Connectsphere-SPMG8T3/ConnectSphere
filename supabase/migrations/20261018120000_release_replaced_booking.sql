-- =============================================================================
-- ConnectSphere - CR-95 AC5 release the booking a replacement replaces
--
-- When a replacement booking is approved, the affected booking it stands in for
-- is released and the history records both. Story 36's approve is the caller
-- and does not exist yet, so it must call this in the same step as approving
-- (IMPLEMENTATION_MAP). Idempotent: asking again changes and writes nothing.
-- The released booking keeps its Affected flag, as the record of why.
-- =============================================================================

create function public.release_replaced_booking(p_booking_id uuid, p_actor_id uuid default null)
returns table (outcome text, released_booking_id uuid)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_replacement public.venue_bookings;
    v_original public.venue_bookings;
begin
    select * into v_replacement from public.venue_bookings where id = p_booking_id for update;
    if not found then
        return query select 'booking_not_found'::text, null::uuid;
        return;
    end if;
    if v_replacement.replaces_booking_id is null then
        return query select 'not_a_replacement'::text, null::uuid;
        return;
    end if;
    if v_replacement.status <> 'approved' then
        return query select 'not_approved'::text, null::uuid;
        return;
    end if;

    select * into v_original from public.venue_bookings where id = v_replacement.replaces_booking_id for update;
    if not found or v_original.status = 'released' then
        return query select 'already_released'::text, v_original.id;
        return;
    end if;

    update public.venue_bookings set status = 'released' where id = v_original.id;

    insert into public.venue_booking_history (booking_id, actor_id, action, from_status, to_status)
    values
        (v_original.id, p_actor_id, 'released_for_replacement', v_original.status, 'released'),
        (v_replacement.id, p_actor_id, 'replacement_approved', v_replacement.status, v_replacement.status);

    return query select 'ok'::text, v_original.id;
end;
$$;

comment on function public.release_replaced_booking(uuid, uuid) is
    'CR-95 AC5: releases the affected booking an approved replacement stands in for, with a history row on each. Story 36''s approve calls it. Returns an outcome code, never raises. API-only.';

revoke execute on function public.release_replaced_booking(uuid, uuid) from public, anon, authenticated;
grant execute on function public.release_replaced_booking(uuid, uuid) to service_role;
