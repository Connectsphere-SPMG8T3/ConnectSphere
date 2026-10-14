-- QA3-23 / CR-98 AC3: spaces may override the event period. A null pair means
-- the space inherits the event's current schedule at venue-search/booking time.

DROP TRIGGER IF EXISTS events_sync_space_periods ON public.events;

UPDATE public.event_space_requests AS es
SET starts_at = NULL,
    ends_at = NULL
FROM public.events AS e
WHERE es.event_id = e.id
  AND es.starts_at IS NOT DISTINCT FROM e.starts_at
  AND es.ends_at IS NOT DISTINCT FROM e.ends_at
  AND (es.starts_at IS NOT NULL OR es.ends_at IS NOT NULL);

COMMENT ON COLUMN public.event_space_requests.starts_at IS
  'Optional explicit start for this space. A null pair inherits the event period.';
COMMENT ON COLUMN public.event_space_requests.ends_at IS
  'Optional explicit end for this space. A null pair inherits the event period.';