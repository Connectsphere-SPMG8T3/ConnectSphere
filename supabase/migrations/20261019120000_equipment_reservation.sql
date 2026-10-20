-- =============================================================================
-- ConnectSphere - SCRUM-24 manage equipment reservation (REQUIREMENTS 6.15-6.17)
--
-- Technical support reserve a pending line, or mark it Not available, keep
-- internal notes and tick "Equipment does not block exits or walkways". The
-- event's technical status is derived from its lines and the tick (AC11) and
-- cached in events.technical_readiness, which only refresh_technical_status
-- writes, so every existing reader keeps working.
--
-- equipment_availability replaces SCRUM-23's Python summing with the §6.16
-- worst-moment rule (AV-R2, defect D43). The reserve function and the API's
-- availability check both call it, so they can't disagree.
--
-- Every function here is API-only (ADR-0002): the API checks the active role
-- first, the function re-checks state under row locks and answers an outcome
-- code instead of raising.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Schema
-- ---------------------------------------------------------------------------

alter table public.equipment_reservations
    add column request_line_id uuid null;
alter table public.equipment_reservations
    add constraint equipment_reservations_request_line_id_fkey
    foreign key (request_line_id) references public.equipment_requests (id) on delete set null;
-- AC4: a line holds at most one live reservation. Seed reservations have no line.
create unique index equipment_reservations_one_confirmed_per_line
    on public.equipment_reservations (request_line_id)
    where status = 'confirmed' and request_line_id is not null;
create index equipment_reservations_event_id_idx on public.equipment_reservations (event_id);

comment on column public.equipment_reservations.request_line_id is
    'The request line this reservation fills (SCRUM-24 AC4). Null for reservations made before request lines existed.';

alter table public.equipment_requests
    add column technical_notes text null,
    add column not_available_reason text null;
alter table public.equipment_requests
    add constraint equipment_requests_technical_notes_length
        check (technical_notes is null or length(btrim(technical_notes)) between 1 and 2000),
    add constraint equipment_requests_not_available_reason_length
        check (not_available_reason is null or length(btrim(not_available_reason)) between 1 and 500);

comment on column public.equipment_requests.technical_notes is
    'Technical support''s internal notes on arranging this line (AC9). Shown to tech support and the assigned coordinator only, never to organisers or attendees (AC12).';
comment on column public.equipment_requests.not_available_reason is
    'Why technical support marked the line Not available (status rejected, EQ-R3).';

alter table public.events
    add column exit_confirmed_by uuid null,
    add column exit_confirmed_at timestamptz null;
alter table public.events
    add constraint events_exit_confirmed_by_fkey
        foreign key (exit_confirmed_by) references public.profiles (id) on delete set null,
    -- Who may be null on its own (the profile was deleted); when may not.
    add constraint events_exit_confirmation_consistent
        check (exit_confirmed_at is not null or exit_confirmed_by is null);
create index events_exit_confirmed_by_idx on public.events (exit_confirmed_by);

comment on column public.events.exit_confirmed_at is
    'When technical support ticked "Equipment does not block exits or walkways" (AC10, W7 CR-06). Cleared when the equipment or venue changes.';
comment on column public.events.technical_readiness is
    'Derived technical status (SCRUM-24 AC11), cached. Written only by private.refresh_technical_status; read through events.service.technical_status.';

-- AC13: one row per status change on a line, the exit tick, or the event's
-- technical status. actor_id is null for the system. Note text is never copied
-- here (AC12).
create table public.event_technical_history (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null references public.events (id) on delete cascade,
    request_id uuid null references public.equipment_requests (id) on delete set null,
    actor_id uuid null references public.profiles (id) on delete set null,
    action text not null,
    from_status text null,
    to_status text null,
    detail text null,
    created_at timestamptz not null default now(),
    constraint event_technical_history_action_known check (action in (
        'reserved', 'refused', 'not_available', 'note_updated', 'released', 're_review',
        'exit_ticked', 'exit_unticked', 'exit_cleared', 'technical_status'
    ))
);

