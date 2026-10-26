-- =============================================================================
-- ConnectSphere - SCRUM-44 modify or remove equipment requirements (REQUIREMENTS
-- 6.15, EQ-R3, EQ-R4)
--
-- The assigned coordinator changes a line's item, quantity or technical
-- requirements, or removes it, while the event is in Planning (AC1-AC4). Each is
-- one function that locks the event, then the line (the order every SCRUM-24
-- function takes them in), re-checks the event's status, the assignment and the
-- status the coordinator saw, so a reservation racing an edit or removal of the
-- same line can't both land (AC6).
--
-- A removed line is kept as `released`, never deleted, so the technical history
-- and safety decisions that name it still do (AC8). Every reader already treats
-- `released` as gone: technical status, readiness, the exit tick's "has
-- equipment" check, and reserving (which refuses it).
--
-- Builds on story 37's 20261025120000: its Needs re-review marker on lines, and
-- its list of history actions, which this extends.
--
-- Every function here is API-only (ADR-0002): the API checks the active role
-- first, the function re-checks state under row locks and answers an outcome
-- code instead of raising.
-- =============================================================================

-- AC8: a coordinator's change and removal are history entries of their own.
alter table public.event_technical_history drop constraint event_technical_history_action_known;
alter table public.event_technical_history add constraint event_technical_history_action_known
    check (action = any (array['reserved', 'refused', 'not_available', 'note_updated', 'released', 're_review',
                               'exit_ticked', 'exit_unticked', 'exit_cleared', 'technical_status',
                               'needs_re_review', 'sent_for_re_review', 'edited', 'removed']));

-- AC1, AC3: Technical Support hear of a change or removal of a line they had
-- already acted on.
insert into public.notification_types (type, recipient_roles) values
    ('equipment_line_changed', '{tech_support}'),
    ('equipment_line_removed', '{tech_support}');

-- Every Technical Support account (they work as a pool, AUTH-R5), never the actor
-- (NT-R1). As story 37's send_equipment_line_for_re_review tells them.
create or replace function private.notify_tech_support(p_event_id uuid, p_type text, p_message text)
returns void
language sql
security definer
set search_path = ''
as $$
    insert into public.notifications (recipient_id, recipient_role, event_id, type, message)
    select distinct ur.profile_id, 'tech_support'::public.user_role, p_event_id, p_type, p_message
      from public.user_roles ur
     where ur.role = 'tech_support'
       and ur.profile_id is distinct from private.current_actor();
$$;

revoke execute on function private.notify_tech_support(uuid, text, text) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Change a line (AC2, AC3, AC5, AC6, AC8)
-- ---------------------------------------------------------------------------

-- A Pending line stays Pending. A Reserved line goes to re-review and keeps its
-- reservation, old quantity and all, until Technical Support re-reserve or reject
-- it (EQ-R4, 37 AC6); a Needs re-review marker is settled by the same step. A
-- line already under re-review stays there. A Not available line returns to
-- Pending. Only this line is written. The SCRUM-24 trigger clears the exit tick
-- when the item or quantity changes and recalculates the technical status.
create or replace function public.update_equipment_line(
    p_line_id uuid,
    p_actor_id uuid,
    p_equipment_id uuid,
    p_quantity integer,
    p_requirements text,
    p_expected_status text
)
returns table (outcome text, line_status text)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_line public.equipment_requests;
    v_requirements text := nullif(btrim(p_requirements), '');
    v_to public.equipment_request_status;
    v_old_name text;
    v_new_name text;
    v_changes text[] := '{}';
    v_detail text;
    v_message text;
begin
    perform private.set_actor(p_actor_id);
    select * into v_event from public.events
     where id = (select event_id from public.equipment_requests where id = p_line_id)
       for update;
    select * into v_line from public.equipment_requests where id = p_line_id for update;
    if v_line.id is null or v_event.id is null then
        return query select 'line_not_found', null::text;
        return;
    end if;
    if v_event.coordinator_id is distinct from p_actor_id then
        return query select 'not_assigned', null::text;
        return;
    end if;
    if v_event.status <> 'planning' then
        return query select 'not_planning', null::text;
        return;
    end if;
    if v_line.status = 'released' or v_line.status::text is distinct from p_expected_status then
        return query select 'stale', v_line.status::text;
        return;
    end if;
    if p_equipment_id is distinct from v_line.equipment_id
       and not exists (select 1 from public.equipment
                        where id = p_equipment_id and status in ('active', 'maintenance')) then
        return query select 'unknown_equipment', null::text;
        return;
    end if;

    select name into v_old_name from public.equipment where id = v_line.equipment_id;
    select name into v_new_name from public.equipment where id = p_equipment_id;
    if p_equipment_id is distinct from v_line.equipment_id then
        v_changes := v_changes || ('Item: ' || coalesce(v_old_name, 'equipment') || ' → ' || coalesce(v_new_name, 'equipment'));
    end if;
    if p_quantity is distinct from v_line.quantity then
        v_changes := v_changes || ('Quantity: ' || v_line.quantity || ' → ' || p_quantity);
    end if;
    if v_requirements is distinct from v_line.technical_requirements then
        v_changes := v_changes || ('Technical requirements: '
            || coalesce('"' || v_line.technical_requirements || '"', 'none') || ' → '
            || coalesce('"' || v_requirements || '"', 'none'));
    end if;
    if cardinality(v_changes) = 0 then
        return query select 'unchanged', v_line.status::text;
        return;
    end if;

    v_to := case v_line.status
                when 'reserved' then 're_review'
                when 'rejected' then 'pending'
                else v_line.status
            end;
    update public.equipment_requests
       set equipment_id = p_equipment_id,
           quantity = p_quantity,
           technical_requirements = v_requirements,
           status = v_to,
           -- Not available's reason belonged to the old request; the history keeps it.
           not_available_reason = case when v_to = 'pending' then null else not_available_reason end,
           needs_re_review_since = null,
           needs_re_review_reason = null
     where id = v_line.id;

    v_detail := array_to_string(v_changes, '. ') || '.';
    perform private.log_technical(v_event.id, v_line.id, 'edited', v_line.status::text, v_to::text, v_detail);

    if v_line.status in ('reserved', 're_review', 'rejected') then
        -- Requirements text stays in the history; the notice only says it changed.
        v_message := 'The coordinator changed ' || private.line_label(v_line) || ' for "' || v_event.name || '"'
            || case when p_equipment_id is distinct from v_line.equipment_id or p_quantity is distinct from v_line.quantity
                    then ' to ' || p_quantity || ' × ' || coalesce(v_new_name, 'equipment') else '' end
            || case when v_requirements is distinct from v_line.technical_requirements
                    then ' and its technical requirements' else '' end
            || case v_line.status
                    when 'rejected' then '. It is Pending again.'
                    else '. It needs re-review; the reservation is kept until you re-approve or reject it.'
               end;
        perform private.notify_tech_support(v_event.id, 'equipment_line_changed', v_message);
    end if;

    return query select 'ok', v_to::text;
