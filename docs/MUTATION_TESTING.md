# Mutation testing

**Whether our tests would notice a bug, not only whether they run the code.** How to run it, when, what to do with the results, and what it has found.

Coverage says a line *ran* during the tests. Mutation testing changes the code on purpose (`<` to `<=`, `and` to `or`, an argument to `None`, a `continue` to a `break`) and runs the tests again. If they still pass, that change is a **surviving mutant**: a bug of that shape would ship with the suite green. The share of mutants the tests catch (**killed**) is the mutation score.

_Last updated: 2026-10-17 — §3: the manual **Mutation testing** GitHub workflow, the way to run the backend half from Windows. 2026-10-16 — first version: mutmut and StrykerJS added, team decision on how they are used, first baselines (`chore/mutation-testing`)._

---

## 1. Why we use it

Line coverage was already above 95% when mutation testing was first tried on the venues module (2026-10-16). It still found:

- **About 100 unchecked behaviours in `venues/service.py`.** Tests ran the code but didn't check what it saved, sent or read. For example, a venue edit could drop fields from its history snapshot, or read another venue's bookings, and no test failed. The fix was assertions, not new code.
- **Eight authorisation tests that had never run.** While tracing why a mutant survived, four `TestWhoMayRequest` methods (including the SCRUM-76 active-role denial) turned out to be nested inside another function since CR-98, so pytest never collected them (defect D33). The suite stayed green throughout.

Both were fixed on `chore/venues-mutation-test-gaps`; `BUILD_LOG.md` has the details. Neither would have shown up in a coverage report.

## 2. When to run it

**[Team decision] 2026-10-16:** mutation testing is a recommended practice, not a CI gate and not a Definition of Done requirement.

| When | What | Who |
|---|---|---|
| **Before opening a PR that changes logic** (a service, a rules module such as `search.py` or `readiness.py`, a store or composable) | Run it on the module you changed. Spend about 15 minutes on the survivors that matter (§4), then add the missing assertions. | Developer or agent |
| **End of sprint** | Run both tools on everything and add a row to the baselines (§6). Bring anything surprising to the retrospective. | Whoever runs the sprint regression |
| Not needed for | Repository-only, migration, docs and UI-layout changes | — |

**Why it isn't a gate:**
- A score threshold would be noisy. Some survivors are harmless (§5).
- A threshold pushes people towards brittle tests that pin exact wording to "kill" a mutant.
- Runs take minutes, not seconds.

## 3. How to run it

### From GitHub: any computer, including Windows

The **Mutation testing** workflow runs the backend half on GitHub's Linux machines. Nothing to install, and it works from Windows, where mutmut can't run.

1. Open the repository on GitHub and go to the **Actions** tab.
2. In the left sidebar, click **Mutation testing**.
3. Click **Run workflow** (on the right). Choose:
   - **Branch:** the branch to test, usually your feature branch;
   - **Backend code to mutate:** `venues`, `events`, `equipment`, `auth`, `core` (`app/core` and `app/db`) or `all`.
4. Click **Run workflow** again. The run appears in the list within a few seconds.
5. When it finishes (about 3–5 minutes):
   - the run's **Summary** page shows the score per file;
   - the **mutation-report** artifact at the bottom holds `survivors.diff`, every surviving mutant's change, to triage with §4.

**Things to know:**
- The workflow only appears in the sidebar once `.github/workflows/mutation.yml` is on `main`.
- It never runs on its own and never blocks a PR.
- Each run uses about 3–5 of the repository's 2,000 free Actions minutes a month.
- It covers the backend only. Run the frontend locally: StrykerJS works on Windows.

### Backend (mutmut), locally on macOS, Linux or WSL

From `backend/`, with the virtualenv active (`mutmut` is in `requirements.txt`; config in `backend/pyproject.toml`):

```bash
no_proxy='*' mutmut run "app.modules.venues.*"     # one module (recommended)
no_proxy='*' mutmut run                            # everything (about 2 minutes on a laptop)
mutmut results                                     # list survivors
mutmut show app.modules.venues.service.x_update_venue__mutmut_15   # see one mutant's diff
mutmut browse                                      # interactive viewer
```

