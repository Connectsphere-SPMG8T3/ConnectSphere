# Live demo: script and demo database — design

Date: 2026-11-04. Branch: `chore/live-demo`. Requested by Jie Ching.

## Why

At next week's presentation a grader picks one user story at random and Jie Ching shows it working live, in about 2–3 minutes, from their laptop against the shared Supabase project. The grader judges whether the story's acceptance criteria really work. There is no time to set data up on stage, so every story's starting state has to exist before the presentation, and there has to be a card that says exactly what to click.

## Goals

1. **A demo script** with one card for every story whose Status in the Product backlog sheet is DONE or IN REVIEW (73 stories on 2026-11-04: 47 Done, 26 In Review). Each card gives:
   - the story ID and title, and the AC(s) the demo proves;
   - the account to sign in as (seeded accounts, password `Cs1234`) and the active role to pick;
   - the demo record to open (by its `Demo · <ID> · …` name) and the page URL;
   - 3–6 numbered steps for the happy path, each with what should appear (exact numbers or text where they are deterministic, as in `docs/test-cases/fixtures/23r-demo-2026-11-04.md`);
   - at most one "key rule" step (a rejection, conflict, boundary or denial) when it fits the 2–3 minutes;
   - one line to say to the grader;
   - whether the story's state is used up by the demo (so a reset is needed before it can be shown again).
2. **A demo database**: the shared project's data replaced by `seed.sql` plus a demo starting state for every story card that needs one.
3. **A safe way back**: the pre-demo data restored after the presentation, proven by row counts.

## Non-goals

- No product code changes. If a story can't be demoed because of a defect, the card says so and the defect goes in `docs/DEFECTS.md`; it isn't fixed on this branch.
- No schema or migration changes.
- No changes to `verify_live.py`, the e2e suite or the backlog sheet.
- Not a regression run: the cards are a presenter's script, not test cases.

## Anti-goals (a failure even if it technically works)

- A card that asks the presenter to type or create something that might fail on stage, when it could have been pre-built.
- Demo data that changes state on its own before the presentation (hold expiry, reminders, past dates).
- Losing any pre-demo row on restore.
- Committing the backup, which holds password hashes and personal data.

## Decisions made by Jie Ching

- Audience: the lecturer/grader. Time per story: about 2–3 minutes.
- Pool: every story with Status DONE or IN REVIEW.
- Run from Jie Ching's laptop: local backend and frontend against the shared Supabase project.
- **Full swap**, not an overlay: back up the shared project's data, wipe it, load `seed.sql` + demo data, restore after the presentation. Teammates have agreed to the project being wiped and frozen for that window.
- The presentation is next week (week of 9 Nov 2026).

## Current state

- **Backup taken 2026-11-04 16:37 SGT**: `~/connectsphere-backups/2026-11-04-1637-pre-demo/`, outside the repo. One JSON file per table (`<schema>.<table>.json`, a JSON array of rows) for every `public` base table plus `auth.users` and `auth.identities`, and `_counts.json` with each table's row count (59 events, 19 auth users, 194 notifications, …). Sessions, refresh tokens and MFA claims were deliberately not backed up; users sign in again after a restore.
- No Docker on this machine, so `supabase db dump` doesn't work. SQL goes through `supabase db query --linked` (CLI 2.121.0 at `/home/linuxbrew/.linuxbrew/bin`), which outside an agent session prints a bare JSON array.
- `seed.sql` is idempotent (fixed ids, `on conflict do nothing`) and creates nine role accounts (`a0000000-…-0001` … `-0009`), the venue catalogue, equipment and the fixture events the live checks rely on.
- `public.notification_types` (47 rows) is reference data from migrations, not seed data.

## The parts

### 1. Wipe and load (`demo_db.py swap`)

