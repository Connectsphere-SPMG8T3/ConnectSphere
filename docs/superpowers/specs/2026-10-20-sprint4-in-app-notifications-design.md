# Sprint 4 in-app notifications (113, 53, 90): design

Date: 2026-10-20. Stories: 113 In-app notifications, 53 Receive notifications about my events, 90 Reminders for upcoming events and incomplete arrangements. 114 (Email organisers) is dropped from Sprint 4: release 1 has no email (team decision, 20/10; the customer left the channel to us, Session 1 and QA2-21).

## Starting point (already decided or built)

- `public.notifications` exists (`recipient_id`, `event_id`, `type`, `message`, `read_at`, `created_at`; index `(recipient_id, read_at, created_at desc)`; RLS select-own; no insert policy). About 31 migrations already insert rows inside the Postgres function that performs the action, so the action and its notification commit together (NT-R3).
- [ADR-0004](../../adr/0004-notification-delivery.md) (status: Proposed, needs team agreement) chooses: the SPA polls the API every 10 seconds while the tab is visible. The poll returns the unread count and newest `created_at`; the full list is fetched when that changes or the bell opens. Email later, from an outbox.
- REQUIREMENTS §6.20 has the recipient table and rules NT-R1 to NT-R4.
- Not built: any read or mark-read endpoint, the bell content (`TopBar.vue` shows an empty panel), reminders.

## Decision

Build what ADR-0004 already describes, plus three things it does not cover: the active-role filter, a shared SQL helper, and scheduled reminders. No email, no outbox, no worker.

### 1. Active role (113 AC4) — the one open design decision

AC4 says a user sees only notifications addressed to them in their **active** role, and `AGENTS.md` forbids authorising by every role the account holds. The table has no role column, so a user holding two roles would see both roles' notifications.

Recommendation:
- Add `recipient_role text` to `notifications` (nullable at first).
- Add a table `notification_types(type text primary key, recipient_role text not null)` listing every type in use and the role it goes to.
- Add a `BEFORE INSERT` trigger that fills `recipient_role` from that table when the inserter left it null. Existing functions and other developers' new stories then need no change beyond registering their type.
- Backfill existing rows from the same table.
- A type that goes to two different roles (for example `comment_added`) is split into two types, or its function sets `recipient_role` itself.
- The API filters `recipient_id = caller AND recipient_role = active role`. A row with a null role is never shown (fail closed), and a test fails if any type in use is missing from `notification_types`.

### 2. Shared SQL helper (Dev 5, merged first)

`public.add_notification(p_recipient uuid, p_event uuid, p_type text, p_message text, p_actor uuid)`: inserts one row, skips it when `p_recipient = p_actor` (NT-R1), `security definer`, empty `search_path`, `service_role` only, like the other functions. Other developers call it (or keep their existing direct inserts; the trigger covers both).

For attendees (53), a second helper `public.notify_registered_attendees(p_event, p_type, p_message, p_actor)` selects the event's Registered attendees. It depends on Dev 1's registrations table, so Dev 5 and Dev 1 agree its name and status column on day 1 (suggested `registrations(event_id, attendee_id, status)` with status `registered`).

### 3. Read API (113): new module `backend/app/modules/notifications/`

Files follow the module convention: `router.py`, `schemas.py`, `service.py`, `repository.py`.

| Endpoint | Behaviour |
|---|---|
| `GET /notifications/unread-count` | `{count, latest_at}` for the caller in the active role. This is the 10-second poll. |
| `GET /notifications?limit=&before=` | Newest first, paged by `created_at`; each item `{id, event_id, type, message, link, read, created_at}`. `link` is built server-side from the type and event id. |
| `POST /notifications/{id}/read` | Marks one read. Someone else's id, or a row for another of the caller's roles: 404. |
| `POST /notifications/read-all` | Marks all of the caller's rows in the active role as read. |

Any signed-in role may call these (organisers and attendees get the bell too). A raw request as a user acting as role Y must not return role X's rows even when the account holds both (SCRUM-76 test).

### 4. Bell (113, 53 AC7): frontend

`useNotificationsStore` (Pinia) polls every 10 seconds while the tab is visible, pauses when hidden, refreshes immediately on becoming visible and after the user's own actions, skips a tick while one is in flight (all as ADR-0004). The `TopBar.vue` bell shows the count and a list with mark-read and mark-all-read. Reusable pieces go under `frontend/src/features/notifications/`. Messages never contain internal information (113 AC4, NT-R2); each trigger's author writes a role-safe message.

### 5. Reminders (53 AC4, 90): scheduled in the database

`pg_cron` is already used (`expire-venue-holds`). Add two SQL functions run by cron jobs:
- `send_attendee_event_reminders()`: 24 hours before an event starts, one notification per Registered attendee; none for waitlisted, withdrawn, or cancelled events.
- `send_staff_arrangement_reminders()`: coordinator, venue staff, technical support (90 AC1 and AC2).

Both are idempotent through a `dedupe_key text` column with a unique partial index, so a re-run or a restart never sends twice.

**[Assumption] for 90 AC3**, which leaves "a set time" open and the customer set no timing (Session 1): remind once per day, from 3 days before the event starts, while an arrangement is still incomplete. To be confirmed in planning poker.

### 6. Who writes which triggers (so nobody waits)

Every other story already writes its own rows. They only need to (a) register their type in `notification_types` and (b) keep the message role-safe.
- Dev 1 (registration): the registration status notifications of 53 AC5, written by the registration functions.
- Dev 2 (cancel 115, change 37): attendee rows through `notify_registered_attendees`.
- Dev 3 (venue bookings, blocks): affected-venue rows; "replacement confirmed" to attendees (53 AC6).
- Dev 4 (assignment, reassignment request): organiser, coordinator and Lead rows.

## Parallel tracks for Dev 5

1. Migration: `recipient_role`, `notification_types`, trigger, backfill, `add_notification` (merged first, small).
2. Backend module and tests; frontend store and bell. These two can proceed in parallel against the endpoint table above.
3. Reminder functions and cron jobs (after track 1).

## Testing

- Backend `pytest`: each endpoint; the active-role denial with a raw request; 404 on another user's id; paging; mark-all only touches the caller's rows in that role.
- Database checks (`supabase/verification/`): the trigger fills the role; a missing type fails the registry test; NT-R1 (actor not notified); reminders are idempotent and skip cancelled, waitlisted and withdrawn.
- Frontend: store polling (visible, hidden, in-flight skip), bell count and list, mark-read.
- Live: `verify_live.py` and the e2e suite, then the manual browser pass on the bell at phone width.

## Out of scope

Email, SMS and web push (ADR-0004 "Revisit when"); Realtime; @mentions; turning notifications off.

## Open items for the team

- Agree ADR-0004 (still "Proposed").
- Confirm the role-column approach in section 1.
- Confirm the registrations table name with Dev 1.
- Confirm the 90 AC3 timing in planning poker.
