# ADR-0001 — Build the backend as a modular monolith

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-09-12 (with SCRUM-48, the first backend code) |
| **Recorded** | 2026-09-22 — written retroactively from `SCENARIO.md` §5 and `REQUIREMENTS.md` §3.2; the reasoning is contemporaneous, the ADR framing is not |
| **Deciders** | Jie Ching Lim — wrote the architecture narrative in `fda8aec` (the SCRUM-48 commit) and the container-decisions table in `b168f0d`; adopted by the team and followed by every module since |

## Context

The customer briefing (`SCENARIO.md` §2.3) sets two non-functional requirements that pull on architecture directly:

- **Maintainability** — "future functionality/business rules must be addable without a full rebuild." The customer confirmed in Session 1 that change can happen at any time.
- **Scalability** — the system must absorb three years of anticipated growth in events, users, venues, equipment and registrations (W1 §8e).

Three further constraints applied when the decision was made:

1. **The tech stack was left to us** (QA-73, QA-74). No customer preference to satisfy.
2. **Team and horizon:** six developers, four sprints, no dedicated ops capacity, no CI at the time (still none — `DEFINITION_OF_DONE.md`, "Not yet enforceable").
3. **The domains are coupled by one workflow, not independent.** The event lifecycle (`SCENARIO.md` §2.2) runs draft → submit → assign → review → venue booking → equipment → registration → confirmation, crossing every domain and all five roles in a single business transaction. The release is graded on *coherent end-to-end workflows* (W4), not on isolated features.

The customer also requires that double-booking be **impossible** — first-come-first-served, no staff override (QA-10, QA-113) — and that pending requests hold a venue exclusively (QA-6).

## Decision

Build the backend as **one FastAPI deployable, with one self-contained package per domain** under `backend/app/modules/<domain>/`, each with a consistent internal shape (`router.py`, `schemas.py`, `service.py`, optionally `dependencies.py`), over shared `app/core/` (config, security, exceptions) and `app/db/` (Supabase client factories).

Two rules make the boundaries real rather than cosmetic:

- **Modules reach other modules only through the service layer** — never by importing another module's router, schemas or internals.
- **`auth/dependencies.py` re-exports `app.core.security` deliberately**, so other modules depend on `app.modules.auth.dependencies` rather than reaching into `app.core` directly.

## Considered options

| Option | Why not |
|---|---|
| **Modular monolith** *(chosen)* | One build, one deploy, in-process calls, explicit module boundaries. A module can be extracted later if growth demands it. |
| **Microservices** (per domain, or per role) | Costs more in operations than it returns at this scale (`REQUIREMENTS.md` §3.2). With no CI, no ops capacity and a four-sprint horizon, per-service deploys and inter-service contracts would consume the schedule. It would also turn the integrity guarantees below into a distributed-transaction problem. |
| **Unstructured monolith** (layered by kind — all routers together, all services together) | Cheapest to start, but the maintainability NFR is about adding *domains*, not adding layers. Features 2–20 each land in one domain; a layered split means every new feature edits every layer package, and nothing stops a new module bypassing the access control built for feature 1. |

## Consequences

**Positive**

- The integrity guarantees stay in one database and one transaction scope: `DB-1`'s GiST exclusion constraint on venue holds, and the locking SQL functions behind `DB-3`/`DB-4`. Under a service split, "no two events book the same venue" becomes a distributed-consistency problem rather than a constraint.
- One API means the *API can be the single policy-enforcement point* (`REQUIREMENTS.md` §3.2). Because the backend reads with the secret-key admin client and bypasses RLS, each module's service-layer checks are the real security boundary — coherent only while there is one boundary to reason about.
- One build, one migration history, one test suite, matching a team with no ops capacity.

**Negative**

- **Module boundaries are enforced by convention, not by a compiler or a network.** They erode quietly, and already have twice: the `equipment` module reached Postgres directly with SQLAlchemy while every other module went through the Supabase client, corrected only at review (`3d4110d`); and `events/service.py` raises its own `HTTPException` subclasses instead of adding them to `app/core/exceptions.py`, which `backend/AGENTS.md` asks for.
- **No independent scaling or deployment.** Accepted — no evidence yet that any one domain has a different load profile.
- **One shared database and one migration history**, which is already the project's main collision point (`PROJECT_REVIEW.md` §A3.10; the migration-drift defect, D8).

**Neutral**

- The extraction path stays open: a module whose only inbound edge is its service layer can move behind HTTP later without its callers changing shape. Today the only cross-module call is `venues` → `events.service.names_by_id`, added by SCRUM-67.

## Confirmation

A change conforms to this ADR when:

1. New domain code lives in `backend/app/modules/<domain>/` with the `router` / `schemas` / `service` shape, rather than in a new top-level package.
2. No module imports another module's `router.py` or `schemas.py`; cross-module reads go through the other module's `service.py`.
3. No module imports `app.core.security` directly — it goes through `app.modules.auth.dependencies`.

None of these are automated. They are review checks until a CI pipeline exists (see `DEFINITION_OF_DONE.md`).

## Notes

`REQUIREMENTS.md` §3.3 describes a richer target shape for modules — `policies.py`, `repository.py`, an `events/lifecycle.py` state machine, and in-process domain events. Those are **not** settled by this ADR, and their adoption is currently uneven (`repository.py` exists in `events`, `venues` and `equipment`; the other three exist nowhere). That belongs in its own ADR.

## Links

- `docs/SCENARIO.md` §5 — the original architecture narrative
- `docs/REQUIREMENTS.md` §3.2 — container decisions table, §3.3 — component diagram
- `docs/SCENARIO.md` §2.3 — the customer's non-functional requirements
- `docs/PROJECT_REVIEW.md` §A3 — design improvements that build on this structure
