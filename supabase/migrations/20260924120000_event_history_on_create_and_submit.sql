-- =============================================================================
-- ConnectSphere - record event creation and submission in event_status_history
-- (fix/event-history-on-create; LC-R2, QA-70)
--
-- Creation: an AFTER INSERT trigger writes (none -> <inserted status>) with the
-- organiser as actor, so every insert path (API, seed, fixtures) starts an
-- event's history in the same transaction as the event itself.
-- Submission: the API now calls transition_event for draft -> under_review, so
-- transition_event stamps submitted_at the first time an event leaves draft.
-- Backfill: existing events get the creation and submission rows they missed.
-- =============================================================================

create or replace function private.record_event_created()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    -- Only organisers create events, so the organiser is always the actor.
    insert into public.event_status_history (event_id, from_status, to_status, actor_id, at)
    values (new.id, null, new.status, new.organiser_id, new.created_at);
    return new;
end;
$$;

revoke execute on function private.record_event_created() from public, anon, authenticated;

create trigger events_record_created
    after insert on public.events
    for each row
    execute function private.record_event_created();

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

comment on table public.event_status_history is
    'Append-only record of every event status transition (LC-R2): creation by the events_record_created trigger, every later transition by public.transition_event.';

-- Backfill. Every event the API created started as a draft (repository.create_event).
insert into public.event_status_history (event_id, from_status, to_status, actor_id, at)
select e.id, null, 'draft', e.organiser_id, e.created_at
  from public.events e
 where not exists (
     select 1 from public.event_status_history h
      where h.event_id = e.id and h.from_status is null
 );

insert into public.event_status_history (event_id, from_status, to_status, actor_id, at)
select e.id, 'draft', 'under_review', e.organiser_id, e.submitted_at
  from public.events e
 where e.submitted_at is not null
   and not exists (
     select 1 from public.event_status_history h
      where h.event_id = e.id and h.from_status = 'draft'
 );
