-- =============================================================================
-- ConnectSphere - CR-101 review fix: reassigning is not a status change
--
-- The first reassign_event wrote an event_status_history row with
-- from_status = to_status. Readers treat every row as a transition: the Safety
-- Officer's queue takes "entered review" from the latest row into
-- safety_review, so a reassignment during review sent the event to the back of
-- the queue, and the organiser's history showed a transition that never
-- happened. A reassignment is recorded by events.assigned_by / assigned_at and
-- by its notices; a proper assignment history belongs to story 81.
-- The p_reason parameter went with the history row, so the function is
-- replaced rather than altered.
-- =============================================================================

drop function if exists public.reassign_event(uuid, uuid, uuid, integer, text[], text, text, text, text);

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
    'Atomically assigns or reassigns an event to a coordinator for an Event Coordinator Lead: update and notices. Writes no status history (not a status change). API-only.';

revoke execute on function public.reassign_event(uuid, uuid, uuid, integer, text[], text, text, text)
    from public, anon, authenticated;
grant execute on function public.reassign_event(uuid, uuid, uuid, integer, text[], text, text, text)
    to service_role;
