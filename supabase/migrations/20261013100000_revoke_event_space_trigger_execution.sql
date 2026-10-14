-- CR-98 security follow-up: trigger functions are invoked by their triggers,
-- not through PostgREST RPC. Prevent direct calls to these SECURITY DEFINER
-- functions by untrusted API roles.

revoke execute on function public.populate_booking_space_request()
    from public, anon, authenticated;
revoke execute on function public.sync_event_space_periods()
    from public, anon, authenticated;