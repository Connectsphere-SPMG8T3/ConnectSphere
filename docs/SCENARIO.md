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

One qualification, from §4.5 (SCRUM-72): `frontend/src/features/events/` now exists, but holds **presentation logic only** — the coordinator dashboard's ordering, grouping and labelling, plus the data contract it expects. There is still no events domain logic, no events table, and no events endpoint. The proposed schema in `docs/proposals/` has not been applied to any database.

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

### 4.4. SCRUM-39 — View Venue Catalogue: venue search, filtering and availability (exact Jira record)

| Field | Value |
|---|---|
| Issue key | `SCRUM-39` |
| Summary | View Venue Catalogue |
| Issue type | Story |
| Status | In progress on branch `feature/scrum-39-venue-search` |
| Parent epic | `SCRUM-15` — Venue catalogue |
| Sprint | SCRUM Sprint 1 |
| Story point estimate | 3.0 |
| Priority | Medium |
| Supersedes | The story's own "setup, reset, and turnaround buffers" criterion, withdrawn per QA-28 (see below) |

**User story (verbatim):**

> As an Event Coordinator, I want to search and filter for venues based on the Event Organiser's information so that I can quickly find venues that meet an event's requirements.

**Acceptance criteria (verbatim from Jira, including the typo "criterias"):**

> Venues with matching criterias are returned
>
> Shows venue availability and information about the venue
>
> Allows filtering by date, time, required attendance, room layout, accessibility, and required facilities
>
> Excludes venues that are marked as unavailable due to maintenance, renovation, or safety restrictions
>
> Automatically incorporates setup, reset, and turnaround buffers between consecutive bookings when checking availability

#### How the implementation maps to the ticket

The story was kept as one deliverable (catalogue view + search/filter + availability) rather than split into 39a/39b as `PROJECT_REVIEW` B4 suggested, because with empty filters the search page *is* the catalogue view. Decisions that the ticket left open, each recorded in `REQUIREMENTS.md` §6.8/§6.10:

- **The buffer criterion was dropped.** The customer set setup/turnaround to zero (QA-28, QA-82, QA-93, QA-103); DB-1 and §6.14 are built on half-open `[starts_at, ends_at)` ranges so back-to-back bookings are allowed. Building the buffer would contradict the rule SCRUM-21 will test. Jira comment to add: *"Updated after Session 1 Q&A (QA-28): turnaround assumed zero; buffer criterion removed."*
- **"Based on the Event Organiser's information"** means the event request's fields (date/time, pax, layout, facilities, accessibility). `events` does not exist yet, so the API takes those as explicit query parameters; pre-filling from an `event_id` is a thin adapter for when SCRUM-8 lands.
- **"Marked as unavailable due to maintenance, renovation, or safety"** maps to **blocks** (§6.9). The three reasons are examples, not an allow-list: any block (also `internal_activity`, `other`) excludes, per CAL-R3, and so do `held`/`approved`/`re_review` bookings (BR-R2, §6.14).
- **Every criterion the coordinator sets is strict** — including layout and accessibility, which §6.11 classes as *warnings* for the suitability badge. Filtering is what the coordinator asked for; SCRUM-18's badge covers the "found it, but with caveats" case. A "Show N excluded" toggle reveals excluded venues with reasons so nothing is silently hidden.
- **Availability and suitability stay distinguishable** (§6.11): availability is its own field on each result; criterion failures are listed as reasons with codes.
- **Controlled lists** for layouts, facilities and accessibility features were never enumerated by the customer; the values are a **[Team decision]** in §6.8. `accessibility_features` became an enum array instead of the ERD's free text so it can be filtered exactly.
- Operating hours are displayed but not enforced (a SCRUM-18 warning). No pagination (≈50 venues, NFR-P1). Singapore has no daylight saving, so the SPA sends a fixed `+08:00` offset.

What was actually built:

