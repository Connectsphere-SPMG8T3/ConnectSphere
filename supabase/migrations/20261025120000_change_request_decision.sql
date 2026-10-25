-- =============================================================================
-- ConnectSphere - Story 37 review and process event change requests
--
-- The assigned coordinator decides the organiser's open change request (story
-- 32). public.approve_event_change applies the requested values to the event
-- and its spaces in one transaction (ADR-0007), provided the event is still at
-- the version whose `before` values the API checked (Q8), closes the request as
-- approved and tells the organiser. public.reject_event_change closes it as rejected with the coordinator's
-- reason and tells the organiser; the event keeps its details, status and
-- arrangements (AC2, AC4, CR-R3). Decisions are refused once the event has
-- started or left the decidable statuses (AC8, Q5). API-only (ADR-0006).
-- =============================================================================

-- Q13: an approved change marks the bookings it touches Needs re-review, separately
-- from flags (so a booking can be marked and flagged at once); readiness counts a
-- marked booking as not ready. The coordinator then sends it to venue staff.
alter table public.venue_bookings
    add column needs_re_review_since timestamptz null,
    add column needs_re_review_reason text null,
    add constraint venue_bookings_needs_re_review_together
        check ((needs_re_review_since is null) = (needs_re_review_reason is null)),
    add constraint venue_bookings_needs_re_review_reason_length
        check (needs_re_review_reason is null or length(btrim(needs_re_review_reason)) between 1 and 1000);

comment on column public.venue_bookings.needs_re_review_since is
    'Story 37: when an approved change touched what venue staff approved (time or layout, CR-R5). Cleared when the coordinator sends it for re-review. Not ready while set.';
comment on column public.venue_bookings.needs_re_review_reason is
    'Story 37: what the change touched, such as "Date or time changed."';

-- Q14: a reserved line an approved time change leaves short is marked the same way,
-- keeping its reservation; the coordinator sends it to technical support.
alter table public.equipment_requests
    add column needs_re_review_since timestamptz null,
    add column needs_re_review_reason text null,
    add constraint equipment_requests_needs_re_review_together
        check ((needs_re_review_since is null) = (needs_re_review_reason is null)),
    add constraint equipment_requests_needs_re_review_reason_length
        check (needs_re_review_reason is null or length(btrim(needs_re_review_reason)) between 1 and 1000);

comment on column public.equipment_requests.needs_re_review_since is
    'Story 37: when an approved time change left this reserved line short. Cleared when the coordinator sends it for re-review. Not ready while set.';
comment on column public.equipment_requests.needs_re_review_reason is
    'Story 37: why, such as "Event time changed; 5 free for 8."';

-- The technical history names both steps: marked by the change, then sent to technical support.
alter table public.event_technical_history drop constraint event_technical_history_action_known;
alter table public.event_technical_history add constraint event_technical_history_action_known
    check (action = any (array['reserved', 'refused', 'not_available', 'note_updated', 'released', 're_review',
                               'exit_ticked', 'exit_unticked', 'exit_cleared', 'technical_status',
                               'needs_re_review', 'sent_for_re_review']));

-- Q19: a booking moved by an approved change records both windows.
alter table public.venue_booking_history
    add column old_period tstzrange null,
    add column new_period tstzrange null;

-- The organiser alone hears of a decision on their request.
insert into public.notification_types (type, recipient_roles) values
    ('event_change_approved', '{event_organiser}'),
    ('event_change_rejected', '{event_organiser}');

-- ---------------------------------------------------------------------------
-- approve_event_change
-- ---------------------------------------------------------------------------

