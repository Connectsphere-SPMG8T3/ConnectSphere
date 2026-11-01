-- SCRUM-53 AC5, AC1/AC3/AC6: attendee notices for their own registration
-- status changes, and for an approved replacement venue (TC-NOTIF-017, 018).
-- Drives the real functions: register_for_event, withdraw_registration,
-- accept_waitlist_invitation, leave_waitlist, expire_waitlist_invitations and
-- approve_venue_booking. Run with `supabase db query --linked -f` or
-- `psql "$DATABASE_URL" -f`. Raises on the first failure and prints
-- NOTIFICATION REGISTRATION CHECKS PASSED otherwise. Everything runs inside
-- `begin; ... rollback;`.
-- Seeded accounts: organiser …0001, coordinator …0002, venue staff …0003,
-- attendee …0005. Venues: Grand Ballroom (b…0001), Seminar Room 1 (b…0003).

begin;

insert into auth.users (id, email, raw_user_meta_data, raw_app_meta_data) values
    ('c5300000-0000-4000-8000-000000000001', 'notif53-check+1@example.invalid',
     '{"full_name":"Notice check attendee 1","role":"attendee"}', '{}'),
    ('c5300000-0000-4000-8000-000000000002', 'notif53-check+2@example.invalid',
     '{"full_name":"Notice check attendee 2","role":"attendee"}', '{}'),
    ('c5300000-0000-4000-8000-000000000003', 'notif53-check+3@example.invalid',
     '{"full_name":"Notice check attendee 3","role":"attendee"}', '{}'),
    ('c5300000-0000-4000-8000-000000000004', 'notif53-check+4@example.invalid',
     '{"full_name":"Notice check attendee 4","role":"attendee"}', '{}');

insert into public.user_roles (profile_id, role) values
    ('c5300000-0000-4000-8000-000000000001', 'attendee'),
    ('c5300000-0000-4000-8000-000000000002', 'attendee'),
    ('c5300000-0000-4000-8000-000000000003', 'attendee'),
    ('c5300000-0000-4000-8000-000000000004', 'attendee')
on conflict (profile_id, role) do nothing;

-- One place, waitlist on: every registration status is reachable.
insert into public.events (
    id, organiser_id, coordinator_id, status, name, starts_at, ends_at,
    registration_enabled, registration_capacity, registration_opens_at,
    registration_closes_at, waitlist_enabled
) values (
    'e0000000-0000-4000-8000-000000000531', 'a0000000-0000-4000-8000-000000000001',
    'a0000000-0000-4000-8000-000000000002', 'confirmed', 'Notice check talk',
    now() + interval '30 days', now() + interval '30 days 2 hours',
    true, 1, now() - interval '1 day', now() + interval '29 days', true
);

-- Replacement venues: 532 has no spaces, 533 replaces its primary space, 534
-- replaces a secondary space while a primary is set, 535 stays in the same venue.
insert into public.events (id, organiser_id, coordinator_id, status, name, starts_at, ends_at) values
    ('e0000000-0000-4000-8000-000000000532', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Notice check no primary',
     '2034-03-01 10:00+08', '2034-03-01 12:00+08'),
    ('e0000000-0000-4000-8000-000000000533', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Notice check primary',
     '2034-03-02 10:00+08', '2034-03-02 12:00+08'),
    ('e0000000-0000-4000-8000-000000000534', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Notice check secondary',
     '2034-03-03 10:00+08', '2034-03-03 12:00+08'),
    ('e0000000-0000-4000-8000-000000000535', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Notice check same venue',
     '2034-03-04 10:00+08', '2034-03-04 12:00+08');

insert into public.event_space_requests (id, event_id, label, is_primary, starts_at, ends_at) values
    ('c0000000-0000-4000-8000-000000000533', 'e0000000-0000-4000-8000-000000000533', 'Main hall', true,
     '2034-03-02 10:00+08', '2034-03-02 12:00+08'),
    ('c0000000-0000-4000-8000-000000005331', 'e0000000-0000-4000-8000-000000000533', 'Breakout', false,
     '2034-03-02 10:00+08', '2034-03-02 12:00+08'),
    ('c0000000-0000-4000-8000-000000000534', 'e0000000-0000-4000-8000-000000000534', 'Main hall', true,
     '2034-03-03 10:00+08', '2034-03-03 12:00+08'),
    ('c0000000-0000-4000-8000-000000005341', 'e0000000-0000-4000-8000-000000000534', 'Breakout', false,
     '2034-03-03 10:00+08', '2034-03-03 12:00+08');