end;
$$;

comment on function public.update_equipment_line(uuid, uuid, uuid, integer, text, text) is
    'SCRUM-44 AC2/AC3: the assigned coordinator changes a line''s item, quantity or requirements while the event is in Planning. Reserved goes to re_review keeping its reservation; Not available returns to pending; Technical Support are told when they had acted on it. Outcomes: ok, unchanged, line_not_found, not_assigned, not_planning, stale, unknown_equipment. API-only.';

-- ---------------------------------------------------------------------------
-- Remove a line (AC1, AC5, AC6, AC8)
-- ---------------------------------------------------------------------------

create or replace function public.remove_equipment_line(p_line_id uuid, p_actor_id uuid, p_expected_status text)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_line public.equipment_requests;
    v_freed boolean;
    v_detail text;
begin
    perform private.set_actor(p_actor_id);
    select * into v_event from public.events
     where id = (select event_id from public.equipment_requests where id = p_line_id)
       for update;
    select * into v_line from public.equipment_requests where id = p_line_id for update;
    if v_line.id is null or v_event.id is null then
        return 'line_not_found';
    end if;
    if v_event.coordinator_id is distinct from p_actor_id then
        return 'not_assigned';
    end if;
    if v_event.status <> 'planning' then
        return 'not_planning';
    end if;
    if v_line.status = 'released' or v_line.status::text is distinct from p_expected_status then
        return 'stale';
    end if;

    -- 24 AC6: the reservation is freed and its quantity returns to availability.
    update public.equipment_reservations set status = 'cancelled'
     where request_line_id = v_line.id and status = 'confirmed';
    v_freed := found;
    update public.equipment_requests
       set status = 'released', needs_re_review_since = null, needs_re_review_reason = null
     where id = v_line.id;
    -- AC5 with 24 AC10: a status change alone doesn't clear the tick in the trigger.
    perform private.clear_exit_confirmation(v_event.id, 'An equipment line was removed.');

    v_detail := 'Removed ' || private.line_label(v_line)
        || coalesce('. Technical requirements: "' || v_line.technical_requirements || '"', '')
        || case when v_freed then '. Its reservation was released' else '' end || '.';
    perform private.log_technical(v_event.id, v_line.id, 'removed', v_line.status::text, 'released', v_detail);

    if v_line.status in ('reserved', 're_review') then
        perform private.notify_tech_support(v_event.id, 'equipment_line_removed',
            'The coordinator removed ' || private.line_label(v_line) || ' from "' || v_event.name
            || '". Its reservation was released.');
    end if;

    return 'ok';
end;
$$;

comment on function public.remove_equipment_line(uuid, uuid, text) is
    'SCRUM-44 AC1: the assigned coordinator removes a line while the event is in Planning. It is kept as released for the history; any reservation is cancelled, the exit tick cleared, and Technical Support told when it was reserved or under re-review. Outcomes: ok, line_not_found, not_assigned, not_planning, stale. API-only.';

revoke execute on function public.update_equipment_line(uuid, uuid, uuid, integer, text, text) from public, anon, authenticated;
revoke execute on function public.remove_equipment_line(uuid, uuid, text) from public, anon, authenticated;
grant execute on function public.update_equipment_line(uuid, uuid, uuid, integer, text, text) to service_role;
grant execute on function public.remove_equipment_line(uuid, uuid, text) to service_role;

-- ---------------------------------------------------------------------------
-- reserve_equipment_line: re-reserving follows the line's item (SCRUM-44 AC3)
-- Body as in 20261019120000, except that re-reserving an existing reservation
-- also moves it to the line's current item: a line under re-review may now name
-- a different item from the one it holds.
-- ---------------------------------------------------------------------------

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
           set equipment_id = v_line.equipment_id, quantity = v_line.quantity,
               start_at = v_event.starts_at, end_at = v_event.ends_at
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