- **`no_proxy='*'` matters on macOS.** mutmut runs each mutant in a forked process. A mutant that reaches a real HTTP client makes httpx look up the system proxy, which crashes a forked process on macOS. You get a "Python quit unexpectedly" dialog, and a mutant reported as `segfault`. Setting `no_proxy` skips that lookup.
- **On Windows, use the GitHub workflow above** (or WSL). mutmut relies on `fork()`, which Windows does not have.
- `mutmut results --all true | python scripts/mutation_report.py` prints the same per-file table the workflow shows.
- The working copy goes to `backend/mutants/`. That folder is gitignored; delete it whenever you like.

### Frontend (StrykerJS), locally on any OS

From `frontend/` (config in `frontend/stryker.config.mjs`):

```bash
npm run test:mutation -- --mutate "src/stores/**/*.js,!src/**/__tests__/**"   # one area (recommended)
npm run test:mutation                                                          # everything (about 35 minutes)
```

- A `--mutate` flag replaces the config's file list, so **repeat the `!src/**/__tests__/**` exclusion**. Otherwise Stryker mutates the spec files themselves.
- The report is written to `frontend/reports/mutation/index.html` (gitignored). Open it to see each survivor in place.
- StrykerJS is pinned to 9.x because 10.x needs Node 22, and CI and docker-compose run Node 20.

## 4. What to do with survivors

Look at each survivor and ask: *if this were the real code, would a user or another module notice?*

| Fix it (add or tighten a test) | Leave it |
|---|---|
| A condition flipped: `and`↔`or`, `<`↔`<=`, `not` dropped | Message wording only: `"Venue is inactive"` → `"VENUE IS INACTIVE"` (unless the exact text is the requirement) |
| `continue`↔`break`, a loop or filter that is never exercised | **Equivalent mutants** that behave identically, e.g. a default argument that equals the value passed |
| An argument replaced with `None` (a call reads or writes the wrong thing) | **Repository query-building** in `repository.py` (`.eq(None, …)`): only a real database catches these. That is `verify_live.py`'s job. |
| A saved field, notification or history row dropped | Time-zone mutants that only survive because your machine is on UTC+8 (`astimezone(SGT)` → `astimezone(None)`) |
| A fallback (`or "your event"`) never reached | Pure performance short-circuits (`if bookings else {}` → always calling) |

If a test you just wrote passes first time, mutate the line it guards by hand. That is what `BUILD_LOG.md` calls a "mutation check", and it is still worth doing for one-off cases.

## 5. Known limits

- **Route handlers and request validation aren't mutated.** mutmut 3 skips decorated functions, so each `router.py` produces no mutants, and Pydantic field constraints aren't mutated either. The role-gate, 401 and 422 tests therefore kill no mutants. **That does not make them redundant.** They guard code that mutation testing can't see, and AGENTS.md requires them.
- **`.vue` components aren't mutated.** StrykerJS's instrumentation breaks `defineProps()` in `<script setup>`, so only `.js` modules are mutated: stores, composables, services, router, feature helpers. That is about 4,200 of the 7,800 lines of frontend script. Component logic relies on the Vitest component specs and the Playwright checks.
- **A test that kills no mutant is not necessarily useless,** and a test that only kills mutants other tests also kill is not necessarily redundant. Most such tests pin a different acceptance criterion. Don't delete tests based on mutation results alone.
- **`core/exceptions.py` scores low (54%)** because most of its mutants change error-message strings. That is expected.

## 6. Baselines

The score is killed ÷ all mutants. "Reached" leaves out mutants that no test executes; for the backend that is `repository.py` code the API tests mock out.

### Backend (`main` at `d059dbb`, 2026-10-16)

5,874 mutants in 2 min 11 s (8 workers, Apple Silicon laptop).

