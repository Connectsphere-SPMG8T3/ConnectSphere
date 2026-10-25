-- =============================================================================
-- ConnectSphere - Story 37 review and process event change requests
--
-- The assigned coordinator decides the organiser's open change request (story
-- 32). public.approve_event_change applies the requested values to the event
-- and its spaces in one transaction (ADR-0007), provided the event is still at
-- the version whose `before` values the API checked (Q8), closes the request as
-- approved and tells the organiser. public.reject_event_change closes it as rejected with the coordinator's
-- reason and tells the organiser; the event keeps its details, status and
-- arrangements (AC2, AC4, CR-R3). Decisions are refused once the event has
-- started or left the decidable statuses (AC8, Q5). API-only (ADR-0006).
-- =============================================================================

-- The organiser alone hears of a decision on their request.
insert into public.notification_types (type, recipient_roles) values
    ('event_change_approved', '{event_organiser}'),
    ('event_change_rejected', '{event_organiser}');

-- ---------------------------------------------------------------------------
-- approve_event_change
-- ---------------------------------------------------------------------------

create or replace function public.approve_event_change(
    p_event_id uuid,
    p_actor_id uuid,
    p_expected_version integer,
    p_from_statuses text[],
    p_event_values jsonb,
    p_space_values jsonb,
    p_organiser_message text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_after public.events;
    v_space_id text;
    v_values jsonb;
begin
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
    if v_event.starts_at is null or v_event.starts_at <= now() then
        return jsonb_build_object('outcome', 'started');
    end if;
    -- The API checked each `before` against this version (Q8); anything newer is unreviewed.
    if v_event.version is distinct from p_expected_version then
        return jsonb_build_object('outcome', 'stale');
    end if;

    update public.event_change_requests
       set status = 'approved', decided_by = p_actor_id, decided_at = now()
     where event_id = p_event_id and kind = 'change' and status = 'open';
    if not found then
        return jsonb_build_object('outcome', 'no_open_request');
    end if;

    -- Only the fields the request changes are in p_event_values; the rest keep their values.
    update public.events e
       set name = r.name, event_timezone = r.event_timezone, purpose = r.purpose,
           description = r.description, starts_at = r.starts_at, ends_at = r.ends_at,
           expected_attendance = r.expected_attendance, layout_preference = r.layout_preference,
           facilities_required = r.facilities_required, accessibility_needs = r.accessibility_needs,
           preliminary_equipment_needs = r.preliminary_equipment_needs,
           registration_enabled = r.registration_enabled, registration_capacity = r.registration_capacity,
           registration_opens_at = r.registration_opens_at, registration_closes_at = r.registration_closes_at,
           re_registration_allowed = r.re_registration_allowed, waitlist_enabled = r.waitlist_enabled,
           version = e.version + 1
      from jsonb_populate_record(v_event, p_event_values) r
     where e.id = p_event_id
    returning e.* into v_after;

    for v_space_id, v_values in select key, value from jsonb_each(p_space_values) loop
        update public.event_space_requests s
           set label = r.label, expected_pax = r.expected_pax, layout_preference = r.layout_preference,
               facilities_required = r.facilities_required, starts_at = r.starts_at, ends_at = r.ends_at,
               version = s.version + 1
          from public.event_space_requests current_space,
               lateral jsonb_populate_record(current_space, v_values) r
         where s.id = v_space_id::uuid and s.event_id = p_event_id and current_space.id = s.id;
    end loop;

    perform public.add_notification(v_event.organiser_id, p_event_id,
        'event_change_approved', p_organiser_message, p_actor_id);

    return jsonb_build_object('outcome', 'ok', 'event', to_jsonb(v_after));
end;
$$;

comment on function public.approve_event_change is
    'Story 37 AC2: approves the open change request on an event the actor coordinates, in one of p_from_statuses, not yet started and still at p_expected_version. Applies p_event_values (only the changed event fields) and p_space_values ({space_id: changed fields}) in one transaction, bumps the versions, closes the request as approved and notifies the organiser. Answers {outcome: ok|not_found|not_assigned|status_changed|started|stale|no_open_request, event}. API-only.';

revoke execute on function public.approve_event_change(uuid, uuid, integer, text[], jsonb, jsonb, text)
    from public, anon, authenticated;
grant execute on function public.approve_event_change(uuid, uuid, integer, text[], jsonb, jsonb, text)
    to service_role;

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