1. **Schema** — `supabase/migrations/20260915090000_venues_catalogue_and_availability.sql`: enums `venue_layout`, `facility`, `accessibility_feature`, `venue_booking_status`, `venue_block_reason`; tables `venues`, `venue_layouts`, `venue_facilities`, `venue_blocks`, `venue_bookings`; **DB-1 exclusion constraint** (`btree_gist`, `venue_id WITH =, occupied_period WITH &&` over occupying statuses) and the **BR-R1 partial unique index** on `event_id`, both landed now while the table is empty; GiST index on blocks; RLS with staff-only `select` policies and no write policies (holds must go through the API). `venue_bookings.event_id` is a plain uuid until `public.events` exists (same choice as the SCRUM-23 branch). Verified by `supabase/verification/venue_schema_checks.sql` (overlap refused, back-to-back accepted, rejected bookings ignored, second active booking per event refused, blocks may overlap bookings, coordinator can read / organiser cannot / nobody inserts directly).
2. **Seed** — `supabase/seed.sql` gains 8 venues, 3 blocks and 3 bookings around 10 Oct 2026 so a search for 10 Oct 14:00–17:00 demonstrates every exclusion reason (Auditorium A booked 11:00–14:00 stays listed; Seminar Room 1 held 13:00–16:00; Heritage Hall blocked for renovation; Grand Ballroom's maintenance block ends exactly at 12:00; Old Lecture Theatre inactive; Innovation Lab's *rejected* booking ignored).
3. **Backend** — `backend/app/modules/venues/` is the **first module to adopt the REQUIREMENTS §3.3 shape**: `router.py` (`GET /api/v1/venues`, `GET /api/v1/venues/{id}`, both `require_roles(["event_coordinator", "venue_staff"])`), `schemas.py` (`VenueSearchCriteria` as a FastAPI query-parameter model; period must be given as a pair, timezone-aware, `ends_at > starts_at`), `service.py`, `repository.py` (the only file touching Supabase; overlap evaluated in Postgres with the range `&&` operator) and `search.py` (pure `evaluate(venue, criteria, occupants)` — the shape §6.11 wants for SCRUM-18's rules). The team has not otherwise adopted §3.3; this is the proposal, stated rather than slipped in.
4. **Frontend** — routes `/venues` and `/venues/:id` (coordinator + venue staff); `views/venues/VenueSearchView.vue`, `VenueDetailView.vue`; `components/venues/VenueCriteriaForm.vue`, `VenueResultCard.vue`; new common `BauhausSelect.vue` and `BauhausCheckboxGroup.vue`; `venuesApi` in `services/api.js` (all calls via `authStore.withSession`); `stores/venues.js` (moved to `features/venues/venueSearchStore.js` by SCRUM-70) keeps criteria and results so returning from a detail page keeps the search, and always requests `include_excluded=true` so the toggle is instant. A "Search venues" button on the coordinator and venue-staff dashboards.
5. **Domain vocabulary** — `CONTEXT.md` (repo root) now defines Venue, Block, Hold, Booking, Occupied period, Turnaround (zero), Availability vs Suitability, Search criteria, Excluded venue.

#### Verification

- `pytest`: 75/75 (41 new: 36 pure-rule cases in `tests/test_venue_search.py` incl. boundaries pax = capacity, 12:00/12:00 back-to-back, 11:59 overlap, every block reason, UTC→SGT message rendering; 19 HTTP cases in `tests/test_venues_api.py` incl. 401/403/422 and the response shape). Written before the implementation; the first run failed on import.
- Vitest: 20/20 (10 store cases; 4 view cases that mount `VenueSearchView`/`VenueDetailView` in jsdom with the real router and Pinia and assert rendered text, including the excluded-venues toggle and Singapore-time formatting of a UTC period).
- Against the live project: migration pushed with `supabase db push`, `venue_schema_checks.sql` → `ALL VENUE SCHEMA CHECKS PASSED` (and rolled back, 0 rows left), `supabase db advisors` shows no new findings, seed loaded. The API was run with real credentials: the §6.10 acceptance search (10 Oct 14:00–17:00, 150 pax, projector) returned Auditorium A and Grand Ballroom, and with `include_excluded=true` the six others with the expected reasons; an 11:59 start against the Grand Ballroom block returned "Blocked: maintenance 10 Oct 08:00–12:00"; the organiser account got 403; an inverted period got 422. This also confirmed the PostgREST range-overlap filter (`ov`) and the `tstzrange` text format parsing, neither of which the mocked tests can prove.
- **Not verified:** the pages in a real browser (no browser automation was available in the session; the SFCs compile under the Vite dev server and render in jsdom). Run TC-VENUE-001–012 manually before closing the story.

**Found on the way (logged as PROJECT_REVIEW D8):** the live project's migration history was missing `20260912000001` although its schema was applied, so `supabase db push` would have re-run it and failed. Repaired with `supabase migration repair --status applied 20260912000001`.

### 4.5. SCRUM-72 — Event Coordinator dashboard (exact Jira record)

| Field | Value |
|---|---|
| Issue key | `SCRUM-72` |
| Summary | Event Coordinator dashboard |
| Issue type | Story |
| Status | Implemented on branch `feature/scrum-72-coordinator-dashboard` |
| Parent epic | `SCRUM-7` — User authorisation and authentication (**misfiled**; PROJECT_REVIEW §B3 asks for a "Role-Based Dashboard" epic) |
| Sprint | SCRUM Sprint 1 |
| Story point estimate | *not recorded in the ticket text supplied* |
| Priority | *not recorded in the ticket text supplied* |

> Fields marked *not recorded* were not in the ticket text handed to the implementer. Fill them in from the Jira export rather than assuming; they are left blank here deliberately instead of guessed.

**User story (verbatim):**

> As an Event Coordinator, I want to access a dashboard showing pending requests, urgent alerts and schedule overviews so that I can quickly prioritize day-to-day actions.

**Acceptance criteria (verbatim from Jira):**

> 1. Displays a prioritized list of incoming event requests requiring immediate action, requests awaiting initial approval/rejection, and items with newly received client clarification responses.
> 2. Displays status for each active event

#### How the implementation maps to the ticket

**The blocking constraint, and the re-scope.** Every data item in both acceptance criteria depends on tables that do not exist. This was verified against the live project rather than inferred from the migration files (AGENTS.md): `GET {SUPABASE_URL}/rest/v1/` lists exactly one table, `profiles`. There is no `events`, `amendment_requests`, or `change_requests`, and `backend/app/modules/events/` is still an empty stub package.

This is the risk `PROJECT_REVIEW.md` §B4 row 1 anticipated for stories 70–73, and the re-scope recorded there was followed: *"shell plus the first widget whose data exists, with empty states for the rest"*, per `REQUIREMENTS.md` §6.21 — *"Build a widget only when its data exists; until then, show an empty state."* The story therefore ships the complete widget structure, the real data contract, and honest empty states. **It does not ship rows.** AC1 and AC2 are structurally present and verified against a stubbed payload, but cannot be demonstrated with live data until the events module lands.

The team chose this scope explicitly over (a) frontend-only with no schema work and (b) landing the core schema as part of this story. Landing the schema was rejected because §C3.5 requires whole-team review of the shared schema before merge. The schema was therefore drafted as a **reviewable proposal** instead: `docs/proposals/core-events-schema.sql`, not applied to any database, with a stand-up note in `docs/proposals/core-events-schema.md`.

**Interpretation of "client clarification responses" (AC1).** The ticket's wording predates the Session 1 answers. The customer's confirmed model is *return for amendment*: the coordinator returns a request with a message, and the organiser edits the same request and resubmits (QA-22, QA-77, `REQUIREMENTS.md` §6.4). `PROJECT_REVIEW.md` §B2a records that this replaced SCRUM-33's older "clarification thread" reading. A resubmission therefore **is** the clarification response, and the widget counts `amendment_requests.resubmitted_at`. If an instructor asks where this mapping came from, the answer is QA-22/QA-77 via §B2a — not the ticket text.

**Interpretation of "prioritized" (AC1).** The ticket does not define priority, and the customer ruled out SLA timers and review deadlines entirely (LC-R4, QA-55, QA-68), so urgency is **not** time-since-submission. Priority is ranked by *what the item blocks*, recorded as a **[Team decision]** in `REQUIREMENTS.md` §6.21. The ranking is an ordered config array, so re-prioritising moves one line (NFR-M1).

**Defect fixed in passing.** The previous `CoordinatorDashboard.vue` displayed three hardcoded metrics — "Requests Awaiting Review: 5", "Venues to Coordinate: 4", "Events in Progress: 9" — as if they were real figures, against a database with no events. Logged and fixed as **D8** in `PROJECT_REVIEW.md` §A2.

What was actually built:

1. **Pure dashboard logic** — `frontend/src/features/events/dashboard.js`. No I/O, so it is unit-testable in isolation (REQUIREMENTS §3.3): the `ACTION_KINDS` priority config, `prioritiseActionItems()`, `summariseActionItems()` (AC1's three named categories), `groupActiveEventsByStatus()` (AC2), `outstandingReadiness()` and `readinessGaps()`, plus the single `STATUS_LABELS` mapping required by LC-R3.
2. **Data contract and store** — `frontend/src/features/events/store.js` and `eventsApi.coordinatorDashboard()` in `services/api.js`, calling `GET /api/v1/events/dashboard/coordinator`. A `404` is treated as "the module isn't built yet" and renders empty; any other failure surfaces as an error, because an empty dashboard that silently swallowed a `500` would tell a coordinator they have nothing to do.
3. **The dashboard** — `frontend/src/views/dashboards/CoordinatorDashboard.vue`: the AS-R5 awaiting-assignment alert, the three AC1 category counters, the prioritised action list with per-kind badges, the AC2 status overview across all four active statuses, and the 14-day readiness-gap schedule overview.
4. **Empty-state component** — `frontend/src/components/common/BauhausEmptyState.vue`, which distinguishes *still loading* from *not built yet* from *genuinely clear*.
5. **Schema proposal** — `docs/proposals/core-events-schema.{sql,md}`: `client_organisations`, `events`, `event_status_history`, `amendment_requests`, `change_requests`, with RLS following the D3 non-recursive pattern. Events side only; venues, equipment and registrations are left to the full §C3.5 migration.

This follows the target SPA structure in `REQUIREMENTS.md` §3.4 (`features/<domain>` with views, store and service; dashboards *compose* from feature stores). It is the **first** part of the codebase to adopt it — `PROJECT_REVIEW.md` §A3.8 recommends it, and nothing had used it before. Noted here rather than diverged silently.

#### Verification

- **Live schema check:** PostgREST spec on `vuiryrzzyfecjqftwicj` returns `['profiles']` and no RPCs — the basis for the re-scope above.
- **Real backend:** logged in as `coordinator@connectsphere.dev` against the running API; `GET /api/v1/events/dashboard/coordinator` returns exactly `404 {"detail":"Not Found"}`, confirming the store's 404 path matches reality rather than an assumption.
- **Real browser (empty state):** Chrome via Playwright against the Vite dev server and the real backend — 13/13 assertions, covering both AC headings, all three AC1 categories, all four AC2 statuses, the awaiting-data notice, and the absence of the old fabricated metrics.
- **Real browser (populated):** the same page with the endpoint stubbed at the network layer with a five-event payload — 14/14, including the exact priority ordering (`arrangement_issue` → `cancellation_request` → `resubmitted` → `awaiting_review`), per-status counts, the `venue_blocked` flag, readiness-gap detail, Asia/Singapore date rendering, and no page errors. This is what proves AC1 and AC2 are met in substance.
- **Test suites:** Vitest 37/37 (28 new), pytest 22/22 unchanged, `npm run build` clean. Mobile (390 px) layout checked.

**A bug this verification caught:** the first browser run showed the counters reading a confident `0` for the several seconds the request is in flight — a coordinator could read "0 immediate actions" as fact while the answer was still unknown. The store now exposes `hasSettled`, and the dashboard shows an em dash until the first load resolves. A mocked test would not have surfaced this; it only appears at real network latency.

**Not verified:** anything requiring event rows — no live data exists to verify against. The priority ordering, status grouping and readiness logic are verified by unit tests and by a stubbed browser render, not against the database. The proposed schema has **not** been applied or run anywhere, so it is unproven SQL: it has not been parsed by Postgres, and no advisor run has been done against it.

### 4.6. SCRUM-74 & SCRUM-75 — Role dropdown and active-role switching (exact Jira record)

| Field | Value |
|---|---|
| Issue key | `SCRUM-74` (View assigned roles in nav dropdown), `SCRUM-75` (Select active role from nav dropdown, depends on SCRUM-74) |
| Issue type | Story (both) |
| Status | Implemented on branch `feature/scrum-74-75-role-switcher` |
| Parent epic | `SCRUM-7` — User authorisation and authentication |
| Sprint | *not recorded in the ticket text supplied* |
| Story point estimate | *not recorded in the ticket text supplied* |
| Priority | Medium (both) |

**User story (verbatim, SCRUM-74):**

> As a user with more than one assigned role, I want to see all roles assigned to me in a dropdown on the nav bar, so that I know which roles I can act as.

**Acceptance criteria (verbatim from Jira, SCRUM-74):**

> * Dropdown appears only if the user has 2 or more assigned roles, single-role users see no dropdown
> * Dropdown lists exactly the roles assigned to that user (from user_roles), nothing else
> * Dropdown shows a human-readable label for each role (e.g. "Venue Staff", not the raw enum value)
>
> Depends on: user_roles schema migration

**User story (verbatim, SCRUM-75):**

> As a user with more than one assigned role, I want to select one role from the dropdown, so that the system treats that role as my current context.

**Acceptance criteria (verbatim from Jira, SCRUM-75):**

> * Selecting a role updates my active role for this session (calls set_active_role RPC, which validates I actually hold that role)
> * After selecting, I am taken to that role's dashboard/homepage
> * My active role persists across page reloads within the session, until I log out or select a different role
> * Attempting to set an active role I do not hold is rejected
>
> Depends on: SCRUM-74, user_roles + active_role schema migration (see SCRUM RBAC implementation plan)

#### How the implementation maps to the ticket

**First concrete implementation of ACC-R4.** `REQUIREMENTS.md` had carried ACC-R4 (an account may hold two roles, QA2-24) as **[Team decision, pending]** since Session 2, sketching a `profile_roles` table and "union-of-permissions" as one possible direction, and explicitly deferring the actual design to "when a story needs it" (§9 Q10). These two tickets are that story; ACC-R4 and §9 Q10 are updated in this branch to record what was actually built, which differs from that sketch in two ways worth calling out for anyone tracing requirement → code:

1. **Table name.** The ticket text and REQUIREMENTS.md's sketch each independently guessed a name (`user_roles` per the ticket, `profile_roles` per the sketch) for a table that didn't exist yet. Built as `user_roles`, matching the ticket's literal wording since that's the concrete spec being implemented.
2. **Active-role model.** Neither the ticket's "RPC" wording nor REQUIREMENTS.md's "union-of-permissions" sketch is what got built. Brainstormed with the developer: the chosen model is **session-scoped active-role switching** — closer to Postgres's own `SET ROLE` or AWS assume-role than either prior sketch — because the ticket explicitly asks for a *current context* the user picks, not a permanent blend of both roles' permissions. `profiles.role` is untouched in meaning (an account's default role for a brand-new session); a new `session_active_roles` table, keyed by the JWT's `session_id` claim (a standard claim on every Supabase access token), holds whichever role a given login session switched into. This makes switching roles on one device provably not affect another concurrent session for the same account — verified below by logging in twice and switching only one session.
3. **"RPC" implemented as a FastAPI endpoint, not a Postgres function.** `POST /auth/active-role` does the membership check and the write in `modules/auth/service.py`, via the existing service-role Supabase client — consistent with this codebase's baseline that the API, not the database, is the policy-enforcement point (root `AGENTS.md`, "Security baseline"). A literal Postgres RPC function was considered and rejected: it would be the only piece of business logic in the whole backend living in SQL rather than Python, for no behavioural benefit here.

**Granting a second role is out of scope**, confirmed with the developer: no grant endpoint or admin UI exists. A system admin inserts directly into `user_roles` via SQL, the same way internal staff roles are already provisioned outside sign-up (ACC-R3). One seeded test account, `coordinator@connectsphere.dev`, is given `venue_staff` in addition to its default `event_coordinator` in `supabase/seed.sql`, so the feature is exercisable immediately after seeding without a manual grant step.

What was actually built:

1. **Schema** — `supabase/migrations/20260917000000_role_switching.sql`: `user_roles` (roles an account holds, backfilled from every existing `profiles.role`), `session_active_roles` (the active role per session, FK'd to `auth.sessions`), and an updated `handle_new_user()` that seeds `user_roles` for new signups. RLS on both tables mirrors `profiles`' select-own-or-internal-staff pattern; neither has a write policy for `authenticated`, since only the backend's service-role client writes them.
2. **Backend** — `core/security.py` gains `resolve_active_role()` and now derives `CurrentUser.role`/`session_id` from the session's active role, not the raw profile column, so `require_roles()` and every existing guard automatically check the *session's* role. `modules/auth/service.py` gains `get_roles()` and `set_active_role()`; `modules/auth/schemas.py`'s `ProfileResponse` gains `roles`; a new `POST /auth/active-role` endpoint and `RoleNotAssignedError` (403) round it out.
3. **Frontend** — `stores/auth.js` gains `roles`, `hasMultipleRoles`, `setActiveRole()`, and the `ROLE_LABELS` map (moved out of `ProfileView.vue`, which now imports it instead of duplicating it). `Nav.vue` renders a `BauhausSelect`-based switcher, shown only when `hasMultipleRoles`, that calls `setActiveRole` then routes to the new `dashboardPath` — mirroring the existing `handleLogout` pattern.
4. **Documentation correction, not a code rename.** `IMPLEMENTATION_MAP.md` and (in an earlier, unedited entry above) this file both described a `BauhausNavbar` component with a role badge that was never actually built — the real file is `Nav.vue`, with no role badge, before this branch. Since the rename wasn't needed by either ticket's acceptance criteria and isn't a prerequisite for the feature, per this project's scope-discipline rule it's corrected in `IMPLEMENTATION_MAP.md`'s current-state description rather than by renaming working code.

#### Verification

- **Automated:** `pytest` 84/84 (backend, including new coverage for `resolve_active_role`, session-scoped `require_roles`, and `POST /auth/active-role`'s success/reject/unauthenticated paths); `npm test` 58/58 (frontend, including the new `Nav.vue` and `stores/auth.js` role-switching specs). Both suites mock the Supabase client seam per `backend/AGENTS.md` and `frontend/AGENTS.md` — the items below are what actually exercised the real system.
- **Real database:** migration applied to the live project (`vuiryrzzyfecjqftwicj`) via the Supabase MCP; `get_advisors` shows no new security findings (the one pre-existing WARN, leaked-password protection, predates this branch) and only the expected "new table, no traffic yet" INFO-level unused-index notices.
- **Real backend, real Supabase session:** logged in as `coordinator@connectsphere.dev` against the running API (not mocked) — login returns `role: event_coordinator`, `roles: [event_coordinator, venue_staff]`; `POST /auth/active-role {"role":"venue_staff"}` returns 200 and `GET /auth/me` immediately reflects `role: venue_staff`; `POST /auth/active-role {"role":"attendee"}` (a role the account doesn't hold) returns 403.
- **Real session isolation:** logged in as the same account a second time (a second, independent Supabase session) — the second session's `role` came back `event_coordinator` (the default), unaffected by the first session's switch to `venue_staff`, which a follow-up `/auth/me` on the first session's token confirmed was still `venue_staff`. This is the concrete proof that the design is session-scoped, not account-wide.
- **Real browser:** Chrome via Playwright against the Vite dev server and the real backend, logged in as `coordinator@connectsphere.dev` — the "Acting as" dropdown appears with both roles correctly labelled, selecting "Venue Staff" redirects to `/dashboard/venue-staff` and updates the dropdown, a full page reload keeps `venue_staff` active (DB-backed persistence, not just local state), and no console errors. Logged in separately as `attendee@connectsphere.dev` (single role) — no dropdown renders, and no console errors.
- **A test-infrastructure bug this caught, not a product bug:** the first browser attempt hit a stale, Dockerized copy of the frontend that happened to be listening on the same port (`localhost:5173`) as the dev server this repo's backend CORS config expects, serving code from before this branch's changes. Verification was redone against a freshly started dev server on a different port with the backend's CORS origins extended to match, which is what the results above reflect.

**Not verified:** the manual-grant workflow itself (a system admin running SQL directly against `user_roles`) wasn't exercised through any tooling, since none exists yet by design — the seed script's insert was used as the equivalent for setting up the verification account. Multi-tab isolation *within the same browser* (as opposed to two separate `TestClient`/browser-context sessions, which was tested) was not separately checked, though it follows from the same `session_id`-keyed mechanism.

### 4.7. SCRUM-74/75 — code review follow-up (pre-merge)

An external code review of the PR (commit range `5c83e19..2c70b48`) found two critical and two important issues before merge. Each was verified against the live system before being accepted as real, per this project's "verify before implementing" review-reception convention — one flagged issue (a claim that `ProfileView.vue`/the commit message said the profile page lists all roles) didn't match what was actually written, and one (a stale "Last updated" date) was already fixed; both were pushed back on rather than blindly applied. What was fixed:

1. **Seed script left staff accounts holding only `attendee` in `user_roles` on a fresh database (critical).** `handle_new_user()` only accepts `event_organiser`/`attendee` from sign-up metadata (D2), so every staff account's insert-time trigger grants it `attendee` in `user_roles`; the seed loop's `update profiles set role = ...` corrected `profiles.role` but never touched `user_roles` to match. On a clean `supabase db reset`, `coordinator@connectsphere.dev` would end up holding `{attendee, venue_staff}` — no `event_coordinator` at all, unable to switch back to its own default role. It passed the original manual verification only because the remote database already had correct `profiles.role` values before the SCRUM-74/75 backfill migration ran, masking the bug. **Reproduced and fixed against the live database**: simulated a fresh signup of a `venue_staff` account through the real trigger, confirmed `user_roles` held only `attendee`, applied the corrected seed logic (remove the stray `attendee` grant, insert the real role), confirmed `user_roles` then held `venue_staff`, and cleaned up the test account. `supabase/seed.sql` now does this correction for every seeded account.
2. **Selecting the nav dropdown's empty placeholder option crashed with an unhandled rejection and desynced the visible selection (critical).** `BauhausSelect` always renders an empty placeholder option; selecting it sent `role: ""` to `POST /auth/active-role`, which pydantic rejects with 422, and `Nav.vue`'s `handleRoleChange` had no error handling. Fixed with a guard (ignore an empty or already-active selection) and a try/catch. Reproducing this in a Vitest spec surfaced a second-order issue: since the switch never actually changes `authStore.role` on a no-op/rejection, Vue's plain `:value` binding (not `v-model`) has nothing to diff and won't reset the native `<select>`'s displayed value back on its own — the browser had already changed it imperatively before the handler ran. Fixed by bumping a `:key` on the switcher on every change attempt, forcing a remount that reapplies the current role.
3. **`session_active_roles` had no link back to `user_roles`, so revoking a role didn't end an active session using it (important).** An admin revoking a role via direct SQL left any session already acting as that role valid until it expired or logged out. Fixed with a composite FK (`session_active_roles (profile_id, role) references user_roles (profile_id, role) on delete cascade`) in a new migration, `20260918000000_session_active_roles_fk_user_roles.sql`, plus a covering index (the security/performance advisors flagged the FK as unindexed until this was added). **Verified against the live database**: inserted a `session_active_roles` row for a real session, deleted the matching `user_roles` row directly, and confirmed the `session_active_roles` row was cascaded away.
4. **`REQUIREMENTS.md` ACC-R4 overstated what RLS enforces (important).** The original wording claimed `require_roles`/RLS both read the session's active role. `private.current_user_role()` (used in RLS policies) reads `profiles.role` directly — it has no session context. Corrected the wording to say the API is the active-role enforcement point and RLS still checks the account's default role, which is an intentional gap (RLS is a defense-in-depth backstop per the root security baseline, not the primary enforcement path) rather than something to fix by threading `session_id` into Postgres session context for this story.
5. **`_token_response` decoded the fresh token without outage handling or JWKS caching (important).** It called `.get_claims()` directly on the per-login `auth_client`, uncaught — a JWKS-fetch outage during that call would have surfaced as an unhandled 500 instead of `AuthServiceUnavailableError` (503), and a brand-new client per login never benefits from the shared anon client's cached JWKS. Switched to reusing `core.security.decode_access_token`. This required reworking the login/refresh test mocks: `decode_access_token` calls `core.security`'s own `get_supabase_anon_client`, a different bound name than `auth_service_module.get_supabase_anon_client`, so both needed patching. Added `TestLogin`/`TestRefresh` cases for the outage path.
6. **Multi-role users couldn't see all their roles on the profile page (important, added at the developer's request — not required by either ticket's acceptance criteria).** `ProfileView.vue` only ever showed the active role badge. Added an "All Roles" section, shown only via `authStore.hasMultipleRoles`, listing every held role with its label. Opened retroactively as `SCRUM-78` (see `/subtask`'s new-story convention) so this work has its own Jira record rather than sitting undocumented inside a SCRUM-74/75 commit; PR #12's title and description were updated to reference it, but neither the branch name nor any existing commit message were rewritten, since both back an already-open PR.
7. **Minor cleanups**: `set_active_role` no longer re-fetches `profiles`/`session_active_roles`/`user_roles` it had already just read or written, since `CurrentUser` already carries every other profile field; `get_roles()` now orders its query so the dropdown's option order is stable across requests; `backend/tests/conftest.py`'s single-shape table mock (which coincidentally worked because a `profiles` row and a `session_active_roles` row both happen to have a `role` key) was replaced with the same table-name-routed mock `test_auth.py` already used, moved into `conftest.py` so both share one implementation.

#### Verification

- `pytest` 86/86 (backend, +2 from the outage-handling tests), `npm test` 63/63 (frontend, +5 from the Nav.vue guard/reject and new ProfileView specs) — all written test-first per this project's TDD rule, each watched red before the fix.
- Seed-script fix and the composite FK's cascade behaviour were each reproduced and verified directly against the live Supabase project (not mocked), as described above, then cleaned up.
- `get_advisors` re-run after the new migration: the FK's "unindexed foreign key" finding is gone; no new security findings.

### 4.8. SCRUM-74/75 — second code review round (pre-merge)

A second review pass before merging PR #12 (this project's own multi-agent `/code-review`) found 4 more real issues on top of §4.7's round. Each was verified against the actual code or the live database before being accepted — this review round's own orchestrator hit Claude's session rate limit partway through and never finished its synthesis/verification step, so its raw per-angle findings were verified independently rather than trusted as-is (one of its five angles never reported back at all).

1. **`resolve_active_role`'s fallback never re-checked that the account's *default* role was still held (high severity).** §4.7 item 3 added a FK so revoking an *actively switched* session's role invalidates it immediately — but a session that never switched (the common case) falls back straight to `profiles.role`, and nothing re-verified that role was still in `user_roles`. A system admin revoking someone's default role (`delete from user_roles where profile_id=x and role=profiles.role`) left it granted indefinitely for every un-switched session, undermining the exact invariant §4.7 set out to close, just for the more common path. **Fixed and verified live**: added a deferred composite FK, `profiles (id, role) references user_roles (profile_id, role)` (`20260919000000_profiles_role_requires_user_roles_membership.sql`), so `profiles.role` itself can never point at a role the account no longer holds. Verified against the real database: a single-statement revoke of a held default role is now rejected (`23503 foreign key violation`); the correct two-step admin workflow (update `profiles.role` to another held role, then delete the old grant, in one transaction) still succeeds, since the FK is deferred to commit time.
2. **`set_active_role` had an unhandled TOCTOU race against the new FK from §4.7, and a lost-update race between concurrent switches.** The membership check (`get_roles`) and the `session_active_roles` write were two separate round trips: a role revoked in between the two made the write raise an unhandled `postgrest.exceptions.APIError` (foreign key violation) — a 500, not the 403 the check was supposed to guarantee. Separately, two near-simultaneous switches for the same session (e.g. two tabs) could race the write, and the response always claimed *its own* requested role was now active regardless of which write actually won. **Fixed**: the FK violation is now caught and translated to `RoleNotAssignedError` (403); the response now reads back the actual `session_active_roles` row after the write instead of assuming the request's role won, so a losing request correctly reports what's really active.
3. **`_token_response` indexed the `session_id` claim directly (`claims["session_id"]`), unlike the equivalent lookup in `get_current_user` which uses `.get()` with an explicit check.** A token ever issued without that claim would raise an unhandled `KeyError` (500) instead of the typed `InvalidOrExpiredTokenError` (401) used everywhere else in this module. Fixed for consistency, and as defensive coding against a claim this codebase doesn't control the issuance of.
4. **The nav role switcher's remount-forcing key bump (§4.7 item 2's fix) ran unconditionally, including on a *successful* switch.** Since it fired synchronously before the `await` on the network call, Vue's reactivity flush ran before the real request resolved, so the switcher visibly reverted to the old role and then jumped to the new one on every successful switch, not just the rejected/no-op cases the fix was meant for. The code comment attributing the underlying issue to "`:value` vs `v-model`" was also inaccurate — `Nav.vue`'s own binding to `BauhausSelect` *is* what `v-model` desugars to; the real gap is that `BauhausSelect`'s native `<select>` binds its value with a plain, non-`v-model` `:value`/`@change` pair internally. Fixed by only bumping the key on the no-op and rejected paths (where `authStore.role` doesn't change and nothing else would correct the DOM), never on success (where it already changes for real); corrected the comment to describe the actual mechanism.
5. **Minor**: `backend/tests/conftest.py`'s shared table mock had a non-atomic check-then-act on its per-table-name cache, exercised by 4 concurrent threads in the existing event-loop test — currently harmless since every build for a given table name is equivalent, but latent. Added a lock. Consolidated `get_current_user` and `_fetch_profile`'s duplicated "load profile, resolve active role" logic into one shared `core.security.load_profile_with_active_role`, a pure refactor with no behaviour change. Labelled the self-approval-allowed default in `REQUIREMENTS.md` §9 as `[Assumption]`, per this project's own convention for unanswered customer questions, which it had been missing.

Two findings from the same review round were investigated and not treated as bugs: collapsing the nav sidebar fully hides the role switcher (other links just drop their text label) — accepted as a reasonable current-scope limitation rather than designing a new icon-only switcher UI, since expanding the sidebar is one click away, not a lost capability. RLS's `private.current_user_role()` reading `profiles.role` rather than the session's active role was re-raised as "not root-caused" — already correctly documented in `REQUIREMENTS.md` ACC-R4 as an intentional defense-in-depth gap per this project's security baseline (root `AGENTS.md`), not a new concern.

#### Verification

- `pytest` 89/89 (backend, +3 from the TOCTOU/lost-update-race and missing-session_id tests), `npm test` 64/64 (frontend, +1 from the no-flicker-on-success test) — test-first, each watched red before the fix.
- The new `profiles`→`user_roles` FK was verified directly against the live database: reproduced the single-statement revoke rejection, then the correct two-step transaction succeeding, then restored the seeded double-hat test account to its original state.
- `get_advisors` re-run after the new migration: the new FK's "unindexed foreign key" finding is gone; no new security findings.

### 4.9. SCRUM-70 — Venue Staff dashboard (exact Jira record)

| Field | Value |
|---|---|
| Issue key | `SCRUM-70` |
| Summary | Venue Staff dashboard |
| Issue type | Story |
| Status | In progress (branch `feature/scrum-70-venue-staff-dashboard`) |
| Parent epic | `SCRUM-69` — Role dashboards |
| Sprint | Sprint 1 |
| Story point estimate | — |
| Priority | P2 |

**User story (verbatim):**

> As a Venue Staff, I want to see a dashboard of the venues I'm in charge of when I log in, so that I can quickly see what needs my attention without navigating through multiple pages.

**Acceptance criteria (verbatim from Jira):**

> On successful login, Venue Staff are routed directly to their dashboard
>
> Dashboard lists all venues the Venue Staff member manages, with each venue's current status (active/blocked) shown at a glance
>
> Dashboard surfaces a count or list of pending booking requests awaiting my decision, across all my venues
>
> Dashboard surfaces any active or upcoming blocks I've set
>
> Selecting a venue or a pending request from the dashboard navigates directly to its full details

#### How the implementation maps to the ticket

**"the venues I'm in charge of" resolves to every venue.** The ticket is written as though staff own a subset, but staff-to-venue allocation is not tracked anywhere in the system and the customer described venue staff as a pool (AUTH-R5, QA-44). `REQUIREMENTS.md` §6.21 and `PROJECT_REVIEW.md` §B4 had already settled this reading; SCRUM-70 is where it becomes visible, so the panel is headed **"All venues"** rather than "My venues" and carries a line saying why. Confirmed with the customer-side decision-maker before building. The same applies to AC3's "across all my venues" and AC4's "blocks I've set" — there is no per-staff attribution on `venue_blocks` either, so the dashboard shows every block and says so.

**AC1 needed no work.** `ROLE_DASHBOARD_ROUTES.venue_staff` in `stores/auth.js` already routes venue staff to `/dashboard/venue-staff`, used by both `LoginView.vue` and the router guard.

**AC2, AC3 and AC4 are backed by real data** — unlike SCRUM-72, which had to ship empty states because the `events` module does not exist. `venues`, `venue_blocks` and `venue_bookings` all exist and are seeded, so this dashboard invents nothing. It is the first of the four remaining shells to clear **defect D8**.

**AC5 is honest about what exists.** A venue row opens `/venues/:id`, which is real. A pending request opens `/bookings/:id`, which is a deliberate placeholder: the request detail view and the approve/reject decision are SCRUM-19/20 and have neither an endpoint nor a design. The route and link are real so those stories fill the page in without touching the dashboard, and the placeholder names them rather than implying the data is missing.

**Layout.** The customer supplied a reference screenshot — a 2×2 grid of stat tiles beside a tall panel, two list panels underneath. The information architecture is kept; the visual treatment is not. The reference's rounded corners and soft shadows contradict the Bauhaus system (`frontend/AGENTS.md`), and its sparklines and "+12% vs last month" trend figures are precisely the fabricated-metric problem D8 exists to fix, so they are absent. The chart panel became the calendar the customer asked for instead.

#### What was actually built

1. **`GET /venues/dashboard/venue-staff`** (`modules/venues/{router,service,repository,schemas}.py`) — `venue_staff` only. Returns `generated_at`, `venues`, `pending_holds` (oldest first), `re_review_bookings` and `blocks`. `event_coordinator` is excluded although it can read the rest of the venues module: this is a staff work queue.
2. **No server-side counts.** Each list is complete, so a count beside it would be a second source of truth that could disagree with the list rendered from it. The SPA derives its tiles from the lists.
3. **Cross-venue repository reads** (`list_all_upcoming_blocks`, `list_all_upcoming_bookings`). The existing per-venue helpers fetch every row and drop past ones in Python; across eight venues that becomes a full-table scan per page load, so the cut-off moved into Postgres as an open-ended `[since,)` range against the existing GiST index. `Period` requires both ends and cannot express that literal, hence a separate `_open_ended_literal`.
4. **`event_name` is declared and always `null`.** There is no `events` table, so `venue_bookings.event_id` has nothing to join to. The field exists now so SCRUM-8/19 fill it without an SPA change; the SPA falls back to a short id and never invents a name.
5. **Only `held` and `re_review` are fetched.** An approved booking is settled work and belongs on the per-venue availability calendar of §6.9 (SCRUM-16). The calendar legend says so, so the omission does not read as a gap.
6. **A hand-rolled calendar with month and week views** (`features/venues/calendar.js`, `components/venues/VenueCalendar.vue`). No dependency was added; the repo has no chart or date library and `frontend/AGENTS.md` forbids introducing one casually. The month view draws each item as a bar spanning the days it covers, labelled with its venue; the week view gives each day a column and lists the items with their times. Both grids emit the same cell shape, so placement, sorting and tone rules are written once, and the bar packing (`layoutWeekSegments`) is a greedy interval colouring that uses the fewest lanes a week needs.
7. **An .ics export** (`features/venues/ics.js`), written by hand against RFC 5545 rather than adding a dependency: UTC stamps, CRLF line endings, 75-octet folding measured in octets so a multi-byte venue name is never split, and `;`/`,`/`\` escaping. It exports the whole payload rather than the month on screen, and gives each entry a stable UID so re-importing updates instead of duplicating. Verified against the live project's data, where a seeded block's notes contain a semicolon.
8. **`stores/venues.js` moved to `features/venues/venueSearchStore.js`**, with `toSingaporeIso` and the fixed +08:00 offset extracted to `features/venues/singaporeTime.js`. `frontend/AGENTS.md` has said since SCRUM-39 that this should happen the next time a story changes the store; adding a second venues store is that moment. Committed separately so the rename stays reviewable.
9. **The seed gains a second hold and a re-review row**, both clear of the 10 Oct window the search cases depend on, plus explicit `created_at` values — oldest-first ordering cannot be demonstrated by rows sharing one insert timestamp.

#### Two rules worth knowing before touching this code

**Half-open ranges map onto day cells via `endsAt − 1ms`.** The last instant inside `[start, end)` is `end − ε`, so the last day a range marks is the day of `end - 1ms`. A block ending exactly at midnight therefore stops on the previous day with no special case and no branch — which is what §6.14 and CAL-R2 ask for. The seeded blocks prove it both ways: 1–15 Oct marks through the 14th, 20–22 Oct through the 21st.

**Never slice a raw ISO string to get a day.** `"2026-10-10T16:00:00Z"` and `"2026-10-11T00:00:00+08:00"` are the same instant; slicing them yields different days, so which day you got would depend on how the backend happened to serialise the value. `singaporeDayKey` works from the instant and a fixed +08:00 offset, exact because Singapore has never observed daylight saving.

#### Two decisions the calendar makes on the user's behalf

**It opens on the first month that has something in it.** Today is September and every seeded item is in October; opening on an empty September would look like a dashboard with nothing on it. The month is named in the panel header, and a **Today** control beside the month arrows returns to the current month, disabled while already there. An earlier revision explained this in a banner above the grid; the customer found it noise, and the header plus the Today control carry the same information in less space.

**It cannot page backwards past the current month.** The payload is upcoming-only, so every earlier month is guaranteed empty — offering them would render a gap in the data as though it were an answer.

#### One bug only a real database could surface

`venue_bookings` has **two** foreign keys to `venues`: `venue_id`, and the `suggested_venue_id` a rejection may carry (§6.13). A bare `venues(name)` embed is therefore ambiguous, and PostgREST rejects the entire query with `PGRST201` rather than picking one. Every mocked test passed; the first real call 500'd. The embed now names its constraint (`venues!venue_bookings_venue_id_fkey(name)`), with a regression test asserting on the `select` string. `venue_blocks` has a single FK and stays unqualified.

#### Verification

- `pytest` 127/127 (+41), `npm test` 146/146 (+75). The frontend additions are concentrated in `features/venues/__tests__/calendar.spec.js`, where the half-open boundary, the two ISO serialisations of one instant, and the Monday-first grid arithmetic are each pinned separately.
- **Exercised against the live Supabase project**, which is how the PGRST201 bug was found: `coordinator@connectsphere.dev` gets **403**, the same account gets **200** after switching active role to Venue Staff, and the payload returns 8 venues, 1 pending hold and 3 blocks with `venue_name` populated and `event_name` null.
- `npm run build` clean; the new route registers ahead of `/venues/{venue_id}` as intended.

#### Not verified

- **No browser screenshot was taken.** The logic, the HTTP contract and the production build are verified, but nobody has yet looked at the rendered page in a browser at desktop or mobile width, or opened it as a disallowed role. `frontend/AGENTS.md` requires that check; it remains outstanding.
- **The new seed rows are not in the live database.** The hosted project still carries the old seed, so the re-review tile reads 0 there rather than 1. `supabase db push`/`db reset` has not been run — no Supabase CLI was available in the environment where this was built.
- The re-review path itself is untested end to end, because nothing can yet *put* a booking into `re_review` — that arrives with SCRUM-19/20.
- `waitingDays` was checked against fixed clocks in tests, not across a real day boundary.

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
| "How does venue search decide what to show?" | `backend/app/modules/venues/search.py` (pure rules) → `repository.py` (Supabase reads) → `router.py`; SPA in `frontend/src/features/venues/` and `views/venues/` |
| "Why can't two events book the same venue?" | `venue_bookings_no_overlap` in `supabase/migrations/20260915090000_venues_catalogue_and_availability.sql` (DB-1), checked by `supabase/verification/venue_schema_checks.sql` |
| "What do Block, Hold, Availability, Suitability mean here?" | `CONTEXT.md` at the repo root |
| "What exactly does story SCRUM-XX require, verbatim?" | §4's entry for that story (each entry is self-contained and quotes Jira verbatim) |
| "What has been built so far, across all sprints?" | Skim §4's entries in order — it's the running log of every completed story |
| "What's in scope for the whole first release?" | §3 of this document (20 features) |
| "What's out of scope entirely (for now)?" | Anything in the customer briefing not listed in §3 — e.g. client management, recurring events, waiting lists, venue/registration reports |
| "What's next?" | The next-highest-priority story in the product backlog under whichever epic is next up — check the backlog/Jira board, not this document, for current priority |
| "I just finished a story — what do I update here?" | Add a new `###` entry to §4 using its template; update the "as of the most recent entry..." sentence at the end of §3 if the story changes what's implemented for one of the 20 features |
