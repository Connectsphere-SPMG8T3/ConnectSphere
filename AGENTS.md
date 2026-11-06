# AGENTS.md — ConnectSphere

Instructions for any AI coding agent (Claude Code, Codex, Cursor, Copilot, etc.) working in this repository. Tool-specific workflows live under `.claude/`; this file is the shared baseline every agent should follow regardless of which tool is driving.

**Claude Code users:** `CLAUDE.md` is gitignored so each developer can keep personal instructions. Claude Code reads `CLAUDE.md`, not `AGENTS.md`, so create your own `CLAUDE.md` at the repo root with `@AGENTS.md` as its first line, then add your personal instructions below it. For the backend and frontend rules to load automatically, also add a `CLAUDE.md` containing `@AGENTS.md` in `backend/` and `frontend/`.

## Project overview

ConnectSphere is a regional event planning and venue booking platform for Singapore, built as a **Modular Monolith**:

- **`backend/`** — Python FastAPI, organised into domain modules (`auth`, `events`, `venues`, `equipment`) under `backend/app/modules/`, sharing a common `core` and `db` layer. Each module is self-contained (`router.py`, `schemas.py`, `service.py`) so new domains can be added without touching existing ones.
- **`frontend/`** — Vue 3 (Composition API, `<script setup>`), Vite, Pinia, Vue Router, Tailwind CSS.
- **`supabase/`** — PostgreSQL schema migrations, seed data, and Supabase Auth configuration (project ref `vuiryrzzyfecjqftwicj`).
- **`mcp/`** — Supabase MCP server configuration.

Layer-specific rules (tech stack, conventions, design system) live in **`backend/AGENTS.md`** and **`frontend/AGENTS.md`**. Read the one for the layer you're touching, in addition to this file.

## How the team works

The team's Scrum process is set by the [Team A-HA! Scrum Playbook](https://docs.google.com/document/d/1wd96yzFLZQ1FNZQFfbxzSQvRzzqs9ZJkgrZUEBKbItg/edit): its board workflow, Definition of Ready, Definition of Done, estimation and change management. This repository's process docs follow it, and the playbook wins if the two disagree.

