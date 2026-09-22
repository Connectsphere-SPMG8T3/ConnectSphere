# ConnectSphere — Definition of Done

**The single checklist a story, fix, or enabler must clear before anyone calls it done.**

This file is the one source of truth. Root `AGENTS.md` and `docs/PROJECT_REVIEW.md` point here rather than keeping their own copies — if a rule changes, it changes here first.

It covers **both** halves of the work: what an AI agent or a developer does while building, and what a human does afterwards to close the loop (review, merge, Jira). Every item is tagged with who owns it:

| Tag | Who |
|---|---|
| **[A]** | The AI agent (or whoever writes the code) |
| **[D]** | A developer — a human step an agent must not do unprompted |
| **[A/D]** | Either, depending on who is driving |

Agents never push, open PRs, or change Jira unless the developer asks (root `AGENTS.md`, "Git workflow"). Phase 4 is therefore where the work is handed back to a person — an agent that stops after Phase 3 has done its job, but the *story* is not done.

_Last updated: 2026-09-22 — "CI is green on the PR" moved from "Not yet enforceable" into Phase 4, now that `.github/workflows/ci.yml` exists. First version (same day) consolidated the checklist in root `AGENTS.md` and the Sprint 2 proposal in `docs/PROJECT_REVIEW.md` §C4._

---

## Phase 1 — Before writing code

- [ ] **[A/D]** The work is identified as a **story** (`SCRUM-<n>`), a **fix** (defect `D<n>` in `docs/PROJECT_REVIEW.md`), or an **enabler** (docs, tooling, config).
- [ ] **[A/D]** For a story: the user story and acceptance criteria come from Jira (or are pasted by the developer). Never work from the ticket title alone, and never invent acceptance criteria.
- [ ] **[D]** Acceptance criteria are written in **Given/When/Then** form on the Jira issue before the sprint starts.
- [ ] **[A/D]** `docs/REQUIREMENTS.md`, `docs/IMPLEMENTATION_MAP.md`, and the live Supabase project have been checked — not just the migration files, which have drifted before.
- [ ] **[A/D]** A plan exists for anything spanning more than one file or layer, mapping each acceptance criterion to the files, tests, and verification that will satisfy it, and naming what it reuses from `docs/IMPLEMENTATION_MAP.md`.
- [ ] **[A/D]** Branched from an up-to-date `main`: `feature/scrum-<n>-<slug>`, `fix/<slug>`, or `chore/<slug>`. **Never commit to `main`.**

## Phase 2 — Code complete

- [ ] **[A]** The failing test was written **first** and confirmed to fail for the expected reason, then made to pass (root `AGENTS.md`, "Test-driven development"). Order matters, not just coverage.
- [ ] **[A]** Every acceptance criterion is met and traced to a named test or a written verification step.
- [ ] **[A]** Tests cover the happy path, boundaries, failures, **and authorisation denials**.
- [ ] **[A]** Authorisation is checked as **role *and* relationship to the resource**, gated on the session's **active** role, with a negative test proving a user holding another role gets 403 (SCRUM-76).
- [ ] **[A]** The **full** suite passes, not only the new tests: `pytest` from `backend/`, `npm test` from `frontend/`.
- [ ] **[A]** Anything crossing an integration boundary (Supabase Auth, PostgREST, RLS, the browser) is verified against the **real system**, not only against mocks. "It imports" is not "it works".
- [ ] **[A]** Database changes: `supabase db push` runs clean, Supabase advisors show **no new** security or performance findings, and verification SQL is added under `supabase/verification/` in the style of `auth_security_checks.sql`.
- [ ] **[A]** Behaviour matches `docs/REQUIREMENTS.md`, or the deviation is recorded there as **[Assumption]** or **[Team decision]** with its reason.
- [ ] **[A]** Reusable pieces were extended or extracted rather than duplicated.
- [ ] **[A]** No secrets in the diff: never `.env`, keys, or tokens; the secret key never reaches the frontend, a `VITE_*` variable, logs, docs, or screenshots.

## Phase 3 — Paper trail (graded evidence)

