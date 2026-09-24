-- Event history on creation and submission (fix/event-history-on-create).
-- Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`. Every row
-- should read `ok = true`. Everything runs inside `begin; ... rollback;`, so the
-- throwaway event, its history rows and the submission leave no trace.

begin;

create temporary table history_check (check_name text, ok boolean) on commit drop;

do $$
declare
    v_organiser uuid;
    v_event public.events;
    v_submitted public.events;
    v_rows integer;
begin
    select p.id into v_organiser
      from public.profiles p
      join public.user_roles ur on ur.profile_id = p.id and ur.role = 'event_organiser'
     limit 1;

    insert into public.events (organiser_id, name)
    values (v_organiser, 'History check (rolled back)')
    returning * into v_event;

    select count(*) into v_rows
      from public.event_status_history h
     where h.event_id = v_event.id
       and h.from_status is null
       and h.to_status = 'draft'
       and h.actor_id = v_organiser;
    insert into history_check values ('creating an event records (none -> draft) by its organiser', v_rows = 1);

    select * into v_submitted
      from public.transition_event(v_event.id, v_organiser, array['draft'], 'under_review', v_event.version);

    insert into history_check values ('submission moves the event to under_review', v_submitted.status = 'under_review');
    insert into history_check values ('submission stamps submitted_at', v_submitted.submitted_at is not null);

    select count(*) into v_rows
      from public.event_status_history h
     where h.event_id = v_event.id
       and h.from_status = 'draft'
       and h.to_status = 'under_review'
       and h.actor_id = v_organiser;
    insert into history_check values ('submission records (draft -> under_review) by its organiser', v_rows = 1);

    select count(*) into v_rows from public.notifications n where n.event_id = v_event.id;
    insert into history_check values ('the organiser is not notified of their own submission', v_rows = 0);

    select * into v_event
      from public.transition_event(v_event.id, v_organiser, array['under_review'], 'planning', v_submitted.version);
    insert into history_check values ('a later transition keeps the original submitted_at',
                                      v_event.submitted_at = v_submitted.submitted_at);
end;
$$;

select check_name as check, ok from history_check;

rollback;
