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
    end loop;
end $$;

-- =============================================================================
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
        4,
        'active',
        '{"resolution": "3840x2160", "brightness_lumens": 7000}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-000000000002',
        'Wireless Mics',
        'microphone',
        'Digital handheld wireless microphones with receivers.',
        12,
        'active',
        '{"channels": 2, "frequency_band": "UHF"}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-000000000003',
        'PA Systems',
        'audio',
        'Portable public-address speaker systems with mixers and stands.',
        3,
        'active',
        '{"power_watts": 2000, "includes_mixer": true}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-000000000004',
        'Stage Lighting',
        'lighting',
        'LED stage-lighting kits for presentations, performances, and ceremonies.',
        8,
        'active',
        '{"fixture_type": "LED", "control": "DMX"}'::jsonb
    ),
    (
        'b0000000-0000-4000-8000-000000000005',
        'HDMI Switchers',
        'video',
        'Multi-input HDMI switchers for hybrid event production.',
        6,
        'active',
        '{"inputs": 4, "outputs": 2, "max_resolution": "4K60"}'::jsonb
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
