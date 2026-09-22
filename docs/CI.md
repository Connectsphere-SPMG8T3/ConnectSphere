# Continuous Integration

**What CI checks today, what it deliberately does not, and what is left to build.**

This file is the single reference for ConnectSphere's automated checks. It sits apart from `DEFINITION_OF_DONE.md` (which says what *a task* must clear) because CI is a standing property of the repository that changes on its own schedule.

_Last updated: 2026-09-22 — first version, written when `.github/workflows/ci.yml` was added on `chore/ci-pipeline` (PR #25)._

---

## 1. What runs today

One workflow, `.github/workflows/ci.yml`, named **CI**. Two jobs run in parallel.

| Job | Steps | Measured |
|---|---|---|
| **Backend (pytest)** | Python 3.11 → `pip install -r requirements.txt` → `pytest` | 207 tests, 27s on the runner (14.5s locally) |
| **Frontend (vitest + build)** | Node 20 → `npm ci` → `npm test` → `cp .env.example .env` → `npm run build` | 312 tests across 23 files, 39s on the runner (46s locally) |

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

GitHub Free includes 2,000 Actions minutes/month for private repositories; Linux runners bill at $0.006/minute beyond that. A full run bills **2 minutes** — GitHub rounds each job up to a whole minute separately. At roughly 20 PRs a month with a few pushes each, that is about 160 minutes, under 10% of the allowance.

---

## 2. What CI proves, and what it does not

This distinction matters more than the job list. It is the honest answer to "would CI catch a broken feature?".

**It proves:** the code imports, both suites pass, and the frontend produces a production bundle. A change that breaks something already written down gets caught.

**It does not prove the system works.** All 519 tests run against mocks — all 8 backend test files mock the Supabase client, and the frontend specs mock `fetch` and the Supabase SDK. Nothing in CI touches a real database, a real PostgREST instance, or a real browser.

That gap is not theoretical. It has already cost this project three times:

- **SCRUM-48 and defect D1** — both passed a fully mocked suite and appeared only against the real Supabase project (root `AGENTS.md`, "Verification").
- **`PGRST201`** — a PostgREST embed that fails the whole query when a table has two foreign keys to the same target. `IMPLEMENTATION_MAP.md` §5 records it plainly: *"Mocked tests cannot catch this; it only appears against a real database."*

So: **CI is a regression gate, not an integration gate.** Until §4 item 3 lands, "verified against the real system" in `DEFINITION_OF_DONE.md` Phase 2 stays a human step that no workflow checks.

---

## 3. Deliberately not included

Each of these was considered when the pipeline was built and left out for a stated reason, not overlooked.

| Not included | Why | Cost to add |
|---|---|---|
| `ruff` (lint) | Has never run over this codebase. Blocking on it would have held the first pipeline red pending an open-ended cleanup, delaying the evidence that CI exists at all. | ~half a day including the first cleanup |
| Coverage reporting | Needs `pytest-cov` (not in `requirements.txt`) and a threshold the team agrees on. | ~1 hour to report; the threshold is a team decision |
| Integration tests against a real database | The largest item, and better placed before Sprint 3's database-heavy stories than bolted on after. See §4. | ~half a day |
| End-to-end browser tests | No Playwright or Cypress installed. `PROJECT_REVIEW.md` §194 parks the end-to-end workflow test in Sprint 4. | ~half a day for one journey |
| Branch protection | Not part of CI at all — a repository setting, needing admin rights. See §4 item 1. | ~5 minutes |

---

## 4. What is left to do

Ordered by cost-to-value, with the sprint each belongs in.

### 1. Branch protection — 5 minutes, needs repo admin

**Branch protection is not part of the CI pipeline.** CI is the workflow that runs the checks; branch protection is the repository setting that makes them *binding*. The pipeline works either way. Without protection, a pull request with a red run can still be merged, so "CI is green on the PR" in `DEFINITION_OF_DONE.md` Phase 4 is advisory rather than enforced.

Suggested settings on `main`: require the status checks `Backend (pytest)` and `Frontend (vitest + build)`, require a pull request with 1 approving review, and leave *Include administrators* off so there is an escape hatch.

### 2. Coverage reporting — ~1 hour

Add `pytest-cov` and run `pytest --cov=app --cov-report=term-missing`, printing the summary on the PR. Report before enforcing: agree a threshold once the team can see the real number. This is the first half of the item parked under "Not yet enforceable" in `DEFINITION_OF_DONE.md`.

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

**Use the ephemeral local stack, never the hosted project.** Six developers' test runs writing to one shared database is the collision `PROJECT_REVIEW.md` item 10 warns about for migrations, and tests are designed to write. Supabase's Branching feature gives a real per-PR database but is not on the Free plan (Pro at $25/month plus $0.01344 per branch-hour) and buys nothing the local stack does not.

### 4. One real-database test per database-backed story — ~10 minutes each, during Sprint 3

Not a task. A line in the Definition of Done: **a story that touches the database ships one test against a real database.**

Rules only the database can enforce cannot be tested any other way — the `venue_bookings` exclusion constraint (DB-1) and all-or-nothing equipment reservation (DB-4) are invisible to a mock by construction. Written by the story's author while they have the context, each is about ten minutes; retrofitted later by someone else, the same coverage is a multi-day job. Expect five or six across the whole project, not one per endpoint.

### 5. `ruff` — ~half a day, optional

Add to `requirements.txt` and run `ruff check .` in the backend job. Start non-blocking (`continue-on-error: true`) to size the cleanup without stopping merges, then make it blocking once the tree is clean.

### 6. End-to-end browser test — ~half a day, Sprint 4

One Playwright run through the reference workflow in `SCENARIO.md` §2.2, against the stack from item 3. One journey, not a suite. `PROJECT_REVIEW.md` §179 already reserves room for this in the showcase sprint.

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

- `docs/DEFINITION_OF_DONE.md` — where "CI is green on the PR" sits as a Phase 4 gate, and the targets still parked as unenforceable.
- `docs/PROJECT_REVIEW.md` A9 — the original recommendation, with what shipped and what did not.
- `docs/IMPLEMENTATION_MAP.md` §5 — the one-paragraph version for someone starting a story.
- `docs/adr/0001` and `0002` — structural rules CI does **not** check, and why they remain review checks.
