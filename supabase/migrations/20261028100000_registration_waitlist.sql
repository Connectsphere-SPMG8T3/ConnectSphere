-- SCRUM-86: FIFO waitlists, reserved invitations, acceptance and expiry.

create sequence public.event_waitlist_order_seq;

alter table public.event_registrations
    drop constraint event_registrations_status_check,
    add constraint event_registrations_status_check check (
        status in (
            'registered', 'withdrawn', 'cancelled', 'waitlisted', 'invited',
            'invitation_expired', 'left'
        )
    ),
    add column waitlist_order bigint null,
    add column invited_at timestamptz null,
    add column invitation_expires_at timestamptz null,
    add constraint event_registrations_waitlist_order_state check (
        (status = 'waitlisted') = (waitlist_order is not null)
    ),
    add constraint event_registrations_invitation_state check (
        (status = 'invited' and invited_at is not null and invitation_expires_at is not null)
        or (status <> 'invited' and invitation_expires_at is null)
    );

drop index public.event_registrations_active_attendee_idx;
create unique index event_registrations_active_attendee_idx
    on public.event_registrations (event_id, attendee_id)
    where status in ('registered', 'waitlisted', 'invited');
create index event_registrations_waitlist_fifo_idx
    on public.event_registrations (event_id, waitlist_order)
    where status = 'waitlisted';
create index event_registrations_invitation_expiry_idx
    on public.event_registrations (invitation_expires_at, event_id)
    where status = 'invited';

comment on column public.event_registrations.waitlist_order is
    'Monotonic enrollment order used to select the earliest attendee; not exposed as a queue position.';
comment on column public.event_registrations.invitation_expires_at is
    'An active invitation reserves one effective-capacity place until this instant (SCRUM-86, 24 hours after issue).';

insert into public.notification_types (type, recipient_roles)
values ('attendee_waitlist_invitation', '{attendee}')
on conflict (type) do update set recipient_roles = excluded.recipient_roles;

create function private.event_registration_capacity(p_event_id uuid)
returns integer
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    v_registration_capacity integer;
    v_primary_capacity integer;
    v_venue_capacity integer;
begin
    select registration_capacity into v_registration_capacity
      from public.events
     where id = p_event_id;

    select venue.capacity into v_primary_capacity
      from public.event_space_requests as space
      join public.venue_bookings as booking
        on booking.event_space_request_id = space.id and booking.status = 'approved'
      join public.venues as venue on venue.id = booking.venue_id
     where space.event_id = p_event_id and space.is_primary
     order by space.created_at, space.id
     limit 1;

    if v_primary_capacity is null then
        select min(venue.capacity) into v_venue_capacity
          from public.event_space_requests as space
          join public.venue_bookings as booking
            on booking.event_space_request_id = space.id and booking.status = 'approved'
          join public.venues as venue on venue.id = booking.venue_id
         where space.event_id = p_event_id;
    else
        v_venue_capacity := v_primary_capacity;
    end if;

    select min(capacity) into v_registration_capacity
      from unnest(array[v_registration_capacity, v_venue_capacity]) as capacities(capacity)
     where capacity is not null;
    return v_registration_capacity;
end;
$$;

revoke all on function private.event_registration_capacity(uuid) from public, anon, authenticated;

create function private.event_registration_occupied_count(p_event_id uuid)
returns integer
language sql
security definer
set search_path = ''
as $$
    select count(*)::integer
      from public.event_registrations
     where event_id = p_event_id
       and (
           status = 'registered'
           or (status = 'invited' and invitation_expires_at > clock_timestamp())
       );
$$;

revoke all on function private.event_registration_occupied_count(uuid) from public, anon, authenticated;

create function private.process_waitlist_for_event(p_event_id uuid)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events%rowtype;
    v_registration public.event_registrations%rowtype;
    v_capacity integer;
    v_invited_count integer := 0;
    v_now timestamptz;
begin
    select * into v_event
      from public.events
     where id = p_event_id
     for update;

    if not found then
        return 0;
    end if;

    update public.event_registrations
       set status = 'invitation_expired',
           invitation_expires_at = null
     where event_id = p_event_id
       and status = 'invited'
       and invitation_expires_at <= clock_timestamp();

    if v_event.status not in ('confirmed', 'preparation')
       or not v_event.registration_enabled
       or v_event.registration_opens_at is null
       or clock_timestamp() < v_event.registration_opens_at
       or (v_event.registration_closes_at is not null
           and clock_timestamp() >= v_event.registration_closes_at) then
        return 0;
    end if;

    v_capacity := private.event_registration_capacity(p_event_id);
    loop
        if v_capacity is not null
           and private.event_registration_occupied_count(p_event_id) >= v_capacity then
            exit;
        end if;

        select * into v_registration
          from public.event_registrations
         where event_id = p_event_id and status = 'waitlisted'
         order by waitlist_order
         limit 1
         for update skip locked;

        if not found then
            exit;
        end if;

        v_now := clock_timestamp();
        update public.event_registrations
           set status = 'invited',
               waitlist_order = null,
               invited_at = v_now,
               invitation_expires_at = v_now + interval '24 hours'
         where id = v_registration.id;

        perform public.add_notification(
            v_registration.attendee_id,
            p_event_id,
            'attendee_waitlist_invitation',
            'A place is available for "' || v_event.name
                || '". Accept within 24 hours to keep it reserved.',
            null,
            'waitlist-invitation:' || v_registration.id::text || ':' || v_now::text
        );
        v_invited_count := v_invited_count + 1;
    end loop;

    return v_invited_count;
