-- Story 37 review and process event change requests: the real approve_event_change,
-- reject_event_change and re-review functions. Run with the Supabase MCP execute_sql
-- or `psql "$DATABASE_URL" -f`. Raises on the first failure and prints CHANGE
-- DECISION CHECKS PASSED otherwise. Everything runs inside `begin; ... rollback;`, so
-- the throwaway events, bookings and lines leave no trace. Uses the seeded organiser
-- (…0001), coordinator (…0002, who also holds venue_staff), venue staff (…0003) and
-- tech support (…0004), and the Grand Ballroom. Dates are in 2031 so no seeded
-- booking overlaps.

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    -- Rejected change: the event keeps everything.
    ('e0000000-0000-4000-8000-000000003701', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Reject change check (rolled back)',
     '2031-04-15 10:00+08', '2031-04-15 12:00+08'),
    -- Started an hour ago: refused (Q5).
    ('e0000000-0000-4000-8000-000000003702', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Started change check (rolled back)',
     now() - interval '1 hour', now() + interval '1 hour'),
    -- A draft: not found to every coordinator.
    ('e0000000-0000-4000-8000-000000003703', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'draft', 'Draft change check (rolled back)',
     null, null);

insert into public.venue_bookings (event_id, venue_id, occupied_period, status) values
    ('e0000000-0000-4000-8000-000000003701', 'b0000000-0000-4000-8000-000000000001',
     tstzrange('2031-04-15 09:00+08', '2031-04-15 13:00+08', '[)'), 'approved');

insert into public.event_change_requests (event_id, kind, reason, requested_by, changes, significant) values
    ('e0000000-0000-4000-8000-000000003701', 'change', 'More guests', 'a0000000-0000-4000-8000-000000000001',
     '{"event": [{"field": "expected_attendance", "before": 80, "after": 150}], "spaces": []}', true),
    ('e0000000-0000-4000-8000-000000003702', 'change', 'Later start', 'a0000000-0000-4000-8000-000000000001',
     '{"event": [{"field": "name", "before": "a", "after": "b"}], "spaces": []}', false);

do $$
declare
    v_reject uuid := 'e0000000-0000-4000-8000-000000003701';
    v_started uuid := 'e0000000-0000-4000-8000-000000003702';
    v_draft uuid := 'e0000000-0000-4000-8000-000000003703';
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_venue_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_decidable text[] := array['submitted', 'under_review', 'planning', 'safety_review',
                                'confirmed', 'preparation'];
    v_result jsonb;
    v_rows integer;
    v_request public.event_change_requests;
begin
    -- Reject (AC2, AC4, CR-R3): refusals first, so nothing they touch has moved yet.
    v_result := public.reject_event_change(v_reject, v_venue_staff, 'x', v_decidable, 'o');
    if v_result->>'outcome' is distinct from 'not_assigned' then
        raise exception 'CHANGE FAIL: a rejection by someone not assigned was not refused: %', v_result;
    end if;
    v_result := public.reject_event_change(v_draft, v_coordinator, 'x', v_decidable, 'o');
    if v_result->>'outcome' is distinct from 'not_found' then
        raise exception 'CHANGE FAIL: rejecting on a draft was not refused as not found: %', v_result;
    end if;
    v_result := public.reject_event_change(v_started, v_coordinator, 'x', v_decidable, 'o');
    if v_result->>'outcome' is distinct from 'started' then
        raise exception 'CHANGE FAIL: rejecting on a started event was not refused: %', v_result;
    end if;
    -- AC8: a status the API no longer allows (the event moved on under the lock).
    v_result := public.reject_event_change(v_reject, v_coordinator, 'x', array['planning'], 'o');
    if v_result->>'outcome' is distinct from 'status_changed' then
        raise exception 'CHANGE FAIL: rejecting in a refused status was not refused: %', v_result;
    end if;

    v_result := public.reject_event_change(v_reject, v_coordinator, '  Venue is fixed  ', v_decidable,
        'to organiser');
    if v_result->>'outcome' is distinct from 'ok' then
        raise exception 'CHANGE FAIL: the rejection was refused: %', v_result;
    end if;
    select * into v_request from public.event_change_requests where event_id = v_reject;
    if v_request.status <> 'rejected' or v_request.decision_reason <> 'Venue is fixed'
       or v_request.decided_by is distinct from v_coordinator or v_request.decided_at is null then
        raise exception 'CHANGE FAIL: the request was not closed as rejected with the trimmed reason';
    end if;
    if (select status from public.events where id = v_reject) <> 'confirmed'
       or not exists (select 1 from public.venue_bookings where event_id = v_reject and status = 'approved') then
        raise exception 'CHANGE FAIL: rejecting changed the event or its venue';
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_reject and type = 'event_change_rejected' and recipient_id = v_organiser
       and recipient_role = 'event_organiser' and message = 'to organiser';
    if v_rows <> 1 then raise exception 'CHANGE FAIL: the organiser was not told of the rejection once'; end if;
    select count(*) into v_rows from public.notifications where event_id = v_reject and recipient_id = v_coordinator;
    if v_rows <> 0 then raise exception 'CHANGE FAIL: the coordinator was notified of their own action (NT-R1)'; end if;
    v_result := public.reject_event_change(v_reject, v_coordinator, 'Again', v_decidable, 'o');
    if v_result->>'outcome' is distinct from 'no_open_request' then
        raise exception 'CHANGE FAIL: a second rejection was not refused: %', v_result;
    end if;

    raise notice 'CHANGE DECISION CHECKS PASSED';
end;
$$;

rollback;
