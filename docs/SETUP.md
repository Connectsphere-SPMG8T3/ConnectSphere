# ConnectSphere — Setup Guide

This document walks through getting the full stack (Supabase, FastAPI backend, Vue frontend) running locally, and records the environment decisions made while first scaffolding the project so they don't need to be re-derived later. For the business/course context behind these decisions (the customer briefing, the first-release scope, and the exact SCRUM-48 ticket this implements), see [docs/SCENARIO.md](SCENARIO.md).

> **Login field note:** the SCRUM-48 Jira ticket's acceptance criteria say "username and password." This implementation authenticates by **email** and password instead, since Supabase Auth's `sign_in_with_password` is email-based and `public.profiles.email` is the unique identifying field (there is no separate username column). If the customer clarifies during Q&A that a distinct, non-email username is required, that's a schema and auth-flow change, not just a label change on the login form.

## 1. Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | Backend runtime |
| Node.js | 20+ | Frontend runtime |
| Supabase project | — | Targets project ref `vuiryrzzyfecjqftwicj` |
| Supabase CLI | latest | Optional, for `supabase db push` / local dev |

## 2. Environment variables

Two `.env.example` files exist — copy each to a real `.env` alongside it and fill in credentials from the Supabase dashboard (Project Settings → API):

- `/.env.example` → `/.env` (used by `docker-compose.yml` and as a reference for the values below)
- `frontend/.env.example` → `frontend/.env` (used directly by Vite; only `VITE_`-prefixed vars are exposed to the browser)

Required values:

| Variable | Where it's used | Source |
|----------|-----------------|--------|
| `SUPABASE_URL` | backend | Supabase dashboard → API → Project URL |
| `SUPABASE_PUBLISHABLE_KEY` (frontend: `VITE_SUPABASE_PUBLISHABLE_KEY`) | backend, frontend | Supabase dashboard → **Settings → API Keys** → the `publishable` key. Safe to expose to the browser. |
| `SUPABASE_SECRET_KEY` | backend only | Supabase dashboard → **Settings → API Keys** → a `secret` key. **Never** expose this to the frontend or commit it. |

No separate JWT secret is configured: session tokens are verified via the Supabase SDK's `get_claims()` (see `app/core/security.py`), which fetches and locally caches this project's published JWKS — this transparently supports both the legacy HS256 shared-secret scheme and newer asymmetric (ES256) signing keys, whichever the project uses, without the backend needing to know or store a secret itself.

> **Key naming note:** this project uses Supabase's newer **publishable**/**secret** API keys rather than the legacy **anon**/**service_role** JWT keys — Supabase is retiring the legacy keys (removal planned for late 2026) in favour of these, and they are drop-in compatible: the client libraries just take whichever key string you give them, no code changes needed. If you only have legacy anon/service_role keys for this project, they still work identically — just put them in the same `SUPABASE_PUBLISHABLE_KEY`/`SUPABASE_SECRET_KEY` slots (the names describe the *role* the key plays, not which key generation it is).

> **Security note:** `.env.example` files are committed to git and must only ever contain placeholder values (e.g. `your-publishable-key-here`). If a real secret is ever pasted into an example file by mistake, rotate that secret in the Supabase dashboard and scrub it from the file (and git history if it was committed) before treating it as safe again.

## 3. Database: migrations and seed data

```bash
supabase link --project-ref vuiryrzzyfecjqftwicj
supabase db push                              # applies supabase/migrations/*.sql
psql "$DATABASE_URL" -f supabase/seed.sql     # creates 5 test accounts, one per role
```

`supabase/migrations/20260912000001_init_auth_and_profiles.sql` creates the `user_role` enum, `public.profiles` table, indexes, the `handle_new_user()` trigger (auto-populates a profile row when a new `auth.users` row is inserted), and RLS policies. `20260913120749_fix_auth_security_defects.sql` then restricts sign-up to the external roles (`event_organiser`, `attendee`), replaces the `profiles` policies with a non-recursive version backed by `private.current_user_role()`, and pins `search_path` on the auth functions (see `docs/SCENARIO.md` §4.2).

`20260915090000_venues_catalogue_and_availability.sql` (SCRUM-39) adds the venue catalogue: the `venue_layout` / `facility` / `accessibility_feature` / `venue_booking_status` / `venue_block_reason` enums, the `venues`, `venue_layouts`, `venue_facilities`, `venue_blocks` and `venue_bookings` tables, the `btree_gist` exclusion constraint that makes overlapping venue bookings impossible (DB-1), and staff-only read policies (see `docs/SCENARIO.md` §4.4). Before pushing, run `supabase migration list --linked` — the live history had drifted once (PROJECT_REVIEW D8).

