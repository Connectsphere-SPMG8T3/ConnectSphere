-- CR-100: venue defaults and safety details. Existing bookings are untouched.
-- Keep the existing RPC signatures, locks, history, flags and service-only grants.
-- update_venue reads new fields from the full p_after snapshot; omitted keys
-- preserve their current values, for a backend deployed before this migration.
-- The API's edit form always sends all four, so omitting one there clears it.

alter table public.venues
    add column setup_minutes integer not null default 0,
    add column turnaround_minutes integer not null default 0,
    add column emergency_access text,
    add column restrictions text,
    add constraint venues_setup_not_negative check (setup_minutes >= 0),
    add constraint venues_turnaround_not_negative check (turnaround_minutes >= 0);

comment on column public.venues.setup_minutes is
    'Default setup for future booking requests (CR-100, VC-R9). Existing bookings keep their own value.';
comment on column public.venues.turnaround_minutes is
    'Default turnaround for future booking requests (CR-100, VC-R9). Non-negative; no business maximum.';
comment on column public.venues.emergency_access is
    'Emergency exits and evacuation routes, recorded by Venue Staff (CR-100). Null means not recorded.';
comment on column public.venues.restrictions is
    'Known venue restrictions, recorded by Venue Staff (CR-100). Null means not recorded.';

