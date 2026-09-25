-- =============================================================================
-- ConnectSphere - SCRUM-33 follow-up: a resubmission note can't be blank
--
-- The message already has a non-blank check; the note didn't, so only the API
-- stopped a whitespace-only note. The table now refuses it too, matching the
-- message (found in review of PR #30).
-- =============================================================================

alter table public.amendment_requests
    add constraint amendment_requests_resubmission_note_not_blank
        check (resubmission_note is null or length(btrim(resubmission_note)) > 0);