-- Each original is approved in Seminar Room 1 and flagged Affected (CR-95).
insert into public.venue_bookings (id, event_id, event_space_request_id, venue_id, occupied_period, status, flag, flag_reason, flagged_at)
values
    ('d0000000-0000-4000-8000-000000000532', 'e0000000-0000-4000-8000-000000000532', null,
     'b0000000-0000-4000-8000-000000000003', tstzrange('2034-03-01 10:00+08', '2034-03-01 12:00+08', '[)'),
     'approved', 'affected', 'Venue unavailable: Maintenance', now()),
    ('d0000000-0000-4000-8000-000000000533', 'e0000000-0000-4000-8000-000000000533', 'c0000000-0000-4000-8000-000000000533',
     'b0000000-0000-4000-8000-000000000003', tstzrange('2034-03-02 10:00+08', '2034-03-02 12:00+08', '[)'),
     'approved', 'affected', 'Venue unavailable: Maintenance', now()),
    ('d0000000-0000-4000-8000-000000000534', 'e0000000-0000-4000-8000-000000000534', 'c0000000-0000-4000-8000-000000005341',
     'b0000000-0000-4000-8000-000000000003', tstzrange('2034-03-03 10:00+08', '2034-03-03 12:00+08', '[)'),
     'approved', 'affected', 'Venue unavailable: Maintenance', now()),
    ('d0000000-0000-4000-8000-000000000535', 'e0000000-0000-4000-8000-000000000535', null,
     'b0000000-0000-4000-8000-000000000003', tstzrange('2034-03-04 10:00+08', '2034-03-04 12:00+08', '[)'),
     'approved', 'affected', 'Venue unavailable: Maintenance', now());

-- Held replacements: Grand Ballroom, except 535's, which stays in Seminar Room 1
-- (in a later slot, since the overlap constraint still counts the original).
insert into public.venue_bookings (id, event_id, event_space_request_id, venue_id, occupied_period, status, expires_at, replaces_booking_id)
values
    ('d0000000-0000-4000-8000-000000005321', 'e0000000-0000-4000-8000-000000000532', null,
     'b0000000-0000-4000-8000-000000000001', tstzrange('2034-03-01 10:00+08', '2034-03-01 12:00+08', '[)'),
     'held', now() + interval '2 days', 'd0000000-0000-4000-8000-000000000532'),
    ('d0000000-0000-4000-8000-000000005332', 'e0000000-0000-4000-8000-000000000533', 'c0000000-0000-4000-8000-000000000533',
     'b0000000-0000-4000-8000-000000000001', tstzrange('2034-03-02 10:00+08', '2034-03-02 12:00+08', '[)'),
     'held', now() + interval '2 days', 'd0000000-0000-4000-8000-000000000533'),
    ('d0000000-0000-4000-8000-000000005342', 'e0000000-0000-4000-8000-000000000534', 'c0000000-0000-4000-8000-000000005341',
     'b0000000-0000-4000-8000-000000000001', tstzrange('2034-03-03 10:00+08', '2034-03-03 12:00+08', '[)'),
     'held', now() + interval '2 days', 'd0000000-0000-4000-8000-000000000534'),
    ('d0000000-0000-4000-8000-000000005352', 'e0000000-0000-4000-8000-000000000535', null,
     'b0000000-0000-4000-8000-000000000003', tstzrange('2034-03-04 13:00+08', '2034-03-04 15:00+08', '[)'),
     'held', now() + interval '2 days', 'd0000000-0000-4000-8000-000000000535');

-- Attendee …0005 is Registered on every replacement event; on 532, user 1 has
-- withdrawn and user 2 is waitlisted, and neither may hear about the venue.
insert into public.event_registrations (event_id, attendee_id, status, withdrawn_at, waitlist_order) values
    ('e0000000-0000-4000-8000-000000000532', 'a0000000-0000-4000-8000-000000000005', 'registered', null, null),
    ('e0000000-0000-4000-8000-000000000532', 'c5300000-0000-4000-8000-000000000001', 'withdrawn', now(), null),
    ('e0000000-0000-4000-8000-000000000532', 'c5300000-0000-4000-8000-000000000002', 'waitlisted', null,
     nextval('public.event_waitlist_order_seq')),
    ('e0000000-0000-4000-8000-000000000533', 'a0000000-0000-4000-8000-000000000005', 'registered', null, null),
    ('e0000000-0000-4000-8000-000000000534', 'a0000000-0000-4000-8000-000000000005', 'registered', null, null),
    ('e0000000-0000-4000-8000-000000000535', 'a0000000-0000-4000-8000-000000000005', 'registered', null, null);

