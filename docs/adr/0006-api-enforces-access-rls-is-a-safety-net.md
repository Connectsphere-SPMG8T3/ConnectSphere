# ADR-0006 — The API enforces access; RLS is a safety net

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-09-12 to 2026-09-14: SCRUM-48 built the backend on the secret-key client (`fda8aec`), and the rule was written into `REQUIREMENTS.md` §3.2 and `AGENTS.md` (`b168f0d`) |
| **Recorded** | 2026-10-16. Written afterwards from `REQUIREMENTS.md` §3.2, the 13 Sep design review and the SCRUM-76 build log. |
| **Deciders** | |

## Context

The customer requires access to depend on **role and relationship to the event** (W1 §8b, QA-25, QA-87). An organiser must not see another client's events, an attendee must not see internal planning, and only *this event's* coordinator may act on it (`REQUIREMENTS.md` §2).

Supabase offers two places to enforce that:

1. **In the database, with row-level security (RLS).** The client sends the user's JWT, and each table's policies decide which rows that user can read or write.
2. **In our API.** The backend checks the caller, then reads and writes with a key that bypasses RLS.

The relationship rules are not simple row filters. They depend on the active role (an account holds several roles but acts as one, ACC-R4), event status, assignment, the Lead's scope, and which fields a role may see (for example AUTH-R2's split of safety decisions). They change as the customer clarifies them.

## Decision

**The FastAPI backend is the single policy-enforcement point. RLS stays on every table as a deny-by-default safety net for anything that reaches the database another way.**

- **The SPA calls only the API** (`REQUIREMENTS.md` §3.2). It never reads or writes Supabase tables directly.
- **The backend reads with the secret-key admin client, which bypasses RLS**, but only after `get_current_user` has verified the caller's JWT ([ADR-0002](0002-supabase-client-only-data-access.md)).
- **Every endpoint checks role and relationship.** `require_roles([...])` checks the session's *active* role. The service layer then checks the relationship to the resource: the assigned coordinator (`NotAssignedCoordinatorError`), the owning organiser, and visibility (`events.service._visible_event`).
- **RLS is deny-by-default.** RLS is enabled on every table; policies are select-only where a direct read makes sense, and there are no insert, update or delete policies on the workflow tables. Writes go through `security definer` functions that only `service_role` can execute ([ADR-0007](0007-postgres-functions-own-multi-table-writes.md)).
- **Both layers use the same active role.** RLS's `private.current_user_role()` reads the session's active role, just as `require_roles` does (SCRUM-76). A user acting as role Y is refused role-X data whether they come through the API or straight to the database.

## Considered options

| Option | Why not |
|---|---|
| **API enforces; RLS as a safety net** *(chosen)* | Relationship rules are ordinary Python: easy to read, unit-test offline with mocks, and change when the customer clarifies them. One place to look when asking "who can do this?". |
| **RLS as the primary enforcement**, with the backend forwarding the user's JWT so every query runs as that user | Every relationship rule (assignment, Lead scope, status-dependent visibility, field-level hiding) would become SQL policy, written and tested against a live database rather than offline. Policies that check other tables risk recursion (the `42P17` bug fixed in D3–D6). Field-level rules such as AUTH-R2 don't fit row filtering at all. |
| **The SPA talks to Supabase directly** (supabase-js plus RLS, with the API only for complex actions) | Two paths to the same data, with business rules split between SQL and the browser. This is the same as the option above for every table the browser touches. |

## Consequences

**Positive**

- Authorisation logic sits beside the business logic it protects, and the offline test suite covers it, including the access-matrix tests (`backend/tests/test_active_role_access.py`).
- A rule change is a Python change and a test, not a migration.
- Direct database access (a leaked publishable key, a future tool) still meets deny-by-default RLS.

**Negative**

- **One missing check is a data leak.** Because the backend bypasses RLS, nothing behind the API catches an endpoint that checks the role but forgets the relationship. Every new endpoint needs an authorisation-denial test (`AGENTS.md`, "Security baseline").
- **The active-role rule exists twice**: in `require_roles` and in `private.current_user_role()`. Changing how roles work means changing both, and `supabase/verification/active_role_checks.sql` exists to keep them in step.
- **RLS policies are still work.** Every new table needs RLS enabled and policies following the pattern in `CLAUDE.md` (no self-referencing policies; `(select auth.uid())`), even though API traffic never meets them.
- **It rules out features that need the browser to read Supabase directly**, such as Supabase Realtime, unless an ADR makes an exception ([ADR-0004](0004-notification-delivery.md)).

## Confirmation

A change conforms when:

1. Every new endpoint uses `require_roles` and, where a resource belongs to someone, a relationship check in the service layer, with a test proving a wrong-role and a wrong-relationship caller are refused.
2. Every new table has RLS enabled, with no insert, update or delete policy for `authenticated` unless an ADR says why.
3. Nothing in `frontend/src/` queries a Supabase table directly.

## Links

- `docs/REQUIREMENTS.md` §2 (the access matrix), §3.2 (the container decisions table), ACC-R4
- `docs/archive/2026-09-13-design-review.md`, recommendation 4: "these checks are the real security boundary"
- `docs/BUILD_LOG.md` §4.11: SCRUM-76, enforcing by active role at both layers
- `backend/app/core/security.py` (`get_current_user`, `require_roles`)
- [ADR-0001](0001-modular-monolith-backend.md), [ADR-0002](0002-supabase-client-only-data-access.md), [ADR-0005](0005-supabase-as-the-platform.md), [ADR-0007](0007-postgres-functions-own-multi-table-writes.md)
