-- =============================================================================
-- ConnectSphere - CR-99: a hold that reaches its expiry becomes `expired`
--
-- Its own migration: Postgres can't use an enum value in the transaction that
-- added it, and 20261012120001 uses it. Like rejected, cancelled and released,
-- `expired` is left out of the occupying statuses, so DB-1
-- (venue_bookings_no_overlap) frees the venue without being changed (AC5).
-- =============================================================================

alter type public.venue_booking_status add value if not exists 'expired';
