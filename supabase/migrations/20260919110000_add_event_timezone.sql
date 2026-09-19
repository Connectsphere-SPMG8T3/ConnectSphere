-- Event schedules are entered and displayed in the event's venue timezone.
-- Instants remain timestamptz values and are normalized by PostgreSQL.

alter table public.events
    add column event_timezone text not null default 'Asia/Singapore';

alter table public.events
    add constraint events_event_timezone_not_blank
    check (length(btrim(event_timezone)) > 0);

comment on column public.events.event_timezone is
    'IANA timezone used to interpret and display the event and registration schedule.';