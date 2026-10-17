# ConnectSphere — Development workflow

**How a Product Backlog Item moves from Ready to Done, step by step, and who does each step.**

[`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md) says what Done means. This file says how to get there. The sections follow the board in the [Team A-HA! Scrum Playbook](https://docs.google.com/document/d/1wd96yzFLZQ1FNZQFfbxzSQvRzzqs9ZJkgrZUEBKbItg/edit) §4.4:

> Backlog → Ready → To Do → In Progress → In Review → Done

Every item is tagged with who owns it:

| Tag | Who |
|---|---|
| **[A]** | The AI agent (or whoever writes the code) |
| **[D]** | A developer: a human step an agent must not do unprompted |
| **[A/D]** | Either, depending on who is driving |
| **[PO]** | The Product Owner |

Agents never push, open PRs, or edit the team's Google Sheets unless the developer asks (root `AGENTS.md`, "Git workflow"). An agent's work ends after §3. The PBI is not Done until a person finishes §4 and §5.

_Last updated: 2026-10-16 — §2 and End of sprint: when to run mutation testing (`chore/mutation-testing`). 2026-10-13 — the DoD (Sprint N) tabs are tracked in the sheet and checked before the PR (§4) and before the merge (§5); "Editing the backlog sheet" lists the Notes column (T) and explains the DoD tabs (`chore/backlog-notes-column`)._

---

## Where the work is tracked

| What | Where |
|---|---|
| PBIs: user story, acceptance criteria, priority, estimate, status, customer clarifications | The **Product backlog** tab of the [Product backlog sheet](https://docs.google.com/spreadsheets/d/18y09jIMc9t1FtvTEM_6u74uWNAg8hrW0eF_LehVgWVY/edit). PBI status is To Do / In Progress / In Review / Done (exact values under "Editing the backlog sheet" below). |
| The sprint goal, tasks and remaining effort, and the burndown chart | The sprint's tab (Sprint 1–4) in the same sheet. Task status is To Do / In Progress / In Review / Done. Remaining effort is updated after every daily scrum. |
| Whether each PBI meets the DoD: its acceptance criteria ticked one by one, the story checklist and the PO's sign-off | The sprint's **DoD (Sprint 1–4)** tab in the same sheet. Stories and ACs fill in from the Product backlog; the ticks are manual, so they are only as current as the last person who updated them (see §4 and §5). |
| Code, tests, test cases and run logs | This repository. The team copies the test cases into the Test cases sheet before submission. |
| Sprint 1 and 2 history | The Jira exports in the shared drive's `#4. Evidence` folder. |

**PBI IDs.** Stories from Sprints 1–2 keep their Jira number: row `12` in the sheet is `SCRUM-12`. Stories added because of a customer change request (the Week 7 change notice and its clarifications) use `CR-<n>`, such as `CR-99`. A Done story reopened for new work keeps its ID with `-R`, such as `72-R` or `CR-104-R`. Other stories the team adds use the sheet's next plain number, such as `98`. Cite whichever the sheet shows, in branches, commits, test cases and log entries.

### Editing the backlog sheet

An agent with the Google Sheets connector can read and write the sheet directly. Anyone signed in with an `smu.edu.sg` account has edit access. Agents edit it only when the developer asks.

- **Columns** in the **Product backlog** tab, as of 13 Oct 2026: A Needs attention, B ID #, C Title, D Type, E Epic, F As a…, G I want to be able to…, H So that…, I Acceptance criteria, J Met DoD?, K Priority, L Estimate, M Sprint #, N Customer clarification, O Assignee, P Status, Q Created date, R Updated date, S Resolved date, T Notes. Teammates can move columns, so re-read row 1 before writing.
- **Never insert a column between B and S.** The sprint tabs list each sprint's stories with `CHOOSECOLS(FILTER('Product backlog'!B2:S, …), 1, 2, 4, 14, 11, 15, 18)`, which picks columns by position and doesn't adjust when one is inserted, so the sprint tables would show the wrong fields. Add new columns after the last one.
- **Notes** (T) is for internal notes on a story that have no other column: hand-off between stories, dependencies, review feedback. Start each note with where it came from, who wrote it and when, such as `From CR-99 (Xuan Wei, 12/10): …`, and add a later note on a new line rather than overwriting. Customer answers still go in **Customer clarification**, and open questions in **Needs attention**. The sprint tabs don't show Notes.
- **Status** must match the dropdown exactly, emoji included: `TO DO 😖`, `IN PROGRESS 🥸`, `IN REVIEW 🥹`, `DONE 🥳`.
- **Dates** are text in `DD/MM/YYYY` form. A status change also sets **Updated date**. Setting a PBI to Done also sets **Resolved date** and fills **Met DoD?**.
- **Reading:** the whole tab is too large for one connector call. Find the row with a narrow range such as `'Product backlog'!B1:C120`, then read just that row.
- **DoD tabs.** Each **DoD (Sprint N)** tab lists the sprint's stories in a story checklist (row 23 onwards) and their acceptance criteria in an AC table (row 56 onwards), both built by formula from the Product backlog. Tick **AC met?** for each AC, and the checklist boxes for the story. **DoD met?** turns to ✅ Done only when every AC and every box is ticked. Ticks stay in their row, not with their story, so if a story leaves the sprint or gains an AC, re-check the ticks below it. Read the row's ID and AC number before ticking.
- **Writing:** re-read the target row right before writing, because teammates edit the sheet at the same time. Read it back afterwards to confirm the change.

## 1. Before starting: Ready → In Progress

- [ ] **[D]** The PBI meets the **Definition of Ready** (playbook §5). It is written as "As a… I want to be able to… So that…" and follows INVEST. Its acceptance criteria are testable. All customer clarifications are resolved, and no dependency blocks it. It was estimated by planning poker and fits in one sprint.
- [ ] **[A/D]** The work is identified as one of:
  - a **story** or **enhancement** (a PBI ID);
  - a **bug fix** (a defect `D<n>` in [`DEFECTS.md`](DEFECTS.md), plus its Bug fix PBI in the backlog);
  - an **enabler**, such as docs, tooling or config.
- [ ] **[A/D]** The user story and acceptance criteria come from the PBI's row in the Product backlog, or are pasted by the developer if the agent can't read the sheet. Never work from the title alone, and never invent acceptance criteria.
- [ ] **[A/D]** `docs/REQUIREMENTS.md`, `docs/IMPLEMENTATION_MAP.md` and the live Supabase project have been checked. Don't rely only on the migration files, which have drifted before.
- [ ] **[A/D]** A plan exists for anything spanning more than one file or layer. It maps each acceptance criterion to the files, tests and verification that will satisfy it, and names what it reuses from `docs/IMPLEMENTATION_MAP.md`.
- [ ] **[A/D]** The branch was made from an up-to-date `main`. **Never commit to `main`.**

  | Work | Branch |
  |---|---|
  | Story or enhancement with a Jira number | `feature/scrum-<n>-<slug>` |
  | Story or enhancement with a sheet ID | `feature/new-<nn>-<slug>` |
  | Bug fix | `fix/<slug>` |
  | Enabler | `chore/<slug>` |

- [ ] **[D]** The developer self-assigns the PBI's tasks in the sprint tab and moves them to In Progress.

## 2. Building: In Progress

- [ ] **[A]** The failing test was written **first** and confirmed to fail for the expected reason, then made to pass (root `AGENTS.md`, "Test-driven development"). Order matters, not just coverage.
- [ ] **[A]** Every acceptance criterion is met and traced to a named test or a written verification step.
- [ ] **[A]** Tests cover the normal path, boundaries, conflicts, failures **and authorisation denials**.
- [ ] **[A]** Authorisation is checked as **role *and* relationship to the resource**, gated on the session's **active** role. A negative test proves that a user holding another role gets 403 (SCRUM-76).
- [ ] **[A]** The **full** suite passes, not only the new tests: `pytest` from `backend/` and `npm test` from `frontend/`.
- [ ] **[A]** New and changed code is fully covered, or each uncovered line is listed with its reason in the PR. Measure it with the full suite: `pytest --cov` from `backend/` and `npm run test:coverage` from `frontend/` ([`CI.md`](CI.md) §4 item 2).
- *Recommended, not required:* when the PBI changes logic (a service, a rules module, a store or composable), run mutation testing on that module and add tests for the survivors that matter ([`MUTATION_TESTING.md`](MUTATION_TESTING.md) §2–4). On Windows, run the backend half from the Actions tab (**Mutation testing** workflow).
- [ ] **[A]** Anything crossing an integration boundary (Supabase Auth, PostgREST, RLS, the browser) is verified against the **real system**, not only against mocks. "It imports" is not "it works".
- [ ] **[A]** The live checks were run with recording on (`backend/scripts/verify_live.py --record`, `npm run test:e2e:record`). The story's new cases were automated wherever a request or a browser assertion can check their outcome (root `AGENTS.md`, "Live checks and the manual browser pass").
- [ ] **[D]** When the agent asked, the developer ran the manual browser pass for the cases that need human judgement (layout, phone width, wording, feel). The results are recorded in `docs/test-cases/runs/`.
- [ ] **[A]** For database changes:
  - `supabase db push` runs clean;
  - the Supabase advisors show **no new** security or performance findings;
  - verification SQL is added under `supabase/verification/`, in the style of `auth_security_checks.sql`.
- [ ] **[A]** Behaviour matches `docs/REQUIREMENTS.md`, or the deviation is recorded there as **[Assumption]** or **[Team decision]** with its reason.
- [ ] **[A]** Reusable pieces were extended or extracted rather than duplicated.
- [ ] **[A]** There are no secrets in the diff: never `.env`, keys or tokens. The secret key never reaches the frontend, a `VITE_*` variable, logs, docs or screenshots.
- [ ] **[D]** The task's remaining effort in the sprint tab is updated after each daily scrum. A blocked task is flagged and raised at the next daily scrum.

## 3. Paper trail, before opening the PR

- [ ] **[A]** `docs/IMPLEMENTATION_MAP.md` is updated **in place** on the same branch: the status table, the reuse tables, anything removed, the "know before you build" notes, and the "Last updated" line.
- [ ] **[A]** A new `docs/BUILD_LOG.md` §4 entry is **appended**, using the existing template. Never rewrite past entries.
- [ ] **[A]** `docs/test-cases/<area>.md` has cases for the new user-facing behaviour, traced to the PBI ID and its acceptance criteria, with the Type, Created and Last run columns filled in ([`test-cases/README.md`](test-cases/README.md)).
- [ ] **[A]** This PBI's run logs, automated and manual, are committed on the branch in `docs/test-cases/runs/`.
- [ ] **[A]** `docs/REQUIREMENTS.md` is updated if a rule, assumption or design decision changed, citing the `QA-<row>` behind it.
- [ ] **[A]** `docs/DEFECTS.md` marks the fixed defects, with the branch or commit, and adds any new defect as the next number.
- [ ] **[A]** The work is committed on a non-`main` branch, staged **by file name**. The message has an imperative summary (`feat(events): …`) and a body explaining *why*, with the PBI ID or defect ID.
- [ ] **[A]** The final report states what changed, how it was verified, **what was not verified and why**, and any follow-ups.

## 4. Review: In Progress → In Review

This section and §5 are human-owned. An agent does these steps only when the developer explicitly asks.

- [ ] **[D]** **Before opening the PR, the PBI's rows in the sprint's DoD tab are brought up to date:** **AC met?** is ticked for each acceptance criterion that now works and has its test cases passing, and the story checklist's boxes that are already true are ticked (usually **Unit / integration tests**, **No open critical bugs** and **Docs updated**). An AC that depends on unbuilt work stays unticked, with the reason in its **Notes**. The PBI's **Status** in the Product backlog moves to In Review.
- [ ] **[D]** A pull request is opened against `main`. It names the PBI ID, and describes any security issue by *class*, never as step-by-step exploits.
- [ ] **[D]** **CI passes on the PR.** The `CI` workflow (`.github/workflows/ci.yml`) runs the backend suite, the frontend suite and the frontend build on every pull request into `main`. Don't merge on the strength of a local run alone.
- [ ] **[D]** At least one other Developer is requested as a reviewer. The PBI's tasks move to In Review in the sprint tab.
- [ ] **[D]** If the reviewer requests changes or CI fails, the tasks go **back to In Progress**.
- [ ] **[D]** **At least one teammate has reviewed and approved the PR.** Review comments are resolved, or captured as new PBIs rather than silently dropped.
- [ ] **[D] [PO]** The acceptance criteria are **demonstrated to the PO, and the PO approves them**. The PO's acceptance is recorded by ticking **PO accepted**, with the PO's name and date, in the DoD tab.

## 5. Done: In Review → Done

- [ ] **[D]** **Before merging, the DoD tab is checked again:** **Code reviewed** and **CI passes** are ticked. Every other PR for the PBI (docs or follow-up fixes) is merged as well; then **Merged to main** is ticked.
- [ ] **[D]** The PR is merged into `main` only after CI passes and the approval is given. Then the branch is deleted.
- [ ] **[D]** Migrations reach the shared Supabase project **through the merged PR**, never applied by hand.
- [ ] **[D]** The PBI's **DoD met?** in the DoD tab shows ✅ Done. Only then is its **Status** in the Product backlog set to Done and **Met DoD?** filled. The tab's "Marked DONE in backlog but DoD not met" count should stay at 0. In the sprint tab, its tasks are set to Done.
- [ ] **[D]** Any customer clarification or scope change found during the work is recorded in the **Customer clarification** column, with its session and date.
- [ ] **[D]** Anything demo-able is noted for the sprint review.

**After Done, a change is a new PBI.** If a clarification or a bug later changes a Done PBI, create a new PBI linked to the original. Done items are never reopened (playbook §10.3).

## End of sprint

- **[PO]** Any PBI that is not Done returns to the Product Backlog. Its remaining work is re-estimated and the PO reorders it. It earns no velocity.
- **[A/D]** Both automated suites are run with recording on, as regression evidence for the sprint review ([`test-cases/runs/README.md`](test-cases/runs/README.md)). There is no sprint-wide manual pass.
- **[A/D]** Mutation testing is run on both stacks and a baseline row is added to [`MUTATION_TESTING.md`](MUTATION_TESTING.md) §6, as evidence that test quality is tracked across sprints.
- **[D]** The task board (the Status view) is screenshotted as evidence.

## Related

- [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md) — the checklist a PBI must clear.
- Root `AGENTS.md` — the working rules behind each step.
- [`CI.md`](CI.md) — what CI checks, and how coverage is measured.
- [`MUTATION_TESTING.md`](MUTATION_TESTING.md) — how to check that tests would catch a bug, and the sprint baselines.
- [`test-cases/README.md`](test-cases/README.md) and [`test-cases/runs/README.md`](test-cases/runs/README.md) — how to write test cases and how to record their runs.
