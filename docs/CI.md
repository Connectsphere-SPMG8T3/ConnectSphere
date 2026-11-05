# Continuous Integration

**What CI checks today, what it deliberately does not, and what is left to build.**

This file is the single reference for ConnectSphere's automated checks. It sits apart from `DEFINITION_OF_DONE.md` (which says what *a task* must clear) because CI is a standing property of the repository that changes on its own schedule.

_Last updated: 2026-11-05 — §1 Cost: the repository is public, so Actions runs are free (`chore/mutation-test-gaps`). 2026-10-17 — §3: the manual **Mutation testing** workflow, which runs only from the Actions tab and never gates a PR (`chore/mutation-testing`). 2026-10-16 — §3: mutation testing added as a local, non-gating practice (`chore/mutation-testing`, see `MUTATION_TESTING.md`). 2026-10-06 — §1, §4 item 2: both jobs now measure coverage, fail below a floor, and publish a summary and the reports (`chore/coverage-reporting`). Earlier the same day — §4 item 2: the team's coverage target (100% of `backend/app/` and `frontend/src/`, exclusions stated) and how CI will get there; Definition of Done references now point at its new sections and `DEVELOPMENT_WORKFLOW.md` (`chore/docs-scrum-playbook`). 2026-09-28 — §1: both jobs upload a JUnit report as a run artifact, kept 90 days, as the unit suites' execution record (`docs/test-cases/runs/README.md`). 2026-09-27 — §3: Playwright specs and a live-check script now exist, run locally rather than in CI (`chore/automated-live-checks`). 2026-09-22 — first version, written when `.github/workflows/ci.yml` was added on `chore/ci-pipeline` (PR #25). Same day: recorded the decision not to point CI at the hosted Supabase project (§4 item 3), after checking the live plan and project count._

---

## 1. What runs today

One workflow, `.github/workflows/ci.yml`, named **CI**. Two jobs run in parallel.

| Job | Steps | Measured |
|---|---|---|
| **Backend (pytest)** | Python 3.11 → `pip install -r requirements.txt` → `pytest --junitxml --cov` (fails below the coverage floor) → coverage table to the run summary → upload `backend-test-report` | 634 tests, 43s locally with coverage (2026-10-06). 207 tests took 27s on the runner on 2026-09-22. |
| **Frontend (vitest + build)** | Node 20 → `npm ci` → `npm run test:coverage` (JUnit reporter; fails below the coverage floor) → coverage table to the run summary → upload `frontend-test-report` → `cp .env.example .env` → `npm run build` | 578 tests across 48 files (2026-10-06). 312 tests took 39s on the runner on 2026-09-22. |

**Test reports.** Each job uploads its per-test results as a JUnit XML artifact (`backend-test-report`, `frontend-test-report`) on every run, including failed ones, kept for 90 days. Each artifact also holds that job's coverage report: `coverage.xml` for the backend, and `coverage/` for the frontend (open `coverage/index.html` to see each file's uncovered lines). Both jobs also add a coverage table to the run's **Summary** page. Find them under the run's **Artifacts** in the Actions tab. They are the execution record for the mocked suites; runs against the real system are logged in `docs/test-cases/runs/`.

**Triggers:** `pull_request` into `main`, and `push` to `main`. A push to a feature branch with no open PR runs nothing — deliberate, to keep intermediate pushes off the minute budget. A branch's first run therefore appears when its PR is opened.

**Versions** come from what the project already pins: Python 3.11 from `backend/Dockerfile`, Node 20 from the `node:20-alpine` image in `docker-compose.yml`. If either moves, move it here too.

**Caching:** pip and npm caches keyed on `backend/requirements.txt` and `frontend/package-lock.json`.

**Concurrency:** a `concurrency` group cancels a run still in flight when the same branch is pushed again, so three quick pushes to one PR bill as one run.

### No secrets, and it must stay that way

