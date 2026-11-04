-- CR-109 venue preparation: the real set_venue_preparation function, which
-- bookings take progress, the move to Preparation, the unchanged-save path,
-- the stage history, who the result names, and grants. Needs the CR-109
-- migrations (20261103170000, 20261103173000, 20261103190000) applied.
-- Run with `supabase db query --linked -f` (verify_live.py does). Raises on the
-- first failure and prints VENUE PREPARATION CHECKS PASSED otherwise.
-- Everything runs inside `begin; ... rollback;`, so the throwaway events,
-- bookings, history and notices leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002), venue staff (…0003)
-- and venues Grand Ballroom (…0001), Innovation Lab (…0006) and Heritage Hall
-- (…0007), 60 days ahead so every event is upcoming whatever day this runs.

begin;

create temporary table venue_prep_check_times on commit drop as
select date_trunc('day', now()) + interval '60 days' as day0;

insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at)
select v.id::uuid, 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
       v.status::public.event_status, v.name,
       t.day0 + (v.day || ' days')::interval + interval '1 hour',
       t.day0 + (v.day || ' days')::interval + interval '3 hours'
from venue_prep_check_times t,
(values
    -- C: confirmed, its approved booking beside old bookings that aren't active.
    ('e0000000-0000-4000-8000-0000000109a1', 'confirmed', 'Venue preparation check C (rolled back)', 0),
    -- H, R: confirmed, holding only a hold or a booking under re-review (an event's
    -- space has one active booking at a time, so these can't sit beside C's).
    ('e0000000-0000-4000-8000-0000000109a3', 'confirmed', 'Venue preparation check H (rolled back)', 2),
    ('e0000000-0000-4000-8000-0000000109a4', 'confirmed', 'Venue preparation check R (rolled back)', 3),
    -- P: planning, an approved booking that stays locked (AC1, AC7).
    ('e0000000-0000-4000-8000-0000000109a2', 'planning', 'Venue preparation check P (rolled back)', 1)
) as v(id, status, name, day);

insert into public.venue_bookings (id, event_id, venue_id, booked_period, setup_minutes, status, expires_at)
select v.id::uuid, v.event_id::uuid, v.venue::uuid,
       tstzrange(t.day0 + (v.day || ' days')::interval + interval '1 hour',
                 t.day0 + (v.day || ' days')::interval + interval '3 hours', '[)'),
       0, v.status::public.venue_booking_status,
       case when v.status = 'held' then now() + interval '7 days' end
from venue_prep_check_times t,
(values
    ('d0000000-0000-4000-8000-0000000109d1', 'e0000000-0000-4000-8000-0000000109a1', 'b0000000-0000-4000-8000-000000000006', 0, 'approved'),
    ('d0000000-0000-4000-8000-0000000109e1', 'e0000000-0000-4000-8000-0000000109a1', 'b0000000-0000-4000-8000-000000000006', 0, 'rejected'),
    ('d0000000-0000-4000-8000-0000000109e2', 'e0000000-0000-4000-8000-0000000109a1', 'b0000000-0000-4000-8000-000000000006', 0, 'cancelled'),
    ('d0000000-0000-4000-8000-0000000109e3', 'e0000000-0000-4000-8000-0000000109a1', 'b0000000-0000-4000-8000-000000000006', 0, 'released'),
    ('d0000000-0000-4000-8000-0000000109e4', 'e0000000-0000-4000-8000-0000000109a1', 'b0000000-0000-4000-8000-000000000006', 0, 'expired'),
    ('d0000000-0000-4000-8000-0000000109e5', 'e0000000-0000-4000-8000-0000000109a3', 'b0000000-0000-4000-8000-000000000007', 2, 'held'),
    ('d0000000-0000-4000-8000-0000000109e6', 'e0000000-0000-4000-8000-0000000109a4', 'b0000000-0000-4000-8000-000000000001', 3, 're_review'),
    ('d0000000-0000-4000-8000-0000000109d2', 'e0000000-0000-4000-8000-0000000109a2', 'b0000000-0000-4000-8000-000000000006', 1, 'approved')
) as v(id, event_id, venue, day, status);

do $$
declare
    c_staff constant uuid := 'a0000000-0000-4000-8000-000000000003';
    c_confirmed constant uuid := 'e0000000-0000-4000-8000-0000000109a1';
    c_planning constant uuid := 'e0000000-0000-4000-8000-0000000109a2';
    c_approved constant uuid := 'd0000000-0000-4000-8000-0000000109d1';
    c_locked constant uuid := 'd0000000-0000-4000-8000-0000000109d2';
    v_inactive uuid;
    v_outcome text;
    v_status text;
    v_name text;
    v_rows integer;
