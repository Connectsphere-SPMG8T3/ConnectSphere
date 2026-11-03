-- CR-108 (QA3-17): the safety review is a structured checklist with comments for the organiser kept
-- apart from the officer's private notes.
--
--   * event_safety_checklist_items: one row per factor mark, written with its decision. The five
--     venue factors are marked for every active venue booking; equipment placement once per event.
--   * event_safety_decisions.organiser_comment: what the organiser is shown. The existing `comment`
--     column now holds the officer's PRIVATE NOTE (kept, not renamed, so history is untouched).
--   * safety_approve_event / safety_return_event take the checklist and both texts, refuse an
--     incomplete checklist (AC3) and a Concern on an approval, and record everything atomically.
--
-- Notifications stay fixed text: neither the comment nor the note is ever copied into one.

-- -----------------------------------------------------------------------------
-- Decision row: the organiser's comment
-- -----------------------------------------------------------------------------
alter table public.event_safety_decisions add column organiser_comment text;

alter table public.event_safety_decisions
    add constraint safety_decision_organiser_comment_length
    check (organiser_comment is null or length(btrim(organiser_comment)) between 1 and 1000);

-- Request changes and reject now need an organiser comment (AC4); the private note is optional.
-- NOT VALID: decisions recorded before CR-108 have a private note and no organiser comment.
alter table public.event_safety_decisions drop constraint safety_decision_comment_required;
alter table public.event_safety_decisions
    add constraint safety_decision_organiser_comment_required
    check (decision not in ('changes_requested','arrangement_rejected') or organiser_comment is not null)
    not valid;

comment on column public.event_safety_decisions.comment is
    'CR-108: the officer''s PRIVATE note. Visible only to Safety Officers and the assigned coordinator; never to the organiser, a notification or the organiser''s history.';
comment on column public.event_safety_decisions.organiser_comment is
    'CR-108 AC4/AC5: the comment shown to the organiser with the outcome.';

-- -----------------------------------------------------------------------------
-- Checklist rows
-- -----------------------------------------------------------------------------
create table public.event_safety_checklist_items (
    id uuid primary key default gen_random_uuid(),
    decision_id uuid not null references public.event_safety_decisions(id) on delete cascade,
    event_id uuid not null references public.events(id) on delete cascade,
    factor text not null check (factor in (
        'attendance_capacity','layout','emergency_access','accessibility','equipment_placement','venue_restrictions')),
    booking_id uuid references public.venue_bookings(id) on delete set null,
    rating text not null check (rating in ('satisfactory','concern','not_applicable')),
    note text check (note is null or length(btrim(note)) between 1 and 1000),
    -- Equipment placement is about the whole event; every other factor is about one venue booking.
    -- (booking_id is set null if a booking is ever deleted, so the rule only binds on insert.)
    constraint safety_checklist_booking_scope check (factor <> 'equipment_placement' or booking_id is null)
);
create unique index event_safety_checklist_items_mark_idx on public.event_safety_checklist_items(
    decision_id, factor, coalesce(booking_id, '00000000-0000-0000-0000-000000000000'::uuid));
create index event_safety_checklist_items_event_idx on public.event_safety_checklist_items(event_id);
create index event_safety_checklist_items_booking_idx on public.event_safety_checklist_items(booking_id);

comment on table public.event_safety_checklist_items is
    'CR-108 AC1/AC2/AC6: the checklist marks recorded with a safety decision. Staff only; append-only.';

alter table public.event_safety_checklist_items enable row level security;
revoke all on public.event_safety_checklist_items from public, anon, authenticated;
grant select on public.event_safety_checklist_items to authenticated;
grant all on public.event_safety_checklist_items to service_role;
create policy safety_checklist_select_officer_or_assigned_coordinator
on public.event_safety_checklist_items for select to authenticated using (
    (select private.current_user_role()) = 'safety_officer'
    or ((select private.current_user_role()) = 'event_coordinator' and exists (
        select 1 from public.events e
        where e.id = event_safety_checklist_items.event_id and e.coordinator_id = (select auth.uid())
    ))
);

-- A decision is history: its marks are never edited or removed (cascades from the event still work).
create trigger event_safety_checklist_items_append_only before update or delete on public.event_safety_checklist_items
    for each row execute function private.refuse_history_change();
revoke update, delete, truncate on public.event_safety_checklist_items from anon, authenticated;

-- -----------------------------------------------------------------------------
-- The completeness rule (AC3), shared by both decision functions
-- -----------------------------------------------------------------------------
-- Returns null when the checklist can be recorded for this decision, otherwise the first problem.
-- Active bookings are the ones the review shows: held, approved or re_review.
create function private.safety_checklist_problem(p_event_id uuid, p_checklist jsonb, p_decision text)
returns text language plpgsql stable set search_path = '' as $$
declare
    v_venue_factors constant text[] := array[
        'attendance_capacity','layout','emergency_access','accessibility','venue_restrictions'];
