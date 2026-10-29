-- CR-110 technical preparation: the real function, the move to Preparation,
-- history, notices and grants. Run with `supabase db query --linked -f`
-- (verify_live.py does). Raises on the first failure and prints
-- TECHNICAL PREPARATION CHECKS PASSED otherwise. Everything runs inside
-- `begin; ... rollback;`, so the throwaway events and notices leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002) and tech support (…0004).
-- Two updates racing on one Confirmed event need two connections, so that is
-- verify_live.py's TC-TPREP-009, not this script's; here the row lock's result
-- (a second update in Preparation doesn't move it again) is checked in sequence.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-0000000009b1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Preparation check C1 (rolled back)',
     '2033-05-01 09:00+08', '2033-05-01 12:00+08'),
    ('e0000000-0000-4000-8000-0000000009b2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Preparation check C2 (rolled back)',
     '2033-05-02 09:00+08', '2033-05-02 12:00+08');

do $$
declare
    c_tech constant uuid := 'a0000000-0000-4000-8000-000000000004';
    c_org constant uuid := 'a0000000-0000-4000-8000-000000000001';
    c_coord constant uuid := 'a0000000-0000-4000-8000-000000000002';
    c_e1 constant uuid := 'e0000000-0000-4000-8000-0000000009b1';
    c_e2 constant uuid := 'e0000000-0000-4000-8000-0000000009b2';
    v_outcome text;
    v_status text;
    v_version integer;
    v_rows integer;
    v_tech public.technical_readiness;
    v_blocked text;