Neither job reads a repository secret, and nothing in CI touches the hosted Supabase project.

- The backend suite injects fake Supabase credentials at import time in `backend/tests/conftest.py`.
- The frontend build copies `frontend/.env.example`, which holds the project URL and a placeholder publishable key. Neither is a secret.

**A test that needs real Supabase credentials will pass locally and fail in CI.** Put it behind a pytest marker and run it locally, or wait for the integration job in §4 — do not add a secret to make it pass. The secret key never belongs in a workflow, a `VITE_*` variable, a build log, or a screenshot (root `AGENTS.md`, "Security baseline").

### Cost

The repository is public, so runs on GitHub's standard runners are free and don't use a monthly minutes allowance.

---

## 2. What CI proves, and what it does not

This distinction matters more than the job list. It is the honest answer to "would CI catch a broken feature?".

**It proves:** the code imports, both suites pass, and the frontend produces a production bundle. A change that breaks something already written down gets caught.

**It does not prove the system works.** All 519 tests run against mocks — all 8 backend test files mock the Supabase client, and the frontend specs mock `fetch` and the Supabase SDK. Nothing in CI touches a real database, a real PostgREST instance, or a real browser.

That gap is not theoretical. It has already cost this project three times:

- **SCRUM-48 and defect D1** — both passed a fully mocked suite and appeared only against the real Supabase project (root `AGENTS.md`, "Verification").
- **`PGRST201`** — a PostgREST embed that fails the whole query when a table has two foreign keys to the same target. `IMPLEMENTATION_MAP.md` §5 records it plainly: *"Mocked tests cannot catch this; it only appears against a real database."*

So: **CI is a regression gate, not an integration gate.** Until §4 item 3 lands, "verified against the real system" (`DEFINITION_OF_DONE.md`, Testing; `DEVELOPMENT_WORKFLOW.md` §2) stays a human step that no workflow checks.

---

## 3. Deliberately not included

Each of these was considered when the pipeline was built and left out for a stated reason, not overlooked.

| Not included | Why | Cost to add |
|---|---|---|
| `ruff` (lint) | Has never run over this codebase. Blocking on it would have held the first pipeline red pending an open-ended cleanup, delaying the evidence that CI exists at all. | ~half a day including the first cleanup |
| Integration tests against a real database | The largest item, and better placed before Sprint 3's database-heavy stories than bolted on after. See §4. | ~half a day |
| End-to-end browser tests | Playwright is installed, and `frontend/e2e/` runs sign-in, session, logout, route-guard and role-switch specs, but **locally, against the live project**, next to `backend/scripts/verify_live.py` (`docs/test-cases/runs/README.md`). They need running servers and real credentials, and item 3 below keeps the hosted project out of CI. Running them in CI waits on the local stack from item 3. | ~2 hours once item 3 exists |
| Mutation testing (mutmut, StrykerJS) | Runs take minutes, and some survivors are harmless by nature (wording, equivalent mutants, query building only a real database can check), so a score threshold would fail runs for no real defect. It is run by hand per PR and at sprint end instead ([`MUTATION_TESTING.md`](MUTATION_TESTING.md), [Team decision] 2026-10-16). The separate **Mutation testing** workflow (`.github/workflows/mutation.yml`) runs the backend half on demand from the Actions tab, for Windows users; it is never triggered by a PR or push. | Already done as a manual workflow; not to be made a PR check |
| Branch protection | Not part of CI at all — a repository setting, needing admin rights. See §4 item 1. | ~5 minutes |

---

## 4. What is left to do

Ordered by cost-to-value, with the sprint each belongs in.

### 1. Branch protection — 5 minutes, needs repo admin

**Branch protection is not part of the CI pipeline.** CI is the workflow that runs the checks; branch protection is the repository setting that makes them *binding*. The pipeline works either way. Without protection, a pull request with a red run can still be merged, so "merged only after CI passes" in `DEFINITION_OF_DONE.md` (Code) is checked by the reviewer rather than enforced.

