# Sprint 1 Handoff — picking up the remaining stories

> **Temporary document.** This is a one-time onboarding note for whoever picks up the stories below (and their AI assistant). It duplicates pointers that already live in `docs/SETUP.md` and `docs/SCENARIO.md` so you don't have to go hunting on your first hour on the repo. Once Sprint 1 is done, delete this file — `docs/SCENARIO.md` is the permanent, append-only record of what each story actually did.

## 1. What's already done

**SCRUM-48 (Basic user authentication)** is fully implemented, tested, and verified end-to-end against the live Supabase project (login, `/auth/me`, logout, role-based dashboard redirect, router guards). Read `docs/SCENARIO.md` §4.1 before touching auth code — it also documents 5 real bugs found during live verification (wrong API key format, wrong JWT verification scheme, wrong exception module, etc.) so you don't reintroduce them.

As a side effect of building auth, some scaffolding for *other* stories already exists — see §3 below. Check before creating new files.

## 2. Environment setup

Follow `docs/SETUP.md` top to bottom. Quick version:

```bash
# backend
cd backend && python -m venv .venv && . .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Or `docker compose up` from the repo root (needs the root `.env` filled in — ask whoever has it, it holds live Supabase keys and is gitignored).

Seeded test accounts (password `Cs1234` for all): `organiser@connectsphere.dev`, `coordinator@connectsphere.dev`, `venue.staff@connectsphere.dev`, `tech.support@connectsphere.dev`, `attendee@connectsphere.dev`.

## 3. What already exists — don't recreate it

**Backend** (`backend/app/modules/`): `auth/` is fully built (use it as the reference pattern — `router.py` / `schemas.py` / `service.py` / `dependencies.py`). `equipment/`, `events/`, `venues/` already exist as **empty placeholder packages** (just `__init__.py`) — build inside these, don't create new top-level modules.

**Frontend**: routes and dashboard shells already exist:
- `frontend/src/router/index.js` already defines `/profile/me` and all 5 role-gated dashboard routes (`/dashboard/organiser`, `/dashboard/coordinator`, `/dashboard/venue-staff`, `/dashboard/tech-support`, `/dashboard/attendee`) with `meta.allowedRoles` guards.
- `frontend/src/views/dashboards/{OrganiserDashboard,CoordinatorDashboard,VenueStaffDashboard,TechSupportDashboard,AttendeeDashboard}.vue` already exist as placeholders — **extend these files**, don't create new ones.
- `frontend/src/views/ProfileView.vue` already exists and calls `GET /auth/me`.
- Shared components live in `frontend/src/components/common/` (`BauhausButton`, `BauhausCard`, `BauhausInput`, `BauhausNavbar`) — reuse these for visual consistency, don't rebuild inputs/buttons/cards per story.
- Pinia: only `frontend/src/stores/auth.js` exists so far. New stores (e.g. a `venues` or `events` store) should follow its shape.

**Database**: only one migration exists, `supabase/migrations/20260912000001_init_auth_and_profiles.sql` (the `user_role` enum + `public.profiles`). No `venues`, `events`, or `equipment` tables exist yet — several stories below need a new migration before any backend work.

## 4. Reusable prompts — use these with your AI

`docs/prompts/` has four task prompts written for this exact codebase (conventions, module pattern, testing approach, migration style). Copy the relevant one into your AI assistant and fill in the `## Task` section at the bottom with your story's specifics:

- `docs/prompts/db-task.md` — for writing a new Supabase migration (do this first if your story needs a new table)
- `docs/prompts/backend-task.md` — for a new FastAPI module (router/schemas/service/dependencies)
- `docs/prompts/vue-frontend-task.md` — for extending a dashboard view or building a new component
- `docs/prompts/test-task.md` — for writing pytest tests mocked at the Supabase client seam (see `backend/tests/test_auth.py` as the reference; mock `get_supabase_admin_client`/`get_supabase_anon_client`, don't hit live Supabase in tests)

These are gitignored (local workflow aids), so they won't show up as a project deliverable — just tools to save you re-explaining conventions to your AI.

## 5. Suggested story → file mapping

| Story | Needs new migration? | Backend module | Frontend |
|---|---|---|---|
| SCRUM-50 — See my own profile | No | `auth` (already has `GET /me`) | `ProfileView.vue` already wired up — **verify it actually satisfies SCRUM-50's acceptance criteria** and add a dedicated test if the story needs behaviour beyond what SCRUM-48 already covers |
| SCRUM-39 — View Venue Catalogue | Yes — `venues` table | `venues/` | new list view (no placeholder yet — check with whoever owns SCRUM-70/71/72 dashboards, since they'll likely embed this) |
| SCRUM-70 — Venue Staff Dashboard | depends on venues/events | `venues/` (+ maybe `events/`) | `VenueStaffDashboard.vue` |
| SCRUM-71 — Event Organiser Dashboard | depends on events | `events/` | `OrganiserDashboard.vue` |
| SCRUM-8 — Event Request Creation | Yes — `events` table | `events/` | likely a form component, surfaced from `OrganiserDashboard.vue` |
| SCRUM-72 — Event Coordinator Dashboard | depends on events | `events/` | `CoordinatorDashboard.vue` |
| SCRUM-73 — Technical Support Staff Dashboard | depends on equipment | `equipment/` | `TechSupportDashboard.vue` |
| SCRUM-23 — Equipment Availability Checking | Yes — `equipment` table | `equipment/` | likely surfaced in `TechSupportDashboard.vue` and/or the organiser's request flow |

**Coordinate on migrations**: SCRUM-39, SCRUM-8, and SCRUM-23 each want a new table, and events/equipment likely reference venues. Whoever picks these up first should decide table shape together (or at least check `supabase/migrations/` for what's already landed) rather than each writing a conflicting migration independently.

## 6. When a story is done

Add an entry to `docs/SCENARIO.md` under `## 4. Implementation log`, following the existing `### 4.1. SCRUM-48 — ...` entry as the template (ticket mapping + a verification section noting anything that only broke when tested against the real Supabase project). Add manual test cases to `docs/TEST_CASES.md` in the same style as the existing `TC-AUTH-0xx` entries.
