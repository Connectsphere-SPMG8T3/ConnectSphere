-- =============================================================================
-- ConnectSphere - SCRUM-34 (approve) and SCRUM-52 (reject)
--
-- event_status_history: every lifecycle transition, visible in the UI (LC-R2, QA-70).
-- notifications: in-app notices, written here; delivery UI is SCRUM-27 (69, 53).
-- transition_event: the one place a lifecycle transition is written, so the
-- status change, its history row, any hold release and the notification commit
-- together (NT-R3). Called by the API through .rpc() (ADR-0002). Reused by
-- SCRUM-12 and SCRUM-33 for their transitions.
-- =============================================================================

create table public.event_status_history (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null,
    from_status public.event_status null,
    to_status public.event_status not null,
    actor_id uuid null,
    reason text null,
    at timestamptz not null default now(),
    constraint event_status_history_event_id_fkey
        foreign key (event_id) references public.events (id) on delete cascade,
    constraint event_status_history_actor_id_fkey
        foreign key (actor_id) references public.profiles (id) on delete set null
);

comment on table public.event_status_history is
    'Append-only record of every event status transition (LC-R2). Written only by public.transition_event.';

create index event_status_history_event_at_idx on public.event_status_history (event_id, at desc);
create index event_status_history_actor_id_idx on public.event_status_history (actor_id);

create table public.notifications (
    id uuid primary key default gen_random_uuid(),
    recipient_id uuid not null references public.profiles (id) on delete cascade,
    event_id uuid null references public.events (id) on delete cascade,
    type text not null,
    message text not null,
    read_at timestamptz null,
    created_at timestamptz not null default now(),
    constraint notifications_type_not_blank check (length(btrim(type)) > 0),
    constraint notifications_message_not_blank check (length(btrim(message)) > 0)
);

comment on table public.notifications is
    'In-app notifications (REQUIREMENTS 6.20). The actor is never a recipient of their own action (NT-R1).';

create index notifications_recipient_unread_idx on public.notifications (recipient_id, read_at, created_at desc);
create index notifications_event_id_idx on public.notifications (event_id);

alter table public.event_status_history enable row level security;
alter table public.notifications enable row level security;

-- Safety net only: the API uses the secret key. The organiser acting as
-- organiser, or the assigned coordinator acting as coordinator, may read.
create policy "event_status_history_select_owner_or_assigned_coordinator"
    on public.event_status_history
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.events e
            where e.id = event_status_history.event_id
              and (
                  (e.organiser_id = (select auth.uid())
                   and (select private.current_user_role()) = 'event_organiser')
                  or (e.coordinator_id = (select auth.uid())
                      and (select private.current_user_role()) = 'event_coordinator')
              )
        )
    );

create policy "notifications_select_own"
    on public.notifications
    for select
    to authenticated
    using (recipient_id = (select auth.uid()));

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
           version = version + 1
     where id = p_event_id
    returning * into v_after;

    insert into public.event_status_history (event_id, from_status, to_status, actor_id, reason)
    values (p_event_id, v_before.status, v_after.status, p_actor_id, nullif(btrim(p_reason), ''));

    -- A rejected event must stop occupying its venue (QA2-13). Equipment
    -- reservations are released here too once SCRUM-24 builds reserving.
    if v_after.status = 'rejected' then
        update public.venue_bookings
           set status = 'released'
         where event_id = p_event_id
           and status in ('held', 'approved', 're_review');
    end if;

    if p_notify_type is not null and v_after.organiser_id is distinct from p_actor_id then
        insert into public.notifications (recipient_id, event_id, type, message)
        values (v_after.organiser_id, p_event_id, p_notify_type, p_notify_message);
    end if;

    return next v_after;
end;
$$;

comment on function public.transition_event is
    'Atomically moves an event between lifecycle statuses, records history, releases venue holds on rejection, and notifies the organiser (never the actor). API-only.';

revoke execute on function public.transition_event(uuid, uuid, text[], text, integer, text, text, text)
    from public, anon, authenticated;
grant execute on function public.transition_event(uuid, uuid, text[], text, integer, text, text, text)
    to service_role;