- Deletes every row of every `public` base table **except reference tables** (at least `notification_types`; the builder confirms the full list from the migrations: any table whose rows a migration inserts and `seed.sql` doesn't), and every `auth.users` row (cascading to identities, sessions and profiles). Then runs `seed.sql`, then the demo loader.
- Refuses to run unless a backup directory with a `_counts.json` is passed and exists.
- Prints the row counts after loading.

### 2. Demo loader (`demo_data.py --load` / `--reset [ID …]`)

- Lives in `backend/scripts/`, next to `verify_live.py`, and reuses its API-client and `db_query` helpers rather than copying them.
- Builds each story's starting state **through the API, signed in as the seeded accounts**, wherever that state comes from a workflow (submit, assign, approve, hold, safety check, register, …), so history, notifications and assignments are real. Direct SQL only for plain fixtures with no workflow behind them (equipment outages, venue blocks if no endpoint fits).
- Every record it creates is named `Demo · <ID> · <what it is>` (events, venues, equipment). Never `live-check` (the live checks delete stale `live-check` rows) and never the seed's names.
- One demo event per story whose demo changes state, so showing one story never uses up another's starting state.
- Read-only stories (dashboards, profile, catalogue, role switcher) get no data of their own when seed data plus other stories' demo events already show them well; their card points at those.
- Dates: on or after 1 Dec 2026, so nothing expires or fires before the presentation. Exception: a story whose AC depends on time relative to now (reminders, "upcoming", hold expiry) gets dates computed from the load time, and its card says it must be loaded on presentation day.
- `--reset <ID>` deletes that story's `Demo · <ID>` records and builds them again, for when a story is picked twice; `--reset` with no ID does all of them. Idempotent: running `--load` twice doesn't duplicate anything.
- Each story's starting state is checked after it's built (the API returns the expected status/count), and the loader stops with the story ID if a check fails.

### 3. Restore (`demo_db.py restore <backup-dir>`)

- Wipes as in part 1, then inserts every backed-up row exactly as it was (same ids, timestamps and columns) with triggers not firing (so no duplicate history, notifications or profiles), in foreign-key order, in one transaction.
- Compares each table's count with `_counts.json` and fails loudly on any difference.
- **Rehearsed before the first real swap**: run wipe + restore inside a single transaction that is rolled back, and show the counts match. The swap doesn't happen until this rehearsal passes.

### 4. The script (a PDF, not in the repo)

- Delivered as a PDF outside the repository (Jie Ching's decision): written as markdown/HTML in a working folder outside the repo, rendered to `~/connectsphere-demo/LIVE_DEMO.pdf` and sent to Jie Ching. Nothing from it is committed.
- One card per story, grouped by role/epic, with an index table at the top (ID → title → account → event) so any story is found in seconds.
- Before-the-presentation checklist: swap done, both servers running, sign in fresh (D4: sessions die after 1 hour), browser at 100% zoom, console open in a hidden tab.
- Built from each story's AC in the Product backlog sheet (column I), `docs/test-cases/*.md` and `frontend/e2e/*.e2e.js`, which already hold the click paths.
- Every card is dry-run once against the demo database before the presentation (the builder drives the API/browser to confirm each step's expected result; Jie Ching does a final read-through in a real browser).

## Left to the builder

- Exact file split and helper names, how the loader groups stories, and which read-only stories need no data.
- How triggers are disabled during restore (e.g. `session_replication_role = replica`), as long as the rehearsal proves the counts and a spot check of a few rows match.
- Whether `swap`/`restore` share code with the backup script (`backup` should become a subcommand of `demo_db.py` so the next backup uses the same code).

## Risks

- **23-R demo on 4 Nov** is done (confirmed by Jie Ching), so its fixtures may be wiped. They're in the backup.
- **Defects found while dry-running.** A card that can't be shown cleanly is flagged at the top of the script so Jie Ching can decide before the presentation.
- **Supabase Auth rate limits** on the many sign-ins the loader makes: sign in once per account and reuse the token.
- **Teammates writing during the swap window** lose that work on restore (accepted).
