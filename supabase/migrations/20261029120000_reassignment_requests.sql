-- =============================================================================
-- ConnectSphere - CR-106 request a reassignment from the Lead
--
-- event_reassignment_requests: the assigned coordinator's request that a Lead
-- reassign their event, and the Lead's response (REQUIREMENTS 6.5 LA-R6, QA3-12,
-- QA3-35, QA3-39). A request changes nothing on the event: the coordinator
-- stays assigned until a Lead reassigns it (public.reassign_event, which now
-- closes the open request) or declines it with a reason.
--
-- It is its own table, not a kind of event_change_requests: that table allows
-- one open request per event across kinds (CR-R14), and a coordinator asking to
-- be moved must not block the organiser's change or cancellation request, nor
-- the reverse. Here at most one request is open per event.
--
-- [Team decision] An open request is closed as superseded when the event leaves
-- the statuses a Lead can reassign (it ends, is cancelled or rejected, or moves
-- to Preparation), so an unreachable request never blocks a new one.
--
-- Recipients: the Lead whose scope holds the event (events.assigned_by, while
-- that user is still a Lead), else every Lead (CR-101 AC5). API-only (ADR-0006).
-- =============================================================================

create table public.event_reassignment_requests (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null,
    status text not null default 'open',
    reason text not null,
    requested_by uuid null,
    requested_at timestamptz not null default now(),
    decided_by uuid null,
    decided_at timestamptz null,
    decision_reason text null,
    constraint event_reassignment_requests_event_id_fkey
        foreign key (event_id) references public.events (id) on delete cascade,
    constraint event_reassignment_requests_requested_by_fkey
        foreign key (requested_by) references public.profiles (id) on delete set null,
    constraint event_reassignment_requests_decided_by_fkey
        foreign key (decided_by) references public.profiles (id) on delete set null,
    constraint event_reassignment_requests_status_check
        check (status in ('open', 'reassigned', 'declined', 'superseded')),
    constraint event_reassignment_requests_reason_length check (length(btrim(reason)) between 1 and 1000),
    constraint event_reassignment_requests_decision_reason_length
        check (decision_reason is null or length(btrim(decision_reason)) between 1 and 1000),
    -- Only an open request is undecided, and a decline always says why (CR-106 AC5).
    constraint event_reassignment_requests_decided_when_closed
        check ((status = 'open') = (decided_at is null)),
    constraint event_reassignment_requests_decline_has_reason
        check (status <> 'declined' or decision_reason is not null)
);

comment on table public.event_reassignment_requests is
    'A coordinator''s request that a Lead reassign their event, and the Lead''s response (CR-106). Written only by API-only functions.';

create unique index event_reassignment_requests_one_open_per_event
    on public.event_reassignment_requests (event_id)
    where status = 'open';
create index event_reassignment_requests_event_requested_at_idx
    on public.event_reassignment_requests (event_id, requested_at);
create index event_reassignment_requests_requested_by_idx on public.event_reassignment_requests (requested_by);
create index event_reassignment_requests_decided_by_idx on public.event_reassignment_requests (decided_by);

alter table public.event_reassignment_requests enable row level security;

-- Safety net only: the API uses the secret key. The assigned coordinator, acting as
-- coordinator, may read their event's requests. The organiser may not: it is internal.
create policy "event_reassignment_requests_select_assigned_coordinator"
    on public.event_reassignment_requests
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.events e
            where e.id = event_reassignment_requests.event_id
              and e.coordinator_id = (select auth.uid())
              and (select private.current_user_role()) = 'event_coordinator'
        )
    );

-- The request goes to a Lead; the Lead's decline goes to the coordinator. (A reassignment
-- already tells the previous coordinator through story 81's event_reassigned notice.)
insert into public.notification_types (type, recipient_roles) values
    ('reassignment_requested', '{event_coordinator_lead}'),
    ('reassignment_declined', '{event_coordinator}');

