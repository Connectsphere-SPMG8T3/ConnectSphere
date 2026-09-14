# ConnectSphere — Project Scenario & Context

This document captures the course context, the business domain, and the architectural decisions behind this codebase, so that future work — by a developer or an AI assistant, on this sprint or a later one — starts from the same shared understanding instead of re-deriving it from the code or from partial summaries.

**This is a living document, not a snapshot of one sprint.** Sections 1–3 and 5–7 (course context, customer briefing, first-release scope, architecture, design system, database principles) are stable reference material that should only change if the customer or the team's architecture actually changes. Section 4 is an **append-only implementation log** — one entry per completed Scrum story — and is where every future sprint should add its own record. See §4's instructions before starting a new story.

Sources for this document: `IS212 (AY2026/27, T1) — Scrum Project Instructions` (Week 4), `IS212 — Customer Briefing: Event Planning and Venue Booking System` (Week 1), and Jira exports for individual issues (e.g. `SCRUM-48`).

## 1. Course context

This repository is the codebase for an **IS212 (Software Project Management) team project**: a term-long exercise in running an agile (Scrum) software project against a simulated customer, ConnectSphere. The grading rubric (Week 4 instructions) weighs the Scrum *process* — sprint evidence, estimation, backlog quality, retrospectives — at least as heavily as the delivered software, and explicitly penalises "an AI-generated solution that you cannot explain/justify." Practically, this means:

- Every change in this repo should be traceable back to a specific backlog item (a Jira issue like `SCRUM-48`) and, ultimately, back to a piece of the customer briefing.
- Code should be something the team can explain and defend in a 20-minute instructor Q&A, not just something that passes.
- Test coverage and traceability from requirement → code → test matters as much as the feature working.

The customer briefing (Week 1) is **deliberately wide-ranging and ambiguous** — the brief itself says so explicitly ("No real-world customer knows precisely what they want on day 1"). It describes a large system; only a subset of it — the 20 core features identified in the Week 4 instructions (§3 below) — is in scope for the first release (due Week 12). Anything in the briefing outside that list of 20 is background/context for the product backlog, not something to build yet.

## 2. The customer: ConnectSphere Event Services

ConnectSphere Event Services is a regional organisation (~500 staff) that provides event planning and venue-booking services across Southeast Asia, operating several physical venues within Singapore and maintaining equipment/resources for events (conferences, seminars, workshops, etc.). It currently coordinates events using a mixture of email, spreadsheets, shared calendars, messaging apps, and manual documents — the motivation for the new system is to replace that fragmented process with one platform.

### 2.1 Roles

| Role | Internal / External | Main responsibility (per customer briefing) |
|------|----------------------|-----------------------------------------------|
| **Event Organiser** | External | Client representative who has an event to organise and communicates event requirements to ConnectSphere. |
| **Event Coordinator** | Internal | Assigned to coordinate the overall planning of an event; acts as the main internal point of contact. |
| **Venue Staff** | Internal | Responsible for venue information, availability, booking decisions, and physical venue preparation. |
| **Technical Support Staff** | Internal | Responsible for equipment, technical requirements, equipment reservations, and technical support for events. |
| **Attendee** | External | Participant who registers for and attends an event. |

### 2.2 The typical event lifecycle (customer briefing §5)

This is the end-to-end workflow the whole system is ultimately meant to support, and the reason the platform is built as a modular monolith rather than five unrelated apps:

1. **Draft Event Request** — an Event Organiser drafts a request and can save/resume it before submitting.
2. **Submission** — the Organiser submits the request.
3. **Coordinator Assignment** — an Event Coordinator is assigned as the main point of contact.
4. **Review and Clarification** — the Coordinator reviews the request, asking the Organiser for clarification/amendment if information is incomplete (e.g. "large room" with no attendance figure, or "hybrid event" with no video-conferencing spec).
5. **Initial Approval** — the Coordinator decides whether planning proceeds; rejected/returned requests retain a record of the decision.
6. **Venue Identification** — the Coordinator searches for venues matching date, time, capacity, layout, accessibility, facilities, and setup requirements.
7. **Venue Request** — the Coordinator submits a venue booking request; Venue Staff approve, reject, or suggest an alternative.
8. **Technical Requirements** — if needed, Technical Support Staff assess and reserve equipment/support.
9. **Event Preparation** — the Coordinator tracks outstanding arrangements as Venue Staff and Technical Support Staff update their pieces.
10. **Event Confirmation** — once essentials are arranged, the Coordinator confirms the event; the Organiser sees the confirmed arrangements.
11. **Attendee Registration** — where applicable, Attendees register within the registration period and subject to capacity.
12. **Changes Before the Event** — the Organiser may request changes; the Coordinator assesses impact on venue/equipment/technical-support/registration.
13. **Event Delivery** — Venue Staff and Technical Support Staff prepare on the day; relevant users see the latest confirmed information.
14. **Completion** — the event is marked completed, with attendance/operational notes recorded.

