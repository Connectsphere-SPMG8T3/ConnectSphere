-- CR-104 AC2/AC3, QA3-46/QA3-47, SF-R3/SF-R4, LC-R7:
-- request changes preserves arrangements; reject flags one booking, never releases it.
-- New enum values are only used inside plpgsql bodies until this migration commits.
alter type public.venue_booking_flag add value 'safety_rejected';

create or replace function public.safety_return_event(
    p_event_id uuid, p_actor_id uuid, p_expected_version integer,
    p_decision text, p_comment text, p_booking_ids uuid[],
    p_equipment_request_ids uuid[], p_coordinator_message text
) returns setof public.events
language plpgsql security definer set search_path = '' as $$
declare
    v_after public.events;
    v_booking_ids uuid[];
    v_equipment_ids uuid[];
    v_rejected_venues uuid[] := '{}';
begin
    if p_decision is null or p_decision not in ('changes_requested','arrangement_rejected') then
        raise exception 'Invalid safety decision' using errcode='22023';
    end if;
    perform 1 from public.events where id=p_event_id
        and version=p_expected_version and status='safety_review' for update;
    if not found then return; end if;
    -- NULL arrays mean no selections; a NULL element is an invalid id.
    if exists (select 1 from unnest(p_booking_ids) requested(id)
        where not exists (select 1 from public.venue_bookings b where b.id=requested.id and b.event_id=p_event_id))
       or exists (select 1 from unnest(p_equipment_request_ids) requested(id)
        where not exists (select 1 from public.equipment_requests r where r.id=requested.id and r.event_id=p_event_id)) then
        return;
    end if;
    select coalesce(array_agg(distinct id order by id),'{}'::uuid[]) into v_booking_ids from unnest(p_booking_ids) requested(id);
    select coalesce(array_agg(distinct id order by id),'{}'::uuid[]) into v_equipment_ids from unnest(p_equipment_request_ids) requested(id);
    perform 1 from public.venue_bookings where id=any(v_booking_ids) order by id for update;
    perform 1 from public.equipment_requests where id=any(v_equipment_ids) order by id for update;
    -- Recheck after waiting for row locks (a concurrent delete/reassignment wins).
    if exists (select 1 from unnest(v_booking_ids) requested(id)
        where not exists (select 1 from public.venue_bookings b where b.id=requested.id and b.event_id=p_event_id))
       or exists (select 1 from unnest(v_equipment_ids) requested(id)
        where not exists (select 1 from public.equipment_requests r where r.id=requested.id and r.event_id=p_event_id)) then
        return;
    end if;
    if p_decision='arrangement_rejected' then
        if cardinality(v_booking_ids) <> 1 or cardinality(v_equipment_ids) <> 0 then
            raise exception 'Reject requires exactly one venue booking and no equipment' using errcode='22023';
        end if;
        if not exists (select 1 from public.venue_bookings
            where id=v_booking_ids[1] and event_id=p_event_id and status='approved' and flag is null) then
            return;
        end if;
    end if;
    select * into v_after from public.transition_event(
        p_event_id,p_actor_id,array['safety_review'],'planning',p_expected_version,null,null,null);
    if not found then return; end if;
    -- Request changes records concerned ids only; arrangements retain their state.
    if p_decision='arrangement_rejected' then
        update public.venue_bookings
        set flag='safety_rejected', flag_reason=btrim(p_comment), flagged_at=now()
        where id=v_booking_ids[1];
        insert into public.venue_booking_history(booking_id,actor_id,action,from_status,to_status)
        values(v_booking_ids[1],p_actor_id,'safety_rejected','approved','approved');
        select array[venue_id] into v_rejected_venues from public.venue_bookings where id=v_booking_ids[1];
    end if;
    insert into public.event_safety_decisions(
        event_id,decision,comment,affected_booking_ids,affected_equipment_request_ids,rejected_venue_ids,decided_by
    ) values(p_event_id,p_decision,btrim(p_comment),v_booking_ids,v_equipment_ids,v_rejected_venues,p_actor_id);
    if v_after.coordinator_id is not null and v_after.coordinator_id is distinct from p_actor_id then
        insert into public.notifications(recipient_id,event_id,type,message)
        values(v_after.coordinator_id,p_event_id,
            case when p_decision='changes_requested' then 'event_safety_changes_requested' else 'event_safety_arrangement_rejected' end,
            p_coordinator_message);
    end if;
    return next v_after;
end $$;

create function public.mark_safety_revision(p_booking_id uuid, p_actor_id uuid)
returns text language plpgsql security definer set search_path = '' as $$
declare
    v_booking public.venue_bookings;
    v_event public.events;
begin
    -- Event before booking, the same order as safety_return_event, so the two never deadlock.
    select * into v_event from public.events
    where id=(select event_id from public.venue_bookings where id=p_booking_id) for update;
    select * into v_booking from public.venue_bookings where id=p_booking_id for update;
    if not found then return 'booking_not_found'; end if;
    if v_booking.flag is distinct from 'safety_rejected' then return 'not_safety_rejected'; end if;
    if v_event.coordinator_id is distinct from p_actor_id then return 'not_assigned'; end if;
    if v_event.status <> 'planning' then return 'not_planning'; end if;
    update public.venue_bookings set flag=null, flag_reason=null, flagged_at=null where id=p_booking_id;
    insert into public.venue_booking_history(booking_id,actor_id,action,from_status,to_status)
    values(p_booking_id,p_actor_id,'safety_revised',v_booking.status,v_booking.status);
    -- [Assumption] Revision has no notification and does not bump the event version.
    return 'ok';
end $$;

comment on function public.mark_safety_revision(uuid,uuid) is
    'CR-104 AC3/AC4 [Team decision]: assigned coordinator marks a Safety-rejected booking revised in Planning. API-only.';
comment on column public.venue_bookings.flag is
    'Open follow-up: affected (CR-95/SCRUM-64), conflict or unsuitable (CR-94), safety_rejected (CR-104: the Safety Officer rejected this venue for the event; cleared by the coordinator''s Mark as revised). First flag wins. A flagged booking is not ready for safety check. Other flags are set by flag_venue_bookings.';

revoke execute on function public.safety_return_event(uuid,uuid,integer,text,text,uuid[],uuid[],text) from public,anon,authenticated;
grant execute on function public.safety_return_event(uuid,uuid,integer,text,text,uuid[],uuid[],text) to service_role;
revoke execute on function public.mark_safety_revision(uuid,uuid) from public,anon,authenticated;
grant execute on function public.mark_safety_revision(uuid,uuid) to service_role;
