-- =============================================================================
-- ConnectSphere - SCRUM-51 AC1: "equipment failure" is a block reason
--
-- On its own because a new enum value can't be used in the transaction that
-- adds it; 20261019100001 builds on it.
-- =============================================================================

alter type public.venue_block_reason add value if not exists 'equipment_failure' after 'maintenance';