Changes are expected to ripple: e.g. attendance going from 80 to 150 may make the booked venue unsuitable; a date change may create a venue/equipment conflict. The customer briefing calls this out explicitly as a **reliability and consistency** requirement — the system must not show contradictory information about a single event's date, venue, equipment, or registration status once something changes.

### 2.3 Non-functional requirements (customer briefing §8)

| Concern | Requirement |
|---|---|
| Performance | Common operations (viewing an event, searching venues, opening a venue calendar, checking equipment availability, submitting a registration) should complete "within a reasonable time." |
| Security | Access depends on role *and* relationship to an event (e.g. an Organiser must not see another client's events; an Attendee must not see internal planning information). |
| Usability | All user groups should complete common activities without extensive training. |
| Reliability & consistency | No contradictory information across related event/venue/equipment/registration records. |
| Scalability | Must support 3 years of anticipated growth in events, users, venues, equipment, registrations. |
| Auditability | Important actions must be traceable — what changed, who changed it, when. |
| Maintainability | Future functionality/business rules must be addable without a full rebuild — the direct justification for the modular monolith architecture used here. |
| Design | Desktop- and mobile-friendly, for both external users and internal staff working on-site. |

## 3. First release scope: 20 core features (Week 4 instructions)

The customer briefing describes far more functionality (client management, recurring events, waiting lists, venue usage reports, etc.) than a one-term project can build. The Week 4 project instructions narrow the **first release** (due Week 12) to exactly these 20 functionality areas:

| # | Functionality area | Summary |
|---|---|---|
| 1 | User Authorisation and Authentication | Secure access; visibility/functionality scoped by role — epic `SCRUM-7`; see the implementation log (§4) for which stories under it are done. |
| 2 | Event Request Creation | Organisers create/submit requests (name, purpose, description, date/time, attendance, venue/accessibility/equipment/registration needs). |
| 3 | Draft Event Requests | Organisers save incomplete requests, distinguishable from submitted ones. |
| 4 | Event Review and Approval | Coordinators review, request clarification/amendment, approve or reject. |
| 5 | Coordinator Assignment | Events assigned to a Coordinator; reassignable. |
| 6 | Event Status Management | Consistent status progression (draft → submitted → under review → approved → planning → confirmed → completed / cancelled / rejected, etc.). |
| 7 | Event Information Management | Authorised edits during planning; distinguishes ordinary edits from changes affecting existing arrangements. |
| 8 | Venue Catalogue | Venue records: location, capacity, facilities, accessibility, layouts, operating info. |
| 9 | Venue Availability Calendar | Internal users see availability, reflecting existing bookings/unavailability. |
| 10 | Venue Search and Filtering | Coordinators filter venues by date/time/attendance/location/capacity/accessibility/layout/facilities. |
| 11 | Venue Suitability Checking | System flags unsuitable venues (e.g. attendance > capacity). |
| 12 | Venue Booking Request | Coordinator requests a venue booking with event timing/requirements. |
| 13 | Venue Booking Approval | Venue Staff approve/reject, with a reason when rejecting. |
| 14 | Booking Conflict Detection | Detects/prevents overlapping bookings; confirmed bookings affect future availability. |
| 15 | Equipment Request Management | Coordinators record equipment type/quantity/technical requirements; Tech Support updates as arranged. |
| 16 | Equipment Availability Checking | Tech Support checks sufficient/suitable equipment for the required date/time. |
| 17 | Equipment Reservation | Reserving equipment reduces availability for overlapping events; stays tied to its event. |
| 18 | Attendee Registration | Attendees view info, register, view status, withdraw; Organisers/Coordinators view registrations for their events. |
| 19 | Event Change Requests | Organisers request changes post-submission; Coordinators review; significant changes (date/time/attendance/venue/equipment) may require re-checking arrangements. |
| 20 | Notification System | Notifications for submission, clarification, approval/rejection, assignment, booking decisions, changes, registration updates, confirmation/cancellation. |

The instructions are explicit that these 20 features are **not isolated** — the release should demonstrate coherent end-to-end workflows across them (matching the lifecycle in §2.2), and design/tests should reflect the relationships between features (e.g. an attendance change should be able to affect venue suitability).

As of the most recent entry in §4's implementation log, only feature #1 (User Authorisation and Authentication) has any implementation. Features 2–20 have empty stub packages (`backend/app/modules/{events,venues,equipment}/`) reserved for future sprints — do not assume any of that domain logic exists until a log entry below says otherwise. **When a story lands for one of features 2–20, add a log entry in §4 and update this sentence and the stub-package note.**

## 4. Implementation log (append one entry per completed Scrum story)

**How to use this section:** when a story is completed, copy the template below, fill it in from the Jira issue (don't paraphrase the user story or acceptance criteria — quote them verbatim, the same way SCRUM-48's entry does), and add it as a new `###` subsection *after* the most recent entry, so the log reads chronologically. Do not delete or rewrite prior entries when requirements change later — instead, add a new entry for the story that changes them, and note in that new entry which earlier entry/behaviour it supersedes. This keeps the log an honest history of what was built and when, which is exactly the kind of requirement → code traceability the course rubric (§1) rewards.

<details>
<summary><strong>Template for a new entry (click to expand)</strong></summary>

```markdown
### 4.N. SCRUM-XX — <issue summary> (exact Jira record)

| Field | Value |
|---|---|
| Issue key | `SCRUM-XX` |
| Summary | <copy from Jira> |
| Issue type | Story / Bug / Task |
| Status | <status at time of writing this entry> |
| Parent epic | `SCRUM-Y` — <epic name> |
| Sprint | <sprint name> |
| Story point estimate | <n> |
| Priority | <priority> |

**User story (verbatim):**

> <paste exactly as written in Jira>

**Acceptance criteria (verbatim from Jira):**

> <paste exactly as written in Jira, including any typos — note them rather than silently fixing them>

#### How the implementation maps to the ticket

<Explain anything the ticket left implicit that you had to interpret, and what NFRs or prior log entries justified that interpretation. Be explicit about assumptions vs. literal ticket text — an instructor may ask "where did requirement X come from?" and the answer should be findable here.>

What was actually built:

1. <bullet per behaviour, naming the actual file/endpoint/component that implements it>
```

</details>

### 4.1. SCRUM-48 — Basic user authentication (exact Jira record)

| Field | Value |
|---|---|
| Issue key | `SCRUM-48` |
| Summary | Basic user authentication |
| Issue type | Story |
| Status | To Do (at time of export) |
| Parent epic | `SCRUM-7` — User authorisation and authentication |
| Sprint | SCRUM Sprint 1 |
| Story point estimate | 5.0 |
| Priority | Medium |

**User story (verbatim):**

> As a registered ConnectSphere user, I want to securely log in with my username and password, So that I can access my role-specific dashboard and system features.

**Acceptance criteria (verbatim from Jira):**

> For successful login:
> - Given a registered user exists with a valid username and password.
> - When they enter their correct credentials on the login screen.
> - Then they are successfully authenticated and redirected to their home dashboard.
> - able to see the profile for for me
>
> For unsuccessful login:
> - Given a user is on the login screen.
> - When they enter an invalid username or incorrect password.
> - Then they see a clear error message and are denied entry.

#### How the implementation maps to the ticket

The ticket text alone specifies: successful login → redirect to a home dashboard + a profile view ("for me"); unsuccessful login → clear error, denied entry. It does **not** spell out RBAC route-guarding or five distinct dashboards in so many words. Those were added as a reasonable, explicit interpretation of *"redirected to their **role-specific** dashboard"* combined with the security NFR in the customer briefing ("access should depend on the user's role") and the five roles defined for the whole system (§2.1) — but this is an interpretation, not literal ticket text, and is worth calling out explicitly to an instructor if asked "where did the RBAC requirement come from?".

What was actually built for SCRUM-48:

1. **Successful login** — `POST /api/v1/auth/login` authenticates against Supabase Auth and returns a JWT + profile; the frontend (`stores/auth.js`) stores the session and redirects to `ROLE_DASHBOARD_ROUTES[profile.role]`.
2. **Unsuccessful login** — invalid credentials surface as a 401 with `detail: "Invalid email or password."`, rendered as an error banner on `LoginView.vue`; the user stays on the login screen.
3. **View own profile** — `GET /api/v1/auth/me` (backend) and `/profile/me` (frontend route) show the authenticated user's profile.
4. **Role-specific dashboard + RBAC** — one dashboard route per role (`/dashboard/organiser`, `/dashboard/coordinator`, `/dashboard/venue-staff`, `/dashboard/tech-support`, `/dashboard/attendee`), each guarded by `meta.allowedRoles` in the Vue Router; unauthenticated or mismatched-role access redirects rather than rendering.

#### Post-implementation verification: real bugs the mocked test suite couldn't catch

The initial implementation was built and unit-tested entirely against a Supabase project with no real credentials (mocked Supabase clients throughout). When the migration was later applied and the flow was run end-to-end against the actual live project (`vuiryrzzyfecjqftwicj`), four real defects surfaced that every mocked test had passed against:

1. **Wrong API key format assumption.** The originally pinned `supabase-py==2.7.4` validated keys against a JWT-shaped regex and rejected this project's newer `sb_publishable_…`/`sb_secret_…` keys outright with `SupabaseException: Invalid API key`. Fixed by upgrading to `supabase==2.31.0` (regex check removed upstream) and switching `.env` variable names from the legacy `SUPABASE_ANON_KEY`/`SUPABASE_SERVICE_ROLE_KEY` to `SUPABASE_PUBLISHABLE_KEY`/`SUPABASE_SECRET_KEY` throughout the backend, frontend, and docs.
2. **Wrong JWT verification scheme.** This Supabase project signs session JWTs with asymmetric ES256 keys, not the legacy HS256 shared secret the original `decode_access_token` assumed (`jose.jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], ...)`) — what had been stored as `SUPABASE_JWT_SECRET` was actually the signing key's *Key ID*, not a secret at all. Every mocked test built its own HS256 token with `jose.jwt.encode` and so never exercised real verification. Fixed by rewriting `decode_access_token` to delegate to the Supabase SDK's `get_claims()`, which verifies against the project's published JWKS and supports either scheme; `SUPABASE_JWT_SECRET` was removed from configuration entirely.
3. **Wrong exception module.** `gotrue.errors` and `supabase_auth.errors` define same-named but unrelated exception classes; the code (and, circularly, the tests that mocked against the same wrong import) caught `gotrue.errors.AuthApiError`/`AuthError`, which real runtime code never raises — a genuine invalid-login or invalid-token error would have 500'd instead of returning a clean 401. Fixed by importing from `supabase_auth.errors` everywhere.
4. **Wrong return-type assumption.** `get_claims()` returns a `ClaimsResponse`, which is a `TypedDict` (a plain `dict` at runtime) — code and test mocks alike initially assumed attribute access (`claims_response.claims`) instead of `claims_response["claims"]`.
5. **Redundant double profile fetch.** `GET /auth/me` fetched the caller's profile once inside the `get_current_user` dependency and then fetched it *again* via `service.get_profile()` in the router handler — harmless functionally, but a real, avoidable extra round trip to `public.profiles` on every request. Fixed by having the router build the response directly from the already-fetched `CurrentUser`.

**Lesson for future stories:** a green `pytest` run against fully mocked Supabase clients proves the code's own logic is internally consistent — it does not prove the code is compatible with the actual pinned SDK version's behaviour or the actual live project's configuration (key format, JWT signing scheme, exception types). Before marking any story that touches Supabase Auth as done, run it at least once against the real project with real credentials, the way §7 of `docs/SETUP.md` describes.

### 4.2. Bug fix — auth session isolation, sign-up role escalation, RLS recursion, session renewal (PROJECT_REVIEW D1–D6)

| Field | Value |
|---|---|
| Issue key | None yet — defects D1–D6 in `docs/PROJECT_REVIEW.md` (log a Jira **Bug** linked to `SCRUM-48` when updating the board) |
| Summary | Fix six defects in the SCRUM-48 auth layer found during the 13 Sep design review |
| Issue type | Bug |
| Status | Fixed on branch `fix/auth-security-bugs`; database migration applied to the live project |
| Parent epic | `SCRUM-7` — User authorisation and authentication |
| Sprint | SCRUM Sprint 1 |
| Supersedes | §4.1 behaviour: logout implementation, sign-up role mapping, `profiles` RLS policies; `docs/TEST_CASES.md` TC-DATA-007's old expected result |

Every defect was reproduced against the live project **before** changing code, and each has a regression test that failed on the old code for the reason the defect describes.

| Defect | Severity | Symptom (reproduced live) | Root cause | Why earlier tests missed it | Fix |
|---|---|---|---|---|---|
| **D1** | Critical | Two users log in; when the *first* logs out, the *second* user's refresh token is revoked (`400 refresh_token_not_found`) while the first user's session stays alive. | `get_supabase_anon_client()` is `@lru_cache`'d and shared by every request. supabase-py stores the session from `sign_in_with_password` **on the client instance**, and `sign_out()` revokes whatever session that instance holds, with `scope="global"`. It also starts a background timer that silently refreshes (and rotates) the stored user's token. | Every test used one user and a `MagicMock` client, so the shared state the bug lives in was mocked away. | `create_auth_client()` (`app/db/supabase.py`) builds a fresh client per sign-in/refresh with `persist_session=False, auto_refresh_token=False`; logout calls `auth.admin.sign_out(<caller's token>, "local")`. Tests: two-login isolation, real-client option checks, logout-uses-caller's-token. |
| **D2** | Critical (security) | A sign-up whose metadata requests `event_coordinator` gets a coordinator profile. Exploitation check: only the 5 seeded accounts existed, so it had not been abused. | `handle_new_user()` copied `raw_user_meta_data ->> 'role'` — client-supplied data — into `profiles.role`, and public sign-up is enabled with the publishable key shipped to the browser. | Only exercised through the seed script, which legitimately wants staff roles. | Migration `20260913120749_fix_auth_security_defects.sql`: role allow-list (`event_organiser`, `attendee`; everything else → `attendee`) per QA-3/QA-4; `EXECUTE` revoked from `anon`/`authenticated`. `seed.sql` now sets staff roles explicitly after insert. |
| **D3** | High | Any query on `profiles` as a logged-in user fails: `42P17 infinite recursion detected in policy for relation "profiles"`. | Policy `profiles_select_internal_staff` queried `public.profiles` from inside a `profiles` policy. | The backend uses the secret key, which bypasses RLS, so no API path ever evaluated the policy. | Same migration: role lookup moved to `private.current_user_role()` (security definer, pinned `search_path`, non-exposed schema); the two SELECT policies merged into one `to authenticated` policy using `(select auth.uid())`. |
| **D4** | High | The SPA discarded the refresh token, so the session died when the 1-hour access token expired; the app also never re-checked a stored session, so an expired/revoked session kept showing the dashboard until an API call failed. | No refresh endpoint and no renewal logic in the store/router. | No frontend tests; manual testing never ran past token expiry. | `POST /api/v1/auth/refresh`; `stores/auth.js` persists the refresh token, `withSession()` renews once on 401 and retries (single in-flight refresh, since Supabase rotates refresh tokens), the router guard verifies the session once per page load, and logout renews-then-revokes if the access token has expired. |
| **D5** | Medium | 8 concurrent `/auth/me` calls took 6× as long as one. | Synchronous supabase-py calls inside `async def` endpoints/dependencies block the event loop. | Tests ran one request at a time. | Auth endpoints, `get_current_user`, and `require_roles` are plain `def` (FastAPI runs them in its threadpool). Test: 4 concurrent requests with a 0.25 s simulated DB call must finish in < 0.6 s. |
| **D6** | Low | Supabase advisors: mutable `search_path` ×2, security-definer function executable via RPC ×2, per-row `auth.uid()` ×3, multiple permissive policies ×6. | Hygiene gaps in the initial migration. | Advisors weren't run after the initial DDL. | Same migration. Remaining advisor findings: leaked-password protection (a dashboard toggle) and one "unused index" INFO (no traffic yet). |

**Verification after the fix:**

- `pytest`: 19/19 passing, including 10 new or changed regression tests.
- Live reproduction script, rerun unchanged:
  - D1: the other user's session survives, and the logged-out user's session is revoked.
  - D4: refresh returns 200, rotates the refresh token, and returns 401 for a bogus token.
  - D5: the burst ratio dropped from 6.0× to 2.9×; the remainder is network round-trips to Supabase.
- `supabase/verification/auth_security_checks.sql` failed on the old schema (`D2 FAIL`), passed in a rolled-back dry run of the migration, and passed again after applying it.
- A live sign-up through the Supabase Auth admin API confirmed the trigger still fires after the `EXECUTE` revoke, a requested `event_coordinator` becomes `attendee`, and a requested `event_organiser` is honoured. The temporary users were deleted.
- A headless-browser run against the real app passed 5/5: login stores the refresh token; an expired access token is renewed silently; a session that can't be renewed signs out with a message; logout revokes the server session; logout with an expired access token still revokes it.

**Known limitation (unchanged):** Supabase access tokens are stateless JWTs verified locally via JWKS, so a revoked session's *access* token stays valid until it expires (up to 1 hour). Revocation takes effect at the next refresh.

**Process follow-up:** `list_migrations` showed the original migration `20260912000001` was applied as raw SQL and isn't recorded in Supabase's migration history, so only `20260913120749` is tracked. That history should be backfilled before anyone uses `supabase db push`.

### 4.3. Bug fix — auth review follow-ups: outage handling, unsupported-role redirect loop, test isolation

| Field | Value |
|---|---|
| Issue key | None yet. Found in an external code review of the §4.2 fix (log a Jira **Bug** linked to `SCRUM-48` when updating the board) |
| Summary | Report Supabase outages as 503 without ending sessions; stop the router looping on a session with no dashboard; isolate the role-guard test |
| Issue type | Bug |
| Status | Fixed on branch `fix/auth-review-followups` |
| Parent epic | `SCRUM-7` — User authorisation and authentication |
| Sprint | SCRUM Sprint 1 |
| Supersedes | §4.2 D4 behaviour: the SPA no longer treats *every* API error during session verification as a rejected session |

Each defect was reproduced before changing code, and each has a regression test that failed on the old code for the reason described.

| Defect | Severity | Symptom (reproduced) | Root cause | Why earlier tests missed it | Fix |
|---|---|---|---|---|---|
| **Outage ends sessions** | High | With the API pointed at a stub Supabase that answers 503: `POST /auth/login` → 500, `POST /auth/refresh` and `GET /auth/me` → 401. In the browser, reloading a dashboard signed the user out with "Your session has expired". | supabase-auth turns a 5xx gateway response into `AuthRetryableError`, a subclass of `AuthError` but not `AuthApiError`. `refresh` and `decode_access_token` caught all `AuthError` and returned 401; `login` caught only `AuthApiError`, so it returned 500. The store then called `clearSession` on *any* `ApiError`, 5xx included. | Every mocked failure was an `AuthApiError` or `AuthInvalidJwtError`; no test modelled an upstream outage, and the frontend had no tests. | `AuthRetryableError` → new `AuthServiceUnavailableError` (503) in `login`, `refresh` and `decode_access_token`. `stores/auth.js` only ends a session on 401/404 (`isSessionRejected`). |
| **Unsupported-role redirect loop** | Medium | A stored session whose role has no dashboard, with the backend unreachable: `/login` renders blank, Vue Router aborts with "Infinite redirect in navigation guard", and the guard fires 32 `/auth/me` calls. | `dashboardPath` falls back to `/login`, and the guard redirects an authenticated visitor of `/login` to `dashboardPath`, i.e. to itself. The `user_role` enum matches `ROLE_DASHBOARD_ROUTES` today, so this needs a stale stored profile or a future role missing from the frontend. | No frontend tests. | The guard clears such a session with a message and shows the login page. |
| **Role-guard test changed the shared app** | Low | `test_require_roles_blocks_mismatched_role` added a probe route to `app.main.app` that stayed for the rest of the run. | The `client` fixture wraps the shared app singleton. | No failure yet, since the probe path collides with nothing. | The probe is mounted on a throwaway `FastAPI()` app. |

**Verification after the fix:**

- `pytest`: 22/22 passing (3 new outage tests; the role-guard test still fails if `require_roles` is inverted, and no probe route remains on the shared app).
- Vitest (new, `npm test` in `frontend/`): 6/6 passing, including 5 regression tests that failed on the old code.
- The live outage reproduction, rerun unchanged, now returns 503 from all three endpoints with a clear message.
- A headless-browser run against the dev server, before and after: during the outage, a 503 from `/auth/me` or from refresh now keeps the user on their dashboard with the session intact. The unsupported-role session now shows the Sign In form with a message, makes one API call, and logs no router warning.

**Not changed, noted for later:** a dropped connection to Supabase (`httpx.ConnectError`) is not converted by supabase-auth and still returns 500. The SPA no longer signs users out on it, but the backend could map it to 503 too. `logout` still returns 500 during an outage; the SPA ignores logout errors, and the server-side session can't be revoked while Supabase is down anyway.

## 5. Architecture: modular monolith

- **`backend/`** — Python FastAPI. Each domain lives in its own package under `app/modules/<domain>/` with a consistent internal shape (`router.py`, `schemas.py`, `service.py`, optionally `dependencies.py`), sharing a common `app/core/` (config, security, exceptions) and `app/db/` (Supabase client factories). Modules talk to each other only through service-layer function calls, never by reaching into another module's internals — the `auth` module's `dependencies.py` re-exports `app.core.security` deliberately, so other future modules depend on `app.modules.auth.dependencies` rather than on `app.core` directly.
- **`frontend/`** — Vue 3 (Composition API, `<script setup>`), Vite, Pinia, Vue Router. Route guards in `src/router/index.js` handle both `requiresAuth` and per-route `allowedRoles`.
- **`supabase/`** — Postgres schema (migrations) and seed data. Supabase Auth (`auth.users`) owns credentials; `public.profiles` owns ConnectSphere-specific attributes (role, department, organisation), kept in sync by a `handle_new_user()` trigger — this is a deliberate 3NF split rather than duplicating auth data.
- **`mcp/`** — Supabase MCP server config for project `vuiryrzzyfecjqftwicj`, so an AI assistant can inspect the live schema/logs/advisors directly.

This architecture choice is a direct response to the customer briefing's **maintainability** NFR (§2.3): future functionality and business rules — features 2–20 — need to be addable as new modules without rebuilding features 1's auth layer, and without those new modules being able to bypass the access control already built here.

### Why the backend never re-implements password checking

`app/modules/auth/service.py` calls Supabase's GoTrue API (`sign_in_with_password`) rather than checking a password hash itself. On success it gets back a Supabase-issued JWT, which `app/core/security.py` then verifies on every subsequent authenticated request via the Supabase SDK's `get_claims()` — this checks the token's signature and expiry against the project's published JWKS (fetched once and cached locally), so it works whether the project signs sessions with the legacy HS256 shared secret or the current asymmetric ES256 signing keys, without the backend hardcoding either. (`get_claims` does not itself check the `aud` claim, so `decode_access_token` verifies that explicitly.) This still avoids a live call to Supabase on the *common* path (only the first request after startup or JWKS-cache expiry triggers a fetch), while trusting Supabase as the single source of truth for "is this password correct" and "is this token genuinely ours."

One thing worth knowing if you're extending this: `supabase-py`'s exception classes live in the `supabase_auth` package at runtime — the older `gotrue` package name still exists (installed as a dependency of `supabase-py`) but defines a **separate, unrelated set of exception classes** that happen to share the same names (`AuthApiError`, `AuthInvalidJwtError`, etc.). Importing from `gotrue.errors` instead of `supabase_auth.errors` will silently fail to catch real runtime errors — code will type-check and pass mocked tests (if the tests import from the same wrong module) while still 500ing in production. Always import Supabase auth exceptions from `supabase_auth.errors`.

A second SDK trap (§4.2, D1): supabase-py keeps the session from `sign_in_with_password`/`refresh_session` **on the client instance** and auto-refreshes it in the background. Never call those on a cached/shared client — use `app.db.supabase.create_auth_client()`, which returns a fresh client with persistence and auto-refresh disabled. The shared publishable-key client is only for stateless calls that take the token explicitly (`get_claims(token)`, `auth.admin.sign_out(token, scope)`).

### Why role checks need a profile lookup, not just the JWT

A Supabase JWT's own `role` claim is the Postgres role (`authenticated`), not a ConnectSphere business role. `get_current_user` in `app/core/security.py` therefore always fetches the corresponding `public.profiles` row (via the service-role client, bypassing RLS since the backend has already verified the caller's identity) to get `role`, `full_name`, etc. `require_roles([...])` builds on top of that.

