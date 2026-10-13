-- =============================================================================
-- ConnectSphere - CR-101: Event Coordinator Lead assignment tracking
--
-- assigned_by / assigned_at: who last assigned or reassigned the event. Null
-- assigned_by on an assigned event = assigned before the Lead role existed, so
-- every Lead sees it (CR-101 AC5).
-- reassign_event: the one place coordinator_id changes on behalf of a Lead, so
-- the update, history row and notices commit together. Story 81 reuses it.
-- =============================================================================

alter table public.events
    add column assigned_by uuid null references public.profiles (id) on delete set null,
    add column assigned_at timestamptz null;

comment on column public.events.assigned_by is
    'The Event Coordinator Lead who last assigned or reassigned the event; null = assigned before the Lead role existed.';

create index events_assigned_by_idx on public.events using btree (assigned_by);

create or replace function public.reassign_event(
    p_event_id uuid,
    p_lead_id uuid,
    p_coordinator_id uuid,
    p_expected_version integer,
    p_active_statuses text[],
    p_reason text,
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

    insert into public.event_status_history (event_id, from_status, to_status, actor_id, reason)
    values (p_event_id, v_before.status, v_after.status, p_lead_id, nullif(btrim(p_reason), ''));

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
    'Atomically assigns or reassigns an event to a coordinator for an Event Coordinator Lead: update, history row and notices. API-only.';

revoke execute on function public.reassign_event(uuid, uuid, uuid, integer, text[], text, text, text, text)
    from public, anon, authenticated;
grant execute on function public.reassign_event(uuid, uuid, uuid, integer, text[], text, text, text, text)
    to service_role;
