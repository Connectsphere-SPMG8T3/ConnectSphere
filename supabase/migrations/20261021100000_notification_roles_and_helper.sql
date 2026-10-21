-- =============================================================================
-- ConnectSphere - SCRUM-113 In-app notifications: who a notification is for
--
-- 113 AC4: a user sees only the notifications addressed to them in their
-- ACTIVE role. `notifications` had no role, and about 30 functions already
-- insert rows directly, so:
--
-- 1. `notification_types` lists every type and the role(s) it goes to.
-- 2. A BEFORE INSERT trigger stamps `recipient_role` from that list, so no
--    existing function has to change. A new story only registers its type.
-- 3. `public.add_notification` is the one-row helper for new code: it keeps
--    NT-R1 (the actor is never told of their own action) and can dedupe, which
--    the scheduled reminders rely on.
--
-- A type that is not registered, or a recipient who holds none of its roles,
-- leaves `recipient_role` null. The API never shows such a row (fail closed).
-- =============================================================================

alter table public.notifications
    add column recipient_role public.user_role null,
    add column dedupe_key text null;

comment on column public.notifications.recipient_role is
    'The role the notification is addressed to (113 AC4). Stamped by trigger from notification_types; null means the type is unregistered or the recipient holds none of its roles, and the API never shows it.';
comment on column public.notifications.dedupe_key is
    'Optional idempotency key: one row per (recipient_id, dedupe_key). Used by scheduled reminders so a re-run never sends twice.';

create unique index notifications_dedupe_key_uidx
    on public.notifications (recipient_id, dedupe_key)
    where dedupe_key is not null;

-- The bell asks "this recipient, this role, unread, newest first".
create index notifications_recipient_role_unread_idx
    on public.notifications (recipient_id, recipient_role, read_at, created_at desc, id);

-- 1. The registry ------------------------------------------------------------------
create table public.notification_types (
    type text primary key,
    recipient_roles public.user_role[] not null,
    constraint notification_types_type_not_blank check (length(btrim(type)) > 0),
    constraint notification_types_roles_not_empty check (cardinality(recipient_roles) > 0)
);

comment on table public.notification_types is
    'Every notification type and the role(s) it is addressed to (113 AC4, REQUIREMENTS 6.20). Register a new type here in the migration that first inserts it. When a type can go to two roles, the recipient''s link to the event decides: the event''s own organiser or coordinator takes that role; otherwise the first other role they hold, in list order.';

alter table public.notification_types enable row level security;
-- No policy on purpose: the API reads it with the secret key; nobody else needs it.

insert into public.notification_types (type, recipient_roles) values
    ('comment_added',                     '{event_organiser,event_coordinator}'),
    ('equipment_not_available',           '{event_coordinator}'),
    ('equipment_note',                    '{event_coordinator}'),
    ('equipment_re_review',               '{event_coordinator}'),
    ('equipment_reserved',                '{event_coordinator}'),
    ('event_approved',                    '{event_organiser}'),
    ('event_assigned',                    '{event_coordinator}'),
    ('event_coordinator_changed',         '{event_organiser}'),
    ('event_reassigned',                  '{event_coordinator}'),
    ('event_rejected',                    '{event_organiser}'),
    ('event_resubmitted',                 '{event_coordinator}'),
    ('event_returned',                    '{event_organiser}'),
    ('event_returned_to_planning',        '{event_coordinator,safety_officer}'),
    ('event_safety_approved',             '{event_organiser,event_coordinator,venue_staff,tech_support}'),
    ('event_safety_arrangement_rejected', '{event_coordinator}'),
    ('event_safety_changes_requested',    '{event_coordinator}'),
    ('event_sent_for_safety_check',       '{event_organiser,safety_officer}'),
    ('venue_booking_affected',            '{event_coordinator}'),
    ('venue_booking_approved',            '{event_coordinator}'),
    ('venue_booking_rejected',            '{event_coordinator}'),
    ('venue_booking_requested',           '{venue_staff}'),
    ('venue_booking_restored',            '{event_coordinator}'),
    ('venue_hold_expired',                '{event_coordinator}'),
    ('venue_hold_expiring',               '{event_coordinator}'),
    ('venue_unavailable_organiser',       '{event_organiser}'),
    ('venue_updated_affects_booking',     '{event_coordinator,venue_staff}');

