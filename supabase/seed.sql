-- =============================================================================
-- ConnectSphere — local/dev seed data
-- Creates one confirmed test account per user role directly in auth.users /
-- auth.identities. public.profiles rows are populated automatically by the
-- on_auth_user_created trigger from raw_user_meta_data. That trigger only
-- accepts external roles from sign-up metadata, so internal staff roles are
-- set explicitly on the profile afterwards.
--
-- Run after applying migrations, e.g.:
--   psql "$DATABASE_URL" -f supabase/seed.sql
--
-- All seeded accounts share the password: Cs1234
-- =============================================================================

create extension if not exists pgcrypto;

do $$
declare
    v_password text := 'Cs1234';
    v_instance_id uuid := '00000000-0000-0000-0000-000000000000';

    v_organiser_id uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator_id uuid := 'a0000000-0000-4000-8000-000000000002';
    v_venue_staff_id uuid := 'a0000000-0000-4000-8000-000000000003';
    v_tech_support_id uuid := 'a0000000-0000-4000-8000-000000000004';
    v_attendee_id uuid := 'a0000000-0000-4000-8000-000000000005';

    v_users jsonb := jsonb_build_array(
        jsonb_build_object(
            'id', v_organiser_id,
            'email', 'organiser@connectsphere.dev',
            'full_name', 'Olivia Tan',
            'role', 'event_organiser',
            'organisation_name', 'Tan & Partners Events',
            'department', null,
            'phone_number', '+65 9000 0001'
        ),
        jsonb_build_object(
            'id', v_coordinator_id,
            'email', 'coordinator@connectsphere.dev',
            'full_name', 'Marcus Lim',
            'role', 'event_coordinator',
            'organisation_name', null,
            'department', 'Event Planning',
            'phone_number', '+65 9000 0002'
        ),
        jsonb_build_object(
            'id', v_venue_staff_id,
            'email', 'venue.staff@connectsphere.dev',
            'full_name', 'Priya Nair',
            'role', 'venue_staff',
            'organisation_name', null,
            'department', 'Venue Operations',
            'phone_number', '+65 9000 0003'
        ),
        jsonb_build_object(
            'id', v_tech_support_id,
            'email', 'tech.support@connectsphere.dev',
            'full_name', 'Daniel Wong',
            'role', 'tech_support',
            'organisation_name', null,
            'department', 'Technical Services',
            'phone_number', '+65 9000 0004'
        ),
        jsonb_build_object(
            'id', v_attendee_id,
            'email', 'attendee@connectsphere.dev',
            'full_name', 'Siti Rahman',
            'role', 'attendee',
            'organisation_name', null,
            'department', null,
            'phone_number', '+65 9000 0005'
        )
    );
    v_user jsonb;
