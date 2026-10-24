-- =============================================================================
-- ConnectSphere - Story 115 cancel an event
--
-- The assigned coordinator approves or rejects the organiser's open cancellation
-- request (story 84), or cancels a Planning, Confirmed or Preparation event
-- directly (AC3). Both ways of cancelling go through public.cancel_event, which
-- in one transaction (ADR-0007):
--   * moves the event to cancelled through public.transition_event, which writes
--     the history row, notifies the organiser and releases the event's venue
--     bookings (new here, Q1) and equipment (SCRUM-24);
--   * closes an open cancellation request as approved (Q9);
--   * notifies the registered attendees, then cancels their registrations (RG-R4);
--   * notifies every venue staff and tech support account, since staff work as
--     pools (AUTH-R5, Q7), and the Safety Officers when the event was in its
--     safety review (Q12).
-- public.reject_cancellation_request closes the open request as rejected with
-- the coordinator's reason and tells the organiser; the event keeps its status
-- (AC2). Both are API-only (ADR-0006).
-- =============================================================================

-- The organiser, the coordinator (never notified of their own action, NT-R1, but
-- listed for a cancellation they didn't make), the staff pools and the Safety
-- Officers; the organiser alone hears of a rejected request.
insert into public.notification_types (type, recipient_roles) values
    ('event_cancelled', '{event_organiser,event_coordinator,venue_staff,tech_support,safety_officer}'),
    ('event_cancellation_rejected', '{event_organiser}');

-- ---------------------------------------------------------------------------
-- transition_event: a cancelled event stops occupying its venues too (Q1,
-- BR-R4, QA3-27). Body as in 20261019120000, with 'cancelled' added to the
-- venue release.
-- ---------------------------------------------------------------------------

create or replace function public.transition_event(
    p_event_id uuid,
    p_actor_id uuid,
    p_from_statuses text[],
    p_to_status text,
    p_expected_version integer,
    p_reason text default null,
    p_notify_type text default null,
    p_notify_message text default null
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
    select *
      into v_before
      from public.events
     where id = p_event_id
       and version = p_expected_version
       and status::text = any (p_from_statuses)
       for update;

    if not found then
        return;
    end if;

    update public.events
       set status = p_to_status::public.event_status,
           version = version + 1,
           -- Leaving draft is submission; later transitions keep the original time.
           submitted_at = case when v_before.status = 'draft' then now() else submitted_at end
     where id = p_event_id
    returning * into v_after;

    insert into public.event_status_history (event_id, from_status, to_status, actor_id, reason)
    values (p_event_id, v_before.status, v_after.status, p_actor_id, nullif(btrim(p_reason), ''));

    -- A rejected or cancelled event must stop occupying its venues (QA2-13, QA3-27).
    if v_after.status in ('rejected', 'cancelled') then
        update public.venue_bookings
           set status = 'released'
         where event_id = p_event_id
           and status in ('held', 'approved', 're_review');
    end if;

    -- RS-R3: a rejected or cancelled event frees its equipment (SCRUM-24 AC6).
    if v_after.status in ('rejected', 'cancelled') then
        perform private.set_actor(p_actor_id);
        perform private.release_event_equipment(p_event_id);
    end if;

    if p_notify_type is not null and v_after.organiser_id is distinct from p_actor_id then
        insert into public.notifications (recipient_id, event_id, type, message)
        values (v_after.organiser_id, p_event_id, p_notify_type, p_notify_message);
    end if;

    return next v_after;
end;
$$;

-- ---------------------------------------------------------------------------
-- cancel_event
-- ---------------------------------------------------------------------------

create or replace function public.cancel_event(
    p_event_id uuid,
    p_actor_id uuid,
    p_expected_version integer,
    p_from_statuses text[],
    p_reason text,
    p_require_open_request boolean,
    p_organiser_message text,
    p_staff_message text,
    p_attendee_message text,
    p_safety_message text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_after public.events;
    v_request_id uuid;
begin
    -- Lock the event so a concurrent decision, request or edit waits its turn.
    select * into v_event from public.events where id = p_event_id for update;
    if not found or v_event.status = 'draft' then
        return jsonb_build_object('outcome', 'not_found');
    end if;
    if v_event.coordinator_id is distinct from p_actor_id then
        return jsonb_build_object('outcome', 'not_assigned');
    end if;
    -- LC-R5, Q5, Q11: once it has started it runs to completed. A submitted event
    -- always has a start time, so a missing one fails closed.
    if v_event.starts_at is null or v_event.starts_at <= now() then
        return jsonb_build_object('outcome', 'started');
    end if;

    select id into v_request_id
      from public.event_change_requests
     where event_id = p_event_id and kind = 'cancellation' and status = 'open'
       for update;
    if p_require_open_request and v_request_id is null then
        return jsonb_build_object('outcome', 'no_open_request');
    end if;

    select * into v_after
      from public.transition_event(p_event_id, p_actor_id, p_from_statuses, 'cancelled',
                                   p_expected_version, p_reason, 'event_cancelled', p_organiser_message);
    if v_after.id is null then
        return jsonb_build_object('outcome', 'status_changed');
    end if;

    -- Q9: cancelling closes the open request as approved. An approval needs no
    -- reason of its own (AC1); a direct cancel's reason is the coordinator's.
    if v_request_id is not null then
        update public.event_change_requests
           set status = 'approved', decided_by = p_actor_id, decided_at = now(),
               decision_reason = case when p_require_open_request then null else btrim(p_reason) end
         where id = v_request_id;
    end if;

    -- RG-R4, QA-114: tell the registered attendees while they still are, then cancel.
    perform public.notify_registered_attendees(p_event_id, 'attendee_event_cancelled', p_attendee_message, p_actor_id);
    update public.event_registrations
       set status = 'cancelled'
     where event_id = p_event_id and status = 'registered';

    -- Q7: staff are pools (AUTH-R5), so every venue staff and tech support account
    -- is told, once per pool role they hold. The role is stamped here, not by the
    -- trigger, so someone in both pools sees it in either.
    insert into public.notifications (recipient_id, event_id, type, message, recipient_role)
    select ur.profile_id, p_event_id, 'event_cancelled', p_staff_message, ur.role
      from public.user_roles ur
     where ur.role in ('venue_staff', 'tech_support')
       and ur.profile_id is distinct from p_actor_id;

    -- Q12: the event leaves the Safety Officers' queue.
    if v_event.status = 'safety_review' then
        insert into public.notifications (recipient_id, event_id, type, message, recipient_role)
        select ur.profile_id, p_event_id, 'event_cancelled', p_safety_message, ur.role
          from public.user_roles ur
         where ur.role = 'safety_officer'
           and ur.profile_id is distinct from p_actor_id;
    end if;

    return jsonb_build_object('outcome', 'ok', 'event', to_jsonb(v_after));
end;
$$;

comment on function public.cancel_event is
    'Story 115: cancels an event the actor coordinates from one of p_from_statuses before it starts, closing an open cancellation request as approved (required when p_require_open_request), releasing venue bookings, equipment and registrations, and notifying the organiser, registered attendees, venue staff, tech support and, from safety review, the Safety Officers. Answers {outcome: ok|not_found|not_assigned|started|no_open_request|status_changed, event}. API-only.';

revoke execute on function public.cancel_event(uuid, uuid, integer, text[], text, boolean, text, text, text, text)
    from public, anon, authenticated;
grant execute on function public.cancel_event(uuid, uuid, integer, text[], text, boolean, text, text, text, text)
    to service_role;

-- ---------------------------------------------------------------------------
-- reject_cancellation_request
-- ---------------------------------------------------------------------------

create or replace function public.reject_cancellation_request(
    p_event_id uuid,
    p_actor_id uuid,
    p_reason text,
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
    select * into v_event from public.events where id = p_event_id for update;
    if not found or v_event.status = 'draft' then
        return jsonb_build_object('outcome', 'not_found');
    end if;
    if v_event.coordinator_id is distinct from p_actor_id then
        return jsonb_build_object('outcome', 'not_assigned');
    end if;

    update public.event_change_requests
       set status = 'rejected', decided_by = p_actor_id, decided_at = now(),
           decision_reason = btrim(p_reason)
     where event_id = p_event_id and kind = 'cancellation' and status = 'open';
    if not found then
        return jsonb_build_object('outcome', 'no_open_request');
    end if;

    perform public.add_notification(v_event.organiser_id, p_event_id,
        'event_cancellation_rejected', p_organiser_message, p_actor_id);

    return jsonb_build_object('outcome', 'ok');
end;
$$;

comment on function public.reject_cancellation_request is
    'Story 115 AC2: closes the open cancellation request on an event the actor coordinates as rejected with the reason, and notifies the organiser. The event keeps its status and arrangements. Answers {outcome: ok|not_found|not_assigned|no_open_request}. API-only.';

revoke execute on function public.reject_cancellation_request(uuid, uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.reject_cancellation_request(uuid, uuid, text, text)
    to service_role;
