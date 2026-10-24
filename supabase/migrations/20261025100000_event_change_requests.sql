-- =============================================================================
-- ConnectSphere - Story 32 request changes to event arrangements
--
-- A change request is a row of story 84's event_change_requests with
-- kind = 'change', carrying the proposed changes as {event: [{field, before,
-- after}], spaces: [{space_id, label, fields}]} and whether any of them is
-- significant (REQUIREMENTS 6.7, 6.19 CR-R16/CR-R17). Story 37 decides it.
--
-- CR-R14 [Team decision, extending CR-R1]: at most one open request per event.
-- request_event_change refuses while a cancellation request is open, under the
-- same event lock request_event_cancellation takes, and the per-kind unique
-- index becomes one open request per event as a backstop. Story 84's
-- supersede still works: it closes the change row before inserting the
-- cancellation, in one transaction.
--
-- CR-R18 [Team decision]: an event that becomes rejected, cancelled or
-- completed closes its open change request as superseded, whatever moved it.
-- API-only (ADR-0006); nothing here changes the event itself.
-- =============================================================================

alter table public.event_change_requests
    add column changes jsonb null,
    add column significant boolean null,
    -- A change request says what changes; a cancellation request has nothing to say.
    add constraint event_change_requests_changes_only_on_change
        check ((kind = 'change') = (changes is not null and significant is not null));

comment on column public.event_change_requests.changes is
    'Story 32: the proposed changes, {event: [{field, before, after}], spaces: [{space_id, label, fields}]}. before is read from the database by the API. Null on cancellation requests.';
comment on column public.event_change_requests.significant is
    'Story 32: whether any proposed change is significant (REQUIREMENTS 6.7). Null on cancellation requests.';

drop index public.event_change_requests_one_open_per_kind;
create unique index event_change_requests_one_open_per_event
    on public.event_change_requests (event_id)
    where status = 'open';

-- The coordinator when one is assigned; each Lead while the event is unassigned.
insert into public.notification_types (type, recipient_roles) values
    ('event_change_requested', '{event_coordinator,event_coordinator_lead}');

create or replace function public.request_event_change(
    p_event_id uuid,
    p_actor_id uuid,
    p_reason text,
    p_changes jsonb,
    p_significant boolean,
    p_from_statuses text[],
    p_expected_version integer,
    p_coordinator_message text,
    p_lead_message text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_request public.event_change_requests;
    v_lead uuid;
begin
    -- The same lock request_event_cancellation takes, so the two can't interleave.
    select * into v_event from public.events where id = p_event_id for update;
    if not found then
        return jsonb_build_object('outcome', 'not_found');
    end if;
    if v_event.organiser_id is distinct from p_actor_id then
        return jsonb_build_object('outcome', 'not_owner');
    end if;
    if not (v_event.status::text = any (p_from_statuses)) then
        return jsonb_build_object('outcome', 'status_changed');
    end if;
    -- The API computed `before` from this version; anything newer makes it wrong.
    if v_event.version is distinct from p_expected_version then
        return jsonb_build_object('outcome', 'stale');
    end if;
    if exists (select 1 from public.event_change_requests
                where event_id = p_event_id and kind = 'cancellation' and status = 'open') then
        return jsonb_build_object('outcome', 'cancellation_open');
    end if;
    if exists (select 1 from public.event_change_requests
                where event_id = p_event_id and kind = 'change' and status = 'open') then
        return jsonb_build_object('outcome', 'already_open');
    end if;

    insert into public.event_change_requests (event_id, kind, reason, requested_by, changes, significant)
    values (p_event_id, 'change', btrim(p_reason), p_actor_id, p_changes, p_significant)
    returning * into v_request;

    if v_event.coordinator_id is not null then
        perform public.add_notification(v_event.coordinator_id, p_event_id,
            'event_change_requested', p_coordinator_message, p_actor_id);
    else
        for v_lead in
            select profile_id from public.user_roles where role = 'event_coordinator_lead'
        loop
            perform public.add_notification(v_lead, p_event_id,
                'event_change_requested', p_lead_message, p_actor_id);
        end loop;
    end if;

    return jsonb_build_object(
        'outcome', 'ok',
        'request', jsonb_build_object(
            'id', v_request.id,
            'kind', v_request.kind,
            'status', v_request.status,
            'reason', v_request.reason,
            'changes', v_request.changes,
            'significant', v_request.significant,
            'requested_at', v_request.requested_at,
            'requested_by', (select jsonb_build_object('id', p.id, 'full_name', p.full_name)
                               from public.profiles p where p.id = v_request.requested_by)
        )
    );
end;
$$;

comment on function public.request_event_change is
    'Story 32: records the owner''s change request on an event in one of p_from_statuses at p_expected_version, unless a cancellation or change request is open (CR-R14), and notifies the assigned coordinator, or every Lead while unassigned. Answers {outcome: ok|not_found|not_owner|status_changed|stale|cancellation_open|already_open, request}. Changes nothing on the event. API-only.';

revoke execute on function public.request_event_change(uuid, uuid, text, jsonb, boolean, text[], integer, text, text)
    from public, anon, authenticated;
grant execute on function public.request_event_change(uuid, uuid, text, jsonb, boolean, text[], integer, text, text)
    to service_role;

-- CR-R18: a closed event's open change request is closed with it.
create or replace function private.close_change_request_on_closed_event()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.event_change_requests
       set status = 'superseded', decided_at = now(),
           decision_reason = format('Closed because the event was %s.', new.status)
     where event_id = new.id and kind = 'change' and status = 'open';
    return null;
end;
$$;

comment on function private.close_change_request_on_closed_event is
    'Story 32, CR-R18: trigger on events; when an event becomes rejected, cancelled or completed, its open change request is superseded. Trigger-only.';

revoke execute on function private.close_change_request_on_closed_event() from public, anon, authenticated;

create trigger events_close_change_request_when_closed
    after update of status on public.events
    for each row
    when (new.status is distinct from old.status
          and new.status in ('rejected', 'cancelled', 'completed'))
    execute function private.close_change_request_on_closed_event();
