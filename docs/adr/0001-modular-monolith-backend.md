# ADR-0001 — Build the backend as a modular monolith

| | |
|---|---|
| **Status** | Accepted |
| **Decided** | 2026-09-12 (with SCRUM-48, the first backend code) |
| **Recorded** | 2026-09-22 — written retroactively from `PROJECT_OVERVIEW.md` §5 and `REQUIREMENTS.md` §3.2; the reasoning is contemporaneous, the ADR framing is not |
| **Deciders** | Jie Ching Lim — wrote the architecture narrative in `fda8aec` (the SCRUM-48 commit) and the container-decisions table in `b168f0d`; adopted by the team and followed by every module since |
| **Clarified** | 2026-11-06 — see [Clarification](#clarification-2026-11-06). The decision is unchanged |

## Context

The customer briefing (`PROJECT_OVERVIEW.md` §2.3) sets two non-functional requirements that pull on architecture directly:

- **Maintainability** — "future functionality/business rules must be addable without a full rebuild." The customer confirmed in Session 1 that change can happen at any time.
- **Scalability** — the system must absorb three years of anticipated growth in events, users, venues, equipment and registrations (W1 §8e).

Three further constraints applied when the decision was made:

1. **The tech stack was left to us** (QA-73, QA-74). No customer preference to satisfy.
2. **Team and horizon:** six developers, four sprints, no dedicated ops capacity, and no CI at the time the decision was taken (CI was added afterwards on `chore/ci-pipeline`; see `.github/workflows/ci.yml`).
3. **The domains are coupled by one workflow, not independent.** The event lifecycle (`PROJECT_OVERVIEW.md` §2.2) runs draft → submit → assign → review → venue booking → equipment → registration → confirmation, crossing every domain and all five roles in a single business transaction. The release is graded on *coherent end-to-end workflows* (W4), not on isolated features.

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
| **Microservices** (per domain, or per role) | Costs more in operations than it returns at this scale (`REQUIREMENTS.md` §3.2). With no CI at the time, no ops capacity and a four-sprint horizon, per-service deploys and inter-service contracts would consume the schedule. It would also turn the integrity guarantees below into a distributed-transaction problem. |
| **Unstructured monolith** (layered by kind — all routers together, all services together) | Cheapest to start, but the maintainability NFR is about adding *domains*, not adding layers. Features 2–20 each land in one domain; a layered split means every new feature edits every layer package, and nothing stops a new module bypassing the access control built for feature 1. |

## Consequences

**Positive**

- The integrity guarantees stay in one database and one transaction scope: `DB-1`'s GiST exclusion constraint on venue holds, and the locking SQL functions behind `DB-3`/`DB-4`. Under a service split, "no two events book the same venue" becomes a distributed-consistency problem rather than a constraint. *(Narrowed in the [Clarification](#clarification-2026-11-06): the constraint could stay local to a venue service; what becomes distributed is the state shared across domains.)*
- One API means the *API can be the single policy-enforcement point* (`REQUIREMENTS.md` §3.2). Because the backend reads with the secret-key admin client and bypasses RLS, each module's service-layer checks are the real security boundary — coherent only while there is one boundary to reason about.
- One build, one migration history, one test suite, matching a team with no ops capacity.

**Negative**

- **Module boundaries are enforced by convention, not by a compiler or a network.** They erode quietly, and already have twice: the `equipment` module reached Postgres directly with SQLAlchemy while every other module went through the Supabase client, corrected only at review (`3d4110d`); and `events/service.py` raises its own `HTTPException` subclasses instead of adding them to `app/core/exceptions.py`, which `backend/AGENTS.md` asks for. *(A third case, schema imports, is in the [Clarification](#clarification-2026-11-06).)*
- **No independent scaling or deployment.** Accepted — no evidence yet that any one domain has a different load profile.
- **One shared database and one migration history**, which is already the project's main collision point ([`archive/2026-09-13-design-review.md`](https://github.com/chasingsunsets/ConnectSphere/blob/91fec10aab05070169286fbbed5268fef9cf6930/docs/archive/2026-09-13-design-review.md) §A3.10; the migration-drift defect, D8).

**Neutral**

- The extraction path stays open: a module whose only inbound edge is its service layer can move behind HTTP later without its callers changing shape. Today the only cross-module call is `venues` → `events.service.names_by_id`, added by SCRUM-67. *(No longer true: see the [Clarification](#clarification-2026-11-06).)*

## Confirmation

A change conforms to this ADR when:

1. New domain code lives in `backend/app/modules/<domain>/` with the `router` / `schemas` / `service` shape, rather than in a new top-level package.
2. No module imports another module's `router.py` or `schemas.py`; cross-module reads go through the other module's `service.py`.
3. No module imports `app.core.security` directly — it goes through `app.modules.auth.dependencies`.

None of these three are automated. CI (`.github/workflows/ci.yml`) runs the test suites and the frontend build, which does not detect a boundary violation: a module importing another module's `router.py` compiles and tests green. They stay review checks until an import-boundary lint rule enforces them.

## Revisit when

- **A domain's load differs enough** that scaling the single deployable no longer meets it.
- **Separate teams need to deploy independently**, so one shared release becomes the bottleneck.
- **A domain stops sharing transactions with the others**, which removes the main cost of moving it out.

## Notes

`REQUIREMENTS.md` §3.3 describes a richer target shape for modules — `policies.py`, `repository.py`, an `events/lifecycle.py` state machine, and in-process domain events. Those are **not** settled by this ADR, and their adoption is currently uneven (`repository.py` exists in `events`, `venues` and `equipment`; the other three exist nowhere). That belongs in its own ADR.

## Clarification (2026-11-06)

Added after the decision, from a review of the code on `main` and of [ADR-0007](0007-postgres-functions-own-multi-table-writes.md). It expands the reasoning and doesn't change the decision. The sections above stay as written, apart from pointers to this section.

**Microservices were feasible.** A tightly coupled workflow doesn't force tightly coupled services. An orchestrator or saga could drive the event lifecycle across separately deployed services that each own their data, and a network boundary would enforce the module rules that convention enforces here. The case against microservices is that the cost outweighs the benefit at this scale, not that they couldn't work.

**The coupling moves rather than disappears.** Between services it sits in API and event contracts. A rule change that spans the lifecycle would mean coordinated, versioned contract changes and ordered deploys, where here it is one pull request and one deploy. That matters because the customer confirmed that change can happen at any time, which is the maintainability requirement in Context.

**Which integrity guarantees depend on one database.** The double-booking constraint alone doesn't: a venue service that owned `venue_bookings` could keep it. The transactions that cross domains do:

- `safety_approve_event` locks the event, its venue bookings and its equipment requests together.
- `transition_event` updates `events` and `venue_bookings`, and writes the history and notifications in the same transaction.

Split across services, these become sagas with compensating steps. ADR-0007 rejects that approach for PostgREST calls, and the objection carries over: a crash between steps leaves partial state, and the compensation is a second thing to get wrong. The customer also requires that the system never shows contradictory information about one event (NFR-R1).

**The module boundaries today.** The "only cross-module call" line under Consequences no longer holds. On `main` at `9b5052c`:

- There are five cross-module service imports: `events` → `equipment`, `venues` and `registrations`; `equipment` → `events`; `venues` → `events`. So `events` and `equipment` import each other, and so do `events` and `venues`.
- Nine files make ten imports of another module's `schemas.py`, which Confirmation rule 2 doesn't allow. For example, `equipment/router.py` and `venues/router.py` both import `ReReviewSendRequest` from `events.schemas`.

This is a third case of the erosion described under Negative consequences. Nothing fails because of it, but the extraction path is narrower than the ADR implies: a two-way dependency has to be broken before either module can move. The shared types need either moving to a common place or a decision that allows them, which would be its own ADR.

## Links

- `docs/PROJECT_OVERVIEW.md` §5 — the original architecture narrative
- `docs/REQUIREMENTS.md` §3.2 — container decisions table, §3.3 — component diagram
- `docs/PROJECT_OVERVIEW.md` §2.3 — the customer's non-functional requirements
- [`docs/archive/2026-09-13-design-review.md`](https://github.com/chasingsunsets/ConnectSphere/blob/91fec10aab05070169286fbbed5268fef9cf6930/docs/archive/2026-09-13-design-review.md) §A3 — design improvements that build on this structure
- [ADR-0007](0007-postgres-functions-own-multi-table-writes.md) — constraints and single-function writes, and why compensation was rejected