do $$
declare
    v_event uuid := 'e0000000-0000-4000-8000-000000000531';
    v_a uuid := 'c5300000-0000-4000-8000-000000000001';
    v_b uuid := 'c5300000-0000-4000-8000-000000000002';
    v_c uuid := 'c5300000-0000-4000-8000-000000000003';
    v_d uuid := 'c5300000-0000-4000-8000-000000000004';
    v_attendee uuid := 'a0000000-0000-4000-8000-000000000005';
    v_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_result jsonb;
    v_b_reg uuid;
    v_c_reg uuid;
    v_d_reg uuid;
    v_outcome text;
    v_count integer;
begin
    -- AC5: registered.
    v_result := public.register_for_event(v_event, v_a);
    if v_result ->> 'outcome' <> 'registered' then
        raise exception 'NOTICE SETUP FAIL: first registration gave %', v_result;
    end if;
    if not exists (select 1 from public.notifications
                    where recipient_id = v_a and event_id = v_event and type = 'attendee_registration_changed'
                      and recipient_role = 'attendee'
                      and message = 'You''re registered for "Notice check talk".') then
        raise exception 'TC-NOTIF-017 FAIL: no "registered" confirmation for the attendee';
    end if;

    -- AC5: waitlisted, with the position.
    v_result := public.register_for_event(v_event, v_b);
    v_b_reg := (v_result ->> 'registration_id')::uuid;
    v_result := public.register_for_event(v_event, v_c);
    v_c_reg := (v_result ->> 'registration_id')::uuid;
    if not exists (select 1 from public.notifications
                    where recipient_id = v_b and event_id = v_event and type = 'attendee_registration_changed'
                      and message = '"Notice check talk" is full. You''re number 1 on the waiting list.') then
        raise exception 'TC-NOTIF-017 FAIL: no "number 1" waitlist confirmation';
    end if;
    if not exists (select 1 from public.notifications
                    where recipient_id = v_c and event_id = v_event and type = 'attendee_registration_changed'
                      and message = '"Notice check talk" is full. You''re number 2 on the waiting list.') then
        raise exception 'TC-NOTIF-017 FAIL: no "number 2" waitlist confirmation';
    end if;

    -- AC5: withdrawn. The freed place invites B, who gets only the existing invitation.
    v_result := public.withdraw_registration(v_event, v_a);
    if v_result ->> 'outcome' <> 'withdrawn' then
        raise exception 'NOTICE SETUP FAIL: withdrawal gave %', v_result;
    end if;
    if not exists (select 1 from public.notifications
                    where recipient_id = v_a and event_id = v_event and type = 'attendee_registration_changed'
                      and message = 'You''ve withdrawn from "Notice check talk".') then
        raise exception 'TC-NOTIF-017 FAIL: no "withdrawn" confirmation';
    end if;
    select count(*) into v_count from public.notifications
     where recipient_id = v_b and event_id = v_event and type = 'attendee_registration_changed';
    if v_count <> 1 or not exists (select 1 from public.notifications
                                    where recipient_id = v_b and event_id = v_event
                                      and type = 'attendee_waitlist_invitation') then
        raise exception 'TC-NOTIF-017 FAIL: an invitation should send only the existing invitation notice (% status notices)', v_count;
    end if;

    -- AC5: accepting the invitation is a registration.
    v_result := public.accept_waitlist_invitation(v_b_reg, v_b);
    if v_result ->> 'outcome' <> 'registered' then
        raise exception 'NOTICE SETUP FAIL: acceptance gave %', v_result;
    end if;
    if not exists (select 1 from public.notifications
                    where recipient_id = v_b and event_id = v_event and type = 'attendee_registration_changed'
                      and message = 'You''re registered for "Notice check talk".') then
        raise exception 'TC-NOTIF-017 FAIL: no "registered" confirmation after accepting';
    end if;

    -- AC5: left the waiting list.
    v_result := public.leave_waitlist(v_c_reg, v_c);
    if v_result ->> 'outcome' <> 'removed' then
        raise exception 'NOTICE SETUP FAIL: leaving gave %', v_result;
    end if;
    if not exists (select 1 from public.notifications
                    where recipient_id = v_c and event_id = v_event and type = 'attendee_registration_changed'
                      and message = 'You''ve left the waiting list for "Notice check talk".') then
        raise exception 'TC-NOTIF-017 FAIL: no "left" confirmation';
    end if;

    -- AC5: an invitation that expires.
    v_result := public.register_for_event(v_event, v_d);
    v_d_reg := (v_result ->> 'registration_id')::uuid;
    perform public.withdraw_registration(v_event, v_b);
    update public.event_registrations set invitation_expires_at = now() - interval '1 second' where id = v_d_reg;
    perform public.expire_waitlist_invitations();
    if (select status from public.event_registrations where id = v_d_reg) <> 'invitation_expired' then
        raise exception 'NOTICE SETUP FAIL: the invitation did not expire';
    end if;
    if not exists (select 1 from public.notifications
                    where recipient_id = v_d and event_id = v_event and type = 'attendee_registration_changed'
                      and message = 'Your reserved place for "Notice check talk" has expired.') then
        raise exception 'TC-NOTIF-017 FAIL: no "expired" notice';
    end if;

    -- No notice when the status doesn't change, or for a cancellation (story 115 has its own).
    select count(*) into v_count from public.notifications where recipient_id = v_a and event_id = v_event;
    update public.event_registrations set withdrawn_at = withdrawn_at where event_id = v_event and attendee_id = v_a;
    update public.event_registrations set status = 'cancelled', withdrawn_at = null where event_id = v_event and attendee_id = v_a;
    if (select count(*) from public.notifications where recipient_id = v_a and event_id = v_event) <> v_count then
        raise exception 'TC-NOTIF-017 FAIL: an unchanged status or a cancellation sent a status notice';
    end if;

    -- AC6: a flagged booking alone tells attendees nothing.
    if exists (select 1 from public.notifications
                where recipient_id = v_attendee and type = 'attendee_event_changed'
                  and event_id in ('e0000000-0000-4000-8000-000000000532', 'e0000000-0000-4000-8000-000000000533',
                                   'e0000000-0000-4000-8000-000000000534', 'e0000000-0000-4000-8000-000000000535')) then
        raise exception 'TC-NOTIF-018 FAIL: attendees were told before a replacement was approved';
    end if;

    -- AC1, AC6: approving the replacement on an event with no primary names the new venue.
    select outcome into v_outcome from public.approve_venue_booking(
        'd0000000-0000-4000-8000-000000005321', v_staff, 'Approved.');
    if v_outcome <> 'ok' then
        raise exception 'NOTICE SETUP FAIL: approving 532''s replacement gave %', v_outcome;
    end if;
    if not exists (select 1 from public.notifications
                    where recipient_id = v_attendee and event_id = 'e0000000-0000-4000-8000-000000000532'
                      and type = 'attendee_event_changed' and recipient_role = 'attendee'
                      and message = 'The venue for "Notice check no primary" has changed to Grand Ballroom.') then
        raise exception 'TC-NOTIF-018 FAIL: no venue-change notice for a Registered attendee';
    end if;
    if exists (select 1 from public.notifications
                where recipient_id in (v_a, v_b) and event_id = 'e0000000-0000-4000-8000-000000000532'
                  and type = 'attendee_event_changed') then
        raise exception 'TC-NOTIF-018 FAIL: a withdrawn or waitlisted attendee was told of the venue change';
    end if;

    -- AC3: replacing the primary venue tells attendees; a secondary one, with a primary set, doesn't.
    select outcome into v_outcome from public.approve_venue_booking(
        'd0000000-0000-4000-8000-000000005332', v_staff, 'Approved.');
    if v_outcome <> 'ok' or not exists (
        select 1 from public.notifications
         where recipient_id = v_attendee and event_id = 'e0000000-0000-4000-8000-000000000533'
           and type = 'attendee_event_changed'
           and message = 'The venue for "Notice check primary" has changed to Grand Ballroom.') then
        raise exception 'TC-NOTIF-018 FAIL: replacing the primary venue sent no notice (%)', v_outcome;
    end if;
    select outcome into v_outcome from public.approve_venue_booking(
        'd0000000-0000-4000-8000-000000005342', v_staff, 'Approved.');
    if v_outcome <> 'ok' or exists (
        select 1 from public.notifications
         where recipient_id = v_attendee and event_id = 'e0000000-0000-4000-8000-000000000534'
           and type = 'attendee_event_changed') then
        raise exception 'TC-NOTIF-018 FAIL: replacing a secondary venue told attendees (%)', v_outcome;
    end if;

    -- A replacement in the same venue changes nothing an attendee sees.
    select outcome into v_outcome from public.approve_venue_booking(
        'd0000000-0000-4000-8000-000000005352', v_staff, 'Approved.');
    if v_outcome <> 'ok' or exists (
        select 1 from public.notifications
         where recipient_id = v_attendee and event_id = 'e0000000-0000-4000-8000-000000000535'
           and type = 'attendee_event_changed') then
        raise exception 'TC-NOTIF-018 FAIL: a same-venue replacement told attendees (%)', v_outcome;
    end if;
end $$;

select 'NOTIFICATION REGISTRATION CHECKS PASSED' as result;
rollback;
