-- =============================================================================
-- ConnectSphere - SCRUM-12 Coordinator assignment (W7 CR-05)
--
-- 1. Submitted events wait in the Lead's unassigned queue (status `submitted`)
--    until a Lead assigns a coordinator, which moves them to `under_review`.
--    Events already `under_review` with no coordinator (submitted before this
--    story) are the same thing under the old rule, so they join the queue.
-- 2. public.assign_event assigns, changes the status, records who/when in
--    event_status_history and notifies, in one locked transaction. Of two
--    simultaneous assignments the second finds the event no longer queued.
-- 3. The Lead role is exclusive (AUTH-R7, QA3-13, M3): an account holding it
--    cannot hold any other role, and an account holding another role cannot be
--    granted it.
-- =============================================================================

-- 1. Backfill ------------------------------------------------------------------
with requeued as (
    update public.events
       set status = 'submitted',
           version = version + 1
     where status = 'under_review'
       and coordinator_id is null
    returning id
)
insert into public.event_status_history (event_id, from_status, to_status, actor_id, reason)
select id, 'under_review', 'submitted', null, 'Moved to the unassigned queue'
  from requeued;

-- 2. assign_event ---------------------------------------------------------------
create or replace function public.assign_event(
    p_event_id uuid,
    p_lead_id uuid,
    p_coordinator_id uuid,
    p_from_statuses text[],
    p_to_status text,
    p_reason text,
    p_notify_assigned text,
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
    -- Only an active account holding the coordinator role (LA-R4). The Lead role
    -- is exclusive, so a Lead can never be a target.
    if not exists (
        select 1 from public.user_roles
         where profile_id = p_coordinator_id and role = 'event_coordinator'
    ) or exists (
        select 1 from auth.users
         where id = p_coordinator_id
           and (deleted_at is not null or banned_until > now())
    ) then
        return;
    end if;

    select * into v_before
      from public.events
     where id = p_event_id
       and coordinator_id is null
       and status::text = any (p_from_statuses)
       for update;

    if not found then
        return;
    end if;

    update public.events
       set coordinator_id = p_coordinator_id,
           assigned_by = p_lead_id,
           assigned_at = now(),
           status = p_to_status::public.event_status,
           version = version + 1
     where id = p_event_id
    returning * into v_after;

    insert into public.event_status_history (event_id, from_status, to_status, actor_id, reason)
    values (p_event_id, v_before.status, v_after.status, p_lead_id, nullif(btrim(p_reason), ''));

    insert into public.notifications (recipient_id, event_id, type, message)
    values (p_coordinator_id, p_event_id, 'event_assigned', p_notify_assigned);

    if v_after.organiser_id is distinct from p_lead_id then
        insert into public.notifications (recipient_id, event_id, type, message)
        values (v_after.organiser_id, p_event_id, 'event_coordinator_changed', p_notify_organiser);
    end if;

    return next v_after;
end;
$$;

comment on function public.assign_event is
    'Atomically assigns a queued event to a coordinator for an Event Coordinator Lead: coordinator, status, history and notices. Returns nothing when the event is no longer queued or the target is not an active coordinator. API-only.';

revoke execute on function public.assign_event(uuid, uuid, uuid, text[], text, text, text, text)
    from public, anon, authenticated;
grant execute on function public.assign_event(uuid, uuid, uuid, text[], text, text, text, text)
    to service_role;

-- 3. The Lead role is exclusive -----------------------------------------------
create or replace function private.enforce_exclusive_lead_role()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if new.role = 'event_coordinator_lead' then
        if exists (select 1 from public.user_roles
                    where profile_id = new.profile_id and role <> 'event_coordinator_lead') then
            raise exception 'An Event Coordinator Lead cannot hold any other role.'
                using errcode = 'check_violation';
        end if;
    elsif exists (select 1 from public.user_roles
                   where profile_id = new.profile_id and role = 'event_coordinator_lead') then
        raise exception 'An Event Coordinator Lead cannot hold any other role.'
            using errcode = 'check_violation';
    end if;
    return new;
end;
$$;

revoke execute on function private.enforce_exclusive_lead_role() from public, anon, authenticated;

create trigger user_roles_exclusive_lead
    before insert or update of role, profile_id on public.user_roles
    for each row execute function private.enforce_exclusive_lead_role();
