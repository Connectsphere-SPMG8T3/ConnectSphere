# CR-100 rollback migration verification — 2026-10-18 23:51 SGT

| | |
|---|---|
| Branch | `feature/cr-100-venue-buffers-safety-details` |
| Commit | `ade5af0` + uncommitted CR-100 changes |
| Run by | Codex |
| System | Real Supabase `vuiryrzzyfecjqftwicj`, Management API via CLI |
| Method | One transaction: `BEGIN`, 3-second lock timeout, migration `20261018153029`, `venue_buffer_checks.sql`, `ROLLBACK` |
| Result | **Pass: VENUE BUFFER CHECKS PASSED** |

The regression script first failed on the original schema with `record v_venue has no field setup_minutes` (expected red). It passed with the migration in the rollback transaction, then passed again after adding the maximum PostgreSQL integer regression. No schema, booking, venue, notification, history, or migration-ledger changes persisted.

| Case | Verified | Result |
|---|---|---|
| TC-VENUE-092 / AC1, AC2 | Independent zero defaults; 1,000,000 and 2,147,483,647 accepted; negative setup/turnaround and null setup rejected | Pass |
| TC-VENUE-092 / AC3, AC6 | Edit RPC stores both safety facts and buffers with actor, time, before and after in venue history | Pass |
| TC-VENUE-092 / AC5 | Both event and space request paths copy defaults; old booking row unchanged after editing defaults; setup-only clash refused; touching windows accepted; space's own time retained | Pass |
| TC-VENUE-092 / large buffers | Full integer and BCE occupied endpoint stored exactly; booked period unchanged | Pass |

This does **not** verify PostgREST schema-cache refresh, browser data round-trip, or shared deployment. Those require the migration to deploy through the merged PR (`DEFINITION_OF_DONE.md`).

Advisors on the unchanged shared project: existing leaked-password protection warning; nine equipment RLS init-plan warnings and three unused-index informational findings. No new tables, policies or indexes are introduced. Post-deployment advisor comparison remains pending.

Claude review was authorized but could not run because its OAuth session expired. A local independent reviewer identified date-overflow/display issues; regression tests were added and those issues corrected. No Claude review verdict is claimed.

Additional compatibility checks, each with the new migration inside its own rollback transaction: `venue_edit_checks.sql`, `venue_booking_request_checks.sql`, `event_space_checks.sql`, `booking_conflict_checks.sql`, and `venue_replacement_checks.sql` all passed. This covers existing edit/history/flags, event and space requests, conflict semantics, and affected-booking replacement after the function replacements.
