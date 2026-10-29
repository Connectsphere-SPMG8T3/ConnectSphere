-- =============================================================================
-- ConnectSphere - CR-110 record technical preparation progress
--
-- Once the Safety Officer has confirmed an event, Technical Support record one
-- preparation stage for the whole event, with an internal note (AC2, RD-R2).
-- public.set_technical_preparation does it in one transaction (ADR-0007):
--   * locks the event and refuses any status but Confirmed or Preparation (AC1);
--   * saves the stage and note and records each change in the technical
--     history, never the note's text (AC5, 24 AC12);
--   * on a Confirmed event, moves it to Preparation through
--     private.start_preparation, which venue preparation (CR-109) calls too
--     (68 AC1, AC3).
-- The stage never changes technical status (SCRUM-24 AC11). Both functions are
-- API-only (ADR-0006).
-- =============================================================================

-- The stages named in the M3 meeting, shared with venue preparation (CR-109).
create type public.preparation_stage as enum ('not_started', 'in_preparation', 'in_progress', 'completed');

-- One row per event once Technical Support first record a change; no row means
-- Not started. Its own table, not columns on events, so the note stays out of
-- what an organiser can read directly (AUTH-R2, as equipment_requests.technical_notes).
create table public.event_technical_preparation (
    event_id uuid primary key references public.events (id) on delete cascade,
    stage public.preparation_stage not null,
    note text null,
    updated_by uuid null,
    updated_at timestamptz not null default now(),
    constraint event_technical_preparation_updated_by_fkey
        foreign key (updated_by) references public.profiles (id) on delete set null,
    constraint event_technical_preparation_note_length
        check (note is null or length(btrim(note)) between 1 and 2000)
);
create index event_technical_preparation_updated_by_idx on public.event_technical_preparation (updated_by);

comment on table public.event_technical_preparation is
    'CR-110 AC2: Technical Support''s preparation stage and internal note for an event. No row means Not started. Kept, but locked, when the event returns to Planning. Written only by set_technical_preparation.';
comment on column public.event_technical_preparation.note is
    'Internal (AUTH-R2): Technical Support and the assigned coordinator only, never organisers or attendees.';

alter table public.event_technical_preparation enable row level security;

-- Safety net only: the API uses the secret key. The same readers as the history.
create policy "event_technical_preparation_select_tech_support_or_assigned_coordinator"
    on public.event_technical_preparation
    for select
    to authenticated
    using (
        (select private.current_user_role()) = 'tech_support'
        or (
            (select private.current_user_role()) = 'event_coordinator'
            and exists (
                select 1 from public.events e
                where e.id = event_technical_preparation.event_id
                  and e.coordinator_id = (select auth.uid())
            )
        )
    );

-- AC5: stage changes and note edits join the technical history. The list is
-- 20261026180000's (SCRUM-44) plus CR-110's two actions.
alter table public.event_technical_history drop constraint event_technical_history_action_known;
alter table public.event_technical_history add constraint event_technical_history_action_known
    check (action = any (array['reserved', 'refused', 'not_available', 'note_updated', 'released', 're_review',
                               'exit_ticked', 'exit_unticked', 'exit_cleared', 'technical_status',
                               'needs_re_review', 'sent_for_re_review', 'edited', 'removed',
                               'preparation', 'preparation_note_updated']));

-- AC3, REQUIREMENTS §5 PreparationStarted: the coordinator and the organiser.
insert into public.notification_types (type, recipient_roles) values
    ('preparation_started', '{event_organiser,event_coordinator}');

-- ---------------------------------------------------------------------------
-- start_preparation: Confirmed -> Preparation, once (68 AC1), through
-- transition_event and lifecycle.TRANSITIONS["start_preparation"]. The caller
-- holds the event's row lock. Returns whether the event moved.
-- ---------------------------------------------------------------------------

create or replace function private.start_preparation(p_event_id uuid, p_actor_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_after public.events;
    v_message text;
begin
    select * into v_event from public.events where id = p_event_id;
    if not found or v_event.status <> 'confirmed' then
        return false;
    end if;

    -- transition_event writes the history row, bumps the version and tells the
    -- organiser (never the actor), as every lifecycle move does.
    v_message := format('Preparation has started for "%s".', v_event.name);
    select * into v_after from public.transition_event(p_event_id, p_actor_id, array['confirmed'], 'preparation',
        v_event.version, null, 'preparation_started', v_message);
    if v_after.id is null then
        return false;
    end if;
    perform public.add_notification(v_after.coordinator_id, p_event_id, 'preparation_started', v_message, p_actor_id);
    return true;
end;
$$;

comment on function private.start_preparation(uuid, uuid) is
    '68 AC1, CR-109, CR-110 AC3: moves a Confirmed event to Preparation, records it in event_status_history and notifies the organiser and coordinator (never the actor). No-op unless Confirmed. The caller locks the event first.';

revoke execute on function private.start_preparation(uuid, uuid) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- set_technical_preparation
-- ---------------------------------------------------------------------------

create or replace function public.set_technical_preparation(
    p_event_id uuid, p_actor_id uuid, p_stage text, p_note text
)
returns table (outcome text, event_status text)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_stage public.preparation_stage := p_stage::public.preparation_stage;
    v_note text := nullif(btrim(p_note), '');
    v_current public.event_technical_preparation;
    v_old_stage public.preparation_stage;
    v_changed boolean := false;
begin
    perform private.set_actor(p_actor_id);
    -- Lock the event so two updates, or an update and a status change, queue up.
    select * into v_event from public.events where id = p_event_id for update;
    if not found or v_event.status = 'draft' then
        return query select 'event_not_found', null::text;
        return;
    end if;
    -- AC1, QA3-45: only after the Safety Officer's approval.
    if v_event.status not in ('confirmed', 'preparation') then
        return query select 'not_confirmed', v_event.status::text;
        return;
    end if;

    select * into v_current from public.event_technical_preparation where event_id = p_event_id;
    v_old_stage := coalesce(v_current.stage, 'not_started');
    if v_stage is distinct from v_old_stage then
        perform private.log_technical(p_event_id, null, 'preparation', v_old_stage::text, v_stage::text);
        v_changed := true;
    end if;
    if v_note is distinct from v_current.note then
        perform private.log_technical(p_event_id, null, 'preparation_note_updated');
        v_changed := true;
    end if;

    -- Saving what is already there records nothing and moves nothing [Assumption].
    if v_changed then
        insert into public.event_technical_preparation (event_id, stage, note, updated_by, updated_at)
        values (p_event_id, v_stage, v_note, p_actor_id, now())
        on conflict (event_id) do update
            set stage = excluded.stage, note = excluded.note,
                updated_by = excluded.updated_by, updated_at = excluded.updated_at;
        perform private.start_preparation(p_event_id, p_actor_id);
    end if;

    return query select 'ok', (select status::text from public.events where id = p_event_id);
end;
$$;

comment on function public.set_technical_preparation(uuid, uuid, text, text) is
    'CR-110: sets the event''s technical preparation stage and internal note. Outcomes: ok, event_not_found, not_confirmed. A change on a Confirmed event moves it to Preparation. API-only.';

revoke execute on function public.set_technical_preparation(uuid, uuid, text, text) from public, anon, authenticated;
