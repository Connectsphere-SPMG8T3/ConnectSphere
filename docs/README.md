# ConnectSphere docs

Every file here has one job, and its name says which. Start with the question you have.

## Which file

| File | What it answers | How it changes |
|---|---|---|
| [`REQUIREMENTS.md`](REQUIREMENTS.md) | What should the system do? Behaviour specs per feature, the access matrix, the domain model, the event lifecycle, customer Q&A answers, open questions | Edited when a rule, assumption or design decision changes |
| [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) | Who is the customer, what is in the first release, and why is the system built this way? Course context, the 20 core features, architecture, design system, database principles | Rarely: only when the customer or the architecture changes |
| [`IMPLEMENTATION_MAP.md`](IMPLEMENTATION_MAP.md) | What exists right now? Status by story, endpoints, components, tables, and what to know before building on them | Edited in place with every change |
| [`BUILD_LOG.md`](BUILD_LOG.md) | How was story SCRUM-XX or CR-XX built and verified? Verbatim backlog record (Jira until Sprint 2), interpretation, what was built | Append-only: one entry per story, fix or enabler |
| [`DEFECTS.md`](DEFECTS.md) | What is known to be broken, and is it fixed? D1, D2, … with evidence and status | Edited in place: new rows, status updates |
| [`ROADMAP.md`](ROADMAP.md) | What is planned for each sprint? | Edited at sprint planning |
| [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md) | When is a backlog item Done? The team's checklist, from the Scrum playbook | Edited when the team changes the DoD at a retrospective |
| [`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md) | How does an item get from Ready to Done, and who does each step? | Edited when the team changes how it works |
| [`SETUP.md`](SETUP.md) | How do I run everything locally? | Edited when setup changes |
| [`CI.md`](CI.md) | What does CI check, and what doesn't it? | Edited when the workflow changes |
| [`MUTATION_TESTING.md`](MUTATION_TESTING.md) | Would our tests catch a bug? How to run mutation testing, what to fix, and the sprint-by-sprint scores | A baseline row each sprint; edited when the practice changes |
| [`adr/`](adr/) | Why did we make architecture decision X? One numbered record per decision | A new file per decision; accepted ones aren't rewritten |
| [`test-cases/`](test-cases/README.md) | How do I test feature X by hand? One file per area, `TC-*` IDs | New cases per story |
| [`test-cases/runs/`](test-cases/runs/README.md) | When was it last tested, and what passed? One file per run | A new file per run |
| [`archive/`](archive/) | Dated snapshots kept for the record, no longer updated | Never |

The repo root also has [`CONTEXT.md`](../CONTEXT.md), the domain glossary (Block, Hold, Availability, Suitability, …), and [`AGENTS.md`](../AGENTS.md), the workflow every contributor and AI agent follows.

## Where to look for what

| Question | Where to look |
|----------|----------------|
| "How does login actually work end to end?" | `frontend/src/stores/auth.js` → `frontend/src/services/api.js` → `backend/app/modules/auth/router.py` → `service.py` |
| "How is a route protected?" | `frontend/src/router/index.js` (`beforeEach` guard) |
| "How is a role protected on the backend?" | `backend/app/core/security.py` (`require_roles`) |
| "What does a user's profile contain?" | `supabase/migrations/20260912000001_init_auth_and_profiles.sql`, mirrored in `backend/app/modules/auth/schemas.py::ProfileResponse` |
| "What test accounts exist?" | `supabase/seed.sql`, table in [`SETUP.md`](SETUP.md) |
| "How does venue search decide what to show?" | `backend/app/modules/venues/search.py` (pure rules) → `repository.py` (Supabase reads) → `router.py`; SPA in `frontend/src/features/venues/` and `views/venues/` |
| "Why can't two events book the same venue?" | `venue_bookings_no_overlap` in `supabase/migrations/20260915090000_venues_catalogue_and_availability.sql` (DB-1), checked by `supabase/verification/venue_schema_checks.sql` |
| "What do Block, Hold, Availability, Suitability mean here?" | [`CONTEXT.md`](../CONTEXT.md) at the repo root |
| "What exactly does story SCRUM-XX require, verbatim?" | That story's entry in [`BUILD_LOG.md`](BUILD_LOG.md) (each entry is self-contained and quotes its backlog record verbatim) |
| "What has been built so far?" | [`IMPLEMENTATION_MAP.md`](IMPLEMENTATION_MAP.md) §1 for the current status; [`BUILD_LOG.md`](BUILD_LOG.md) in order for how it got there |
| "What's in scope for the whole first release?" | [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) §3 (20 features) |
| "What's out of scope entirely (for now)?" | Anything in the customer briefing not listed in [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) §3, and [`REQUIREMENTS.md`](REQUIREMENTS.md) §8 and §11 |
| "What's next?" | The next-highest-priority item in the [Product backlog sheet](https://docs.google.com/spreadsheets/d/18y09jIMc9t1FtvTEM_6u74uWNAg8hrW0eF_LehVgWVY/edit); [`ROADMAP.md`](ROADMAP.md) for the sprint plan behind it |
| "How does the team run Scrum?" | The [Team A-HA! Scrum Playbook](https://docs.google.com/document/d/1wd96yzFLZQ1FNZQFfbxzSQvRzzqs9ZJkgrZUEBKbItg/edit): board, Definition of Ready, estimation, change management |
| "When is a story actually done? What do I do after merging?" | [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md) for the checklist; [`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md) §4–5 for the human steps (teammate review, PO acceptance, merge, Status → Done in the backlog) |
| "I just finished a story — what do I update?" | §3 of [`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md): a [`BUILD_LOG.md`](BUILD_LOG.md) entry, [`IMPLEMENTATION_MAP.md`](IMPLEMENTATION_MAP.md), test cases, and [`REQUIREMENTS.md`](REQUIREMENTS.md) / [`DEFECTS.md`](DEFECTS.md) if they changed |

## Old names

Files were renamed on 2026-09-28. Jira comments, commits and older log entries still use the old names:

| Old reference | Now |
|---|---|
| `SCENARIO.md` §4, §4.N | [`BUILD_LOG.md`](BUILD_LOG.md) §4.N (same numbers) |
| `SCENARIO.md` §1–§3, §5–§7 | [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md), same section numbers |
| `SCENARIO.md` §8 | "Where to look for what" above |
| `PROJECT_REVIEW.md` D1–D16 (§A2) | [`DEFECTS.md`](DEFECTS.md), same numbers |
| `PROJECT_REVIEW.md` §A1, §A3, Part B | [`archive/2026-09-13-design-review.md`](archive/2026-09-13-design-review.md) |
| `PROJECT_REVIEW.md` Part C, §C1–§C4 | [`ROADMAP.md`](ROADMAP.md), same labels |
| `TEST_CASES.md` | [`test-cases/`](test-cases/README.md), same `TC-*` IDs |
| `HANDOFF_SPRINT1.md`, `superpowers/`, `proposals/` | Removed; retrieve them from git history (e.g. `git show 36aa9a7:docs/HANDOFF_SPRINT1.md`) |
