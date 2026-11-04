-- SCRUM-68 AC2: complete confirmed events once their end time has passed.
-- The lifecycle function keeps the status history and related closed-event
-- behavior in the same transaction. The database job runs hourly (LC-R6).

create index if not exists events_due_completion_idx
    on public.events (ends_at, id)
    where status in ('confirmed', 'preparation');

create or replace function public.complete_due_events(p_now timestamptz default now())
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_completed public.events;
    v_count integer := 0;
begin
    for v_event in
        select *
          from public.events
         where status in ('confirmed', 'preparation')
           and ends_at <= p_now
         order by ends_at, id
         for update skip locked
    loop
        select *
          into v_completed
          from public.transition_event(
              v_event.id,
              null,
              array[v_event.status::text],
              'completed',
              v_event.version,
              'Event date/time passed'
          );
        if found then
            v_count := v_count + 1;
        end if;
    end loop;

    return v_count;
end;
$$;

comment on function public.complete_due_events(timestamptz) is
    'SCRUM-68 AC2 / LC-R6: completes Confirmed and Preparation events whose end time has passed, through transition_event so history and closed-event rules remain atomic. Runs hourly by pg_cron.';

revoke execute on function public.complete_due_events(timestamptz) from public, anon, authenticated;
grant execute on function public.complete_due_events(timestamptz) to service_role;

create extension if not exists pg_cron with schema pg_catalog;

select cron.schedule(
    'complete-due-events',
    '0 * * * *',
    'select public.complete_due_events()'
);
