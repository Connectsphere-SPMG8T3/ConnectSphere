-- =============================================================================
-- ConnectSphere - story 62 an event's change history
--
-- The history is read from each part's own record (ADR-0008). This migration
-- adds the one record nothing kept: edits to an event's fields (AC1).
--   * event_edit_history: one row per changed field, with its old and new value.
--   * private.record_event_edits: writes those rows; story 112 calls it too.
--   * public.edit_event: saves an edit and records it in one transaction
--     (ADR-0007), so an edit can't be saved without its history.
-- Edits to a draft are saved but not recorded (IM-R1 [Assumption]).
-- =============================================================================

create table public.event_edit_history (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null,
    actor_id uuid null,
    field text not null,
    old_value jsonb null,
    new_value jsonb null,
    at timestamptz not null default now(),
    constraint event_edit_history_event_id_fkey
        foreign key (event_id) references public.events (id) on delete cascade,
    constraint event_edit_history_actor_id_fkey
        foreign key (actor_id) references public.profiles (id) on delete set null
);
create index event_edit_history_event_id_idx on public.event_edit_history (event_id, at desc);
create index event_edit_history_actor_id_idx on public.event_edit_history (actor_id);

comment on table public.event_edit_history is
    'Story 62 AC1: one row per changed field of an event, with its old and new value. Written only by private.record_event_edits.';

alter table public.event_edit_history enable row level security;
revoke all on public.event_edit_history from public, anon, authenticated;
grant select on public.event_edit_history to authenticated;
grant all on public.event_edit_history to service_role;

-- Safety net only: the API uses the secret key (ADR-0006). The event's
-- organiser and its assigned coordinator, in that active role.
create policy "event_edit_history_select_owner_or_assigned_coordinator"
    on public.event_edit_history
    for select
    to authenticated
    using (
        exists (
            select 1 from public.events e
            where e.id = event_edit_history.event_id
              and (
                  ((select private.current_user_role()) = 'event_organiser' and e.organiser_id = (select auth.uid()))
                  or ((select private.current_user_role()) = 'event_coordinator' and e.coordinator_id = (select auth.uid()))
              )
        )
    );

-- ---------------------------------------------------------------------------
-- record_event_edits: one row per field whose value changed. p_before and
-- p_after hold the same fields; a field sent unchanged is skipped.
-- ---------------------------------------------------------------------------

create or replace function private.record_event_edits(
    p_event_id uuid, p_actor_id uuid, p_before jsonb, p_after jsonb
)
returns void
language sql
security definer
set search_path = ''
as $$
    insert into public.event_edit_history (event_id, actor_id, field, old_value, new_value)
    select p_event_id, p_actor_id, f.key, p_before -> f.key, f.value
      from jsonb_each(p_after) f
     where (p_before -> f.key) is distinct from f.value;
$$;

comment on function private.record_event_edits(uuid, uuid, jsonb, jsonb) is
    'Story 62 AC1, story 112 AC5: records each changed field of an event with its old and new value. The caller writes the edit in the same transaction.';

revoke execute on function private.record_event_edits(uuid, uuid, jsonb, jsonb) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- edit_event: saves the given fields if the event is at p_expected_version and
-- in one of p_from_statuses (DB-5), and records the edit unless it is a draft.
-- Returns the saved event, or no row when the version or status has moved on.
-- Which fields a caller may change is the API's decision; this refuses any
-- field outside what an organiser's edit form holds (EventUpdateRequest).
-- ---------------------------------------------------------------------------

create or replace function public.edit_event(
    p_event_id uuid, p_actor_id uuid, p_values jsonb, p_expected_version integer, p_from_statuses text[]
)
returns setof public.events
language plpgsql
security definer
set search_path = ''
as $$
declare
    c_editable constant text[] := array[
        'name', 'event_timezone', 'purpose', 'description', 'starts_at', 'ends_at', 'expected_attendance',
        'layout_preference', 'facilities_required', 'accessibility_needs', 'preliminary_equipment_needs',
        'registration_enabled', 'registration_capacity', 'registration_opens_at', 'registration_closes_at',
        'withdrawal_closes_at', 're_registration_allowed', 'waitlist_enabled'];
    v_fields text[];
    v_event public.events;
    v_new public.events;
    v_after public.events;