begin
    -- ---- TC-TPREP-001 (AC1): every status but Confirmed and Preparation is refused
    foreach v_blocked in array array['submitted', 'under_review', 'returned', 'planning', 'safety_review',
                                      'rejected', 'cancelled', 'completed'] loop
        update public.events set status = v_blocked::public.event_status where id = c_e2;
        select s.outcome, s.event_status into v_outcome, v_status
          from public.set_technical_preparation(c_e2, c_tech, 'in_progress', null) s;
        if v_outcome <> 'not_confirmed' or v_status <> v_blocked then
            raise exception 'TPREP FAIL: % gave % / %, expected not_confirmed', v_blocked, v_outcome, v_status;
        end if;
    end loop;
    if exists (select 1 from public.event_technical_preparation where event_id = c_e2)
       or exists (select 1 from public.event_technical_history where event_id = c_e2) then
        raise exception 'TPREP FAIL: a refused update changed the event or wrote history';
    end if;

    update public.events set status = 'draft' where id = c_e2;
    select s.outcome into v_outcome from public.set_technical_preparation(c_e2, c_tech, 'in_progress', null) s;
    if v_outcome <> 'event_not_found' then raise exception 'TPREP FAIL: a draft gave %', v_outcome; end if;
    select s.outcome into v_outcome
      from public.set_technical_preparation('e0000000-0000-4000-8000-0000000009ff', c_tech, 'in_progress', null) s;
    if v_outcome <> 'event_not_found' then raise exception 'TPREP FAIL: a missing event gave %', v_outcome; end if;

    -- ---- TC-TPREP-002 (AC2, AC3): the first update saves, moves to Preparation, once
    select version, technical_readiness into v_version, v_tech from public.events where id = c_e1;
    select s.outcome, s.event_status into v_outcome, v_status
      from public.set_technical_preparation(c_e1, c_tech, 'in_preparation', '  Cables ordered  ') s;
    if v_outcome <> 'ok' or v_status <> 'preparation' then
        raise exception 'TPREP FAIL: the first update gave % / %', v_outcome, v_status;
    end if;
    perform 1 from public.event_technical_preparation
     where event_id = c_e1 and stage = 'in_preparation' and note = 'Cables ordered' and updated_by = c_tech;
    if not found then raise exception 'TPREP FAIL: the stage, trimmed note or who was not saved'; end if;
    if (select version from public.events where id = c_e1) <> v_version + 1 then
        raise exception 'TPREP FAIL: moving to Preparation did not bump the event version';
    end if;
    -- The stage never changes technical status (SCRUM-24 AC11).
    if (select technical_readiness from public.events where id = c_e1) is distinct from v_tech then
        raise exception 'TPREP FAIL: recording preparation changed the technical status';
    end if;

    select count(*) into v_rows from public.event_status_history
     where event_id = c_e1 and from_status = 'confirmed' and to_status = 'preparation' and actor_id = c_tech;
    if v_rows <> 1 then raise exception 'TPREP FAIL: % Confirmed -> Preparation history rows, expected 1', v_rows; end if;

    -- AC3: the organiser and the coordinator are told, in their roles; the actor isn't.
    select count(*) into v_rows from public.notifications
     where event_id = c_e1 and type = 'preparation_started'
       and ((recipient_id = c_org and recipient_role = 'event_organiser')
         or (recipient_id = c_coord and recipient_role = 'event_coordinator'));
    if v_rows <> 2 then raise exception 'TPREP FAIL: % preparation_started notices, expected 2', v_rows; end if;
    if exists (select 1 from public.notifications where event_id = c_e1 and recipient_id = c_tech) then
        raise exception 'TPREP FAIL: the actor was notified of their own update';
    end if;

    -- ---- TC-TPREP-003 (AC5): the stage change and the note edit are recorded, never the note's text
    select count(*) into v_rows from public.event_technical_history
     where event_id = c_e1 and actor_id = c_tech
       and ((action = 'preparation' and from_status = 'not_started' and to_status = 'in_preparation')
         or (action = 'preparation_note_updated' and detail is null));
    if v_rows <> 2 then raise exception 'TPREP FAIL: % preparation history rows, expected 2', v_rows; end if;
    if exists (select 1 from public.event_technical_history where event_id = c_e1 and detail like '%Cables%') then
        raise exception 'TPREP FAIL: the note text was copied into the history';
    end if;

    -- ---- TC-TPREP-004 (AC3): further updates in Preparation don't move it or notify again
    select version into v_version from public.events where id = c_e1;
    select s.event_status into v_status from public.set_technical_preparation(c_e1, c_tech, 'completed', 'Cables ordered') s;
    if v_status <> 'preparation' then raise exception 'TPREP FAIL: a later update left the event %', v_status; end if;
    if (select version from public.events where id = c_e1) <> v_version then
        raise exception 'TPREP FAIL: a later update bumped the event version';
    end if;
    if (select count(*) from public.event_status_history where event_id = c_e1 and to_status = 'preparation') <> 1
       or (select count(*) from public.notifications where event_id = c_e1 and type = 'preparation_started') <> 2 then
        raise exception 'TPREP FAIL: a later update moved the event or notified again';
    end if;

    -- Any stage can follow any other [Assumption]; a blank note clears it.
    select s.outcome into v_outcome from public.set_technical_preparation(c_e1, c_tech, 'in_progress', '   ') s;
    if v_outcome <> 'ok' or (select stage::text || coalesce(note, '-')
                               from public.event_technical_preparation where event_id = c_e1) <> 'in_progress-' then
        raise exception 'TPREP FAIL: Completed -> In progress with a blank note was not saved';
    end if;

    -- Saving what is already there records nothing.
    select count(*) into v_rows from public.event_technical_history where event_id = c_e1;
    perform public.set_technical_preparation(c_e1, c_tech, 'in_progress', null);
    if (select count(*) from public.event_technical_history where event_id = c_e1) <> v_rows then
        raise exception 'TPREP FAIL: an unchanged save wrote history';
    end if;

    -- ---- TC-TPREP-005 (Q9): back in Planning the stage is kept and locked;
    -- confirmed again, the next change moves it to Preparation again.
    update public.events set status = 'planning' where id = c_e1;
    select s.outcome into v_outcome from public.set_technical_preparation(c_e1, c_tech, 'completed', null) s;
    if v_outcome <> 'not_confirmed'
       or (select stage from public.event_technical_preparation where event_id = c_e1) <> 'in_progress' then
        raise exception 'TPREP FAIL: an event back in Planning lost or changed its stage';
    end if;
    update public.events set status = 'confirmed' where id = c_e1;
    select s.event_status into v_status from public.set_technical_preparation(c_e1, c_tech, 'completed', null) s;
    if v_status <> 'preparation' then raise exception 'TPREP FAIL: a re-confirmed event was not moved again'; end if;

    -- ---- start_preparation is a no-op unless Confirmed
    update public.events set status = 'planning' where id = c_e2;
    if private.start_preparation(c_e2, c_tech) then
        raise exception 'TPREP FAIL: start_preparation moved a Planning event';
    end if;

    -- ---- TC-TPREP-006 (AC6, ADR-0006): only the API can call either function
    if has_function_privilege('authenticated', 'public.set_technical_preparation(uuid, uuid, text, text)', 'execute')
       or has_function_privilege('anon', 'public.set_technical_preparation(uuid, uuid, text, text)', 'execute')
       or has_function_privilege('authenticated', 'private.start_preparation(uuid, uuid)', 'execute')
       or has_function_privilege('anon', 'private.start_preparation(uuid, uuid)', 'execute') then
        raise exception 'TPREP FAIL: a signed-in or anonymous user can execute a preparation function';
    end if;
end $$;

-- RLS (AC4, AUTH-R2): the organiser can read neither the note nor the history,
-- even directly; the assigned coordinator and Technical Support can.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_technical_preparation where event_id = 'e0000000-0000-4000-8000-0000000009b1') <> 0
       or (select count(*) from public.event_technical_history where event_id = 'e0000000-0000-4000-8000-0000000009b1') <> 0 then
        raise exception 'TPREP FAIL: the organiser can read the preparation note or history';
    end if;
end $$;
reset role;

select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_technical_preparation where event_id = 'e0000000-0000-4000-8000-0000000009b1') <> 1 then
        raise exception 'TPREP FAIL: the assigned coordinator cannot read the preparation';
    end if;
end $$;
reset role;

select 'TECHNICAL PREPARATION CHECKS PASSED' as result;
rollback;