## 6. Design system: Bauhaus constructivist modernism

The frontend deliberately avoids generic UI-kit aesthetics in favour of a strict, opinionated system:

- **Palette:** off-white canvas (`#F0F0F0`), stark black ink (`#121212`), and three primaries — red (`#D02020`), blue (`#1040C0`), yellow (`#F0C020`) — plus a muted grey (`#E0E0E0`).
- **Typography:** `Outfit` (weights 400/500/700/900), headlines in uppercase `font-black tracking-tighter leading-[0.9]`, labels in `font-bold uppercase tracking-widest`.
- **Radii:** binary only — `rounded-none` or `rounded-full`. No soft corners anywhere.
- **Shadows:** hard offset shadows (`shadow-hard` / `shadow-hard-lg`, mapped to `4px_4px_0px_0px_#121212` / `8px_8px_0px_0px_#121212`), with buttons pressing flat on `:active`.
- **Components** (`frontend/src/components/common/`): `BauhausButton`, `BauhausCard` (with a geometric corner accent — circle, square, or triangle), `BauhausInput` (with validation error states), `BauhausNavbar` (geometric brand mark, role badge, logout).

These tokens live in `frontend/tailwind.config.js` and `frontend/src/assets/main.css`. Note that Tailwind's JIT scanner needs fully static class names — `BauhausCard`'s accent colour is resolved through a lookup object (`accentBgClasses` / `accentBorderClasses`) rather than a dynamic `bg-${accentColor}` string, since the latter would be invisible to Tailwind's build-time scan and silently produce no styles.

