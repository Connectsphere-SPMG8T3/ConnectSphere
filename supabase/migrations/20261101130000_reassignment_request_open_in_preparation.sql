-- =============================================================================
-- ConnectSphere - CR-106 follow-up: a request stays open in Preparation
--
-- 20261029120000 closed an open reassignment request when its event moved to
-- Preparation, on the reading that Preparation was no longer reassignable. CR-110
-- (QA3-3, D73) since made Preparation an active coordinator status: the Lead's
-- dashboard lists it, `reassign_event` accepts it, and the API now takes a request
-- from it. Closing the request on entering Preparation would therefore answer it for
-- no reason, so the trigger now closes it only when the event is rejected, cancelled
-- or completed, the statuses nobody can reassign from.
--
-- Same function, same trigger name; only the trigger's condition and the function's
-- comment change. API-only (ADR-0006).
-- =============================================================================

drop trigger events_close_reassignment_request_when_unreassignable on public.events;

create trigger events_close_reassignment_request_when_unreassignable
    after update of status on public.events
    for each row
    when (new.status is distinct from old.status
          and new.status in ('rejected', 'cancelled', 'completed'))
    execute function private.close_reassignment_request_on_unreassignable_event();

comment on function private.close_reassignment_request_on_unreassignable_event is
    'CR-106: trigger on events; when an event becomes rejected, cancelled or completed, its open reassignment request is superseded. An event in Preparation is still reassignable (QA3-3, D73), so it keeps its request. Trigger-only.';
