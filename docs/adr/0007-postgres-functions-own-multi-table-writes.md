# ADR-0007 — Postgres guarantees integrity; multi-table writes are single database functions

| | |
|---|---|
| **Status** | Accepted. Narrows the "Scope" section of [ADR-0002](0002-supabase-client-only-data-access.md). |
| **Decided** | In two steps: 2026-09-15, DB-1's exclusion constraint on venue holds (migration `20260915090000`); 2026-09-23, the first transactional function, `transition_event` (SCRUM-34, migration `20260923120000`). Every write story since has followed the pattern. |
| **Recorded** | 2026-10-16. Written afterwards from `REQUIREMENTS.md` §3.2 and §4, the build log and the migrations. |
| **Deciders** | |

## Context

The customer requires that double-booking be **impossible**, first come first served, with no override (QA-6, QA-10, QA-113, QA2-23). The system must never show contradictory information about one event (NFR-R1). Most workflow actions change several tables at once. Approving an event changes its status, writes a history row and notifies the organiser. Requesting a venue locks the event, inserts a hold and notifies every venue staff member.

Two facts about the stack decide where those guarantees can live:

1. **Checking and then writing in application code races.** Two coordinators both read "Hall A is free", and both insert.
2. **PostgREST has no transaction across requests.** The backend reaches the database only through `supabase-py` ([ADR-0002](0002-supabase-client-only-data-access.md)). Three `.insert()` calls are three separate commits, so a failure halfway leaves the event changed with no history or notification.

## Decision

**Rules that must hold under concurrency are constraints in Postgres. Any write that changes more than one table, or must win a race, is one Postgres function called once through `.rpc()`.**

- **Constraints carry the invariants.** DB-1 is `EXCLUDE USING gist (venue_id WITH =, occupied_period WITH &&)` over active bookings, plus unique indexes such as one active booking per event space (`venue_bookings_one_active_per_space`).
- **Functions carry the multi-table writes.** They include `transition_event`, `return_event_for_amendment`, `resubmit_event`, `add_event_comment`, `request_venue_booking`, `reject_venue_booking`, `update_venue`, `reassign_event`, `send_event_to_safety_review`, `safety_approve_event`, `submit_equipment_request` and `expire_venue_holds`. In one transaction, each:
  - locks the row it depends on (`for update`),
  - re-checks the state it needs (status, expected `version`, assignment),
  - writes the change, its history row and its notifications (NT-R3),
  - returns an outcome (`ok`, `held_by_other`, a stale-version empty result and so on), which the service layer maps to an HTTP status.
- **Every such function has the same security shape:** `security definer`, `set search_path = ''`, and `execute` granted to `service_role` only, so neither the browser nor a signed-in user can call it ([ADR-0006](0006-api-enforces-access-rls-is-a-safety-net.md)).
- **Python still decides first.** The service layer authorises the caller, validates the request and checks the lifecycle table (`events/lifecycle.py`). The function then re-checks under a lock what could have changed since.

**This narrows ADR-0002's boundary.** ADR-0002 drew the line as "business rules in Python, transactional integrity primitives in SQL" and expected only DB-1, DB-3 and DB-4 to live in the database. In practice the functions also hold the status guards, recipient selection for notifications and history writes, because those must commit with the change.

## Considered options

| Option | Why not |
|---|---|
| **Constraints plus one function per multi-table write** *(chosen)* | Atomic, race-safe, and still reached through the one client library ADR-0002 allows. |
| **Check, then write, from Python** | Loses races (both requests read "free"), and a failure between writes leaves partial state. Rejected for anything contended. |
| **Several PostgREST calls with compensation on failure** | No real transaction; a crash between calls still leaves partial state, and the compensation code is a second thing to get wrong. |
| **A direct Postgres connection with transactions in Python** (SQLAlchemy or `psycopg`) | Would give transactions without moving logic into SQL, but ADR-0002 rules out a second data-access stack. |
| **The in-process `core.events` dispatcher** in `REQUIREMENTS.md` §3.3 (publish `EventApproved`, and subscribers write history and notifications) | Not adopted (`REQUIREMENTS.md` §3.3, status note). Subscribers would run after the change commits, so NT-R3 would need an outbox anyway, and there was only one consumer of each event. Revisit when email becomes a second subscriber ([ADR-0004](0004-notification-delivery.md)). |

## Consequences

**Positive**

- Double-booking is impossible however many backend processes run, and the database proves it under real concurrency (TC-BOOK-007).
- An action and its history and notifications always commit together.
- The functions are reusable. `transition_event` serves approve, reject, submit, return and the safety transitions.

**Negative**

- **Logic is split between Python and SQL.** Reading one action means reading the service function and the migration that defines its RPC. A changed function is a new migration (`create or replace`), not an edit.
- **The offline test suite can't run the SQL.** Mocked tests only see the outcome codes. Each function has a SQL verification script in `supabase/verification/` and live checks, which makes verifying against the real database load-bearing (`DEFINITION_OF_DONE.md`).
- **Races fail in surprising ways.** Two simultaneous overlapping inserts can end in a deadlock (`40P01`) rather than the exclusion violation, so `request_venue_booking` has to map both to `held_by_other` (BUILD_LOG, SCRUM-19).
- **Shared helpers must be called on every path.** A new hold path must call `expire_venue_holds()` before its overlap check, or an expired hold still blocks it (a real defect, fixed in PR #64).

## Not built yet

DB-2 (one active registration per attendee), DB-3 (`register_attendee`, registrations stop at capacity) and DB-4 (`reserve_equipment`, all-or-nothing reservations) are specified in `REQUIREMENTS.md` §4 but don't exist yet. They must follow this ADR when built.

## Confirmation

A change conforms when:

1. No endpoint makes more than one write call to PostgREST for a single user action.
2. Every new rule that must hold under concurrency is a constraint or a lock taken inside a function, with a race test or live check.
3. Every new function is `security definer`, sets `search_path = ''`, is executable only by `service_role`, and has a script in `supabase/verification/`.

## Links

- `docs/REQUIREMENTS.md` §3.2 (the "Integrity" row), §4 (DB-1 to DB-6), §6.12 (BR-R2), NT-R3
- `docs/IMPLEMENTATION_MAP.md`: the migrations table and the "Generic status-transition RPC" entry
- `docs/BUILD_LOG.md`: SCRUM-34 (`transition_event`), SCRUM-19 (the deadlock case)
- `supabase/migrations/20260915090000_venues_catalogue_and_availability.sql`, `supabase/migrations/20260923120000_event_review_history_and_notifications.sql`
- [ADR-0001](0001-modular-monolith-backend.md), [ADR-0002](0002-supabase-client-only-data-access.md), [ADR-0004](0004-notification-delivery.md), [ADR-0005](0005-supabase-as-the-platform.md), [ADR-0006](0006-api-enforces-access-rls-is-a-safety-net.md)