begin
    if p_checklist is null or jsonb_typeof(p_checklist) <> 'array' then
        return 'The checklist must be a list of marks';
    end if;
    if exists (
        select 1 from jsonb_array_elements(p_checklist) a
        where jsonb_typeof(a) <> 'object'
           or a->>'factor' is null
           or a->>'factor' not in ('attendance_capacity','layout','emergency_access','accessibility','equipment_placement','venue_restrictions')
           or a->>'rating' is null or a->>'rating' not in ('satisfactory','concern','not_applicable')
           or length(coalesce(a->>'note','')) > 1000
           or ((a->>'factor') = 'equipment_placement') <> ((a->>'booking_id') is null)
    ) then
        return 'The checklist has an unknown factor or rating, a note that is too long, or a mark on the wrong scope';
    end if;
    if exists (
        select 1 from jsonb_array_elements(p_checklist) a
        group by a->>'factor', a->>'booking_id' having count(*) > 1
    ) then
        return 'The checklist marks a factor more than once';
    end if;
    if exists (
        select 1 from jsonb_array_elements(p_checklist) a
        where a->>'booking_id' is not null and not exists (
            select 1 from public.venue_bookings b
            where b.id = (a->>'booking_id')::uuid and b.event_id = p_event_id
              and b.status in ('held','approved','re_review'))
    ) then
        return 'The checklist names a venue booking that is not active on this event';
    end if;
    if exists (
        select 1 from public.venue_bookings b cross join unnest(v_venue_factors) f
        where b.event_id = p_event_id and b.status in ('held','approved','re_review')
          and not exists (
            select 1 from jsonb_array_elements(p_checklist) a
            where a->>'factor' = f and (a->>'booking_id')::uuid = b.id)
    ) then
        return 'Every venue factor must be marked for every venue booking';
    end if;
    if not exists (select 1 from jsonb_array_elements(p_checklist) a where a->>'factor' = 'equipment_placement') then
        return 'Equipment placement must be marked';
    end if;
    if p_decision = 'approved' and exists (select 1 from jsonb_array_elements(p_checklist) a where a->>'rating' = 'concern') then
        return 'A factor marked Concern blocks approval';
    end if;
    return null;
end $$;

revoke execute on function private.safety_checklist_problem(uuid, jsonb, text) from public, anon, authenticated;

create function private.record_safety_checklist(p_decision_id uuid, p_event_id uuid, p_checklist jsonb)
returns void language sql set search_path = '' as $$
    insert into public.event_safety_checklist_items(decision_id, event_id, factor, booking_id, rating, note)
    select p_decision_id, p_event_id, a->>'factor', (a->>'booking_id')::uuid, a->>'rating', nullif(btrim(a->>'note'), '')
    from jsonb_array_elements(p_checklist) a;
$$;

revoke execute on function private.record_safety_checklist(uuid, uuid, jsonb) from public, anon, authenticated;

-- -----------------------------------------------------------------------------
-- safety_approve_event: checklist and organiser comment (CR-108 AC1-AC4)
-- -----------------------------------------------------------------------------
drop function public.safety_approve_event(uuid, uuid, integer, text, text, text);

create function public.safety_approve_event(
    p_event_id uuid, p_actor_id uuid, p_expected_version integer,
    p_checklist jsonb, p_organiser_comment text, p_private_note text,
    p_organiser_message text, p_staff_message text
) returns setof public.events
language plpgsql security definer set search_path = '' as $$
declare
    v_after public.events;
    v_decision_id uuid;
    v_problem text;
begin
    -- Serialise decisions before inspecting arrangements. Lock booking rows too,
    -- so an existing booking cannot change while approval commits.
    perform 1 from public.events where id=p_event_id
        and version=p_expected_version and status='safety_review' for update;
    if not found then return; end if;
    perform 1 from public.venue_bookings where event_id=p_event_id order by id for update;
    if not exists (select 1 from public.venue_bookings where event_id=p_event_id and status in ('held','approved','re_review'))
       or exists (select 1 from public.venue_bookings where event_id=p_event_id and status in ('held','re_review'))
       -- SCRUM-64: a flagged arrangement needs follow-up before approval.
       or exists (select 1 from public.venue_bookings where event_id=p_event_id
                  and status in ('held','approved','re_review') and flag is not null) then
        return;
    end if;
    -- AC3: every factor marked for every active booking, and no Concern on an approval.
    v_problem := private.safety_checklist_problem(p_event_id, p_checklist, 'approved');
    if v_problem is not null then
        raise exception '%', v_problem using errcode='22023';
    end if;
    select * into v_after from public.transition_event(
        p_event_id,p_actor_id,array['safety_review'],'confirmed',p_expected_version,
        null,'event_safety_approved',p_organiser_message);
    if not found then return; end if;
    insert into public.event_safety_decisions(event_id,decision,comment,organiser_comment,decided_by)
    values(p_event_id,'approved',nullif(btrim(p_private_note),''),nullif(btrim(p_organiser_comment),''),p_actor_id)
    returning id into v_decision_id;
    perform private.record_safety_checklist(v_decision_id, p_event_id, p_checklist);
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

