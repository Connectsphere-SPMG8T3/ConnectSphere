-- =============================================================================
-- ConnectSphere - SCRUM-8: allow registration to close through event end
-- =============================================================================

alter table public.events
    drop constraint events_registration_closes_before_event;

alter table public.events
    add constraint events_registration_closes_before_event_end check (
        registration_closes_at is null
        or ends_at is null
        or registration_closes_at <= ends_at
    );