- [ ] **[A]** `docs/IMPLEMENTATION_MAP.md` — updated **in place** in the same branch: status table, reuse tables, anything removed, "know before you build" notes, and the "Last updated" line.
- [ ] **[A]** `docs/SCENARIO.md` §4 — a new entry **appended** using the existing template. Never rewrite past entries.
- [ ] **[A]** `docs/TEST_CASES.md` — manual cases for new user-facing behaviour, traced to the Jira key and its acceptance criteria.
- [ ] **[A]** `docs/REQUIREMENTS.md` — updated when a rule, assumption, or design decision changed, citing the `QA-<row>` behind it.
- [ ] **[A]** `docs/PROJECT_REVIEW.md` — defects marked fixed, with the branch or commit.
- [ ] **[A]** Committed on a non-`main` branch, staged **by file name**, with an imperative summary (`feat(events): …`) and a body explaining *why*, carrying the Jira key or defect ID.
- [ ] **[A]** The final report states what changed, how it was verified, **what was not verified and why**, and any follow-ups.

## Phase 4 — Review, merge, close

This phase is human-owned. An agent does these steps only when the developer explicitly asks.

- [ ] **[D]** A pull request is opened against `main`, linking the Jira issue, and describing security issues by *class* — never as step-by-step exploits.
- [ ] **[D]** **CI is green on the PR.** The `CI` workflow (`.github/workflows/ci.yml`) runs the backend suite, the frontend suite, and the frontend build on every pull request into `main`. A red run blocks the merge; do not merge on the strength of a local green run alone.
- [ ] **[D]** **At least one teammate has reviewed and approved the PR.** Self-merging an unreviewed PR does not clear this checklist.
- [ ] **[D]** Review comments are resolved, or captured as follow-up issues rather than silently dropped.
- [ ] **[D]** Migrations reach the shared Supabase project **through the merged PR**, never applied by hand.
- [ ] **[D]** The branch is merged into `main` and then deleted.
- [ ] **[D]** **The Jira issue is moved to Done and the PR is linked on it.** This is the step most often missed — a merged branch with the ticket still In Progress breaks the sprint burndown, which is graded evidence.
- [ ] **[D]** Any customer clarification or scope change discovered during the work is recorded as a Jira comment citing its `QA-<row>`.
- [ ] **[D]** Anything demo-able is noted for the sprint review (`docs/PROJECT_REVIEW.md` §C4, "Scrum evidence").

---

## Not yet enforceable

These were agreed as targets in `docs/PROJECT_REVIEW.md` §C4 but **cannot be checked today**. They are listed separately on purpose: a checklist with unenforceable items on it teaches the team to ignore the whole list. Move an item up into the phases above on the day the tooling lands.

| Target | Blocked on | Move up when |
|---|---|---|
| "New domain code is at 100% line coverage (or the exclusion is justified)" | No coverage tooling is configured: `pytest-cov` is not in `backend/requirements.txt`, and Vitest runs without a coverage reporter. | Coverage is reported on the PR and a threshold is agreed. |
| "Each acceptance criterion has an automated test named or tagged with the Jira key" | Partly practised, not consistent — tests are grouped in classes without Jira keys in their names. | The team agrees on a naming or marker convention and backfills it. |

Until then, Phase 2's "full suite passes" and "verified against the real system" are what actually gate a merge. CI now enforces the first of those automatically on every PR; the reviewer in Phase 4 remains the check that the real-system verification actually happened, since no workflow can prove it.

---

## Related

- `docs/CI.md` — what the automated checks cover, what they deliberately do not, and the two targets below that are waiting on tooling described there.
- Root `AGENTS.md` — the working rules this checklist enforces (git workflow, TDD, security baseline, scope discipline).
- `docs/PROJECT_REVIEW.md` §C4 — the sprint plan and the Scrum evidence to capture alongside it.
- `docs/IMPLEMENTATION_MAP.md` — what exists right now, to check before building and to update after.
- `docs/REQUIREMENTS.md` — the behaviour specs, access matrix, and open questions (§9) this checklist tests against.
