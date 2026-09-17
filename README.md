# ConnectSphere

ConnectSphere is a regional event planning and venue booking platform for Singapore, orchestrating workflows across five user roles: **Event Organiser**, **Event Coordinator**, **Venue Staff**, **Technical Support Staff**, and **Attendee**.

This repository implements a **Modular Monolith** architecture:

- **`backend/`** — Python FastAPI, organised into domain modules (`auth`, `events`, `venues`, `equipment`) sharing a common `core` and `db` layer.
- **`frontend/`** — Vue 3 (Composition API, `<script setup>`), Vite, Pinia, Vue Router, and Tailwind CSS styled with a Bauhaus constructivist design system.
- **`supabase/`** — PostgreSQL schema migrations, seed data, and Supabase Auth configuration.
- **`mcp/`** — Supabase MCP server configuration for project `vuiryrzzyfecjqftwicj`.

For the full business context (roles, the Scrum item this implements, and the architectural reasoning behind it), see [docs/SCENARIO.md](docs/SCENARIO.md). For a step-by-step local setup, see [docs/SETUP.md](docs/SETUP.md) (this README's [Getting started](#getting-started) is the short version).

## Current scope: SCRUM-48 — Secure Login & Role-Based Dashboards

Implements the foundational authentication service:

1. Login with email/password against Supabase Auth, issuing a JWT session.
2. Role-based redirection to one of five dashboard placeholders.
3. `GET /profile/me` (frontend) / `GET /api/v1/auth/me` (backend) to view the authenticated user's profile.
4. Route guards that intercept unauthorised access and redirect to login or an appropriate dashboard.

## Getting started

See [Run instructions](#run-instructions) below for the full local setup.

### Prerequisites

- Python 3.11+
- Node.js 20+
- A Supabase project (this repo targets `vuiryrzzyfecjqftwicj`)
- Supabase CLI (optional, for local migrations)

### 1. Configure environment variables

```bash
cp .env.example .env
# fill in SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_SECRET_KEY
```

### 2. Apply database migrations and seed data

```bash
supabase link --project-ref vuiryrzzyfecjqftwicj
supabase db push
psql "$DATABASE_URL" -f supabase/seed.sql
```

### 3. Run the backend

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API is served at `http://localhost:8000`, docs at `http://localhost:8000/docs`.

### 4. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

The app is served at `http://localhost:5173`.

### 5. Run backend tests

```bash
cd backend
pytest
```

## Run instructions

| Step | Command | Notes |
|------|---------|-------|
| Migrate DB | `supabase db push` | Creates `user_role` enum, `public.profiles`, trigger, RLS policies |
| Seed test accounts | `psql "$DATABASE_URL" -f supabase/seed.sql` | One account per role, see below |
| Start backend | `uvicorn app.main:app --reload --port 8000` | Run from `backend/` |
| Start frontend | `npm run dev` | Run from `frontend/` |
| Run tests | `pytest` | Run from `backend/` |

### Seeded test accounts

| Role | Email | Password | Notes |
|------|-------|----------|-------|
| Event Organiser | organiser@connectsphere.dev | Cs1234 | Single role |
| Event Coordinator | coordinator@connectsphere.dev | Cs1234 | Dual-role account (double hat): also holds **Venue Staff** in `user_roles` for SCRUM-74/75 role switcher testing |
| Venue Staff | venue.staff@connectsphere.dev | Cs1234 | Single role |
| Technical Support | tech.support@connectsphere.dev | Cs1234 | Single role |
| Attendee | attendee@connectsphere.dev | Cs1234 | Single role |

## Architecture notes

- Authentication credentials (email/password) live in Supabase-managed `auth.users`; domain attributes (role, department, organisation) live in `public.profiles`, kept in sync via a Postgres trigger on user creation.
- The FastAPI backend never re-implements password verification — it defers to Supabase's GoTrue API, then verifies the returned JWT via the Supabase SDK's `get_claims`, which validates against the project's published JWKS (supporting both the legacy HS256 shared-secret scheme and the current asymmetric ES256 signing keys) rather than a single hardcoded secret.
- Each backend module (`auth`, `events`, `venues`, `equipment`) is self-contained (`router.py`, `schemas.py`, `service.py`) so future domains can be added without touching existing modules.
