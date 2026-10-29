-- SCRUM-86 waitlist capacity, FIFO invitation and attendee transitions.
-- Run only against the project after the waitlist migration is applied:
-- `supabase db query --linked -f supabase/verification/registration_waitlist_checks.sql`
-- All fixture data is rolled back.

begin;

insert into public.user_roles (profile_id, role) values
    ('a0000000-0000-4000-8000-000000000006', 'attendee'),
    ('a0000000-0000-4000-8000-000000000007', 'attendee'),
    ('a0000000-0000-4000-8000-000000000008', 'attendee'),
    ('a0000000-0000-4000-8000-000000000009', 'attendee')
on conflict (profile_id, role) do nothing;

insert into public.events (
    id, organiser_id, coordinator_id, status, name, starts_at, ends_at,
    registration_enabled, registration_capacity, registration_opens_at,
    registration_closes_at, waitlist_enabled
) values (
    'e0000000-0000-4000-8000-000000000860',
    'a0000000-0000-4000-8000-000000000001',
    'a0000000-0000-4000-8000-000000000002',
    'confirmed',
    'SCRUM-86 waitlist verification',
    now() + interval '30 days',
    now() + interval '30 days 3 hours',
    true,
    2,
    now() - interval '1 day',
    now() + interval '29 days',
    true
);

insert into public.event_registrations (event_id, attendee_id, status) values
    ('e0000000-0000-4000-8000-000000000860', 'a0000000-0000-4000-8000-000000000003', 'registered'),
    ('e0000000-0000-4000-8000-000000000860', 'a0000000-0000-4000-8000-000000000004', 'registered');

insert into public.events (
    id, organiser_id, coordinator_id, status, name, starts_at, ends_at,
    registration_enabled, registration_capacity, registration_opens_at,
    registration_closes_at, waitlist_enabled
) values (
    'e0000000-0000-4000-8000-000000000861',
    'a0000000-0000-4000-8000-000000000001',
    'a0000000-0000-4000-8000-000000000002',
    'confirmed',
    'SCRUM-86 venue capacity verification',
    now() + interval '30 days',
    now() + interval '30 days 3 hours',
    true,
    3,
    now() - interval '1 day',
    now() + interval '29 days',
    true
);

insert into public.venues (id, name, location, capacity, opens_at, closes_at)
values (
    'a0000000-0000-4000-8000-000000000861',
    'SCRUM-86 Waitlist Verification Venue',
    'Live check',
    2,
    '08:00',
    '22:00'
);

insert into public.event_space_requests (id, event_id, label, is_primary)
values (
    'b0000000-0000-4000-8000-000000000861',
    'e0000000-0000-4000-8000-000000000861',
    'Main space',
    true
);

insert into public.venue_bookings (
    id, event_id, event_space_request_id, venue_id, booked_period,
    occupied_period, status, requested_by
) values (
    'd0000000-0000-4000-8000-000000000861',
    'e0000000-0000-4000-8000-000000000861',
    'b0000000-0000-4000-8000-000000000861',
    'a0000000-0000-4000-8000-000000000861',
    tstzrange(now() + interval '30 days', now() + interval '30 days 3 hours', '[)'),
    tstzrange(now() + interval '30 days', now() + interval '30 days 3 hours', '[)'),
    'approved',
    'a0000000-0000-4000-8000-000000000002'
);

insert into public.event_registrations (event_id, attendee_id, status) values
    ('e0000000-0000-4000-8000-000000000861', 'a0000000-0000-4000-8000-000000000003', 'registered'),
    ('e0000000-0000-4000-8000-000000000861', 'a0000000-0000-4000-8000-000000000004', 'registered');

