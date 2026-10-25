-- SCRUM-24 equipment reservation: the real functions, triggers, history and RLS.
-- Run with `supabase db query --linked -f` (verify_live.py does). Raises on the
-- first failure and prints EQUIPMENT RESERVATION CHECKS PASSED otherwise.
-- Everything runs inside `begin; ... rollback;`, so the throwaway events,
-- equipment, lines, reservations, bookings and notices leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002), tech support (…0004)
-- and venue Boardroom Orchid (b…0004). Every throwaway event is dated 2033 so it
-- overlaps nothing seeded or left by a live check.
-- AC5 (two staff reserving the last units at once) needs two connections, so it
-- is verify_live.py's TC-EQR-021, not this script's.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    -- E1 09:00–12:00, E2 overlaps it (10:00–13:00), E3 starts as E1 ends (back to back).
    ('e0000000-0000-4000-8000-0000000008a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Reservation check E1 (rolled back)',
     '2033-03-01 09:00+08', '2033-03-01 12:00+08'),
    ('e0000000-0000-4000-8000-0000000008a2', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Reservation check E2 (rolled back)',
     '2033-03-01 10:00+08', '2033-03-01 13:00+08'),
    ('e0000000-0000-4000-8000-0000000008a3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Reservation check E3 (rolled back)',
     '2033-03-01 12:00+08', '2033-03-01 15:00+08'),
    -- E4 is another day; E5 has no schedule; E6 is rejected later; E7 is closed.
    ('e0000000-0000-4000-8000-0000000008a4', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Reservation check E4 (rolled back)',
     '2033-03-02 09:00+08', '2033-03-02 12:00+08'),
    ('e0000000-0000-4000-8000-0000000008a5', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Reservation check E5 (rolled back)',
     null, null),
    ('e0000000-0000-4000-8000-0000000008a6', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Reservation check E6 (rolled back)',
     '2033-03-05 10:00+08', '2033-03-05 12:00+08'),
    ('e0000000-0000-4000-8000-0000000008a7', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'completed', 'Reservation check E7 (rolled back)',
     '2033-03-03 09:00+08', '2033-03-03 12:00+08');

-- X: 5 units for the reserve checks. Y and Z: the §6.16 worked examples.
insert into public.equipment (id, name, equipment_type, total_quantity, status) values
    ('b0000000-0000-4000-8000-0000000008f1', 'Reservation check X (rolled back)', 'check', 5, 'active'),
    ('b0000000-0000-4000-8000-0000000008f2', 'Reservation check Y (rolled back)', 'check', 20, 'active'),
    ('b0000000-0000-4000-8000-0000000008f3', 'Reservation check Z (rolled back)', 'check', 20, 'active');

do $$
declare
    c_tech constant uuid := 'a0000000-0000-4000-8000-000000000004';
    c_coord constant uuid := 'a0000000-0000-4000-8000-000000000002';
    c_x constant uuid := 'b0000000-0000-4000-8000-0000000008f1';
    c_y constant uuid := 'b0000000-0000-4000-8000-0000000008f2';
    c_z constant uuid := 'b0000000-0000-4000-8000-0000000008f3';
    c_e1 constant uuid := 'e0000000-0000-4000-8000-0000000008a1';
    c_e2 constant uuid := 'e0000000-0000-4000-8000-0000000008a2';
    c_e3 constant uuid := 'e0000000-0000-4000-8000-0000000008a3';
    c_e4 constant uuid := 'e0000000-0000-4000-8000-0000000008a4';
    c_e5 constant uuid := 'e0000000-0000-4000-8000-0000000008a5';
    c_e6 constant uuid := 'e0000000-0000-4000-8000-0000000008a6';
    c_e7 constant uuid := 'e0000000-0000-4000-8000-0000000008a7';
    v_l1 uuid; v_l1b uuid; v_l2 uuid; v_l3 uuid; v_l4 uuid; v_l5 uuid; v_l6 uuid; v_l7 uuid;
    v_outcome text;
    v_free integer;
    v_left boolean;
    v_flagged integer;
    v_rows integer;
    v_status text;
    v_tech public.technical_readiness;
    v_version integer;
