-- =============================================================================
-- ConnectSphere - CR-94 part 2: a venue edit flags the bookings it makes
-- Unsuitable (AC3, AC5)
--
-- update_venue (SCRUM-63) is recreated from its live definition, changed only
-- where marked CR-94. It takes p_flags, one entry per booking the API judged
-- Unsuitable, and flags each through SCRUM-64's flag_venue_bookings in the
-- same transaction as the save. The edit and its flags commit together:
-- flagging after the save could fail and never be retried, since saving the
-- same values again breaks nothing new.
--
-- flag_venue_bookings flags by venue and period. The booking's own period is
-- read here, under a row lock, and DB-1 (venue_bookings_no_overlap) allows no
-- other active booking at the venue to overlap it, so each call flags exactly
-- that booking. A booking that can't take the flag (already flagged, since the
-- first flag wins; in re-review; or no longer active) gets the entry's
-- unflagged_message instead, so its coordinator still hears about the edit.
--
-- The return type changes from setof venues to jsonb (null when the version
-- check fails), so the function is dropped and created rather than replaced.
-- =============================================================================

drop function public.update_venue(
    uuid, uuid, integer, varchar, varchar, integer, time, time, text,
    public.accessibility_feature[], jsonb, public.facility[], jsonb, jsonb, jsonb
);

create function public.update_venue(
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
