# Architecture Decision Records

An ADR records one significant architecture decision: what forced it, what we chose, what we rejected and what it costs us. Its job is to answer "why is it built this way?" with the reasoning we had at the time, so nobody has to reconstruct it from the code.

## When to write one

Write an ADR for a decision that is any of:

- **expensive to reverse** (it shapes the schema, every endpoint or the platform),
- **likely to be questioned**, by a reviewer, an instructor or a new teammate, or
- **something a teammate would otherwise have to reverse-engineer** from the code.

Not every choice needs one. Business rules, UI choices and **[Team decision]** / **[Assumption]** items belong in `docs/REQUIREMENTS.md`. Conventions belong in `AGENTS.md`.

## Index

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-modular-monolith-backend.md) | Build the backend as a modular monolith | Accepted |
| [0002](0002-supabase-client-only-data-access.md) | Access Postgres through the Supabase client only | Accepted; Scope narrowed by 0007 |
| [0003](0003-signup-via-admin-api-without-email-confirmation.md) | Create sign-up accounts through the admin API, already confirmed | Accepted |
| [0004](0004-notification-delivery.md) | Deliver in-app notifications by polling the API every 10 seconds | Accepted |
| [0005](0005-supabase-as-the-platform.md) | Build on Supabase as the platform | Accepted |
| [0006](0006-api-enforces-access-rls-is-a-safety-net.md) | The API enforces access; RLS is a safety net | Accepted |
| [0007](0007-postgres-functions-own-multi-table-writes.md) | Postgres guarantees integrity; multi-table writes are single database functions | Accepted |
| [0008](0008-event-history-read-from-source-tables.md) | An event's change history is read from its source tables, not copied into one table | Accepted |

## Writing one

- **File name:** `NNNN-short-slug.md`, numbered in sequence. Numbers are never reused.
- **Header table:** **Status**, **Decided** (when and in which story), **Recorded** (when written, if later than the decision), **Deciders** (may be left empty until the team assigns them; this is also the place to name who presents the ADR in a Q&A).
- **Sections:** Context (the constraint, no solution yet) → Decision → Considered options (each with why it lost) → Consequences (positive and negative; be honest about the weak points) → Revisit when / Confirmation (how a reviewer checks a change conforms) → Links. Copy an existing ADR as the template.
- **Recording a past decision:** mark it **Accepted** and add a **Recorded** date. Take the reasoning from the commit, build-log entry or doc where it was made, and say so when part of it has to be reconstructed.

## Statuses

- **Proposed:** written, waiting for team agreement. A teammate's review on the pull request is where it gets agreed.
- **Accepted:** the team agreed, or it is already built and followed.
- **Superseded by NNNN** / **narrowed by NNNN:** an accepted ADR is not rewritten. When a later decision changes it, update only its Status line (and, if needed, add a short pointer note where the changed part is) and put the new reasoning in the new ADR.

When an ADR's status changes, update the index above.
