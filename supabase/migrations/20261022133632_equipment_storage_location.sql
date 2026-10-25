-- 23-R AC3 (QA3-34): catalogue information only, never part of availability.
-- Existing stock stays unrecorded until its real storage location is known.
alter table public.equipment add column storage_location text;
comment on column public.equipment.storage_location is
    'Storage location for Technical Support reference only; does not affect availability.';