`supabase/seed.sql` inserts directly into `auth.users` / `auth.identities` (the standard pattern for locally seeding confirmed Supabase Auth accounts outside the GoTrue signup API) so the five role-specific test accounts exist immediately, with no email confirmation step needed. Because the trigger no longer accepts staff roles from sign-up metadata, the seed sets each profile's role explicitly afterwards.

Verify the auth/RLS security rules after applying migrations and seed (runs inside a transaction that rolls back, and raises on any failure):

```bash
psql "$DATABASE_URL" -f supabase/verification/auth_security_checks.sql   # expect: ALL AUTH SECURITY CHECKS PASSED
psql "$DATABASE_URL" -f supabase/verification/venue_schema_checks.sql    # expect: ALL VENUE SCHEMA CHECKS PASSED
```

Without `DATABASE_URL`, the linked Supabase CLI runs the same scripts: `supabase db query --linked -f supabase/verification/venue_schema_checks.sql`.

The seed also loads 8 venues with a few blocks and bookings around 10 Oct 2026, so a venue search for that afternoon shows every exclusion reason (TEST_CASES §8).

### Seeded test accounts

All seeded accounts share the password `Cs1234`. Emails intentionally use the `@connectsphere.dev` domain, **not** `.test` — `pydantic.EmailStr` (via `email-validator`) rejects RFC 2606 reserved TLDs (`.test`, `.example`, `.invalid`, `.localhost`) as invalid addresses, which would make the seeded accounts unable to log in through the backend's `UserLoginRequest` validation.

| Role | Email |
|------|-------|
| Event Organiser | organiser@connectsphere.dev |
| Event Coordinator | coordinator@connectsphere.dev |
| Venue Staff | venue.staff@connectsphere.dev |
| Technical Support | tech.support@connectsphere.dev |
| Attendee | attendee@connectsphere.dev |

## 4. Backend

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs: `http://localhost:8000/docs`. Health check: `GET /health`.

Run tests:

```bash
cd backend
pytest
```

The test suite (`backend/tests/test_auth.py`) mocks the Supabase client at the seams rather than hitting a real Supabase project, so it runs offline and needs no real credentials — `backend/tests/conftest.py` seeds dummy env vars before importing the app. The seams are:

- `app.modules.auth.service.create_auth_client` — the fresh per-request client used for sign-in and refresh;
- `app.modules.auth.service.get_supabase_anon_client` — the shared client, used for logout's `auth.admin.sign_out`;
- `app.modules.auth.service.get_supabase_admin_client` and `app.core.security.get_supabase_admin_client` — profile reads;
- `app.core.security.get_supabase_anon_client` — `auth.get_claims()`.

A few tests deliberately use real supabase-py client objects (no network) or real concurrency, because the defects they guard against lived in SDK session state and event-loop blocking, which mocks can't reproduce.

Session lifecycle endpoints: `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh` (exchanges a refresh token for a new session; Supabase rotates the refresh token on every use), `GET /api/v1/auth/me`, `POST /api/v1/auth/logout` (revokes only the caller's current session).

## 5. Frontend

```bash
cd frontend
npm install
npm run dev
```

Served at `http://localhost:5173`. Build for production with `npm run build` (output in `frontend/dist/`, gitignored).

The frontend resolves `@/` to `frontend/src/` (configured in `vite.config.js`).

Run tests:

```bash
cd frontend
npm test
```

Unit tests use Vitest with a jsdom environment and live in `__tests__/` folders next to the code they cover (e.g. `src/stores/__tests__/`). They mock `@/services/api`, so no backend is needed.

## 6. Docker Compose (optional)

`docker-compose.yml` at the repo root runs both services against a shared `.env`:

```bash
docker compose up
```

## 7. Verifying the auth flow manually

1. Start the backend and frontend as above (with real Supabase credentials and a seeded database).
2. Visit `http://localhost:5173/login`.
3. Log in with one of the seeded accounts.
4. Confirm redirection to the role-appropriate dashboard (e.g. `coordinator@connectsphere.dev` → `/dashboard/coordinator`).
5. Visit `/profile/me` and confirm the profile details match the seeded row.
6. Try navigating to a different role's dashboard URL directly — the router guard should redirect you back to your own dashboard.
7. Log out and try visiting a `/dashboard/*` URL directly — you should be redirected to `/login?redirect=...`.

This exact flow was verified during initial scaffolding using a headless Chromium session (Playwright) driving the real Vite dev server, with a mocked `localStorage` session standing in for a real Supabase login (no live Supabase project was available at scaffold time).
