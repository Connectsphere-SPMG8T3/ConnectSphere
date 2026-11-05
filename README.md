# ConnectSphere

ConnectSphere is a regional event planning and venue booking platform for Singapore, orchestrating workflows across seven user roles: **Event Organiser**, **Event Coordinator**, **Event Coordinator Lead**, **Venue Staff**, **Technical Support Staff**, **Safety Officer**, and **Attendee**.

This repository implements a **Modular Monolith** architecture:

- **`backend/`** — Python FastAPI, organised into domain modules (`auth`, `events`, `venues`, `equipment`) sharing a common `core` and `db` layer.
- **`frontend/`** — Vue 3 (Composition API, `<script setup>`), Vite, Pinia, Vue Router, and Tailwind CSS styled with a Bauhaus constructivist design system.
- **`supabase/`** — PostgreSQL schema migrations, seed data, and Supabase Auth configuration.
- **`mcp/`** — Supabase MCP server configuration for project `vuiryrzzyfecjqftwicj`.

For the full business context (the roles and the architectural reasoning behind the design), see [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) (and [docs/README.md](docs/README.md) for every other doc). For a step-by-step local setup, see [docs/SETUP.md](docs/SETUP.md) (this README's [Getting started](#getting-started) is the short version).

**Contributing?** The team's Scrum process is in the [Playbook](https://docs.google.com/document/d/1wd96yzFLZQ1FNZQFfbxzSQvRzzqs9ZJkgrZUEBKbItg/edit), and the backlog is in the [Product backlog sheet](https://docs.google.com/spreadsheets/d/18y09jIMc9t1FtvTEM_6u74uWNAg8hrW0eF_LehVgWVY/edit). [docs/DEFINITION_OF_DONE.md](docs/DEFINITION_OF_DONE.md) is the checklist every backlog item has to clear before it counts as Done. [docs/DEVELOPMENT_WORKFLOW.md](docs/DEVELOPMENT_WORKFLOW.md) walks through each step from Ready to Done: PR review, the PO's acceptance, merge, and setting the item to Done in the backlog. The working rules behind it (branch naming, test-first development, the security baseline) are in [AGENTS.md](AGENTS.md), which applies to human contributors as much as to AI agents.

## Getting started

See [Run instructions](#run-instructions) below for the full local setup.

### Prerequisites

- Python 3.11+
- Node.js 20+
- A Supabase project (this repo targets `vuiryrzzyfecjqftwicj`)
- Supabase CLI (optional, for local migrations)

### 1. Configure environment variables

macOS / Linux / WSL:

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env
```

Then fill in `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and `SUPABASE_SECRET_KEY` (and the `VITE_` values in `frontend/.env`).

### 2. Apply database migrations and seed data

```bash
supabase link --project-ref vuiryrzzyfecjqftwicj
supabase db push
psql "$DATABASE_URL" -f supabase/seed.sql
```

### 3. Run the backend

macOS / Linux / WSL:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Windows PowerShell:

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Creating the virtualenv and `pip install` are one-time steps; after that, activate it in each new terminal before starting the server. For cmd, Git Bash, or a PowerShell "running scripts is disabled" error, see [docs/SETUP.md §4](docs/SETUP.md#4-backend).

The API is served at `http://localhost:8000`, docs at `http://localhost:8000/docs`.

### 4. Run the frontend

In a second terminal (same commands on every OS):

```bash
cd frontend
npm install
npm run dev
```

The app is served at `http://localhost:5173`.

### 5. Run backend tests

With the virtualenv active:

```bash
cd backend
pytest
```

To measure coverage, run `pytest --cov` here, or `npm run test:coverage` in `frontend/`. Use the full suite each time: CI fails a run that drops below the floor in [docs/CI.md](docs/CI.md) §4 item 2.

## Run instructions

| Step | Command | Notes |
|------|---------|-------|
| Migrate DB | `supabase db push` | Creates `user_role` enum, `public.profiles`, trigger, RLS policies |
| Seed test accounts | `psql "$DATABASE_URL" -f supabase/seed.sql` | Creates 9 accounts covering all 7 roles, see below |
| Start backend | `uvicorn app.main:app --reload --port 8000` | Run from `backend/` |
| Start frontend | `npm run dev` | Run from `frontend/` |
| Run tests | `pytest` | Run from `backend/` |

### Seeded test accounts

| Role | Name | Email | Password | Notes |
|------|------|-------|----------|-------|
| Event Organiser | Olivia Tan | organiser@connectsphere.dev | Cs1234 | Single role |
| Event Coordinator | Marcus Lim | coordinator@connectsphere.dev | Cs1234 | Dual-role account (double hat): also holds **Venue Staff** in `user_roles` for SCRUM-74/75 role switcher testing |
| Venue Staff | Priya Nair | venue.staff@connectsphere.dev | Cs1234 | Single role |
| Technical Support | Daniel Wong | tech.support@connectsphere.dev | Cs1234 | Single role |
| Attendee | Siti Rahman | attendee@connectsphere.dev | Cs1234 | Single role |
| Safety Officer | Hafiz Ismail | safety.officer@connectsphere.dev | Cs1234 | Single role (CR-103 AC5) |
| Event Coordinator Lead | Grace Chua | coordinator.lead@connectsphere.dev | Cs1234 | Single role (12 AC12) |
| Event Coordinator Lead (second) | Daniel Foo | coordinator.lead2@connectsphere.dev | Cs1234 | Single role; a second Lead, so CR-101 AC5's scope (each Lead sees the events they assigned) can be tested |
| Event Coordinator (second) | Nadia Koh | coordinator2@connectsphere.dev | Cs1234 | Single role; a second coordinator for assignment and cross-coordinator checks |

## Architecture notes

- Authentication credentials (email/password) live in Supabase-managed `auth.users`; domain attributes (role, department, organisation) live in `public.profiles`, kept in sync via a Postgres trigger on user creation.
- The FastAPI backend never re-implements password verification — it defers to Supabase's GoTrue API, then verifies the returned JWT via the Supabase SDK's `get_claims`, which validates against the project's published JWKS (supporting both the legacy HS256 shared-secret scheme and the current asymmetric ES256 signing keys) rather than a single hardcoded secret.
- Each backend module (`auth`, `events`, `venues`, `equipment`) is self-contained (`router.py`, `schemas.py`, `service.py`) so future domains can be added without touching existing modules.
