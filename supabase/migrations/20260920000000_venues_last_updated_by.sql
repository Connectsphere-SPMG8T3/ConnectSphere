-- =============================================================================
-- ConnectSphere — SCRUM-67: who last updated a venue profile
-- Project: vuiryrzzyfecjqftwicj
--
-- SCRUM-67 AC2 asks venue staff to see "when the profile was last updated and
-- by whom". `venues.updated_at` already answers "when" (the SCRUM-39 trigger
-- maintains it); nothing answered "by whom".
--
-- This is deliberately a last-writer stamp, not an audit trail. The full
-- per-field change history is §6.7 / SCRUM-14, which needs its own table; a
-- single column here answers the one question SCRUM-67 asks without
-- pre-empting that design.
-- =============================================================================

alter table public.venues
    add column updated_by uuid null,
    add constraint venues_updated_by_fkey
        foreign key (updated_by) references public.profiles (id) on delete set null;

comment on column public.venues.updated_by is
    'Profile that last edited this venue (SCRUM-67 AC2). Null means the last edit '
    'predates this column or the editor''s account has since been removed — the API '
    'reports "not recorded" rather than guessing. Set by the venue edit path '
    '(SCRUM-63/64); there is no trigger, because the database cannot see which '
    'signed-in user the API is acting for (every write uses the secret key).';

-- The venue profile embeds `profiles` through this key, and lint 0001 wants an
-- index on every foreign key.
create index venues_updated_by_idx on public.venues using btree (updated_by);
