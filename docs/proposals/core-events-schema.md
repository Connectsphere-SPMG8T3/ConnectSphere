# Proposal for stand-up — core events schema (events side only)

**Raised from:** SCRUM-72 (Event Coordinator dashboard)
**Branch:** `feature/scrum-72-coordinator-dashboard`
**File to review:** [`core-events-schema.sql`](core-events-schema.sql)
**Status:** **not applied to any database.** Nothing has been pushed to the live project.

---

## Why this exists

SCRUM-72's acceptance criteria need event data — pending requests, requests awaiting an initial decision, clarification responses, and the status of each active event. None of those tables exist. Verified on the live project (`vuiryrzzyfecjqftwicj`), the public schema exposes exactly one table: `profiles`.

The dashboard shipped anyway, as the re-scope in `PROJECT_REVIEW.md` §B4 prescribes: real widgets, real data shape, honest empty states. What it cannot do is show data. This file is the missing half, drafted so the team can approve a schema rather than have three people invent three incompatible ones (§B4, risk 4).

It is **not** merged directly because `PROJECT_REVIEW.md` §C3.5 says the core schema migration must be *"reviewed with the whole team at stand-up before merging."*

## What it covers, and what it deliberately does not

| In scope | Out of scope (for the full core-schema migration, §C3.5) |
|---|---|
| `client_organisations` | `venues`, `venue_layouts`, `venue_facilities` |
| `events` | `venue_bookings` (incl. the DB-1 exclusion constraint), `venue_blocks` |
| `event_status_history` | `equipment_types`, `equipment_outages`, `equipment_requests`, `equipment_reservations` |
| `amendment_requests` | `registrations` |
| `change_requests` | `notifications`, `change_history` |
| RLS policies for the above | `reserve_equipment()`, `register_attendee()` |

This is a **subset**, not a competing proposal. The full migration should absorb this file, not sit next to it. I stopped at the events boundary on purpose: drafting the venue and equipment tables would be exactly the unilateral schema decision §B4 warns about, and those carry the hardest correctness rules (DB-1 through DB-4).

## Decisions worth a second opinion

1. **Draft rows live in `events` with `status = 'draft'`.** The alternative is a separate drafts table. One table keeps the lifecycle in one state machine (§5) and means submitting is a status change, not a row move — but it does mean `events` holds rows where most columns are null. The required-field set for submission (§6.2) is therefore enforced in the service layer, not by check constraints. DR-R2 (drafts never appear in staff queues) is then a rule the API and the RLS policy each have to apply; both do.

2. **`event_status` as a Postgres enum.** Matches `user_role` (SCENARIO.md §7). But the customer has already reconciled the status set once (QA-18 vs QA-56, §9 Q1 is still open), and altering an enum is more awkward than updating a lookup table. If we expect the status set to keep moving, a `event_statuses` lookup table may age better. **Team call.**

3. **Child-table RLS delegates to the parent.** `event_status_history`, `amendment_requests` and `change_requests` each test `exists (select 1 from public.events ...)`, which RLS filters down to "can the caller see the parent event". One rule, four tables. It reads like `where true` at a glance — flagged inline in the SQL. The explicit alternative repeats the organiser/coordinator/staff predicate four times.

4. **`profiles.organisation_id` is added but not backfilled.** `organisation_name` stays as free text for now. Linking existing rows is a separate story; adding the column now is the cheap half of §A3.11.

5. **No INSERT/UPDATE/DELETE policies.** Every write goes through the API with the secret key. DB-6 ("no hard deletes once submitted") is service-layer only in this draft. If the team wants it structural, a delete-blocking trigger belongs here.

## Open questions this schema does not settle

- **§9 Q1 (statuses).** The enum encodes our reconciliation: `approve` → `planning`, `confirm` → `confirmed`, with no separate `approved` status. If the customer rejects that at the next Q&A, this enum changes.
- **§9 Q6 (organiser edits under review).** Whether an organiser may edit directly while `under_review` affects nothing structural here, but it does affect what the service layer allows.
- **AS-R4 (reassignment)** is an `[Assumption]`. `coordinator_id` being nullable and `on delete set null` supports handover either way.

## Review checklist before this becomes a migration

- [ ] Names and shapes agreed against `REQUIREMENTS.md` §4 by the whole team
- [ ] Decisions 1–5 above each have a call recorded
- [ ] Renamed to `supabase/migrations/<timestamp>_core_events_schema.sql`
- [ ] Applied through a PR, not by hand on the shared project (§A3.10)
- [ ] `supabase db push` runs clean on a local or branch database first
- [ ] Supabase advisors show **no new** security or performance findings (Definition of Done)
- [ ] Verification SQL added under `supabase/verification/`, in the style of `auth_security_checks.sql`, covering: drafts invisible to staff (DR-R2), an organiser cannot see another organiser's event (AUTH-R1), the single-open-change-request index (CR-R1)
- [ ] Seed data extended with a few events per status, so the dashboards have something to demo

## What unblocks once it lands

`GET /api/v1/events/dashboard/coordinator`, returning the contract the SPA already consumes (`frontend/src/features/events/store.js`). The dashboard needs no component changes — it fills in on its own. Verified by driving the real page against a stubbed response: widgets, priority order, badges, flags and readiness gaps all render correctly from that payload.