begin
    -- ---- TC-EQR-016 (D45, §6.16, AV-R2): free = total − peak outage − peak reserved
    insert into public.equipment_unavailability (equipment_id, quantity, start_at, end_at, reason)
    values (c_y, 2, '2033-04-01 08:00+08', '2033-04-01 18:00+08', 'Reservation check (rolled back)');
    insert into public.equipment_reservations (equipment_id, event_id, quantity, start_at, end_at)
    values (c_y, c_e4, 14, '2033-04-01 09:00+08', '2033-04-01 12:00+08');
    select a.free_quantity into v_free
      from public.equipment_availability(array[c_y], '2033-04-01 10:00+08', '2033-04-01 11:00+08') a;
    if v_free <> 4 then raise exception 'EQRES FAIL: §6.16 example 1 gives % free, expected 4', v_free; end if;
    select a.free_quantity into v_free
      from public.equipment_availability(array[c_y], '2033-04-02 10:00+08', '2033-04-02 11:00+08') a;
    if v_free <> 20 then raise exception 'EQRES FAIL: a window clear of everything gives %, expected 20', v_free; end if;
    select a.free_quantity into v_free
      from public.equipment_availability(array[c_y], '2033-04-01 17:00+08', '2033-04-01 19:00+08') a;
    if v_free <> 18 then raise exception 'EQRES FAIL: §6.16 example 2 gives % free, expected 18', v_free; end if;
    insert into public.equipment_reservations (equipment_id, event_id, quantity, start_at, end_at) values
        (c_z, c_e4, 10, '2033-04-01 09:00+08', '2033-04-01 11:00+08'),
        (c_z, c_e4, 10, '2033-04-01 11:00+08', '2033-04-01 13:00+08');
    select a.free_quantity into v_free
      from public.equipment_availability(array[c_z], '2033-04-01 09:00+08', '2033-04-01 13:00+08') a;
    if v_free <> 10 then raise exception 'EQRES FAIL (D45): worst moment gives % free, expected 10 not 0', v_free; end if;
    -- A cancelled reservation holds nothing.
    update public.equipment_reservations set status = 'cancelled' where equipment_id = c_z;
    select a.free_quantity into v_free
      from public.equipment_availability(array[c_z], '2033-04-01 09:00+08', '2033-04-01 13:00+08') a;
    if v_free <> 20 then raise exception 'EQRES FAIL: cancelled reservations still count (% free)', v_free; end if;

    -- ---- AC11: no lines is Not required
    if public.derive_technical_status(c_e1) <> 'not_required' then
        raise exception 'EQRES FAIL: an event with no lines is not Not required';
    end if;

    -- Lines arrive through submit_equipment_request (SCRUM-45).
    select (r.lines -> 0 ->> 'id')::uuid into v_l1 from public.submit_equipment_request(
        c_e1, c_coord, jsonb_build_array(jsonb_build_object('equipment_id', c_x, 'quantity', 3))) r;
    select (r.lines -> 0 ->> 'id')::uuid into v_l2 from public.submit_equipment_request(
        c_e2, c_coord, jsonb_build_array(jsonb_build_object('equipment_id', c_x, 'quantity', 3))) r;
    select (r.lines -> 0 ->> 'id')::uuid into v_l3 from public.submit_equipment_request(
        c_e3, c_coord, jsonb_build_array(jsonb_build_object('equipment_id', c_x, 'quantity', 5))) r;
    select (r.lines -> 0 ->> 'id')::uuid into v_l4 from public.submit_equipment_request(
        c_e4, c_coord, jsonb_build_array(jsonb_build_object('equipment_id', c_x, 'quantity', 5))) r;
    select (r.lines -> 0 ->> 'id')::uuid into v_l6 from public.submit_equipment_request(
        c_e6, c_coord, jsonb_build_array(jsonb_build_object('equipment_id', c_x, 'quantity', 4))) r;
    -- E5 (no schedule) and E7 (completed) get their lines directly.
    insert into public.equipment_requests (event_id, equipment_id, submission_id, quantity)
    values (c_e5, c_x, gen_random_uuid(), 1) returning id into v_l5;
    insert into public.equipment_requests (event_id, equipment_id, submission_id, quantity)
    values (c_e7, c_x, gen_random_uuid(), 1) returning id into v_l7;

    -- AC11: a pending line makes the cached status Pending (trigger refresh).
    select technical_readiness into v_tech from public.events where id = c_e1;
    if v_tech <> 'pending' then raise exception 'EQRES FAIL: a pending line leaves technical status %', v_tech; end if;

    -- ---- TC-EQR-017 (AC1, AC4): reserve when enough; linked; Reserved; coordinator told
    select r.outcome, r.free_quantity into v_outcome, v_free from public.reserve_equipment_line(v_l1, c_tech) r;
    if v_outcome <> 'ok' or v_free <> 2 then
        raise exception 'EQRES FAIL: reserving 3 of 5 gave % with % left', v_outcome, v_free;
    end if;
    select status into v_status from public.equipment_requests where id = v_l1;
    if v_status <> 'reserved' then raise exception 'EQRES FAIL: the reserved line is %', v_status; end if;
    select count(*) into v_rows from public.equipment_reservations
     where request_line_id = v_l1 and event_id = c_e1 and equipment_id = c_x and quantity = 3
       and status = 'confirmed' and start_at = '2033-03-01 09:00+08' and end_at = '2033-03-01 12:00+08';
    if v_rows <> 1 then raise exception 'EQRES FAIL: the reservation is not linked to its event, line and window'; end if;
    select count(*) into v_rows from public.notifications
     where recipient_id = c_coord and event_id = c_e1 and type = 'equipment_reserved';
    if v_rows <> 1 then raise exception 'EQRES FAIL: the coordinator got % reserve notices', v_rows; end if;
    select count(*) into v_rows from public.notifications where recipient_id = c_tech and event_id = c_e1;
    if v_rows <> 0 then raise exception 'EQRES FAIL: the actor was notified of their own reserve'; end if;
    -- One confirmed reservation per line.
    begin
        insert into public.equipment_reservations (equipment_id, event_id, quantity, start_at, end_at, request_line_id)
        values (c_x, c_e1, 1, '2033-03-01 09:00+08', '2033-03-01 12:00+08', v_l1);
        raise exception 'EQRES FAIL: a line took a second confirmed reservation';
    exception when unique_violation then null;
    end;
    -- A reserved line can't be reserved again.
    select r.outcome into v_outcome from public.reserve_equipment_line(v_l1, c_tech) r;
    if v_outcome <> 'not_reservable' then raise exception 'EQRES FAIL: re-reserving a reserved line gave %', v_outcome; end if;

    -- ---- TC-EQR-018 (AC2, AC3): an overlapping event sees the reduction and is refused with the free count
    select r.outcome, r.free_quantity into v_outcome, v_free from public.reserve_equipment_line(v_l2, c_tech) r;
    if v_outcome <> 'insufficient' or v_free <> 2 then
        raise exception 'EQRES FAIL: an overlapping 3 gave % with % free, expected insufficient with 2', v_outcome, v_free;
    end if;
    select status into v_status from public.equipment_requests where id = v_l2;
    if v_status <> 'pending' then raise exception 'EQRES FAIL: a refused line became %', v_status; end if;
    select count(*) into v_rows from public.equipment_reservations where request_line_id = v_l2;
    if v_rows <> 0 then raise exception 'EQRES FAIL: a refused reserve wrote a reservation'; end if;
    -- Back to back (E3 starts as E1 ends) and another day (E4) are unaffected: all 5.
    select r.outcome into v_outcome from public.reserve_equipment_line(v_l3, c_tech) r;
    if v_outcome <> 'ok' then raise exception 'EQRES FAIL: a back-to-back event could not take all 5 (%)', v_outcome; end if;
    select r.outcome into v_outcome from public.reserve_equipment_line(v_l4, c_tech) r;
    if v_outcome <> 'ok' then raise exception 'EQRES FAIL: an event on another day could not take all 5 (%)', v_outcome; end if;

    -- Other refusals.
    select r.outcome into v_outcome from public.reserve_equipment_line(gen_random_uuid(), c_tech) r;
    if v_outcome <> 'line_not_found' then raise exception 'EQRES FAIL: an unknown line gave %', v_outcome; end if;
    select r.outcome into v_outcome from public.reserve_equipment_line(v_l5, c_tech) r;
    if v_outcome <> 'no_schedule' then raise exception 'EQRES FAIL: an unscheduled event gave %', v_outcome; end if;
    select r.outcome into v_outcome from public.reserve_equipment_line(v_l7, c_tech) r;
    if v_outcome <> 'event_closed' then raise exception 'EQRES FAIL: a completed event gave %', v_outcome; end if;

    -- ---- TC-EQR-019 (AC3, AC9): Not available needs a reason; the line is Rejected; Issue; coordinator told
    select r.outcome into v_outcome from public.mark_equipment_line_not_available(v_l2, c_tech, '   ') r;
    if v_outcome <> 'reason_required' then raise exception 'EQRES FAIL: a blank reason gave %', v_outcome; end if;
    select r.outcome into v_outcome from public.mark_equipment_line_not_available(v_l2, c_tech, 'Only 2 free that morning') r;
    if v_outcome <> 'ok' then raise exception 'EQRES FAIL: marking Not available gave %', v_outcome; end if;
    select status::text into v_status from public.equipment_requests
     where id = v_l2 and not_available_reason = 'Only 2 free that morning';
    if v_status is distinct from 'rejected' then raise exception 'EQRES FAIL: the Not available line is %', v_status; end if;
    select technical_readiness into v_tech from public.events where id = c_e2;
    if v_tech <> 'issue' then raise exception 'EQRES FAIL: a Not available line leaves status %', v_tech; end if;
    select count(*) into v_rows from public.notifications
     where recipient_id = c_coord and event_id = c_e2 and type = 'equipment_not_available'
       and message like '%Only 2 free that morning%';
    if v_rows <> 1 then raise exception 'EQRES FAIL: the coordinator was not told the line is Not available'; end if;

    -- ---- TC-EQR-020 (AC9, AC12): notes are kept, the coordinator is told, history holds no note text
    select public.set_equipment_line_note(v_l1, c_tech, '  Projectors from store B  ') into v_outcome;
    if v_outcome <> 'ok' then raise exception 'EQRES FAIL: adding a note gave %', v_outcome; end if;
    if (select technical_notes from public.equipment_requests where id = v_l1) <> 'Projectors from store B' then
        raise exception 'EQRES FAIL: the note was not stored trimmed';
    end if;
    select count(*) into v_rows from public.notifications
     where recipient_id = c_coord and event_id = c_e1 and type = 'equipment_note';
    if v_rows <> 1 then raise exception 'EQRES FAIL: the coordinator was not told about the note'; end if;
    select count(*) into v_rows from public.event_technical_history where detail like '%store B%';
    if v_rows <> 0 then raise exception 'EQRES FAIL: note text was copied into history'; end if;
    select public.set_equipment_line_note(gen_random_uuid(), c_tech, 'x') into v_outcome;
    if v_outcome <> 'line_not_found' then raise exception 'EQRES FAIL: a note on an unknown line gave %', v_outcome; end if;

    -- ---- TC-EQR-022 (AC10, AC11): the exit tick makes Ready; a note keeps it; a new line clears it
    select r.outcome into v_outcome from public.set_exit_confirmation(c_e5, c_tech, true) r;
    if v_outcome <> 'ok' then raise exception 'EQRES FAIL: ticking an event with a line gave %', v_outcome; end if;
    select r.outcome into v_outcome from public.set_exit_confirmation(c_e7, c_tech, true) r;
    if v_outcome <> 'event_closed' then raise exception 'EQRES FAIL: ticking a completed event gave %', v_outcome; end if;
    select r.outcome into v_outcome from public.set_exit_confirmation(c_e1, c_tech, true) r;
    if v_outcome <> 'ok' then raise exception 'EQRES FAIL: ticking E1 gave %', v_outcome; end if;
    if not exists (select 1 from public.events where id = c_e1 and exit_confirmed_by = c_tech
                   and exit_confirmed_at is not null and technical_readiness = 'ready') then
        raise exception 'EQRES FAIL: every line Reserved plus the tick is not Ready with who and when';
    end if;
    if not exists (select 1 from public.event_technical_history where event_id = c_e1 and action = 'technical_status'
                   and from_status = 'pending' and to_status = 'ready' and actor_id = c_tech) then
        raise exception 'EQRES FAIL: the change to Ready is not in history with its actor';
    end if;
    perform public.set_equipment_line_note(v_l1, c_tech, 'Projectors from store C');
    if (select exit_confirmed_at from public.events where id = c_e1) is null then
        raise exception 'EQRES FAIL (D4): a note-only edit cleared the exit tick';
    end if;
    select (r.lines -> 0 ->> 'id')::uuid into v_l1b from public.submit_equipment_request(
        c_e1, c_coord, jsonb_build_array(jsonb_build_object('equipment_id', c_y, 'quantity', 1))) r;
    if exists (select 1 from public.events where id = c_e1 and (exit_confirmed_at is not null or exit_confirmed_by is not null)) then
        raise exception 'EQRES FAIL (AC10): adding a line did not clear the exit tick';
    end if;
    select technical_readiness into v_tech from public.events where id = c_e1;
    if v_tech <> 'pending' then raise exception 'EQRES FAIL: a new pending line leaves status %', v_tech; end if;
    if not exists (select 1 from public.event_technical_history where event_id = c_e1 and action = 'exit_cleared') then
        raise exception 'EQRES FAIL: clearing the tick is not in history';
    end if;
    -- Changing a line's quantity clears it too.
    perform public.reserve_equipment_line(v_l1b, c_tech);
    perform public.set_exit_confirmation(c_e1, c_tech, true);
    update public.equipment_requests set quantity = 2 where id = v_l1b;
    if (select exit_confirmed_at from public.events where id = c_e1) is not null then
        raise exception 'EQRES FAIL (AC10): changing a quantity did not clear the exit tick';
    end if;
    update public.equipment_requests set quantity = 1 where id = v_l1b;
    -- Unticking by hand is recorded and leaves Ready.
    perform public.set_exit_confirmation(c_e1, c_tech, true);
    select r.outcome, r.left_ready into v_outcome, v_left from public.set_exit_confirmation(c_e1, c_tech, false) r;
    if v_outcome <> 'ok' or not v_left then raise exception 'EQRES FAIL: unticking a Ready event gave % / %', v_outcome, v_left; end if;
    perform public.set_exit_confirmation(c_e1, c_tech, true);

    -- AC10: a venue change clears the tick. E4: tick, then book a venue.
    perform public.set_exit_confirmation(c_e4, c_tech, true);
    if (select technical_readiness from public.events where id = c_e4) <> 'ready' then
        raise exception 'EQRES FAIL: E4 did not become Ready';
    end if;
    insert into public.venue_bookings (event_id, venue_id, occupied_period, status)
    values (c_e4, 'b0000000-0000-4000-8000-000000000004',
            tstzrange('2033-03-02 09:00+08', '2033-03-02 12:00+08', '[)'), 'held');
    if (select exit_confirmed_at from public.events where id = c_e4) is not null then
        raise exception 'EQRES FAIL (AC10): booking a venue did not clear the exit tick';
    end if;
    -- Approving that booking is not a venue change.
    perform public.set_exit_confirmation(c_e4, c_tech, true);
    update public.venue_bookings set status = 'approved' where event_id = c_e4;
    if (select exit_confirmed_at from public.events where id = c_e4) is null then
        raise exception 'EQRES FAIL (D4): approving a booking cleared the exit tick';
    end if;

    -- ---- TC-EQR-023 (AC7, D8): a schedule change re-checks; failures are flagged, never removed
    select r.outcome into v_outcome from public.reserve_equipment_line(v_l6, c_tech) r;
    if v_outcome <> 'ok' then raise exception 'EQRES FAIL: E6 could not reserve 4 (%)', v_outcome; end if;
    -- E1 (3 reserved) moves onto E6's morning, where only 1 is free.
    select version into v_version from public.events where id = c_e1;
    update public.events set starts_at = '2033-03-05 09:00+08', ends_at = '2033-03-05 12:00+08' where id = c_e1;
    select r.outcome, r.flagged, r.left_ready into v_outcome, v_flagged, v_left
      from public.recheck_event_reservations(c_e1, null) r;
    if v_outcome <> 'ok' or v_flagged <> 1 or not v_left then
        raise exception 'EQRES FAIL: recheck gave % with % flagged, left_ready %', v_outcome, v_flagged, v_left;
    end if;
    -- Story 37 Q14: the line that no longer fits stays Reserved and is marked Needs re-review;
    -- the coordinator sends it to technical support.
    select status into v_status from public.equipment_requests where id = v_l1;
    if v_status <> 'reserved' or (select needs_re_review_reason from public.equipment_requests where id = v_l1)
                                  is distinct from 'Event time changed; 1 free for 3.' then
        raise exception 'EQRES FAIL: the line that no longer fits is % and not marked', v_status;
    end if;
    select status into v_status from public.equipment_requests where id = v_l1b;
    if v_status <> 'reserved' then raise exception 'EQRES FAIL: a line that still fits became %', v_status; end if;
    if not exists (select 1 from public.equipment_reservations where request_line_id = v_l1 and status = 'confirmed'
                   and start_at = '2033-03-05 09:00+08' and end_at = '2033-03-05 12:00+08') then
        raise exception 'EQRES FAIL: the flagged reservation was removed or not moved to the new window';
    end if;
    select a.free_quantity into v_free
      from public.equipment_availability(array[c_x], '2033-03-05 10:00+08', '2033-03-05 11:00+08') a;
    if v_free <> 0 then raise exception 'EQRES FAIL: a flagged reservation stopped counting (% free)', v_free; end if;
    select count(*) into v_rows from public.notifications
     where recipient_id = c_coord and event_id = c_e1 and type = 'equipment_re_review';
    if v_rows <> 1 then raise exception 'EQRES FAIL: the coordinator was not told about the re-review'; end if;
    if (select technical_readiness from public.events where id = c_e1) <> 'pending' then
        raise exception 'EQRES FAIL: a marked line is not Pending';
    end if;
    -- Sent to technical support, as the coordinator's send does (story 37 AC6).
    update public.equipment_requests
       set status = 're_review', needs_re_review_since = null, needs_re_review_reason = null
     where id = v_l1;
    -- D8: re-reserving is refused while it still doesn't fit, and the line stays flagged.
    select r.outcome, r.free_quantity into v_outcome, v_free from public.reserve_equipment_line(v_l1, c_tech) r;
    if v_outcome <> 'insufficient' or v_free <> 1 then
        raise exception 'EQRES FAIL: re-reserving the flagged line gave % with % free', v_outcome, v_free;
    end if;
    -- Once E6's line is Not available its units return, and the re-reserve succeeds without a second reservation.
    perform public.mark_equipment_line_not_available(v_l6, c_tech, 'Event moved');
    if exists (select 1 from public.equipment_reservations where request_line_id = v_l6 and status = 'confirmed') then
        raise exception 'EQRES FAIL (RS-R3): Not available kept the reservation';
    end if;
    select r.outcome into v_outcome from public.reserve_equipment_line(v_l1, c_tech) r;
    if v_outcome <> 'ok' then raise exception 'EQRES FAIL: re-reserving after the units returned gave %', v_outcome; end if;
    select count(*) into v_rows from public.equipment_reservations where request_line_id = v_l1;
    if v_rows <> 1 then raise exception 'EQRES FAIL: re-reserving wrote % reservations', v_rows; end if;

    -- ---- TC-EQR-024 (AC6): removing a line, or rejecting the event, returns the quantity
    delete from public.equipment_requests where id = v_l3;
    if exists (select 1 from public.equipment_reservations where event_id = c_e3 and status = 'confirmed') then
        raise exception 'EQRES FAIL: removing a line kept its reservation';
    end if;
    select version into v_version from public.events where id = c_e4;
    perform public.transition_event(c_e4, 'a0000000-0000-4000-8000-000000000002', array['planning'], 'rejected', v_version);
    if exists (select 1 from public.equipment_reservations where event_id = c_e4 and status = 'confirmed') then
        raise exception 'EQRES FAIL (D1): rejecting the event kept its equipment reservations';
    end if;
    select status into v_status from public.equipment_requests where id = v_l4;
    if v_status <> 'released' then raise exception 'EQRES FAIL: a rejected event''s line is %', v_status; end if;
    select a.free_quantity into v_free
      from public.equipment_availability(array[c_x], '2033-03-02 09:00+08', '2033-03-02 12:00+08') a;
    if v_free <> 5 then raise exception 'EQRES FAIL: released units did not come back (% free)', v_free; end if;
    select r.outcome into v_outcome from public.reserve_equipment_line(v_l4, c_tech) r;
    if v_outcome <> 'event_closed' then raise exception 'EQRES FAIL: reserving on a rejected event gave %', v_outcome; end if;

    -- ---- TC-EQR-025 (AC13): each change is in history with who and when
    select count(*) into v_rows from public.event_technical_history
     where actor_id = c_tech and created_at is not null
       and action in ('reserved', 'refused', 'not_available', 'note_updated', 'exit_ticked', 'exit_unticked');
    if v_rows < 10 then raise exception 'EQRES FAIL: only % staff actions are in history', v_rows; end if;
    if not exists (select 1 from public.event_technical_history where request_id = v_l2 and action = 'refused') then
        raise exception 'EQRES FAIL: the refused reserve is not in history';
    end if;
    -- Story 37 Q14: the time change records the marker; sending it is a step of its own.
    if not exists (select 1 from public.event_technical_history where request_id = v_l1 and action = 'needs_re_review') then
        raise exception 'EQRES FAIL: the re-review marker is not in history';
    end if;
    if not exists (select 1 from public.event_technical_history where event_id = c_e4 and action = 'released') then
        raise exception 'EQRES FAIL: the release on rejection is not in history';
    end if;
