# ConnectSphere — Manual Test Cases (SCRUM-48: Basic User Authentication · SCRUM-39: Venue Catalogue & Search · SCRUM-72: Coordinator Dashboard · SCRUM-70: Venue Staff Dashboard)

Manual test-case suite for the features implemented so far:

- **§1–§7 — SCRUM-48: Basic user authentication** (epic SCRUM-7): login, session/profile retrieval, logout, and role-based dashboard routing.
- **§8 — SCRUM-39: Venue catalogue, search and availability**.
- **§9 — SCRUM-72: Event Coordinator dashboard**: the prioritised action list, the active-event status overview, and their empty states.
- **§10 — SCRUM-70: Venue Staff dashboard**: the four work-queue tiles, the month calendar, the pending-request list and the venue list — all against real seeded data.

See [docs/SCENARIO.md](SCENARIO.md) for the full requirement context and [docs/SETUP.md](SETUP.md) for environment setup.

Every test case traces back to either the SCRUM-48 acceptance criteria, a customer-briefing non-functional requirement (security, reliability/consistency), or a concrete implementation detail (an exception type, a route guard) — see the traceability matrix in §7. Cases are written to be run manually against a running instance of the app, but each names the exact code path it exercises so it can be converted into an automated test later.

## 0. Scope, environment, and data notes

- **In scope:** `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `GET /api/v1/auth/me`, `POST /api/v1/auth/logout`, the `LoginView`/`ProfileView` pages, the five role dashboards as RBAC targets, and the Vue Router guards that protect them.
- **Also in scope (§8):** `GET /api/v1/venues`, `GET /api/v1/venues/{id}`, the `/venues` search page and `/venues/:id` detail page (SCRUM-39).
- **Also in scope (§9):** the Event Coordinator dashboard's presentation logic (SCRUM-72) — rendering, ordering, and empty states, not event data.
- **Also in scope (§10):** `GET /api/v1/venues/dashboard/venue-staff`, the `/dashboard/venue-staff` page and the `/bookings/:id` placeholder (SCRUM-70). Unlike §9 this runs against real data, since the venue tables exist and are seeded.
- **Out of scope:** everything under the `events` and `equipment` **backend** modules — empty stub packages with no logic to test yet. §9 therefore tests the coordinator dashboard's rendering and empty states only.
- **Environment:** a Supabase project with every migration in `supabase/migrations/` applied and `supabase/seed.sql` run, backend on `http://localhost:8000`, frontend on `http://localhost:5173`. The live project (`vuiryrzzyfecjqftwicj`) has both migrations and the seed applied. The data-layer cases in §6 are automated by `supabase/verification/auth_security_checks.sql` (runs inside a rolled-back transaction and raises on any failure).
- **Seeded accounts** (all share the password `Cs1234`, per `supabase/seed.sql`):

  | Role | Email | Notes |
  |------|-------|-------|
  | Event Organiser | `organiser@connectsphere.dev` | Single role |
  | Event Coordinator | `coordinator@connectsphere.dev` | Dual-role account (double hat): `event_coordinator` (default) + `venue_staff` in `user_roles` |
  | Venue Staff | `venue.staff@connectsphere.dev` | Single role |
  | Technical Support | `tech.support@connectsphere.dev` | Single role |
  | Attendee | `attendee@connectsphere.dev` | Single role |

- **Dashboard route map** (`frontend/src/stores/auth.js::ROLE_DASHBOARD_ROUTES`): `event_organiser → /dashboard/organiser`, `event_coordinator → /dashboard/coordinator`, `venue_staff → /dashboard/venue-staff`, `tech_support → /dashboard/tech-support`, `attendee → /dashboard/attendee`.
- **Priority key:** 🔴 High (blocks core AC) · 🟠 Medium (important edge case) · 🟢 Low (nice-to-have / defensive).

---

## 1. Login — successful cases

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-AUTH-001 | Successful login redirects to the correct role dashboard (Event Coordinator) | Seed data applied; user is logged out; on `/login` | 1. Enter email and password. 2. Click **Sign In**. | `email: coordinator@connectsphere.dev`, `password: Cs1234` | HTTP 200 from `POST /auth/login` with a JSON body containing `access_token`, `refresh_token`, `profile.role = "event_coordinator"`. Browser navigates to `/dashboard/coordinator` and shows "Welcome, Marcus Lim". | 🔴 |
| TC-AUTH-002 | Successful login redirects correctly for every remaining role | Seed data applied; logged out | Repeat TC-AUTH-001's steps once per remaining seeded account | `organiser@connectsphere.dev` / `venue.staff@connectsphere.dev` / `tech.support@connectsphere.dev` / `attendee@connectsphere.dev`, all with `Cs1234` | Each redirects to its own dashboard (`/dashboard/organiser`, `/dashboard/venue-staff`, `/dashboard/tech-support`, `/dashboard/attendee` respectively) and no other. | 🔴 |
| TC-AUTH-003 | Login response includes a profile the frontend can render without a second round trip | Seed data applied; logged out | Log in as the Attendee account and inspect the network response for `POST /auth/login` | `attendee@connectsphere.dev` / `Cs1234` | Response body's `profile` object contains `id`, `email`, `full_name`, `role`, and (nullable) `organisation_name`, `department`, `phone_number` — matching `ProfileResponse` in `backend/app/modules/auth/schemas.py`. | 🟠 |
| TC-AUTH-004 | Session persists across a page reload | Logged in as any seeded account | Reload the browser tab (F5) while on a dashboard | — | User remains authenticated (no redirect to `/login`); the router guard verifies the persisted session once per page load by calling `GET /auth/me` (`fetchProfile()`), renewing it first if the access token has expired (see TC-AUTH-030). | 🟠 |
| TC-AUTH-005 | Redirect target after login honours a `redirect` query param set by the router guard | Logged out; visit `/profile/me` directly first | 1. Navigate to `/profile/me` while logged out (guard redirects to `/login?redirect=/profile/me`). 2. Log in with any seeded account. | any seeded account | After login, browser lands on `/profile/me` (the originally requested page), not the role dashboard. | 🟠 |