comment on table public.event_technical_history is
    'Append-only record of equipment line, exit-tick and technical-status changes (SCRUM-24 AC13). Written only by security-definer functions.';

create index event_technical_history_event_created_idx on public.event_technical_history (event_id, created_at desc);
create index event_technical_history_request_id_idx on public.event_technical_history (request_id);
create index event_technical_history_actor_id_idx on public.event_technical_history (actor_id);

alter table public.event_technical_history enable row level security;

-- Safety net only: the API uses the secret key. The same readers as the lines.
create policy "event_technical_history_select_tech_support_or_assigned_coordinator"
    on public.event_technical_history
    for select
    to authenticated
    using (
        (select private.current_user_role()) = 'tech_support'
        or (
            (select private.current_user_role()) = 'event_coordinator'
            and exists (
                select 1 from public.events e
                where e.id = event_technical_history.event_id
                  and e.coordinator_id = (select auth.uid())
            )
        )
    );

-- ---------------------------------------------------------------------------
-- Availability (§6.16, AV-R2): total − peak outage − peak reserved over [start, end)
-- ---------------------------------------------------------------------------

-- Usage only rises where a commitment starts, so the peak inside the window is
-- at the window's start or at a commitment's start within it.
create or replace function public.equipment_availability(
    p_equipment_ids uuid[],
    p_start_at timestamptz,
    p_end_at timestamptz,
    p_exclude_reservation_id uuid default null
)
returns table (
    equipment_id uuid,
    total_quantity integer,
    outage_quantity integer,
    reserved_quantity integer,
    free_quantity integer
)
language sql
stable
security definer
set search_path = ''
as $$
    with commitments as (
        select r.equipment_id, 'reserved'::text as kind, r.quantity, r.start_at, r.end_at
          from public.equipment_reservations r
         where r.equipment_id = any (p_equipment_ids)
           and r.status = 'confirmed'
           and r.start_at < p_end_at and r.end_at > p_start_at
           and r.id is distinct from p_exclude_reservation_id
        union all
        select u.equipment_id, 'outage', u.quantity, u.start_at, u.end_at
          from public.equipment_unavailability u
         where u.equipment_id = any (p_equipment_ids)
           and u.start_at < p_end_at and u.end_at > p_start_at
    ),
    moments as (
        select e.id as equipment_id, p_start_at as at
          from public.equipment e where e.id = any (p_equipment_ids)
        union
        select c.equipment_id, c.start_at from commitments c where c.start_at > p_start_at
    ),
    peaks as (
        select m.equipment_id,
               max(coalesce((select sum(c.quantity) from commitments c
                              where c.equipment_id = m.equipment_id and c.kind = 'outage'
                                and c.start_at <= m.at and c.end_at > m.at), 0))::integer as outage_peak,
               max(coalesce((select sum(c.quantity) from commitments c
                              where c.equipment_id = m.equipment_id and c.kind = 'reserved'
                                and c.start_at <= m.at and c.end_at > m.at), 0))::integer as reserved_peak
          from moments m
         group by m.equipment_id
    )
    select e.id, e.total_quantity, p.outage_peak, p.reserved_peak,
           greatest(0, e.total_quantity - p.outage_peak - p.reserved_peak)
      from public.equipment e
      join peaks p on p.equipment_id = e.id;
$$;

comment on function public.equipment_availability(uuid[], timestamptz, timestamptz, uuid) is
    'Free quantity per item over [start, end): total − peak concurrent outage − peak concurrent confirmed reservations (§6.16 AV-R2, D43). Excludes one reservation when re-checking it. API-only.';

-- ---------------------------------------------------------------------------
-- Technical status (AC11) and history helpers
-- ---------------------------------------------------------------------------

create or replace function public.derive_technical_status(p_event_id uuid)
returns public.technical_readiness
language sql
stable
security definer
set search_path = ''
as $$
    select case
        when not exists (select 1 from public.equipment_requests r
                          where r.event_id = p_event_id and r.status <> 'released')
            then 'not_required'::public.technical_readiness
        when exists (select 1 from public.equipment_requests r
                      where r.event_id = p_event_id and r.status = 'rejected')
            then 'issue'
        when not exists (select 1 from public.equipment_requests r
                          where r.event_id = p_event_id and r.status not in ('reserved', 'released'))
             and exists (select 1 from public.events e
                          where e.id = p_event_id and e.exit_confirmed_at is not null)
            then 'ready'
        else 'pending'
    end;