This design system is a project-specific/team choice (matching the customer briefing's generic "should be desktop- and mobile-friendly" and "presented clearly" requirements, §2.3), not something specified by the customer briefing itself.

## 7. Database design principles

- 3NF normalisation: auth credentials in `auth.users`, domain attributes in `public.profiles`.
- Surrogate UUID primary keys throughout (`profiles.id` is also a foreign key to `auth.users.id`, cascading on delete).
- `user_role` is a Postgres enum (`event_organiser`, `event_coordinator`, `venue_staff`, `tech_support`, `attendee`), not a free-text column.
- B-tree indexes on `profiles(role)` and `profiles(email)` for the lookups the auth flow performs on every request.
- Row Level Security is enabled on `profiles`: users can read/update their own row; internal staff (`event_coordinator`, `venue_staff`, `tech_support`) can read every profile (for cross-role coordination); a trigger explicitly blocks users from changing their own `role` column, since role elevation must go through a privileged path in a future story, not self-service.
- A policy must never query its own table (that recurses, `42P17`): role checks inside policies use the `private.current_user_role()` security-definer helper, and per-request functions are wrapped as `(select auth.uid())`. Security-definer functions pin `search_path = ''` and are not callable via RPC (§4.2).
- Sign-up metadata is client-controlled: `handle_new_user()` only accepts the external roles `event_organiser` and `attendee` from it; staff roles are set by seed/migration only (§4.2, QA-3/QA-4).

## 8. Where to look for what

| Question | Where to look |
|----------|----------------|
| "How does login actually work end to end?" | `frontend/src/stores/auth.js` → `frontend/src/services/api.js` → `backend/app/modules/auth/router.py` → `service.py` |
| "How is a route protected?" | `frontend/src/router/index.js` (`beforeEach` guard) |
| "How is a role protected on the backend?" | `backend/app/core/security.py` (`require_roles`) |
| "What does a user's profile contain?" | `supabase/migrations/20260912000001_init_auth_and_profiles.sql`, mirrored in `backend/app/modules/auth/schemas.py::ProfileResponse` |
| "What test accounts exist?" | `supabase/seed.sql`, table in `docs/SETUP.md` |
| "What exactly does story SCRUM-XX require, verbatim?" | §4's entry for that story (each entry is self-contained and quotes Jira verbatim) |
| "What has been built so far, across all sprints?" | Skim §4's entries in order — it's the running log of every completed story |
| "What's in scope for the whole first release?" | §3 of this document (20 features) |
| "What's out of scope entirely (for now)?" | Anything in the customer briefing not listed in §3 — e.g. client management, recurring events, waiting lists, venue/registration reports |
| "What's next?" | The next-highest-priority story in the product backlog under whichever epic is next up — check the backlog/Jira board, not this document, for current priority |
| "I just finished a story — what do I update here?" | Add a new `###` entry to §4 using its template; update the "as of the most recent entry..." sentence at the end of §3 if the story changes what's implemented for one of the 20 features |
