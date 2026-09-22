# ADR-0002 — Access Postgres through the Supabase client only

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-09-22, at stand-up, when the divergence below was brought to the team |
| **Recorded** | 2026-09-22 — the reasoning is lifted from commit `3d4110d`, where it was written at the time |
| **Deciders** | The team (stand-up); implemented by Eileen Tan in `3d4110d` |
| **Supersedes** | Nothing formally — but it settles the "needs team agreement before merging" flag that `IMPLEMENTATION_MAP.md` §6 had carried since the equipment branch appeared |

## Context

Every module written up to this point — `auth`, `venues`, `events` — read Postgres through `supabase-py` (PostgREST over HTTPS), using the client factories in `app/db/supabase.py`.

The `equipment` module arrived differently. SCRUM-23 and SCRUM-73 were developed on a branch that reached Postgres **directly with SQLAlchemy**: an ORM layer in `db/models.py`, a `get_db()` session dependency in `db/session.py`, and a new `database_url` setting. `IMPLEMENTATION_MAP.md` §6 flagged this as *"diverges from the Supabase-client-only data access used everywhere else, so the team needs to agree before merging"* and the branch sat unmerged pending that conversation.

Two facts framed the choice:

1. **This was never a working alternative.** SQLAlchemy was pinned in `requirements.txt` with no database driver alongside it, so the direct connection could never actually have opened. The divergence was structural, not proven.
2. **The project had no recorded position** to point at. "Use the Supabase client" was a convention visible only by reading the other three modules — which is precisely how a fourth developer ends up inventing something else in good faith.

## Decision

**All application data access goes through the Supabase client.** No direct Postgres connection, no ORM, no second data-access stack.

Concretely:

- Modules read and write through the factories in `app/db/supabase.py` — the `@lru_cache`d publishable-key client for stateless token calls, the secret-key admin client for data reads after a JWT has been verified, and `create_auth_client()` for sign-in and refresh.
- Each module's `repository.py` is its **only I/O seam**; the service layer is pure logic over the rows the repository returns.
- `DATABASE_URL` stays an **operator** convenience for `psql`, seeding and the verification scripts (`docs/SETUP.md`). It is never read by application code, and it is deliberately absent from `.env.example`.

This rule governs *application* data access. It does not push business rules into the database, and it does not ban SQL — see **Scope** below.

## Considered options

| Option | Why not |
|---|---|
| **Supabase client / PostgREST** *(chosen)* | One data-access stack, one mocking seam for the offline test suite, one place where the secret key and the RLS-bypass rule live. A fresh clone runs from the Supabase keys alone. |
| **SQLAlchemy or direct `psycopg`** | Would add a second connection path, a second set of credentials, and a second thing to mock. It also splits the security story: the admin client's "bypasses RLS, only after the caller's JWT is verified" rule is enforced by convention in one place today, and a raw connection is a second place to get that wrong. Its real advantages (below) did not outweigh that here. |
| **Mixed — per module, developer's choice** | The status quo by accident. Guarantees divergent test infrastructure and two ways to express every query. |

## Consequences

**Positive**

- A fresh clone works from the Supabase keys alone; `DATABASE_URL` is no longer a backend prerequisite.
- The test suite keeps a single mocking seam. Rewriting `equipment` onto a repository took its coverage from 6 tests to 19, because the service became pure logic over rows.
- SQLAlchemy left `requirements.txt`, where it was pinned without a driver.

**Negative**

- **PostgREST cannot express `GROUP BY`.** The equipment inventory read now fetches commitment rows and aggregates them in Python (`equipment/repository.py::_commitments`) rather than in Postgres. Fine at present volumes; revisit with a database view or an RPC if reservations grow.
- **PostgREST's shape quirks leak into every repository.** An embed must name its FK constraint when a table has two foreign keys to the same target, or the *whole query* fails with `PGRST201` (`venue_bookings` points at `venues` twice). And a to-one embed comes back as a dict but falls back to a one-element list when PostgREST cannot prove the relationship is to-one — both `venues/repository.py` and `equipment/repository.py` carry a helper for exactly that.
- **Mocked tests cannot catch either quirk.** They appear only against a real database, which makes the verify-against-real-Supabase step in `DEFINITION_OF_DONE.md` load-bearing rather than ceremonial.
- **The named escape hatch is untested.** "Revisit with a view or RPC" assumes calling Postgres functions from the app — and no module calls `.rpc()` anywhere yet.

## Scope: this is not "no SQL"

The integrity guarantees in `REQUIREMENTS.md` §4 live in the database **by design**, and this ADR does not disturb them:

- `DB-1` — the GiST exclusion constraint that makes double-booking impossible (already applied).
- `DB-3` / `DB-4` — `register_attendee()` and `reserve_equipment()`, `SECURITY DEFINER` functions that take row locks so reservations and registrations cannot race. **Neither exists yet**; both are specified for Sprint 3.

When those land, the application will call them through the Supabase client's `.rpc()`. That is consistent with this ADR, not an exception to it. The boundary the project actually holds is:

> **Business rules in Python. Transactional integrity primitives in SQL. One client library reaching both.**

This is the same line SCRUM-74/75 drew when it rejected implementing `set_active_role` as a Postgres function — *"it would be the only piece of business logic in the whole backend living in SQL rather than Python, for no behavioural benefit here."*

## Confirmation

A change conforms when:

1. `backend/requirements.txt` contains no database driver or ORM (`sqlalchemy`, `psycopg`, `asyncpg`).
2. Data access goes through the module's `repository.py`, which imports from `app.db.supabase`.
3. No application module reads `DATABASE_URL`.

None are automated. CI (`.github/workflows/ci.yml`) runs the test suites and the frontend build; it does not grep `requirements.txt` for an ORM or check where `DATABASE_URL` is read. These stay review checks until a dependency or lint check enforces them.

## Follow-ups this ADR creates

Both of these still describe the question as open and should now point here instead:

- `IMPLEMENTATION_MAP.md` §5 — *"Adopting SQLAlchemy or a direct Postgres connection is a project-wide change, so confirm with the team first"*. The team has confirmed.
- `IMPLEMENTATION_MAP.md` §6 — still lists the equipment branch as in-flight and diverging. It is merged, and the divergence is gone.

## Links

- Commit `3d4110d` — `refactor(equipment): read through the Supabase client like every other module`
- `backend/app/db/supabase.py` — the three client factories; `app/db/session.py` — now a re-export, previously the SQLAlchemy seam
- `docs/REQUIREMENTS.md` §4 — the DB-1…DB-6 integrity guarantees
- `CLAUDE.md` / `docs/SCENARIO.md` §5 — the supabase-py client traps (session leakage, `supabase_auth.errors`)
- [ADR-0001](0001-modular-monolith-backend.md) — the module shape this repository seam sits inside