create or replace function public.request_reassignment(
    p_event_id uuid,
    p_actor_id uuid,
    p_reason text,
    p_active_statuses text[],
    p_lead_message text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_request public.event_reassignment_requests;
    v_lead uuid;
    v_scope_lead uuid;
begin
    -- The same lock reassign_event takes, so a request and a reassignment can't interleave.
    select * into v_event from public.events where id = p_event_id for update;
    if not found then
        return jsonb_build_object('outcome', 'not_found');
    end if;
    if v_event.coordinator_id is distinct from p_actor_id then
        return jsonb_build_object('outcome', 'not_assigned');
    end if;
    if not (v_event.status::text = any (p_active_statuses)) then
        return jsonb_build_object('outcome', 'status_changed');
    end if;
    if exists (select 1 from public.event_reassignment_requests
                where event_id = p_event_id and status = 'open') then
        return jsonb_build_object('outcome', 'already_open');
    end if;

    insert into public.event_reassignment_requests (event_id, reason, requested_by)
    values (p_event_id, btrim(p_reason), p_actor_id)
    returning * into v_request;

    -- The Lead whose scope holds the event, while they are still a Lead; else every Lead.
    select ur.profile_id into v_scope_lead
      from public.user_roles ur
     where ur.profile_id = v_event.assigned_by and ur.role = 'event_coordinator_lead';

    if v_scope_lead is not null then
        perform public.add_notification(v_scope_lead, p_event_id,
            'reassignment_requested', p_lead_message, p_actor_id);
    else
        for v_lead in
            select profile_id from public.user_roles where role = 'event_coordinator_lead'
        loop
            perform public.add_notification(v_lead, p_event_id,
                'reassignment_requested', p_lead_message, p_actor_id);
        end loop;
    end if;

    return jsonb_build_object(
        'outcome', 'ok',
        'request', jsonb_build_object(
            'id', v_request.id,
            'kind', 'reassignment',
            'status', v_request.status,
            'reason', v_request.reason,
            'requested_at', v_request.requested_at,
            'requested_by', (select jsonb_build_object('id', p.id, 'full_name', p.full_name)
                               from public.profiles p where p.id = v_request.requested_by)
        )
    );
end;
$$;

comment on function public.request_reassignment is
    'CR-106: records the assigned coordinator''s request that a Lead reassign an event in one of p_active_statuses, unless one is already open, and notifies the Lead whose scope holds the event, or every Lead if none does. Answers {outcome: ok|not_found|not_assigned|status_changed|already_open, request}. Changes nothing on the event. API-only.';

revoke execute on function public.request_reassignment(uuid, uuid, text, text[], text)
    from public, anon, authenticated;
grant execute on function public.request_reassignment(uuid, uuid, text, text[], text)
    to service_role;

create or replace function public.decline_reassignment_request(
    p_event_id uuid,
    p_lead_id uuid,
    p_reason text,
    p_coordinator_message text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_request public.event_reassignment_requests;
begin
    select * into v_event from public.events where id = p_event_id for update;
    if not found then
        return jsonb_build_object('outcome', 'not_found');
    end if;

    update public.event_reassignment_requests
       set status = 'declined', decided_by = p_lead_id, decided_at = now(),
           decision_reason = btrim(p_reason)
     where event_id = p_event_id and status = 'open'
    returning * into v_request;
    if not found then
        return jsonb_build_object('outcome', 'no_open_request');
    end if;

    if v_request.requested_by is not null then
        perform public.add_notification(v_request.requested_by, p_event_id,
            'reassignment_declined', p_coordinator_message, p_lead_id);
    end if;

    return jsonb_build_object(
        'outcome', 'ok',
        'request', jsonb_build_object(
            'id', v_request.id,
            'kind', 'reassignment',
            'status', v_request.status,
            'reason', v_request.reason,
            'requested_at', v_request.requested_at,
            'requested_by', (select jsonb_build_object('id', p.id, 'full_name', p.full_name)
                               from public.profiles p where p.id = v_request.requested_by)
        )
    );
end;
$$;

comment on function public.decline_reassignment_request is
    'CR-106 AC5: closes the open reassignment request as declined with the Lead''s reason and notifies the coordinator who asked. Answers {outcome: ok|not_found|no_open_request, request}. The assignment is unchanged. API-only.';

revoke execute on function public.decline_reassignment_request(uuid, uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.decline_reassignment_request(uuid, uuid, text, text)
    to service_role;

-- reassign_event (CR-101, story 81) also closes the open request: same signature and
-- behaviour as 20261020110000, plus the final update. The previous coordinator is
-- already told by its event_reassigned notice (AC5).
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

    -- CR-106 AC5: the Lead has acted, so the coordinator's open request is answered.
    update public.event_reassignment_requests
       set status = 'reassigned', decided_by = p_lead_id, decided_at = now()
     where event_id = p_event_id and status = 'open';

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
    'Atomically assigns or reassigns an active event for an Event Coordinator Lead: update, assignment-history row, closing of the coordinator''s open reassignment request (CR-106) and notices. Writes no event_status_history row (not a status change). API-only.';

-- [Team decision] An event no Lead can reassign any more closes its open request.
create or replace function private.close_reassignment_request_on_unreassignable_event()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.event_reassignment_requests
       set status = 'superseded', decided_at = now(),
           decision_reason = format('Closed because the event was %s.', new.status)
     where event_id = new.id and status = 'open';
    return null;
end;
$$;

comment on function private.close_reassignment_request_on_unreassignable_event is
    'CR-106: trigger on events; when an event becomes preparation, rejected, cancelled or completed, its open reassignment request is superseded. Trigger-only.';

revoke execute on function private.close_reassignment_request_on_unreassignable_event()
    from public, anon, authenticated;

create trigger events_close_reassignment_request_when_unreassignable
    after update of status on public.events
    for each row
    when (new.status is distinct from old.status
          and new.status in ('preparation', 'rejected', 'cancelled', 'completed'))
    execute function private.close_reassignment_request_on_unreassignable_event();
