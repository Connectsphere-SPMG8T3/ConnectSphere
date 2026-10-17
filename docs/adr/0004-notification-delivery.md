# ADR-0004 — Deliver in-app notifications by polling the API every 10 seconds

| | |
|---|---|
| **Status** | Proposed — for team review |
| **Decided** | 2026-10-16, while planning SCRUM-27 (Notification system: 69, 53) |
| **Deciders** | Ng Xuan Wei (proposer); needs team agreement |
| **Applies to** | SCRUM-27 and every story that writes a `notifications` row |

## Context

Notifications are half built. Every action that notifies someone (approve, reject, return, resubmit, comment, venue booking request, safety review and so on) inserts its `notifications` rows inside the same Postgres function as the action, so the action and its notifications commit together (NT-R3). Nothing reads them yet: there is no read endpoint, and the bell in `TopBar.vue` shows an empty panel.

What the customer asked for, and what they left to us:

1. **The channel and delivery preferences are a team choice** (QA-11, QA-39, QA2-21). Release 1 is in-app only; email is P3 (`REQUIREMENTS.md` §6.20).
2. **No latency is specified.** No customer answer asks for live or instant notifications. The only timing is our own acceptance criterion in §6.20.
3. **Scale is modest and unquantified.** About 500 staff plus organisers and attendees, with three years of growth (NFR-SC1). That is thousands of notifications a day at most.
4. **Delivery is already asynchronous.** A notification row waits in the table until its recipient next opens the app. The table is each user's inbox: it holds read/unread state and history, which the bell needs.
5. **The API is the policy-enforcement point**, and all application data access goes through the backend's Supabase client ([ADR-0002](0002-supabase-client-only-data-access.md)). The browser does not read Supabase directly today.
6. **The project is on Supabase's free plan.** As of 2026-10-16, Supabase Realtime there allows 200 concurrent connections and 2 million messages a month ([Realtime limits](https://supabase.com/docs/guides/realtime/limits)).

## Decision

**The SPA polls the API for the caller's notifications every 10 seconds while the tab is visible.** Notifications keep being written to `public.notifications` in the same transaction as the action that causes them.

- The polled call is cheap: it returns the unread count and the newest `created_at`, served by the existing `(recipient_id, read_at, created_at desc)` index. The full list is fetched only when that changes or when the user opens the bell.
- Polling pauses while the tab is hidden and runs immediately when it becomes visible again.
- The store also re-fetches straight after the user's own actions.
- Polls go through `authStore.withSession`. A failed poll (503, network error) skips one tick silently; a 401/404 ends the session as every other call does (`isSessionRejected`).
- A tick is skipped while the previous poll is still in flight.
- The interval is a single constant, so changing it is a one-line change.

The worst-case delay is 10 seconds while the page is open; the average is about 5.

## Considered options

| Option | Why not |
|---|---|
| **Poll the API every 10 seconds** *(chosen)* | Uses the same SPA → API path as every other read, so the API stays the policy-enforcement point. No quota, no new infrastructure, no new library. 100 visible tabs come to about 10 small, indexed requests a second. |
| **Poll every 30 seconds** (the original §6.20 decision) | Works, but a 30-second worst case is longer than needed when a 10-second poll costs little more. |
| **Supabase Realtime** (`postgres_changes` on `notifications`) | Instant, and the existing RLS policy already limits each user to their own rows. But the free plan's 200 concurrent connections is one per open tab. It would also be the first place the browser reads data from Supabase directly, making RLS rather than the API the only check on that path. It needs extra token handling too: `realtime.setAuth` after every session refresh, unsubscribing at logout, and re-fetching after a reconnect. |
| **Server-Sent Events or WebSockets from FastAPI** | Instant, with no Supabase quota. But ADR-0002 rules out the direct Postgres connection `LISTEN/NOTIFY` needs, so the backend would have to poll the table itself and fan out rows from memory, which works only with a single backend process. Endpoints are plain `def`, so each open stream would also tie up a threadpool slot unless it were rewritten as `async`. |
| **A message broker (Kafka or RabbitMQ)** | Solves a problem we don't have. The recipients are users, not independent consuming services; ConnectSphere is one deployable with one consumer (the in-app writer). A broker deletes messages once consumed (or, with Kafka, keeps a log that can't answer "has this user read it?"), so the `notifications` table would still be needed as the inbox. Publishing to a broker alongside the database write would also break NT-R3 unless we added an outbox table and a relay. And it is another service to host and run. |
| **Web Push** (service worker and the browser's push service) | The only option that reaches users who don't have the app open. That makes it a separate channel, like email, not a faster bell. It needs HTTPS, a permission prompt and a new library. |

## Consequences

**Positive**

- No new infrastructure, quota or library. The bell is built from the same pieces as every other screen, and tested the same way (`vi.mock("@/services/api")`).
- Every notification read is authorised by the API, like every other read.
- NT-R3 is unchanged: an action and its notifications still commit together.

**Negative**

- **Up to 10 seconds of delay** for something another user does while you're watching the screen. Actions you take yourself, and switching back to the tab, show current data immediately.
- **Constant background traffic** from every visible tab, including when nothing has changed. Each poll costs a profile read (`get_current_user`) and a count query.
- **Nothing reaches a user who isn't in the app.** That is the job of a later channel (email, Web Push).

## Revisit when

- **An external channel is added** (email, SMS, Web Push). Send it from a background worker over an outbox in Postgres (an `emailed_at` column polled by `pg_cron`, or a `pgmq` queue), so a slow or failing provider never blocks an action. This is also the point to decide whether to adopt the in-process `core.events` dispatcher planned in `REQUIREMENTS.md` §3.3, since email would be its second subscriber.
- **The customer asks for instant notifications.** Add Supabase Realtime on top, disconnecting hidden tabs, and keep this poll as the fallback. That needs its own ADR because the browser would then read Supabase directly.
- **Polling traffic becomes a measurable load** on the backend or Supabase.
- **Several separately deployed services need the same domain events, or volume grows far beyond this scale.** Only then is a broker worth its running cost: RabbitMQ to hand jobs to workers, Kafka for replayable event streams.

## Links

- Backlog SCRUM-27 (Notification system: 69, 53)
- `docs/REQUIREMENTS.md` §6.20 (recipients, NT-R1–R4), NFR-SC1, §3.3 (the `core.events` dispatcher, not adopted)
- `supabase/migrations/20260923120000_event_review_history_and_notifications.sql` — the `notifications` table, its index and its select-own RLS policy
- [ADR-0001](0001-modular-monolith-backend.md) — one deployable
- [ADR-0002](0002-supabase-client-only-data-access.md) — application data access only through the backend's Supabase client