From Sprint 3 (6 Oct 2026), the backlog lives in the [Product backlog sheet](https://docs.google.com/spreadsheets/d/18y09jIMc9t1FtvTEM_6u74uWNAg8hrW0eF_LehVgWVY/edit), not Jira. Its **Product backlog** tab holds every PBI: user story, acceptance criteria, priority, estimate, status and customer clarifications. Each sprint has its own tab with the sprint's tasks and burndown. Jira's Sprint 1–2 records are kept only as exports in the shared drive. Before writing to the sheet, read "Editing the backlog sheet" in `docs/DEVELOPMENT_WORKFLOW.md` for the column layout, exact status values and date format.

**PBI IDs.** Stories from Sprints 1–2 keep their Jira number: row `12` in the sheet is `SCRUM-12`. Stories added because of a customer change request (the Week 7 change notice and its clarifications) use `CR-<n>`, such as `CR-99`. A Done story reopened for new work keeps its ID with `-R`, such as `72-R` or `CR-104-R`. Other stories the team adds use the sheet's next plain number, such as `98`. Cite whichever the sheet shows.

## Start every task: Scrum story or fix?

Before exploring or changing code, ask the developer which kind of work this is (skip the question if they've already said):

1. **Scrum story** (or enhancement)
   - Ask for the PBI ID (`SCRUM-<n>`, `CR-<n>`, a plain number, or one ending in `-R`).
   - Read its row in the Product backlog sheet through the Google Sheets connector: user story, acceptance criteria, epic, priority, estimate, sprint and customer clarifications. **Read only.** Never edit the sheet unless the developer asks.
   - If the sheet can't be read, ask the developer to paste the **user story** and **acceptance criteria**. Never work from the title alone, and never invent acceptance criteria.
   - **Suggest planning first.** In Claude Code, recommend switching to plan mode before any code is written. In other tools, write the plan out and get the developer's agreement. The plan maps every acceptance criterion to the files, tests, and verification that will satisfy it, and names anything from `docs/IMPLEMENTATION_MAP.md` it will reuse.
   - Branch: `feature/scrum-<n>-<short-slug>`, or `feature/cr-<n>-<short-slug>` for a `CR-<n>` ID.
2. **Fix**
   - Ask for the defect ID from `docs/DEFECTS.md` (D1, D2, …), or the observed vs expected behaviour and how to reproduce it. A fix has no row in the Product backlog: its record is its `docs/DEFECTS.md` row, linked to the PBI it affects. If the work would change a rule or an acceptance criterion, it's a story instead: a new PBI linked to the original, with an ID ending in `-R`.
   - Reproduce the defect first, then write a failing regression test before changing code.
   - Branch: `fix/<short-slug>`.

Work that is neither (docs, tooling, config) is an enabler on a `chore/<short-slug>` branch.

**Finish every story or fix by updating `docs/IMPLEMENTATION_MAP.md`** with what now exists and anything the next developer must know, before reporting the task done (see "Keep the paper trail current").

## Ground yourself before touching code

Read, in this order:

1. `docs/REQUIREMENTS.md` — what the system *should* do: behaviour specs, acceptance criteria, the domain model, customer clarifications cited as `QA-<row>`.
2. `docs/IMPLEMENTATION_MAP.md` — what exists **right now** (modules, endpoints, tables, reusable components) and what to know before building on it.
3. `docs/PROJECT_OVERVIEW.md` — course and customer context, the 20 first-release features, and the reasoning behind the architecture and design system.
4. `docs/BUILD_LOG.md` — what each story built, up to 1 Nov 2026 (frozen). Later stories are recorded in their PR descriptions.
5. `docs/SETUP.md` — how to run everything locally.
6. `docs/DEFECTS.md` — known defects (D1, D2, …) and their status.
7. `docs/test-cases/` — existing manual test cases, one file per area (start at its `README.md`).
8. `docs/DEFINITION_OF_DONE.md` — the checklist this task has to clear before it counts as done.
9. `docs/DEVELOPMENT_WORKFLOW.md` — how a PBI moves from Ready to Done, step by step, and which steps belong to a person.

Customer rules take precedence in this order: session Q&A answers (`QA-<row>`), then the Week 4 core features, then the Week 1 briefing.

- Never invent a business rule.
- If a rule is unanswered, implement the most reasonable default, label it **[Assumption]** in `docs/REQUIREMENTS.md`, and add it to §9 (open questions).
- If the customer left a choice to the team, label it **[Team decision]** and give the reason.

**Pull live context instead of trusting memory or repo files** — the live Supabase schema has drifted from the migration files before. Check the actual project (tables, migrations, advisors), not just `supabase/migrations/`. Check pinned versions in `backend/requirements.txt` and `frontend/package.json` before relying on library behaviour from training data or memory.

Plan any change that spans more than one file or layer before writing code.

## Git workflow

- **Never commit to `main`.** Branch from an up-to-date `main`:
  - stories and enhancements: `feature/scrum-<n>-<short-slug>`, or `feature/cr-<n>-<short-slug>` for a `CR-<n>` ID
  - bugs: `fix/<short-slug>`
  - enablers: `chore/<short-slug>`
- Run `git status` first. Never discard or overwrite uncommitted work you didn't create.
- Commit only what the task changed, staging files by name — never `.env`, keys, or tokens. `.claude/` and `docs/prompts/` are gitignored local workflow aids.
- Commit message: an imperative summary line (`fix(auth): …`, `feat(events): …`), then a body explaining *why*, with the PBI ID or defect ID.
- Don't push, open PRs, or edit the team's Google Sheets (backlog, sprint tabs, test cases) without the user asking. When the user does ask for a backlog update, record any requirement change in the PBI's **Customer clarification** column, citing the `QA-<row>` and its session.
- A PR that changes anything a person can see carries screenshots of what it refers to: each page or state it changes, and for a fix the defect before and after. Commit them under `docs/screenshots/<branch-name>/` and embed them in the PR description with full `https://github.com/<owner>/<repo>/blob/<sha>/<path>?raw=true` URLs, because the GitHub API can't upload attachments. Show seeded or throwaway data only, never secrets.

## Security baseline (applies to every layer)

- **The API is the policy-enforcement point.** The backend talks to Postgres with the **secret key, which bypasses RLS**. RLS alone protects nothing on API traffic — every endpoint must check **role *and* the caller's relationship to the resource** (see `docs/REQUIREMENTS.md` §2). RLS remains a deny-by-default safety net for any direct database access.
- **Authorise by the session's *active* role, never by every role the account holds.** An account can hold several roles (`user_roles`) but acts as one at a time (`session_active_roles`). Every new endpoint, dependency, RLS policy, and page or route guard must gate on the active role: in the API use `require_roles([...])` / `CurrentUser.role`, in RLS use `private.current_user_role()`, and in the frontend use the store's active `role`. Never check membership in `user_roles`, `CurrentUser.roles`, or `profiles.role` to grant access. A user acting as role Y must get 403 on role-X-only resources even if they also hold X. Any new page, module, or policy needs a test that proves this denial, ideally with a raw request that bypasses the UI (SCRUM-76).
- Never trust client-supplied identity or privilege data: request bodies, sign-up metadata, or query params claiming a role or owner. Derive identity from the verified JWT.
- The secret key never goes into the frontend, a `VITE_*` variable, logs, docs, screenshots, or commits.
- In anything visible to others (PRs, the backlog, docs), describe security bugs by *class*, never as step-by-step exploits.

## Scope discipline

- Change only what the task needs. When you notice something else broken or questionable, **report it** (and add it to `docs/DEFECTS.md` if it's a defect) rather than silently fixing it on the side.
- Don't adopt new libraries, restructure modules, or change project-wide conventions without confirming with the user first.
- New modules follow the target module design in `docs/REQUIREMENTS.md` §3.3. If the team hasn't adopted part of that design yet, say so rather than diverging silently.

## Build for reuse

Several roles and stories touch the same domains (venues, events, equipment), so the same logic and UI keep coming back.

- **Check before building.** Look in `docs/IMPLEMENTATION_MAP.md` and the code for an existing module, service function, component, or helper, and extend it rather than writing a parallel version.
- **Write likely-to-be-reused pieces as modules from the start.** "Likely" means another story in the backlog, another role's dashboard, or a second screen needs the same behaviour. Don't inline it into one endpoint or view.
- **Don't generalise for hypothetical needs.** If nothing concrete will reuse it, keep it local. Extract it when the second use arrives.
- Where reusable pieces go is specific to each layer: see "Reuse" in `backend/AGENTS.md` and `frontend/AGENTS.md`.

## Test-driven development

Write the test before the implementation, for any new feature or bugfix:

1. Write a failing test that encodes the required behaviour (or, for a bugfix, that reproduces the defect) before writing implementation code.
2. Run it and confirm it fails for the expected reason — not a typo or import error.
3. Write the minimum code to make it pass.
4. Refactor with the test suite green.

This applies at whatever layer the change lives in — `pytest` in `backend/tests/` for backend/API behaviour, component/unit tests for frontend logic, and `docs/test-cases/` entries for user-facing behaviour that needs a manual trace to a PBI ID. Don't write the implementation first and backfill tests afterward — that's covered by "Definition of done" below but the order matters, not just the coverage.

**Don't change an existing test to make it pass.** When new work makes an existing test fail, the test is reporting a regression: fix the code, not the test. Never edit, loosen, skip or delete an existing test (its assertions, fixtures, expected values or mocks) just so the suite goes green. Change it only when the behaviour it checks has deliberately changed: an acceptance criterion of the PBI you're implementing, a customer clarification (`QA-<row>`) or a decision the developer made replaces the old behaviour. Then say so in the commit message and the PR description, naming the test and the AC or decision that changed it. If you're not sure the old behaviour should change, stop and ask the developer.

The team's DoD sets the coverage bar: 100% of new and changed code in `backend/app/` and `frontend/src/`, or each uncovered line is listed with the reason (`docs/CI.md` §4 item 2).

## Verification: "it imports" is not "it works"

Several early bugs (SCRUM-48, logout defect D1) passed a fully mocked test suite and only showed up against the real Supabase project. For anything crossing an integration boundary (Supabase Auth, PostgREST, RLS, the browser), verify against the real system:

- backend: `uvicorn app.main:app --reload` from `backend/`, plus real HTTP requests
- database: queries run as the actual role, not the service key
- frontend: the dev server, exercised in a real browser, with the console checked

Run the full test suite (`pytest` from `backend/`) before declaring done, not only the new tests. In the final report, state what **was not** verified and why.

## Live checks and the manual browser pass

Every run of the test cases against the real system is recorded in `docs/test-cases/runs/` (its `README.md` has the commands and the manual template). When a story or fix reaches verification:

1. **Run the automated live checks with recording on**, against a backend and frontend running this branch: `python scripts/verify_live.py --record` from `backend/`, then `npm run test:e2e:record` from `frontend/`. If the developer's own servers are on 8000/5173, start yours on spare ports and pass `--api` / `E2E_BASE_URL` / `E2E_API_URL`. A failure is a finding to fix or report, never something to re-run until it passes. Record once per verification: run without `--record` while iterating, delete a log that failed only because of setup (port, CORS, rate limit) and record again, and put the trigger in each log's title (`SCRUM-45 verification — …`), as `docs/test-cases/runs/README.md` "When to record a run" describes.
2. **Automate the story's new cases where you can.** A case whose outcome is a status code, a redirect, a stored value, a field's text, or whether a request was sent gets a check in `backend/scripts/verify_live.py` or `frontend/e2e/`, named with its case ID first. Never change seeded or shared data. A check may create its own throwaway records only if the run deletes them, as the sign-up checks do with `live-check+…` accounts. Otherwise it stays manual.
3. **Then stop and ask the developer to do the manual pass.** List the story's cases that still need a person: design and layout (including phone width), wording, anything that must not flash or jump, anything outside the app, and cases that change shared data. For each one, give the case ID, the page to open, and exactly what to look at. Keep it a short checklist grouped by page. Don't mark these as passed yourself. If you drive a browser, it can confirm that something works, but only the developer can judge how it looks and reads.
4. **Record what the developer reports** as a manual run file (template in `docs/test-cases/runs/README.md`). A failure also becomes a defect in `docs/DEFECTS.md`.
5. If the developer defers the manual pass, the final report lists those cases under "not verified".

At the end of a sprint, if the developer asks, run both suites with recording on as regression evidence, titled `Sprint <n> regression — …`. There is no sprint-wide manual pass.

Commit the run logs with the story, since they are the evidence that it was tested.

## Keep the paper trail current (graded evidence)

- `docs/IMPLEMENTATION_MAP.md`: **after adding or changing anything another story will reuse or rely on**, update the map in the same branch: an endpoint (method, path, guard), a table, a reusable component, store or helper, or a changed contract (request/response shape, guard, enum). Edit it in place: add the new pieces next to related rows (not at the end of a table), remove what no longer exists, and record any "know before you build" notes the next developer needs. The map has no status table and no "Last updated" line; don't add them back.
- `docs/BUILD_LOG.md` is **frozen** (1 Nov 2026): never add an entry. The PR description is a story's or fix's record. Draft it in the final report, following `.github/pull_request_template.md`, so the developer can paste it: each acceptance criterion with the test or TC ID that proves it, the normal, boundary, conflict and failure scenarios covered, the recorded runs as full `blob/<sha>/…` URLs (relative links break in a PR description), and what wasn't verified.
- How a story was interpreted goes in `docs/REQUIREMENTS.md` as **[Assumption]** or **[Team decision]**, citing the `QA-<row>`, and the developer copies it into the PBI's Customer clarification or Notes column.
- `docs/test-cases/<area>.md`: add manual cases for new behaviour, traced to PBI IDs and acceptance criteria, with the Type, Created and Last run columns (`docs/test-cases/README.md`). The team copies them into the Test cases sheet before submission, so don't write to that sheet.
- `docs/REQUIREMENTS.md`: update it when a rule, assumption, or design decision changes.
- `docs/DEFECTS.md`: mark defects fixed, with the branch or commit, and add any new defect as the next number.

## Run commands

| Step | Command | Notes |
|------|---------|-------|
| Migrate DB | `supabase db push` | from repo root |
| Seed test accounts | `psql "$DATABASE_URL" -f supabase/seed.sql` | one account per role |
| Start backend | `uvicorn app.main:app --reload --port 8000` | from `backend/` |
| Start frontend | `npm run dev` | from `frontend/` |
| Run tests | `pytest` | from `backend/` |
| Coverage | `pytest --cov` / `npm run test:coverage` | from `backend/` / `frontend/`; full suite only, fails below the floor in `docs/CI.md` §4 item 2 |
| Mutation testing | `no_proxy='*' mutmut run "app.modules.<module>.*"` / `npm run test:mutation -- --mutate "src/<area>/**/*.js,!src/**/__tests__/**"` | from `backend/` / `frontend/`; recommended before a PR that changes logic, not a gate; on Windows run the backend half from the Actions tab (**Mutation testing** workflow); triage rules in `docs/MUTATION_TESTING.md` §4 |
| Live API + database checks | `python scripts/verify_live.py --record` | from `backend/`; backend running, `supabase login` done |
| Live browser checks | `npm run test:e2e:record` | from `frontend/`; both servers running; first time `npx playwright install chromium` |

## Definition of done (every task)

Two files, both for humans and agents:

- **`docs/DEFINITION_OF_DONE.md`** is the team's checklist: what a PBI must meet to count as Done. It is the playbook's DoD, plus the checks specific to this repository.
- **`docs/DEVELOPMENT_WORKFLOW.md`** is how to get there. It follows the board (Ready → In Progress → In Review → Done) and marks which steps are the developer's.

This section is only the agent-facing summary of the workflow's §1–3.

- [ ] For a story: every acceptance criterion from the PBI's Product backlog row (or as supplied by the developer) is met and traced to a test or verification step.
- [ ] Behaviour matches `docs/REQUIREMENTS.md`, or any deviation is recorded there.
- [ ] Reusable pieces were extended or extracted rather than duplicated, and `docs/IMPLEMENTATION_MAP.md` reflects the new state.
- [ ] Automated tests cover the happy path, boundaries, conflicts, failures, and authorisation denials, new and changed code is fully covered (or the gaps are stated), and the full suite passes.
- [ ] The change is verified against the real system wherever it crosses an integration boundary.
- [ ] The live checks were run with recording on, and the developer was asked for the manual browser pass, with the results recorded in `docs/test-cases/runs/`.
- [ ] Database changes show no new security or performance advisories.
- [ ] Docs are updated per "Keep the paper trail current" above. The work is on a non-`main` branch, committed with a *why*-focused message.
- [ ] The final report covers: what changed, how it was verified, what wasn't verified, and follow-ups.

Stopping here is correct for an agent. **The workflow's §4–5 are the developer's**: the PR, the teammate review, the PO's acceptance, the merge, and setting the PBI to Done in the Product backlog. An agent only does them when asked. Say so in the final report, so the PBI is not left merged with its status still In Review. The report also reminds the developer to update the PBI's rows in the sprint's **DoD (Sprint N)** tab before opening the PR and again before merging: which acceptance criteria are now met, which are not and why, and which checklist boxes are now true. Offer to make those ticks if the developer wants.