Suggested settings on `main`: require the status checks `Backend (pytest)` and `Frontend (vitest + build)`, require a pull request with 1 approving review, and leave *Include administrators* off so there is an escape hatch.

### 2. Coverage — done on `chore/coverage-reporting`, raised each sprint

**The target — [Team decision], 2026-10-06.** 100% line coverage of everything we write: `backend/app/` and `frontend/src/`. The only exclusions are listed in the table below, each with the reason it can't be covered. The team's Definition of Done says "100% code coverage". The course rubric's top band for "Testing and traceability" says *"100% coverage unless not possible and stated why"*. The target covers both layers because neither says backend only, and the frontend holds real logic in its stores, composables and components.

**What a PBI must meet** (`DEFINITION_OF_DONE.md`, Testing): its new and changed code is fully covered, or the PR lists each uncovered line and the reason. CI checks only the totals, so the reviewer checks this by looking at the changed files in the coverage report.

**How to measure it.** Always run the full suite, because a subset falls below the floor and fails.

| Stack | Command | Settings |
|---|---|---|
| Backend | `pytest --cov` from `backend/` | `backend/.coveragerc`: source `app`, line coverage, `fail_under` |
| Frontend | `npm run test:coverage` from `frontend/` | `coverage` in `frontend/vite.config.js`: `src/**`, the exclusions, `thresholds.lines`. Writes `frontend/coverage/` (gitignored). |

Plain `pytest` and `npm test` don't measure coverage, so day-to-day runs of a single test file aren't affected.

**Baseline and floor.** The floor is the measured number rounded down. CI fails any run that drops below it.

| Stack | Measured on 2026-10-06 | Floor |
|---|---|---|
| Backend `app/` | **92.63%** of lines (1,635 / 1,765). 91% with branches counted. | `fail_under = 92` |
| Frontend `src/` | **94.52%** of lines (8,799 / 9,309). Branches 84.39%, functions 74.42%. | `thresholds.lines: 94` |

**Raising the floor.** At the end of each sprint, set each floor to the new measured number, rounded down, and record it in the table above. The floors only go up, reaching 100 for the Sprint 4 showcase (3 Nov). Lowering one needs the team's agreement and a reason written here.

**Standing exclusions.** Anything not listed here counts against the target.

| Path | Why it isn't covered |
|---|---|
| `frontend/src/main.js` | It only mounts the app when a browser loads the page, so there is nothing for a unit test to call. Every Playwright run exercises it (`frontend/e2e/`). |

The backend has no exclusions.

**Where the gaps are** (2026-10-06; both stacks reached 100% on `chore/mutation-test-gaps`, 2026-11-05):

- **Backend.** Most of the 130 uncovered lines are in the three repository modules: venues 44%, equipment 62%, events 66%. These are the Supabase query wrappers that the mocked tests replace. Covering them honestly means tests against a real database (item 3), not more mocks. Two smaller gaps:
  - `app/db/session.py` (0%) was imported nowhere, so it was deleted.
  - The `/health` endpoint in `app/main.py` has no test.
- **Frontend.** These files are at 0%: `App.vue`, `components/common/Toast.vue` and `services/supabase.js`. `LoginView.vue`, `VenueSearchView.vue`, `services/api.js` and `stores/auth.js` are at 67–74%. The function figure (74%) is lower than the line figure mostly because of event handlers that no test triggers.

### 3. Endpoint smoke test against a real database — ~half a day, start of Sprint 3 (6 Oct)

**This is the item that changes what CI is worth,** and the one that makes "tests the system" true.

Add a job that runs `supabase start` (the full local stack in Docker: Postgres, GoTrue, PostgREST), applies the migrations, seeds, and sends one real request to every mounted endpoint.

