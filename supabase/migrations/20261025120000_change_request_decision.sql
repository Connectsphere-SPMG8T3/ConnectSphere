-- =============================================================================
-- ConnectSphere - Story 37 review and process event change requests
--
-- The assigned coordinator decides the organiser's open change request (story
-- 32). public.reject_event_change closes it as rejected with the coordinator's
-- reason and tells the organiser; the event keeps its details, status and
-- arrangements (AC2, AC4, CR-R3). Decisions are refused once the event has
-- started or left the decidable statuses (AC8, Q5). API-only (ADR-0006).
-- =============================================================================

-- The organiser alone hears of a decision on their request.
insert into public.notification_types (type, recipient_roles) values
    ('event_change_rejected', '{event_organiser}');

-- ---------------------------------------------------------------------------
-- reject_event_change
-- ---------------------------------------------------------------------------

create or replace function public.reject_event_change(
    p_event_id uuid,
    p_actor_id uuid,
    p_reason text,
    p_from_statuses text[],
    p_organiser_message text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
begin
    -- The lock request_event_change takes, so a decision and a new request can't interleave.
    select * into v_event from public.events where id = p_event_id for update;
    if not found or v_event.status = 'draft' then
        return jsonb_build_object('outcome', 'not_found');
    end if;
    if v_event.coordinator_id is distinct from p_actor_id then
        return jsonb_build_object('outcome', 'not_assigned');
    end if;
    if not (v_event.status::text = any (p_from_statuses)) then
        return jsonb_build_object('outcome', 'status_changed');
    end if;
    -- A submitted event always has a start; a missing one is refused, as CR-R10.
    if v_event.starts_at is null or v_event.starts_at <= now() then
        return jsonb_build_object('outcome', 'started');
    end if;

    update public.event_change_requests
       set status = 'rejected', decided_by = p_actor_id, decided_at = now(),
           decision_reason = btrim(p_reason)
     where event_id = p_event_id and kind = 'change' and status = 'open';
    if not found then
        return jsonb_build_object('outcome', 'no_open_request');
    end if;

    perform public.add_notification(v_event.organiser_id, p_event_id,
        'event_change_rejected', p_organiser_message, p_actor_id);

    return jsonb_build_object('outcome', 'ok');
end;
$$;

comment on function public.reject_event_change is
    'Story 37 AC2: closes the open change request on an event the actor coordinates, in one of p_from_statuses and not yet started, as rejected with the reason, and notifies the organiser. The event keeps its details, status and arrangements. Answers {outcome: ok|not_found|not_assigned|status_changed|started|no_open_request}. API-only.';

revoke execute on function public.reject_event_change(uuid, uuid, text, text[], text)
    from public, anon, authenticated;
grant execute on function public.reject_event_change(uuid, uuid, text, text[], text)
    to service_role;
