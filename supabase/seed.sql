-- =============================================================================
-- ConnectSphere — local/dev seed data
-- Creates one confirmed test account per user role directly in auth.users /
-- auth.identities. public.profiles rows are populated automatically by the
-- on_auth_user_created trigger from raw_user_meta_data.
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
    end loop;
end $$;