**Do not hand-write a test per endpoint.** Extend the pattern already in `backend/tests/test_active_role_access.py`, whose `_protected_routes()` iterates `app.routes` and whose `_concrete()` fills each `{param}` with a UUID. Its docstring states the property to preserve: *"The matrix runs over every route the app mounts, so a new endpoint is covered automatically."* The smoke test is that same enumeration with two swaps:

- the mocked Supabase client becomes the real local stack;
- the assertion becomes **no 5xx and no `PGRST` error**, rather than a specific status.

That assertion is endpoint-agnostic — against an unseeded UUID, 404, 403 and 422 are all healthy; a 500 or a malformed-query error never is. So the marginal cost of a new endpoint is **zero**: add a route in Sprint 3 and it is covered on the next run with nobody remembering to do anything. This is what keeps the pipeline "comprehensive" as the API grows from 14 endpoints to 40.

Two known limits, so nobody is surprised:

- Endpoints needing a real row to be interesting (`GET /venues/{venue_id}`) just 404 on a random UUID. Register seeded ids in a small map keyed by path parameter — about four entries covers today's 14 endpoints, and it grows per *kind of resource*, not per endpoint.
- Write endpoints mostly answer 422 on an empty body. That still proves the route is wired, validation runs and the database is reachable, but it is not deep coverage. Depth is item 4.

**Use the ephemeral local stack, never the hosted project.** The reasoning is below, because this gets proposed regularly.

#### Why not the hosted Supabase project — [Team decision]

Supabase's own CI guidance uses the local stack: the example in [Local development → testing](https://supabase.com/docs/guides/local-development/testing/overview) runs `supabase start` and then the tests, with no hosted connection. It also warns that application tests should not depend on a clean database state, because that "makes tests difficult to parallelize".

This project's situation makes the case stronger. Checked live on 2026-09-22:

| | |
|---|---|
| Organisation plan | **free** |
| Projects | **exactly one** — `ConnectSphere` (`vuiryrzzyfecjqftwicj`), ap-southeast-1, `ACTIVE_HEALTHY` |

**There is no staging environment.** The hosted project is simultaneously the development database, the demo database, and the graded evidence. Pointing CI at it would mean:

