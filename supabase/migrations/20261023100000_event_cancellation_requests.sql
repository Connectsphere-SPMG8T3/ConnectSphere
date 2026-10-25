-- =============================================================================
-- ConnectSphere - Story 84 request cancellation of my event
--
-- event_change_requests: an organiser's change or cancellation request on an
-- event and the coordinator's decision (REQUIREMENTS 6.19). Story 84 writes the
-- cancellation kind; SCRUM-32/37 add change requests to the same table, and
-- story 115 records the decision on the same row. At most one open request of
-- each kind per event (CR-R1), enforced by a partial unique index.
--
-- request_event_cancellation records the request, supersedes an open change
-- request (CR-R1) and notifies the assigned coordinator, or every Event
-- Coordinator Lead while the event is unassigned, in one transaction
-- (ADR-0007). Nothing is released: arrangements stay held until the
-- coordinator decides (QA-12, story 115). API-only (ADR-0006).
-- =============================================================================

create table public.event_change_requests (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null,
    kind text not null,
    status text not null default 'open',
    reason text not null,
    requested_by uuid null,
    requested_at timestamptz not null default now(),
    decided_by uuid null,
    decided_at timestamptz null,
    decision_reason text null,
    constraint event_change_requests_event_id_fkey
        foreign key (event_id) references public.events (id) on delete cascade,
    constraint event_change_requests_requested_by_fkey
        foreign key (requested_by) references public.profiles (id) on delete set null,
    constraint event_change_requests_decided_by_fkey
        foreign key (decided_by) references public.profiles (id) on delete set null,
    constraint event_change_requests_kind_check check (kind in ('change', 'cancellation')),
    constraint event_change_requests_status_check
        check (status in ('open', 'approved', 'rejected', 'superseded')),
    constraint event_change_requests_reason_length check (length(btrim(reason)) between 1 and 1000),
    constraint event_change_requests_decision_reason_length
        check (decision_reason is null or length(btrim(decision_reason)) between 1 and 1000),
    -- Only an open request is undecided.
    constraint event_change_requests_decided_when_closed
        check ((status = 'open') = (decided_at is null))
);

comment on table public.event_change_requests is
    'Change and cancellation requests on an event and their decisions (REQUIREMENTS 6.19; story 84, SCRUM-32/37, story 115). Written only by API-only functions.';

create unique index event_change_requests_one_open_per_kind
    on public.event_change_requests (event_id, kind)
    where status = 'open';
create index event_change_requests_event_requested_at_idx
    on public.event_change_requests (event_id, requested_at);
create index event_change_requests_requested_by_idx on public.event_change_requests (requested_by);
create index event_change_requests_decided_by_idx on public.event_change_requests (decided_by);

alter table public.event_change_requests enable row level security;

-- Safety net only: the API uses the secret key. Same readers as event_comments.
create policy "event_change_requests_select_owner_or_assigned_coordinator"
    on public.event_change_requests
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.events e
            where e.id = event_change_requests.event_id
              and (
                  (e.organiser_id = (select auth.uid())
                   and (select private.current_user_role()) = 'event_organiser')
                  or (e.coordinator_id = (select auth.uid())
                      and (select private.current_user_role()) = 'event_coordinator')
              )
        )
    );

-- The coordinator when one is assigned; each Lead while the event is unassigned.
insert into public.notification_types (type, recipient_roles) values
    ('event_cancellation_requested', '{event_coordinator,event_coordinator_lead}');

create or replace function public.request_event_cancellation(
    p_event_id uuid,
    p_actor_id uuid,
    p_reason text,
    p_from_statuses text[],
    p_coordinator_message text,
    p_lead_message text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_request public.event_change_requests;
    v_lead uuid;
begin
    -- Lock the event so a concurrent decision or second request waits its turn.
    select * into v_event from public.events where id = p_event_id for update;
    if not found then
        return jsonb_build_object('outcome', 'not_found');
    end if;
    if v_event.organiser_id is distinct from p_actor_id then
        return jsonb_build_object('outcome', 'not_owner');
    end if;
    if not (v_event.status::text = any (p_from_statuses)) then
        return jsonb_build_object('outcome', 'status_changed');
    end if;
    if exists (select 1 from public.event_change_requests
                where event_id = p_event_id and kind = 'cancellation' and status = 'open') then
        return jsonb_build_object('outcome', 'already_open');
    end if;

    -- CR-R1: a cancellation request supersedes an open change request.
    update public.event_change_requests
       set status = 'superseded', decided_by = p_actor_id, decided_at = now(),
           decision_reason = 'Superseded by a cancellation request.'
     where event_id = p_event_id and kind = 'change' and status = 'open';

    insert into public.event_change_requests (event_id, kind, reason, requested_by)
    values (p_event_id, 'cancellation', btrim(p_reason), p_actor_id)
    returning * into v_request;

    if v_event.coordinator_id is not null then
        perform public.add_notification(v_event.coordinator_id, p_event_id,
            'event_cancellation_requested', p_coordinator_message, p_actor_id);
    else
        for v_lead in
            select profile_id from public.user_roles where role = 'event_coordinator_lead'
        loop
            perform public.add_notification(v_lead, p_event_id,
                'event_cancellation_requested', p_lead_message, p_actor_id);
        end loop;
    end if;

    return jsonb_build_object(
        'outcome', 'ok',
        'request', jsonb_build_object(
            'id', v_request.id,
            'kind', v_request.kind,
            'status', v_request.status,
            'reason', v_request.reason,
            'requested_at', v_request.requested_at,
            'requested_by', (select jsonb_build_object('id', p.id, 'full_name', p.full_name)
                               from public.profiles p where p.id = v_request.requested_by)
        )
    );
end;
$$;

comment on function public.request_event_cancellation is
    'Story 84: records the owner''s cancellation request on an event in one of p_from_statuses, supersedes an open change request (CR-R1) and notifies the assigned coordinator, or every Lead while unassigned. Answers {outcome: ok|not_found|not_owner|status_changed|already_open, request}. Releases nothing. API-only.';

revoke execute on function public.request_event_cancellation(uuid, uuid, text, text[], text, text)
    from public, anon, authenticated;
grant execute on function public.request_event_cancellation(uuid, uuid, text, text[], text, text)
    to service_role;
