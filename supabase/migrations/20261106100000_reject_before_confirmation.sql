-- 115-R: a coordinator rejects before confirmation and cancels after it (QA2-6), and
-- answers an open cancellation request before doing either.
--
-- An event can return to Planning with registrations, so rejecting it has to end them
-- as cancelling does. Both now share private.close_event_registrations, which also
-- covers waitlisted and invited attendees (added by SCRUM-86, after cancel_event).
--
-- public.reject_event wraps transition_event for the coordinator's Reject, as
-- public.cancel_event does for Cancel. Both check for an open request under the event's
-- lock, the lock request_event_cancellation takes, so one can't slip in between.

create function private.close_event_registrations(
    p_event_id uuid,
    p_attendee_message text,
    p_actor_id uuid
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_attendee uuid;
begin
    -- RG-R4, QA-114: tell them while they are still active, then cancel.
    for v_attendee in
        select r.attendee_id
          from public.event_registrations r
         where r.event_id = p_event_id
           and r.status in ('registered', 'waitlisted', 'invited')
    loop
        perform public.add_notification(v_attendee, p_event_id, 'attendee_event_cancelled',
                                        p_attendee_message, p_actor_id);
    end loop;

    update public.event_registrations
       set status = 'cancelled',
           waitlist_order = null,
           invitation_expires_at = null
     where event_id = p_event_id
       and status in ('registered', 'waitlisted', 'invited');
end;
$$;

revoke all on function private.close_event_registrations(uuid, text, uuid) from public, anon, authenticated;

comment on function private.close_event_registrations is
    '115-R: ends an event''s registered, waitlisted and invited entries and notifies each attendee once. Called by reject_event and cancel_event, which hold the event''s lock.';

create function public.reject_event(
    p_event_id uuid,
    p_actor_id uuid,
    p_expected_version integer,
    p_from_statuses text[],
    p_reason text,
    p_organiser_message text,
    p_attendee_message text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_after public.events;
begin
    -- Lock the event so a concurrent request, decision or edit waits its turn.
    select * into v_event from public.events where id = p_event_id for update;
    if not found or v_event.status = 'draft' then
        return jsonb_build_object('outcome', 'not_found');
    end if;
    if v_event.coordinator_id is distinct from p_actor_id then
        return jsonb_build_object('outcome', 'not_assigned');
    end if;

    if exists (
        select 1 from public.event_change_requests
         where event_id = p_event_id and kind = 'cancellation' and status = 'open'
    ) then
        return jsonb_build_object('outcome', 'open_request');
    end if;

    select * into v_after
      from public.transition_event(p_event_id, p_actor_id, p_from_statuses, 'rejected',
                                   p_expected_version, p_reason, 'event_rejected', p_organiser_message);
    if v_after.id is null then
        return jsonb_build_object('outcome', 'status_changed');
    end if;

    perform private.close_event_registrations(p_event_id, p_attendee_message, p_actor_id);

    return jsonb_build_object('outcome', 'ok', 'event', to_jsonb(v_after));
end;
$$;

revoke execute on function public.reject_event(uuid, uuid, integer, text[], text, text, text)
    from public, anon, authenticated;
grant execute on function public.reject_event(uuid, uuid, integer, text[], text, text, text)
    to service_role;

comment on function public.reject_event is
    '115-R: rejects an event the actor coordinates from one of p_from_statuses, ending its registrations, unless a cancellation request is open. Answers {outcome, event}: ok / not_found / not_assigned / open_request / status_changed.';

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
    -- 115-R AC3: a direct cancel waits for the open request to be decided.
    if not p_require_open_request and v_request_id is not null then
        return jsonb_build_object('outcome', 'open_request');
    end if;

    select * into v_after
      from public.transition_event(p_event_id, p_actor_id, p_from_statuses, 'cancelled',
                                   p_expected_version, p_reason, 'event_cancelled', p_organiser_message);
    if v_after.id is null then
        return jsonb_build_object('outcome', 'status_changed');
    end if;

    -- An approval closes the request it decides. It needs no reason of its own (AC1).
    if v_request_id is not null then
        update public.event_change_requests
           set status = 'approved', decided_by = p_actor_id, decided_at = now()
         where id = v_request_id;
    end if;

    perform private.close_event_registrations(p_event_id, p_attendee_message, p_actor_id);

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
    'Story 115, 115-R: cancels an event the actor coordinates from one of p_from_statuses before it starts, releasing venue bookings, equipment and registrations, and notifying the organiser, attendees, venue staff, tech support and, from safety review, the Safety Officers. With p_require_open_request it approves the open cancellation request; without it, it refuses while one is open. Answers {outcome, event}.';
