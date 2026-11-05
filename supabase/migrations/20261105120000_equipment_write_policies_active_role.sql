-- =============================================================================
-- ConnectSphere — DEFECTS D19: equipment write policies follow the active role.
--
-- The write policies from 20260921150000 gated on the JWT's app_metadata role
-- claim. No account carries that claim, so direct writes were refused even for
-- tech support, while a token that did carry it was let through whatever role
-- the session was acting as. They now gate on private.current_user_role(), the
-- session's active role (SCRUM-76), like every other policy. Safety net only:
-- the API uses the secret key and checks require_roles itself.
-- Checked by supabase/verification/equipment_rls_checks.sql.
-- =============================================================================

drop policy if exists "equipment_insert_tech_support" on public.equipment;
drop policy if exists "equipment_update_tech_support" on public.equipment;
drop policy if exists "equipment_delete_tech_support" on public.equipment;
drop policy if exists "equipment_unavailability_insert_tech_support" on public.equipment_unavailability;
drop policy if exists "equipment_unavailability_update_tech_support" on public.equipment_unavailability;
drop policy if exists "equipment_unavailability_delete_tech_support" on public.equipment_unavailability;
drop policy if exists "equipment_reservations_insert_tech_support" on public.equipment_reservations;
drop policy if exists "equipment_reservations_update_tech_support" on public.equipment_reservations;
drop policy if exists "equipment_reservations_delete_tech_support" on public.equipment_reservations;

create policy "equipment_insert_tech_support"
    on public.equipment
    for insert
    to authenticated
    with check ((select private.current_user_role()) = 'tech_support');

create policy "equipment_update_tech_support"
    on public.equipment
    for update
    to authenticated
    using ((select private.current_user_role()) = 'tech_support')
    with check ((select private.current_user_role()) = 'tech_support');

create policy "equipment_delete_tech_support"
    on public.equipment
    for delete
    to authenticated
    using ((select private.current_user_role()) = 'tech_support');

create policy "equipment_unavailability_insert_tech_support"
    on public.equipment_unavailability
    for insert
    to authenticated
    with check ((select private.current_user_role()) = 'tech_support');

create policy "equipment_unavailability_update_tech_support"
    on public.equipment_unavailability
    for update
    to authenticated
    using ((select private.current_user_role()) = 'tech_support')
    with check ((select private.current_user_role()) = 'tech_support');

create policy "equipment_unavailability_delete_tech_support"
    on public.equipment_unavailability
    for delete
    to authenticated
    using ((select private.current_user_role()) = 'tech_support');

create policy "equipment_reservations_insert_tech_support"
    on public.equipment_reservations
    for insert
    to authenticated
    with check ((select private.current_user_role()) = 'tech_support');

create policy "equipment_reservations_update_tech_support"
    on public.equipment_reservations
    for update
    to authenticated
    using ((select private.current_user_role()) = 'tech_support')
    with check ((select private.current_user_role()) = 'tech_support');

create policy "equipment_reservations_delete_tech_support"
    on public.equipment_reservations
    for delete
    to authenticated
    using ((select private.current_user_role()) = 'tech_support');
