-- Story 115 cancel an event: the real cancel_event and reject_cancellation_request
-- functions. Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`.
-- Raises on the first failure and prints CANCELLATION DECISION CHECKS PASSED
-- otherwise. Everything runs inside `begin; ... rollback;`, so the throwaway events,
-- bookings, lines and registrations leave no trace. Uses the seeded organiser
-- (…0001), coordinator (…0002, who also holds venue_staff), venue staff (…0003),
-- tech support (…0004), attendee (…0005) and Safety Officer (…0006), the Grand
-- Ballroom and the 4K Projector. Dates are in 2031 so no seeded booking overlaps.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    -- Approved: holds a venue, a line and a registration.
    ('e0000000-0000-4000-8000-000000001b01', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Approve check (rolled back)',
     '2031-03-15 10:00+08', '2031-03-15 12:00+08'),
    -- Rejected request: keeps everything.
    ('e0000000-0000-4000-8000-000000001b02', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Reject check (rolled back)',
     '2031-03-16 10:00+08', '2031-03-16 12:00+08'),
    -- Direct cancel with an open request (Q9).
    ('e0000000-0000-4000-8000-000000001b03', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Direct cancel check (rolled back)',
     '2031-03-17 10:00+08', '2031-03-17 12:00+08'),
    -- Approved from safety review: the Safety Officers are told (Q12).
    ('e0000000-0000-4000-8000-000000001b04', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'safety_review', 'Safety review check (rolled back)',
     '2031-03-18 10:00+08', '2031-03-18 12:00+08'),
    -- Started an hour ago: refused (Q11, LC-R5).
    ('e0000000-0000-4000-8000-000000001b05', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Started check (rolled back)',
     now() - interval '1 hour', now() + interval '1 hour'),
    -- A draft: not found to every coordinator.
    ('e0000000-0000-4000-8000-000000001b06', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'draft', 'Draft check (rolled back)',
     null, null);

insert into public.venue_bookings (event_id, venue_id, occupied_period, status) values
    ('e0000000-0000-4000-8000-000000001b01', 'b0000000-0000-4000-8000-000000000001',
     tstzrange('2031-03-15 09:00+08', '2031-03-15 13:00+08', '[)'), 'approved'),
    ('e0000000-0000-4000-8000-000000001b02', 'b0000000-0000-4000-8000-000000000001',
     tstzrange('2031-03-16 09:00+08', '2031-03-16 13:00+08', '[)'), 'approved');

insert into public.equipment_requests (event_id, equipment_id, submission_id, quantity) values
    ('e0000000-0000-4000-8000-000000001b01', 'b0000000-0000-4000-8000-000000000001', gen_random_uuid(), 2);

insert into public.event_registrations (event_id, attendee_id) values
    ('e0000000-0000-4000-8000-000000001b01', 'a0000000-0000-4000-8000-000000000005');

insert into public.event_change_requests (event_id, kind, reason, requested_by) values
    ('e0000000-0000-4000-8000-000000001b01', 'cancellation', 'Speaker withdrew', 'a0000000-0000-4000-8000-000000000001'),
    ('e0000000-0000-4000-8000-000000001b02', 'cancellation', 'Budget cut', 'a0000000-0000-4000-8000-000000000001'),
    ('e0000000-0000-4000-8000-000000001b03', 'cancellation', 'Low sign-ups', 'a0000000-0000-4000-8000-000000000001'),
    ('e0000000-0000-4000-8000-000000001b04', 'cancellation', 'Clash with a holiday', 'a0000000-0000-4000-8000-000000000001');

do $$
declare
    v_approve uuid := 'e0000000-0000-4000-8000-000000001b01';
    v_reject uuid := 'e0000000-0000-4000-8000-000000001b02';
    v_direct uuid := 'e0000000-0000-4000-8000-000000001b03';
    v_safety uuid := 'e0000000-0000-4000-8000-000000001b04';
    v_started uuid := 'e0000000-0000-4000-8000-000000001b05';
    v_draft uuid := 'e0000000-0000-4000-8000-000000001b06';
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_venue_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_tech uuid := 'a0000000-0000-4000-8000-000000000004';
    v_attendee uuid := 'a0000000-0000-4000-8000-000000000005';
    v_officer uuid := 'a0000000-0000-4000-8000-000000000006';
    v_requestable text[] := array['submitted', 'under_review', 'returned', 'planning', 'safety_review',
                                  'confirmed', 'preparation'];
    v_direct_from text[] := array['confirmed', 'planning', 'preparation'];
    v_result jsonb;
    v_rows integer;
    v_request public.event_change_requests;
    v_version integer;
begin
    -- Refusals first, so nothing they touch has moved yet.
    v_result := public.cancel_event(v_approve, v_venue_staff, 1, v_requestable, 'x', true, 'o', 's', 'a', 'f');
    if v_result->>'outcome' is distinct from 'not_assigned' then
        raise exception 'DECISION FAIL: a coordinator who is not assigned was not refused: %', v_result;
    end if;
    v_result := public.cancel_event(v_draft, v_coordinator, 1, v_requestable, 'x', true, 'o', 's', 'a', 'f');
    if v_result->>'outcome' is distinct from 'not_found' then
        raise exception 'DECISION FAIL: a draft was not refused as not found: %', v_result;
    end if;
    v_result := public.cancel_event(v_started, v_coordinator, 1, v_direct_from, 'x', false, 'o', 's', 'a', 'f');
    if v_result->>'outcome' is distinct from 'started' then
        raise exception 'DECISION FAIL: a started event was not refused: %', v_result;
    end if;
    v_result := public.cancel_event(v_approve, v_coordinator, 999, v_requestable, 'x', true, 'o', 's', 'a', 'f');
    if v_result->>'outcome' is distinct from 'status_changed'
       or (select status from public.events where id = v_approve) <> 'confirmed' then
        raise exception 'DECISION FAIL: a stale version was not refused, or it changed the event: %', v_result;
    end if;
    v_result := public.cancel_event(v_started, v_coordinator, 1, v_requestable, 'x', true, 'o', 's', 'a', 'f');
    if v_result->>'outcome' is distinct from 'started' then
        raise exception 'DECISION FAIL: approval of a started event was not refused: %', v_result;
    end if;

    -- AC1: approval cancels and releases everything in one call.
    select version into v_version from public.events where id = v_approve;
    v_result := public.cancel_event(v_approve, v_coordinator, v_version, v_requestable,
        'Cancellation approved. Organiser''s reason: Speaker withdrew', true,
        'to organiser', 'to staff', 'to attendees', 'to safety');
    if v_result->>'outcome' is distinct from 'ok' or v_result->'event'->>'status' is distinct from 'cancelled' then
        raise exception 'DECISION FAIL: approval did not cancel the event: %', v_result;
    end if;
    if exists (select 1 from public.venue_bookings
                where event_id = v_approve and status in ('held', 'approved', 're_review')) then
        raise exception 'DECISION FAIL: approval left a venue booking occupying the venue (Q1)';
    end if;
    if exists (select 1 from public.equipment_requests where event_id = v_approve and status <> 'released') then
        raise exception 'DECISION FAIL: approval left an equipment line unreleased';
    end if;
    if exists (select 1 from public.event_registrations where event_id = v_approve and status <> 'cancelled') then
        raise exception 'DECISION FAIL: approval left a registration active';
    end if;
    select * into v_request from public.event_change_requests where event_id = v_approve;
    if v_request.status <> 'approved' or v_request.decided_by is distinct from v_coordinator
       or v_request.decided_at is null or v_request.decision_reason is not null then
        raise exception 'DECISION FAIL: the approved request was not closed as approved by the coordinator';
    end if;
    select count(*) into v_rows from public.event_status_history
     where event_id = v_approve and to_status = 'cancelled' and actor_id = v_coordinator
       and reason = 'Cancellation approved. Organiser''s reason: Speaker withdrew';
    if v_rows <> 1 then raise exception 'DECISION FAIL: the history row is missing or has the wrong reason (AC6)'; end if;

    -- Who heard: the organiser and attendee in their roles, each pool once, not the actor.
    select count(*) into v_rows from public.notifications
     where event_id = v_approve and type = 'event_cancelled' and recipient_id = v_organiser
       and recipient_role = 'event_organiser' and message = 'to organiser';
    if v_rows <> 1 then raise exception 'DECISION FAIL: the organiser was not notified once, as organiser'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_approve and type = 'attendee_event_cancelled' and recipient_id = v_attendee
       and recipient_role = 'attendee' and message = 'to attendees';
    if v_rows <> 1 then raise exception 'DECISION FAIL: the registered attendee was not notified once'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_approve and type = 'event_cancelled' and recipient_id = v_venue_staff
       and recipient_role = 'venue_staff' and message = 'to staff';
    if v_rows <> 1 then raise exception 'DECISION FAIL: venue staff were not notified once, as venue staff'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_approve and type = 'event_cancelled' and recipient_id = v_tech
       and recipient_role = 'tech_support' and message = 'to staff';
    if v_rows <> 1 then raise exception 'DECISION FAIL: tech support was not notified once, as tech support'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_approve and recipient_id = v_coordinator;
    if v_rows <> 0 then raise exception 'DECISION FAIL: the coordinator was notified of their own action (NT-R1)'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_approve and recipient_role = 'safety_officer';
    if v_rows <> 0 then raise exception 'DECISION FAIL: Safety Officers heard of an event not in safety review'; end if;
    select count(*) into v_rows from public.notifications where event_id = v_approve and recipient_role is null;
    if v_rows <> 0 then raise exception 'DECISION FAIL: a notification has no role, so nobody can read it'; end if;

    -- A second approval finds nothing to approve.
    v_result := public.cancel_event(v_approve, v_coordinator, v_version + 1, v_requestable, 'x', true, 'o', 's', 'a', 'f');
    if v_result->>'outcome' is distinct from 'no_open_request' then
        raise exception 'DECISION FAIL: a second approval was not refused: %', v_result;
    end if;

    -- AC2: rejection closes the request with the reason; the event keeps everything.
    v_result := public.reject_cancellation_request(v_reject, v_venue_staff, 'x', 'o');
    if v_result->>'outcome' is distinct from 'not_assigned' then
        raise exception 'DECISION FAIL: a rejection by someone not assigned was not refused: %', v_result;
    end if;
    v_result := public.reject_cancellation_request(v_reject, v_coordinator, '  Venue already paid  ', 'to organiser');
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'DECISION FAIL: the rejection was refused: %', v_result;
    end if;
    select * into v_request from public.event_change_requests where event_id = v_reject;
    if v_request.status <> 'rejected' or v_request.decision_reason <> 'Venue already paid'
       or v_request.decided_by is distinct from v_coordinator or v_request.decided_at is null then
        raise exception 'DECISION FAIL: the request was not closed as rejected with the trimmed reason';
    end if;
    if (select status from public.events where id = v_reject) <> 'planning'
       or not exists (select 1 from public.venue_bookings where event_id = v_reject and status = 'approved') then
        raise exception 'DECISION FAIL: rejecting changed the event or released its venue';
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_reject and type = 'event_cancellation_rejected' and recipient_id = v_organiser
       and recipient_role = 'event_organiser' and message = 'to organiser';
    if v_rows <> 1 then raise exception 'DECISION FAIL: the organiser was not told of the rejection once'; end if;
    v_result := public.reject_cancellation_request(v_reject, v_coordinator, 'Again', 'o');
    if v_result->>'outcome' is distinct from 'no_open_request' then
        raise exception 'DECISION FAIL: a second rejection was not refused: %', v_result;
    end if;
    v_result := public.reject_cancellation_request(v_draft, v_coordinator, 'x', 'o');
    if v_result->>'outcome' is distinct from 'not_found' then
        raise exception 'DECISION FAIL: rejecting on a draft was not refused as not found: %', v_result;
    end if;

    -- AC3 + Q9: a direct cancel closes the open request as approved with the coordinator's reason.
    select version into v_version from public.events where id = v_direct;
    v_result := public.cancel_event(v_direct, v_coordinator, v_version, v_direct_from,
        'No replacement venue', false, 'o', 's', 'a', 'f');
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'DECISION FAIL: the direct cancel was refused: %', v_result;
    end if;
    select * into v_request from public.event_change_requests where event_id = v_direct;
    if v_request.status <> 'approved' or v_request.decision_reason <> 'No replacement venue' then
        raise exception 'DECISION FAIL: the direct cancel did not close the open request as approved (Q9)';
    end if;

    -- Q12: approving from safety review tells each Safety Officer, as Safety Officer.
    select version into v_version from public.events where id = v_safety;
    v_result := public.cancel_event(v_safety, v_coordinator, v_version, v_requestable, 'r', true, 'o', 's', 'a', 'to safety');
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'DECISION FAIL: approval from safety review was refused: %', v_result;
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_safety and type = 'event_cancelled' and recipient_id = v_officer
       and recipient_role = 'safety_officer' and message = 'to safety';
    if v_rows <> 1 then raise exception 'DECISION FAIL: the Safety Officer was not told once (Q12)'; end if;

    -- API-only: not callable by signed-in or anonymous users.
    if has_function_privilege('authenticated',
            'public.cancel_event(uuid, uuid, integer, text[], text, boolean, text, text, text, text)', 'execute')
       or has_function_privilege('anon',
            'public.cancel_event(uuid, uuid, integer, text[], text, boolean, text, text, text, text)', 'execute')
       or has_function_privilege('authenticated',
            'public.reject_cancellation_request(uuid, uuid, text, text)', 'execute')
       or has_function_privilege('anon',
            'public.reject_cancellation_request(uuid, uuid, text, text)', 'execute') then
        raise exception 'DECISION FAIL: a signed-in or anonymous user can execute a decision function';
    end if;

    raise notice 'CANCELLATION DECISION CHECKS PASSED';
end $$;

rollback;
