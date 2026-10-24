-- =============================================================================
-- ConnectSphere - Story 115 follow-up: an ended event closes its open
-- cancellation request
--
-- CR-R22 [Team decision]: an event that becomes rejected or completed closes its
-- open cancellation request as superseded, whatever moved it. Left open, the
-- coordinator still saw the request on a rejected event, approving it answered
-- 409 and rejecting it told the organiser their request was turned down. The
-- organiser already hears of the rejection itself, so nothing more is sent.
-- Cancelled is not covered: public.cancel_event closes the request as approved.
-- Trigger-only, like story 32's close_change_request_on_closed_event.
-- =============================================================================

create or replace function private.close_cancellation_request_on_ended_event()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.event_change_requests
       set status = 'superseded', decided_at = now(),
           decision_reason = format('Closed because the event was %s.', new.status)
     where event_id = new.id and kind = 'cancellation' and status = 'open';
    return null;
end;
$$;

comment on function private.close_cancellation_request_on_ended_event is
    'Story 115, CR-R22: trigger on events; when an event becomes rejected or completed, its open cancellation request is superseded. Trigger-only.';

revoke execute on function private.close_cancellation_request_on_ended_event() from public, anon, authenticated;

create trigger events_close_cancellation_request_when_ended
    after update of status on public.events
    for each row
    when (new.status is distinct from old.status
          and new.status in ('rejected', 'completed'))
    execute function private.close_cancellation_request_on_ended_event();
