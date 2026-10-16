# ADR-0005 — Build on Supabase as the platform

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-09-12, with SCRUM-48 (`fda8aec`), the first backend code |
| **Recorded** | 2026-10-16. Written afterwards. The reasons for the choice and the MySQL comparison were confirmed by the team on 2026-10-16. The other rejected options, and the benefits under "Turned out to matter", were added when this was written. |
| **Deciders** | |

## Context

ConnectSphere needs a relational database, user accounts with sessions, and somewhere to host both. The constraints when the choice was made:

1. **The tech stack was left to us** (QA-73, QA-74), and so was the authentication mechanism (QA-50).
2. **Six developers, four sprints, no ops capacity** ([ADR-0001](0001-modular-monolith-backend.md)). Nobody on the team was going to run a database server, patch it or back it up.
3. **Six people need the same data.** Everyone develops and tests against workflows that cross every role, so the team needs one shared database from day one, not six local copies.
4. **Credentials are a liability.** Storing and checking passwords ourselves is the kind of code a student project gets wrong.

## Decision

**One hosted Supabase project (`vuiryrzzyfecjqftwicj`) provides the database, authentication and the APIs over them.** The FastAPI backend and the Vue SPA are our code; everything under them is Supabase.

Why Supabase, in the order the team weighed them:

1. **Auth is ready-made, and was the deciding reason.** Sign-up, password storage, sign-in, sessions and token rotation come built in. With MySQL, the team would have built and secured all of that in FastAPI.
2. **Free hosting with nothing to run.** The free plan gives one hosted database the whole team reaches from day one, with no server to set up, patch or back up.
3. **The dashboard.** Its table editor and SQL editor let all six developers inspect and fix shared data without installing a database client.
4. **Familiar ground.** Supabase was a known, well-documented option for the team, which mattered with four sprints to deliver.

What the project depends on from Supabase:

| Supabase piece | What we use it for |
|---|---|
| **Postgres** | All data, constraints (DB-1's exclusion constraint), RLS policies and the transactional functions in [ADR-0007](0007-postgres-functions-own-multi-table-writes.md) |
| **Auth (GoTrue)** | Credentials in `auth.users`, password sign-in, refresh-token rotation, sign-out. The backend verifies every JWT locally against the project's JWKS (`get_claims`), so no JWT secret is configured anywhere. |
| **PostgREST and `supabase-py`** | The only way the backend reaches the database ([ADR-0002](0002-supabase-client-only-data-access.md)), including `.rpc()` calls to Postgres functions |
| **`pg_cron`** | Scheduled work with no backend worker: the `expire-venue-holds` job (CR-99) |
| **CLI and migration ledger** | `supabase db push` applies `supabase/migrations/` |

ConnectSphere's own user data lives in `public.profiles` and `user_roles`, linked to `auth.users` by the `handle_new_user()` trigger. Supabase owns *who you are*; we own *what you may do*.

## Considered options

| Option | Why not |
|---|---|
| **Supabase** *(chosen)* | Managed authentication and a hosted Postgres database, from one dashboard and a free plan. Nothing to install or run. |
| **MySQL** *(considered by the team)* | No built-in authentication, so sign-up, password storage and sessions would be ours to build and secure. It also needed somewhere to host it so the whole team could share one database. |
| **Self-hosted Postgres plus our own authentication** (for example FastAPI with a password-hashing library) | We would write and secure password storage, reset and session handling, and someone would have to host, back up and patch the database. Too much ops for this team and timeline. |
| **Another managed database plus a separate auth provider** (for example a cloud Postgres and Auth0 or Firebase Auth) | Two vendors, two consoles and two sets of keys, and user identity in a different system from the data it guards. RLS would have to trust a foreign token issuer. |
| **Firebase or another non-relational backend** | Can't express the time-range exclusion constraint or transactional multi-table writes, which the customer's no-double-booking rule depends on. |

## Consequences

**Positive**

- No servers to run. A fresh clone works from the Supabase URL and keys alone.
- Password storage, hashing, rotation and key rotation are Supabase's problem. JWKS verification accepts both the legacy HS256 and the current ES256 signing keys, so a key rotation needs no code change.

**Turned out to matter** (not why Supabase was chosen, but the design now depends on them, and MySQL has none of them)

- **Range types and exclusion constraints** (`btree_gist`). They make double-booking impossible in the database (DB-1, [ADR-0007](0007-postgres-functions-own-multi-table-writes.md)). In MySQL this rule would need locking in application code.
- **Row-level security**, the deny-by-default safety net behind the API ([ADR-0006](0006-api-enforces-access-rls-is-a-safety-net.md)).
- **Database functions called through `.rpc()`**, which make each multi-table write atomic (ADR-0007).
- **`pg_cron`**, which expires venue holds with no backend worker (CR-99).
- **The Supabase MCP server** (`mcp/`), which lets AI assistants inspect the live schema, logs and advisors.

**Negative**

- **Expensive to leave.** Leaving would mean rewriting authentication, sessions and sign-up, every RLS policy (they call `auth.uid()` and read the JWT's `session_id`), the `pg_cron` job and the data access layer. This is the most expensive decision in the project to reverse.
- **SDK traps.** `supabase-py` keeps sessions on the client instance (DEFECTS D1), has two same-named exception packages (`gotrue` and `supabase_auth`), and reports outages as `AuthRetryableError`, not `AuthApiError`. Each one caused a real bug before it was written down in `CLAUDE.md`.
- **One shared project for the whole team.** Every developer migrates the same live database, so the schema has drifted from `supabase/migrations/` (D8, D26), and checks against "the real system" share data with everyone else.
- **Free-plan limits shape the design.** For example, the built-in email sender is limited to a few messages an hour ([ADR-0003](0003-signup-via-admin-api-without-email-confirmation.md)), and Realtime allows 200 concurrent connections ([ADR-0004](0004-notification-delivery.md)).
- **PostgREST shapes how queries are written** (no `GROUP BY`, embed quirks; see ADR-0002).

## Revisit when

- The free plan's limits block a feature or a demo, which means a paid plan or moving that piece off Supabase.
- The customer needs hosting, data residency or authentication (for example single sign-on with their staff directory) that Supabase can't provide.

## Links

- `docs/PROJECT_OVERVIEW.md` §5: the architecture narrative, the auth flow and the SDK traps
- `docs/REQUIREMENTS.md` §3.2: the container decisions table ("Authentication: Supabase Auth; the API verifies JWTs via JWKS")
- `docs/archive/2026-09-13-design-review.md`: "Authentication is delegated to Supabase Auth"
- `backend/app/db/supabase.py`, `backend/app/core/security.py`
- [ADR-0002](0002-supabase-client-only-data-access.md), [ADR-0003](0003-signup-via-admin-api-without-email-confirmation.md), [ADR-0004](0004-notification-delivery.md), [ADR-0006](0006-api-enforces-access-rls-is-a-safety-net.md), [ADR-0007](0007-postgres-functions-own-multi-table-writes.md)
