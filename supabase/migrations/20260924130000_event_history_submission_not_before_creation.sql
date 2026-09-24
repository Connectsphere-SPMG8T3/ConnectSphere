-- =============================================================================
-- ConnectSphere - correct backfilled submission times (fix/event-history-on-create)
--
-- 20260924120000 backfilled each submission row from events.submitted_at. Before
-- that migration, submitted_at came from the API server's clock while
-- created_at comes from the database's, so a skewed server clock could put
-- submission before creation and list the history out of order. transition_event
-- now stamps submitted_at with the database's now(), so only backfilled rows
-- can be affected. events.submitted_at itself is left as recorded.
-- =============================================================================

update public.event_status_history h
   set at = e.created_at
  from public.events e
 where e.id = h.event_id
   and h.from_status = 'draft'
   and h.to_status = 'under_review'
   and h.at < e.created_at;