end;
$$;

revoke all on function private.process_waitlist_for_event(uuid) from public, anon, authenticated;

create function public.registration_occupied_count(p_event_id uuid)
returns integer
language sql
security definer
set search_path = ''
as $$
    select private.event_registration_occupied_count(p_event_id);
$$;

revoke all on function public.registration_occupied_count(uuid) from public, anon, authenticated;
grant execute on function public.registration_occupied_count(uuid) to service_role;

create or replace function public.register_for_event(p_event_id uuid, p_attendee_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events%rowtype;
    v_existing public.event_registrations%rowtype;
    v_capacity integer;
    v_occupied_count integer;
    v_now timestamptz;
begin
    select * into v_event
      from public.events
     where id = p_event_id
     for update;

    if not found or v_event.status not in ('confirmed', 'preparation') then
        return jsonb_build_object('outcome', 'unavailable');
    end if;

    perform private.process_waitlist_for_event(p_event_id);

    select * into v_existing
      from public.event_registrations
     where event_id = p_event_id and attendee_id = p_attendee_id
     order by registered_at desc
     limit 1
     for update;

    if v_existing.status = 'registered' then
        return jsonb_build_object('outcome', 'already_registered', 'registration_id', v_existing.id);
    end if;
    if v_existing.status = 'waitlisted' then
        return jsonb_build_object(
            'outcome', 'already_waitlisted',
            'registration_id', v_existing.id,
            'registered_at', v_existing.registered_at
        );
    end if;
    if v_existing.status = 'invited' then
        return jsonb_build_object(
            'outcome', 'invited',
            'registration_id', v_existing.id,
            'registered_at', v_existing.registered_at,
            'invitation_expires_at', v_existing.invitation_expires_at
        );
    end if;
    if v_existing.status = 'withdrawn' and not v_event.re_registration_allowed then
        return jsonb_build_object('outcome', 'reregistration_disabled');
    end if;

    if not v_event.registration_enabled or v_event.registration_opens_at is null
       or clock_timestamp() < v_event.registration_opens_at then
        return jsonb_build_object('outcome', 'not_open');
    end if;
    if v_event.registration_closes_at is not null
       and clock_timestamp() >= v_event.registration_closes_at then
        return jsonb_build_object('outcome', 'closed');
    end if;

    v_capacity := private.event_registration_capacity(p_event_id);
    v_occupied_count := private.event_registration_occupied_count(p_event_id);
    v_now := clock_timestamp();

    if v_capacity is not null and v_occupied_count >= v_capacity then
        if not v_event.waitlist_enabled then
            return jsonb_build_object('outcome', 'full');
        end if;

        if v_existing.id is not null then
            update public.event_registrations
               set status = 'waitlisted',
                   registered_at = v_now,
                   withdrawn_at = null,
                   waitlist_order = nextval('public.event_waitlist_order_seq'),
                   invited_at = null,
                   invitation_expires_at = null
             where id = v_existing.id
             returning * into v_existing;
        else
            insert into public.event_registrations (
                event_id, attendee_id, status, registered_at, waitlist_order
            ) values (
                p_event_id, p_attendee_id, 'waitlisted', v_now,
                nextval('public.event_waitlist_order_seq')
            )
            returning * into v_existing;
        end if;

        return jsonb_build_object(
            'outcome', 'waitlisted',
            'registration_id', v_existing.id,
            'registered_at', v_existing.registered_at
        );
    end if;

    if v_existing.id is not null then
        update public.event_registrations
           set status = 'registered',
               registered_at = v_now,
               withdrawn_at = null,
               waitlist_order = null,
               invited_at = null,
               invitation_expires_at = null
         where id = v_existing.id
         returning * into v_existing;
    else
        insert into public.event_registrations (event_id, attendee_id, registered_at)
        values (p_event_id, p_attendee_id, v_now)
        returning * into v_existing;
    end if;

    return jsonb_build_object(
        'outcome', 'registered',
        'registration_id', v_existing.id,
        'registered_at', v_existing.registered_at
    );
end;
$$;

create or replace function public.accept_waitlist_invitation(
    p_registration_id uuid,
    p_attendee_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event_id uuid;
    v_registration public.event_registrations%rowtype;
begin
    select event_id into v_event_id
      from public.event_registrations
     where id = p_registration_id and attendee_id = p_attendee_id;

    if v_event_id is null then
        return jsonb_build_object('outcome', 'not_found');
    end if;

    perform 1 from public.events where id = v_event_id for update;
    perform private.process_waitlist_for_event(v_event_id);

    select * into v_registration
      from public.event_registrations
     where id = p_registration_id and attendee_id = p_attendee_id
     for update;

    if v_registration.status = 'invitation_expired' then
        return jsonb_build_object('outcome', 'expired');
    end if;
    if v_registration.status <> 'invited'
       or v_registration.invitation_expires_at <= clock_timestamp() then
        return jsonb_build_object('outcome', 'not_invited');
    end if;

    update public.event_registrations
       set status = 'registered',
           registered_at = clock_timestamp(),
           invitation_expires_at = null
     where id = p_registration_id
     returning * into v_registration;

    return jsonb_build_object(
        'outcome', 'registered',
        'registration_id', v_registration.id,
        'registered_at', v_registration.registered_at
    );
end;
$$;

create function public.leave_waitlist(p_registration_id uuid, p_attendee_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event_id uuid;
    v_registration public.event_registrations%rowtype;
begin
    select event_id into v_event_id
      from public.event_registrations
     where id = p_registration_id and attendee_id = p_attendee_id;

    if v_event_id is null then
        return jsonb_build_object('outcome', 'not_found');
    end if;

    perform 1 from public.events where id = v_event_id for update;
    perform private.process_waitlist_for_event(v_event_id);

    select * into v_registration
      from public.event_registrations
     where id = p_registration_id and attendee_id = p_attendee_id
     for update;

    if v_registration.status not in ('waitlisted', 'invited') then
        return jsonb_build_object('outcome', 'not_active');
    end if;

    update public.event_registrations
       set status = 'left',
           waitlist_order = null,
           invitation_expires_at = null
     where id = p_registration_id;

    perform private.process_waitlist_for_event(v_event_id);
    return jsonb_build_object('outcome', 'removed');
end;
$$;

create function public.expire_waitlist_invitations()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event_id uuid;
    v_expired_count integer := 0;
begin
    for v_event_id in
        select distinct event_id
          from public.event_registrations
         where status = 'invited'
           and invitation_expires_at <= clock_timestamp()
    loop
        v_expired_count := v_expired_count + (
            select count(*)::integer
              from public.event_registrations
             where event_id = v_event_id
               and status = 'invited'
               and invitation_expires_at <= clock_timestamp()
        );
        perform private.process_waitlist_for_event(v_event_id);
    end loop;
    return v_expired_count;
end;
$$;

create function private.invite_waitlist_after_withdrawal()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if old.status = 'registered' and new.status = 'withdrawn' then
        perform private.process_waitlist_for_event(new.event_id);
    end if;
    return new;
end;
$$;

create trigger event_registrations_invite_after_withdrawal
    after update of status on public.event_registrations
    for each row
    when (old.status = 'registered' and new.status = 'withdrawn')
    execute function private.invite_waitlist_after_withdrawal();

revoke all on function public.register_for_event(uuid, uuid) from public, anon, authenticated;
grant execute on function public.register_for_event(uuid, uuid) to service_role;
revoke all on function public.accept_waitlist_invitation(uuid, uuid) from public, anon, authenticated;
grant execute on function public.accept_waitlist_invitation(uuid, uuid) to service_role;
revoke all on function public.leave_waitlist(uuid, uuid) from public, anon, authenticated;
grant execute on function public.leave_waitlist(uuid, uuid) to service_role;
revoke all on function public.expire_waitlist_invitations() from public, anon, authenticated;
grant execute on function public.expire_waitlist_invitations() to service_role;
revoke all on sequence public.event_waitlist_order_seq from public, anon, authenticated;
grant usage, select on sequence public.event_waitlist_order_seq to service_role;

comment on function public.register_for_event(uuid, uuid) is
    'Registers an active Attendee under an event-row lock, placing the Attendee in the FIFO waitlist when enabled and full (SCRUM-43/86).';
comment on function public.accept_waitlist_invitation(uuid, uuid) is
    'Accepts only the caller-owned, unexpired waitlist invitation and converts its reserved place to a registration (SCRUM-86).';
comment on function public.leave_waitlist(uuid, uuid) is
    'Removes the caller-owned waitlist entry or invitation and passes any released reservation to the next Attendee (SCRUM-86).';
comment on function public.expire_waitlist_invitations() is
    'Expires 24-hour waitlist invitations and reserves each released place for the next eligible Attendee (SCRUM-86).';

create extension if not exists pg_cron with schema pg_catalog;
select cron.schedule(
    'expire-event-waitlist-invitations',
    '* * * * *',
    'select public.expire_waitlist_invitations()'
);
