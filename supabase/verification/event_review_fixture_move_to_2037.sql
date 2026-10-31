-- ONE-OFF DATA FIX (D78). This is not a check: it ends with `commit`.
-- Run it once, by hand, on a database seeded before D78 (the shared project),
-- and only on the developer's go-ahead.
--
-- The SCRUM-34/52 review fixtures (events …0201 and …0202, and …0202's held
-- booking d…0201) were dated 12–13 Nov 2026. Once those dates pass, the held
-- booking expires and both events count as started, so the live checks and
-- e2e specs built on them fail (TC-SAFE-002–004), and TC-BOOK-004 would book a
-- venue for real. supabase/seed.sql now dates them in Nov 2037.
--
-- Every time moves by the same 4018 days (12 Nov 2026 → 12 Nov 2037). 2037
-- shares 2026's calendar, so weekdays and times of day stay as they are,
-- including any edits made to the live rows since seeding. Only times still
-- before 2030 move, so running it twice changes nothing. Changing an event's
-- times fires no status trigger; a booking's occupied period is re-derived
-- from booked_period by venue_bookings_derive_occupied_period.

begin;

update public.events
   set starts_at = starts_at + interval '4018 days',
       ends_at = ends_at + interval '4018 days'
 where id in ('e0000000-0000-4000-8000-000000000201', 'e0000000-0000-4000-8000-000000000202')
   and starts_at < '2030-01-01';

update public.event_space_requests
   set starts_at = starts_at + interval '4018 days',
       ends_at = ends_at + interval '4018 days'
 where event_id in ('e0000000-0000-4000-8000-000000000201', 'e0000000-0000-4000-8000-000000000202')
   and starts_at < '2030-01-01';

update public.venue_bookings
   set booked_period = tstzrange(lower(booked_period) + interval '4018 days',
                                 upper(booked_period) + interval '4018 days', '[)'),
       expires_at = expires_at + interval '4018 days'
 where id = 'd0000000-0000-4000-8000-000000000201'
   and upper(booked_period) < '2030-01-01';

-- What the fixtures look like now, so the operator can confirm before relying on them.
select 'event ' || right(id::text, 4) as row, status::text as status,
       starts_at::text as starts, ends_at::text as ends, null::text as expires
  from public.events
 where id in ('e0000000-0000-4000-8000-000000000201', 'e0000000-0000-4000-8000-000000000202')
union all
select 'booking ' || right(id::text, 4), status::text,
       lower(booked_period)::text, upper(booked_period)::text, expires_at::text
  from public.venue_bookings
 where id = 'd0000000-0000-4000-8000-000000000201'
order by 1;

commit;
