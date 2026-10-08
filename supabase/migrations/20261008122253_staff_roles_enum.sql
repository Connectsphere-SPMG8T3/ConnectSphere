-- =============================================================================
-- ConnectSphere — 12 AC12 (Event Coordinator Lead) and CR-103 AC5 (Safety Officer):
-- add the two roles to public.user_role.
--
-- This file does nothing else, on purpose. Postgres will not let a newly added
-- enum value be used in the transaction that adds it, so no policy, function or
-- row here may mention the new roles. The existing staff access lists
-- (event_coordinator, venue_staff, tech_support) are left alone: each story that
-- needs the new roles grants them access itself, so nothing opens by accident.
-- handle_new_user() still accepts only event_organiser and attendee at sign-up.
-- Accounts holding these roles are granted by hand (docs/SETUP.md).
-- =============================================================================

alter type public.user_role add value if not exists 'event_coordinator_lead';
alter type public.user_role add value if not exists 'safety_officer';