begin
    for v_user in select * from jsonb_array_elements(v_users)
    loop
        insert into auth.users (
            instance_id,
            id,
            aud,
            role,
            email,
            encrypted_password,
            email_confirmed_at,
            raw_app_meta_data,
            raw_user_meta_data,
            created_at,
            updated_at,
            confirmation_token,
            recovery_token,
            email_change_token_new,
            email_change
        )
        values (
            v_instance_id,
            (v_user ->> 'id')::uuid,
            'authenticated',
            'authenticated',
            v_user ->> 'email',
            crypt(v_password, gen_salt('bf')),
            now(),
            '{"provider": "email", "providers": ["email"]}'::jsonb,
            jsonb_build_object(
                'full_name', v_user ->> 'full_name',
                'role', v_user ->> 'role',
                'organisation_name', v_user ->> 'organisation_name',
                'department', v_user ->> 'department',
                'phone_number', v_user ->> 'phone_number'
            ),
            now(),
            now(),
            '',
            '',
            '',
            ''
        )
        on conflict (id) do nothing;

        insert into auth.identities (
            id,
            provider_id,
            user_id,
            identity_data,
            provider,
            last_sign_in_at,
            created_at,
            updated_at
        )
        values (
            gen_random_uuid(),
            v_user ->> 'id',
            (v_user ->> 'id')::uuid,
            jsonb_build_object('sub', v_user ->> 'id', 'email', v_user ->> 'email'),
            'email',
            now(),
            now(),
            now()
        )
        on conflict (provider, provider_id) do nothing;

        update public.profiles
        set role = (v_user ->> 'role')::public.user_role
        where id = (v_user ->> 'id')::uuid
          and role is distinct from (v_user ->> 'role')::public.user_role;

        -- handle_new_user() only accepts 'event_organiser'/'attendee' from sign-up
        -- metadata (D2), so it grants every staff account 'attendee' in user_roles
        -- on insert. Correct that stray grant to match the role actually seeded,
        -- so a fresh `supabase db reset` doesn't leave staff accounts unable to
        -- switch back to their own role (they'd hold only 'attendee').
        if (v_user ->> 'role') <> 'attendee' then
            delete from public.user_roles
            where profile_id = (v_user ->> 'id')::uuid
              and role = 'attendee';
        end if;

        insert into public.user_roles (profile_id, role)
        values ((v_user ->> 'id')::uuid, (v_user ->> 'role')::public.user_role)
        on conflict do nothing;
    end loop;

    -- SCRUM-74/75: give the coordinator test account a second role, the same
    -- Coordinator + Venue Staff pairing ACC-R4 itself uses as its example, so
    -- the role switcher is exercisable immediately after seeding.
    insert into public.user_roles (profile_id, role)
    values (v_coordinator_id, 'venue_staff')
    on conflict do nothing;
end $$;

-- =============================================================================
-- SCRUM-8: event records referenced by the venue catalogue fixtures. These are
-- planning records so the venue bookings have valid event foreign keys while
-- remaining outside the organiser's normal draft workflow.
-- =============================================================================

insert into public.events (
    id, organiser_id, status, name, purpose, starts_at, ends_at,
    expected_attendance, layout_preference
)
values
    ('e0000000-0000-4000-8000-000000000101', 'a0000000-0000-4000-8000-000000000001', 'planning',
     'Seed Auditorium Event', 'Venue search fixture', '2026-10-10 11:00+08', '2026-10-10 14:00+08', 120, 'theatre'),
    ('e0000000-0000-4000-8000-000000000102', 'a0000000-0000-4000-8000-000000000001', 'planning',
     'Seed Seminar Event', 'Venue search fixture', '2026-10-10 13:00+08', '2026-10-10 16:00+08', 50, 'classroom'),
    ('e0000000-0000-4000-8000-000000000103', 'a0000000-0000-4000-8000-000000000001', 'planning',
     'Seed Innovation Event', 'Venue search fixture', '2026-10-10 14:00+08', '2026-10-10 17:00+08', 60, 'classroom')
on conflict (id) do nothing;

-- =============================================================================
-- SCRUM-39: venue catalogue with a few blocks and bookings on 10 Oct 2026, so
-- a search for 10 Oct 14:00–17:00 (Asia/Singapore) demonstrates every
-- exclusion reason. Idempotent: fixed ids, `on conflict do nothing`.
-- Event ids are placeholders until the events module lands.
-- =============================================================================

insert into public.venues (id, name, location, capacity, accessibility_features, opens_at, closes_at, is_active, description)
values
    ('b0000000-0000-4000-8000-000000000001', 'Grand Ballroom', 'Marina Bay Convention Centre, Level 3', 500,
     '{wheelchair_access,step_free_entry,accessible_toilet,lift_access}', '08:00', '23:00', true,
     'Pillar-free ballroom with a built-in stage and pre-function foyer.'),
    ('b0000000-0000-4000-8000-000000000002', 'Auditorium A', 'Bukit Timah Campus, Block A', 200,
     '{wheelchair_access,hearing_loop,accessible_toilet}', '08:00', '22:00', true,
     'Tiered auditorium with fixed seating.'),
    ('b0000000-0000-4000-8000-000000000003', 'Seminar Room 1', 'Bukit Timah Campus, Block B, Level 2', 60,
     '{wheelchair_access,lift_access}', '08:00', '22:00', true,
     'Flexible seminar room with movable furniture.'),
    ('b0000000-0000-4000-8000-000000000004', 'Boardroom Orchid', 'Orchard Road Office, Level 12', 16,
     '{wheelchair_access,lift_access,accessible_toilet}', '09:00', '18:00', true,
     'Executive boardroom.'),
    ('b0000000-0000-4000-8000-000000000005', 'Rooftop Terrace', 'Orchard Road Office, Level 20', 120,
     '{}', '10:00', '22:00', true,
     'Open-air terrace; stairs only from Level 19.'),
    ('b0000000-0000-4000-8000-000000000006', 'Innovation Lab', 'Jurong East Hub, Level 1', 80,
     '{step_free_entry,accessible_toilet}', '08:00', '21:00', true,
     'Workshop space with writable walls.'),
    ('b0000000-0000-4000-8000-000000000007', 'Heritage Hall', 'Chinatown Heritage Centre', 150,
     '{step_free_entry}', '09:00', '22:00', true,
     'Restored shophouse hall.'),
    ('b0000000-0000-4000-8000-000000000008', 'Old Lecture Theatre', 'Bukit Timah Campus, Block C', 300,
     '{}', '08:00', '22:00', false,
     'Decommissioned pending refurbishment.')
on conflict (name) do nothing;

-- SCRUM-67: the venue profile shows when it was last updated and by whom. The
-- catalogue was entered by venue staff, so the seed stamps them as the last
-- editor. Guarded on `updated_by is null` so re-running the seed does not keep
-- bumping `updated_at` through the trigger.
update public.venues
   set updated_by = 'a0000000-0000-4000-8000-000000000003'
 where updated_by is null;

insert into public.venue_layouts (venue_id, layout, capacity_for_layout)
values
    ('b0000000-0000-4000-8000-000000000001', 'theatre', 500),
    ('b0000000-0000-4000-8000-000000000001', 'banquet', 300),
    ('b0000000-0000-4000-8000-000000000001', 'reception', 500),
    ('b0000000-0000-4000-8000-000000000001', 'classroom', 250),
    ('b0000000-0000-4000-8000-000000000002', 'theatre', null),
    ('b0000000-0000-4000-8000-000000000003', 'classroom', 40),
    ('b0000000-0000-4000-8000-000000000003', 'u_shape', 24),
    ('b0000000-0000-4000-8000-000000000003', 'boardroom', 20),
    ('b0000000-0000-4000-8000-000000000003', 'theatre', null),
    ('b0000000-0000-4000-8000-000000000004', 'boardroom', null),
    ('b0000000-0000-4000-8000-000000000005', 'reception', null),
    ('b0000000-0000-4000-8000-000000000005', 'banquet', 80),
    ('b0000000-0000-4000-8000-000000000006', 'classroom', 60),
    ('b0000000-0000-4000-8000-000000000006', 'u_shape', 30),
    ('b0000000-0000-4000-8000-000000000006', 'reception', null),
    ('b0000000-0000-4000-8000-000000000007', 'theatre', null),
    ('b0000000-0000-4000-8000-000000000007', 'banquet', 100),
    ('b0000000-0000-4000-8000-000000000008', 'theatre', null)
on conflict do nothing;

insert into public.venue_facilities (venue_id, facility)
values
    ('b0000000-0000-4000-8000-000000000001', 'projector'),
    ('b0000000-0000-4000-8000-000000000001', 'sound_system'),
    ('b0000000-0000-4000-8000-000000000001', 'microphone'),
    ('b0000000-0000-4000-8000-000000000001', 'stage'),
    ('b0000000-0000-4000-8000-000000000001', 'wifi'),
    ('b0000000-0000-4000-8000-000000000001', 'catering_space'),
    ('b0000000-0000-4000-8000-000000000002', 'projector'),
    ('b0000000-0000-4000-8000-000000000002', 'sound_system'),
    ('b0000000-0000-4000-8000-000000000002', 'microphone'),
    ('b0000000-0000-4000-8000-000000000002', 'wifi'),
    ('b0000000-0000-4000-8000-000000000003', 'projector'),
    ('b0000000-0000-4000-8000-000000000003', 'whiteboard'),
    ('b0000000-0000-4000-8000-000000000003', 'wifi'),
    ('b0000000-0000-4000-8000-000000000003', 'video_conferencing'),
    ('b0000000-0000-4000-8000-000000000004', 'video_conferencing'),
    ('b0000000-0000-4000-8000-000000000004', 'whiteboard'),
    ('b0000000-0000-4000-8000-000000000004', 'wifi'),
    ('b0000000-0000-4000-8000-000000000005', 'sound_system'),
    ('b0000000-0000-4000-8000-000000000005', 'catering_space'),
    ('b0000000-0000-4000-8000-000000000006', 'projector'),
    ('b0000000-0000-4000-8000-000000000006', 'whiteboard'),
    ('b0000000-0000-4000-8000-000000000006', 'wifi'),
    ('b0000000-0000-4000-8000-000000000006', 'video_conferencing'),
    ('b0000000-0000-4000-8000-000000000007', 'sound_system'),
    ('b0000000-0000-4000-8000-000000000007', 'stage'),
    ('b0000000-0000-4000-8000-000000000007', 'microphone'),
    ('b0000000-0000-4000-8000-000000000008', 'projector')
on conflict do nothing;

insert into public.venue_blocks (id, venue_id, blocked_period, reason, notes)
values
    ('c0000000-0000-4000-8000-000000000001', 'b0000000-0000-4000-8000-000000000007',
     tstzrange('2026-10-01 00:00+08', '2026-10-15 00:00+08', '[)'), 'renovation', 'Floor restoration.'),
    ('c0000000-0000-4000-8000-000000000002', 'b0000000-0000-4000-8000-000000000001',
     tstzrange('2026-10-10 08:00+08', '2026-10-10 12:00+08', '[)'), 'maintenance', 'Air-con servicing; ends exactly at noon.'),
    ('c0000000-0000-4000-8000-000000000003', 'b0000000-0000-4000-8000-000000000005',
     tstzrange('2026-10-20 00:00+08', '2026-10-22 00:00+08', '[)'), 'safety', 'Railing inspection.')
on conflict (id) do nothing;

-- `created_at` is given explicitly rather than left to its default: the
-- venue-staff dashboard sorts pending holds oldest-first (BR-R4), and a seed
-- whose rows all share one insert timestamp cannot demonstrate that ordering.
insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, created_at)
values
    -- Back-to-back with a 14:00–17:00 search: Auditorium A stays listed.
    ('d0000000-0000-4000-8000-000000000001', 'e0000000-0000-4000-8000-000000000101',
     'b0000000-0000-4000-8000-000000000002', tstzrange('2026-10-10 11:00+08', '2026-10-10 14:00+08', '[)'),
     'approved', '2026-09-01 09:00+08'),
    -- Overlaps a 14:00–17:00 search: Seminar Room 1 is "held by another event".
    ('d0000000-0000-4000-8000-000000000002', 'e0000000-0000-4000-8000-000000000102',
     'b0000000-0000-4000-8000-000000000003', tstzrange('2026-10-10 13:00+08', '2026-10-10 16:00+08', '[)'),
     'held', '2026-09-03 10:30+08'),
    -- Rejected bookings no longer occupy the venue: Innovation Lab stays listed.
    ('d0000000-0000-4000-8000-000000000003', 'e0000000-0000-4000-8000-000000000103',
     'b0000000-0000-4000-8000-000000000006', tstzrange('2026-10-10 14:00+08', '2026-10-10 17:00+08', '[)'),
     'rejected', '2026-09-04 14:00+08'),
    -- The two rows below exist for the venue-staff dashboard (SCRUM-70) and are
    -- clear of the 10 Oct window the search cases above depend on.
    --
    -- A second hold, requested *before* the Seminar Room 1 one, so the
    -- dashboard's oldest-first ordering is visible rather than merely asserted.
    ('d0000000-0000-4000-8000-000000000004', 'e0000000-0000-4000-8000-000000000104',
     'b0000000-0000-4000-8000-000000000005', tstzrange('2026-10-13 09:00+08', '2026-10-13 12:00+08', '[)'),
     'held', '2026-08-28 16:15+08'),
    -- A booking sent back for re-review after an approved change (§6.19), so
    -- that dashboard tile has something to show.
    ('d0000000-0000-4000-8000-000000000005', 'e0000000-0000-4000-8000-000000000105',
     'b0000000-0000-4000-8000-000000000004', tstzrange('2026-10-12 09:00+08', '2026-10-12 12:00+08', '[)'),
     're_review', '2026-09-10 11:45+08')
on conflict (id) do nothing;
