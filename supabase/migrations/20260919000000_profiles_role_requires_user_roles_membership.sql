-- =============================================================================
-- ConnectSphere — code review follow-up (SCRUM-74/75, round 2): close the
-- revocation gap for a never-switched session's default role.
-- =============================================================================

-- The FK added in 20260918000000 only invalidates an *actively switched*
-- session's session_active_roles row when its user_roles grant is revoked.
-- It does nothing for the common case — a session that never switched — since
-- resolve_active_role() falls back straight to profiles.role without
-- re-checking user_roles. A system admin revoking an account's default role
-- (delete from user_roles where profile_id=x and role=profiles.role) left
-- that role granted indefinitely for every un-switched session.
--
-- This FK makes profiles.role itself require a matching user_roles row.
-- DEFERRABLE INITIALLY DEFERRED so handle_new_user()'s same-transaction
-- inserts (profiles row, then its user_roles row) still validate correctly at
-- commit; NO ACTION (the default) on delete means deleting a user_roles row
-- that profiles.role currently points at is rejected unless the same
-- transaction first updates profiles.role to another role the account still
-- holds — the correct admin workflow for revoking someone's active default
-- role, enforced rather than merely documented.
alter table public.profiles
    add constraint profiles_role_requires_user_roles_membership_fkey
    foreign key (id, role) references public.user_roles (profile_id, role)
    deferrable initially deferred;

-- Covering index for this FK (lint 0001): Postgres needs it to efficiently
-- check, on every delete from user_roles, whether any profiles row still
-- references the (profile_id, role) pair being removed.
create index profiles_id_role_idx on public.profiles using btree (id, role);
