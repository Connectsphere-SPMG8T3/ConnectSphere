-- Fix SCRUM-109 RPC return projection: the output column named updated_at
-- otherwise makes the table reference ambiguous in PL/pgSQL.
create or replace function public.set_venue_preparation(
    p_booking_id uuid,
    p_actor_id uuid,
    p_stage text,
    p_note text
)
returns table(outcome text, stage text, note text, updated_at timestamptz, event_status text)
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
        return query select 'booking_not_found', null::text, null::text, null::timestamptz, null::text;
        return;
    end if;

    select * into v_event
    from public.events
    where id = v_booking.event_id
    for update;
    if not found or v_event.status = 'draft' then
        return query select 'event_not_found', null::text, null::text, null::timestamptz, null::text;
        return;
    end if;

    if v_event.status not in ('confirmed', 'preparation') then
        return query select 'not_confirmed', null::text, null::text, null::timestamptz, v_event.status::text;
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
    select 'ok', v_stage::text, v_note, coalesce(
        (select evp.updated_at from public.event_venue_preparation as evp where evp.booking_id = p_booking_id),
        v_current.updated_at
    ), (select e.status::text from public.events as e where e.id = v_event.id);
end;
$$;

comment on function public.set_venue_preparation(uuid, uuid, text, text) is
    'SCRUM-109 AC1-AC3: records one venue booking preparation update, starts Preparation on the first changed update from Confirmed, and keeps progress locked while the event is in Planning.';

revoke execute on function public.set_venue_preparation(uuid, uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.set_venue_preparation(uuid, uuid, text, text)
    to service_role;