$$;

comment on function public.derive_technical_status(uuid) is
    'AC11: Not required with no live lines; Issue if any line is Not available; Ready when every line is Reserved and the exit box is ticked; Pending otherwise.';

-- The acting staff member for the transaction, so history written by triggers
-- names who caused it (AC13). Null means the system.
create or replace function private.current_actor()
returns uuid
language sql
stable
set search_path = ''
as $$
    select nullif(current_setting('connectsphere.actor_id', true), '')::uuid;
$$;

create or replace function private.set_actor(p_actor_id uuid)
returns void
language sql
set search_path = ''
as $$
    select set_config('connectsphere.actor_id', coalesce(p_actor_id::text, ''), true);
$$;

create or replace function private.log_technical(
    p_event_id uuid, p_request_id uuid, p_action text,
    p_from text default null, p_to text default null, p_detail text default null
)
returns void
language sql
security definer
set search_path = ''
as $$
    insert into public.event_technical_history (event_id, request_id, actor_id, action, from_status, to_status, detail)
    values (p_event_id, p_request_id, private.current_actor(), p_action, p_from, p_to, p_detail);
$$;

-- NT-R1 and D13: the coordinator assigned at this moment, never the actor.
create or replace function private.notify_coordinator(p_event_id uuid, p_type text, p_message text)
returns void
language sql
security definer
set search_path = ''
as $$
    insert into public.notifications (recipient_id, event_id, type, message)
    select e.coordinator_id, e.id, p_type, p_message
      from public.events e
     where e.id = p_event_id
       and e.coordinator_id is not null
       and e.coordinator_id is distinct from private.current_actor();
$$;