create or replace function public.approve_event_change(
    p_event_id uuid,
    p_actor_id uuid,
    p_expected_version integer,
    p_from_statuses text[],
    p_event_values jsonb,
    p_space_values jsonb,
    p_organiser_message text,
    p_history_reason text default null,
    p_officer_message text default null,
    p_attendee_message text default null,
    p_bookings jsonb default '[]'
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_after public.events;
    v_space_id text;
    v_values jsonb;
    v_significant boolean;
    v_plan jsonb;
    v_booking public.venue_bookings;
    v_new tstzrange;
    v_clash record;
begin
    select * into v_event from public.events where id = p_event_id for update;
    if not found or v_event.status = 'draft' then
        return jsonb_build_object('outcome', 'not_found');
    end if;
    if v_event.coordinator_id is distinct from p_actor_id then
        return jsonb_build_object('outcome', 'not_assigned');
    end if;
    if not (v_event.status::text = any (p_from_statuses)) then
        return jsonb_build_object('outcome', 'status_changed');
    end if;
    if v_event.starts_at is null or v_event.starts_at <= now() then
        return jsonb_build_object('outcome', 'started');
    end if;
    -- The API checked each `before` against this version (Q8); anything newer is unreviewed.
    if v_event.version is distinct from p_expected_version then
        return jsonb_build_object('outcome', 'stale');
    end if;

    update public.event_change_requests
       set status = 'approved', decided_by = p_actor_id, decided_at = now()
     where event_id = p_event_id and kind = 'change' and status = 'open'
    returning significant into v_significant;
    if not found then
        return jsonb_build_object('outcome', 'no_open_request');
    end if;

    -- Only the fields the request changes are in p_event_values; the rest keep their values.
    update public.events e
       set name = r.name, event_timezone = r.event_timezone, purpose = r.purpose,
           description = r.description, starts_at = r.starts_at, ends_at = r.ends_at,
           expected_attendance = r.expected_attendance, layout_preference = r.layout_preference,
           facilities_required = r.facilities_required, accessibility_needs = r.accessibility_needs,
           preliminary_equipment_needs = r.preliminary_equipment_needs,
           registration_enabled = r.registration_enabled, registration_capacity = r.registration_capacity,
           registration_opens_at = r.registration_opens_at, registration_closes_at = r.registration_closes_at,
           re_registration_allowed = r.re_registration_allowed, waitlist_enabled = r.waitlist_enabled,
           version = e.version + 1
      from jsonb_populate_record(v_event, p_event_values) r
     where e.id = p_event_id
    returning e.* into v_after;

    for v_space_id, v_values in select key, value from jsonb_each(p_space_values) loop
        update public.event_space_requests s
           set label = r.label, expected_pax = r.expected_pax, layout_preference = r.layout_preference,
               facilities_required = r.facilities_required, starts_at = r.starts_at, ends_at = r.ends_at,
               version = s.version + 1
          from public.event_space_requests current_space,
               lateral jsonb_populate_record(current_space, v_values) r
         where s.id = v_space_id::uuid and s.event_id = p_event_id and current_space.id = s.id;
    end loop;

    -- AC3, AC5: what the change does to each booking, as the API planned it. Every move
    -- is re-checked here under the booking's lock, against the occupied window with the
    -- booking's own setup and turnaround (SCRUM-21, VC-R9).
    perform public.expire_venue_holds(now());
    for v_plan in select value from jsonb_array_elements(p_bookings) loop
        select * into v_booking from public.venue_bookings
         where id = (v_plan->>'booking_id')::uuid and event_id = p_event_id
           for update;
        if not found or v_booking.status not in ('held', 'approved', 're_review') then
            continue;
        end if;

        if jsonb_typeof(v_plan->'period') = 'array' then
            v_new := tstzrange((v_plan->'period'->>0)::timestamptz, (v_plan->'period'->>1)::timestamptz, '[)');
            select c.kind, c.event_name, c.block_reason into v_clash
              from public.venue_conflicts(
                       tstzrange(lower(v_new) - make_interval(mins => v_booking.setup_minutes),
                                 upper(v_new) + make_interval(mins => v_booking.turnaround_minutes), '[)'),
                       v_booking.venue_id, v_booking.id) c
             order by c.kind = 'block' desc, lower(c.occupied_period)
             limit 1;
            if found then
                -- Q11, Q16: it keeps the old window and can't go to venue staff; the first flag wins.
                if v_booking.flag is null then
                    update public.venue_bookings
                       set flag = 'conflict', flagged_at = now(),
                           flag_reason = case when v_clash.kind = 'block'
                               then format('The new time clashes with a venue block (%s).',
                                           private.venue_block_reason_label(v_clash.block_reason::public.venue_block_reason))
                               else format('The new time clashes with "%s".', v_clash.event_name) end
                     where id = v_booking.id;
                end if;
                continue;
            end if;
            update public.venue_bookings set booked_period = v_new where id = v_booking.id;
            insert into public.venue_booking_history (booking_id, actor_id, action, from_status, to_status,
                                                      old_period, new_period)
            values (v_booking.id, p_actor_id, 'moved_by_change', v_booking.status, v_booking.status,
                    v_booking.booked_period, v_new);
        end if;

        -- Only what venue staff approved needs them again; a hold is still theirs to decide (Q15).
        if v_plan->>'mark' is not null and v_booking.status = 'approved' then
            update public.venue_bookings
               set needs_re_review_since = now(), needs_re_review_reason = v_plan->>'mark'
             where id = v_booking.id;
        end if;
        if v_plan->>'unsuitable' is not null and v_booking.flag is null then
            update public.venue_bookings
               set flag = 'unsuitable', flag_reason = v_plan->>'unsuitable', flagged_at = now()
             where id = v_booking.id;
        end if;
        -- Q17: only an Unsuitable flag an approved change set is cleared by one.
        if (v_plan->>'clear_unsuitable')::boolean is true and v_booking.flag = 'unsuitable'
           and v_booking.flag_reason like 'After an approved change: %' then
            update public.venue_bookings
               set flag = null, flag_reason = null, flagged_at = null
             where id = v_booking.id;
        end if;
    end loop;

    -- Q14, RS-R5: a new time moves every reservation; a line the new time leaves short is
    -- marked. The coordinator is the actor, so the re-check's notice skips them (NT-R1).
    if (v_after.starts_at, v_after.ends_at) is distinct from (v_event.starts_at, v_event.ends_at) then
        perform public.recheck_event_reservations(p_event_id, p_actor_id);
    end if;

    -- AC7, QA3-16: a significant change must pass the safety check again, so a Confirmed
    -- or Preparation event goes back to Planning, and so does one in Safety review,
    -- which is being checked against details that no longer hold (Q6).
    if v_significant and v_event.status in ('confirmed', 'preparation', 'safety_review') then
        select * into v_after from public.transition_event(p_event_id, p_actor_id,
            array[v_event.status::text], 'planning', v_after.version, p_history_reason, null, null);
        if v_event.status = 'safety_review' then
            insert into public.event_safety_decisions (event_id, decision, reason_code, decided_by)
            values (p_event_id, 'withdrawn', 'approved_details_changed', null);
            insert into public.notifications (recipient_id, recipient_role, event_id, type, message)
            select distinct ur.profile_id, 'safety_officer'::public.user_role, p_event_id,
                   'event_returned_to_planning', p_officer_message
              from public.user_roles ur
             where ur.role = 'safety_officer' and ur.profile_id is distinct from p_actor_id;
        end if;
    end if;

    perform public.add_notification(v_event.organiser_id, p_event_id,
        'event_change_approved', p_organiser_message, p_actor_id);
    -- RG-R4, Q9: the API sends a message only when the date or time changed.
    if p_attendee_message is not null then
        perform public.notify_registered_attendees(p_event_id, 'attendee_event_changed',
            p_attendee_message, p_actor_id);
    end if;

    return jsonb_build_object('outcome', 'ok', 'event', to_jsonb(v_after));
end;
$$;

comment on function public.approve_event_change is
    'Story 37 AC2: approves the open change request on an event the actor coordinates, in one of p_from_statuses, not yet started and still at p_expected_version. Applies p_event_values (only the changed event fields) and p_space_values ({space_id: changed fields}) in one transaction, bumps the versions, closes the request as approved and notifies the organiser. Answers {outcome: ok|not_found|not_assigned|status_changed|started|stale|no_open_request, event}. API-only.';

revoke execute on function public.approve_event_change(uuid, uuid, integer, text[], jsonb, jsonb, text, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.approve_event_change(uuid, uuid, integer, text[], jsonb, jsonb, text, text, text, text, jsonb)
    to service_role;

-- ---------------------------------------------------------------------------
-- reject_event_change
-- ---------------------------------------------------------------------------

create or replace function public.reject_event_change(
    p_event_id uuid,
    p_actor_id uuid,
    p_reason text,
    p_from_statuses text[],
    p_organiser_message text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
begin
    -- The lock request_event_change takes, so a decision and a new request can't interleave.
    select * into v_event from public.events where id = p_event_id for update;
    if not found or v_event.status = 'draft' then
        return jsonb_build_object('outcome', 'not_found');
    end if;
    if v_event.coordinator_id is distinct from p_actor_id then
        return jsonb_build_object('outcome', 'not_assigned');
    end if;
    if not (v_event.status::text = any (p_from_statuses)) then
        return jsonb_build_object('outcome', 'status_changed');
    end if;
    -- A submitted event always has a start; a missing one is refused, as CR-R10.
    if v_event.starts_at is null or v_event.starts_at <= now() then
        return jsonb_build_object('outcome', 'started');
    end if;

    update public.event_change_requests
       set status = 'rejected', decided_by = p_actor_id, decided_at = now(),
           decision_reason = btrim(p_reason)
     where event_id = p_event_id and kind = 'change' and status = 'open';
    if not found then
        return jsonb_build_object('outcome', 'no_open_request');
    end if;

    perform public.add_notification(v_event.organiser_id, p_event_id,
        'event_change_rejected', p_organiser_message, p_actor_id);

    return jsonb_build_object('outcome', 'ok');
end;
$$;

comment on function public.reject_event_change is
    'Story 37 AC2: closes the open change request on an event the actor coordinates, in one of p_from_statuses and not yet started, as rejected with the reason, and notifies the organiser. The event keeps its details, status and arrangements. Answers {outcome: ok|not_found|not_assigned|status_changed|started|no_open_request}. API-only.';

revoke execute on function public.reject_event_change(uuid, uuid, text, text[], text)
    from public, anon, authenticated;
grant execute on function public.reject_event_change(uuid, uuid, text, text[], text)
    to service_role;

-- ---------------------------------------------------------------------------
-- Q16, Q17: a booking an approved change flagged Conflict or Unsuitable can be
-- replaced through CR-95's path, like an Affected or Safety-rejected one. The
-- replacement may sit beside it in the space until it is approved, which releases
-- the original (release_replaced_booking). Both request functions are as live
-- (20261020150000), with the two flags added to the replaceable ones.
-- ---------------------------------------------------------------------------

drop index public.venue_bookings_one_active_per_space;
create unique index venue_bookings_one_active_per_space
    on public.venue_bookings (event_space_request_id)
    where status in ('held', 'approved', 're_review')
      and (flag is null or flag not in ('affected', 'safety_rejected', 'conflict', 'unsuitable'));

CREATE OR REPLACE FUNCTION public.request_venue_booking(p_event_id uuid, p_venue_id uuid, p_actor_id uuid, p_note text, p_notify_message text, p_replaces_booking_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(outcome text, booking_id uuid, conflict jsonb)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_replaced public.venue_bookings;
    v_event public.events;
    v_booking_id uuid;
    v_venue_active boolean;
    v_occupied tstzrange;
    v_booked tstzrange;
    v_setup integer;
    v_turnaround integer;
    v_conflict jsonb;
begin
    -- Lock the event so a concurrent status change can't slip between the
    -- checks and the insert.
    select * into v_event from public.events where id = p_event_id for update;
    if not found then
        return query select 'event_not_found'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- BR-R6 (QA-22): planning only. A returned event is still having its
    -- requirements amended, which gets its own message.
    if v_event.status = 'returned' then
        return query select 'returned'::text, null::uuid, null::jsonb;
        return;
    end if;
    if v_event.status <> 'planning' then
        return query select 'not_planning'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- The API already checked this; re-checked under the lock in case the
    -- event was reassigned in between.
    if v_event.coordinator_id is distinct from p_actor_id then
        return query select 'not_assigned'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- Submission requires both times, so a planning event should always have
    -- them; without them the range below would be unbounded and overlap
    -- everything.
    if v_event.starts_at is null or v_event.ends_at is null then
        return query select 'no_period'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- SCRUM-64: a shared lock on the venue serialises this request against
    -- deactivate_venue's update lock, so there is never an unflagged hold at
    -- an inactive venue.
    select v.is_active, v.setup_minutes, v.turnaround_minutes
      into v_venue_active, v_setup, v_turnaround
      from public.venues v where v.id = p_venue_id for share;
    if not found then
        return query select 'venue_not_found'::text, null::uuid, null::jsonb;
        return;
    end if;
    if not v_venue_active then
        return query select 'venue_inactive'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- CR-95 AC4: a replacement names the event's own affected, Safety-rejected, conflicting or
    -- unsuitable (story 37) booking, which is
    -- still live; the lock stops it being released or restored under us.
    if p_replaces_booking_id is not null then
        select * into v_replaced from public.venue_bookings vb where vb.id = p_replaces_booking_id for update;
        if not found
           or v_replaced.event_id <> v_event.id
           or (v_replaced.flag is null or v_replaced.flag not in ('affected','safety_rejected','conflict','unsuitable'))
           or v_replaced.status not in ('held', 'approved') then
            return query select 'replaced_booking_invalid'::text, null::uuid, null::jsonb;
            return;
        end if;
    end if;

    -- BR-R1: one venue per event. Checked before the insert because
    -- re-requesting the venue the event already holds would otherwise read as
    -- another event's hold. The event lock serialises requests for the same
    -- event; the unique index is the backstop.
    if exists (
        select 1
        from public.venue_bookings vb
        where vb.event_id = p_event_id
          and vb.status in ('held', 'approved', 're_review')
          and (p_replaces_booking_id is null or vb.id <> p_replaces_booking_id)
    ) then
        return query select 'already_booked'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- CR-99 AC5: expire overdue holds first, so DB-1 no longer counts them.
    perform public.expire_venue_holds(now());

    -- CR-100: snapshot defaults under the venue lock, before checking clashes.
    v_booked := tstzrange(v_event.starts_at, v_event.ends_at, '[)');
    v_occupied := tstzrange(v_event.starts_at - make_interval(mins => v_setup),
                           v_event.ends_at + make_interval(mins => v_turnaround), '[)');
    v_conflict := private.first_venue_conflict(v_occupied, p_venue_id);
    if v_conflict is not null then
        return query select
            case when v_conflict ->> 'kind' = 'block' then 'blocked' else 'held_by_other' end,
            null::uuid, v_conflict;
        return;
    end if;

    -- DB-1 (venue_bookings_no_overlap) is the authority on overlaps, so two
    -- coordinators racing for the same slot resolve first-come-first-served
    -- (QA2-23): the loser's insert waits on the winner's and then violates it.
    begin
        insert into public.venue_bookings (event_id, venue_id, booked_period, setup_minutes, turnaround_minutes, status, request_note, requested_by, replaces_booking_id)
        values (p_event_id, p_venue_id, v_booked, v_setup, v_turnaround, 'held', nullif(btrim(p_note), ''), p_actor_id, p_replaces_booking_id)
        returning id into v_booking_id;
    exception
        -- Two truly simultaneous overlapping inserts can each wait on the
        -- other; Postgres then aborts one with a deadlock. Either way this
        -- request lost; the winner is named if it is visible by now.
        when exclusion_violation or deadlock_detected then
            return query select 'held_by_other'::text, null::uuid,
                private.first_venue_conflict(v_occupied, p_venue_id);
            return;
        when unique_violation then
            return query select 'already_booked'::text, null::uuid, null::jsonb;
            return;
    end;

    -- Venue staff work as a pool (AUTH-R5), so every holder of the role is
    -- told, in this transaction (NT-R3). Never the actor (NT-R1).
    insert into public.notifications (recipient_id, event_id, type, message)
    select ur.profile_id, p_event_id, 'venue_booking_requested', p_notify_message
    from public.user_roles ur
    where ur.role = 'venue_staff'
      and ur.profile_id <> p_actor_id;

    return query select 'ok'::text, v_booking_id, null::jsonb;
end;
$function$;

CREATE OR REPLACE FUNCTION public.request_venue_booking_for_space(p_event_space_request_id uuid, p_venue_id uuid, p_actor_id uuid, p_note text, p_notify_message text, p_replaces_booking_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(outcome text, booking_id uuid, conflict jsonb)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_replaced public.venue_bookings;
    v_space public.event_space_requests;
    v_event public.events;
    v_starts_at timestamptz;
    v_ends_at timestamptz;
    v_booking_id uuid;
    v_capacity integer;
    v_venue_active boolean;
    v_occupied tstzrange;
    v_booked tstzrange;
    v_setup integer;
    v_turnaround integer;
    v_conflict jsonb;
begin
    select es.* into v_space
    from public.event_space_requests es
    where es.id = p_event_space_request_id
    for update;
    if not found then
        return query select 'event_not_found'::text, null::uuid, null::jsonb;
        return;
    end if;

    select e.* into v_event
    from public.events e
    where e.id = v_space.event_id
    for update;
    if not found then
        return query select 'event_not_found'::text, null::uuid, null::jsonb;
        return;
    end if;

    if v_event.status = 'returned' then
        return query select 'returned'::text, null::uuid, null::jsonb;
        return;
    end if;
    if v_event.status <> 'planning' then
        return query select 'not_planning'::text, null::uuid, null::jsonb;
        return;
    end if;
    if v_event.coordinator_id is distinct from p_actor_id then
        return query select 'not_assigned'::text, null::uuid, null::jsonb;
        return;
    end if;
    v_starts_at := coalesce(v_space.starts_at, v_event.starts_at);
    v_ends_at := coalesce(v_space.ends_at, v_event.ends_at);
    if v_starts_at is null or v_ends_at is null then
        return query select 'no_period'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- D33 / SCRUM-64 AC2: the same shared lock and refusal as the event path,
    -- so a request can't race a deactivation into an unflagged hold.
    select v.is_active, v.setup_minutes, v.turnaround_minutes
      into v_venue_active, v_setup, v_turnaround
      from public.venues v where v.id = p_venue_id for share;
    if not found then
        return query select 'venue_not_found'::text, null::uuid, null::jsonb;
        return;
    end if;
    if not v_venue_active then
        return query select 'venue_inactive'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- CR-95 AC4: a replacement names the event's own affected, Safety-rejected, conflicting or
    -- unsuitable (story 37) booking, which is
    -- still live; the lock stops it being released or restored under us.
    if p_replaces_booking_id is not null then
        select * into v_replaced from public.venue_bookings vb where vb.id = p_replaces_booking_id for update;
        if not found
           or v_replaced.event_id <> v_event.id
           or v_replaced.event_space_request_id is distinct from p_event_space_request_id
           or (v_replaced.flag is null or v_replaced.flag not in ('affected','safety_rejected','conflict','unsuitable'))
           or v_replaced.status not in ('held', 'approved') then
            return query select 'replaced_booking_invalid'::text, null::uuid, null::jsonb;
            return;
        end if;
    end if;

    -- CR-97 AC10: the venue must seat the space's expected pax. The venue's
    -- figure for the space's layout wins when it has one (venue search's
    -- effective capacity); a space with no expected pax is not checked.
    if v_space.expected_pax is not null then
        select coalesce(
            (select l.capacity_for_layout from public.venue_layouts l
             where l.venue_id = p_venue_id and l.layout = v_space.layout_preference),
            v.capacity
        ) into v_capacity
        from public.venues v
        where v.id = p_venue_id;
        if v_capacity is not null and v_space.expected_pax > v_capacity then
            return query select 'over_capacity'::text, null::uuid, null::jsonb;
            return;
        end if;
    end if;

    perform public.expire_venue_holds(now());

    if exists (
        select 1 from public.venue_bookings vb
        where vb.event_space_request_id = p_event_space_request_id
          and vb.status in ('held', 'approved', 're_review')
          and (p_replaces_booking_id is null or vb.id <> p_replaces_booking_id)
    ) then
        return query select 'already_booked'::text, null::uuid, null::jsonb;
        return;
    end if;

    -- CR-100: each space keeps its own window and a snapshot of venue defaults.
    v_booked := tstzrange(v_starts_at, v_ends_at, '[)');
    v_occupied := tstzrange(v_starts_at - make_interval(mins => v_setup),
                           v_ends_at + make_interval(mins => v_turnaround), '[)');
    v_conflict := private.first_venue_conflict(v_occupied, p_venue_id);
    if v_conflict is not null then
        return query select
            case when v_conflict ->> 'kind' = 'block' then 'blocked' else 'held_by_other' end,
            null::uuid, v_conflict;
        return;
    end if;

    begin
        insert into public.venue_bookings (
            event_id, event_space_request_id, venue_id, booked_period, setup_minutes, turnaround_minutes,
            status, request_note, requested_by, replaces_booking_id
        )
        values (
            v_event.id, p_event_space_request_id, p_venue_id, v_booked, v_setup, v_turnaround,
            'held', nullif(btrim(p_note), ''), p_actor_id, p_replaces_booking_id
        )
        returning id into v_booking_id;
    exception
        when exclusion_violation or deadlock_detected then
            return query select 'held_by_other'::text, null::uuid,
                private.first_venue_conflict(v_occupied, p_venue_id);
            return;
        when unique_violation then
            return query select 'already_booked'::text, null::uuid, null::jsonb;
            return;
    end;

    insert into public.notifications (recipient_id, event_id, type, message)
    select ur.profile_id, v_event.id, 'venue_booking_requested', p_notify_message
    from public.user_roles ur
    where ur.role = 'venue_staff'
      and ur.profile_id <> p_actor_id;

    return query select 'ok'::text, v_booking_id, null::jsonb;
end;
$function$;

-- ---------------------------------------------------------------------------
-- Equipment after an approved time change (Q14, RS-R5). As SCRUM-24 built it
-- (20261019120000), except that a reserved line the new time leaves short is
-- marked Needs re-review rather than sent straight to technical support: the
-- coordinator sends it (AC6). A marked line is not Ready.
-- ---------------------------------------------------------------------------

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
    v_reason text;
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
            v_reason := 'Event time changed; ' || coalesce(v_free, 0) || ' free for ' || v_line.quantity || '.';
            update public.equipment_requests
               set needs_re_review_since = now(), needs_re_review_reason = v_reason
             where id = v_line.id;
            perform private.log_technical(p_event_id, v_line.id, 'needs_re_review', 'reserved', 'reserved', v_reason);
            perform private.notify_coordinator(p_event_id, 'equipment_re_review',
                'Equipment needs re-review after a time change: ' || private.line_label(v_line)
                || ' for "' || v_event.name || '". Send it to technical support; the reservation is kept until they decide.');
            v_flagged := v_flagged + 1;
        end if;
    end loop;

    return query select 'ok', v_flagged,
        v_event.technical_readiness = 'ready' and (select technical_readiness from public.events where id = p_event_id) <> 'ready';
end;
$$;

-- A marked line is not Ready, whatever its status.
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
                          where r.event_id = p_event_id
                            and (r.status not in ('reserved', 'released') or r.needs_re_review_since is not null))
             and exists (select 1 from public.events e
                          where e.id = p_event_id and e.exit_confirmed_at is not null)
            then 'ready'
        else 'pending'
    end;
$$;

-- Marking or sending a line moves technical status, so the refresh trigger watches the marker too.
drop trigger equipment_requests_refresh_technical_status on public.equipment_requests;
create trigger equipment_requests_refresh_technical_status
    after insert or delete or update of equipment_id, quantity, status, needs_re_review_since
    on public.equipment_requests
    for each row execute function private.equipment_request_changed();

