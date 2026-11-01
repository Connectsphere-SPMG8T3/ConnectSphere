-- =============================================================================
-- ConnectSphere - D71: a Preparation event returns to Planning too
--
-- CR-104 AC10 returns an event to Planning when an arrangement stops being
-- ready. Since CR-109/CR-110 a confirmed event moves on to Preparation, which
-- this function refused, so an equipment line marked Not available or a cleared
-- exit check left a Preparation event where it was. Body as in 20261009110000,
-- with 'preparation' accepted as a source; Safety Officers are still told only
-- for a withdrawal from safety_review. Signature and grants unchanged.
-- =============================================================================

create or replace function public.return_event_to_planning(
    p_event_id uuid, p_expected_version integer, p_from_status text,
    p_reason_code text, p_coordinator_message text, p_officer_message text
) returns setof public.events
language plpgsql security definer set search_path = '' as $$
declare v_after public.events;
begin
    if p_from_status is null or p_from_status not in ('safety_review','confirmed','preparation') then
        raise exception 'Invalid safety withdrawal source status' using errcode='22023';
    end if;
    select * into v_after from public.transition_event(
        p_event_id,null,array[p_from_status],'planning',p_expected_version,null,null,null);
    if not found then return; end if;
    insert into public.event_safety_decisions(event_id,decision,reason_code,decided_by)
    values(p_event_id,'withdrawn',p_reason_code,null);
    -- UNION prevents duplicates when the coordinator also holds safety_officer.
    insert into public.notifications(recipient_id,event_id,type,message)
    select recipient,p_event_id,'event_returned_to_planning',
        case when recipient=v_after.coordinator_id then p_coordinator_message else p_officer_message end
    from (
        select v_after.coordinator_id recipient
        union select ur.profile_id from public.user_roles ur
        where p_from_status='safety_review' and ur.role='safety_officer'
    ) recipients where recipient is not null;
    return next v_after;
end $$;