## 2. Login — unsuccessful / error cases

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-AUTH-006 | Wrong password is rejected with a clear on-screen error | Seed data applied; logged out | Submit the login form with a valid email and an incorrect password | `email: coordinator@connectsphere.dev`, `password: WrongPassword!1` | `POST /auth/login` returns HTTP 401 with `detail: "Invalid email or password."` (`app/core/exceptions.py::InvalidCredentialsError`). The login page shows a red error banner with that message; user stays on `/login`; no token is stored. | 🔴 |
| TC-AUTH-007 | Unregistered email is rejected the same way as a wrong password (no user enumeration) | Seed data applied; logged out | Submit the login form with an email that was never seeded | `email: nobody@connectsphere.dev`, `password: Cs1234` | HTTP 401, identical `"Invalid email or password."` message — the error text must **not** reveal whether the email exists, per the customer briefing's security NFR. | 🔴 |
| TC-AUTH-008 | Empty email and empty password are caught client-side before any request is sent | Logged out; on `/login` | Click **Sign In** without typing anything | `email: ""`, `password: ""` | Inline validation shows "Email is required." and "Password is required." under the respective fields (`LoginView.vue::validate()`); no network request to `/auth/login` is made. | 🔴 |
| TC-AUTH-009 | Empty password only | Logged out | Enter a valid email, leave password blank, submit | `email: attendee@connectsphere.dev`, `password: ""` | Inline error "Password is required." shown; no request sent. | 🟠 |
| TC-AUTH-010 | Malformed email address is rejected by backend schema validation | Logged out | Bypass the client-side check (e.g. call the API directly, or note this is what the backend would do if the frontend check were absent) and submit a syntactically invalid email | `email: "not-an-email"`, `password: "irrelevant"` | `POST /auth/login` returns HTTP 422 (Pydantic `EmailStr` validation failure on `UserLoginRequest.email`), before any Supabase call is made. | 🟠 |
| TC-AUTH-011 | Email using a reserved/special-use TLD is rejected by the same validation, not treated as a valid but unregistered address | Logged out | Submit a `.test`-domain email | `email: "someone@example.test"`, `password: "Cs1234"` | HTTP 422 — `email-validator` rejects RFC 2606 reserved TLDs (`.test`, `.example`, `.invalid`, `.localhost`) outright. This is why the seed data intentionally uses `@connectsphere.dev`, not `.test` (see `docs/SETUP.md`). | 🟢 |
| TC-AUTH-012 | Email with leading/trailing whitespace | Logged out | Submit an email padded with spaces | `email: "  coordinator@connectsphere.dev  "`, `password: "Cs1234"` | Current behaviour: the raw string is passed to Supabase's `sign_in_with_password` without trimming; login fails as if the email were unregistered (HTTP 401). **Flag as a candidate UX fix** — the frontend/backend should probably trim email input before submission. | 🟢 |
| TC-AUTH-013 | Email is case-sensitivity-tolerant per standard email semantics | Seed data applied; logged out | Submit the coordinator's email in a different case | `email: "COORDINATOR@connectsphere.dev"`, `password: "Cs1234"` | Supabase Auth normalises email case internally; login should still succeed and return the same profile as TC-AUTH-001. If it instead fails, this is a defect to raise with the team (Supabase treats email as case-insensitive for matching but case-preserving for storage). | 🟠 |
| TC-AUTH-014 | SQL-injection–style input in the password field is safely rejected, not executed | Seed data applied; logged out | Submit a classic SQL-injection payload as the password for a valid email | `email: coordinator@connectsphere.dev`, `password: "' OR '1'='1"` | Treated as an ordinary (incorrect) password string — HTTP 401 `"Invalid email or password."` Supabase's GoTrue backend uses parameterised queries, so no injection is possible; this test exists to have documented evidence of that for the security NFR. | 🟠 |
| TC-AUTH-015 | Login attempt for an email that exists in `auth.users` but has no matching `public.profiles` row | A user manually deleted from `public.profiles` while remaining in `auth.users` (simulates trigger failure or manual data corruption) | Log in with that account's correct credentials | valid email/password for the corrupted account | Supabase Auth succeeds (credentials are correct), but the subsequent profile fetch in `auth/service.py::_fetch_profile` finds no row and raises `ProfileNotFoundError` → HTTP 404 `"User profile not found."` Login screen should surface this as a generic error, not a raw 404. | 🟠 |
| TC-AUTH-016 | Login attempt against an unconfirmed email account | An account created via GoTrue signup (not the seed script, which pre-confirms) with `email_confirmed_at` still null | Attempt login with correct credentials | valid email/password for an unconfirmed account | GoTrue rejects with `400 email_not_confirmed`; the backend's `AuthApiError` catch-all currently maps this to the same generic `InvalidCredentialsError` (401 "Invalid email or password."). Documented as current behaviour — consider a more specific message in a later story. | 🟢 |
| TC-AUTH-017 | Login attempt against a banned/disabled account | An account with `banned_until` set in the future (simulating a staff member suspended by an admin) | Attempt login with correct credentials | valid email/password for a banned account | GoTrue rejects with `400 user_banned`; same current fallback to generic 401 as TC-AUTH-016. | 🟢 |
| TC-AUTH-018 | Repeated rapid failed login attempts trigger Supabase's rate limiting | Seed data applied | Submit incorrect credentials for the same account in quick succession (e.g. 10+ times within a minute) | `email: coordinator@connectsphere.dev`, `password: wrong` (repeated) | After Supabase's threshold, GoTrue returns `429 over_request_rate_limit`; verify the backend does not crash (the `AuthApiError` catch is generic) and the frontend shows *some* error rather than hanging silently. | 🟢 |