1. **Tests write, and the demo is what they write to.** The database shown at the Sprint 4 showcase would be whatever the last CI run happened to leave behind.
2. **It invalidates the manual test evidence.** The Venue Staff and Technical Support dashboard cases in `docs/test-cases/dashboards.md` trace explicitly "against real seeded data". Those cases assume a stable seed; CI churning it breaks the trace from test case to result.
3. **It forces the secret key into CI.** The backend cannot reach Postgres without it, and that key **bypasses RLS** (root `AGENTS.md`, "Security baseline"). This repository has already failed GitGuardian twice over generated secrets (PRs #4 and #6 — `IMPLEMENTATION_MAP.md` §5). CI currently needs **zero** secrets; that is a property to keep, not to trade away.
4. **Free projects pause after about a week of inactivity.** CI would then go red across a quiet recess week for reasons unrelated to any code — directly undermining "reliably" in the grading rubric.
5. **Concurrent runs collide.** Six developers with overlapping pull requests against one mutable database produces flaky tests: the same collision the design review's A3 item 10 (`archive/2026-09-13-design-review.md`) warns about for migrations, and tests write far more often than migrations do.

**The one honest counter-argument** is configuration drift. A local stack has its own configuration and cannot catch the hosted project's settings changing underneath the code — which is exactly what bit SCRUM-48, recorded in `BUILD_LOG.md` §4.1: a green mocked run *"does not prove the code is compatible with ... the actual live project's configuration (key format, JWT signing scheme, exception types)"*.

**If that recurs, the defensible response is narrow:** a **read-only** health check running **after merge to `main`**, signing in as a seeded account and calling one endpoint, asserting 200. No writes, no schema changes. It needs only the *publishable* key and a seed password already committed in `supabase/seed.sql`, so it introduces no secret that is not already public in this repository. That is the only hosted-project check worth having, and it belongs outside the test suite.

**On Supabase Branching** (a real per-PR database, ephemeral, deleted when the PR closes): the pricing page lists it as a paid line item — Pro at $25/month plus $0.01344 per branch-hour — while the branching documentation says deploying from GitHub works "on any plan". Those do not obviously agree, so check the billing page before assuming either. It is moot regardless: the local stack covers the same bug class for nothing.

### 4. One real-database test per database-backed story — ~10 minutes each, during Sprint 3

Not a task. A line in the Definition of Done: **a story that touches the database ships one test against a real database.**

Rules only the database can enforce cannot be tested any other way — the `venue_bookings` exclusion constraint (DB-1) and all-or-nothing equipment reservation (DB-4) are invisible to a mock by construction. Written by the story's author while they have the context, each is about ten minutes; retrofitted later by someone else, the same coverage is a multi-day job. Expect five or six across the whole project, not one per endpoint.

### 5. `ruff` — ~half a day, optional

Add to `requirements.txt` and run `ruff check .` in the backend job. Start non-blocking (`continue-on-error: true`) to size the cleanup without stopping merges, then make it blocking once the tree is clean.

### 6. End-to-end browser test — ~half a day, Sprint 4

One Playwright run through the reference workflow in `PROJECT_OVERVIEW.md` §2.2, against the stack from item 3. One journey, not a suite. The design review's A3 item 8 (`archive/2026-09-13-design-review.md`) already reserves room for this in the showcase sprint.

---

## 5. How this maps to the grading rubric

The criterion is **"Code quality and CI"** — both halves count, and CI alone does not carry it.

| Band | Wording | State |
|---|---|---|
| Fair | *"refactoring or CI is limited or applied late"* | Cleared. CI landed 22 Sep — end of Sprint 1 of 4, with ~75% of development still ahead. |
| **Good** | *"reasonably modular, with evidence of refactoring and a basic CI pipeline used during development"* | **Where the project is now.** |
| Excellent | *"modular and maintainable, quality practices are sustained, and a comprehensive CI pipeline reliably builds and tests the system"* | Two gaps: **"tests the system"** (item 3) and **"sustained"** (below). |

Two of those words are earned at near-zero cost:

- **"Reliably"** means failures actually block — item 1, five minutes of settings.
- **"Sustained"** and **"used during development"** are evidenced by run history accumulating across Sprints 2–4, and by pull requests carrying teammate approvals. Nobody builds that; you get it by working through PRs and not bypassing review. Conversely, self-merging an unreviewed PR is evidence *against* this band, on the exact criterion being graded.

---

## 6. Day to day

**Reproduce a CI failure locally.** CI runs exactly these, nothing more:

```
cd backend  && pytest
cd frontend && npm test
cd frontend && npm run build
```

**Read a failure** on the pull request's Checks tab. The job name says which stack; the jobs are independent, so one red and one green is normal and means the failure is confined to that stack.

**Known warnings, not failures.** Runs log that `actions/checkout@v4`, `actions/setup-node@v4` and `actions/setup-python@v5` execute on a deprecated Node 20 runtime. That concerns the *actions'* runtime, not the Node 20 that builds the frontend, which is unaffected. Clearing it is a version bump to `checkout@v5`, `setup-node@v5`, `setup-python@v6`.

---

## Related

- `docs/DEFINITION_OF_DONE.md` — where "merged only after CI passes" and the coverage rule sit, and its "Checked by people, not tools (yet)" table.
- `docs/DEVELOPMENT_WORKFLOW.md` §4 — the review step where CI must pass before a PR moves to In Review.
- `docs/archive/2026-09-13-design-review.md` A3 item 9 — the original recommendation, with what shipped and what did not.
- `docs/IMPLEMENTATION_MAP.md` §5 — the one-paragraph version for someone starting a story.
- `docs/adr/0001` and `0002` — structural rules CI does **not** check, and why they remain review checks.
