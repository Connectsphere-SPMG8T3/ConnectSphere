-- =============================================================================
-- ConnectSphere - SCRUM-12 follow-up: event assignment history
--
-- A reassignment is not a status change, so it can't go in event_status_history
-- (CR-101 tried: readers treat every row there as a transition, and a same-status
-- row sent a Lead-reassigned event to the back of the Safety Officer's queue).
-- This table records who moved an event from one coordinator to another, and
-- when. The history endpoint merges it with the status history by time.
--
-- Written only by public.reassign_event. An assignment from the queue is already
-- a status change (submitted -> under_review) recorded by public.assign_event in
-- event_status_history, so it is not written here as well.
-- =============================================================================

create table public.event_assignment_history (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null,
    from_coordinator_id uuid null,
    to_coordinator_id uuid not null,
    actor_id uuid null,
    at timestamptz not null default now(),
    constraint event_assignment_history_event_id_fkey
        foreign key (event_id) references public.events (id) on delete cascade,
    constraint event_assignment_history_from_coordinator_id_fkey
        foreign key (from_coordinator_id) references public.profiles (id) on delete set null,
    constraint event_assignment_history_to_coordinator_id_fkey
        foreign key (to_coordinator_id) references public.profiles (id) on delete cascade,
    constraint event_assignment_history_actor_id_fkey
        foreign key (actor_id) references public.profiles (id) on delete set null
);

comment on table public.event_assignment_history is
    'Append-only record of reassignments (who moved an event from which coordinator to which, and when). Not a status change, so it is separate from event_status_history. Written by public.reassign_event.';

create index event_assignment_history_event_id_at_idx
    on public.event_assignment_history (event_id, at desc);
create index event_assignment_history_from_coordinator_id_idx
    on public.event_assignment_history (from_coordinator_id);
create index event_assignment_history_to_coordinator_id_idx
    on public.event_assignment_history (to_coordinator_id);
create index event_assignment_history_actor_id_idx
    on public.event_assignment_history (actor_id);

alter table public.event_assignment_history enable row level security;

-- Safety net only: the API uses the secret key. Same readers as the status
-- history: the organiser acting as organiser, or the assigned coordinator acting
-- as coordinator. Nobody can write through a user session.
create policy "event_assignment_history_select_owner_or_assigned_coordinator"
    on public.event_assignment_history
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.events e
            where e.id = event_assignment_history.event_id
              and (
                  (e.organiser_id = (select auth.uid())
                   and (select private.current_user_role()) = 'event_organiser')
                  or (e.coordinator_id = (select auth.uid())
                      and (select private.current_user_role()) = 'event_coordinator')
              )
        )
    );

-- reassign_event now also records the reassignment. Same signature as before.
create or replace function public.reassign_event(
    p_event_id uuid,
    p_lead_id uuid,
    p_coordinator_id uuid,
    p_expected_version integer,
    p_active_statuses text[],
    p_notify_assigned text,
    p_notify_previous text,
    p_notify_organiser text
)
returns setof public.events
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_before public.events;
    v_after public.events;
begin
    if not exists (
        select 1 from public.user_roles
         where profile_id = p_coordinator_id and role = 'event_coordinator'
    ) then
        return;
    end if;

    select * into v_before
      from public.events
     where id = p_event_id
       and version = p_expected_version
       and status::text = any (p_active_statuses)
       for update;

    if not found then
        return;
    end if;

    update public.events
       set coordinator_id = p_coordinator_id,
           assigned_by = p_lead_id,
           assigned_at = now(),
           version = version + 1
     where id = p_event_id
    returning * into v_after;

    insert into public.event_assignment_history (event_id, from_coordinator_id, to_coordinator_id, actor_id)
    values (p_event_id, v_before.coordinator_id, p_coordinator_id, p_lead_id);

    if p_coordinator_id is distinct from p_lead_id then
        insert into public.notifications (recipient_id, event_id, type, message)
        values (p_coordinator_id, p_event_id, 'event_assigned', p_notify_assigned);
    end if;

    if v_before.coordinator_id is not null
       and v_before.coordinator_id is distinct from p_lead_id
       and v_before.coordinator_id is distinct from p_coordinator_id then
        insert into public.notifications (recipient_id, event_id, type, message)
        values (v_before.coordinator_id, p_event_id, 'event_reassigned', p_notify_previous);
    end if;

    if v_after.organiser_id is distinct from p_lead_id then
        insert into public.notifications (recipient_id, event_id, type, message)
        values (v_after.organiser_id, p_event_id, 'event_coordinator_changed', p_notify_organiser);
    end if;

    return next v_after;
end;
$$;

comment on function public.reassign_event is
    'Atomically assigns or reassigns an active event for an Event Coordinator Lead: update, assignment-history row and notices. Writes no event_status_history row (not a status change). API-only.';

revoke execute on function public.reassign_event(uuid, uuid, uuid, integer, text[], text, text, text)
    from public, anon, authenticated;
grant execute on function public.reassign_event(uuid, uuid, uuid, integer, text[], text, text, text)
    to service_role;
