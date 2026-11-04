-- =============================================================================
-- ConnectSphere - CR-109: cast the updater's name in set_venue_preparation
--
-- 20261103190000 returned `profiles.full_name` (varchar(150)) in a `text`
-- column, so every successful update raised "structure of query does not match
-- function result type". Found by supabase/verification/venue_preparation_checks.sql
-- against the live project. Same signature and return columns, so replaced in place.
-- =============================================================================

create or replace function public.set_venue_preparation(
    p_booking_id uuid,
    p_actor_id uuid,
    p_stage text,
    p_note text
)
returns table(
    outcome text,
    stage text,
    note text,
    updated_at timestamptz,
    updated_by_name text,
    event_status text
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_booking public.venue_bookings;
    v_event public.events;
    v_current public.event_venue_preparation;
    v_stage public.preparation_stage := p_stage::public.preparation_stage;
    v_note text := nullif(btrim(p_note), '');
    v_old_stage public.preparation_stage;
    v_changed boolean := false;
begin
    perform private.set_actor(p_actor_id);

    select * into v_booking
    from public.venue_bookings
    where id = p_booking_id
    for update;
    if not found then
        return query select 'booking_not_found', null::text, null::text, null::timestamptz, null::text, null::text;
        return;
    end if;

    select * into v_event
    from public.events
    where id = v_booking.event_id
    for update;
    if not found or v_event.status = 'draft' then
        return query select 'event_not_found', null::text, null::text, null::timestamptz, null::text, null::text;
        return;
    end if;

    if v_event.status not in ('confirmed', 'preparation') then
        return query select 'not_confirmed', null::text, null::text, null::timestamptz, null::text, v_event.status::text;
        return;
    end if;

    if v_booking.status <> 'approved' then
        return query select 'booking_not_active', null::text, null::text, null::timestamptz, null::text, v_event.status::text;
        return;
    end if;

    select * into v_current
    from public.event_venue_preparation
    where booking_id = p_booking_id;

    v_old_stage := coalesce(v_current.stage, 'not_started');
    if v_stage is distinct from v_old_stage then
        insert into public.venue_booking_history (
            booking_id, actor_id, action, old_preparation_stage, new_preparation_stage
        )
        values (p_booking_id, p_actor_id, 'preparation', v_old_stage::text, v_stage::text);
        v_changed := true;
    end if;
    if v_note is distinct from v_current.note then
        insert into public.venue_booking_history (
            booking_id, actor_id, action, old_preparation_stage, new_preparation_stage
        )
        values (p_booking_id, p_actor_id, 'preparation_note_updated', null, null);
        v_changed := true;
    end if;

    if v_changed then
        insert into public.event_venue_preparation (booking_id, stage, note, updated_by, updated_at)
        values (p_booking_id, v_stage, v_note, p_actor_id, now())
        on conflict (booking_id) do update
            set stage = excluded.stage, note = excluded.note,
                updated_by = excluded.updated_by, updated_at = excluded.updated_at;
        perform private.start_preparation(v_event.id, p_actor_id);
    end if;

    return query
    select 'ok', v_stage::text, v_note, evp.updated_at, p.full_name::text,
        (select e.status::text from public.events as e where e.id = v_event.id)
    from (select 1) as one
    left join public.event_venue_preparation as evp on evp.booking_id = p_booking_id
    left join public.profiles as p on p.id = evp.updated_by;
end;
$$;

comment on function public.set_venue_preparation(uuid, uuid, text, text) is
    'CR-109 AC1-AC3: records one approved venue booking''s preparation update, starts Preparation on the first changed update from Confirmed, keeps progress locked while the event is in Planning, and names who the recorded progress is by.';

revoke execute on function public.set_venue_preparation(uuid, uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.set_venue_preparation(uuid, uuid, text, text)
    to service_role;