## 3. Session — `GET /api/v1/auth/me` and `/profile/me`

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-AUTH-019 | Authenticated user can view their own profile | Logged in as any seeded account | Navigate to `/profile/me` | — | Page shows full name, role badge, email, and (if applicable) organisation/department/phone, matching the seeded row exactly. | 🔴 |
| TC-AUTH-020 | `/auth/me` without any Authorization header is rejected | No session | `curl http://localhost:8000/api/v1/auth/me` with no `Authorization` header | — | HTTP 401, `WWW-Authenticate: Bearer` header present (`core/security.py::get_current_user`). | 🔴 |
| TC-AUTH-021 | `/auth/me` with a syntactically invalid bearer token is rejected | No session | `curl -H "Authorization: Bearer not-a-real-token" http://localhost:8000/api/v1/auth/me` | `Authorization: Bearer not-a-real-token` | HTTP 401 `"Invalid or expired authentication token."` (JWT decode failure in `decode_access_token`). | 🔴 |
| TC-AUTH-022 | `/auth/me` with a token signed with the wrong key is rejected | No session | Craft a JWT with `sub`/`aud` claims matching a real user but signed with an arbitrary key, then call `/auth/me` | forged JWT, wrong signature | HTTP 401 — signature verification fails before the payload is ever trusted. Verification is delegated to the Supabase SDK's `get_claims()`, which checks the signature against this project's published JWKS (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`) — it supports both the legacy HS256 shared-secret scheme and this project's current asymmetric ES256 signing keys. This is the core defence against a client fabricating role/identity claims. | 🔴 |
| TC-AUTH-023 | `/auth/me` with an expired token is rejected | No session | Use a token whose `exp` claim is in the past | expired JWT for a real user | HTTP 401 — `get_claims()` validates `exp` explicitly. | 🟠 |
| TC-AUTH-024 | `/auth/me` with a token missing the `aud: "authenticated"` claim is rejected | No session | Craft a validly-signed token with a different or missing `aud` claim | validly-signed JWT with `aud: "something-else"` | HTTP 401 — `get_claims()` itself does **not** check `aud`, so `decode_access_token` in `core/security.py` verifies it explicitly after calling `get_claims()`; omitting this check would let a token issued for a different audience/service be accepted here. | 🟠 |
| TC-AUTH-025 | `/auth/me` with a valid token whose `sub` doesn't match any profile | No session | Craft a valid, correctly-signed token with `sub` set to a random UUID not present in `public.profiles` | valid JWT, unknown `sub` | HTTP 404 `"User profile not found."` (`ProfileNotFoundError`). | 🟠 |

## 4. Logout

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-AUTH-026 | Logout clears the local session and returns to login | Logged in as any seeded account | Click **Logout** in the navbar | — | Local `token`/`refreshToken`/`profile` state and `localStorage` entry are cleared (`stores/auth.js::logout`); browser navigates to `/login`; subsequent visits to any `/dashboard/*` URL redirect back to `/login`. Server-side, the session is revoked: refreshing with the pre-logout refresh token fails (`400 refresh_token_not_found`). | 🔴 |
| TC-AUTH-027 | Logout still clears local state even if the server-side call fails | Logged in; simulate backend being unreachable (stop the backend process) | Click **Logout** | — | Frontend clears local session regardless of the `authApi.logout()` network failure (caught and swallowed in `stores/auth.js::logout`) — user is never stuck unable to log out because of a backend outage. | 🟠 |
| TC-AUTH-028 | `POST /auth/logout` without a token is rejected the same as any other protected endpoint | No session | `curl -X POST http://localhost:8000/api/v1/auth/logout` with no Authorization header | — | HTTP 401 (same as TC-AUTH-020 — `logout` depends on `get_current_user` too). | 🟢 |
| TC-AUTH-029 | Logging out one user does not end another user's session (regression, PROJECT_REVIEW D1) | Two seeded accounts; backend running | 1. Log in as the Organiser, then as the Coordinator (in that order, e.g. two browsers or two `curl` sessions). 2. Log out the **Organiser**. 3. Use the **Coordinator's** refresh token (`POST /auth/refresh`) and the Organiser's old refresh token. | `organiser@connectsphere.dev` / `coordinator@connectsphere.dev`, both `Cs1234` | Coordinator's refresh succeeds (HTTP 200); Organiser's old refresh token fails (HTTP 401). Before the fix, the opposite happened: logout revoked whoever had signed in most recently. | 🔴 |
| TC-AUTH-030 | An expired access token is renewed without re-entering credentials (regression, D4) | Logged in as any seeded account | In DevTools, replace `token` inside the `connectsphere.session` localStorage entry with an invalid value (keep `refreshToken`), then reload a dashboard | invalid access token, valid refresh token | Network shows `GET /auth/me` 401 → `POST /auth/refresh` 200 → `GET /auth/me` 200; user stays on the dashboard; the stored `token` and `refreshToken` are both replaced (Supabase rotates the refresh token). | 🔴 |
| TC-AUTH-031 | A session that cannot be renewed signs the user out with a clear message (D4) | Logged in as any seeded account | Replace both `token` and `refreshToken` in `connectsphere.session` with invalid values, then reload a dashboard | invalid access and refresh tokens | `GET /auth/me` 401 → `POST /auth/refresh` 401; localStorage entry removed; redirected to `/login?redirect=...` showing "Your session has expired. Please sign in again." | 🟠 |
| TC-AUTH-032 | `POST /auth/refresh` input validation | Backend running | `curl -X POST .../api/v1/auth/refresh` with (a) an unknown refresh token, (b) an empty string | (a) `{"refresh_token": "not-a-real-refresh-token"}` (b) `{"refresh_token": ""}` | (a) HTTP 401 `"Invalid or expired authentication token."` (b) HTTP 422 (schema validation, no Supabase call). | 🟠 |
| TC-AUTH-033 | Logout with an expired access token still revokes the server-side session (D4) | Logged in; access token expired but refresh token valid | Click **Logout** | expired access token | `POST /auth/logout` 401 → `POST /auth/refresh` 200 → `POST /auth/logout` 204; the original refresh token no longer works. | 🟢 |
| TC-AUTH-034 | A Supabase outage does not sign the user out | Logged in as any seeded account; then point the backend's `SUPABASE_URL` at a server that answers every request with HTTP 503 and restart it | Reload a dashboard, (a) as is, and (b) after replacing `token` in `connectsphere.session` with an invalid value | (a) stored session (b) invalid access token, stored refresh token | (a) `GET /auth/me` 503; (b) `GET /auth/me` 401 → `POST /auth/refresh` 503. In both, the user stays on the dashboard and the `connectsphere.session` entry is unchanged. A 503 says nothing about the tokens, so only 401/404 end the session. | 🟠 |
| TC-AUTH-035 | Login during a Supabase outage reports the outage, not bad credentials | Backend pointed at a 503 server as in TC-AUTH-034 | Submit the login form with a seeded account | `attendee@connectsphere.dev` / `Cs1234` | `POST /auth/login` returns HTTP 503 with `detail: "The authentication service is temporarily unavailable. Please try again."`, shown in the error banner. Never 401 "Invalid email or password." and never 500. | 🟠 |

## 5. Role-based access control (RBAC) and routing

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-RBAC-001 | Unauthenticated access to a protected route redirects to login with the intended destination preserved | Logged out | Navigate directly to `/dashboard/attendee` | — | Redirected to `/login?redirect=/dashboard/attendee` (router guard `beforeEach`, `to.meta.requiresAuth`). | 🔴 |
| TC-RBAC-002 | Authenticated user cannot access another role's dashboard | Logged in as Attendee | Navigate directly to `/dashboard/venue-staff` | — | Redirected away (back to `/dashboard/attendee`, the user's own `dashboardPath`) — the venue-staff dashboard is never rendered. | 🔴 |
| TC-RBAC-003 | Every role is blocked from every other role's dashboard (full matrix) | One seeded account per role | For each of the 5 roles, attempt to visit each of the other 4 dashboard URLs (20 combinations) | e.g. Coordinator → `/dashboard/organiser`, `/dashboard/venue-staff`, `/dashboard/tech-support`, `/dashboard/attendee` | All 20 cross-role attempts redirect to the visiting user's own dashboard; none render the foreign dashboard's content even momentarily. | 🟠 |
| TC-RBAC-004 | Authenticated user visiting `/login` is bounced to their own dashboard, not shown the form | Logged in as any seeded account | Navigate to `/login` while already authenticated | — | Immediate redirect to the user's `dashboardPath`; the login form is not shown. | 🟠 |
| TC-RBAC-005 | Unknown/undefined route redirects to login | Any session state | Navigate to a nonexistent path, e.g. `/this-page-does-not-exist` | — | Redirected to `/login` (catch-all `path: '/:pathMatch(.*)*'` route). | 🟢 |
| TC-RBAC-006 | Backend role guard blocks a mismatched role even if the frontend guard is bypassed | Logged in as Attendee; obtain their valid access token | Call a hypothetical `require_roles(["venue_staff"])`-protected endpoint directly with the Attendee's token (e.g. via `curl`) | Attendee's bearer token | HTTP 403 with `detail: "This action requires one of the following roles: venue_staff."` (`core/security.py::require_roles` / `InsufficientRoleError`) — proves RBAC is enforced server-side, not just hidden by the UI. | 🔴 |
| TC-RBAC-007 | Backend role guard allows a request when the caller's role is in the allowed list | Logged in as Venue Staff | Call the same hypothetical endpoint with the Venue Staff token | Venue Staff's bearer token | HTTP 200 — request proceeds normally. | 🟠 |
| TC-RBAC-008 | Stale/invalid persisted token is cleared on route-guard hydration, not left in a broken half-logged-in state | `localStorage` manually seeded with a `token` but no matching valid session server-side (e.g. token revoked or malformed) | Reload the app on a protected route | corrupted/invalid persisted token | `fetchProfile()` first tries to renew the session with the stored refresh token; when that also fails, the store clears `token`/`refreshToken`/`profile`, and the guard redirects to `/login?redirect=...` with the session-expired message (TC-AUTH-031). | 🟠 |
| TC-RBAC-009 | A stored session whose role has no dashboard shows the login page instead of looping | Backend stopped (so the stored profile can't be re-verified); `localStorage` seeded with `connectsphere.session` whose `profile.role` is missing or not one of the five roles | Navigate to (a) `/login` and (b) `/dashboard/attendee` | `{"token": "x", "refreshToken": "y", "profile": {"id": "u1", "role": "platform_admin"}}` | Both end on the **Sign In** form with "Your account can't be opened in this app. Please contact support."; the `connectsphere.session` entry is removed; the console shows no `[Vue Router warn]` infinite-redirection warning. | 🟢 |

## 5a. Role dropdown and active-role switching (SCRUM-74/75/78)

Environment as in §0, plus the `20260917000000_role_switching.sql` migration and the `venue_staff` grant on `coordinator@connectsphere.dev` in `supabase/seed.sql` (the seeded account that holds two roles).

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-ROLE-001 | The nav shows no role dropdown for a single-role account | Logged in as `attendee@connectsphere.dev` (one role) | Look at the nav sidebar | — | No "Acting as" dropdown is rendered anywhere in the nav. | 🔴 |
| TC-ROLE-002 | The nav shows a role dropdown listing exactly the held roles, with human-readable labels | Logged in as `coordinator@connectsphere.dev` (`event_coordinator` + `venue_staff`) | Look at the nav sidebar | — | An "Acting as" dropdown is present, its options are exactly "Event Coordinator" and "Venue Staff" (no other role, no raw enum value like `venue_staff` shown as text), and the currently active role is selected. | 🔴 |
| TC-ROLE-003 | Selecting a held role switches the active role and redirects to that role's dashboard | Logged in as `coordinator@connectsphere.dev`, currently acting as Event Coordinator | Select "Venue Staff" from the dropdown | — | Browser navigates to `/dashboard/venue-staff` and renders the Venue Staff dashboard; the dropdown now shows "Venue Staff" selected. | 🔴 |
| TC-ROLE-004 | The switched role persists across a page reload | Continuing from TC-ROLE-003 (acting as Venue Staff) | Reload the page | — | Still on `/dashboard/venue-staff` with "Venue Staff" selected in the dropdown — the active role is read back from the server (`session_active_roles`), not just cached client state. | 🔴 |
| TC-ROLE-005 | Switching roles in one session does not affect another concurrent session for the same account | Log in as `coordinator@connectsphere.dev` in two separate browsers (or one normal + one private window) | In session A, switch to Venue Staff. In session B, reload and check the active role. | — | Session B still shows/acts as Event Coordinator (the account's default); session A stays on Venue Staff. Proves the switch is scoped to the session (`session_id`), not the account. | 🟠 |
| TC-ROLE-006 | The backend rejects switching to a role the account does not hold | Logged in as `coordinator@connectsphere.dev`, valid access token | `curl -X POST http://localhost:8000/api/v1/auth/active-role -H "Authorization: Bearer <token>" -d '{"role":"attendee"}'` | `{"role": "attendee"}` | HTTP 403, `detail: "You do not hold the 'attendee' role."` (`RoleNotAssignedError`); the account's active role is unchanged. | 🔴 |
| TC-ROLE-007 | `POST /auth/active-role` without a token is rejected | No session | `curl -X POST http://localhost:8000/api/v1/auth/active-role -d '{"role":"venue_staff"}'` with no Authorization header | — | HTTP 401 (same guard as every other authenticated endpoint). | 🟢 |
| TC-ROLE-008 | `GET /auth/me` and `POST /auth/login` both report every role the account holds | Logged in as `coordinator@connectsphere.dev` | `GET /auth/me` and, separately, `POST /auth/login` | — | Both responses include `"roles": ["event_coordinator", "venue_staff"]`, sourced from `user_roles`, not hardcoded. | 🟠 |
| TC-ROLE-009 | The backend role guard (`require_roles`) checks the session's active role, not the account's default | Logged in as `coordinator@connectsphere.dev`, switched to Venue Staff (TC-ROLE-003) | Call a `venue_staff`-only endpoint (e.g. `GET /venues`) with the same token | — | HTTP 200 — the endpoint treats this session as Venue Staff, even though the account's default role is Event Coordinator. | 🟠 |
| TC-ROLE-010 | Selecting the dropdown's empty placeholder option is a no-op, not a crash (code review follow-up) | Logged in as `coordinator@connectsphere.dev` | Select the dropdown's top ("Select a role") option | — | No `POST /auth/active-role` call is made, no console error, and the dropdown still shows the actual active role. | 🟠 |
| TC-ROLE-011 | Revoking a role via direct SQL invalidates any session currently acting as it (code review follow-up) | An account holding 2 roles, with a session currently switched to the second role | As a system admin, `delete from user_roles where profile_id = ... and role = '<second role>'` | — | The session's `session_active_roles` row is cascaded away (composite FK); the next `GET /auth/me`/guarded request for that session falls back to the account's default role. | 🟠 |
| TC-ROLE-012 | Revoking an account's *default* role in a single statement is rejected, not silently left active (2nd code review round) | An account whose `profiles.role` equals a role it holds in `user_roles` | As a system admin, `delete from user_roles where profile_id = ... and role = <profiles.role>` as a single autocommitted statement | — | HTTP/SQL error `23503 foreign key violation`; the row is not deleted, and `profiles.role` still resolves for every session that never switched. | 🔴 |
| TC-ROLE-013 | The correct two-step admin workflow for revoking a default role still succeeds (2nd code review round) | Same as TC-ROLE-012 | In one transaction: `update profiles set role = '<another held role>' where id = ...;` then `delete from user_roles where profile_id = ... and role = '<old default>';` then `commit;` | — | Both statements succeed; `profiles.role` is now the other held role, and the old role no longer appears in `user_roles` for that account. | 🟠 |
| TC-ROLE-014 | A successful role switch updates the dropdown in place, without a visible revert-then-jump (2nd code review round) | Logged in as `coordinator@connectsphere.dev` | Select "Venue Staff" from the dropdown and watch it, rather than just checking the end state | — | The dropdown shows "Venue Staff" once, directly — it does not briefly flash back to "Event Coordinator" first. | 🟢 |
| TC-ROLE-015 | The profile page shows an "All Roles" section listing every held role, only for a multi-role account (SCRUM-78) | Logged in as `coordinator@connectsphere.dev` (`event_coordinator` + `venue_staff`) | Navigate to `/profile/me` | — | An "All Roles" section is present, listing exactly "Event Coordinator" and "Venue Staff" (same source/labels as the nav dropdown); the existing role badge still shows only the session's active role. | 🟠 |
| TC-ROLE-016 | The profile page shows no "All Roles" section for a single-role account (SCRUM-78) | Logged in as `attendee@connectsphere.dev` (one role) | Navigate to `/profile/me` | — | No "All Roles" section is rendered; the profile page is otherwise unchanged. | 🟠 |

## 6. Data integrity and Row Level Security (Supabase)

These require direct database access (e.g. the Supabase SQL editor or MCP `execute_sql`, testing as different authenticated roles inside a rolled-back transaction: `set_config('request.jwt.claims', ...)` + `set local role authenticated`) rather than the application UI, and validate the customer briefing's **security** and **reliability/consistency** NFRs at the data layer, independent of the API. `supabase/verification/auth_security_checks.sql` automates TC-DATA-001–005, 007, 008, 010–012.

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-DATA-001 | A user can select their own profile row under RLS, without error | Querying as the Attendee (`authenticated` role, Attendee's JWT claims) | `select * from public.profiles;` | Attendee's own `auth.uid()` | Exactly one row returned — their own — and no error. (Before migration `20260913120749`, every such query failed with `42P17 infinite recursion detected in policy`, PROJECT_REVIEW D3.) | 🔴 |
| TC-DATA-002 | An external-role user (Organiser/Attendee) cannot select another user's profile | Querying as the Attendee | `select * from public.profiles where id = '<coordinator's uuid>';` | Coordinator's `id` | Zero rows returned (policy `profiles_select_own_or_internal_staff` matches only `id = auth.uid()` for non-staff roles). | 🔴 |
| TC-DATA-003 | An internal-staff user can select any profile | Querying as the Event Coordinator | `select * from public.profiles;` | — | Every profile row returned — the same policy grants staff roles (`event_coordinator`, `venue_staff`, `tech_support`) read access to every profile, via the `private.current_user_role()` helper. | 🟠 |
| TC-DATA-004 | A user can update their own non-role profile fields | Signed in as the Attendee | `update public.profiles set phone_number = '+65 9111 1111' where id = auth.uid();` | new phone number | Update succeeds; `updated_at` is bumped automatically by the `profiles_set_updated_at` trigger. | 🟠 |
| TC-DATA-005 | A user cannot change their own role | Signed in as the Attendee | `update public.profiles set role = 'event_coordinator' where id = auth.uid();` | `role = 'event_coordinator'` | Statement fails with the `prevent_self_role_change` trigger's raised exception ("Users may not change their own role."). Confirms privilege escalation isn't possible via self-service profile edits. | 🔴 |
| TC-DATA-006 | Deleting an `auth.users` row cascades to delete the matching `public.profiles` row | Service-role/admin access | Delete a test user from `auth.users` (e.g. via the Admin API), then query `public.profiles` for that id | test user's `id` | Zero rows in `public.profiles` for that id — enforced by `references auth.users(id) on delete cascade`. | 🟢 |
| TC-DATA-007 | Creating a new `auth.users` row automatically creates a matching profile with metadata mapped correctly | Service-role/admin access | Create a user via the Admin API with `user_metadata = {"full_name": "Test Organiser", "role": "event_organiser", "organisation_name": "Acme"}`, then query `public.profiles` | metadata as above | A new `profiles` row exists with `full_name = 'Test Organiser'`, `role = 'event_organiser'`, `organisation_name = 'Acme'` (`handle_new_user()` trigger). | 🟠 |
| TC-DATA-008 | Creating a new `auth.users` row with no `role` in metadata defaults to `attendee` | Service-role/admin access | Create a user with metadata omitting `role`, then query `public.profiles` | metadata without `role` | New profile row has `role = 'attendee'` (the trigger's fallback). | 🟢 |
| TC-DATA-010 | Sign-up metadata cannot grant an internal staff role (regression, PROJECT_REVIEW D2) | Service-role/admin access (the Admin API runs the same trigger as public sign-up) | Create users whose metadata requests `event_coordinator`, `venue_staff`, and `tech_support` | `user_metadata.role` = each staff role | Each profile is created with `role = 'attendee'`. Only `event_organiser` and `attendee` are accepted from sign-up (QA-3, QA-4); staff roles are set only by seed/migration. Delete the test users afterwards. | 🔴 |
| TC-DATA-011 | Anonymous callers cannot read profiles | Querying as `anon` (no JWT claims) | `select count(*) from public.profiles;` | — | `0` — policies are scoped to `authenticated`. | 🟠 |
| TC-DATA-012 | Trigger and RLS helper functions are not callable as RPCs | Service-role/admin access | `select has_function_privilege('anon', 'public.handle_new_user()', 'execute'), has_function_privilege('authenticated', 'public.handle_new_user()', 'execute');` and `get_advisors` (security) | — | Both `false`; the security advisor reports no `function_search_path_mutable` or `*_security_definer_function_executable` findings. `private.current_user_role()` lives in a schema the Data API does not expose. | 🟢 |
| TC-DATA-009 | `profiles.email` uniqueness is enforced | Service-role/admin access | Attempt to insert a second profile row reusing an existing email (bypassing the trigger, direct insert) | duplicate `email` | Insert fails on the `unique` constraint on `profiles.email`. | 🟢 |

## 8. Venue catalogue, search and availability (SCRUM-39)

Environment as in §0 plus the SCRUM-39 migration and the venue rows from `supabase/seed.sql` (8 venues, 3 blocks, 3 bookings around **10 Oct 2026**). All times are Singapore time. The §8.3 data cases are automated by `supabase/verification/venue_schema_checks.sql`.

### 8.1 Search and filter (`/venues`, signed in as the Event Coordinator unless stated)

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-VENUE-001 | Empty search lists the whole active catalogue | Logged in as Coordinator | 1. Open `/dashboard/coordinator`. 2. Click **Search venues**. | — | `/venues` loads and immediately shows "7 matching venues" (every seeded venue except the inactive Old Lecture Theatre), each card badged **Availability not checked** with the note "Add a date and time to check availability". A **Show 1 excluded** button is present. | 🔴 |
| TC-VENUE-002 | Acceptance search returns only venues that fit and are free (§6.10 AC 1) | On `/venues` | Fill date/time, attendance, tick Projector; click **Search venues** | date `2026-10-10`, `14:00`–`17:00`, attendance `150`, facilities `Projector` | "2 matching venues": **Auditorium A** and **Grand Ballroom**, both badged **Available**. Network: `GET /api/v1/venues?starts_at=2026-10-10T14:00:00%2B08:00&ends_at=…&min_capacity=150&facilities=projector&include_excluded=true` → 200. | 🔴 |
| TC-VENUE-003 | Back-to-back booking does not exclude a venue (§6.10 AC 2, §6.14 zero turnaround) | TC-VENUE-002 result | Inspect the Auditorium A card; open its detail page | — | Auditorium A is **Available** for 14:00–17:00 although it has an approved booking 11:00–14:00 on the same day; the detail page lists that booking under "Upcoming unavailability". | 🔴 |
| TC-VENUE-004 | Excluded venues are revealed with reasons (§6.10 AC 3) | TC-VENUE-002 result | Click **Show 6 excluded** | — | An "Excluded venues" section appears with: Boardroom Orchid ("Capacity 16 is below the required 150", "Missing facilities: projector"); Heritage Hall (**Unavailable**, "Blocked: renovation 1 Oct 00:00 – 15 Oct 00:00"); Innovation Lab ("Capacity 80 …"); Old Lecture Theatre ("Venue is inactive"); Rooftop Terrace (capacity + projector); Seminar Room 1 (**Unavailable**, "Held by another event 10 Oct 13:00–16:00"). Clicking **Hide 6 excluded** collapses the section without a new request. | 🔴 |
| TC-VENUE-005 | A block ending at the search start does not exclude; one overlapping by a minute does (CAL-R2) | On `/venues` | (a) Search `2026-10-10` `12:00`–`15:00`, location `Marina`. (b) Search `11:59`–`13:00`, same location. | as stated | (a) Grand Ballroom is **Available** (its maintenance block is 08:00–12:00). (b) Grand Ballroom is excluded, **Unavailable**, "Blocked: maintenance 10 Oct 08:00–12:00". | 🔴 |
| TC-VENUE-006 | Per-layout capacity is used when a layout is chosen (§6.11 capacity rule) | On `/venues` | Search attendance `100`, layout `Banquet`, show excluded | — | Rooftop Terrace is excluded with "Banquet capacity 80 is below the required 100" (venue capacity 120 is not used). Grand Ballroom (banquet 300) and Heritage Hall (banquet 100, boundary: equal passes) match on capacity. | 🟠 |
| TC-VENUE-007 | Layout and accessibility filters are strict | On `/venues` | Search layout `U-shape`, accessibility `Hearing loop`, show excluded | — | No venue matches ("No venue meets every requirement…"). Excluded reasons include "U shape layout is not supported" / "Missing accessibility features: hearing loop" as applicable. | 🟠 |
| TC-VENUE-008 | Incomplete or inverted period is refused client-side | On `/venues` | (a) Enter date and start time only; submit. (b) Enter `17:00`–`14:00`; submit. | as stated | (a) "Enter the end time." under End time; no request sent. (b) "End time must be after start time."; no request sent. | 🟠 |
| TC-VENUE-009 | Detail page shows full venue information and upcoming unavailability | On `/venues` | Click **Seminar Room 1** | — | `/venues/b0000000-0000-4000-8000-000000000003` shows location, capacity 60, hours 08:00–22:00, layouts (Classroom · 40 pax, U-shape · 24 pax, Boardroom · 20 pax, Theatre), facilities, accessibility, and a **Tentative hold** entry for 10 Oct 2026, 13:00–16:00. **← Back to venue search** returns to the previous results without re-searching. | 🟠 |
| TC-VENUE-010 | Venue staff can search; organisers, attendees and tech support cannot | Logged in as each role | Visit `/venues` directly | — | Venue Staff: page renders (button also on their dashboard). Organiser / Attendee / Tech Support: router redirects to their own dashboard; `curl` with their token → `403 This action requires one of the following roles: event_coordinator, venue_staff.` | 🔴 |
| TC-VENUE-011 | Unknown or malformed venue id | Coordinator token | `GET /api/v1/venues/b0000000-0000-4000-8000-0000000000ff` and `GET /api/v1/venues/not-a-uuid` | — | 404 `Venue not found.` and 422 respectively. `/venues/not-a-uuid` in the browser shows the error banner. | 🟢 |
| TC-VENUE-012 | API outage keeps previous results on screen | Results shown; stop the backend | Click **Search venues** again | — | Red banner with the error message; the previous result cards remain; the session is not ended. | 🟢 |

### 8.2 API contract (`curl` with a coordinator token)

| ID | Title | Request | Expected Result | Priority |
|----|-------|---------|------------------|----------|
| TC-VENUE-020 | Period must be a timezone-aware pair with end after start | `?starts_at=2026-10-10T14:00:00%2B08:00` alone; `?starts_at=…17:00…&ends_at=…14:00…`; `?starts_at=2026-10-10T14:00:00&ends_at=2026-10-10T17:00:00` (no offset) | 422 each, with `detail[0].msg` naming the rule. | 🟠 |
| TC-VENUE-021 | Unknown enum values are refused | `?facilities=jacuzzi`, `?layout=cinema`, `?min_capacity=0` | 422 each. | 🟢 |
| TC-VENUE-022 | Response shape | any 200 search | `criteria` echoes the applied filters; `results[]` each have `venue{…}`, `availability ∈ {available, unavailable, not_checked}`, `excluded`, `reasons[{code, message}]`; `included_count`, `excluded_count`. Without `include_excluded=true` only non-excluded venues are in `results` but `excluded_count` still counts them. | 🟠 |

### 8.3 Data integrity (automated by `supabase/verification/venue_schema_checks.sql`)

| ID | Title | Test Steps | Expected Result | Priority |
|----|-------|------------|------------------|----------|
| TC-VENUE-030 | Overlapping occupying bookings are impossible (DB-1, QA-6, QA-10, QA-113) | Insert `held` 09:00–12:00 and `approved` 12:00–15:00 for one venue, then `held` 11:59–13:00 | First two succeed (back-to-back), third fails with `exclusion_violation`. | 🔴 |
| TC-VENUE-031 | Non-occupying statuses do not block (§6.14) | Insert a `rejected` booking overlapping an `approved` one | Succeeds. | 🟠 |
| TC-VENUE-032 | One occupying booking per event (BR-R1) | Insert a second `held` booking for an event that already has one | Fails with `unique_violation`. | 🔴 |
| TC-VENUE-033 | Blocks may overlap bookings (CAL-R1) | Insert a block over an approved booking | Succeeds (resolution is manual). | 🟠 |
| TC-VENUE-034 | Periods are bounded and half-open | Insert a block with `'[]'` bounds | Fails with `check_violation`. | 🟢 |
| TC-VENUE-035 | RLS: staff read, external roles see nothing, nobody writes directly | As the seeded coordinator: select venues/bookings, insert a block. As the organiser: select venues. | Coordinator reads rows; insert fails with `insufficient_privilege`; organiser sees 0 rows. | 🔴 |

## 7. Traceability matrix

| SCRUM-48 acceptance criterion / NFR | Covered by |
|---|---|
| "Given a registered user exists with a valid username and password... they are successfully authenticated and redirected to their home dashboard" | TC-AUTH-001, TC-AUTH-002, TC-AUTH-003 |
| "...able to see the profile for me" | TC-AUTH-003, TC-AUTH-019 |
| "Given a user is on the login screen... enters an invalid username or incorrect password... sees a clear error message and are denied entry" | TC-AUTH-006, TC-AUTH-007, TC-AUTH-008, TC-AUTH-009 |
| Role-specific dashboard (interpretation, see `docs/SCENARIO.md` §4.1) | TC-AUTH-001, TC-AUTH-002, TC-RBAC-001–TC-RBAC-009 |
| Customer briefing — Security NFR ("access should depend on the user's role") | TC-RBAC-002, TC-RBAC-003, TC-RBAC-006, TC-RBAC-007, TC-DATA-001–TC-DATA-005 |
| Customer briefing — Reliability & consistency NFR | TC-DATA-005, TC-DATA-006, TC-DATA-007, TC-AUTH-029 |
| Customer briefing — Auditability NFR (partial — `created_at`/`updated_at` only; no full audit log yet) | TC-DATA-004 |
| Session usability (a signed-in user is not silently logged out after the access token expires) | TC-AUTH-030, TC-AUTH-031, TC-AUTH-032, TC-AUTH-033 |
| Customer briefing — Reliability NFR (an upstream outage is reported as such and does not end sessions) | TC-AUTH-034, TC-AUTH-035 |
| Accounts: only Organisers and Attendees self-register; staff are system defaults (QA-3, QA-4) | TC-DATA-010, TC-DATA-012 |
| Defect regressions (docs/PROJECT_REVIEW.md) | D1: TC-AUTH-029 · D2: TC-DATA-010 · D3: TC-DATA-001–003, TC-DATA-011 · D4: TC-AUTH-030–033 · D6: TC-DATA-012 |

| SCRUM-74/75 acceptance criterion (ACC-R4) | Covered by |
|---|---|
| "Dropdown appears only if the user has 2 or more assigned roles, single-role users see no dropdown" | TC-ROLE-001, TC-ROLE-002 |
| "Dropdown lists exactly the roles assigned to that user (from user_roles), nothing else" | TC-ROLE-002, TC-ROLE-008 |
| "Dropdown shows a human-readable label for each role" | TC-ROLE-002 |
| "Selecting a role updates my active role for this session... which validates I actually hold that role" | TC-ROLE-003, TC-ROLE-006, TC-ROLE-009 |
| "After selecting, I am taken to that role's dashboard/homepage" | TC-ROLE-003 |
| "My active role persists across page reloads within the session, until I log out or select a different role" | TC-ROLE-004, TC-ROLE-005 |
| "Attempting to set an active role I do not hold is rejected" | TC-ROLE-006 |

| SCRUM-78 acceptance criterion | Covered by |
|---|---|
| "Profile page shows an 'All Roles' section only when the account holds 2 or more roles; single-role users see no such section" | TC-ROLE-015, TC-ROLE-016 |
| "The section lists exactly the roles assigned to that user (from user_roles), each with a human-readable label — same source and labelling as the nav dropdown" | TC-ROLE-015 |
| "The existing role badge continues to show the session's currently active role, unchanged" | TC-ROLE-015 |

| SCRUM-39 acceptance criterion / rule | Covered by |
|---|---|
| "Venues with matching criterias are returned" | TC-VENUE-001, TC-VENUE-002, TC-VENUE-022 |
| "Shows venue availability and information about the venue" | TC-VENUE-001, TC-VENUE-003, TC-VENUE-009 |
| "Allows filtering by date, time, required attendance, room layout, accessibility, and required facilities" | TC-VENUE-002, TC-VENUE-006, TC-VENUE-007, TC-VENUE-008, TC-VENUE-020, TC-VENUE-021 |
| "Excludes venues that are marked as unavailable due to maintenance, renovation, or safety restrictions" (any block, CAL-R3) | TC-VENUE-004, TC-VENUE-005, TC-VENUE-035 |
| "Automatically incorporates setup, reset, and turnaround buffers" — **withdrawn (QA-28)**: back-to-back is allowed | TC-VENUE-003, TC-VENUE-005, TC-VENUE-030 |
| VS-R1 (active, no hard failure, no hold/booking/block overlap) | TC-VENUE-002, TC-VENUE-004 |
| DB-1 / BR-R1 / CAL-R1 | TC-VENUE-030–034 |
| Access matrix §2 (coordinators read/search, venue staff manage, others none) | TC-VENUE-010, TC-VENUE-035 |

Cases with no seeded-data shortcut (forged/expired/wrong-audience JWTs, rate limiting, unconfirmed/banned accounts) require a small script/`curl` command or direct Supabase SQL access. The automated `pytest` suite (`backend/tests/test_auth.py`) covers the equivalents of TC-AUTH-001, TC-AUTH-006, TC-AUTH-020, TC-AUTH-021, TC-AUTH-025, TC-AUTH-026 (server-side revoke), TC-AUTH-028, TC-AUTH-029 (fresh auth client per sign-in), TC-AUTH-030–032, the backend half of TC-AUTH-034 and TC-AUTH-035 (503 on outage), and TC-RBAC-006. The Vitest suite (`frontend/src/**/__tests__/`) covers the frontend half of TC-AUTH-031 and TC-AUTH-034 (which errors end a session) and TC-RBAC-009. The §6 data-layer cases are automated by `supabase/verification/auth_security_checks.sql`. For SCRUM-74/75, `backend/tests/test_auth.py` covers the backend equivalents of TC-ROLE-002 (`roles` on the profile), TC-ROLE-003/006/009 (`POST /auth/active-role` success/reject, session-scoped `require_roles`), and TC-ROLE-007; the Vitest specs `stores/__tests__/auth.spec.js` and `components/common/__tests__/Nav.spec.js` cover the frontend equivalents of TC-ROLE-001–003 and TC-ROLE-010. TC-ROLE-004, TC-ROLE-005, and TC-ROLE-008's login/`/auth/me` parity were verified manually against the real Supabase project and a real browser (`docs/SCENARIO.md` §4.6) rather than by an automated test, since they depend on genuine cross-request/cross-session persistence that a mocked Supabase client can't demonstrate. For SCRUM-78, `views/__tests__/ProfileView.spec.js` covers the frontend equivalents of TC-ROLE-015 and TC-ROLE-016. For SCRUM-39, `backend/tests/test_venue_search.py` and `test_venues_api.py` cover TC-VENUE-002–007 (rules), TC-VENUE-010–011, TC-VENUE-020–022; the Vitest specs `stores/__tests__/venues.spec.js` and `views/__tests__/venueSearch.spec.js` cover TC-VENUE-004 (toggle), TC-VENUE-008, TC-VENUE-009 (rendering), TC-VENUE-012; `supabase/verification/venue_schema_checks.sql` automates TC-VENUE-030–035.

---

## 9. Event Coordinator dashboard (SCRUM-72)

**Preconditions for every case:** logged in as `coordinator@connectsphere.dev` / `Cs1234`, on `/dashboard/coordinator`.

**A note on how these are run.** The events module does not exist, so `GET /api/v1/events/dashboard/coordinator` returns `404` against a real backend. TC-DASH-001–005 exercise that real state directly. TC-DASH-006–012 need event data, so they are run by **stubbing the endpoint response** at the network layer (Playwright `page.route`, or DevTools' local-overrides / a request-interception extension). Once the events module ships, re-run 006–012 against real seeded data and delete this note.

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-DASH-001 | Dashboard loads with honest empty states when the events module is absent | Backend running; no events tables | Open `/dashboard/coordinator` and wait for the network to settle | — | `GET /events/dashboard/coordinator` returns 404. The page shows "AWAITING DATA — the events module has not been built yet…", all counters read `0`, and each widget's empty state explains it will populate once the module ships. No error banner. | 🔴 |
| TC-DASH-002 | No fabricated metrics are displayed (regression, PROJECT_REVIEW D8) | As TC-DASH-001 | Read every number on the page | — | No counter shows a non-zero value. The strings "Requests Awaiting Review", "Venues to Coordinate" and "Events in Progress" do **not** appear — they were the hardcoded placeholders removed by this story. | 🔴 |
| TC-DASH-003 | Counts are withheld until the first load settles | Throttle the network (DevTools → Slow 3G) before loading | Open `/dashboard/coordinator` and watch the counters while the request is in flight | — | While loading, the three category counters and the four status counters show "—", not `0`, and empty states read "Checking for updates…". They switch to real figures only once the request settles. A `0` must never be shown before the answer is known. | 🟠 |
| TC-DASH-004 | A server failure is surfaced, not silently rendered as an empty dashboard | Point the backend at a stub that answers 503, or stop the backend | Reload `/dashboard/coordinator` | — | A red error banner shows the failure message. The dashboard does **not** claim the coordinator has nothing to do. (Contrast with TC-DASH-001: only a 404 is treated as "not built yet".) | 🔴 |
| TC-DASH-005 | The dashboard is usable on a phone-width viewport (NFR-U1) | As TC-DASH-001 | Set the viewport to 390 × 844 | — | Category cards stack to one column, status cards stack to one column, no horizontal scrolling, all text legible. | 🟠 |
| TC-DASH-006 | AC1 — the action list is ordered by what each item blocks | Stubbed payload containing one item of each kind: `awaiting_review`, `arrangement_issue`, `resubmitted`, `cancellation_request` | Read the numbered action list top to bottom | four action items, mixed order in the payload | Order is: arrangement issue → cancellation requested → amended and resubmitted → awaiting first review (REQUIREMENTS §6.21.1). Each row shows its kind badge, the event date in Asia/Singapore, and the organiser's name. | 🔴 |
| TC-DASH-007 | AC1 — the three named categories are counted separately | Stubbed payload with 2 immediate-action items, 1 `awaiting_review`, 1 `resubmitted` | Read the three counter cards | as above | "Immediate action" = 2, "Awaiting approval" = 1, "Clarification responses" = 1. | 🔴 |
| TC-DASH-008 | AC1 — ties are broken by the soonest event date | Stubbed payload with two `awaiting_review` items, differing only in `starts_at` | Read their relative order | two items, same kind | The event starting sooner appears first. | 🟠 |
| TC-DASH-009 | AC1 — an unrecognised action kind is still shown, ranked last | Stubbed payload containing `"kind": "something_new"` alongside a known kind | Read the list | unknown kind | The unknown item appears, last, with the generic "Needs attention" badge. It is never dropped. | 🟠 |
| TC-DASH-010 | AC2 — every active status is shown with its count and events | Stubbed payload with events in `under_review` (×2), `returned`, `planning`, `confirmed` | Read the "Active events by status" section | five events | Four cards appear — Under review (2), Returned for amendment (1), Approved – planning (1), Confirmed (1) — each listing its events with dates. Statuses with no events still appear, showing `0` and "None." | 🔴 |
| TC-DASH-011 | AC2 — drafts never appear in a coordinator's view (DR-R2) | Stubbed payload including an event with `"status": "draft"` and a terminal-status event | Read the whole page | draft + cancelled event | Neither appears in any card, and neither is counted anywhere. | 🔴 |
| TC-DASH-012 | Urgent alerts and the schedule overview render | Stubbed payload with `unassigned_count: 3`, one event flagged `venue_blocked`, and one `planning` event starting in 8 days with `readiness.venue = "pending"` | Read the alert banner, the status cards, and the readiness section | as above | A red "Urgent — awaiting assignment" card shows `3` (AS-R5). The flagged event shows a "VENUE BLOCKED" badge (§7 NFR-R1). "Readiness gaps — next 14 days" lists the event with "Outstanding: Venue". | 🟠 |

### 9.1 Traceability — SCRUM-72

| Acceptance criterion / rule | Covered by |
|---|---|
| AC1 "prioritized list of incoming event requests requiring immediate action" | TC-DASH-006, TC-DASH-007, TC-DASH-008 |
| AC1 "requests awaiting initial approval/rejection" | TC-DASH-007, TC-DASH-010 |
| AC1 "items with newly received client clarification responses" (QA-22, QA-77 return/resubmit) | TC-DASH-007 |
| AC2 "Displays status for each active event" | TC-DASH-010, TC-DASH-011 |
| REQUIREMENTS §6.21 "build a widget only when its data exists; until then, show an empty state" | TC-DASH-001, TC-DASH-003 |
| REQUIREMENTS §6.21.1 prioritisation [Team decision] | TC-DASH-006, TC-DASH-008, TC-DASH-009 |
| DR-R2 (drafts invisible to staff) | TC-DASH-011 |
| AS-R5 (awaiting-assignment alert) | TC-DASH-012 |
| §7 NFR-R1 (flags stay visible until resolved) | TC-DASH-012 |
| NFR-U1 (desktop and mobile friendly) | TC-DASH-005 |
| PROJECT_REVIEW D8 (fabricated metrics) | TC-DASH-002 |
| Reliability (an outage is not rendered as "nothing to do") | TC-DASH-004 |

Automated equivalents live in `frontend/src/features/events/__tests__/` (Vitest): `dashboard.spec.js` covers TC-DASH-006, 008, 009, 010, 011 and 012's readiness logic as pure unit tests; `store.spec.js` covers TC-DASH-001, 003 and 004. TC-DASH-002 and TC-DASH-005 are visual and remain manual.

## 10. Venue Staff dashboard (SCRUM-70)

**Preconditions for every case:** logged in as `venue.staff@connectsphere.dev` / `Cs1234`, on `/dashboard/venue-staff`, with every migration and `supabase/seed.sql` applied.

**Read this before running any of these.** `coordinator@connectsphere.dev` also holds `venue_staff`, but `require_roles` checks the **session's active role**, not the roles the account holds. That account signs in as `event_coordinator`, so the endpoint answers **403** until the role is switched in the nav dropdown. This is correct behaviour and TC-VSD-005 pins it — do not file it as a bug.

Unlike §9, no stubbing is needed: `venues`, `venue_blocks` and `venue_bookings` all exist and are seeded, so every case below runs against real data.

**Expected seeded figures:** 1 pending hold · 1 in re-review · 3 blocks · 8 venues (7 active, 1 inactive). If the re-review tile reads `0`, the live database predates the seed row added by this story — re-run the seed.

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-VSD-001 | The four tiles show real figures from the endpoint | Seed applied | Open `/dashboard/venue-staff` and read the four tiles | — | Pending requests `1`, In re-review `1`, Active & upcoming blocks `3`, Venues `8` with the sub-line "7 active · 1 inactive". Every figure matches `GET /api/v1/venues/dashboard/venue-staff`. | 🔴 |
| TC-VSD-002 | No fabricated metrics remain (regression, PROJECT_REVIEW D8) | As above | Read every label and number on the page | — | The strings "Venues Managed", "Booking Requests" and "Availability Updates Due" do **not** appear, and no tile reads `12`, `6` or `2` unless that is the true count. Those were the hardcoded placeholders this story removed. | 🔴 |
| TC-VSD-003 | Counts are withheld until the first load settles | Throttle the network (DevTools → Slow 3G) | Reload and watch the tiles while the request is in flight | — | All four tiles show "—", not `0`, and the lists read "Checking for updates…". A `0` must never appear before the answer is known. | 🟠 |
| TC-VSD-004 | A server failure is surfaced, not rendered as an empty queue | Stop the backend, or point it at a stub answering 503 | Reload the dashboard | — | A red error banner shows the failure. The page does **not** say "Nothing is waiting on your decision". | 🔴 |
| TC-VSD-005 | The endpoint is gated on the session's active role, not roles held | Signed in as `coordinator@connectsphere.dev` | `curl` the endpoint with the coordinator's token; then switch the nav dropdown to Venue Staff and retry | coordinator token | First call **403**. After the switch, **200** and the dashboard renders. Confirms the guard reads the active role (SCRUM-74/75). | 🔴 |
| TC-VSD-006 | A coordinator cannot reach the page by URL | Signed in as `coordinator@connectsphere.dev`, active role Event Coordinator | Navigate to `/dashboard/venue-staff` | — | Redirected to `/dashboard/coordinator`. Same for `/bookings/<any-id>`. | 🔴 |
| TC-VSD-007 | The calendar opens on the month that has something in it | Seed applied; system date before October 2026 | Read the calendar header, then press **Today** | — | The header reads **October 2026**, and **Today** is enabled. Pressing it returns to September 2026, after which **Today** is disabled. The header always names the month on screen. | 🟠 |
| TC-VSD-008 | A block's end is exclusive (§6.14, CAL-R2) | Seed applied | In October 2026, inspect the cells for 20, 21 and 22 Oct; then 14 and 15 Oct | — | 20 and 21 Oct are marked (Rooftop Terrace, safety); **22 Oct is not**. 14 Oct is marked (Heritage Hall, renovation); **15 Oct is not**. The seeded blocks run 20–22 and 1–15 Oct. | 🔴 |
| TC-VSD-009 | Selecting a day lists what is on it | Seed applied | Click 10 Oct 2026 | — | Below the grid: "Saturday, 10 October 2026", then the day's items, each with a colour-coded badge, its venue name and its Singapore-time span. Clicking again deselects. | 🟠 |
| TC-VSD-010 | The calendar will not page back before the current period | Seed applied | Press ← repeatedly, in each of Month and Week | — | It steps back to the current month (or week) and the ← control is then disabled. The payload is upcoming-only, so earlier periods would be empty by construction, not by fact. | 🟠 |
| TC-VSD-017 | The week view names each item rather than dotting it | Seed applied | Press **Week** | — | Seven day columns, Monday first, headed with the week's date range. Each item appears in its day's column with the venue name and its Singapore-time span, colour-coded by kind. A day with more items than fit scrolls within its column. | 🟠 |
| TC-VSD-018 | Switching view keeps the period in view | Seed applied | From the month view press → to reach November, then press **Week** | — | The week view opens inside November rather than jumping back to the current week. Pressing **Month** returns to the month the shown week sits in. The arrows step by week while in Week, by month while in Month. | 🟠 |
| TC-VSD-011 | Pending requests are ordered longest-waiting first, without SLA framing (BR-R4, LC-R4) | Seed applied (two holds after re-seeding) | Read the "Pending requests" list | — | The oldest request is first. Each row shows "Waiting N days" in **neutral ink** — never red, never "overdue", never a countdown. Holds do not expire. | 🔴 |
| TC-VSD-012 | A request row opens its own page (AC5) | Seed applied | Click a pending request | — | Navigates to `/bookings/<booking id>`, which states that the full request view and the approve/reject decision arrive with SCRUM-19/20 and echoes the booking id back. It does not 404 or dead-end. | 🟠 |
| TC-VSD-013 | Venue rows show status at a glance and open the venue (AC2, AC5) | Seed applied | Read the "All venues" panel, then click a venue | — | All 8 venues listed, needing-attention first: `BLOCKED NOW` (red) / `BLOCK SCHEDULED` (yellow) / `ACTIVE` / `INACTIVE`. Old Lecture Theatre reads INACTIVE. Clicking opens `/venues/:id`. The panel is headed "All venues" with the pool note (AUTH-R5). | 🔴 |
| TC-VSD-014 | An inactive venue reads inactive even while blocked | Seed applied; add a block on Old Lecture Theatre | Read its row | — | Status is `INACTIVE`, not `BLOCKED NOW`. Out of service entirely outranks a block on it. | 🟠 |
| TC-VSD-015 | Usable on a phone-width viewport (NFR-U1) | Seed applied | Set the viewport to 390 × 844 | — | Tiles stack to one column, the calendar sits below them, both list panels stack, no horizontal scrolling, all 7 calendar columns legible. | 🟠 |
| TC-VSD-016 | Times display in Asia/Singapore (REQUIREMENTS §4) | Set the OS timezone to something other than SGT | Reload and read any period | — | Times are unchanged — rendered in Asia/Singapore regardless of the browser's zone, matching the venue detail page. | 🟠 |

### 10.1 Traceability — SCRUM-70

| Acceptance criterion / rule | Covered by |
|---|---|
| AC1 "On successful login, Venue Staff are routed directly to their dashboard" | TC-RBAC-003 (existing), TC-VSD-005 |
| AC2 "lists all venues … current status (active/blocked) shown at a glance" | TC-VSD-001, TC-VSD-013, TC-VSD-014 |
| AC3 "a count or list of pending booking requests awaiting my decision" | TC-VSD-001, TC-VSD-011 |
| AC4 "any active or upcoming blocks I've set" | TC-VSD-001, TC-VSD-008, TC-VSD-009 |
| AC5 "Selecting a venue or a pending request … navigates directly to its full details" | TC-VSD-012, TC-VSD-013 |
| REQUIREMENTS §6.21 widget priority order (holds → re-review → blocks → venues) | TC-VSD-001 |
| REQUIREMENTS §6.21.2 month and week views | TC-VSD-017, TC-VSD-018 |
| REQUIREMENTS §6.21 "build a widget only when its data exists" | TC-VSD-003, TC-VSD-012 |
| AUTH-R5 / QA-44 (staff are a pool; scope is all venues) | TC-VSD-013 |
| BR-R4 (holds never expire; oldest first) | TC-VSD-011 |
| LC-R4, QA-55, QA-68 (no SLA or deadline framing) | TC-VSD-011 |
| §6.14, CAL-R2 (half-open periods; a block's end is exclusive) | TC-VSD-008 |
| §6.19 (re-review after an approved change) | TC-VSD-001 |
| SCRUM-74/75 (guards read the session's active role) | TC-VSD-005 |
| RBAC (venue staff only) | TC-VSD-006 |
| REQUIREMENTS §4 (stored UTC, displayed Asia/Singapore) | TC-VSD-016 |
| NFR-U1 (desktop and mobile friendly) | TC-VSD-015 |
| PROJECT_REVIEW D8 (fabricated metrics) | TC-VSD-002 |
| Reliability (an outage is not rendered as "nothing to do") | TC-VSD-004 |

Automated equivalents live in `frontend/src/features/venues/__tests__/` and `backend/tests/`. `calendar.spec.js` covers TC-VSD-007, 008, 010 and the week-grid half of 017 as pure unit tests, including boundaries a manual pass cannot easily reach (a range ending one millisecond after midnight, and the same instant written two ways). `dashboard.spec.js` covers TC-VSD-011's ordering and TC-VSD-013/014's status precedence. `venueStaffDashboardStore.spec.js` covers TC-VSD-003 and 004. `views/__tests__/venueStaffDashboard.spec.js` covers TC-VSD-001, 002, 009, 012 and 013. `backend/tests/test_venues_api.py` covers TC-VSD-005 and 006's server side. TC-VSD-015 and TC-VSD-016 are visual and remain manual.