-- The only writer of events.technical_readiness. Doesn't bump the event's
-- version: a status change from arranging equipment isn't an edit of the event.
create or replace function private.refresh_technical_status(p_event_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_old public.technical_readiness;
    v_new public.technical_readiness;
begin
    select technical_readiness into v_old from public.events where id = p_event_id;
    if not found then
        return;
    end if;
    v_new := public.derive_technical_status(p_event_id);
    if v_new is distinct from v_old then
        update public.events set technical_readiness = v_new where id = p_event_id;
        perform private.log_technical(p_event_id, null, 'technical_status', v_old::text, v_new::text);
    end if;
end;
$$;

-- AC10, D4: a change to the event's equipment or venue clears the tick.
create or replace function private.clear_exit_confirmation(p_event_id uuid, p_detail text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.events
       set exit_confirmed_by = null, exit_confirmed_at = null
     where id = p_event_id and exit_confirmed_at is not null;
    if found then
        perform private.log_technical(p_event_id, null, 'exit_cleared', null, null, p_detail);
    end if;
end;
$$;

create or replace function private.line_label(p_line public.equipment_requests)
returns text
language sql
stable
security definer
set search_path = ''
as $$
    select p_line.quantity || ' × ' || coalesce((select name from public.equipment where id = p_line.equipment_id), 'equipment');
$$;

-- AC6, RS-R3: frees every confirmed reservation of a rejected or cancelled
-- event and releases its open lines.
create or replace function private.release_event_equipment(p_event_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_line public.equipment_requests;
begin
    update public.equipment_reservations
       set status = 'cancelled'
     where event_id = p_event_id and status = 'confirmed';
    for v_line in
        select * from public.equipment_requests
         where event_id = p_event_id and status in ('pending', 'reserved', 're_review')
         order by id
         for update
    loop
        update public.equipment_requests set status = 'released' where id = v_line.id;
        perform private.log_technical(p_event_id, v_line.id, 'released', v_line.status::text, 'released');
    end loop;
end;
$$;

-- ---------------------------------------------------------------------------
-- Triggers: keep the cached status and the exit tick in step with the lines
-- and the venue (AC6, AC10, AC11), whichever story changes them.
-- ---------------------------------------------------------------------------

create or replace function private.equipment_request_changed()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if tg_op = 'DELETE' then
        -- An event being deleted takes its lines with it; nothing to record.
        if not exists (select 1 from public.events where id = old.event_id) then
            return old;
        end if;
        perform private.clear_exit_confirmation(old.event_id, 'An equipment line was removed.');
        perform private.refresh_technical_status(old.event_id);
        return old;
    end if;
    if tg_op = 'INSERT' then
        perform private.clear_exit_confirmation(new.event_id, 'An equipment line was added.');
    elsif new.equipment_id is distinct from old.equipment_id or new.quantity is distinct from old.quantity then
        perform private.clear_exit_confirmation(new.event_id, 'An equipment line''s item or quantity changed.');
    end if;
    perform private.refresh_technical_status(new.event_id);
    return new;
end;
$$;

-- AC6 (story 44): removing a line frees its reservation before the link is lost.
create or replace function private.equipment_request_removed()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.equipment_reservations
       set status = 'cancelled'
     where request_line_id = old.id and status = 'confirmed';
    if found and exists (select 1 from public.events where id = old.event_id) then
        perform private.log_technical(old.event_id, old.id, 'released', old.status::text, null,
                                      private.line_label(old) || ' removed.');
    end if;
    return old;
end;
$$;

create trigger equipment_requests_release_on_delete
    before delete on public.equipment_requests
    for each row execute function private.equipment_request_removed();

create trigger equipment_requests_refresh_technical_status
    after insert or delete or update of equipment_id, quantity, status on public.equipment_requests
    for each row execute function private.equipment_request_changed();

-- D4: a new booking, a different venue or space, or a booking that stops
-- occupying is a venue change. Approval and flags are not.
create or replace function private.venue_booking_changed()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if tg_op = 'INSERT'
       or new.venue_id is distinct from old.venue_id
       or new.event_space_request_id is distinct from old.event_space_request_id
       or (old.status in ('held', 'approved', 're_review')
           and new.status not in ('held', 'approved', 're_review')) then
        perform private.clear_exit_confirmation(new.event_id, 'The event''s venue booking changed.');
        perform private.refresh_technical_status(new.event_id);
    end if;
    return new;
end;
$$;

create trigger venue_bookings_clear_exit_confirmation
    after insert or update of venue_id, event_space_request_id, status on public.venue_bookings
    for each row execute function private.venue_booking_changed();

revoke execute on function private.current_actor() from public, anon, authenticated;
revoke execute on function private.set_actor(uuid) from public, anon, authenticated;
revoke execute on function private.log_technical(uuid, uuid, text, text, text, text) from public, anon, authenticated;
revoke execute on function private.notify_coordinator(uuid, text, text) from public, anon, authenticated;
revoke execute on function private.refresh_technical_status(uuid) from public, anon, authenticated;
revoke execute on function private.clear_exit_confirmation(uuid, text) from public, anon, authenticated;
revoke execute on function private.line_label(public.equipment_requests) from public, anon, authenticated;
revoke execute on function private.release_event_equipment(uuid) from public, anon, authenticated;
revoke execute on function private.equipment_request_changed() from public, anon, authenticated;
revoke execute on function private.equipment_request_removed() from public, anon, authenticated;
revoke execute on function private.venue_booking_changed() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Staff actions (API-only)
-- ---------------------------------------------------------------------------

-- Each line action locks the event, then the line (the order
-- safety_return_event uses, so they never deadlock). Reserving then locks the
-- catalogue item, so two reserves of the same item queue up and the second
-- re-reads availability after the first commits (AC5, RS-R2).

create or replace function public.reserve_equipment_line(p_line_id uuid, p_actor_id uuid)
returns table (outcome text, free_quantity integer, left_ready boolean)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_line public.equipment_requests;
    v_reservation_id uuid;
    v_free integer;
    v_before public.technical_readiness;
begin
    perform private.set_actor(p_actor_id);
    select * into v_event from public.events
     where id = (select event_id from public.equipment_requests where id = p_line_id)
       for update;
    select * into v_line from public.equipment_requests where id = p_line_id for update;
    if v_line.id is null or v_event.id is null then
        return query select 'line_not_found', null::integer, false;
        return;
    end if;
    if v_event.status not in ('planning', 'safety_review', 'confirmed') then
        return query select 'event_closed', null::integer, false;
        return;
    end if;
    -- D8: a line flagged for re-review is cleared by reserving it again.
    if v_line.status not in ('pending', 're_review') then
        return query select 'not_reservable', null::integer, false;
        return;
    end if;
    if v_event.starts_at is null or v_event.ends_at is null then
        return query select 'no_schedule', null::integer, false;
        return;
    end if;
    v_before := v_event.technical_readiness;

    perform 1 from public.equipment where id = v_line.equipment_id for update;
    select id into v_reservation_id from public.equipment_reservations
     where request_line_id = v_line.id and status = 'confirmed';
    select a.free_quantity into v_free
      from public.equipment_availability(array[v_line.equipment_id], v_event.starts_at, v_event.ends_at, v_reservation_id) a;
    v_free := coalesce(v_free, 0);

    if v_free < v_line.quantity then
        perform private.log_technical(v_event.id, v_line.id, 'refused', v_line.status::text, v_line.status::text,
                                      'Requested ' || v_line.quantity || '; ' || v_free || ' free.');
        return query select 'insufficient', v_free, false;
        return;
    end if;

    if v_reservation_id is null then
        insert into public.equipment_reservations
            (equipment_id, event_id, quantity, start_at, end_at, status, request_line_id)
        values (v_line.equipment_id, v_event.id, v_line.quantity, v_event.starts_at, v_event.ends_at, 'confirmed', v_line.id);
    else
        update public.equipment_reservations
           set quantity = v_line.quantity, start_at = v_event.starts_at, end_at = v_event.ends_at
         where id = v_reservation_id;
    end if;
    update public.equipment_requests set status = 'reserved', not_available_reason = null where id = v_line.id;
    perform private.log_technical(v_event.id, v_line.id, 'reserved', v_line.status::text, 'reserved');
    perform private.notify_coordinator(v_event.id, 'equipment_reserved',
        'Equipment reserved: ' || private.line_label(v_line) || ' for "' || v_event.name || '".');

    return query select 'ok', v_free - v_line.quantity,
        v_before = 'ready' and (select technical_readiness from public.events where id = v_event.id) <> 'ready';
end;
$$;

comment on function public.reserve_equipment_line(uuid, uuid) is
    'SCRUM-24 AC1-5: reserves a pending or re-review line for its event''s window if enough is free. Outcomes: ok, insufficient (with free_quantity), line_not_found, event_closed, not_reservable, no_schedule. API-only.';

create or replace function public.mark_equipment_line_not_available(p_line_id uuid, p_actor_id uuid, p_reason text)
returns table (outcome text, left_ready boolean)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_line public.equipment_requests;
    v_reason text := nullif(btrim(p_reason), '');
    v_before public.technical_readiness;
begin
    if v_reason is null then
        return query select 'reason_required', false;
        return;
    end if;
    perform private.set_actor(p_actor_id);
    select * into v_event from public.events
     where id = (select event_id from public.equipment_requests where id = p_line_id)
       for update;
    select * into v_line from public.equipment_requests where id = p_line_id for update;
    if v_line.id is null or v_event.id is null then
        return query select 'line_not_found', false;
        return;
    end if;
    if v_event.status not in ('planning', 'safety_review', 'confirmed') then
        return query select 'event_closed', false;
        return;
    end if;
    if v_line.status not in ('pending', 'reserved', 're_review') then
        return query select 'not_reservable', false;
        return;
    end if;
    v_before := v_event.technical_readiness;

    -- RS-R3: a rejected line frees what it held.
    update public.equipment_reservations set status = 'cancelled'
     where request_line_id = v_line.id and status = 'confirmed';
    update public.equipment_requests set status = 'rejected', not_available_reason = v_reason where id = v_line.id;
    perform private.log_technical(v_event.id, v_line.id, 'not_available', v_line.status::text, 'rejected', v_reason);
    perform private.notify_coordinator(v_event.id, 'equipment_not_available',
        'Equipment not available: ' || private.line_label(v_line) || ' for "' || v_event.name || '". Reason: ' || v_reason);

    return query select 'ok',
        v_before = 'ready' and (select technical_readiness from public.events where id = v_event.id) <> 'ready';
end;
$$;

comment on function public.mark_equipment_line_not_available(uuid, uuid, text) is
    'SCRUM-24 AC3/AC9: marks a line Not available (status rejected) with a required reason, freeing any reservation. Outcomes: ok, reason_required, line_not_found, event_closed, not_reservable. API-only.';

create or replace function public.set_equipment_line_note(p_line_id uuid, p_actor_id uuid, p_note text)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_line public.equipment_requests;
    v_note text := nullif(btrim(p_note), '');
begin
    perform private.set_actor(p_actor_id);
    select * into v_event from public.events
     where id = (select event_id from public.equipment_requests where id = p_line_id)
       for update;
    select * into v_line from public.equipment_requests where id = p_line_id for update;
    if v_line.id is null or v_event.id is null then
        return 'line_not_found';
    end if;
    if v_event.status not in ('planning', 'safety_review', 'confirmed') then
        return 'event_closed';
    end if;
    if v_note is not distinct from v_line.technical_notes then
        return 'ok';
    end if;
    update public.equipment_requests set technical_notes = v_note where id = v_line.id;
    perform private.log_technical(v_event.id, v_line.id, 'note_updated');
    perform private.notify_coordinator(v_event.id, 'equipment_note',
        'Technical support updated the notes on ' || private.line_label(v_line) || ' for "' || v_event.name || '".');
    return 'ok';
end;
$$;

comment on function public.set_equipment_line_note(uuid, uuid, text) is
    'SCRUM-24 AC9/AC12: sets (or with blank, clears) a line''s internal technical notes and tells the coordinator. History records that notes changed, never their text. API-only.';

create or replace function public.set_exit_confirmation(p_event_id uuid, p_actor_id uuid, p_confirmed boolean)
returns table (outcome text, left_ready boolean)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
begin
    perform private.set_actor(p_actor_id);
    select * into v_event from public.events where id = p_event_id for update;
    if not found or v_event.status = 'draft' then
        return query select 'event_not_found', false;
        return;
    end if;
    if v_event.status not in ('planning', 'safety_review', 'confirmed') then
        return query select 'event_closed', false;
        return;
    end if;
    if not exists (select 1 from public.equipment_requests where event_id = p_event_id and status <> 'released') then
        return query select 'no_equipment', false;
        return;
    end if;
    if p_confirmed and v_event.exit_confirmed_at is null then
        update public.events set exit_confirmed_by = p_actor_id, exit_confirmed_at = now() where id = p_event_id;
        perform private.log_technical(p_event_id, null, 'exit_ticked');
    elsif not p_confirmed and v_event.exit_confirmed_at is not null then
        update public.events set exit_confirmed_by = null, exit_confirmed_at = null where id = p_event_id;
        perform private.log_technical(p_event_id, null, 'exit_unticked');
    end if;
    perform private.refresh_technical_status(p_event_id);
    return query select 'ok',
        v_event.technical_readiness = 'ready' and (select technical_readiness from public.events where id = p_event_id) <> 'ready';
end;
$$;

comment on function public.set_exit_confirmation(uuid, uuid, boolean) is
    'SCRUM-24 AC10: ticks or unticks "Equipment does not block exits or walkways" with who and when. Outcomes: ok, event_not_found, event_closed, no_equipment. API-only.';

-- AC7 (story 37 calls this after a date or time change). Each reservation moves
-- to the new window; one that no longer fits keeps holding its units and its
-- line goes to re_review for technical support to re-reserve or reject (D8).
create or replace function public.recheck_event_reservations(p_event_id uuid, p_actor_id uuid)
returns table (outcome text, flagged integer, left_ready boolean)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_line public.equipment_requests;
    v_reservation_id uuid;
    v_free integer;
    v_flagged integer := 0;
begin
    perform private.set_actor(p_actor_id);
    select * into v_event from public.events where id = p_event_id for update;
    if not found then
        return query select 'event_not_found', 0, false;
        return;
    end if;
    if v_event.starts_at is null or v_event.ends_at is null then
        return query select 'no_schedule', 0, false;
        return;
    end if;
    perform 1 from public.equipment
     where id in (select equipment_id from public.equipment_requests
                   where event_id = p_event_id and status in ('reserved', 're_review'))
     order by id for update;

    for v_line in
        select * from public.equipment_requests
         where event_id = p_event_id and status in ('reserved', 're_review')
         order by equipment_id, id
         for update
    loop
        update public.equipment_reservations
           set start_at = v_event.starts_at, end_at = v_event.ends_at
         where request_line_id = v_line.id and status = 'confirmed'
        returning id into v_reservation_id;
        if v_line.status <> 'reserved' then
            continue;
        end if;
        select a.free_quantity into v_free
          from public.equipment_availability(array[v_line.equipment_id], v_event.starts_at, v_event.ends_at, v_reservation_id) a;
        if coalesce(v_free, 0) < v_line.quantity then
            update public.equipment_requests set status = 're_review' where id = v_line.id;
            perform private.log_technical(p_event_id, v_line.id, 're_review', 'reserved', 're_review',
                                          'Event time changed; ' || coalesce(v_free, 0) || ' free for ' || v_line.quantity || '.');
            perform private.notify_coordinator(p_event_id, 'equipment_re_review',
                'Equipment needs re-review after a time change: ' || private.line_label(v_line)
                || ' for "' || v_event.name || '". The reservation is kept until technical support decide.');
            v_flagged := v_flagged + 1;
        end if;
    end loop;

    return query select 'ok', v_flagged,
        v_event.technical_readiness = 'ready' and (select technical_readiness from public.events where id = p_event_id) <> 'ready';
end;
$$;

comment on function public.recheck_event_reservations(uuid, uuid) is
    'SCRUM-24 AC7: re-checks an event''s reservations against its current window. A line that no longer fits goes to re_review and keeps its reservation. Outcomes: ok, event_not_found, no_schedule. API-only.';

revoke execute on function public.equipment_availability(uuid[], timestamptz, timestamptz, uuid) from public, anon, authenticated;
revoke execute on function public.derive_technical_status(uuid) from public, anon, authenticated;
revoke execute on function public.reserve_equipment_line(uuid, uuid) from public, anon, authenticated;
revoke execute on function public.mark_equipment_line_not_available(uuid, uuid, text) from public, anon, authenticated;
revoke execute on function public.set_equipment_line_note(uuid, uuid, text) from public, anon, authenticated;
revoke execute on function public.set_exit_confirmation(uuid, uuid, boolean) from public, anon, authenticated;
revoke execute on function public.recheck_event_reservations(uuid, uuid) from public, anon, authenticated;
grant execute on function public.equipment_availability(uuid[], timestamptz, timestamptz, uuid) to service_role;
grant execute on function public.derive_technical_status(uuid) to service_role;
grant execute on function public.reserve_equipment_line(uuid, uuid) to service_role;
grant execute on function public.mark_equipment_line_not_available(uuid, uuid, text) to service_role;
grant execute on function public.set_equipment_line_note(uuid, uuid, text) to service_role;
grant execute on function public.set_exit_confirmation(uuid, uuid, boolean) to service_role;
grant execute on function public.recheck_event_reservations(uuid, uuid) to service_role;

-- ---------------------------------------------------------------------------
-- transition_event: rejection and cancellation release equipment too (D1, AC6)
-- Body as in 20260924120000, plus the equipment release.
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

    -- A rejected event must stop occupying its venue (QA2-13).
    if v_after.status = 'rejected' then
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
-- Backfill: the cached status now follows the lines (no history for this).
-- ---------------------------------------------------------------------------

update public.events e
   set technical_readiness = public.derive_technical_status(e.id)
 where e.technical_readiness is distinct from public.derive_technical_status(e.id);
