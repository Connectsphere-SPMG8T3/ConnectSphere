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
    -- CR-103 AC5 and 12 AC12: staff accounts are system defaults (ACC-R3, QA2-1).
    v_safety_officer_id uuid := 'a0000000-0000-4000-8000-000000000006';
    v_coordinator_lead_id uuid := 'a0000000-0000-4000-8000-000000000007';
    -- A second, single-role coordinator (no Venue Staff pairing), so two
    -- coordinators exist for assignment and cross-coordinator denial checks.
    v_coordinator_2_id uuid := 'a0000000-0000-4000-8000-000000000008';
    -- A second Event Coordinator Lead (CR-101 AC5: the system supports one or more
    -- Leads, and each sees the events they assigned), so the two-Lead scope can be tested.
    v_coordinator_lead_2_id uuid := 'a0000000-0000-4000-8000-000000000009';

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
        ),
        jsonb_build_object(
            'id', v_safety_officer_id,
            'email', 'safety.officer@connectsphere.dev',
            'full_name', 'Hafiz Ismail',
            'role', 'safety_officer',
            'organisation_name', null,
            'department', 'Operational Safety',
            'phone_number', '+65 9000 0006'
        ),
        jsonb_build_object(
            'id', v_coordinator_lead_id,
            'email', 'coordinator.lead@connectsphere.dev',
            'full_name', 'Grace Chua',
            'role', 'event_coordinator_lead',
            'organisation_name', null,
            'department', 'Event Planning',
            'phone_number', '+65 9000 0007'
        ),
        jsonb_build_object(
            'id', v_coordinator_2_id,
            'email', 'coordinator2@connectsphere.dev',
            'full_name', 'Nadia Koh',
            'role', 'event_coordinator',
            'organisation_name', null,
            'department', 'Event Planning',
            'phone_number', '+65 9000 0008'
        ),
        jsonb_build_object(
            'id', v_coordinator_lead_2_id,
            'email', 'coordinator.lead2@connectsphere.dev',
            'full_name', 'Daniel Foo',
            'role', 'event_coordinator_lead',
            'organisation_name', null,
            'department', 'Event Planning',
            'phone_number', '+65 9000 0009'
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
     'Seed Innovation Event', 'Venue search fixture', '2026-10-10 14:00+08', '2026-10-10 17:00+08', 60, 'classroom'),
    -- The venue-staff dashboard fixtures' events (bookings d…0004 and d…0005 below;
    -- DEFECTS D38): without them those bookings fail their event foreign key.
    ('e0000000-0000-4000-8000-000000000104', 'a0000000-0000-4000-8000-000000000001', 'planning',
     'Seed Terrace Event', 'Venue staff dashboard fixture', '2026-10-13 09:00+08', '2026-10-13 12:00+08', 80, 'reception'),
    ('e0000000-0000-4000-8000-000000000105', 'a0000000-0000-4000-8000-000000000001', 'planning',
     'Seed Boardroom Event', 'Venue staff dashboard fixture', '2026-10-12 09:00+08', '2026-10-12 12:00+08', 10, 'boardroom')
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
     'Restored shophouse hall.')
on conflict (name) do nothing;

-- An inactive venue needs a reason (SCRUM-64, venues_inactive_reason_consistent;
-- DEFECTS D38). The values match the shared project, where this row was given
-- them by hand when the constraint arrived.
insert into public.venues (id, name, location, capacity, accessibility_features, opens_at, closes_at, is_active,
                           inactive_reason, inactive_note, description)
