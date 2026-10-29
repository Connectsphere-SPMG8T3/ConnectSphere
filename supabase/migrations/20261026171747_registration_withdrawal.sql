alter table public.events
    add column withdrawal_closes_at timestamptz null,
    add constraint events_withdrawal_cutoff_before_start check (
        withdrawal_closes_at is null
        or (starts_at is not null and withdrawal_closes_at <= starts_at)
    );

comment on column public.events.withdrawal_closes_at is
    'SCRUM-55: the organiser-configured attendee withdrawal cutoff; null means the event start time.';

create function public.withdraw_registration(p_event_id uuid, p_attendee_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events%rowtype;
    v_registration public.event_registrations%rowtype;
    v_now timestamptz;
begin
    select * into v_event
    from public.events
    where id = p_event_id
    for update;

    if not found or v_event.status not in ('confirmed', 'preparation') then
        return jsonb_build_object('outcome', 'unavailable');
    end if;

    select * into v_registration
    from public.event_registrations
    where event_id = p_event_id and attendee_id = p_attendee_id
    order by registered_at desc
    limit 1
    for update;

    if not found then
        return jsonb_build_object('outcome', 'not_registered');
    end if;
    if v_registration.status = 'withdrawn' then
        return jsonb_build_object('outcome', 'already_withdrawn');
    end if;
    if v_registration.status <> 'registered' then
        return jsonb_build_object('outcome', 'not_registered');
    end if;

    -- Evaluate after the locks so a request waiting across the deadline cannot succeed.
    v_now := clock_timestamp();
    if v_event.starts_at is null or v_now >= v_event.starts_at then
        return jsonb_build_object('outcome', 'event_started');
    end if;
    if v_now >= coalesce(v_event.withdrawal_closes_at, v_event.starts_at) then
        return jsonb_build_object('outcome', 'cutoff_passed');
    end if;

    update public.event_registrations
    set status = 'withdrawn', withdrawn_at = v_now
    where id = v_registration.id
    returning * into v_registration;

    return jsonb_build_object(
        'outcome', 'withdrawn',
        'registration_id', v_registration.id,
        'withdrawn_at', v_registration.withdrawn_at
    );
end;
$$;

revoke all on function public.withdraw_registration(uuid, uuid) from public, anon, authenticated;
grant execute on function public.withdraw_registration(uuid, uuid) to service_role;

comment on function public.withdraw_registration(uuid, uuid) is
    'SCRUM-55: withdraws a current attendee registration before the configured cutoff under the same event-row lock used by registration, so a place is released once.';