| File | Killed | Survived | No test | Score | Reached |
|---|---:|---:|---:|---:|---:|
| `core/exceptions.py` | 109 | 93 | 0 | 54% | 54% |
| `core/security.py` | 80 | 22 | 0 | 78% | 78% |
| `db/supabase.py` | 23 | 1 | 0 | 96% | 96% |
| `auth/service.py` | 126 | 40 | 0 | 76% | 76% |
| `equipment/repository.py` | 48 | 186 | 68 | 16% | 21% |
| `equipment/service.py` | 373 | 51 | 0 | 88% | 88% |
| `events/lead_scope.py` | 28 | 0 | 0 | 100% | 100% |
| `events/lifecycle.py` | 10 | 0 | 0 | 100% | 100% |
| `events/readiness.py` | 37 | 0 | 0 | 100% | 100% |
| `events/repository.py` | 624 | 211 | 61 | 70% | 75% |
| `events/schemas.py` | 16 | 10 | 0 | 62% | 62% |
| `events/service.py` | 1,191 | 376 | 0 | 76% | 76% |
| `venues/impact.py` | 67 | 13 | 0 | 84% | 84% |
| `venues/repository.py` | 502 | 183 | 356 | 48% | 73% |
| `venues/schemas.py` | 11 | 1 | 0 | 92% | 92% |
| `venues/search.py` | 156 | 11 | 0 | 93% | 93% |
| `venues/service.py` | 678 | 112 | 0 | 86% | 86% |
| **Total** | **4,079** | **1,310** | **485** | **69%** | **76%** |

`chore/venues-mutation-test-gaps` (on top of CR-94) raises `venues/service.py` to 848 of 860 killed and `venues/search.py` to 159 of 163.

**Where to look next:** `events/service.py` (376 survivors), `auth/service.py` and `core/security.py`. The last two are the authentication path, where an unchecked branch matters most.

### Frontend (`main` at `d059dbb`, 2026-10-16)

4,091 mutants in 35 min 24 s (`.js` modules only, §5). Timeouts count as killed: the mutant made the code hang, which the tests noticed.

| Area | Killed (incl. timeout) | Survived | No test | Score | Reached |
|---|---:|---:|---:|---:|---:|
| `features/venues/` | 1,340 | 345 | 77 | 76% | 80% |
| `features/events/` | 924 | 245 | 45 | 76% | 79% |
| `features/equipment/` | 142 | 33 | 7 | 78% | 81% |
| `router/index.js` | 166 | 46 | 1 | 78% | 78% |
| `stores/` (`auth.js`, `events.js`) | 271 | 93 | 48 | 66% | 74% |
| `services/` (`api.js`, `supabase.js`) | 95 | 14 | 148 | 37% | 87% |
| `components/common/dateFormat.js` | 23 | 10 | 0 | 70% | 70% |
| `composables/` | 6 | 8 | 4 | 33% | 43% |
| **Total** | **2,967** | **794** | **330** | **73%** | **79%** |

`services/` scores low only because the specs mock `@/services/api` (`AGENTS.md`), so most of `api.js` never runs in a unit test. The live browser checks cover it.

**Where to look next:**
- `stores/auth.js`. It is the session and refresh path, which has hit defects before (D1, D4).
- `features/events/timezones.js` (44%).
- `features/venues/venueEditStore.js` (47%).
- `composables/useSidebarState.js` (14%).

## 7. How this supports the rubric

The course rubric rewards **"100% coverage unless not possible and stated why"** under testing, and **"quality practices are sustained"** under code quality ([`CI.md`](CI.md) §5). Mutation testing is not required by either, but it supports both:

- **Coverage says the code ran; mutation testing shows the tests would catch it breaking.** The baselines above are measured evidence of how good the tests are, not just how many there are.
- **It turns gaps into traceable fixes.** Each finding becomes a named test (and, for D33, a defect) recorded in `BUILD_LOG.md`.
- **The end-of-sprint baseline row is evidence that the practice is sustained.** Keep adding one each sprint.

## Related

- [`CI.md`](CI.md): what CI checks (mutation testing deliberately is not one of them, §3).
- [`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md) §2 and "End of sprint": where the two runs sit in the workflow.
- [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md): the coverage rule mutation testing complements.
- [`BUILD_LOG.md`](BUILD_LOG.md): the venues findings and this tooling's entry.