do $$
declare
    v_event uuid := 'e0000000-0000-4000-8000-000000000860';
    v_capacity_event uuid := 'e0000000-0000-4000-8000-000000000861';
    v_first uuid := 'a0000000-0000-4000-8000-000000000005';
    v_second uuid := 'a0000000-0000-4000-8000-000000000006';
    v_third uuid := 'a0000000-0000-4000-8000-000000000007';
    v_fourth uuid := 'a0000000-0000-4000-8000-000000000008';
    v_fifth uuid := 'a0000000-0000-4000-8000-000000000009';
    v_first_registration uuid;
    v_second_registration uuid;
    v_third_registration uuid;
    v_fourth_registration uuid;
    v_fifth_registration uuid;
    v_sixth_registration uuid;
    v_result jsonb;
    v_active integer;
begin
    -- Venue capacity is the effective limit when it is below the event limit.
    v_result := public.register_for_event(v_capacity_event, 'a0000000-0000-4000-8000-000000000005');
    if v_result ->> 'outcome' <> 'waitlisted'
       or private.event_registration_capacity(v_capacity_event) <> 2
       or public.registration_occupied_count(v_capacity_event) <> 2 then
        raise exception 'WAITLIST FAIL: the approved primary venue did not cap capacity at two: %', v_result;
    end if;

    v_result := public.register_for_event(v_event, v_first);
    if v_result ->> 'outcome' <> 'waitlisted' then
        raise exception 'WAITLIST FAIL: first full-event registration returned %', v_result;
    end if;
    v_first_registration := (v_result ->> 'registration_id')::uuid;

    v_result := public.register_for_event(v_event, v_second);
    if v_result ->> 'outcome' <> 'waitlisted' then
        raise exception 'WAITLIST FAIL: second full-event registration returned %', v_result;
    end if;
    v_second_registration := (v_result ->> 'registration_id')::uuid;

    v_result := public.register_for_event(v_event, v_third);
    if v_result ->> 'outcome' <> 'waitlisted' then
        raise exception 'WAITLIST FAIL: third full-event registration returned %', v_result;
    end if;
    v_third_registration := (v_result ->> 'registration_id')::uuid;

    v_result := public.register_for_event(v_event, v_fourth);
    if v_result ->> 'outcome' <> 'waitlisted' then
        raise exception 'WAITLIST FAIL: fourth full-event registration returned %', v_result;
    end if;
    v_fourth_registration := (v_result ->> 'registration_id')::uuid;

    if (select count(*) from public.event_registrations
         where event_id = v_event and status = 'waitlisted') <> 4 then
        raise exception 'WAITLIST FAIL: expected four queued attendees';
    end if;

    -- One freed place reserves an invitation for the first queued attendee.
    update public.event_registrations
       set status = 'withdrawn', withdrawn_at = now()
     where event_id = v_event and attendee_id = 'a0000000-0000-4000-8000-000000000003';

    if not exists (
        select 1 from public.event_registrations
         where id = v_first_registration and status = 'invited'
           and invitation_expires_at > now()
           and invitation_expires_at = invited_at + interval '24 hours'
    ) then
        raise exception 'WAITLIST FAIL: earliest attendee was not invited with an active reservation';
    end if;
    if not exists (
        select 1 from public.event_registrations
         where id = v_second_registration and status = 'waitlisted'
    ) then
        raise exception 'WAITLIST FAIL: later attendee left the queue too early';
    end if;
    if not exists (
        select 1 from public.notifications
         where event_id = v_event and recipient_id = v_first
           and type = 'attendee_waitlist_invitation'
           and recipient_role = 'attendee'
    ) then
        raise exception 'WAITLIST FAIL: invitation notification missing or not addressed to the Attendee role';
    end if;

    -- Another attendee cannot accept this invitation.
    v_result := public.accept_waitlist_invitation(v_first_registration, v_second);
    if v_result ->> 'outcome' <> 'not_found' then
        raise exception 'WAITLIST FAIL: another attendee could accept an invitation: %', v_result;
    end if;

    -- Acceptance consumes the reservation without increasing occupied places.
    v_result := public.accept_waitlist_invitation(v_first_registration, v_first);
    if v_result ->> 'outcome' <> 'registered' then
        raise exception 'WAITLIST FAIL: invitee could not accept: %', v_result;
    end if;
    select count(*) into v_active
      from public.event_registrations
     where event_id = v_event and status in ('registered', 'invited')
       and (status = 'registered' or invitation_expires_at > now());
    if v_active <> 2 then
        raise exception 'WAITLIST FAIL: expected two occupied places after acceptance, got %', v_active;
    end if;

    -- A later withdrawal invites the next attendee. Expiry advances FIFO again.
    update public.event_registrations
       set status = 'withdrawn', withdrawn_at = now()
     where id = v_first_registration;
    if (select status from public.event_registrations where id = v_second_registration) <> 'invited' then
        raise exception 'WAITLIST FAIL: next FIFO attendee was not invited after withdrawal';
    end if;
    update public.event_registrations
       set invitation_expires_at = now() - interval '1 second'
     where id = v_second_registration;
    perform public.expire_waitlist_invitations();
    if (select status from public.event_registrations where id = v_second_registration) <> 'invitation_expired'
       or (select status from public.event_registrations where id = v_third_registration) <> 'invited' then
        raise exception 'WAITLIST FAIL: an expired invitation did not pass to the next FIFO attendee';
    end if;

    -- Leaving while invited cancels the reservation and advances it again.
    v_result := public.leave_waitlist(v_third_registration, v_third);
    if v_result ->> 'outcome' <> 'removed' then
        raise exception 'WAITLIST FAIL: invited attendee could not leave: %', v_result;
    end if;
    if (select status from public.event_registrations where id = v_fourth_registration) <> 'invited' then
        raise exception 'WAITLIST FAIL: leaving an invitation did not pass the reservation to the next attendee';
    end if;

    v_result := public.register_for_event(v_event, v_fifth);
    if v_result ->> 'outcome' <> 'waitlisted' then
        raise exception 'WAITLIST FAIL: new attendee was not queued behind an open invitation: %', v_result;
    end if;
    v_fifth_registration := (v_result ->> 'registration_id')::uuid;
    if (select count(*) from public.event_registrations
         where event_id = v_event and status in ('registered', 'invited')
           and (status = 'registered' or invitation_expires_at > now())) > 2 then
        raise exception 'WAITLIST FAIL: Registered plus invited exceeds effective capacity';
    end if;

    v_result := public.register_for_event(v_event, 'a0000000-0000-4000-8000-000000000001');
    if v_result ->> 'outcome' <> 'waitlisted' then
        raise exception 'WAITLIST FAIL: another attendee was not queued: %', v_result;
    end if;
    v_sixth_registration := (v_result ->> 'registration_id')::uuid;
    v_result := public.leave_waitlist(v_sixth_registration, 'a0000000-0000-4000-8000-000000000001');
    if v_result ->> 'outcome' <> 'removed'
       or (select status from public.event_registrations where id = v_sixth_registration) <> 'left'
       or (select status from public.event_registrations where id = v_fifth_registration) <> 'waitlisted' then
        raise exception 'WAITLIST FAIL: leaving the queue did not remove only that attendee: %', v_result;
    end if;

    -- Disabling new joins does not delete the existing queue or invitation.
    update public.events set waitlist_enabled = false where id = v_event;
    v_result := public.register_for_event(v_event, 'a0000000-0000-4000-8000-000000000002');
    if v_result ->> 'outcome' <> 'full' then
        raise exception 'WAITLIST FAIL: new joins were not refused after disabling the waitlist: %', v_result;
    end if;
    if (select status from public.event_registrations where id = v_fourth_registration) <> 'invited'
       or (select status from public.event_registrations where id = v_fifth_registration) <> 'waitlisted'
       or (select status from public.event_registrations where id = v_sixth_registration) <> 'left' then
        raise exception 'WAITLIST FAIL: disabling new joins removed an existing invitation or queue entry';
    end if;
end $$;

select 'WAITLIST CHECKS PASSED' as result;
rollback;
