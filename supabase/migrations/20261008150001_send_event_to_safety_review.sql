-- SCRUM-82: atomic history and organiser/officer notifications; API-only.
create or replace function public.send_event_to_safety_review(
 p_event_id uuid, p_actor_id uuid, p_from_statuses text[], p_to_status text,
 p_expected_version integer, p_organiser_message text, p_officer_message text
) returns setof public.events
language plpgsql security definer set search_path = ''
as $$
declare v_after public.events;
begin
 select * into v_after from public.transition_event(
  p_event_id, p_actor_id, p_from_statuses, p_to_status, p_expected_version,
  null, 'event_sent_for_safety_check', p_organiser_message);
 if not found then return; end if;
 -- Held roles, not the active one: a notification grants no access.
 -- Never notify the actor (NT-R1), who may also hold safety_officer.
 insert into public.notifications (recipient_id, event_id, type, message)
 select ur.profile_id, p_event_id, 'event_sent_for_safety_check', p_officer_message
 from public.user_roles ur where ur.role = 'safety_officer' and ur.profile_id <> p_actor_id;
 return next v_after;
end;
$$;
comment on function public.send_event_to_safety_review is
 'Sends a ready event for safety review: status, history and organiser/officer notifications atomically. API-only.';
revoke execute on function public.send_event_to_safety_review(uuid,uuid,text[],text,integer,text,text) from public, anon, authenticated;
grant execute on function public.send_event_to_safety_review(uuid,uuid,text[],text,integer,text,text) to service_role;

-- Live definition checked 2026-10-08. Only the status list changes.
-- Mirrors backend COMMENTABLE_STATUSES and frontend comments.js.
CREATE OR REPLACE FUNCTION public.add_event_comment(p_event_id uuid, p_author_id uuid, p_body text, p_notify_message text)
 RETURNS SETOF public.event_comments
 LANGUAGE plpgsql SECURITY DEFINER SET search_path TO ''
AS $function$
declare
    v_event public.events;
    v_comment public.event_comments;
    v_recipient uuid;
begin
    select * into v_event from public.events where id = p_event_id for update;
    if not found
       or v_event.status not in ('submitted', 'under_review', 'returned', 'planning', 'safety_review', 'confirmed') then
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
$function$;