end $$;

-- API-only: no client role may call the functions.
do $$
declare
    v_fn text;
begin
    foreach v_fn in array array[
        'public.equipment_availability(uuid[],timestamptz,timestamptz,uuid)',
        'public.reserve_equipment_line(uuid,uuid)',
        'public.mark_equipment_line_not_available(uuid,uuid,text)',
        'public.set_equipment_line_note(uuid,uuid,text)',
        'public.set_exit_confirmation(uuid,uuid,boolean)',
        'public.recheck_event_reservations(uuid,uuid)'
    ] loop
        if has_function_privilege('authenticated', v_fn, 'execute') or has_function_privilege('anon', v_fn, 'execute') then
            raise exception 'EQRES FAIL: % is executable by a client role', v_fn;
        end if;
    end loop;
end $$;

-- RLS: the assigned coordinator, acting as coordinator, reads the event's history.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_technical_history where event_id = 'e0000000-0000-4000-8000-0000000008a1') = 0 then
        raise exception 'EQRES FAIL: the assigned coordinator cannot read the history';
    end if;
end $$;
reset role;

-- RLS: tech support read it.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000004","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_technical_history where event_id = 'e0000000-0000-4000-8000-0000000008a1') = 0 then
        raise exception 'EQRES FAIL: tech support cannot read the history';
    end if;
