-- =============================================================================
-- ConnectSphere — SCRUM-63: update venue capacity and facilities information
--
-- venues.version: optimistic concurrency (DB-5), the same pattern as
-- events.version — "the only pattern so far, copy it rather than inventing a
-- second scheme" (docs/IMPLEMENTATION_MAP.md).
-- venue_edit_history: VC-R3 ("every edit is recorded in history"), scoped to
-- venues only. The generic change_history table (REQUIREMENTS §6.7) is
-- SCRUM-62 and unbuilt, so this is a small venue-specific table rather than
-- building that generic shape ahead of its own story.
-- update_venue: one transaction for the version-checked update, the
-- venue_layouts/venue_facilities replace, the history row, and the
-- notifications VC-R2 asks for when an edit newly affects an upcoming
-- booking — same shape as transition_event (events module).
-- =============================================================================

alter table public.venues add column version integer not null default 0;

comment on column public.venues.version is
    'Optimistic concurrency (DB-5): an edit reads this, then writes conditioned on it being unchanged (SCRUM-63).';

create table public.venue_edit_history (
    id uuid primary key default gen_random_uuid(),
    venue_id uuid not null references public.venues (id) on delete cascade,
    actor_id uuid null references public.profiles (id) on delete set null,
    before jsonb not null,
    after jsonb not null,
    created_at timestamptz not null default now()
);

comment on table public.venue_edit_history is
    'Append-only record of every saved venue edit (VC-R3). Written only by public.update_venue.';

create index venue_edit_history_venue_created_idx on public.venue_edit_history (venue_id, created_at desc);
create index venue_edit_history_actor_id_idx on public.venue_edit_history (actor_id);

alter table public.venue_edit_history enable row level security;

-- Safety net only: the API uses the secret key. Same readers as the venue
-- catalogue itself (SCRUM-39's venues_select_internal_staff).
create policy "venue_edit_history_select_internal_staff"
    on public.venue_edit_history for select to authenticated
    using ((select private.current_user_role()) in ('event_coordinator', 'venue_staff', 'tech_support'));

create or replace function public.update_venue(
    p_venue_id uuid,
    p_actor_id uuid,
    p_expected_version integer,
    p_name varchar,
    p_location varchar,
    p_capacity integer,
    p_opens_at time,
    p_closes_at time,
    p_description text,
    p_accessibility_features public.accessibility_feature[],
    p_layouts jsonb,
    p_facilities public.facility[],
    p_before jsonb,
    p_after jsonb,
    p_notifications jsonb default '[]'::jsonb
)
returns setof public.venues
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_after public.venues;
    v_notification jsonb;
begin
    update public.venues
       set name = p_name,
           location = p_location,
           capacity = p_capacity,
           opens_at = p_opens_at,
           closes_at = p_closes_at,
           description = p_description,
           accessibility_features = p_accessibility_features,
           version = version + 1,
           updated_by = p_actor_id
     where id = p_venue_id
       and version = p_expected_version
    returning * into v_after;

    if not found then
        return;
    end if;

    delete from public.venue_layouts where venue_id = p_venue_id;
    insert into public.venue_layouts (venue_id, layout, capacity_for_layout)
    select p_venue_id, (elem ->> 'layout')::public.venue_layout, (elem ->> 'capacity_for_layout')::integer
      from jsonb_array_elements(p_layouts) as elem;

    delete from public.venue_facilities where venue_id = p_venue_id;
    insert into public.venue_facilities (venue_id, facility)
    select p_venue_id, unnest(p_facilities)
     where p_facilities is not null and array_length(p_facilities, 1) > 0;

    insert into public.venue_edit_history (venue_id, actor_id, before, after)
    values (p_venue_id, p_actor_id, p_before, p_after);

    for v_notification in select * from jsonb_array_elements(p_notifications)
    loop
        insert into public.notifications (recipient_id, event_id, type, message)
        values (
            (v_notification ->> 'recipient_id')::uuid,
            (v_notification ->> 'event_id')::uuid,
            'venue_updated_affects_booking',
            v_notification ->> 'message'
        );
    end loop;

    return next v_after;
end;
$$;

comment on function public.update_venue is
    'Atomically saves a venue edit: version-checked update, layouts/facilities replace, history row, and notifications for any newly-affected booking (VC-R2, VC-R3). API-only.';

revoke execute on function public.update_venue(
    uuid, uuid, integer, varchar, varchar, integer, time, time, text,
    public.accessibility_feature[], jsonb, public.facility[], jsonb, jsonb, jsonb
) from public, anon, authenticated;
grant execute on function public.update_venue(
    uuid, uuid, integer, varchar, varchar, integer, time, time, text,
    public.accessibility_feature[], jsonb, public.facility[], jsonb, jsonb, jsonb
) to service_role;