create or replace function public.update_venue(
    p_venue_id uuid,
    p_actor_id uuid,
    p_expected_version integer,
    p_name varchar,
    p_location varchar,
    p_capacity integer,
    p_opens_at time,
    p_closes_at time,
    p_description text,
    p_accessibility_features public.accessibility_feature[],
    p_layouts jsonb,
    p_facilities public.facility[],
    p_before jsonb,
    p_after jsonb,
    p_notifications jsonb default '[]'::jsonb,
    p_flags jsonb default '[]'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_after public.venues;
    v_notification jsonb;
    v_flag jsonb;
    v_period tstzrange;
    v_flagged uuid[];
    v_flagged_events uuid[] := '{}'::uuid[];
begin
    update public.venues
       set name = p_name,
           location = p_location,
           capacity = p_capacity,
           opens_at = p_opens_at,
           closes_at = p_closes_at,
           description = p_description,
           accessibility_features = p_accessibility_features,
           setup_minutes = case when p_after ? 'setup_minutes' then (p_after ->> 'setup_minutes')::integer else setup_minutes end,
           turnaround_minutes = case when p_after ? 'turnaround_minutes' then (p_after ->> 'turnaround_minutes')::integer else turnaround_minutes end,
           emergency_access = case when p_after ? 'emergency_access' then nullif(btrim(p_after ->> 'emergency_access'), '') else emergency_access end,
           restrictions = case when p_after ? 'restrictions' then nullif(btrim(p_after ->> 'restrictions'), '') else restrictions end,
           version = version + 1,
           updated_by = p_actor_id
     where id = p_venue_id
       and version = p_expected_version
    returning * into v_after;

    if not found then
        return null;
    end if;

    delete from public.venue_layouts where venue_id = p_venue_id;
    insert into public.venue_layouts (venue_id, layout, capacity_for_layout)
    select p_venue_id, (elem ->> 'layout')::public.venue_layout, (elem ->> 'capacity_for_layout')::integer
      from jsonb_array_elements(p_layouts) as elem;

    delete from public.venue_facilities where venue_id = p_venue_id;
    insert into public.venue_facilities (venue_id, facility)
    select p_venue_id, unnest(p_facilities)
     where p_facilities is not null and array_length(p_facilities, 1) > 0;

    insert into public.venue_edit_history (venue_id, actor_id, before, after)
    values (p_venue_id, p_actor_id, p_before, p_after);

    for v_notification in select * from jsonb_array_elements(p_notifications)
    loop
        insert into public.notifications (recipient_id, event_id, type, message)
        values (
            (v_notification ->> 'recipient_id')::uuid,
            (v_notification ->> 'event_id')::uuid,
            'venue_updated_affects_booking',
            v_notification ->> 'message'
        );
    end loop;

    -- CR-94: flag each Unsuitable booking, or tell its coordinator when it
    -- can't take the flag.
    for v_flag in select * from jsonb_array_elements(p_flags)
    loop
        v_flagged := '{}'::uuid[];
        select occupied_period into v_period
          from public.venue_bookings
         where id = (v_flag ->> 'booking_id')::uuid
           and venue_id = p_venue_id
         for update;

        if found then
            select coalesce(array_agg(f), '{}'::uuid[]) into v_flagged
              from public.flag_venue_bookings(
                  p_venue_id, v_period, 'unsuitable', v_flag ->> 'reason', v_flag ->> 'message'
              ) f;
        end if;

        if cardinality(v_flagged) > 0 then
            v_flagged_events := v_flagged_events || v_flagged;
        elsif v_flag ->> 'coordinator_id' is not null then
            insert into public.notifications (recipient_id, event_id, type, message)
            values (
                (v_flag ->> 'coordinator_id')::uuid,
                (v_flag ->> 'event_id')::uuid,
                'venue_updated_affects_booking',
                v_flag ->> 'unflagged_message'
            );
        end if;
    end loop;

    return jsonb_build_object(
        'venue_id', v_after.id,
        'flagged_event_ids', (select coalesce(jsonb_agg(distinct e), '[]'::jsonb) from unnest(v_flagged_events) e)
    );
end;
$$;

comment on function public.update_venue is
    'Atomically saves a venue edit: version-checked update, layouts/facilities replace, history row, notifications for any newly-affected booking (VC-R2, VC-R3), and the Unsuitable flags through flag_venue_bookings (CR-94). Returns {venue_id, flagged_event_ids}, or null when the version is stale. API-only.';

revoke execute on function public.update_venue(
    uuid, uuid, integer, varchar, varchar, integer, time, time, text,
    public.accessibility_feature[], jsonb, public.facility[], jsonb, jsonb, jsonb, jsonb
) from public, anon, authenticated;
grant execute on function public.update_venue(
    uuid, uuid, integer, varchar, varchar, integer, time, time, text,
    public.accessibility_feature[], jsonb, public.facility[], jsonb, jsonb, jsonb, jsonb
) to service_role;

create or replace function public.request_venue_booking(p_event_id uuid, p_venue_id uuid, p_actor_id uuid, p_note text, p_notify_message text, p_replaces_booking_id uuid default null)
 RETURNS TABLE(outcome text, booking_id uuid, conflict jsonb)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $$
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

    -- CR-95 AC4: a replacement names the event's own affected booking, which is
    -- still live; the lock stops it being released or restored under us.
    if p_replaces_booking_id is not null then
        select * into v_replaced from public.venue_bookings vb where vb.id = p_replaces_booking_id for update;
        if not found
           or v_replaced.event_id <> v_event.id
           or v_replaced.flag is distinct from 'affected'
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
$$;

create or replace function public.request_venue_booking_for_space(p_event_space_request_id uuid, p_venue_id uuid, p_actor_id uuid, p_note text, p_notify_message text, p_replaces_booking_id uuid default null)
 RETURNS TABLE(outcome text, booking_id uuid, conflict jsonb)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $$
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

    -- CR-95 AC4: a replacement names the event's own affected booking, which is
    -- still live; the lock stops it being released or restored under us.
    if p_replaces_booking_id is not null then
        select * into v_replaced from public.venue_bookings vb where vb.id = p_replaces_booking_id for update;
        if not found
           or v_replaced.event_id <> v_event.id
           or v_replaced.event_space_request_id is distinct from p_event_space_request_id
           or v_replaced.flag is distinct from 'affected'
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
$$;

comment on function public.request_venue_booking is
    'Holds a venue for a planning event (SCRUM-19). Refuses on the occupied window with the clash named in `conflict` (SCRUM-21), an inactive venue (SCRUM-64) and a second venue for the event. With p_replaces_booking_id it replaces that affected booking (CR-95 AC4). API-only.';
comment on function public.request_venue_booking_for_space is
    'Requests a venue for one event space using its effective period (CR-97). Refuses on the occupied window (SCRUM-21), an inactive venue (D33) and a venue that cannot seat the space''s expected pax. With p_replaces_booking_id it replaces that space''s affected booking (CR-95 AC4). API-only.';

revoke execute on function public.request_venue_booking(uuid, uuid, uuid, text, text, uuid)
    from public, anon, authenticated;
grant execute on function public.request_venue_booking(uuid, uuid, uuid, text, text, uuid)
    to service_role;
revoke execute on function public.request_venue_booking_for_space(uuid, uuid, uuid, text, text, uuid)
    from public, anon, authenticated;
grant execute on function public.request_venue_booking_for_space(uuid, uuid, uuid, text, text, uuid)
    to service_role;