begin
    select coalesce(array_agg(k), '{}') into v_fields from jsonb_object_keys(p_values) k;
    if not v_fields <@ c_editable then
        raise exception 'Not an editable event field: %', array(select unnest(v_fields) except select unnest(c_editable))
            using errcode = '22023';
    end if;

    select * into v_event from public.events where id = p_event_id for update;
    if not found or v_event.version <> p_expected_version or not (v_event.status::text = any (p_from_statuses)) then
        return;
    end if;

    v_new := jsonb_populate_record(v_event, p_values);
    update public.events set
        name = v_new.name,
        event_timezone = v_new.event_timezone,
        purpose = v_new.purpose,
        description = v_new.description,
        starts_at = v_new.starts_at,
        ends_at = v_new.ends_at,
        expected_attendance = v_new.expected_attendance,
        layout_preference = v_new.layout_preference,
        facilities_required = v_new.facilities_required,
        accessibility_needs = v_new.accessibility_needs,
        preliminary_equipment_needs = v_new.preliminary_equipment_needs,
        registration_enabled = v_new.registration_enabled,
        registration_capacity = v_new.registration_capacity,
        registration_opens_at = v_new.registration_opens_at,
        registration_closes_at = v_new.registration_closes_at,
        withdrawal_closes_at = v_new.withdrawal_closes_at,
        re_registration_allowed = v_new.re_registration_allowed,
        waitlist_enabled = v_new.waitlist_enabled,
        version = version + 1
    where id = p_event_id
    returning * into v_after;

    if v_event.status <> 'draft' then
        perform private.record_event_edits(p_event_id, p_actor_id,
            (select jsonb_object_agg(k, to_jsonb(v_event) -> k) from unnest(v_fields) k),
            (select jsonb_object_agg(k, to_jsonb(v_after) -> k) from unnest(v_fields) k));
    end if;
    return next v_after;
end;
$$;

comment on function public.edit_event(uuid, uuid, jsonb, integer, text[]) is
    'Story 62 AC1 (and 112): saves an edit to an event''s fields at the expected version and status, and records each changed field unless the event is a draft. API-only.';

revoke execute on function public.edit_event(uuid, uuid, jsonb, integer, text[]) from public, anon, authenticated;
grant execute on function public.edit_event(uuid, uuid, jsonb, integer, text[]) to service_role;

-- ---------------------------------------------------------------------------
-- AC6: history can't be edited or deleted. One trigger function on every table
-- an event's history is read from. Foreign keys keep working: a deleted event,
-- booking or venue takes its history with it, and a deleted account clears its
-- actor (ON DELETE SET NULL). Both run nested inside the RI trigger, so a
-- direct statement (depth 1) is always refused, from the API or a function.
-- connectsphere.history_maintenance lets a test-fixture reset clear history in
-- its own transaction (event_review_fixture_reset.sql); the API can't set it.
-- ---------------------------------------------------------------------------

create or replace function private.refuse_history_change()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if current_setting('connectsphere.history_maintenance', true) = 'on' then
        return case when tg_op = 'DELETE' then old else new end;
    end if;
    if pg_trigger_depth() > 1 then
        if tg_op = 'DELETE' then
            return old;
        end if;
        -- Only columns cleared to null may change.
        if not exists (select 1 from jsonb_each(to_jsonb(new)) n
                        where n.value is distinct from (to_jsonb(old) -> n.key) and n.value <> 'null'::jsonb) then
            return new;
        end if;
    end if;
    raise exception '% is a permanent record: its rows cannot be changed or deleted', tg_table_name
        using errcode = '55000';
end;
$$;

comment on function private.refuse_history_change() is
    'Story 62 AC6: refuses UPDATE and DELETE on history rows, except the cascades and set-nulls of their foreign keys and a fixture reset that sets connectsphere.history_maintenance.';

revoke execute on function private.refuse_history_change() from public, anon, authenticated;

create trigger event_status_history_append_only before update or delete on public.event_status_history
    for each row execute function private.refuse_history_change();
create trigger event_assignment_history_append_only before update or delete on public.event_assignment_history
    for each row execute function private.refuse_history_change();
create trigger event_edit_history_append_only before update or delete on public.event_edit_history
    for each row execute function private.refuse_history_change();
create trigger event_technical_history_append_only before update or delete on public.event_technical_history
    for each row execute function private.refuse_history_change();
create trigger event_safety_decisions_append_only before update or delete on public.event_safety_decisions
    for each row execute function private.refuse_history_change();
create trigger venue_booking_history_append_only before update or delete on public.venue_booking_history
    for each row execute function private.refuse_history_change();
create trigger venue_edit_history_append_only before update or delete on public.venue_edit_history
    for each row execute function private.refuse_history_change();
-- A change or cancellation request is history once decided; an open one is
-- still updated when it is decided or superseded.
create trigger event_change_requests_append_only_once_decided before update or delete on public.event_change_requests
    for each row when (old.status <> 'open') execute function private.refuse_history_change();

-- Belt and braces: no signed-in or anonymous user may change history directly.
revoke update, delete, truncate on public.event_status_history, public.event_assignment_history,
    public.event_edit_history, public.event_technical_history, public.event_safety_decisions,
    public.venue_booking_history, public.venue_edit_history from anon, authenticated;
