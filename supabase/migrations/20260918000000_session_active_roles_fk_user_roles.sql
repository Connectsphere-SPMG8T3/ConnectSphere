-- =============================================================================
-- ConnectSphere — code review follow-up (SCRUM-74/75): close a revocation
-- bypass on session_active_roles.
-- =============================================================================

-- Without this, deleting a role from user_roles (a system admin revoking it
-- via direct SQL) leaves any session currently acting as that role
-- unaffected until it expires or logs out, since session_active_roles had no
-- link back to user_roles to cascade through. user_roles' primary key is
-- already (profile_id, role), so it's a valid composite FK target.
alter table public.session_active_roles
    add constraint session_active_roles_profile_role_fkey
    foreign key (profile_id, role) references public.user_roles (profile_id, role)
    on delete cascade;

-- The new composite FK needs a covering index (lint 0001); it also covers
-- the plain profile_id lookups the old single-column index served, which is
-- dropped as redundant.
drop index if exists public.session_active_roles_profile_id_idx;
create index session_active_roles_profile_id_role_idx
    on public.session_active_roles using btree (profile_id, role);
