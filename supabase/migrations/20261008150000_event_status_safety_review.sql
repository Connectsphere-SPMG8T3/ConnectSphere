-- =============================================================================
-- ConnectSphere — SCRUM-82 / CR-104 groundwork (W7 CR-06): add safety_review to
-- public.event_status, between planning and confirmed.
--
-- This file does nothing else, on purpose. Postgres will not let a newly added
-- enum value be used in the transaction that adds it. public.transition_event
-- already takes its statuses as text, so the safety transitions in
-- events/lifecycle.py need no function change. Comment access, staff queues and
-- notifications for events in safety_review are decided by 82 and CR-104.
-- =============================================================================

alter type public.event_status add value if not exists 'safety_review' after 'planning';