end $$;
reset role;

-- RLS (AC12): the organiser sees neither history nor lines, so never a note.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_technical_history where event_id = 'e0000000-0000-4000-8000-0000000008a1') <> 0
       or (select count(*) from public.equipment_requests where event_id = 'e0000000-0000-4000-8000-0000000008a1') <> 0 then
        raise exception 'EQRES FAIL: the organiser can read technical history or notes';
    end if;
end $$;
reset role;

-- RLS (SCRUM-76): the coordinator account acting as venue staff sees nothing.
insert into auth.sessions (id, user_id, created_at, updated_at)
values ('c0000000-0000-4000-8000-0000000008c1', 'a0000000-0000-4000-8000-000000000002', now(), now());
insert into public.session_active_roles (session_id, profile_id, role)
values ('c0000000-0000-4000-8000-0000000008c1', 'a0000000-0000-4000-8000-000000000002', 'venue_staff');
select set_config('request.jwt.claims',
    '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated","session_id":"c0000000-0000-4000-8000-0000000008c1"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_technical_history where event_id = 'e0000000-0000-4000-8000-0000000008a1') <> 0 then
        raise exception 'EQRES FAIL: the coordinator acting as venue staff can read the history';
    end if;
end $$;
reset role;

select 'EQUIPMENT RESERVATION CHECKS PASSED' as result;
rollback;
