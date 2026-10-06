# AGENTS.md — backend

Applies to everything under `backend/`. The root `AGENTS.md` still applies in full; this file adds backend-specific rules.

## Tech stack

Versions are pinned in `requirements.txt`. Check them before relying on version-specific behaviour, and look up docs for those exact versions.

| Concern | Choice |
|---|---|
| Language | Python 3.11 (`Dockerfile`: `python:3.11-slim`) |
| Web framework | FastAPI 0.115, served by Uvicorn 0.30 |
| Validation and settings | Pydantic 2.11, pydantic-settings 2.5, email-validator |
| Auth and data | Supabase via `supabase` (supabase-py) 2.31: Supabase Auth for credentials and JWTs, Postgres through PostgREST |
| HTTP client | httpx 0.27 |
| Tests | pytest 8.3, pytest-asyncio 0.24 (`asyncio_mode = auto`), respx 0.21 |

## Layout

```
backend/app/
  main.py                 app setup; routers mounted under settings.api_v1_prefix (/api/v1)
  core/                   config.py, security.py (get_current_user, require_roles), exceptions.py
  db/                     supabase.py client factories
  modules/<domain>/
    router.py             HTTP only: parse, guard, call the service, return the schema
    schemas.py            Pydantic request/response models
    service.py            business logic and the module's public API for other modules
    repository.py         Supabase reads/writes (optional; used by venues)
    <rules>.py            pure business rules with no I/O (optional; e.g. venues/search.py)
    dependencies.py       FastAPI dependencies (optional; auth re-exports core.security)
backend/tests/            pytest; conftest.py sets fake env vars and shared fixtures
```

Reference implementations: `modules/auth/` for Supabase Auth, and `modules/venues/` for the full router → service → repository flow with pure rules split out.

## Conventions

- **Routers stay thin.** No Supabase calls and no business rules in `router.py`.
- **Every endpoint is guarded** with `get_current_user` or `require_roles([...])`, and checks the caller's relationship to the resource, not just their role. The secret-key client bypasses RLS (root security baseline).
- **Import guards from `app.modules.auth.dependencies`**, not from `app.core.security` directly. The auth module re-exports them on purpose so other modules depend on its public surface. See `venues/router.py` for the pattern, including a named `Annotated` alias per access level (e.g. `VenueReader`).
- **Endpoints that call Supabase are plain `def`, not `async def`.** supabase-py is synchronous, so FastAPI runs a plain `def` in its threadpool, whereas an `async def` would block the event loop.
- **Errors** are typed exceptions in `app/core/exceptions.py`. Add new ones there instead of raising bare `HTTPException` from services. Report a Supabase outage as `503` (see `AuthServiceUnavailableError`), not `401` or `500`.
- **Supabase SDK traps** (see `docs/PROJECT_OVERVIEW.md` §5):
  - Never call `sign_in_with_password` or `refresh_session` on a shared client. Use `app.db.supabase.create_auth_client()`.
  - Import auth exceptions from `supabase_auth.errors`, never `gotrue.errors`.
- **Schema changes go through a migration** in `supabase/migrations/`, never ad-hoc SQL against the live project.

## Reuse

- **Pure rules in their own file.** Availability, overlap, suitability, and status-transition logic belongs in a no-I/O module (like `venues/search.py`), so other modules can call it and it can be unit-tested without mocks.
- **Cross-module calls go through `service.py`.** Another module may call `venues.service.some_function(...)`, but must never import another module's `repository.py` or `router.py`.
- **Cross-cutting pieces go in `app/core/` or `app/db/`**: guards, exceptions, config, client factories. Don't copy them into a module.
- **Shared schemas stay with their owning module.** If equipment needs a venue shape, import it from `venues.schemas` rather than redefining it.
- Before adding a helper, check the backend section of `docs/IMPLEMENTATION_MAP.md`.

## Tests

- Run `pytest` from `backend/`, and run the full suite before declaring done.
- Mock at the Supabase client seam (`get_supabase_admin_client`, `get_supabase_anon_client`, `create_auth_client`). Tests never hit live Supabase; verify against the real project separately (root "Verification").
- Name test files by module and behaviour (e.g. `test_venue_search.py`, `test_venues_api.py`), not by PBI ID. Put the ID (`SCRUM-<n>` or `NEW-<nn>`) in the test module's docstring for traceability.
- Cover the happy path, boundaries, failures (including Supabase outages), and authorisation denials for every endpoint.