values
    ('b0000000-0000-4000-8000-000000000008', 'Old Lecture Theatre', 'Bukit Timah Campus, Block C', 300,
     '{}', '08:00', '22:00', false, 'other', 'Deactivated before reasons were recorded',
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

-- CR-98: every event has at least one space requirement. 20261008100000 backfilled a
-- "Main space" from each existing event's requirements, but on a fresh database it
-- runs before the seed creates any events (DEFECTS D38). Do the same here, before
-- the bookings below link to it, or the booking trigger creates a bare "Main space" without the
-- event's attendance, layout and facilities. Idempotent: skips events that have one.
insert into public.event_space_requests (
    event_id, label, expected_pax, layout_preference, facilities_required, starts_at, ends_at
)
select e.id, 'Main space', e.expected_attendance, e.layout_preference,
       e.facilities_required, e.starts_at, e.ends_at
from public.events e
where e.id in (
    'e0000000-0000-4000-8000-000000000101',
    'e0000000-0000-4000-8000-000000000102',
    'e0000000-0000-4000-8000-000000000103',
    'e0000000-0000-4000-8000-000000000104',
    'e0000000-0000-4000-8000-000000000105'
)
  and not exists (select 1 from public.event_space_requests es where es.event_id = e.id);

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
-- Equipment availability fixtures
-- These records support local API checks for overlapping reservations and
-- maintenance windows. Example test window: 2026-10-15 09:00-17:00 UTC.
-- =============================================================================

truncate table
    public.equipment_reservations,
    public.equipment_unavailability,
    public.equipment
restart identity cascade;

insert into public.equipment (
    id,
    name,
    equipment_type,
    description,
    total_quantity,
    status,
    specifications
)
values
    (
        'b0000000-0000-4000-8000-000000000001',
        '4K Projector',
        'projector',
        'High-brightness 4K laser projector for conference halls and auditoriums.',
        14,
        'active',
        '{"resolution": "3840x2160", "brightness_lumens": 7000}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-000000000002',
        'Wireless Mics',
        'microphone',
        'Digital handheld wireless microphones with receivers.',
        24,
        'active',
        '{"channels": 2, "frequency_band": "UHF"}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-000000000003',
        'PA Systems',
        'audio',
        'Portable public-address speaker systems with mixers and stands.',
        10,
        'active',
        '{"power_watts": 2000, "includes_mixer": true}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-000000000004',
        'Stage Lighting',
        'lighting',
        'LED stage-lighting kits for presentations, performances, and ceremonies.',
        16,
        'active',
        '{"fixture_type": "LED", "control": "DMX"}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-000000000005',
        'HDMI Switchers',
        'video',
        'Multi-input HDMI switchers for hybrid event production.',
        12,
        'active',
        '{"inputs": 4, "outputs": 2, "max_resolution": "4K60"}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-000000000006',
        'Sound System',
        'audio',
        'Full sound system: line-array speakers, subwoofers and a digital mixing console.',
        10,
        'active',
        '{"power_watts": 6000, "mixer_channels": 16}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-000000000007',
        'Speaker Stands',
        'audio',
        'Adjustable tripod stands for PA and full-range speakers.',
        22,
        'active',
        '{"max_height_m": 2.1, "max_load_kg": 50}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-000000000008',
        'Whiteboards',
        'presentation',
        'Mobile double-sided whiteboards on lockable wheels, with markers and erasers.',
        18,
        'active',
        '{"width_cm": 180, "height_cm": 90, "double_sided": true}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-000000000009',
        'Flip Chart Stands',
        'presentation',
        'Easel flip chart stands with paper pads for workshops and breakouts.',
        12,
        'active',
        '{"pad_size": "A1"}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-00000000000a',
        'Projector Screens',
        'projector',
        'Portable tripod projection screens, 16:9.',
        13,
        'active',
        '{"diagonal_inches": 120, "aspect_ratio": "16:9"}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-00000000000b',
        'Lecterns',
        'staging',
        'Standing lecterns with a gooseneck microphone mount.',
        11,
        'active',
        '{"height_cm": 115, "mic_mount": true}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-00000000000c',
        'Extension Cords',
        'power',
        'Heavy-duty extension cords with Singapore Type G plugs.',
        40,
        'active',
        '{"length_m": 10, "outlets": 4, "plug": "Type G"}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-00000000000d',
        'Presentation Laptops',
        'computer',
        'Laptops preloaded with presentation software, with HDMI and USB-C adapters.',
        15,
        'active',
        '{"os": "Windows 11", "ports": ["HDMI", "USB-C"]}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-00000000000e',
        'Wireless Presenters',
        'presentation',
        'Wireless slide clickers with laser pointers.',
        20,
        'active',
        '{"range_m": 30, "laser": true}'::jsonb
    );

insert into public.equipment_unavailability (
    id,
    equipment_id,
    quantity,
    start_at,
    end_at,
    reason
)
values
    (
        'b1000000-0000-4000-8000-000000000001',
        'b0000000-0000-4000-8000-000000000001',
        1,
        '2026-10-15 12:00:00+00',
        '2026-10-15 18:00:00+00',
        'Scheduled maintenance and lens calibration'
    ),
    (
        'b1000000-0000-4000-8000-000000000002',
        'b0000000-0000-4000-8000-000000000003',
        1,
        '2026-10-15 08:00:00+00',
        '2026-10-15 13:00:00+00',
        'Amplifier inspection and battery replacement'
    );

insert into public.equipment_reservations (
    id,
    equipment_id,
    event_id,
    quantity,
    start_at,
    end_at,
    status,
    notes
)
values
    (
        'b2000000-0000-4000-8000-000000000001',
        'b0000000-0000-4000-8000-000000000001',
        'c0000000-0000-4000-8000-000000000001',
        2,
        '2026-10-15 09:00:00+00',
        '2026-10-15 17:00:00+00',
        'confirmed',
        'Conference A main hall projection'
    ),
    (
        'b2000000-0000-4000-8000-000000000002',
        'b0000000-0000-4000-8000-000000000002',
        'c0000000-0000-4000-8000-000000000002',
        8,
        '2026-10-15 10:00:00+00',
        '2026-10-15 14:00:00+00',
        'confirmed',
        'Panel discussion microphones'
    ),
    (
        'b2000000-0000-4000-8000-000000000003',
        'b0000000-0000-4000-8000-000000000003',
        'c0000000-0000-4000-8000-000000000003',
        2,
        '2026-10-15 14:00:00+00',
        '2026-10-15 20:00:00+00',
        'confirmed',
        'Evening awards ceremony audio'
    );

-- =============================================================================
-- SCRUM-34 / SCRUM-52: requests assigned to Marcus Lim (coordinator) so approve
-- and reject can be exercised before SCRUM-12's auto-assignment exists. 0202 is
-- in planning with a held booking, to show rejection releasing it (QA2-13).
-- =============================================================================

insert into public.events (
    id, organiser_id, coordinator_id, status, name, purpose, starts_at, ends_at,
    expected_attendance, layout_preference, submitted_at
)
values
    ('e0000000-0000-4000-8000-000000000201', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'under_review', 'Review Fixture: Partner Summit',
     'Approve/reject fixture', '2037-11-12 10:00+08', '2037-11-12 12:00+08', 12, 'boardroom', now()),
    ('e0000000-0000-4000-8000-000000000202', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Review Fixture: Year-End Dinner',
     'Approve/reject fixture', '2037-11-13 10:00+08', '2037-11-13 12:00+08', 12, 'boardroom', now())
on conflict (id) do nothing;

-- CR-98: every event has at least one space requirement. 20261008100000 backfilled a
-- "Main space" from each existing event's requirements, but on a fresh database it
-- runs before the seed creates any events (DEFECTS D38). Do the same here, before
-- the held booking below links to it, or the booking trigger creates a bare "Main space" without the
-- event's attendance, layout and facilities. Idempotent: skips events that have one.
insert into public.event_space_requests (
    event_id, label, expected_pax, layout_preference, facilities_required, starts_at, ends_at
)
select e.id, 'Main space', e.expected_attendance, e.layout_preference,
       e.facilities_required, e.starts_at, e.ends_at
from public.events e
where e.id in (
    'e0000000-0000-4000-8000-000000000201',
    'e0000000-0000-4000-8000-000000000202'
)
  and not exists (select 1 from public.event_space_requests es where es.event_id = e.id);

-- CR-99: holds expire. This one is held until its event starts, not the 7-day
-- default, so the fixture (and TC-BOOK-004, which relies on it) doesn't expire
-- a week after seeding.
insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, created_at, expires_at)
values
    ('d0000000-0000-4000-8000-000000000201', 'e0000000-0000-4000-8000-000000000202',
     'b0000000-0000-4000-8000-000000000004', tstzrange('2037-11-13 10:00+08', '2037-11-13 12:00+08', '[)'),
     'held', now(), '2037-11-13 10:00+08')
on conflict (id) do nothing;