revoke execute on function public.safety_approve_event(uuid,uuid,integer,jsonb,text,text,text,text) from public,anon,authenticated;
grant execute on function public.safety_approve_event(uuid,uuid,integer,jsonb,text,text,text,text) to service_role;

-- -----------------------------------------------------------------------------
-- safety_return_event: checklist and organiser comment (CR-108 AC1-AC4)
-- Request changes and reject need an organiser comment; a rejection flags the booking with it,
-- because that reason is read by the coordinator and venue staff and must be safe to share.
-- -----------------------------------------------------------------------------
drop function public.safety_return_event(uuid, uuid, integer, text, text, uuid[], uuid[], text);

create function public.safety_return_event(
    p_event_id uuid, p_actor_id uuid, p_expected_version integer,
    p_decision text, p_checklist jsonb, p_organiser_comment text, p_private_note text,
    p_booking_ids uuid[], p_equipment_request_ids uuid[], p_coordinator_message text
) returns setof public.events
language plpgsql security definer set search_path = '' as $$
declare
    v_after public.events;
    v_booking_ids uuid[];
    v_equipment_ids uuid[];
    v_rejected_venues uuid[] := '{}';
    v_decision_id uuid;
    v_problem text;
begin
    if p_decision is null or p_decision not in ('changes_requested','arrangement_rejected') then
        raise exception 'Invalid safety decision' using errcode='22023';
    end if;
    if p_organiser_comment is null or length(btrim(p_organiser_comment)) not between 1 and 1000 then
        raise exception 'An organiser comment is required' using errcode='22023';
    end if;
    perform 1 from public.events where id=p_event_id
        and version=p_expected_version and status='safety_review' for update;
    if not found then return; end if;
    -- Event first, then every booking in id order (the order safety_approve_event uses), so the
    -- checklist is judged against bookings that cannot change under it.
    perform 1 from public.venue_bookings where event_id=p_event_id order by id for update;
    -- NULL arrays mean no selections; a NULL element is an invalid id.
    if exists (select 1 from unnest(p_booking_ids) requested(id)
        where not exists (select 1 from public.venue_bookings b where b.id=requested.id and b.event_id=p_event_id))
       or exists (select 1 from unnest(p_equipment_request_ids) requested(id)
        where not exists (select 1 from public.equipment_requests r where r.id=requested.id and r.event_id=p_event_id)) then
        return;
    end if;
    select coalesce(array_agg(distinct id order by id),'{}'::uuid[]) into v_booking_ids from unnest(p_booking_ids) requested(id);
    select coalesce(array_agg(distinct id order by id),'{}'::uuid[]) into v_equipment_ids from unnest(p_equipment_request_ids) requested(id);
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
    -- AC3: every factor marked for every active booking before the decision is recorded.
    v_problem := private.safety_checklist_problem(p_event_id, p_checklist, p_decision);
    if v_problem is not null then
        raise exception '%', v_problem using errcode='22023';
    end if;
    select * into v_after from public.transition_event(
        p_event_id,p_actor_id,array['safety_review'],'planning',p_expected_version,null,null,null);
    if not found then return; end if;
    -- Request changes records concerned ids only; arrangements retain their state.
    if p_decision='arrangement_rejected' then
        update public.venue_bookings
        set flag='safety_rejected', flag_reason=btrim(p_organiser_comment), flagged_at=now()
        where id=v_booking_ids[1];
        insert into public.venue_booking_history(booking_id,actor_id,action,from_status,to_status)
        values(v_booking_ids[1],p_actor_id,'safety_rejected','approved','approved');
        select array[venue_id] into v_rejected_venues from public.venue_bookings where id=v_booking_ids[1];
    end if;
    insert into public.event_safety_decisions(
        event_id,decision,comment,organiser_comment,affected_booking_ids,affected_equipment_request_ids,
        rejected_venue_ids,decided_by
    ) values(p_event_id,p_decision,nullif(btrim(p_private_note),''),btrim(p_organiser_comment),v_booking_ids,
        v_equipment_ids,v_rejected_venues,p_actor_id)
    returning id into v_decision_id;
    perform private.record_safety_checklist(v_decision_id, p_event_id, p_checklist);
    if v_after.coordinator_id is not null and v_after.coordinator_id is distinct from p_actor_id then
        insert into public.notifications(recipient_id,event_id,type,message)
        values(v_after.coordinator_id,p_event_id,
            case when p_decision='changes_requested' then 'event_safety_changes_requested' else 'event_safety_arrangement_rejected' end,
            p_coordinator_message);
    end if;
    return next v_after;
end $$;

revoke execute on function public.safety_return_event(uuid,uuid,integer,text,jsonb,text,text,uuid[],uuid[],text) from public,anon,authenticated;
grant execute on function public.safety_return_event(uuid,uuid,integer,text,jsonb,text,text,uuid[],uuid[],text) to service_role;