-- 2. Resolve the role, then stamp it ------------------------------------------------
-- Among the type's roles the recipient holds: the organiser or coordinator role
-- the recipient has on THIS event first, then roles that need no link to the
-- event (venue staff, tech support, safety officer, attendee), then an organiser
-- or coordinator role they hold but have no link to here. Ties go in list order.
-- Known limit: a person who is both the organiser and the coordinator of one
-- event, and receives a type listed for both, is stamped with the first listed.
create or replace function private.resolve_notification_role(
    p_recipient uuid,
    p_event uuid,
    p_type text
)
returns public.user_role
language sql
stable
security definer
set search_path = ''
as $$
    select o.role
      from public.notification_types nt
     cross join lateral unnest(nt.recipient_roles) with ordinality as o(role, ord)
      left join public.events e on e.id = p_event
     where nt.type = p_type
       and (
           exists (select 1 from public.user_roles ur
                    where ur.profile_id = p_recipient and ur.role = o.role)
           or exists (select 1 from public.profiles p
                       where p.id = p_recipient and p.role = o.role)
       )
     order by
        case
            when o.role = 'event_organiser' and e.organiser_id = p_recipient then 0
            when o.role = 'event_coordinator' and e.coordinator_id = p_recipient then 0
            when o.role in ('event_organiser', 'event_coordinator') then 2
            else 1
        end,
        o.ord
     limit 1;
$$;

revoke execute on function private.resolve_notification_role(uuid, uuid, text) from public, anon, authenticated;

create or replace function private.set_notification_role()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if new.recipient_role is null then
        new.recipient_role := private.resolve_notification_role(new.recipient_id, new.event_id, new.type);
    end if;
    return new;
end;
$$;

revoke execute on function private.set_notification_role() from public, anon, authenticated;

create trigger notifications_set_recipient_role
    before insert on public.notifications
    for each row execute function private.set_notification_role();

-- Rows written before this migration.
update public.notifications n
   set recipient_role = private.resolve_notification_role(n.recipient_id, n.event_id, n.type)
 where n.recipient_role is null;

-- The RLS safety net follows the API: a user reads their own notifications
-- addressed to the role the session is acting as (SCRUM-76), not every role they
-- hold. A row with no role is read by nobody.
drop policy "notifications_select_own" on public.notifications;
create policy "notifications_select_own_in_active_role"
    on public.notifications
    for select
    to authenticated
    using (
        recipient_id = (select auth.uid())
        and recipient_role = (select private.current_user_role())
    );

-- 3. The helper for new code --------------------------------------------------------
create or replace function public.add_notification(
    p_recipient uuid,
    p_event uuid,
    p_type text,
    p_message text,
    p_actor uuid default null,
    p_dedupe_key text default null
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_id uuid;
begin
    -- NT-R1: the actor is never notified of their own action.
    if p_recipient is null or p_recipient is not distinct from p_actor then
        return null;
    end if;

    insert into public.notifications (recipient_id, event_id, type, message, dedupe_key)
    values (p_recipient, p_event, p_type, p_message, p_dedupe_key)
    on conflict (recipient_id, dedupe_key) where dedupe_key is not null do nothing
    returning id into v_id;

    return v_id;
end;
$$;

comment on function public.add_notification is
    'Inserts one notification for p_recipient and returns its id. Returns null, inserting nothing, when the recipient is the actor (NT-R1) or the dedupe key was already used for that recipient. The role is stamped by trigger. API-only.';

revoke execute on function public.add_notification(uuid, uuid, text, text, uuid, text)
    from public, anon, authenticated;
grant execute on function public.add_notification(uuid, uuid, text, text, uuid, text)
    to service_role;
