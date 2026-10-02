-- =============================================================================
-- ConnectSphere - SCRUM-61 comment and discuss on an event
--
-- event_comments: the organiser-coordinator discussion thread kept with the
-- event record (REQUIREMENTS 8; QA2-27). Append-only. add_event_comment writes
-- the comment and notifies the other party in one transaction (NT-R3).
-- API-only (ADR-0002): the API checks role and relationship before calling.
-- =============================================================================

create table public.event_comments (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null,
    author_id uuid null,
    body text not null,
    created_at timestamptz not null default now(),
    constraint event_comments_event_id_fkey
        foreign key (event_id) references public.events (id) on delete cascade,
    constraint event_comments_author_id_fkey
        foreign key (author_id) references public.profiles (id) on delete set null,
    constraint event_comments_body_length check (length(btrim(body)) between 1 and 1000)
);

comment on table public.event_comments is
    'Discussion thread on an event between its organiser and assigned coordinator (SCRUM-61). Append-only; written only by add_event_comment.';

create index event_comments_event_created_at_idx on public.event_comments (event_id, created_at);
create index event_comments_author_id_idx on public.event_comments (author_id);

alter table public.event_comments enable row level security;

-- Safety net only: the API uses the secret key. Same readers as event_status_history.
create policy "event_comments_select_owner_or_assigned_coordinator"
    on public.event_comments
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.events e
            where e.id = event_comments.event_id
              and (
                  (e.organiser_id = (select auth.uid())
                   and (select private.current_user_role()) = 'event_organiser')
                  or (e.coordinator_id = (select auth.uid())
                      and (select private.current_user_role()) = 'event_coordinator')
              )
        )
    );

create or replace function public.add_event_comment(
    p_event_id uuid,
    p_author_id uuid,
    p_body text,
    p_notify_message text
)
returns setof public.event_comments
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_comment public.event_comments;
    v_recipient uuid;
begin
    -- Lock the event so a concurrent close can't slip between the check and the insert.
    select * into v_event from public.events where id = p_event_id for update;
    if not found
       or v_event.status not in ('submitted', 'under_review', 'returned', 'planning', 'confirmed') then
        return;
    end if;

    insert into public.event_comments (event_id, author_id, body)
    values (p_event_id, p_author_id, btrim(p_body))
    returning * into v_comment;

    v_recipient := case
        when p_author_id = v_event.organiser_id then v_event.coordinator_id
        else v_event.organiser_id
    end;
    if v_recipient is not null and v_recipient is distinct from p_author_id then
        insert into public.notifications (recipient_id, event_id, type, message)
        values (v_recipient, p_event_id, 'comment_added', p_notify_message);
    end if;

    return next v_comment;
end;
$$;

comment on function public.add_event_comment is
    'Adds a comment to an open (submitted to confirmed) event and notifies the other party, atomically. No row for a missing, draft or closed event. API-only.';

revoke execute on function public.add_event_comment(uuid, uuid, text, text) from public, anon, authenticated;
grant execute on function public.add_event_comment(uuid, uuid, text, text) to service_role;