begin
    -- ---- TC-VENUE-109-010 (AC2, AC3 [Assumption]): a booking that isn't approved is
    -- refused and never moves the event, even on a Confirmed event.
    foreach v_inactive in array array[
        'd0000000-0000-4000-8000-0000000109e1', 'd0000000-0000-4000-8000-0000000109e2',
        'd0000000-0000-4000-8000-0000000109e3', 'd0000000-0000-4000-8000-0000000109e4',
        'd0000000-0000-4000-8000-0000000109e5', 'd0000000-0000-4000-8000-0000000109e6']::uuid[] loop
        select s.outcome, s.event_status into v_outcome, v_status
          from public.set_venue_preparation(v_inactive, c_staff, 'in_progress', 'Should not save') s;
        if v_outcome <> 'booking_not_active' or v_status <> 'confirmed' then
            raise exception 'VPREP FAIL: booking % gave % / %, expected booking_not_active', v_inactive, v_outcome, v_status;
        end if;
    end loop;
    if exists (select 1 from public.events
                where id in (c_confirmed, 'e0000000-0000-4000-8000-0000000109a3', 'e0000000-0000-4000-8000-0000000109a4')
                  and status <> 'confirmed')
       or exists (select 1 from public.event_venue_preparation
                   where booking_id in (select id from public.venue_bookings where event_id::text like 'e0000000-0000-4000-8000-0000000109a_'))
       or exists (select 1 from public.venue_booking_history h join public.venue_bookings b on b.id = h.booking_id
                   where b.event_id::text like 'e0000000-0000-4000-8000-0000000109a_' and h.action like 'preparation%') then
        raise exception 'VPREP FAIL: an inactive booking moved the event or wrote progress or history';
    end if;

    -- AC1, AC7: a Planning event's approved booking is locked.
    select s.outcome into v_outcome from public.set_venue_preparation(c_locked, c_staff, 'completed', null) s;
    if v_outcome <> 'not_confirmed' then raise exception 'VPREP FAIL: a Planning booking gave %', v_outcome; end if;

    select s.outcome into v_outcome
      from public.set_venue_preparation('d0000000-0000-4000-8000-0000000109ff', c_staff, 'completed', null) s;
    if v_outcome <> 'booking_not_found' then raise exception 'VPREP FAIL: a missing booking gave %', v_outcome; end if;

    -- ---- AC3: the approved booking's first update saves, moves to Preparation, names who.
    select s.outcome, s.event_status, s.updated_by_name into v_outcome, v_status, v_name
      from public.set_venue_preparation(c_approved, c_staff, 'in_progress', '  Doors checked  ') s;
    if v_outcome <> 'ok' or v_status <> 'preparation' then
        raise exception 'VPREP FAIL: the first update gave % / %', v_outcome, v_status;
    end if;
    if v_name is distinct from (select full_name from public.profiles where id = c_staff) then
        raise exception 'VPREP FAIL: the result named % as the updater', v_name;
    end if;
    perform 1 from public.event_venue_preparation
     where booking_id = c_approved and stage = 'in_progress' and note = 'Doors checked' and updated_by = c_staff;
    if not found then raise exception 'VPREP FAIL: the stage, trimmed note or who was not saved'; end if;

    -- AC5: the stage change carries its old and new stage; the note edit never its text.
    select count(*) into v_rows from public.venue_booking_history
     where booking_id = c_approved and actor_id = c_staff
       and ((action = 'preparation' and old_preparation_stage = 'not_started' and new_preparation_stage = 'in_progress')
         or (action = 'preparation_note_updated' and old_preparation_stage is null and reason is null));
    if v_rows <> 2 then raise exception 'VPREP FAIL: % preparation history rows, expected 2', v_rows; end if;

    -- Saving what is already there records nothing and still names who it is by.
    select count(*) into v_rows from public.venue_booking_history where booking_id = c_approved;
    select s.outcome, s.updated_by_name into v_outcome, v_name
      from public.set_venue_preparation(c_approved, c_staff, 'in_progress', 'Doors checked') s;
    if v_outcome <> 'ok' or v_name is null
       or (select count(*) from public.venue_booking_history where booking_id = c_approved) <> v_rows then
        raise exception 'VPREP FAIL: an unchanged save wrote history or lost who it is by';
    end if;

    -- A later change in Preparation records only the stage step and doesn't move the event again.
    select s.event_status into v_status from public.set_venue_preparation(c_approved, c_staff, 'completed', 'Doors checked') s;
    if v_status <> 'preparation'
       or (select count(*) from public.event_status_history where event_id = c_confirmed and to_status = 'preparation') <> 1 then
        raise exception 'VPREP FAIL: a later update moved the event again';
    end if;
    if (select count(*) from public.venue_booking_history where booking_id = c_approved) <> v_rows + 1 then
        raise exception 'VPREP FAIL: a stage-only change wrote other history';
    end if;

    -- ADR-0006: only the API can call it.
    if has_function_privilege('authenticated', 'public.set_venue_preparation(uuid, uuid, text, text)', 'execute')
       or has_function_privilege('anon', 'public.set_venue_preparation(uuid, uuid, text, text)', 'execute') then
        raise exception 'VPREP FAIL: a signed-in or anonymous user can execute set_venue_preparation';
    end if;
end $$;

select 'VENUE PREPARATION CHECKS PASSED' as result;
rollback;
