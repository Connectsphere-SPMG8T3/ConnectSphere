-- =============================================================================
-- ConnectSphere - SCRUM-33 return an event request for amendment
--
-- amendment_requests: one row per return (message + flagged fields), closed by
-- the organiser's resubmission note (REQUIREMENTS 4, 6.4; QA-22, QA-77).
-- return_event_for_amendment / resubmit_event: wrap transition_event so the
-- status change, its history row, the amendment row and the notification commit
-- together (NT-R3). transition_event itself is unchanged. API-only (ADR-0002).
-- =============================================================================

create table public.amendment_requests (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null,
    message text not null,
    flagged_fields text[] not null default '{}',
    returned_at timestamptz not null default now(),
    resubmission_note text null,
    resubmitted_at timestamptz null,
    constraint amendment_requests_event_id_fkey
        foreign key (event_id) references public.events (id) on delete cascade,
    constraint amendment_requests_message_not_blank check (length(btrim(message)) > 0),
    constraint amendment_requests_resubmission_complete
        check ((resubmission_note is null) = (resubmitted_at is null))
);

comment on table public.amendment_requests is
    'Each return of an event for amendment (REQUIREMENTS 6.4). At most one open (not yet resubmitted) row per event. Written only by return_event_for_amendment and resubmit_event.';

create unique index amendment_requests_one_open_per_event_idx
    on public.amendment_requests (event_id) where resubmitted_at is null;
create index amendment_requests_event_returned_at_idx
    on public.amendment_requests (event_id, returned_at desc);

alter table public.amendment_requests enable row level security;

-- Safety net only: the API uses the secret key. Same readers as event_status_history.
create policy "amendment_requests_select_owner_or_assigned_coordinator"
    on public.amendment_requests
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.events e
            where e.id = amendment_requests.event_id
              and (
                  (e.organiser_id = (select auth.uid())
                   and (select private.current_user_role()) = 'event_organiser')
                  or (e.coordinator_id = (select auth.uid())
                      and (select private.current_user_role()) = 'event_coordinator')
              )
        )
    );

create or replace function public.return_event_for_amendment(
    p_event_id uuid,
    p_actor_id uuid,
    p_from_statuses text[],
    p_to_status text,
    p_expected_version integer,
    p_message text,
    p_flagged_fields text[],
    p_notify_message text
)
returns setof public.events
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_after public.events;
begin
    -- transition_event records the message as the history reason and notifies the organiser.
    select * into v_after
      from public.transition_event(p_event_id, p_actor_id, p_from_statuses, p_to_status,
                                   p_expected_version, p_message, 'event_returned', p_notify_message);
    if not found then
        return;
    end if;

    insert into public.amendment_requests (event_id, message, flagged_fields)
    values (p_event_id, btrim(p_message), coalesce(p_flagged_fields, '{}'));

    return next v_after;
end;
$$;

comment on function public.return_event_for_amendment is
    'Returns an event for amendment: status, history (message as reason), organiser notification and the amendment row, atomically. API-only.';

create or replace function public.resubmit_event(
    p_event_id uuid,
    p_actor_id uuid,
    p_from_statuses text[],
    p_to_status text,
    p_expected_version integer,
    p_note text,
    p_notify_message text
)
returns setof public.events
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_after public.events;
begin
    -- No notification here: transition_event can only notify the organiser, who is the actor.
    select * into v_after
      from public.transition_event(p_event_id, p_actor_id, p_from_statuses, p_to_status,
                                   p_expected_version, p_note, null, null);
    if not found then
        return;
    end if;

    update public.amendment_requests
       set resubmission_note = btrim(p_note),
           resubmitted_at = now()
     where event_id = p_event_id
       and resubmitted_at is null;

    if v_after.coordinator_id is not null and v_after.coordinator_id is distinct from p_actor_id then
        insert into public.notifications (recipient_id, event_id, type, message)
        values (v_after.coordinator_id, p_event_id, 'event_resubmitted', p_notify_message);
    end if;

    return next v_after;
end;
$$;

comment on function public.resubmit_event is
    'Resubmits a returned event to the same coordinator: status, history (note as reason), closes the open amendment and notifies the coordinator, atomically. API-only.';

revoke execute on function public.return_event_for_amendment(uuid, uuid, text[], text, integer, text, text[], text)
    from public, anon, authenticated;
grant execute on function public.return_event_for_amendment(uuid, uuid, text[], text, integer, text, text[], text)
    to service_role;
revoke execute on function public.resubmit_event(uuid, uuid, text[], text, integer, text, text)
    from public, anon, authenticated;
grant execute on function public.resubmit_event(uuid, uuid, text[], text, integer, text, text)
    to service_role;
