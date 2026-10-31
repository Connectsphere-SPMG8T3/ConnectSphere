# ADR-0008 — An event's change history is read from its source tables, not copied into one table

| | |
|---|---|
| **Status** | Accepted. Replaces the single `change_history` table that `REQUIREMENTS.md` §6.7 (IM-R1) and §3.3 assumed. |
| **Decided** | 2026-10-30, planning story 62. |
| **Recorded** | 2026-10-30. |
| **Deciders** | Xuan Wei |

## Context

The customer requires that authorised users can see what changed on an event, who changed it and when, from the UI (QA-70, W1 §8f). Story 62's AC5 adds that the existing records feed into that history rather than being rebuilt.

By the time story 62 was planned, each part of an event already kept its own append-only record, written in the same transaction as the change ([ADR-0007](0007-postgres-functions-own-multi-table-writes.md)):

- `event_status_history`: creation and every status change;
- `event_assignment_history`: reassignments;
- `event_change_requests`: change and cancellation requests and their decisions;
- `event_safety_decisions`: safety decisions;
- `venue_booking_history` and `venue_edit_history`: bookings and venues;
- `event_technical_history`: equipment and technical preparation.

`GET /events/{id}/history` already combined the first three. The only change that nothing recorded was an edit to an event's fields.

## Decision

**An event's change history is assembled at read time, in `events.service.history()`, from the source tables above. The one new table, `event_edit_history`, stores field edits only: field, old value, new value, who and when.** Each writer records its own entry in the same transaction as the change: `private.record_event_edits(...)` for field edits, called by the organiser's edit of a returned request (story 62) and the coordinator's direct edit (story 112).

What each role sees is decided in the same service function, per source, so the API never returns an entry the caller may not see (story 62 AC3, AC4; [ADR-0006](0006-api-enforces-access-rls-is-a-safety-net.md)).

Every history table refuses UPDATE and DELETE through a trigger (AC6). The only exceptions keep foreign keys working: a deleted profile can null out `actor_id`, and a deleted event can remove its own history.

## Considered options

| Option | Why not |
|---|---|
| **Read from the source tables, plus `event_edit_history` for field edits** *(chosen)* | Nothing is copied, so the history can't drift from the records it shows. Stories that already write history keep writing it unchanged. |
| **One `change_history` table, filled by triggers on every source table, with old rows copied in once** | Two copies of every entry, which can disagree. Triggers on six tables that other stories own change those stories' writes. The one-off copy has to map six shapes into one. |
| **One `change_history` table that every writer calls directly** | The same duplication, and every existing write function would need a new migration. |

## Consequences

- **A new source of history means a change to `events.service.history()`.** For example, CR-109's venue preparation or any later section must be added there, with its visibility rule.
- **The response is a union of kinds.** `EventHistoryEntry.kind` says which source an entry came from, and the frontend renders each kind.
- Reading an event's history makes one query per source. That's fine at this scale; revisit it if an event's history grows large.

## Links

- `docs/REQUIREMENTS.md` §6.7 (IM-R1, IM-R2), §3.3 status note, LC-R2, NFR-A1
- Backlog stories 62 and 112
- [ADR-0006](0006-api-enforces-access-rls-is-a-safety-net.md), [ADR-0007](0007-postgres-functions-own-multi-table-writes.md)
