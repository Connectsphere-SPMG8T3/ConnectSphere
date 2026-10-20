-- SCRUM-113 notification roles: the BEFORE INSERT trigger that stamps each
-- notification with the role it is addressed to, the type registry, and
-- public.add_notification. Run with the Supabase MCP execute_sql or
-- `psql "$DATABASE_URL" -f`. Raises on the first failure and prints
-- NOTIFICATION ROLE CHECKS PASSED otherwise. Everything runs inside
-- `begin; ... rollback;`, so the throwaway events and rows leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002, who also holds
-- venue_staff) and venue staff (…0003).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name) values
    ('e0000000-0000-4000-8000-0000000007a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Role check, coordinator 0002 (rolled back)'),
    ('e0000000-0000-4000-8000-0000000007a2', 'a0000000-0000-4000-8000-000000000001',
     null, 'planning', 'Role check, no coordinator (rolled back)');

do $$
declare
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_venue_staff uuid := 'a0000000-0000-4000-8000-000000000003';
    v_event uuid := 'e0000000-0000-4000-8000-0000000007a1';
    v_other_event uuid := 'e0000000-0000-4000-8000-0000000007a2';
    v_role public.user_role;
    v_id uuid;
    v_missing text;
begin
    -- 1. The trigger stamps the role from the registry.
    insert into public.notifications (recipient_id, event_id, type, message)
    values (v_coordinator, v_event, 'event_assigned', 'x');
    select recipient_role into v_role from public.notifications
     where recipient_id = v_coordinator and event_id = v_event and type = 'event_assigned';
    if v_role is distinct from 'event_coordinator' then
        raise exception 'ROLE FAIL: event_assigned was not stamped event_coordinator (got %)', v_role;
    end if;

    -- 2. An unregistered type stays null, so the API never shows it.
    insert into public.notifications (recipient_id, event_id, type, message)
    values (v_coordinator, v_event, 'zz_unregistered_type', 'x');
    if (select recipient_role from public.notifications where type = 'zz_unregistered_type') is not null then
        raise exception 'ROLE FAIL: an unregistered type must stay null';
    end if;

    -- 3. An explicit role is kept.
    insert into public.notifications (recipient_id, event_id, type, message, recipient_role)
    values (v_coordinator, v_event, 'event_assigned', 'explicit', 'venue_staff');
    if (select recipient_role from public.notifications where message = 'explicit') is distinct from 'venue_staff' then
        raise exception 'ROLE FAIL: an explicit recipient_role was overwritten';
    end if;

    -- 4. A type that can go to two roles resolves by the recipient's link to the event.
    --    0002 holds event_coordinator and venue_staff. On an event they coordinate, the
    --    notice is theirs as coordinator; on any other event it reaches them as venue staff.
    insert into public.notifications (recipient_id, event_id, type, message)
    values (v_coordinator, v_event, 'venue_updated_affects_booking', 'own event');
    insert into public.notifications (recipient_id, event_id, type, message)
    values (v_coordinator, v_other_event, 'venue_updated_affects_booking', 'other event');
    if (select recipient_role from public.notifications where message = 'own event') is distinct from 'event_coordinator' then
        raise exception 'ROLE FAIL: the event''s own coordinator was not stamped event_coordinator';
    end if;
    if (select recipient_role from public.notifications where message = 'other event') is distinct from 'venue_staff' then
        raise exception 'ROLE FAIL: a coordinator who is not on this event was not stamped venue_staff';
    end if;
    -- comment_added: the organiser's copy and the coordinator's copy.
    insert into public.notifications (recipient_id, event_id, type, message)
    values (v_organiser, v_event, 'comment_added', 'to organiser'),
           (v_coordinator, v_event, 'comment_added', 'to coordinator');
    if (select recipient_role from public.notifications where message = 'to organiser') is distinct from 'event_organiser'
       or (select recipient_role from public.notifications where message = 'to coordinator') is distinct from 'event_coordinator' then
        raise exception 'ROLE FAIL: comment_added did not resolve to the organiser and the coordinator';
    end if;

    -- 5. add_notification: NT-R1, dedupe and return values.
    if public.add_notification(v_organiser, v_event, 'event_coordinator_changed', 'm', v_organiser) is not null then
        raise exception 'ROLE FAIL: the actor was notified of their own action';
    end if;
    v_id := public.add_notification(v_organiser, v_event, 'event_coordinator_changed', 'm', v_coordinator, 'k1');
    if v_id is null then raise exception 'ROLE FAIL: add_notification returned null for a real recipient'; end if;
    if (select recipient_role from public.notifications where id = v_id) is distinct from 'event_organiser' then
        raise exception 'ROLE FAIL: add_notification rows are not stamped through the trigger';
    end if;
    if public.add_notification(v_organiser, v_event, 'event_coordinator_changed', 'm', v_coordinator, 'k1') is not null then
        raise exception 'ROLE FAIL: the same dedupe key inserted twice';
    end if;
    if public.add_notification(v_venue_staff, v_event, 'venue_booking_requested', 'm', v_coordinator, 'k1') is null then
        raise exception 'ROLE FAIL: a dedupe key is per recipient, a different recipient was blocked';
    end if;

    -- 6. Every type any existing function can raise is registered.
    select string_agg(t, ', ') into v_missing
      from unnest(array[
          'comment_added', 'equipment_not_available', 'equipment_note', 'equipment_re_review',
          'equipment_reserved', 'event_approved', 'event_assigned', 'event_coordinator_changed',
          'event_reassigned', 'event_rejected', 'event_resubmitted', 'event_returned',
          'event_returned_to_planning', 'event_safety_approved', 'event_safety_arrangement_rejected',
          'event_safety_changes_requested', 'event_sent_for_safety_check', 'venue_booking_affected',
          'venue_booking_approved', 'venue_booking_rejected', 'venue_booking_requested',
          'venue_booking_restored', 'venue_hold_expired', 'venue_hold_expiring',
          'venue_unavailable_organiser', 'venue_updated_affects_booking'
      ]) as t
     where not exists (select 1 from public.notification_types nt where nt.type = t);
    if v_missing is not null then
        raise exception 'ROLE FAIL: unregistered notification types: %', v_missing;
    end if;

    -- 7. The backfill left no registered-type row without a role.
    if exists (
        select 1 from public.notifications n
         join public.notification_types nt on nt.type = n.type
         where n.recipient_role is null
           and exists (select 1 from public.user_roles ur
                        where ur.profile_id = n.recipient_id and ur.role = any (nt.recipient_roles))
    ) then
        raise exception 'ROLE FAIL: a registered-type row still has no recipient_role';
    end if;

    -- 8. Grants: service_role only.
    if has_function_privilege('anon', 'public.add_notification(uuid, uuid, text, text, uuid, text)', 'execute')
       or has_function_privilege('authenticated', 'public.add_notification(uuid, uuid, text, text, uuid, text)', 'execute') then
        raise exception 'ROLE FAIL: add_notification is executable by anon or authenticated';
    end if;
    if not has_function_privilege('service_role', 'public.add_notification(uuid, uuid, text, text, uuid, text)', 'execute') then
        raise exception 'ROLE FAIL: add_notification is not executable by service_role';
    end if;

    raise notice 'NOTIFICATION ROLE CHECKS PASSED';
end $$;

select 'NOTIFICATION ROLE CHECKS PASSED' as result;

rollback;
