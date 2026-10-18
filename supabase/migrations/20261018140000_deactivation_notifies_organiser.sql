-- =============================================================================
-- ConnectSphere - SCRUM-64 AC3: notify organisers when a venue is deactivated
--
-- AC3 (updated 17/10), CAL-R5 and QA3-7 require the organiser to hear that
-- their venue arrangement is affected and what happens next (D40). Notify
-- once per newly flagged event, excluding the actor; attendees are not told.
-- Keep this notice in the deactivation caller so CR-94 edits are unchanged.
-- =============================================================================

create or replace function public.deactivate_venue(
    p_venue_id uuid,
    p_actor_id uuid,
    p_expected_version integer,
    p_reason public.venue_inactive_reason,
    p_note text,
    p_before jsonb,
    p_after jsonb,
    p_flag_reason text,
    p_message text
) returns table (outcome text, event_ids uuid[])
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_venue public.venues;
    v_events uuid[];
begin
    select * into v_venue from public.venues where id = p_venue_id for update;
    if not found then
        return query select 'venue_not_found'::text, '{}'::uuid[];
        return;
    end if;
    if not v_venue.is_active then
        return query select 'already_inactive'::text, '{}'::uuid[];
        return;
    end if;
    if v_venue.version <> p_expected_version then
        return query select 'stale'::text, '{}'::uuid[];
        return;
    end if;

    update public.venues
       set is_active = false,
           inactive_reason = p_reason,
           inactive_note = nullif(btrim(p_note), ''),
           updated_by = p_actor_id,
           version = version + 1
     where id = p_venue_id;

    insert into public.venue_edit_history (venue_id, actor_id, before, after)
    values (p_venue_id, p_actor_id, p_before, p_after);

    select coalesce(array_agg(f), '{}') into v_events
      from public.flag_venue_bookings(p_venue_id, tstzrange(now(), null), 'affected', p_flag_reason, p_message) f;

    insert into public.notifications (recipient_id, event_id, type, message)
    select e.organiser_id, e.id, 'venue_unavailable_organiser',
           'The venue "' || v_venue.name || '" has been deactivated. Your event is not cancelled: your coordinator will arrange an alternative venue and update you.'
      from public.events e
     where e.id = any (v_events)
       and e.organiser_id is not null
       and e.organiser_id is distinct from p_actor_id;

    return query select 'ok'::text, v_events;
end;
$$;

comment on function public.deactivate_venue(uuid, uuid, integer, public.venue_inactive_reason, text, jsonb, jsonb, text, text) is
    'SCRUM-64: marks the venue inactive with its reason, records the history row and flags its future held/approved bookings affected and notifies each affected event''s organiser once, excluding the actor (CAL-R5, QA3-7), in one transaction. Outcomes: ok, venue_not_found, already_inactive, stale. API-only.';

revoke execute on function public.deactivate_venue(uuid, uuid, integer, public.venue_inactive_reason, text, jsonb, jsonb, text, text) from public, anon, authenticated;
grant execute on function public.deactivate_venue(uuid, uuid, integer, public.venue_inactive_reason, text, jsonb, jsonb, text, text) to service_role;
