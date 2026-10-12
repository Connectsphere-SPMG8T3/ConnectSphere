# ConnectSphere — Definition of Done

**What a Product Backlog Item (PBI) must meet before it counts as Done.** Use it as a checklist when you review a PBI.

The team agreed this DoD in the [Team A-HA! Scrum Playbook](https://docs.google.com/document/d/1wd96yzFLZQ1FNZQFfbxzSQvRzzqs9ZJkgrZUEBKbItg/edit) §6, which applies from Sprint 3 (6 Oct 2026). The **General**, **Code**, **Testing** and **Quality** sections below are that DoD, with each item spelt out for this repository. **ConnectSphere specifics** adds the checks this codebase needs on top of it.

This file says *what* to check. *How* to get there (branching, TDD, the live checks, who does each step) is in [`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md).

_Last updated: 2026-10-13 — Done also needs the PBI's row in the sprint's DoD tab to show ✅ Done, with its ticks updated before the PR and the merge (`chore/backlog-notes-column`)._

---

## The rules

- A PBI is Done only when it meets **every applicable item** below. An item that can't apply (for example, the database items for a PBI with no schema change) is skipped, not ticked.
- A PBI that is not Done by the end of the sprint **returns to the Product Backlog**. It does not count towards velocity and is not part of the Increment. There is no partial credit.
- Done is recorded by setting the PBI's **Status** to Done and filling **Met DoD?** in the [Product backlog sheet](https://docs.google.com/spreadsheets/d/18y09jIMc9t1FtvTEM_6u74uWNAg8hrW0eF_LehVgWVY/edit), and only once its row in the sprint's **DoD (Sprint N)** tab shows ✅ Done. Keep that tab's ticks current: the developer updates them before opening the PR and again before merging ([`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md) §4–5).

## General

- [ ] All acceptance criteria are met, **demonstrated to the PO, and approved by the PO**.
- [ ] All tasks broken down from the PBI in the sprint tab are Done.

## Code

- [ ] The code is reviewed and **approved by at least one other Developer** on a GitHub pull request. Self-merging an unreviewed PR does not count. Review comments are resolved, or captured as new PBIs rather than dropped.
- [ ] The pull request is merged into `main` **only after CI passes** and the review approval is given.
- [ ] The build passes with **no critical warnings**: no warnings from our own code in the build, test or browser-console output (Vue warnings, unhandled promise rejections, deprecations in our code). Third-party warnings already listed under "Known warnings" in [`CI.md`](CI.md) §6 don't block.

## Testing

- [ ] All unit and integration tests pass in the CI pipeline: the **full** backend (`pytest`) and frontend (Vitest) suites, not only the new tests.
- [ ] Functional and UI behaviour is verified against the acceptance criteria:
  - the live checks were run with recording on (`verify_live.py --record`, `npm run test:e2e:record`);
  - the developer's manual browser pass is recorded;
  - both go in [`test-cases/runs/`](test-cases/runs/README.md).
- [ ] Developed **test-first** (red, green, refactor): a failing test, then the minimum code to pass it, then refactoring with the suite green. The playbook requires this for backend functions. This repository applies it to frontend logic too (root `AGENTS.md`, "Test-driven development").
- [ ] **100% code coverage** of the new and changed code in `backend/app/` and `frontend/src/`, or every uncovered line is listed with the reason it can't be covered. This follows the course rubric: *"100% coverage unless not possible and stated why."* How coverage is measured, and the standing exclusions, are in [`CI.md`](CI.md) §4 item 2.
- [ ] Tests cover the normal path, boundaries, conflicts, failures **and authorisation denials**. Every acceptance criterion traces to a test case (`TC-*`) and an automated test in the story's traceability table in [`test-cases/`](test-cases/README.md).

## Quality

- [ ] During the PO demo, the application runs **without crashes or unhandled errors** (no uncaught errors in the browser console, no 5xx in the backend log), and pages load without noticeable delay.

## ConnectSphere specifics

**Security** (root `AGENTS.md`, "Security baseline")

- [ ] Every new endpoint, RLS policy, page and route guard checks **role *and* the caller's relationship to the resource**, gated on the session's **active** role. A test proves that a user acting as another role gets 403 (SCRUM-76).
- [ ] No secrets in the diff: never `.env`, keys or tokens. The secret key never reaches the frontend, a `VITE_*` variable, logs, docs or screenshots.

**Database** (only when the PBI changes the schema)

- [ ] The migration is in `supabase/migrations/` and reaches the shared Supabase project **through the merged PR**, never applied by hand.
- [ ] `supabase db push` runs clean, and the Supabase advisors show **no new** security or performance findings.
- [ ] Verification SQL is added under `supabase/verification/`, and anything that crosses an integration boundary (Supabase Auth, PostgREST, RLS, the browser) was verified against the real system, not only against mocks.

**Paper trail** (graded evidence)

- [ ] [`REQUIREMENTS.md`](REQUIREMENTS.md) matches the behaviour, or the deviation is recorded as **[Assumption]** or **[Team decision]**, citing the `QA-<row>` behind it.
- [ ] [`IMPLEMENTATION_MAP.md`](IMPLEMENTATION_MAP.md) is updated in place.
- [ ] A [`BUILD_LOG.md`](BUILD_LOG.md) §4 entry is appended.
- [ ] [`DEFECTS.md`](DEFECTS.md) is updated for any defect found or fixed.
- [ ] New test cases are in `test-cases/<area>.md` with their Type, Created and Last run columns, and the run logs are committed on the branch.
- [ ] Any customer clarification found during the work is recorded in the Product backlog's **Customer clarification** column, with its session and date.

---

## Checked by people, not tools (yet)

Two items above are only as strong as the reviewer, because no tool enforces them today:

| Item | Why a tool doesn't enforce it | What closes the gap |
|---|---|---|
| Merge only after CI passes | Branch protection is off on `main`, so a PR with a failing run can still be merged ([`CI.md`](CI.md) §4 item 1). | A repo admin turns on branch protection. |
| 100% coverage of new and changed code | CI fails a run only when *total* coverage drops below the floor. It doesn't check which lines a PR changed. | The reviewer opens the run's coverage report and checks the changed files ([`CI.md`](CI.md) §4 item 2). |

Until those land, the reviewer checks both by hand and writes in the PR if they couldn't.

## Maintaining the DoD

The whole team agreed on this DoD. We review it at each sprint retrospective and update it when we find gaps, for example when a bug is found in an item already marked Done. Change the playbook first, then this file to match, on a `chore/` branch.

## Related

- [`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md) — how a PBI moves from Ready to Done, step by step, and who owns each step.
- [`CI.md`](CI.md) — what the automated checks cover, how coverage is measured, and what is still waiting on tooling.
- Root `AGENTS.md` — the working rules this checklist enforces (git workflow, TDD, security baseline, scope discipline).
- [Team A-HA! Scrum Playbook](https://docs.google.com/document/d/1wd96yzFLZQ1FNZQFfbxzSQvRzzqs9ZJkgrZUEBKbItg/edit) — the team's process: board workflow (§4.4), Definition of Ready (§5), this DoD (§6), estimation, change management.
