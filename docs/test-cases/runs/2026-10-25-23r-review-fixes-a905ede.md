# 23-R / D57–D58 verification — local and rollback checks — 2026-10-25 SGT

| | |
|---|---|
| Story / fix | 23-R, D57, D58 |
| Base | `a905ede` + uncommitted changes on `feature/scrum-23-r-equipment-availability` |
| Worktree | `/home/jclim/projects/ConnectSphere-pbi-23-r` |
| Environment | Candidate DDL and own SQL fixtures inside BEGIN/ROLLBACK against shared Supabase; offline unit suites; branch servers on 8013/5179 |
| Run by | Codex automated checks; Claude read-only review explicitly authorized by developer |

| Check | Result | Detail |
|---|---|---|
| D58 API RED | Expected fail | Two equivalent-UUID cases returned 200 instead of 422 before validation |
| D58 Vue RED | Expected fail | Added duplicate demand sent a check and showed no combine-quantities guidance |
| D57 SQL RED | Expected fail | Existing RPC returned 5 free for retired stock instead of 0 |
| D57 inventory RED | Expected fail | Two inventory modes showed 2 available for retired stock; repository discarded status (3 failures) |
| Focused equipment unit suite | Pass | 39 tests; active/maintenance/retired, window and no-window, counters preserved |
| Focused Vue suite | Pass | 23 tests, including correcting a duplicate and submitting distinct selections |
| TC-EQR-038 candidate SQL | Pass within rollback only | Retired zero, total/outage/reserved counters, held reservation survives, exclude-self zero, actual time-change Re-review and re-reserve insufficient, partial maintenance and restored active stock |
| TC-EQR-042 real API | Pass | [Recorded live check](2026-10-25-0151-api-db-a905ede.md) |
| TC-EQR-043 real browser | Pass | [Recorded browser check](2026-10-25-0153-e2e-a905ede.md) |
| TC-EQR-040 | Blocked at 3 widths | Missing deployed storage_location column |
| Production frontend build | Pass | Vite build completed |
| Full backend coverage | Pass | Final 1887 passed, 97.44%; no uncovered changed executable statements. One existing Starlette/AnyIO deprecation warning. Initial pre-inventory-fix run also passed 1880 tests. |
| Full frontend coverage | Pass | Final full run with --maxWorkers=1: 1503 passed (97 files), 97.44%; all changed Vue lines covered. Earlier four failures and the diagnostic failure were not reproduced in the final run; no unrelated code or tests changed. |
| Claude review | Findings addressed or evaluated | Inventory mismatch fixed with RED/GREEN; actual SQL reserve/recheck behavior tested/documented; throwaway cleanup confirmed. Session `d8dfb35c-4cb8-4bc6-93a7-4187a6345a15` |
| Shared cleanup | Pass | After final rollback, zero own equipment/event fixture rows remain; both migration ledger/column checks still absent |
| Shared deployment | Not deployed | Both 23-R migrations remain local; candidate SQL was rolled back |
| Isolated test stack | Blocked | No installed container runtime/native CLI stack command and no existing hosted branch; paid resource not created |
| TC-EQR-041 developer manual pass | Not run | Real results remain blocked pending migration in a test environment |

Earlier full live regressions remain recorded; this follow-up did not repeat the entire live suite or reset shared fixtures. Shared deployment, post-deployment advisor comparison, developer acceptance and integration gates remain pending.

| Initial frontend failure / diagnostic | Observation |
|---|---|
| `OrganiserDashboard > renders every owned event with key details in separate drafts and requests sections` | 5000ms timeout in initial full coverage run; passed in one-worker diagnostic |
| `CoordinatorEventView > goes back to the Events view, not the dashboard Overview` | 5000ms timeout in initial full coverage run; passed in diagnostic |
| `CoordinatorEventView > an affected venue booking > shows why a planning event's venue is unavailable and opens venue search to replace it` | Initial run and diagnostic navigation assertion stayed coordinator-event instead of venue-search |
| Same affected-venue case for safety_review | Initial full run navigation assertion; passed in diagnostic |

| Advisor baseline (no migration persisted) | Observed notices |
|---|---|
| Security | 2 RLS-without-policy informational notices; existing [leaked-password protection warning](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection) |
| Performance | 1 unindexed FK, 9 [RLS initplan warnings](https://supabase.com/docs/guides/database/database-linter?lint=0003_auth_rls_initplan), 3 unused-index notices |
