# AGENTS.md — ConnectSphere

Instructions for any AI coding agent (Claude Code, Codex, Cursor, Copilot, etc.) working in this repository. Tool-specific workflows live under `.claude/`; this file is the shared baseline every agent should follow regardless of which tool is driving.

## Project overview

ConnectSphere is a regional event planning and venue booking platform for Singapore, built as a **Modular Monolith**:

- **`backend/`** — Python FastAPI, organised into domain modules (`auth`, `events`, `venues`, `equipment`) under `backend/app/modules/`, sharing a common `core` and `db` layer. Each module is self-contained (`router.py`, `schemas.py`, `service.py`) so new domains can be added without touching existing ones.
- **`frontend/`** — Vue 3 (Composition API, `<script setup>`), Vite, Pinia, Vue Router, Tailwind CSS.
- **`supabase/`** — PostgreSQL schema migrations, seed data, and Supabase Auth configuration (project ref `vuiryrzzyfecjqftwicj`).
- **`mcp/`** — Supabase MCP server configuration.

## Ground yourself before touching code

Read, in this order:

1. `docs/REQUIREMENTS.md` — what the system *should* do: behaviour specs, acceptance criteria, the domain model, customer clarifications cited as `QA-<row>`.
2. `docs/SCENARIO.md` — project context and the append-only log of what each story actually built.
3. `docs/SETUP.md` — how to run everything locally.
4. `docs/PROJECT_REVIEW.md` — known defects (D1, D2, …), design decisions, and the sprint plan.
5. `docs/TEST_CASES.md` — existing manual test cases.

Customer rules take precedence in this order: session Q&A answers (`QA-<row>`), then the Week 4 core features, then the Week 1 briefing.

- Never invent a business rule.
- If a rule is unanswered, implement the most reasonable default, label it **[Assumption]** in `docs/REQUIREMENTS.md`, and add it to §9 (open questions).
- If the customer left a choice to the team, label it **[Team decision]** and give the reason.

**Pull live context instead of trusting memory or repo files** — the live Supabase schema has drifted from the migration files before. Check the actual project (tables, migrations, advisors), not just `supabase/migrations/`. Check pinned versions in `backend/requirements.txt` and `frontend/package.json` before relying on library behaviour from training data or memory.

Plan any change that spans more than one file or layer before writing code.

## Git workflow

- **Never commit to `main`.** Branch from an up-to-date `main`:
  - stories: `feature/scrum-<n>-<short-slug>`
  - bugs: `fix/<short-slug>`
  - enablers: `chore/<short-slug>`
- Run `git status` first. Never discard or overwrite uncommitted work you didn't create.
- Commit only what the task changed, staging files by name — never `.env`, keys, or tokens. `.claude/` and `docs/prompts/` are gitignored local workflow aids.
- Commit message: an imperative summary line (`fix(auth): …`, `feat(events): …`), then a body explaining *why*, with the Jira key or defect ID.
- Don't push, open PRs, or change Jira without the user asking. When the user does ask for Jira updates, cite the `QA-<row>` behind any requirement change.

## Security baseline (applies to every layer)

- **The API is the policy-enforcement point.** The backend talks to Postgres with the **secret key, which bypasses RLS**. RLS alone protects nothing on API traffic — every endpoint must check **role *and* the caller's relationship to the resource** (see `docs/REQUIREMENTS.md` §2). RLS remains a deny-by-default safety net for any direct database access.
- Never trust client-supplied identity or privilege data: request bodies, sign-up metadata, or query params claiming a role or owner. Derive identity from the verified JWT.
- The secret key never goes into the frontend, a `VITE_*` variable, logs, docs, screenshots, or commits.
- In anything visible to others (PRs, Jira, docs), describe security bugs by *class*, never as step-by-step exploits.

## Scope discipline

- Change only what the task needs. When you notice something else broken or questionable, **report it** (and add it to `docs/PROJECT_REVIEW.md` if it's a defect) rather than silently fixing it on the side.
- Don't adopt new libraries, restructure modules, or change project-wide conventions without confirming with the user first.
- New modules follow the target module design in `docs/REQUIREMENTS.md` §3.3. If the team hasn't adopted part of that design yet, say so rather than diverging silently.

## Test-driven development

Write the test before the implementation, for any new feature or bugfix:

1. Write a failing test that encodes the required behaviour (or, for a bugfix, that reproduces the defect) before writing implementation code.
2. Run it and confirm it fails for the expected reason — not a typo or import error.
3. Write the minimum code to make it pass.
4. Refactor with the test suite green.

This applies at whatever layer the change lives in — `pytest` in `backend/tests/` for backend/API behaviour, component/unit tests for frontend logic, and `docs/TEST_CASES.md` entries for user-facing behaviour that needs a manual trace to a Jira key. Don't write the implementation first and backfill tests afterward — that's covered by "Definition of done" below but the order matters, not just the coverage.

## Verification: "it imports" is not "it works"

Several early bugs (SCRUM-48, logout defect D1) passed a fully mocked test suite and only showed up against the real Supabase project. For anything crossing an integration boundary (Supabase Auth, PostgREST, RLS, the browser), verify against the real system:

- backend: `uvicorn app.main:app --reload` from `backend/`, plus real HTTP requests
- database: queries run as the actual role, not the service key
- frontend: the dev server, exercised in a real browser, with the console checked

Run the full test suite (`pytest` from `backend/`) before declaring done, not only the new tests. In the final report, state what **was not** verified and why.

## Keep the paper trail current (graded evidence)

- `docs/SCENARIO.md` §4: append an entry for each completed story or bug fix, following the existing template. Never rewrite past entries.
- `docs/TEST_CASES.md`: add manual cases for new behaviour, traced to Jira keys and acceptance criteria.
- `docs/REQUIREMENTS.md`: update it when a rule, assumption, or design decision changes.
- `docs/PROJECT_REVIEW.md`: mark defects fixed, with the branch or commit.

## Run commands

| Step | Command | Notes |
|------|---------|-------|
| Migrate DB | `supabase db push` | from repo root |
| Seed test accounts | `psql "$DATABASE_URL" -f supabase/seed.sql` | one account per role |
| Start backend | `uvicorn app.main:app --reload --port 8000` | from `backend/` |
| Start frontend | `npm run dev` | from `frontend/` |
| Run tests | `pytest` | from `backend/` |

## Definition of done (every task)

- [ ] Behaviour matches `docs/REQUIREMENTS.md`, or any deviation is recorded there.
- [ ] Automated tests cover the happy path, boundaries, failures, and authorisation denials, and the full suite passes.
- [ ] The change is verified against the real system wherever it crosses an integration boundary.
- [ ] Database changes show no new security or performance advisories.
- [ ] Docs are updated per "Keep the paper trail current" above. The work is on a non-`main` branch, committed with a *why*-focused message.
- [ ] The final report covers: what changed, how it was verified, what wasn't verified, and follow-ups.
