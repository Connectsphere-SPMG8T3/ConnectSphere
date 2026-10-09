-- CR-103/104: comments remain private; API-only fixed safety transitions.
create table public.event_safety_decisions (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null references public.events(id) on delete cascade,
    decision text not null check (decision in ('approved','changes_requested','arrangement_rejected','withdrawn')),
    comment text,
    reason_code text,
    affected_booking_ids uuid[] not null default '{}',
    affected_equipment_request_ids uuid[] not null default '{}',
    rejected_venue_ids uuid[] not null default '{}',
    decided_by uuid references public.profiles(id) on delete set null,
    decided_at timestamptz not null default now(),
    constraint safety_decision_comment_length check (comment is null or length(btrim(comment)) between 1 and 1000),
    constraint safety_decision_comment_required check (decision not in ('changes_requested','arrangement_rejected') or comment is not null),
    constraint safety_decision_reason_code check (
        (decision = 'withdrawn' and reason_code is not null)
        or (decision <> 'withdrawn' and reason_code is null)
    )
);
create index event_safety_decisions_event_decided_idx on public.event_safety_decisions(event_id,decided_at desc);
create index event_safety_decisions_decided_by_idx on public.event_safety_decisions(decided_by);
alter table public.event_safety_decisions enable row level security;
-- Explicit grants avoid depending on the project's default table privileges.
revoke all on public.event_safety_decisions from public,anon,authenticated;
grant select on public.event_safety_decisions to authenticated;
grant all on public.event_safety_decisions to service_role;
create policy safety_decisions_select_officer_or_assigned_coordinator
on public.event_safety_decisions for select to authenticated using (
    (select private.current_user_role()) = 'safety_officer'
    or ((select private.current_user_role()) = 'event_coordinator' and exists (
        select 1 from public.events e
        where e.id = event_safety_decisions.event_id and e.coordinator_id = (select auth.uid())
    ))
);

create function public.safety_approve_event(
    p_event_id uuid, p_actor_id uuid, p_expected_version integer,
    p_comment text, p_organiser_message text, p_staff_message text
) returns setof public.events
language plpgsql security definer set search_path = '' as $$
declare v_after public.events;
begin
    -- Serialise decisions before inspecting arrangements. Lock booking rows too,
    -- so an existing booking cannot change while approval commits.
    perform 1 from public.events where id=p_event_id
        and version=p_expected_version and status='safety_review' for update;
    if not found then return; end if;
    perform 1 from public.venue_bookings where event_id=p_event_id order by id for update;
    if not exists (select 1 from public.venue_bookings where event_id=p_event_id and status in ('held','approved','re_review'))
       or exists (select 1 from public.venue_bookings where event_id=p_event_id and status in ('held','re_review')) then
        return;
    end if;
    select * into v_after from public.transition_event(
        p_event_id,p_actor_id,array['safety_review'],'confirmed',p_expected_version,
        null,'event_safety_approved',p_organiser_message);
    if not found then return; end if;
    insert into public.event_safety_decisions(event_id,decision,comment,decided_by)
    values(p_event_id,'approved',btrim(p_comment),p_actor_id);
    -- Held roles are notification recipients, never an authorisation test.
    insert into public.notifications(recipient_id,event_id,type,message)
    select recipient,p_event_id,'event_safety_approved',p_staff_message from (
        select v_after.coordinator_id recipient
        union select ur.profile_id from public.user_roles ur where ur.role in ('venue_staff','tech_support')
    ) recipients
    where recipient is not null and recipient is distinct from p_actor_id
        and recipient is distinct from v_after.organiser_id;
    return next v_after;
end $$;

create function public.safety_return_event(
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
    select * into v_after from public.transition_event(
        p_event_id,p_actor_id,array['safety_review'],'planning',p_expected_version,null,null,null);
    if not found then return; end if;
    if p_decision='changes_requested' then
        update public.venue_bookings set status='re_review'
        where id=any(v_booking_ids) and event_id=p_event_id and status='approved';
        -- Spec §3 / Task 1 ruling: only story-24 reservations can be re-reviewed.
        update public.equipment_requests set status='re_review'
        where id=any(v_equipment_ids) and event_id=p_event_id and status='reserved';
    else
        with released as (
            update public.venue_bookings set status='released'
            where id=any(v_booking_ids) and event_id=p_event_id and status in ('held','approved','re_review')
            returning venue_id
        ) select coalesce(array_agg(distinct venue_id order by venue_id),'{}'::uuid[]) into v_rejected_venues from released;
        update public.equipment_requests set status='rejected'
        where id=any(v_equipment_ids) and event_id=p_event_id and status in ('pending','reserved','re_review');
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

create function public.return_event_to_planning(
    p_event_id uuid, p_expected_version integer, p_from_status text,
    p_reason_code text, p_coordinator_message text, p_officer_message text
) returns setof public.events
language plpgsql security definer set search_path = '' as $$
declare v_after public.events;
begin
    if p_from_status is null or p_from_status not in ('safety_review','confirmed') then
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

revoke execute on function public.safety_approve_event(uuid,uuid,integer,text,text,text) from public,anon,authenticated;
grant execute on function public.safety_approve_event(uuid,uuid,integer,text,text,text) to service_role;
revoke execute on function public.safety_return_event(uuid,uuid,integer,text,text,uuid[],uuid[],text) from public,anon,authenticated;
grant execute on function public.safety_return_event(uuid,uuid,integer,text,text,uuid[],uuid[],text) to service_role;
revoke execute on function public.return_event_to_planning(uuid,integer,text,text,text,text) from public,anon,authenticated;
grant execute on function public.return_event_to_planning(uuid,integer,text,text,text,text) to service_role;
