# ConnectSphere — Build Log

**What each story, fix and enabler actually built, in the order it landed.** Append-only.

This is the requirement → code → test trail the course rubric rewards. Each entry quotes its Jira issue verbatim and records how the ticket was interpreted, what was built, and how it was verified.

- It was §4 of `docs/SCENARIO.md` until 2026-09-28. **Entries keep their `4.N` numbers**, so a citation like "SCENARIO §4.17" in Jira or an old commit is the same entry as "BUILD_LOG §4.17" here. Number 4.9 was used twice: the first 4.9 is SCRUM-70, the second SCRUM-8.
- Inside entries, a bare "§1"–"§3" or "§5"–"§7" means [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md); a bare "§4.N" means this file.
- For what exists *now*, see [`IMPLEMENTATION_MAP.md`](IMPLEMENTATION_MAP.md); for what the system *should* do, [`REQUIREMENTS.md`](REQUIREMENTS.md).

## How to add an entry

When a story is completed, copy the template below, fill it in from the Jira issue (don't paraphrase the user story or acceptance criteria — quote them verbatim, the same way SCRUM-48's entry does), and add it as a new `###` subsection *after* the most recent entry, so the log reads chronologically. Do not delete or rewrite prior entries when requirements change later — instead, add a new entry for the story that changes them, and note in that new entry which earlier entry/behaviour it supersedes. This keeps the log an honest history of what was built and when, which is exactly the kind of requirement → code traceability the course rubric ([`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) §1) rewards.

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

## Entries

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
- **"Based on the Event Organiser's information"** means the event request's fields (date/time, pax, layout, facilities, accessibility). At the time this venue-search entry was implemented, `events` did not exist, so the API took those as explicit query parameters; SCRUM-8 now provides the event request and its detail workflow.
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
### 4.9. SCRUM-8 — Event request creation, drafts, submission, and timezone support

SCRUM-8 is implemented on `feature/scrum-8-event-request`, pending merge. Organisers can create minimal drafts, resume and update their own drafts, discard never-submitted drafts, submit validated requests, and retrieve submitted request details. Submission changes the request to `under_review`; coordinator assignment, reassignment, and notifications are explicitly outside SCRUM-8 and remain tracked under SCRUM-12 / SCRUM-68.

The event request workflow now treats the event's local timezone as explicit data rather than assuming Singapore for every request. Organisers choose an IANA timezone from the supported Southeast Asia list, the frontend converts local date/time input to timezone-aware UTC ISO instants, and the backend validates the event and registration calendar dates in that selected timezone. PostgreSQL stores the instants in `timestamptz` columns and stores the IANA identifier in `events.event_timezone`, defaulting existing events to `Asia/Singapore`.

The submitted request detail view converts returned UTC instants back into the event timezone and labels the timezone beside the schedule. Venue catalogue records still have no timezone field and remain Singapore-specific; extending venue operating hours and venue display to multiple countries requires a separate venue-catalogue migration.

#### Verification

- TDD regression tests were red before implementation for Bangkok payload conversion, response normalization, and API timezone persistence.
- `pytest`: 114 passing.
- `npm test -- --run`: 85 passing across 13 files.
- `npm run build`: passed.
- Editor diagnostics and `git diff --check`: passed.

### 4.10. SCRUM-67 — View venue details (exact Jira record)

| Field | Value |
|---|---|
| Issue key | `SCRUM-67` |
| Summary | View venue details |
| Issue type | Story |
| Parent epic | `SCRUM-15` — Venue catalogue |
| Status | In progress at time of writing (`feature/scrum-67-view-venue-details`) |

**User story (verbatim, as supplied by the developer):**

> As a Venue Staff, I want to view the full details of a venue, so that I can verify current information and plan around it.

**Acceptance criteria (verbatim, as supplied by the developer):**

> Can view a single venue's full profile in one place: location, capacity, facilities, accessibility, supported room layouts, operating hours, and setup/turnaround time
>
> Can view when the profile was last updated and by whom
>
> Can view a summary of the venue's upcoming confirmed and tentative bookings from this profile

*(The Jira MCP was not available in this session, so the story and criteria were taken from the developer's message rather than fetched from the ticket.)*

#### How the implementation maps to the ticket

SCRUM-39 already shipped a venue detail page, so this story is mostly about the three things it did **not** answer. Each needed a decision the ticket left implicit:

1. **"setup/turnaround time" (AC1).** The catalogue has no such column, and adding one would have invented a business rule. The customer already answered the question: turnaround is **zero** (QA-28, QA-82, QA-103), which is why DB-1 uses half-open ranges and back-to-back bookings are allowed (§6.14). So the profile *states* the rule rather than storing a per-venue figure — `TURNAROUND_MINUTES` in `backend/app/modules/venues/schemas.py`, served as `turnaround_minutes`. Recorded as **VC-R5** in REQUIREMENTS §6.8. The SPA reads the number off the contract, so if the customer ever asks for a real buffer it changes in one place instead of in a template.

2. **"last updated and by whom" (AC2).** `venues.updated_at` already existed (SCRUM-39's trigger); nothing recorded the editor. Migration `20260920000000_venues_last_updated_by.sql` adds `venues.updated_by → profiles(id) on delete set null`. It is deliberately a **last-writer stamp, not an audit trail** — the per-field change history VC-R3 asks for is §6.7 / SCRUM-14 and wants its own table, and pre-empting that design here would have been the wrong shape. No trigger fills the column: every API write uses the secret key, so Postgres cannot see which signed-in user the request is acting for; the venue edit path (SCRUM-63/64) will set it from the verified JWT. Until then it is null everywhere except the seed, and the UI says **"Not recorded"** rather than naming anyone. Recorded as **VC-R4**.

3. **"confirmed and tentative bookings" (AC3).** `CONTEXT.md` fixes the vocabulary: an **approved** booking is the confirmed one, a **hold** is the tentative one. `re_review` is neither — it is a settled booking reopened by a significant change (§6.19) — so it gets its own group rather than being folded into either, which would have misstated what is actually agreed. All three occupy the venue, so all three constrain planning. Recorded as **VC-R6**. Each row names its event: the bookings already carried `event_id`, and `public.events` exists since SCRUM-8, so `events.service.names_by_id` resolves the names. `venue_bookings.event_id` still has no foreign key to `events`, so a PostgREST embed is not available and the lookup is a second query — skipped entirely when the venue has no bookings.

Following `VenueStaffDashboard`'s precedent, the API returns **one flat list with a status on each row and no server-side counts**; grouping and counting happen in `features/venues/venueProfile.js`, so a count can never disagree with the list rendered beside it.

What was actually built:

1. `supabase/migrations/20260920000000_venues_last_updated_by.sql` — `venues.updated_by`, its named `venues_updated_by_fkey` constraint (the profile embeds `profiles` through it) and a covering index. `supabase/seed.sql` stamps the seeded catalogue as edited by the venue-staff account, guarded on `updated_by is null` so re-seeding does not keep bumping `updated_at`.
2. `backend/app/modules/venues/schemas.py` — `Editor`, `VenueProfile` (the catalogue fields plus the audit stamp), `TURNAROUND_MINUTES`, and `event_name` moved onto `BookingSummary` so `VenueStaffBooking` inherits it instead of redeclaring it. The audit fields are deliberately **not** on `VenueSummary`, which is also a search result and a dashboard row.
3. `backend/app/modules/venues/repository.py` — `_VENUE_PROFILE_COLUMNS` with the `profiles!venues_updated_by_fkey(id, full_name)` embed; `_to_one_embed` generalised out of `_embedded_venue_name`, and `_to_editor`, which falls back to the bare `updated_by` id when the embed is empty.
4. `backend/app/modules/events/{repository,service}.py` — `list_event_names` / `names_by_id`, the events module's answer to "what is this event called?" for a module that only holds an `event_id`.
5. `backend/app/modules/venues/service.py` — `get_venue` now resolves booking event names in one lookup for the whole list.
6. `frontend/src/features/venues/venueProfile.js` — `groupUpcomingBookings`, `formatTurnaround`, `lastEditorName`, `BOOKING_GROUPS`. An unrecognised booking status lands in a trailing "Other" group rather than being dropped: a booking nobody can see is the one way this screen could actively mislead someone planning around the venue.
7. `frontend/src/views/venues/VenueDetailView.vue` — last-updated line in the header, a Turnaround row beside capacity and hours, and the old "Upcoming unavailability" card split into **Upcoming bookings** (grouped, counted, each naming its event) and **Blocks**.

#### Verification

- `pytest`: 162 passing (10 new, written red first — the SCRUM-67 class failed to import before `Editor`/`VenueProfile` existed).
- `npm test`: 273 passing across 20 files (29 in `venueProfile.spec.js`, 20 view tests, 5 in `VenueLayoutDiagram.spec.js`).
- `npm run build`: passing — see D9 below, which it was failing on beforehand.
- Against the live project (`vuiryrzzyfecjqftwicj`): login, `GET /venues`, `GET /venues/dashboard/venue-staff` all 200; the `events?select=id,name&id=in.(…)` read behind `names_by_id` returns the two seeded events and silently skips an id with no row.
- **Verified against live after the migration landed:** `GET /venues/{id}` returns 200 with CORS headers; Seminar Room 1 shows its tentative booking named "Seed Seminar Event", Auditorium A its confirmed "Seed Auditorium Event", Boardroom Orchid an empty summary, Heritage Hall a renovation block and no bookings; `turnaround_minutes` is 0 and `photos` is `[]`.
- **Not verified:** the page in a real browser (no browser automation in this session — the Vitest specs assert rendered text in jsdom, which is not the same as a visual check), and AC2's "by whom" against live, because `venues.updated_by` is null on all 8 rows: the seed's stamping `update` is a write to the shared project and was blocked here. Run it, then re-check.

#### Follow-up in the same story: slideshow and tabs

The developer asked for a photo slideshow at the top and the detail sections behind tabs. Neither is in SCRUM-67's acceptance criteria, but the tabs are a presentation choice about AC1's content, and the slideshow needed a decision rather than a build:

- **There is no venue photo data anywhere** — no column on `venues`, no `venue_photos` table, zero storage buckets on the project, and no mention of photos in REQUIREMENTS or CONTEXT. Stock imagery was rejected: this page's stated purpose is letting staff *verify current information*, so invented photos are the same class of problem as the fabricated dashboard metrics in PROJECT_REVIEW D8. The chosen route was contract-first — `VenueDetail.photos` is declared and always `[]` — and the carousel was then filled from data we *do* hold: **one schematic per layout the venue supports**, drawn from `venue_layouts`. That keeps the slot useful for planning without inventing anything, and real photos lead the carousel the day they exist. The honesty guard is the labelling: the system holds no venue geometry, so every schematic slide says "Schematic arrangement — not this room's floor plan" and repeats it in the SVG `<title>` for screen readers, and a slide whose capacity is the venue-wide figure rather than one measured for that layout (VS-R6) says that too. Recorded as **VC-R8**, with the photo library added to the §8 backlog.
- **Tabs hide things**, which is a genuine cost for AC3 — the bookings summary is what staff are planning around, and a closed tab can imply there is nothing behind it. The two time-based tabs therefore carry a count in the tab itself ("Upcoming bookings · 2"), while the attribute tabs carry none, because every venue has capacity and hours and a `0` there would read as "none recorded". Recorded as **VC-R7**.

The booking statuses were then tabbed one level in as well. The venue's total stays above that inner row so it is never hidden, each status tab carries its own count, and the row **opens on the first status that has bookings** (`defaultBookingGroupKey`) rather than always Confirmed — a venue whose only commitment is a hold would otherwise open on an empty Confirmed panel reading as "nothing booked", the exact misreading the counts exist to prevent.

Built: `components/venues/VenueGallery.vue` (prev/next, dot indicators, arrow keys, wrapping via `stepIndex` so the controls never dead-end) and `components/venues/VenueLayoutDiagram.vue` (inline SVG, geometry computed from one table so a seventh layout is a single entry), plus `venueSlides`, `venueProfileTabs` and `stepIndex` in `features/venues/venueProfile.js` and an ARIA tablist in the view. Only the selected panel is mounted, and switching tabs makes no network request.

#### Migration history repair (2026-09-20)

Pushing `20260920000000` surfaced drift far worse than PROJECT_REVIEW D8's single missing row. `supabase migration list --linked` showed six local files applied-but-unrecorded and three remote rows with no local file. Querying `supabase_migrations.schema_migrations` showed the three were the *same* migrations under earlier timestamps from another working copy (`role_switching`, `session_active_roles_fk_user_roles`, `profiles_role_requires_user_roles_membership`), and direct schema checks confirmed all six local files were live in substance — `public.events`, `events.event_timezone`, `events_registration_closes_before_event_end`, `user_roles`, `session_active_roles_profile_role_fkey`, `profiles_role_requires_user_roles_membership_fkey` all present. A plain `db push` would have replayed `create table public.events` against a populated table.

Repaired with `migration repair --status applied` on the six and `--status reverted` on the three duplicates, then pushed. Local and remote now match exactly. **Check `migration list --linked` before every push** — this is the second time the ledger has drifted.

#### Defect found while doing this (D9)

`npm run build` and `npm test` were already broken on `main`: `frontend/src/stores/events.js` imports `@/stores/venues`, which SCRUM-70 moved to `features/venues/venueSearchStore.js` while SCRUM-8 was in flight. The two merged without the import being repointed, so the SPA would not build at all. Fixed in a separate commit on this branch because it blocked verifying anything in a browser; logged as **D9** in `docs/PROJECT_REVIEW.md`.

### 4.11. SCRUM-76 — Enforce endpoint access by active role, not all held roles (exact Jira record)

| Field | Value |
|---|---|
| Issue key | `SCRUM-76` |
| Summary | Enforce endpoint access by active role, not all held roles |
| Issue type | Story |
| Parent epic | `SCRUM-7` — User authorisation and authentication |
| Status | In progress at time of writing (`feature/scrum-76-enforce-active-role`) |

**User story (verbatim):**

> As a system, I want every protected endpoint to check the user's currently active role, not the full set of roles they hold, so that a user cannot access another role's data just because they also hold that role.

**Acceptance criteria (verbatim from Jira):**

> * Calling an endpoint restricted to role X while active role is Y returns 403, even if the user separately holds role X
> * RLS policies enforce this at the database layer, not just the API layer (private.current_user_role() reads active_role)
> * This holds true even for direct API calls that bypass the UI (verified with a raw request, not just clicking through the app)
> * Existing RLS policies (events, profiles, venues, venue_bookings, venue_blocks, venue_facilities, venue_layouts) continue to pass their current test cases after the function is repointed

*Jira also notes that SCRUM-70, 71, 73 (and a re-check of 72) have acceptance criteria that assume direct routing to one dashboard on login.*

#### How the implementation maps to the ticket

SCRUM-74/75 had already made the **API** layer correct: `get_current_user` resolves the session's active role and `require_roles` gates on it. What was still wrong was the database layer. `private.current_user_role()`, which every RLS policy calls, read `profiles.role`, the account's default. `docs/REQUIREMENTS.md` ACC-R4 had recorded that as an intentional gap; it is superseded here, because a session switched to another role kept its default role's access to anything reached through RLS.

1. **AC2 and AC4 — the function.** Migration `20260920100000_current_user_role_reads_active_role.sql` rewrites `private.current_user_role()` with the same signature, so no policy needed editing. It returns the `session_active_roles` row matching the JWT's `session_id` **and** `auth.uid()`, falling back to `profiles.role` when the session never switched or the token has no `session_id` (the same fallback as `resolve_active_role`). Matching on the profile as well means a session id belonging to another account is never honoured.
2. **AC1 and AC3 — the API.** No production change was needed, so this is proved rather than built: `backend/tests/test_active_role_access.py` sends a raw request through the app for **every mounted route and every (held role, active role) pair** and asserts that acting as Y while also holding X is denied exactly when a Y-only account is. A second test fails any endpoint that no role is denied on, so a new endpoint written without `require_roles` cannot slip through.
3. **Route guards.** `frontend/src/router/__tests__/activeRoleAccess.spec.js` does the same for every guarded page: with an account that holds all five roles, each route opens only for the role the session is acting as. A route without `allowedRoles` fails unless it is `login` or `profile`. The guard is UX; the API is the enforcement point.
4. **Parity in the API lookup (code review follow-up).** `resolve_active_role` in `backend/app/core/security.py` filtered `session_active_roles` by `session_id` alone, while the SQL function also matches `profile_id`. Both ids come from the same verified JWT so it was not exploitable, but it now takes `user_id` and applies the same scoping, so the two layers follow one rule.
5. **Standing rule.** `AGENTS.md`'s security baseline now says every new endpoint, policy and page authorises by the active role, and REQUIREMENTS gains **AUTH-R6**.

**Scope decision:** the dashboards for SCRUM-71 and SCRUM-73 are on unmerged branches, so they were not touched. `docs/IMPLEMENTATION_MAP.md` records the pre-merge check, and the matrix tests will cover them once merged. SCRUM-70/72 (on `main`) are covered by the route matrix.

#### Verification

- Written red first: `supabase/verification/active_role_checks.sql` failed against the live function with `switched session (attendee) resolved as venue_staff`, then passed with the new function, run in a rolled-back transaction so nothing was persisted.
- The two matrices passed on their first run (they characterise behaviour SCRUM-74/75 already built), so each was **mutation-checked**: making `get_current_user` ignore the active role failed the backend matrix on every organiser route, and making the guard accept any held role failed two frontend tests. Both changes were reverted.
- `npm test`: 281 passing across 21 files. `pytest`: 168 passing including the 19 new matrix tests and the parity test (written red first), with 14 failures in `test_events_api.py` that fail identically without this story: this Windows Python has no IANA timezone data, so `event_timezone = "Asia/Singapore"` is rejected (an environment problem, not a code defect).
- **Migration applied to the live project (2026-09-20).** The ledger matched the ten local files first; `apply_migration` recorded it under a generated version, which was renamed to `20260920100000` so the ledger matches the file. `get_advisors` (security) shows only the leaked-password warning that was already open.
- **Live, after applying:** `active_role_checks.sql`, `auth_security_checks.sql` and `venue_schema_checks.sql` all pass (each rolled back). With real tokens through PostgREST (not simulated claims), both tokens carry a `session_id` claim; the attendee reads 0 venues and the coordinator reads 8. `event_schema_checks.sql` passes too, after fixing a typo in it: it used organiser id `a0000000-0000-0000-0000-000000000001`, which does not exist (the seed's is `...4000-8000-...`), so its RLS check failed regardless of this story.
- **In a browser** (dev servers against the live project): signed in as `coordinator@connectsphere.dev`, acting as Event Coordinator, `/dashboard/venue-staff` redirected to `/dashboard/coordinator` and a raw request to `/venues/dashboard/venue-staff` returned 403; after switching to Venue Staff both opened (200); switching back returned 403 again (TC-ROLE-017–019).
- **Not verified:** RLS denial through a real token for an account that *holds* a staff role but acts as a non-staff one, because no seeded account is shaped that way; it is covered with simulated claims in `active_role_checks.sql` instead.

### 4.12. Chore — SCRUM-76 follow-ups: timezone data and a real-token RLS check

Not a Jira story; two loose ends left by SCRUM-76 (§4.11), done on `chore/timezone-data-and-real-token-rls-check`.

1. **Timezone data.** 14 tests in `test_events_api.py` failed on Windows with `event_timezone must be a valid IANA timezone`. `events/schemas.py` validates with `zoneinfo.ZoneInfo`, which reads the operating system's timezone database, and Windows has none. `tzdata` was neither installed nor in `requirements.txt`, so every Windows developer hit it. It is now pinned in `backend/requirements.txt` (`tzdata==2026.4`) and `pytest` passes in full (182). Linux and the Docker image already had system data, so nothing there changes.
2. **RLS denial through a real token.** SCRUM-76's own verification left one gap: `active_role_checks.sql` simulates JWT claims, and no seeded account holds a staff role while acting as a non-staff one. A throwaway account (`venue_staff` default, also `attendee`) was created on the live project, logged in through the real API, and queried through PostgREST with its own access token: **8 venues** un-switched, **0 venues and a 403 from the API** after switching to `attendee` through `POST /auth/active-role`, **8 and 200** after switching back. The account was then deleted and every table it touched checked empty. Recorded as **TC-DATA-014** so it can be repeated.
### 4.13. SCRUM-71 — Event Organiser dashboard

SCRUM-71 is implemented in the frontend using the existing organiser-owned events response and SCRUM-8 request/detail flows. The dashboard presents owned events across their lifecycle, separates drafts from requests, and keeps filtering and sorting client-side after the initial load. Overview and Events are side-navigation views matching the coordinator dashboard pattern. Dashboard actions edit a draft, amend a returned request, or open the event detail flow; inline editing, change/cancellation workflows, and the future organisation-wide read-only view remain out of scope as recorded in `REQUIREMENTS.md` §6.21.2.

What was actually built:

1. **Dashboard presentation** — `frontend/src/views/dashboards/OrganiserDashboard.vue` renders overview counts, every owned lifecycle status, external-safe event details, status-aware attention states, loading/error/empty states, responsive filters, and status-specific actions.
2. **Pure dashboard logic** — `frontend/src/features/events/organiserDashboard.js` owns filtering, sorting, draft/request grouping, overview grouping, attention detection, and status-specific action metadata.
3. **Flow navigation** — draft actions route to `event-new` with the draft id; returned, submitted, and other requests route to `event-detail`; the new-request action uses the existing request flow.
4. **Reusable controls and accessibility** — compact `BauhausInput` and `BauhausSelect` controls support the 50px filter layout, status multi-select, custom sort dropdown, direction icons, and explicit aria labels.
5. **Honest data states** — loading and API-error states suppress fabricated counts and empty sections; successful empty results use the existing empty-state component.

#### Verification

- `npm test`: 116 passing across 15 frontend files, including SCRUM-71 selector/view tests.
- `npm run build`: passed.
- `python -m pytest` from `backend/`: 114 passing.
- Editor diagnostics: passed; `git diff --check`: passed.
- Manual browser checks completed for desktop and 390 × 844 mobile filter layout, including the mobile header Clear action and inline Sort direction control.
- **Not verified:** rejection/cancellation reasons are not currently exposed by the events API, so the dashboard cannot display those optional fields until the backend response contract provides them.

### 4.14. Bug fix — "Approved – planning" label contradicted the customer's status model

Not a Jira story; a fix on `fix/planning-status-label`, prompted by re-reading the Session 1 and 2 answers while refining SCRUM-34.

The UI labelled `planning` as **"Approved – planning"**, a reading taken from QA-56 ("Approved (initial check passed)"). Session 2 settled the term the other way: "Confirmed/Approved" is **one final status**, reached when the essential venue and technical arrangements are approved (QA2-8, consistent with QA-18). So an organiser whose request had only passed initial review saw "Approved", then later "Confirmed", which is the exact confusion the customer briefing lists (organisers "unsure whether an event … has been approved or confirmed", W1 §2).

- `planning` is now labelled **"Planning"**, and its description reads "Passed initial review — venue and equipment being arranged." (`frontend/src/features/events/dashboard.js`). The coordinator and organiser dashboards both read these labels, so both change.
- Two tests in `features/events/__tests__/dashboard.spec.js` pin the rule: `planning` is labelled "Planning", and no label or description except `confirmed`'s says "approved".
- REQUIREMENTS §5 and §6.6 record it as a **[Team decision]**; TEST_CASES TC-DASH-010 expects the new label.
- In Jira, SCRUM-34 now moves an event to Planning, and final confirmation became its own backlog story, **SCRUM-82**, blocked by SCRUM-19, 36, 45 and 24.

#### Verification

- Both new tests failed first on the old label, then passed after the change.
- `npm test`: 314 passing across 23 frontend files. `npm run build`: passed.
- **Not verified:** no backend change, so `pytest` wasn't re-run, and the dashboards weren't checked in a browser. The change is two strings read through `STATUS_LABELS`/`STATUS_DESCRIPTIONS`.

#### Review follow-up (same PR)

The PR review raised three non-blocking points, all fixed before merge:

1. **The organiser's event page showed the raw status.** `EventDetailView.vue` rendered `event.status.replaceAll("_", " ")`, so a submitted request read "SUBMITTED" there but "Awaiting assignment" on the dashboard. The badge and the "Planning status" line now read `STATUS_LABELS`, and fall back to the raw status only for an unknown value. This predates the label fix.
2. **Organiser group labels were typed out separately.** `groupOrganiserActiveEvents` now takes "Planning", "Confirmed" and "Completed" from `STATUS_LABELS`. "Under review" keeps its own label because that group also holds `submitted`. The organiser **descriptions stay separate on purpose**: `STATUS_DESCRIPTIONS` is written for coordinators ("Waiting on your approval…"), so sharing it would show organisers the wrong wording.
3. **The "approved" test only covered the coordinator maps.** `organiserDashboard.spec.js` now checks that the single-status group labels match `STATUS_LABELS`, and that no organiser group except confirmed says "approved".

Verification for the follow-up:
- A new `views/__tests__/EventDetailView.spec.js` failed first, because the page showed the raw status where "Awaiting assignment" was expected, and passes after the fix. The two organiser tests guard a refactor that kept the same wording, so they passed both before and after.
- `npm test`: 318 passing across 24 files. `npm run build`: passed.
- **In the browser**, signed in as `organiser@connectsphere.dev` against the live project: the event page for a `planning` event shows "Planning" in the badge and the status line. The dashboard's status groups read Under review / Planning / Confirmed / Completed. The only console error was a missing `favicon.ico`.
- **Not verified in the browser:** "Awaiting assignment" on the event page, because the organiser account has no `submitted` event. The view test covers it.

### 4.15. SCRUM-34 — Approve event request to start planning (exact Jira record)

| Field | Value |
|---|---|
| Issue key | `SCRUM-34` |
| Summary | Approve event request to start planning |
| Issue type | Story |
| Status | In Progress (at time of writing this entry) |
| Parent epic | `SCRUM-11` — Event Review and Approval |
| Sprint | SCRUM Sprint 2 |
| Story point estimate | 1 |
| Priority | Medium |

**User story (verbatim):**

> As an Event Coordinator, I want to approve a submitted request once its requirements are clear, so that venue and equipment planning can begin.

**Acceptance criteria (verbatim from Jira):**

> * **Given** an event in _Under review_ that is assigned to me, **when** I approve it, **then** its status becomes **Planning**. Approval is the initial feasibility decision (W1 Step 5, QA-23, QA2-8). It is **not** confirmation.
> * Approve is available **only** when the status is _Under review_. Approving an event that is Returned, Submitted, Planning, Confirmed, Rejected, Cancelled or Completed is blocked with "Cannot approve an event that is <status>" (QA-22).
> * Only the **assigned** coordinator can approve. Any other coordinator, any other role, and a user who holds the coordinator role but is currently acting as a different role all get _Forbidden_.
> * The organiser is notified of the approval. The coordinator isn't notified of their own action.
> * The approval, who made it, and when are recorded in the event history and visible in the UI (QA-70).
> * Approving does not book a venue or reserve equipment. Confirming the event is a separate, later step.

#### How the implementation maps to the ticket

The ticket's "Forbidden" cases are one line ("any other coordinator, any other role, and a user who holds the coordinator role but is currently acting as a different role"); the implementation splits this into two different HTTP shapes that the ticket doesn't itself distinguish. A coordinator who isn't the *assigned* one gets **403**, not the organiser-endpoint's "404, not 403" pattern (§2, `_owned_event`) — deliberate, because coordinators can already search every non-draft event (QA-87), so a 403 tells them nothing a 404 would have hidden. A coordinator-holding account acting as a different active role gets 403 through the existing `require_roles`/active-role machinery (SCRUM-76), proved with a dedicated test rather than assumed.

"Recorded in the event history and visible in the UI" (QA-70) is new schema, not a field on `events`: a rejection reason especially has nowhere else to live without duplicating it per-status, so `event_status_history` (one append-only table, reused by SCRUM-52) is the single home for every transition, `from_status`/`to_status`/`actor_id`/`reason`/`at`. "Approving does not book a venue or reserve equipment" is enforced by omission: `transition_event`'s only conditional side effect is releasing venue bookings, and only on a `rejected` outcome — approve never touches `venue_bookings` or equipment.

The ticket is silent on *how* a decision reaches the organiser. The generic `transition_event` RPC (built to be reused by SCRUM-12 and SCRUM-33 too, per the design doc) writes a `notifications` row for the organiser whenever `p_notify_type` is set and the organiser isn't the actor — satisfying "the organiser is notified... the coordinator isn't notified of their own action" without a second code path. There is deliberately no read API or bell for it yet (SCRUM-27); the row exists so that story doesn't have to change this one's write path later.

What was actually built:

1. **The transition rule** — `backend/app/modules/events/lifecycle.py`: `TRANSITIONS["approve"] = ({under_review}, planning)`; `target()` raises `EventTransitionError("Cannot approve an event that is <status with spaces>")` for anything else.
2. **The endpoint** — `POST /events/{event_id}/approve` in `backend/app/modules/events/router.py`, guarded by `require_roles(["event_coordinator"])`, plus an explicit assigned-coordinator check (`NotAssignedCoordinatorError`, 403) before calling the lifecycle and the RPC.
3. **The data layer** — migration `20260923120000_event_review_history_and_notifications.sql`: `event_status_history`, `notifications`, and `public.transition_event(...)` (`security definer`, executable only by `service_role`); `backend/app/modules/events/repository.py::transition_event` calls it via `.rpc()`.
4. **The UI** — `frontend/src/views/events/CoordinatorEventView.vue`: an Approve button (shown only while `under_review`) behind the existing `ConfirmModal`, confirmation copy "Approve this request? It moves to Planning so venue and equipment planning can begin. This does not confirm the event." On success the toast reads **"Request moved to Planning"** — never "approved" — consistent with REQUIREMENTS §5's rule that only `confirmed` is described that way (QA2-8).
5. **The store** — `frontend/src/features/events/eventReviewStore.js::approve()`, which calls the endpoint, applies the returned event, then reloads history in a way that can't turn a successful approval into a reported failure (see the reject entry below for the shared detail).

#### Verification

- **Written red first:** `backend/tests/test_event_lifecycle.py::test_approve_moves_under_review_to_planning` and `test_approve_is_blocked_from_every_other_status` failed on import before `lifecycle.py` existed; `backend/tests/test_event_review_api.py::TestApprove` failed the same way before the router changes.
- `pytest` (full suite, backend): **283 passed**.
- `npm test` (full suite, frontend): **357 passed** across 28 files, including `CoordinatorEventView.spec.js::"approves after confirmation and shows Planning"` and the `eventReviewStore` and `RejectEventModal`/`EventStatusHistory` specs.
- **Real system (Task 9):** `POST /events/{id}/approve` on a seeded `under_review` event returned `200` with `"status":"planning"`; repeating it returned `409 "Cannot approve an event that is planning"`; a `venue_staff`-acting coordinator and the organiser both got `403`; the organiser's `notifications` row (`type: event_approved`) was written with no matching row for the coordinator; `transition_event` refused execution as `authenticated` with `permission denied for function transition_event`; the Playwright browser flow showed the Approve button disappear and a new "Planning · by Marcus Lim" history entry appear after confirming.
- **Not verified:** the notification is written but has no read API or bell (SCRUM-27), so "the organiser is notified" is checked at the database row, not by an organiser seeing anything in the app.

### 4.16. SCRUM-52 — Reject Event Request (exact Jira record)

| Field | Value |
|---|---|
| Issue key | `SCRUM-52` |
| Summary | Reject Event Request |
| Issue type | Story |
| Status | In Progress (at time of writing this entry) |
| Parent epic | `SCRUM-11` — Event Review and Approval |
| Sprint | SCRUM Sprint 2 |
| Story point estimate | 2 |
| Priority | Medium |

**User story (verbatim):**

> As an Event Coordinator, I want to reject an unfeasible event request with a mandatory reason, so that ConnectSphere does not commit resources to unviable events.

**Acceptance criteria (verbatim from Jira):**

> * **Given** an event in _Under review_ or _Planning_ that is assigned to me, **when** I reject it with a reason, **then** its status becomes **Rejected**. Valid grounds are venue or equipment unavailability, or a suitability issue (QA-23, QA-83, QA2-8).
> * A reason is **required**. An empty or whitespace-only reason is blocked before the action is confirmed.
> * Reject is available **only** before confirmation, from _Under review_ or _Planning_. Rejecting an event that is Submitted, Returned, Confirmed, Rejected, Cancelled or Completed is blocked with "Cannot reject an event that is <status>". A confirmed event is cancelled instead (QA2-6).
> * Only the **assigned** coordinator can reject. Any other coordinator, any other role, and a user who holds the coordinator role but is currently acting as a different role all get _Forbidden_.
> * A rejected request is closed. It can't be edited or resubmitted (QA-34, QA-95).
> * Rejecting an event in _Planning_ releases its tentative venue hold (QA2-13).
> * The organiser is notified of the rejection with the reason. The coordinator isn't notified of their own action.
> * The rejection, its reason, who made it, and when are recorded in the event history and visible in the UI to the organiser and the assigned coordinator (QA-70).

*This description already reflects the settled rules (the design doc calls it "the settled rules, which the Jira rewrite carries"); it was not edited again for this entry.*

#### How the implementation maps to the ticket

"An empty or whitespace-only reason is blocked **before the action is confirmed**" is a client-side requirement, not just a server one: `RejectEventModal.vue` disables its confirm button while the trimmed reason is empty, and the server independently rejects a blank/whitespace/**or over-1000-character** reason with 422 — the 1000-character cap is not in the ticket at all; it's recorded as an **[Assumption]** in REQUIREMENTS §6.4 and §9, because Jira sets no bound and something has to stop an unbounded `text` column reaching the history table and the notification message.

"A rejected request is closed. It can't be edited or resubmitted" is enforced where editing already lives, not as new code: `events.service._validate_submission`/the PATCH guard already blocks anything outside `draft`/`returned`, and `rejected` was never one of those statuses, so this AC needed only a regression test (`test_a_rejected_event_cannot_be_edited_by_its_organiser`), not a new rule.

"Releases its tentative venue hold" from `planning` is read broadly as `held`, `approved` **and** `re_review` bookings (not only `held`) — `re_review` is a settled booking reopened by a significant change (§6.7/VC-R6), and leaving it occupying the venue after the event itself is rejected would contradict "does not commit resources to unviable events" in the user story. Equipment reservations get the same treatment only as a documented hook in `transition_event`, because SCRUM-24's reservation flow isn't built yet — recorded as a known gap, not silently skipped.

"Visible in the UI to the organiser and the assigned coordinator" reuses `EventStatusHistory.vue` on both `CoordinatorEventView` (new, this story) and the organiser's existing `EventDetailView` (SCRUM-8), rather than building two components — the same component, same data shape, same `GET /events/{id}/history` endpoint, gated by the same "owner or assigned coordinator" rule as the event read itself.

What was actually built:

1. **The transition rule** — `lifecycle.py`: `TRANSITIONS["reject"] = ({under_review, planning}, rejected)`.
2. **The endpoint** — `POST /events/{event_id}/reject` (body `EventRejectRequest {reason}`, stripped, required, `max_length=1000`); `GET /events/{event_id}/history` (owner or assigned coordinator, newest first, actor embedded as `{id, full_name}`); `GET /events/{event_id}` broadened so the assigned coordinator can read it too (previously organiser-only).
3. **The data layer** — the same migration and `transition_event` RPC as SCRUM-34: on a `rejected` outcome it additionally sets matching `venue_bookings.status` to `released` and writes the organiser's notification with the reason, in the same transaction as the history insert.
4. **The reject UI** — `components/events/RejectEventModal.vue`: required reason textarea, a 1000-character counter, confirm disabled while blank/whitespace, wired into `CoordinatorEventView.vue`'s Reject button (shown from both `under_review` and `planning`).
5. **The organiser's rejection notice** — `EventDetailView.vue`: a solid red block (the page's own alert tokens, not `BauhausCard background="red"` — see the note below) headed "THIS REQUEST WAS REJECTED", showing the reason and "It is closed and can't be resubmitted."
6. **History isolation** — `eventReviewStore.js` tags its loaded `history` with the event id it belongs to and clears it before loading a different event's data, so a Pinia singleton shared by the coordinator and organiser pages never shows one event's history (or rejection reason) while another event's page is still rendering the previous load.

**Bug fix folded into this story (found in review, fixed before the branch was reported done):** `BauhausCard background="red"` renders in the browser as a plain white card with only a ~4px red accent stripe on one edge (confirmed visually in Task 9) — nowhere near "unmistakably rejected." `EventDetailView`'s rejection notice was rewritten to use a dedicated solid-red block instead of that prop, in commit `92f1b97`. `components/common/BauhausCard` itself is unchanged; this is a usage fix, not a design-system change, since other screens use `background="red"` for a lighter accent on purpose.

#### Verification

- **Written red first:** `test_event_lifecycle.py::test_reject_is_allowed_before_confirmation`/`test_reject_is_blocked_from_every_other_status`, `test_event_review_api.py::TestReject` (including `test_a_blank_reason_is_rejected`, `test_a_missing_reason_is_rejected`, `test_a_reason_over_1000_characters_is_rejected`), and `RejectEventModal.spec.js` (`"cannot be confirmed without a reason"`, `"cannot be confirmed with a whitespace-only reason"`) all failed for the expected reason before their implementation existed.
- `pytest` (full suite): **283 passed**. `npm test` (full suite): **357 passed** across 28 files.
- **Real system (Task 9):** rejecting a whitespace reason returned `422`; rejecting event `…0202` (`planning`, with a `held` booking) with `"Venue unavailable"` returned `200` `"status":"rejected"`, and the matching `venue_bookings` row moved to `released`; `GET /events/{id}/history` showed the reason and actor to both the organiser and the assigned coordinator; the organiser's `notifications` row read `"...was rejected: Venue unavailable"` with no row for the coordinator. In the browser: the reject modal kept its confirm button disabled for a 3-character whitespace-only reason (counter still moved, `3 / 1000`), then rejected successfully once a real reason was typed; the organiser's event page showed the rejection card and both rejection entries (the HTTP one and the browser one) in history, correctly attributed.
- **Visual finding, not a regression of this story's own code:** before commit `92f1b97`, the rejection card was confirmed in the browser to be only a thin accent stripe rather than a clearly red notice (see the bug-fix note above) — fixed on this branch before being reported done.
- **Not verified:** equipment-reservation release (no reservation flow exists yet, SCRUM-24); the notifications bell (SCRUM-27); a live re-run of the transient `httpx.RemoteProtocolError`/CORS-looking failure Task 9 hit once on this page (see IMPLEMENTATION_MAP §5 "Still open") — it resolved on retry and wasn't deliberately reproduced.

### 4.17. Bug fix — event history skipped creation and submission (PROJECT_REVIEW D11)

Not a Jira story; a fix on `fix/event-history-on-create`, branched from `feature/scrum-34-52-approve-reject` because `event_status_history` exists only there. Reported by the developer: "when an event is created there is no history log."

**Symptom.** An organiser's History panel read "No status changes recorded yet." for a new draft, and still did after submission. The first entry appeared only when a coordinator approved or rejected. LC-R2 and QA-70 require every transition to be recorded and visible.

**Reproduction (live project, before the fix).** A query over `events` showed none of the 15 events had a creation row (`from_status is null`), and all 9 in `draft`/`under_review` had no history at all. A rolled-back check (`supabase/verification/event_history_checks.sql`) that inserts an event and submits it through `transition_event` failed on "creating an event records (none -> draft)" and "submission stamps submitted_at".

**Root cause.** `public.transition_event` is the only writer of `event_status_history`. Creation (`repository.create_event`) and submission (`repository.submit_event`) both wrote `events` directly, and SCRUM-8 built them before the RPC existed. The submission gap was already recorded as a known exception in IMPLEMENTATION_MAP §5; the creation gap wasn't recorded anywhere. **Why tests missed it:** the SCRUM-34/52 history tests start from events that already exist, and the SCRUM-8 tests mock the repository, so nothing asserted that creating or submitting leaves a history trace.

**Fix.**
- **Creation:** trigger `events_record_created` (`after insert on events`, `private.record_event_created()`) writes `(null → new.status)` with the organiser as actor, at `created_at`, in the same transaction as the insert. It's a trigger rather than a new RPC (a team decision on this fix) so every insert path is covered, seed and fixtures included.
- **Submission:** `lifecycle.TRANSITIONS["submit"] = ({draft}, under_review)`, and `service.submit` calls `repository.transition_event` with the organiser as actor and no notification. `transition_event` now stamps `submitted_at = now()` when an event leaves `draft`, so the RPC's signature and grants are unchanged. `repository.submit_event` is deleted. The "Only draft events can be submitted." 409 is kept, so the API contract is unchanged.
- **Data:** migration `20260924120000` backfilled a `(null → draft)` row for every existing event and a `(draft → under_review)` row at `submitted_at` for every submitted one.
- **Found while verifying in the browser:** one backfilled event listed "Draft" above "Under review". Its old `submitted_at` came from the API server's clock, about 2 seconds behind the database clock that sets `created_at`, so "submission" preceded "creation". Migration `20260924130000` moves such rows up to `created_at`. New submissions can't recur this, because `submitted_at` now comes from the database. `list_status_history` also breaks timestamp ties with the creation row last, since seeded fixtures set both times to the same `now()`.
- `supabase/verification/event_review_fixture_reset.sql` now keeps each fixture's creation and submission rows and deletes only review-decision rows.

#### Verification

- **Written red first:** `test_event_lifecycle.py::test_submit_moves_draft_to_under_review` (and the blocked-from-every-other-status cases), `test_events_api.py::…_through_transition_event` (no `transition_event` call recorded), `test_events_repository.py::test_status_history_puts_the_creation_entry_last_when_timestamps_tie`, and `event_history_checks.sql` against the live schema all failed for the expected reason before the change.
- `pytest` (full suite): **300 passed**.
- **Real system:** both migrations were first run with their checks in a rolled-back transaction, then applied. `event_history_checks.sql` passes all six checks. Every live event now has a creation row, and every submitted event has a submission row. Through the running API as `organiser@connectsphere.dev`: create → history `[(none → draft) by Olivia Tan]`; submit → `200`, `submitted_at` set, history `[(draft → under_review), (none → draft)]`; resubmit → `409`. The throwaway event was then deleted. In the browser, the organiser's page for a real approved event lists Planning, Under review, Draft, and fixture `…0201` lists Under review, Draft, with no console errors. `get_advisors` security findings are unchanged: only the pre-existing leaked-password toggle.
- **Not verified:** no frontend code changed, so `npm test` wasn't re-run. The creation entry reads "Draft · by <organiser>", with no separate "Created" wording. That's `EventStatusHistory`'s existing label, left as is.

### 4.18. SCRUM-33 — Return event request for amendment (Jira record, and the criteria it was built to)

| Field | Value |
|---|---|
| Issue key | `SCRUM-33` |
| Summary | Request Clarification for Event (title unchanged in Jira; the work is "return for amendment") |
| Issue type | Story |
| Status | In Progress (at time of writing this entry) |
| Parent epic | `SCRUM-11` — Event Review and Approval |
| Sprint | SCRUM Sprint 2 |
| Story point estimate | 3 |
| Priority | Medium |

**User story and criteria as they stood in Jira (verbatim):**

> As an Event Coordinator, I want to send clarification queries to Event Organisers so that I can obtain clear requirements before deciding whether planning should proceed.
>
> * Can highlight specific ambiguous fields (e.g. room layout, attendee count) and give comments asking for additional information.
> * Submitting clarification queries sends a notification to the Event Organiser.
> * Clarification requests and responses are tracked in the event history.
> * The coordinator can mark the clarifications as resolved once adequate information is provided.

**Why it was not built as written.** The customer's model is *return for amendment*: the organiser edits the same request and resubmits it (QA-22, QA-77), not a clarification thread the coordinator marks resolved. PROJECT_REVIEW §B2a had already listed SCRUM-33 as contradicted. The criteria below were agreed with the developer on 2026-09-24 and are the ones implemented; **the Jira description still needs updating to them**, with a comment citing QA-22 and QA-77.

**Acceptance criteria (as agreed):**

> 1. **Given** an under-review event assigned to me, **when** I return it with a message and flag fields (e.g. expected attendance), **then** the status is `returned` and the organiser is notified.
> 2. The organiser sees my message, with the flagged fields highlighted on their request.
> 3. **Given** a returned request, **when** the organiser edits any field and resubmits with a note, **then** the status goes back to `under_review` with the **same coordinator**, and I'm notified.
> 4. Every return and resubmission is recorded in the event history. A request can be returned more than once.
> 5. The return message is required: an empty or whitespace-only message is blocked.
> 6. Only the assigned coordinator can return, and only the owning organiser can resubmit. Others get 403/404.
> 7. Approve or reject while `returned` → 409.

The "no venue booking while returned" rule in REQUIREMENTS §6.4 was left out: no booking-creation endpoint exists yet, so the story that builds booking creation owns that guard (IMPLEMENTATION_MAP §5).

#### How the implementation maps to the ticket

"Highlight specific fields" (the old wording) and AC2 are one mechanism: the coordinator ticks fields from `EVENT_FIELD_LABELS`, the API stores their names (`EventField`, the 15 editable fields) in `amendment_requests.flagged_fields`, and the organiser's form highlights every input behind each one — `starts_at` covers both the date and the start-time inputs, because the form splits it. The highlight is a new `flag` prop on the common inputs rather than reusing `error`: a flag asks for review, it isn't a validation failure, and both can show at once.

The return and resubmission each run as **one** database transaction (`return_event_for_amendment`, `resubmit_event`), wrapping the existing `transition_event` so status, history, the amendment row and the notification can't disagree. `transition_event` itself was not changed, so approve, reject and submit are untouched; the resubmit function notifies the coordinator itself because `transition_event` can only notify the organiser.

Resubmission re-runs the full submission validation (the §5 guard "basic info still complete"). The resubmission note is required (also a §5 guard). Message and note are capped at 1000 characters after trimming — an **[Assumption]** (REQUIREMENTS §9), the same cap as a rejection reason.

What was actually built:

1. **Data** — migration `20260924140000`: `amendment_requests` (one row per return, at most one open per event), select-only RLS matching `event_status_history`, and the two functions (`service_role` only).
2. **API** — `lifecycle.TRANSITIONS` rows `return`/`resubmit`; `POST /events/{id}/return` (assigned coordinator), `POST /events/{id}/resubmit` (owning organiser); `GET` and `PATCH /events/{id}` carry the open `amendment` while `returned`, so saving changes keeps the organiser's banner.
3. **Coordinator UI** — "Return for amendment" beside Approve/Reject on `CoordinatorEventView`, via `ReturnEventModal`; afterwards `AmendmentBanner` ("Waiting for the organiser to amend") and no decision buttons.
4. **Organiser UI** — "Amend and resubmit" on the dashboard and on `EventDetailView` opens `EventRequestView` in amend mode: "Amend your request", the coordinator's banner, highlighted inputs, "Save changes", and "Resubmit" through `ResubmitEventModal` (required note).

**Bug found and fixed during real-system verification:** at 375×812 the return dialog (fifteen checkboxes) is taller than the screen, and its centred scrolling overlay pushed the heading 161px above the scroll origin, where it could not be reached. Fixed by aligning to the top and centring with `my-auto` (commit `7b34d7c`), with a regression test.

**Fixed after the whole-branch review:** (1) flagged inputs, selects and the description box carried both `bg-canvas` and the yellow tint, and `bg-canvas` wins in the built stylesheet, so a flagged field stayed white with only its caption — the fill is now one or the other (`e4fa4d5`); (2) the response model validated stored flag names against `EventField`, so a field later renamed or removed would have made every read of a returned event a 500 — responses now pass names through as strings, and only the return request validates them (`f91a573`). Both were written red first.

**Fixed after the PR #30 review (Gemini), all written red first:** (1) `EventRequestView` looked the `?id=` event up in the organiser store's cached list, so a stale list left a blank form whose Save draft would create a duplicate event — it now always reads the event with `get`, and a non-editable one redirects to its detail page (`79eefde`); (2) emptying an optional field didn't clear it, because `eventToPayload` left it out of the body — edits now send `null` (`56ba0f1`, PROJECT_REVIEW D12, a bug dating from SCRUM-8 that broke AC3 here); (3) `BauhausInput` warned on numeric values (`c0b00f2`); (4) migration `20260925100000` makes the table refuse a blank resubmission note, applied live (`4294fc2`). The review's point that resubmission is two steps (edits, then the database function) was declined: the spec chose it to match `submit`, and a test pins that a lost race leaves the edits saved and the request `returned`.

#### Verification

- **Written red first:** `test_event_lifecycle.py` return/resubmit cases (`KeyError`), `test_events_repository.py` wrappers (`AttributeError`), `test_event_amendment_api.py` (routes 404 before they existed, `amendment` missing), the Vitest specs for `amendment.js`, the review store, the `flag` prop, both modals, `AmendmentBanner`, `CoordinatorEventView`, `EventRequestView`, `EventDetailView` and the organiser dashboard, and `supabase/verification/event_amendment_checks.sql` against the live schema (function missing) all failed for the expected reason first.
- `pytest` (full suite): **386 passed**. `npm test` (full suite): **419 passed** across 34 files. `npm run build` succeeds.
- **Database:** the migration applied to the live project (ledger row renamed to `20260924140000`); `event_amendment_checks.sql` prints `AMENDMENT CHECKS PASSED` (return → resubmit → return, one-open rule, blank-message check, stale version changes nothing, notifications to the right party only, functions not executable by `authenticated`, RLS: owner and assigned coordinator read, venue staff and `anon` read nothing). `get_advisors` unchanged (security: the pre-existing leaked-password toggle only).
- **Real system, in the browser with the live project** (the developer signed in; fixture `…0201`):
  - As the coordinator: returned it with a message, flagging *Expected attendance* and *Proposed date and start time* → `POST /return 200`, banner and new history entry shown, toast "Returned to organiser". Database: `returned`, same coordinator, one open amendment `[starts_at, expected_attendance]`, history reason = the message, one `event_returned` notification to the organiser.
  - As the organiser: the dashboard's **Amend and resubmit** opened `/events/new?id=…0201` headed "Amend your request"; exactly the date, start-time and attendance inputs were flagged. **Save changes** (attendance 12 → 40, `PATCH 200`) kept the banner and all three flags; the event stayed `returned`. **Resubmit** with a note → `POST /resubmit 200`, back on the dashboard. Database: `under_review`, same coordinator, amendment closed with the note, history `returned → under_review` by the organiser with the note, one `event_resubmitted` notification to the coordinator.
  - As the coordinator again: Under review, both history entries, Approve offered again; a second return with no flags → two amendment rows, one open, and a banner without a field list.
  - At 375×812: the return dialog bug above, fixed and re-checked (heading at +52px, confirm button reachable).
  - Console: the only error is the pre-existing 404 on `GET /events/dashboard/coordinator` (SCRUM-72's endpoint, not built; TC-DASH-001).
  - The fixture was reset afterwards (attendance back to 12, no amendment rows or notifications).
- **Review fixes, in the browser with the live project (25 Sep, organiser signed in; returns done through `return_event_for_amendment` in SQL):** `/events/new?id=…0201` while under review redirected to `/events/…0201`, and the organiser's event count stayed 15 (no duplicate draft); with the dashboard's cached list still saying `under_review`, in-app navigation to the form opened the returned event in amend mode with its banner and flagged field; emptying the flagged equipment note and pressing **Save changes** (`PATCH 200`) left it `NULL` in the database, still `returned`; after the note was put back directly, **Resubmit** with the field empty left it `NULL`, `under_review`, same coordinator, one `event_resubmitted` notification; flagged input, select and description box computed a yellow 30% background, an unflagged input white. No console errors. Fixture reset afterwards.
- **Not verified:** raw `curl` requests as each role against the live API — they need a sign-in with a password, which the agent doesn't enter; the 403/409 denial paths are covered by `pytest` and `test_active_role_access.py` instead. The notification bell (SCRUM-27) doesn't exist, so notifications were checked in the table only. Keyboard focus handling in the new dialogs (same known gap as `RejectEventModal`, IMPLEMENTATION_MAP §5).

### 4.19. Bug fix — Enter did nothing inside a card (PROJECT_REVIEW D13)

Not a Jira story; a fix on `fix/card-enter-key`. Reported by the developer: "improve the log in screen so that keyboard enter can log in without clicking the log in button."

**Symptom.** On `/login`, pressing Enter in the Email or Password field did nothing. Only clicking **Sign In** logged in.

**Reproduction (browser, before the fix).** On a logged-out `/login` with both fields empty, pressing Enter in Email showed no errors, and nothing else changed. Clicking **Sign In** on the same form showed "Email is required." and "Password is required." The DOM was correct: one `<form>` with `@submit.prevent="handleSubmit"`, and the button rendered as `type="submit"` inside it. So the browser's implicit submission should have fired, and something was cancelling it.

**Root cause.** `BauhausCard.vue` listened with `@keydown.enter.prevent="activate"` on its root `<div>` to make `clickable` cards keyboard-operable, but it registered the listener on every card, clickable or not. An Enter pressed in any field inside a card bubbles up to it, and `.prevent` cancels the keydown's default action. The login form sits in a `BauhausCard`, so the browser never submitted it. `activate()` then did nothing, because the login card isn't clickable. **Why tests missed it:** `BauhausCard` had no tests, and jsdom doesn't simulate implicit form submission, so a view-level test of `LoginView` couldn't have caught it either.

**Blast radius.** Every form, field and button inside a card had the same problem. There are four `<form>`s in the app. Three sit inside a card: login, venue search (`VenueCriteriaForm` in `VenueSearchView`) and the event request form. The fourth, TopBar search, isn't in one. So Enter couldn't submit any of those three. The event request's Description box couldn't take a new line, and a focused button inside a card, such as the organiser dashboard's **New event request**, couldn't be pressed with Enter. The coordinator's return/reject/resubmit dialogs and `ConfirmModal` render outside any card and weren't affected. No data was affected.

**Fix.** `@keydown.enter.self.prevent="activate"`: the card handles Enter only when the key is pressed on the card itself. Only a `clickable` card has `tabindex="0"`, so only a clickable card can have focus. An Enter from anything inside a card now reaches the browser. A comment on `activate()` records why. **Behaviour change to know about:** Enter in an event-request field now does what clicking **Submit request** does. It validates the form and, if the form is valid, opens the "Submit event request?" dialog. Nothing is sent until **Confirm and submit**.

#### Verification

- **Written red first:** `components/common/__tests__/BauhausCard.spec.js`. On the old line, the input, textarea and button cases failed (`defaultPrevented` was `true`), and so did "does not activate a clickable card when Enter is pressed in a field inside it" (the card's click fired). "Activates a focused clickable card on Enter" passed before and after; it guards the keyboard access for dashboard tiles. All 5 pass after the fix.
- `npm test`: **35 files, 424 passed**. `npm run build`: passed. `pytest`: **386 passed**. No backend code changed.
- **In a real browser** (Playwright, frontend and backend running locally against the live project; the organiser's stored session was set aside while logged out, then restored):
  - `/login`, empty form, Enter in Email: "Email is required." and "Password is required." appeared, and focus stayed in the field. With an email filled in, Enter in the empty Password field showed only "Password is required."
  - Organiser dashboard: with the **Drafts** tile focused, Enter still opened `?tab=events&status=draft`. With **New event request** (a button inside a card) focused, Enter opened `/events/new`.
  - `/events/new`: the Description box kept `line one\nline two`. Enter in the empty **Event title** showed the required-field errors and opened no dialog. The only API call was `GET /auth/me`, so nothing was saved. The typed text was cleared afterwards.
  - No console errors or warnings.
- **Not verified:** an actual sign-in by pressing Enter, which needs a password, and the agent doesn't enter passwords (TC-AUTH-036 covers it manually). Venue search in the browser, because it's open only to coordinators and venue staff, and only the organiser session was available (TC-VENUE-055). Both go through the same card change the unit tests cover.

### 4.20. SCRUM-80 — Event organiser signup (exact Jira record)

| Field | Value |
|---|---|
| Issue key | `SCRUM-80` |
| Summary | Event organiser signup |
| Issue type | Story |
| Status | To Do (at time of writing this entry) |
| Parent epic | `SCRUM-7` — User authorisation and authentication |
| Sprint | SCRUM Sprint 2 |
| Story point estimate | 3 |
| Priority | Medium |

**User story (verbatim):**

> As an event organiser, I want to signup for  an account at the ConnectSphere platform so that I can create event requests

**Acceptance criteria (verbatim from Jira):**

> 1. **Registration form**
>     * The user can access a sign-up page.
>     * The form requires the user to enter their name, email address, and password.
>     * The user must select/register as an **Event Organiser**.
> 2. **Valid registration**
>     * Given the user provides all required information in a valid format, when they submit the registration form, then an account is created successfully.
>     * The user's role is stored as **Event Organiser**.
> 3. **Email validation**
>     * The system rejects an invalid email format.
>     * The system rejects registration if the email address is already registered.
> 4. **Password requirements**
>     * The system enforces the platform's password requirements.
>     * The system displays an appropriate error message when the password does not meet the requirements.
> 5. **Required fields**
>     * The system prevents registration when any required field is empty.
>     * The user is shown which fields need to be completed.
> 6. **Successful signup**
>     * After successful registration, the user is informed that their account has been created.
>     * The user can log in using their newly registered credentials.
>     * After logging in, the user has access to functionality available to **Event Organisers**, including creating event requests.

(The user story's double space after "signup for" is as written in Jira.)

#### How the implementation maps to the ticket

The design was agreed with the developer on 2026-09-27, before any code was written.

- **Vocabulary.** The ticket says "registration". In this domain *Registration* already means an attendee's place on an event (§6.18, SCRUM-43), so account creation is called **Sign-up** throughout the code and docs (`CONTEXT.md`, "Accounts").
- **Organisers only.** ACC-R2 lets both Organisers and Attendees sign up, but the Sprint 2 goal covers organisers only. Attendee sign-up became its own backlog story, **SCRUM-83**, outside this sprint. The API accepts `role: "event_organiser"` and nothing else; SCRUM-83 widens that to `attendee`. AC1's "must select Event Organiser" is met by the page being an organiser sign-up, with no role picker yet.
- **Accounts are created already confirmed** (AC3, AC6; **ADR-0003**). The live project has email confirmation on. With it on, GoTrue's own sign-up can't report a duplicate email, and a new user can't log in until they click an emailed link. So the backend creates the account with the admin API and `email_confirm=True`, which reports a duplicate as `email_exists` and lets the user log in straight away. The project's confirmation setting was left unchanged. **[Team decision]**, REQUIREMENTS ACC-R7.
- **"The platform's password requirements"** (AC4) weren't defined anywhere. **[Team decision]**: at least 8 characters, with at least one letter and one digit (REQUIREMENTS ACC-R8). The developer set Supabase's minimum password length to 8 to match.
- **Organisation name and phone number.** The ticket lists only name, email and password, but REQUIREMENTS §6.1 and ACC-R5 (QA-90) ask organisers for an organisation name and phone number. Organisation name is required and phone number is optional. Both are stored as plain text on `profiles`. Linking to a client profile (ACC-R5) is deferred, because no client table or story exists yet. **[Assumption]**, REQUIREMENTS ACC-R5.
- **After signing up** (AC6), the user is sent to the login page with a confirmation and their email already filled in, rather than being logged in automatically. Sign-up never opens a session.

What was actually built:

1. **API** — `POST /api/v1/auth/signup` (`modules/auth/router.py`, `service.signup`, `schemas.SignupRequest`). The admin client's `auth.admin.create_user` gets the email, password, `email_confirm=True`, and `role`, `full_name`, `organisation_name` and `phone_number` in `user_metadata`. The business role has to go in `user_metadata`: `AdminUserAttributes` has its own top-level `role`, which is the *Postgres* role. The existing `handle_new_user()` trigger creates the `profiles` and `user_roles` rows. The endpoint returns 201 with the profile read back from `profiles`, plus `roles`.
2. **Errors** — 409 `EmailAlreadyRegisteredError` ("An account with this email already exists."), matched on the `email_exists` code. 503 for `AuthRetryableError`, caught first. 422 naming the field, before Supabase is called, when the role isn't `event_organiser`, a required field is missing or only spaces, the email is malformed, or the password breaks the rule (with one fixed message). An empty phone number is stored as no phone number.
3. **SPA** — `views/SignupView.vue` at public `/signup`, built from the Bauhaus input, button and card components. It checks empty fields, the email's shape and the password rule before sending, using the backend's exact password message. A server 409 shows under Email, a server 422 shows each message under the field its `loc` names, and anything else shows a banner above the form while keeping what was typed. On success it pushes `/login` with the email in history state, so it never appears in the URL.
4. **Login page** — `LoginView` shows "Account created. Please sign in." with the email filled in when it arrives from sign-up, and links to `/signup`. The router guard sends a signed-in user who opens `/signup` to their dashboard, as it already did for `/login`.
5. **`ApiError.detail`** (`services/api.js`) — the response's raw `detail`, so a form can place 422 errors per field. This is additive: `message` and `status` are unchanged.

**Not built, and recorded instead:** a rate limit or captcha on sign-up (PROJECT_REVIEW D14, accepted risk); email verification (ADR-0003); a way for an existing account to add the other external role (REQUIREMENTS ACC-R4).

#### Verification

- **Written red first**, one behaviour at a time, at two agreed seams: the `POST /auth/signup` endpoint with only the admin client mocked (`tests/test_auth.py::TestSignup`), and the sign-up flow through the real router and store with only `@/services/api` mocked (`views/__tests__/SignupView.spec.js`). Each failed for the expected reason first: the route 404, the uncaught `AuthApiError`/`AuthRetryableError`, 201 where 422 was wanted, no field errors, and no redirect for a signed-in user. The invalid-email tests passed as soon as they were written, because `email` was already typed `EmailStr`. Swapping it for `str` made all four fail, so the tests do guard the rule.
- **An email padded with spaces is trimmed at both layers**, so no fix was needed. It was suspected while writing TC-AUTH-047, and the test written to catch it passed at once. The email fields are `type="email"`, whose value the browser strips of surrounding whitespace, and `EmailStr` trims at the API. Setting the field to `type="text"` made the test fail, so it now guards that. The same check showed TC-AUTH-012's expected 401 on login was wrong; that case is corrected.
- `pytest` (full suite): **417 passed**. `npm test` (full suite): **441 passed** across 36 files. `npm run build` succeeds. `router/__tests__/activeRoleAccess.spec.js` failed until `signup` joined its list of routes that need no role list. That test exists to catch exactly this, a new route without `allowedRoles`.
- **Real system, run by the developer on 2026-09-27** against the live project, who reported that everything worked. The checklist: sign up as an organiser in the browser; confirm the new `profiles` row (`event_organiser`, organisation and phone) and `user_roles` row; try the same email again (409 under Email) and a weak password; log in with the new account and reach event-request creation.
- **Not covered by automated tests:** `services/api.js` putting a 422's `detail` on `ApiError`, because the view tests mock the whole module (the live check exercised it).
- **Cleanup:** the developer deleted the test account made during the live check.

#### Review follow-ups (PR #32)

A two-axis review (coding standards; SCRUM-80 spec) found these, fixed on the same branch, each test seen failing first:

- **A password Supabase refuses returned 500.** supabase-auth raises `AuthWeakPasswordError` for GoTrue's `weak_password`, and it is not an `AuthApiError`, so `signup()` never caught it. It is now `SupabasePasswordRejectedError`: 422 with GoTrue's reason on `loc: ["body", "password"]`, which the page already shows under Password (AC4; TC-AUTH-048).
- **Any other `AuthApiError` returned 500.** Rate limits and disabled sign-ups are nothing the user can fix in the form, so they now return 503 like an outage.
- **A missing `profiles` row returned 500.** Sign-up now reads the row through `core.security.load_profile`, the same guarded query `get_current_user` uses, and returns 404 `ProfileNotFoundError` when `handle_new_user()` wrote none.
- **The two password checks disagreed on "digit".** The API used `str.isdigit`, which accepts "²"; the page uses `\p{Nd}`, which does not. The API now uses `str.isdecimal` (ACC-R8 note).
- **Duplicated markup.** The login and sign-up pages share `components/common/AuthPageLayout.vue` for the backdrop and wordmark. The red error banner stays inline: the same markup is already repeated in ten views, which is a wider refactor than this story.
- **Housekeeping.** The sign-up page names `PASSWORD_MIN_LENGTH`. The rule-breaking test passwords are built from their parts.

Left for the team: AC1's "select" an Event Organiser. The page has no role picker, only the organiser subtitle, and SCRUM-83 adds the second option. Whether AC1 needs a picker now is the Product Owner's call.

After the fixes: `pytest` **421 passed**, `npm test` **442 passed**, `npm run build` succeeds.

### 4.21. UI fix — Tech support dashboard navigation and colours

Not a Jira story; a fix on `fix/ui-TechSupportDashboard`. Requested by the developer: make the tech support dashboard follow the other dashboards' colour scheme, and put its tabs in the sidebar.

**Before.** The dashboard switched between its two views with its own tab bar at the top of the page (blue when selected, yellow on hover), and the sidebar showed a single **Dashboard** link. Its status badges used raw Tailwind colours outside the design tokens (`orange-400`, `green-500`, `green-700`). Errors showed as pale red boxes, loading states as yellow bars, and the availability result card turned solid yellow when stock was sufficient. The result card also stayed visible after switching to the inventory view.

**Change.**
- `Nav.vue` shows **Availability** and **Inventory** in place of **Dashboard** when the active role is `tech_support`. They link to `/dashboard/tech-support?tab=availability|inventory`, the same pattern as the organiser's Overview/Events. The check uses the active role, so an account acting as another role doesn't see them.
- `TechSupportDashboard.vue` reads the view from `route.query.tab` and has no tab bar of its own. It loads the inventory the first time that view opens, including a direct link or reload on `?tab=inventory`.
- Badges use the venue-staff dashboard's colours: red for out of stock and insufficient, yellow for under repair and in-progress maintenance, blue for partially reserved, `bauhaus-green` for available and sufficient, white for scheduled maintenance, and muted for completed maintenance. Green now has a second use beyond the venue-staff ACTIVE badge, with the same meaning: this needs nothing from you. Errors use the solid red banner the venue-staff and organiser dashboards use, loading states are neutral, **Refresh inventory** is an outline `BauhausButton`, and the result card is white and shows only on the Availability view.

#### Verification

- **Written red first:** `views/__tests__/techSupportDashboard.spec.js` (4 cases: no in-page tab bar, `?tab=inventory` renders and loads, a sidebar switch loads, token green and no raw colours), plus two `Nav.spec.js` cases (tech support sees both links; another active role holding `tech_support` doesn't). Five failed on the old code for the expected reasons. The sixth, the denial case, passed before the change as a guard.
- `npm test`: **37 files, 448 passed**. `npm run build`: passed. No backend code changed.
- **In a browser** (headless Chrome against the Vite dev server, with a stored tech-support session and no backend running): both views render with the right sidebar item highlighted at 1440px and 390px. With no backend, the error banners showed in the new style. No console errors.
- **Not verified:** the pages with real data. No `.env` was available locally, so I didn't check the inventory table, badges, or availability result against the live project (TC-TSD-013–015 cover them manually).

**Noticed, not fixed (out of scope; recorded as PROJECT_REVIEW D15).** When the inventory fails to load, the table still shows "No equipment matches this filter" and the maintenance panel shows "No maintenance records scheduled" under the error. That is what TC-TSD-011 says must not happen. The equipment picker on the availability form is still a hardcoded list of five seeded IDs, not the inventory endpoint.

**Follow-up on the same branch (developer request).** The developer asked for the page to follow the venue-staff dashboard's layout, with inventory as the main view:
- Inventory is now the default view. Login lands on it, and **Inventory** is first in the sidebar with **Availability** below it. Availability is at `?tab=availability`.
- The yellow welcome card and the large card border around each view are gone. Like `VenueStaffDashboard.vue`, the `py-12` main holds a row of four tiles and then headed sections (`text-2xl`/`sm:text-3xl` headings with a small grey subtitle). Maintenance records and equipment rows are bordered, shadowed list items like the venue-staff pending-request rows.
- The tiles show Out of stock, Under repair, Maintenance scheduled (scheduled or in progress) and Equipment types (with total units). They're computed from the `/equipment/inventory` and `/equipment/maintenance` responses already on the page. Each shows "—" until the inventory has actually loaded, so a failed load never reads as zero (D8, REQUIREMENTS §6.21). Each tile's colour matches the badge for the same status.
- Verification: tests updated red-first (default view is inventory and loads it, `?tab=availability` shows the form without loading inventory, tiles show counts and "—" on failure, Inventory link precedes Availability). `npm test` **37 files, 449 passed**. `npm run build` passed. Headless Chrome at 1440px and 390px showed both views with the seeded figures, served by an in-browser stub of the two equipment endpoints. There were no console errors. The live project still wasn't checked, for the same reason as above.

### 4.22. Chore — Automated live checks and a test execution log

Not a Jira story. An enabler on `chore/automated-live-checks`. It makes every run of the test cases leave a record, and it means a person only runs the cases that need human judgement.

1. **`backend/scripts/verify_live.py`** runs 32 API cases with real requests to a running backend: TC-AUTH-001–003, 006, 007, 010–014, 019–022, 028, 029, 032, 037, 038, 040–044 and 047; TC-RBAC-006 and 007; and TC-ROLE-006–008, 017 and 018. It also runs the seven rolled-back `supabase/verification/` scripts through `supabase db query --linked --project-ref`, which needs only `supabase login` and no `DATABASE_URL`. `event_review_fixture_reset.sql` is left out because it writes.
2. **Playwright specs in `frontend/e2e/`** run 36 browser checks: TC-AUTH-001, 002, 004–006, 008, 009, 026, 030, 031, 036–042, 046 and 047; TC-RBAC-001–005; and TC-ROLE-001–005, 015, 016 and 019. `@playwright/test` is a new dev dependency. Spec files end in `.e2e.js` so Vitest never collects them. The specs run one at a time because they share the seeded accounts and Supabase's sign-in rate limit.
3. **Neither changes seeded or shared data.** They sign in as the seeded accounts, switch roles only in sessions they opened themselves, and log out every session at the end. The SCRUM-80 sign-up checks create throwaway `live-check+…@connectsphere.dev` accounts, and every such account is deleted (cascading to everything it owns) before and after each run. Cases that approve or reject, need a failing server, or change a Supabase setting stay manual (e.g. TC-AUTH-045, TC-AUTH-048, TC-DATA-014). This keeps the live project usable as the demo database (`docs/CI.md` §4 item 3). Neither runs in CI.
4. **Run logs.** `--record` and `npm run test:e2e:record` each write one file per run to `docs/test-cases/runs/`: commit, branch, servers, who ran it, and a row per case. A check that couldn't run is recorded as **Blocked**: after the first sign-in refused with known-good credentials (broken sign-in, or Supabase's per-IP rate limit), no further sign-ins are attempted. A combined run makes 33 correct sign-ins and 4 deliberately wrong ones. Manual browser checks use the template in that folder's README. The log starts on 2026-09-27. Earlier stories' verification stays as the prose in their §4 entries and is not backfilled.
5. **CI test reports.** Both CI jobs write a JUnit report and upload it as a run artifact (`backend-test-report`, `frontend-test-report`), including on failure, kept for 90 days. That is the execution record for the mocked suites.
6. **Process.** Root `AGENTS.md` gains "Live checks and the manual browser pass". At story or fix verification, an agent runs both suites with recording on and automates the story's new cases where a request or browser assertion can check them. It then asks the developer to run the cases that need human judgement (layout, phone width, wording, feel) and records their verdicts. At sprint end, the automated suites are re-run with recording on; there is no sprint-wide manual pass. `DEFINITION_OF_DONE.md` Phases 2 and 3 carry the matching items.

- **Verified:** both suites against the live project, run from this branch on spare ports (backend 8010, frontend 5177), with the run logs in `docs/test-cases/runs/`. No `live-check+` accounts remained after either run. TC-AUTH-013, whose case left the outcome open, was confirmed live: an upper-case email signs in. The JUnit flags were run locally for both suites (pytest 421, Vitest 449), and the workflow YAML parses.
- **Found:** the backend reports Supabase's sign-in rate limit as a 401 "Invalid email or password." (PROJECT_REVIEW **D16**, accepted as low risk: it makes no test case fail and needs many sign-ins from one IP), so the checks can't distinguish a rate limit from broken sign-in. The Blocked handling was exercised against a stand-in backend that refuses every sign-in: one Fail, and every later sign-in check Blocked (13 in the script, 27 in Playwright), with no further sign-in attempts.
- **Not verified:** the artifact upload itself, which first runs on this branch's PR. A run on Windows: the npm scripts avoid shell-specific syntax, but the `E2E_*` variables in the README examples are written for a POSIX shell.


### 4.23. SCRUM-61 — Comment and discuss on my event (exact Jira record)

| Field | Value |
|---|---|
| Issue key | `SCRUM-61` |
| Summary | Comment and discuss on my event |
| Issue type | Story |
| Status | In Progress (at time of writing this entry) |
| Parent epic | `SCRUM-14` — Event Information Management |
| Sprint | SCRUM Sprint 2 |
| Priority | Medium |

**User story and criteria as they stood in Jira (verbatim):**

> As an Event Organiser, I want to add comments and questions to my event record, so that planning conversations are retained alongside the event rather than scattered across email.
>
> Organiser and authorised staff can add comments/questions to an event record.
>
> * Each comment records the contributor and timestamp.
> * Relevant parties are notified of new comments.
> * All discussions are stored as part of the event history.

The criteria are not yet in Given/When/Then form on the issue (Definition of Done, Phase 1); they are numbered AC1–AC4 here and in `docs/test-cases/events.md`.

#### Decisions taken with the developer

- **"Authorised staff"** is the event's assigned coordinator. Readers and posters are the owning organiser and the assigned coordinator, each in that active role, the same readers as the status history (QA2-27 names comments as the organiser–coordinator channel). Venue staff and tech support wait until bookings and equipment requests link them to an event. **[Team decision]**
- **Notifications (AC3)** are written as `comment_added` rows for the other party. There is still no read API or bell; that remains SCRUM-27. **[Team decision]**
- **History (AC4)** is a separate, permanent Discussion thread beside the status timeline, not merged into it; a unified change log remains SCRUM-62. **[Team decision]**
- **When posting is open:** `submitted` to `confirmed`. Rejected, cancelled and completed events keep a read-only thread; a draft has none. **[Team decision]**
- **Body:** plain text, trimmed, 1–1000 characters (**[Assumption]**, REQUIREMENTS §9 Q15). Comments are append-only. No @mentions or resolve (optional per QA-131/132). REQUIREMENTS §9 Q12 (are comments in release 1?) is answered yes.

Design and plan: `docs/superpowers/specs/2026-10-02-scrum-61-event-comments-design.md`, `docs/superpowers/plans/2026-10-02-scrum-61-event-comments.md`.

#### What was built

1. **Data** — migration `20261002120000`: `event_comments` (append-only, author kept as `null` if the profile is deleted), select-only RLS for the organiser and assigned coordinator in their active roles, and `add_event_comment`, a `security definer` function callable only by the backend that locks the event, refuses drafts and closed events by returning no row, and writes the comment and the other party's notification in one transaction. Applied to the live project on 2026-10-02.
2. **API** — `GET` and `POST /events/{id}/comments`, gated by `require_roles(["event_organiser", "event_coordinator"])` and the same `_visible_event` check as `/history`. The comment's `author.role` is derived from the event (owner or assigned coordinator), never from `profiles.role`, so a dual-role account is labelled by the part it plays on that event.
3. **UI** — `EventDiscussion` on the organiser's `EventDetailView` (hidden on drafts) and on `CoordinatorEventView`, backed by `useEventCommentsStore` and the pure rules in `features/events/comments.js`.
4. **Fixtures** — `event_review_fixture_reset.sql` now also clears the two fixtures' comments.

**Found while building:** adding a second `<textarea>` to the coordinator page broke two existing view tests that picked the first one on the page; they now select the modal's as `[role="dialog"] textarea`. The product was unaffected.

**Fixed after the whole-branch review, each written red first:** (1) a 1000-character word stretched the organiser page to about 7,100px at 1440px wide, because `break-words` doesn't lower an element's min-content width inside the page grid; the body now uses `[overflow-wrap:anywhere]`, re-measured in a real browser at 1440px and 375px. (2) Posting on one event and opening another before the reply left **Post** stuck on "Posting…" on every later event page until a reload; switching events now clears the flag. (3) After the comment was committed, the API re-read the whole thread just to get the author's name, so a failed read reported a saved, already-notified comment as an error and invited a duplicate retry; the name now comes from the caller's verified profile.

#### Verification

- **Written red first:** `test_events_repository.py` comment wrappers (`AttributeError`), `test_event_comments_api.py` (404 from the missing routes), `comments.spec.js`, `eventCommentsStore.spec.js`, `EventDiscussion.spec.js` (unresolved imports), and the view tests (panel absent).
- **Suites (after the review fixes):** backend `pytest` 470 passed; frontend Vitest 474 passed in 40 files; `npm run build` succeeds.
- **Real system:** `verify_live.py -k TC-CMT` against this branch's backend and the live database: TC-CMT-008 and TC-CMT-009 pass, which also proves the author embed through `event_comments_author_id_fkey` works on the real schema.
- **Advisors:** no new security findings; the only new performance notes are INFO "unused index" on the two new, still-empty `event_comments` indexes.
- **Recorded live runs (after updating the Supabase CLI from v2.48.3 to v2.119.0):** `verify_live.py --record` 42/42, including `event_comment_checks.sql` (function, notifications, refusals, RLS) — `runs/2026-10-02-1949-api-db-c7d0736.md`; Playwright 36/36 — `runs/2026-10-02-1951-e2e-c7d0736.md`.
- **Manual browser pass (developer, 2026-10-03):** TC-CMT-001, 002, 003, 009, 012, the empty-state wording and both pages at 375px pass — `runs/2026-10-03-0830-manual-c06f7f3.md`.
- **Not verified by hand:** TC-CMT-004 (closed event read-only), which needs the fixture set to `rejected` by SQL; it is covered by `TestPost::test_a_closed_event_refuses_new_comments` and `EventDiscussion.spec.js`.

### 4.24. SCRUM-66 — Reuse a previous or recurring event

**User story:**

> As an Event Organiser, I want to create a new request based on a previous or recurring event, so that I do not have to re-enter unchanged information.

**Scope decision.** The first-release implementation lets an organiser reuse only their own events. `profiles.organisation_name` is descriptive data, not an authorisation relationship, so same-organisation sharing is deferred until client organisations are implemented. The clone creates a draft template; it does not automatically schedule or submit a recurring event.

**What was built:**

1. **API** — `POST /api/v1/events/{event_id}/clone`, guarded by the active `event_organiser` role and the existing owner check. It copies reusable request fields through `service.clone` and creates a new draft through the existing repository path. Dates, registration windows, assignments, workflow state, registrations, notifications, comments, and history are not copied.
2. **Frontend** — `eventsApi.clone`, `useEventsStore.clone`, and **Use as template** actions on organiser event cards. The returned draft is opened in the existing event request form for normal editing and submission.
3. **Traceability** — manual cases TC-EVENT-040–042 were added to `docs/test-cases/events.md`.

#### Verification

- **Written red first:** backend clone tests initially failed with the expected missing-route `404`; the frontend store test initially failed because `store.clone` did not exist.
- Backend focused SCRUM-66 tests: **5 passed** (clone creation, source independence after edit/submit, owner denial, missing-event denial, and non-organiser role denial); full backend suite: **477 passed** with 3 existing deprecation warnings.
- Frontend focused SCRUM-66 tests: **35 passed** across the API adapter, store, organiser dashboard, and mobile menu; full frontend suite: **480 passed** across 41 files; `npm run build` succeeds.
- Browser verification (2026-10-04): the inline copy icon is visible, its action box is `52px` square like **Edit draft**, and clicking it opens a new draft form with copied name and blank date/time fields. At 375px, the two action buttons collapse into a three-dot menu with visible **Edit draft** and **Use as template** options. The throwaway draft was deleted after verification.
- SCRUM-66 clone-specific implementation paths are **100% exercised**: API adapter success/denial, store success/error state, dashboard copy navigation, backend creation, field exclusions, source independence, ownership denial, missing-event denial, and active-role denial. Whole-file reports remain below 100% (`events.js` **98.44%**, `OrganiserDashboard.vue` **97.3%**) because those modules contain unrelated SCRUM-8/33/71 branches; whole-repository 100% coverage is not claimed.
- **Not verified:** live same-organisation/non-owner API denial and the full manual TC-EVENT-041 edit/save/submit flow. No database migration was needed.

### 4.25. SCRUM-72 — Coordinator dashboard on real data, in the organiser's layout

Finishes SCRUM-72 on `feature/scrum-72-coordinator-dashboard-api`. The acceptance criteria are as recorded verbatim in §4.5 (the developer confirmed they are current; the Jira MCP was not connected).

**Before.** The dashboard's store called `GET /events/dashboard/coordinator`, which didn't exist, so every widget read "Awaiting data". §4.5 built it that way on purpose, because the events tables didn't exist then. They do now (SCRUM-8/33/34/52). The coordinator review page (`/coordinator/events/:id`) was reachable only by typing its URL.

**Backend.**
- `GET /events/dashboard/coordinator` (`event_coordinator` only, by active role) returns the shape the store already expected: `action_items`, `active_events`, `unassigned_count`.
- It covers only the caller's assigned events in `under_review`, `returned`, `planning` or `confirmed`; drafts never appear (DR-R2).
- It produces three action kinds: `awaiting_review`, `resubmitted` (AC1's clarification response, QA-22/QA-77), and `arrangement_issue` when technical readiness is `issue`.
- Readiness uses two new service reads, `venues.service.booking_statuses_by_event` and `equipment.service.reserved_event_ids`, so no module reads another's tables.
- The route is declared above `/{event_id}`, which would otherwise answer 422.
- Three rules had no customer answer and are recorded as **[Assumption]** in REQUIREMENTS §6.21.1 and §9 items 16–18: the arrangement-issue signal, equipment readiness before SCRUM-24, and the unassigned count before SCRUM-12. The other action kinds have no data source yet, so they are never produced; nothing is faked.

**Frontend.**
- Every event on the dashboard links to its review page.
- At the developer's request, the page now follows the organiser dashboard (SCRUM-71). The sidebar has **Overview** and **Events** for the coordinator (`?tab=`), from one `EVENT_VIEW_DASHBOARDS` map in `Nav.vue`.
- **Overview** reuses the organiser's header card, category tiles, and paged "by status" cards. It keeps the AC1 prioritised list, the awaiting-assignment alert and the readiness gaps. A tile or status heading opens Events filtered to it.
- **Events** reuses the organiser's filter bar (search, status, sort and direction) and event cards, split into "Needs your action" and "In progress", each with a **Review** button.
- The filtering, sorting and grouping are pure functions in `features/events/coordinatorDashboard.js`. They sit alongside `organiserDashboard.js` rather than reusing it, because the payload is shaped differently. The AC1 category → kinds map moved into `dashboard.js` as `ACTION_CATEGORY_KINDS`, so the tiles and the filter share one definition.
- While loading, the page now shows "Loading events..." instead of dashes in each counter, as the organiser's does. Either way, no zero is shown before the answer is known (TC-DASH-003, reworded).

#### Verification

- **Written red first:**
  - `backend/tests/test_coordinator_dashboard.py` (25 cases: derivation, the repository query shapes including the named organiser FK, the cross-module reads, 200/403 ×4/401, and 200-not-422)
  - `features/events/__tests__/coordinatorDashboard.spec.js` (12)
  - `views/__tests__/CoordinatorDashboard.spec.js` (14)
  - one new `Nav.spec.js` case

  Each failed first because the code didn't exist yet. In the view spec, two link cases already passed after the first half of the work.
- **Full suites:** `pytest` **448 passed**. `npm test` **39 files, 476 passed**. `npm run build` passed.
- **Real API** (this branch on port 8010, live project):
  - As `coordinator@connectsphere.dev`: 200, with the three assigned events (fixtures `…0201`, `…0202`, and one planning event) and `unassigned_count` 7, matching a direct database count. The organiser name resolved through `events_organiser_id_fkey`.
  - 403 as the organiser, 403 after switching to Venue Staff, 401 with no token.
  - `verify_live.py -k TC-DASH`: TC-DASH-013–018 **6/6 passed**.
- **Real browser** (Vite on 5180 against that API): Overview and Events at 1280px and 390px, compared with the organiser's Overview. No horizontal scroll, no console errors. Playwright TC-DASH-001 and 022 passed.
- **Found (DEFECTS D18, open):** TC-DASH-019 failed in 2 of 5 runs. The link was right, but the review page's first two parallel requests both answered 500 (`httpx.ReadError`, WinError 10035, inside `get_current_user` on the shared Supabase client), and the page showed "Failed to fetch" (D10). The code is unchanged by this branch. It is recorded rather than fixed here.
- **Recorded runs** (commit `ff5925e`, servers on 8010/5180):
  - `runs/2026-09-30-1914-api-db-ff5925e.md`: **45/45 passed**.
  - `runs/2026-09-30-1915-e2e-ff5925e.md`: **37 passed, 2 failed**. TC-DASH-019 and TC-ROLE-005 both failed on server errors in the shared Supabase client (the review page, then the dashboard and a role switch), not on anything they assert about. That is recorded under D18. Neither was re-run to make it pass.
- **Not verified:** TC-DASH-020 (return and resubmit a fixture, because it changes shared data) and the arrangement-issue path in a browser (nothing in the UI can set technical readiness yet; it is covered by pytest only). The visual cases TC-DASH-002, 003, 005 and 024 are waiting on the developer's manual pass.
- **Noticed, not fixed:** `IMPLEMENTATION_MAP.md` still says `modules/equipment/` is an empty package and lists the equipment branches as unmerged, but the equipment module is on `main`.

**Follow-up on the same branch: unassigned events move to the Event Coordinator Lead** (customer clarification of 2026-10-05, QA row to be added). The customer introduced an Event Coordinator Lead who assigns submitted requests from an unassigned queue, so a coordinator no longer needs to see unassigned events. The branch is now `fix/scrum-72-coordinator-dashboard-api`.
- The developer removed the "Urgent — awaiting assignment" alert from the Overview (`b9065e5`).
- A code review then found what that left behind: the view spec still expected the alert (the frontend suite failed), the test cases still described it, and the endpoint still ran a count query every load for a figure nothing showed.
- Now removed end to end: `unassigned_count` from `CoordinatorDashboard`, `count_unassigned` and `UNASSIGNED_STATUSES` from the events module, and `unassignedCount` from the store.
- TC-DASH-012 and TC-DASH-015 now check that the coordinator sees nothing about unassigned events, and the live check TC-DASH-015 asserts the response has no such field.
- REQUIREMENTS §6.5 records the clarification as superseding AS-R1, AS-R3 and AS-R5 until the Lead story rewrites that section. §9 item 18 is resolved, and item 18 lists what the clarification leaves open.
- **Verification:** the tests were changed first and failed for the expected reasons (15 backend, because the service still called the removed query, and 1 store case), then passed. `pytest` **448 passed**, `npm test` **39 files, 476 passed**, `npm run build` passed. Live checks at `db0f8c4`, on a freshly started backend on 8010:
  - `runs/2026-10-05-1102-api-db-db0f8c4.md`: **45/45 passed**, including the reworded TC-DASH-015.
  - `runs/2026-10-05-1103-e2e-db0f8c4.md`: **37 passed, 2 failed**. TC-DASH-019 and TC-ROLE-003 failed on server errors in the shared Supabase client (D18), which occurred on the review page and on a role switch. Neither was re-run to make it pass.
- **Merged with `main`** before opening the PR: SCRUM-61 (comments) and SCRUM-66 (clone) had changed the same events files, so their code was kept alongside the dashboard. `main` had already used D17 and §9 item 15, so this branch's defect became **D18** and its §9 items became 16–19. Commit messages and the run logs above still say D17 for the shared-client defect, because they were written before the merge.

### 4.26. SCRUM-19 — Venue booking request

| Field | Value |
|---|---|
| Issue key | `SCRUM-19` |
| Summary | Venue Booking Request |
| Issue type | Story (1 point) |
| Status | To Do (at time of writing this entry) |
| Parent epic | none |
| Sprint | SCRUM Sprint 2 (ends 2026-10-05; carries over) |
| Priority | Medium |

**User story as it stood in Jira (verbatim):**

> An Event Coordinator can submit a request to book a venue for an event. The request should contain the relevant event timing and venue requirements needed by Venue Staff to assess the booking.

The issue had no acceptance criteria. Six were written from REQUIREMENTS §6.12 with the developer and added to the issue on 2026-10-05, each citing its `QA-<row>`. They are AC1–AC6 here and in `docs/test-cases/venues.md`. They cover the tentative hold, overlap refusal including blocks, first come first served, one venue per event, planning only, and the assigned coordinator acting as coordinator.

#### Decisions taken with the developer

- **Trimmed to the 1-point core** after comparing the full §6.12 scope with past estimates:
  - Suitability (BR-R3) moves to SCRUM-18.
  - The venue-staff request page moves to SCRUM-20/36.
  - Cancelling a hold (BR-R5) becomes a follow-up story, which the developer is raising.
  - The block check stayed in, because it is one query and SCRUM-21 has no owner. Recorded in REQUIREMENTS §6.12 (scope note, BR-R7–R9).
- **The period is the event's own**, never the client's (BR-R7). **[Team decision]**
- **Every refusal is decided in the database** under a lock on the event, so concurrent requests resolve first come, first served (BR-R8). **[Team decision]**
- **The note** is optional, ≤ 1000 characters after trimming (BR-R9, §9 Q20). **[Assumption]**
- **Venue staff are notified as a pool:** every `venue_staff` holder except the requester (AUTH-R5, NT-R1).
- **Organisers don't see booking state** on their event read (AUTH-R2). **[Team decision]**
- **Test seams agreed with the developer:**
  - the HTTP API (pytest, repositories faked);
  - the database function (a rolled-back SQL script against the live project);
  - the frontend store's `request()` (Vitest).

  The Vue templates are covered by the e2e and the manual pass.

#### What was built

1. **Data**
   - Migration `20261005120000`: `venue_bookings.request_note` and `requested_by`.
   - `request_venue_booking`, a `security definer` function callable only by the backend. It locks the event, then refuses with an outcome code in this order:
     - a missing event;
     - a `returned` event;
     - any other non-planning event;
     - a caller who isn't the assigned coordinator;
     - an event with no start and end time (`no_period`);
     - an unknown venue;
     - an event that already has a venue;
     - an overlapping block.
   - It then inserts the `held` booking over the event's period. DB-1's exclusion violation becomes `held_by_other`, as does a deadlock between two simultaneous overlapping inserts. The unique-index violation becomes `already_booked`.
   - It notifies venue staff in the same transaction.
2. **API**
   - `POST /venue-bookings`, gated on the active role `event_coordinator`, checks the assigned coordinator through `events.service.assigned_event` (new public wrapper) and maps each outcome to 201 / 409 / 403 / 404.
   - The coordinator's `GET /events/{id}` now carries `venue_booking`.
3. **UI**
   - A **Venue** panel on `CoordinatorEventView`.
   - `/venues?event=<id>`, which pre-fills the search from the event in Singapore time and offers **Request this venue** on available results only while the search checks the event's own period.
   - `RequestVenueModal`, which takes a note and shows a refusal inline.
   - `useVenueBookingStore`, `features/venues/bookingRequest.js`, and an `actions` slot on `VenueResultCard`.
4. **Checks**
   - `supabase/verification/venue_booking_request_checks.sql`.
   - `verify_live.py` TC-BOOK-001–007, which create throwaway "live-check …" events in 2031 and delete them before and after the run.
   - Playwright `bookings.e2e.js` TC-BOOK-008.

**Found while building:** two existing tests (`test_event_review_api.py`, `test_event_amendment_api.py`) read an event as a coordinator. Once that read also looked up the venue booking, they reached for the real network. Their fixtures now fake `venues.repository.get_active_booking` like every other repository call.

#### Verification

- **Written red first, each for the expected reason:**
  - **SQL checks, one slice at a time:**
    - the function didn't exist;
    - the overlap raised `23P01`;
    - a request into a maintenance block was accepted;
    - a second venue raised `23505`;
    - a returned event was accepted;
    - no notification was written.

    The grant check was added after the grant and was never red.
  - **API tests:**
    - the repository function was missing;
    - the outcomes were ignored, so the booking was built from `null`;
    - lifecycle and race outcomes were unmapped;
    - `venue_booking` was missing.
  - **Store spec:** the module was missing.
  - **Tests that passed on first run:** the authorisation and body-validation tests reuse existing guards, so they were green immediately. A mutation check (letting `venue_staff` through the router guard) made the role tests fail as they should.
- **Suites:** backend `pytest` 535 passed; frontend Vitest 44 files, 510 passed; `npm run build` succeeds.
- **Database:** the migration and `venue_booking_request_checks.sql` pass together inside one rolled-back transaction on the live project. Afterwards the live database has no new column or function.
- **Manual browser pass (developer, 2026-10-05):** TC-BOOK-008–013 all pass, at desktop and 375px. The run log is `runs/2026-10-05-1900-manual-f9852a8.md`. The migration, advisors and recorded automated runs are below.
- **Safety review before applying the migration**, at the developer's request. It found two gaps, now fixed:
  - **A planning event without times** had an unbounded period. It was wrongly refused as `blocked` by an unrelated block, and on a venue with no blocks it would have raised a check-constraint error (500). This was written red first: the SQL check failed with outcome `blocked`. It is now the `no_period` outcome, answered with a 409. No live event is affected today, because submission requires times.
  - **A deadlock between two truly simultaneous overlapping inserts.** An exclusion constraint is checked after the insert, so Postgres can end that race with `40P01` instead of the exclusion violation. The deadlock is now caught as `held_by_other`. A single session can't produce it, so it wasn't written red. TC-BOOK-007 exercises it live.
- **Also checked in the review:**
  - The columns are nullable, and the 4 existing rows pass the new constraints.
  - The `venue_bookings` lock lasts only for the `ALTER` on a 4-row table.
  - RLS on `venue_bookings` (internal staff read only, no write policies) covers the new columns.
  - The function is `service_role` only, with a pinned `search_path`.
  - Locks are taken in the same order as `transition_event` (event row, then bookings).
  - The migration ledger matched the local files with only `20261005120000` pending.
  - Every existing script in `supabase/verification/` passes with the migration applied in one rolled-back transaction.
  - Advisor baseline before applying: 9 WARN `auth_rls_initplan`, 1 WARN leaked-password protection, 5 INFO unused index, all pre-existing.
- **Applied to the live project** on 2026-10-05 with `supabase db push` (dry run first: only this migration, no seeds); the ledger now lists `20261005120000` as remote. `venue_booking_request_checks.sql` passes against the applied function. **Advisors after:** one new finding, INFO "unused index" on the new `venue_bookings_requested_by_idx`; no new security or WARN findings.
- **Recorded live runs** (servers on 8010/5177, working tree uncommitted on top of `f9852a8`, so the logs name that commit):
  - `runs/2026-10-05-1851-api-db-f9852a8.md`: **56/56 passed**, including TC-BOOK-001–007 and the simultaneous-request race. Afterwards no "live-check" event or block was left, and `venue_bookings` was back to its 4 rows.
  - `runs/2026-10-05-1853-e2e-f9852a8.md`: **39 passed, 1 failed**. TC-BOOK-008 passed. TC-DASH-019 failed with "Failed to fetch" on the review page. The backend log shows 5 server errors, all `httpx.ReadError: [Errno 35]` in the shared Supabase client (`resolve_active_role`, `events.repository.get_event`), none in the new booking code. This is D18, now also seen on macOS, and was not re-run to make it pass.
- **Fixture reset extended.** The manual pass requested a venue for review fixture `…-0201` after approving it, which left a hold the reset script didn't know about: it would have reset the event to `under_review` while it still held Boardroom Orchid. `event_review_fixture_reset.sql` now also deletes any booking on the two fixtures other than the seeded `d0000000-…-0201`.
- **Follow-up raised:** cancelling a hold (BR-R5) is **SCRUM-85**, linked to SCRUM-19 in Jira.

### 4.27. SCRUM-45 — Record and submit an event equipment request

Built on `feature/scrum-45-equipment-request`, branched from `main` at `f9852a8`. The developer pasted the user story and acceptance criteria, then revised them after a conflict check. The Jira MCP was not connected.

**Story.** As an Event Coordinator, I want to specify and submit the types, quantities, and technical requirements of equipment needed for an event, so that I can request the necessary hardware from Technical Support Staff to ensure the event is properly equipped.

**Acceptance criteria (as revised by the developer).**
1. An Event Coordinator assigned to an event can add items from the equipment catalogue and specify a quantity for each.
2. Each item can optionally include technical requirements (up to 1,000 characters), which are saved and shown to Technical Support Staff.
3. Quantity must be a whole number of at least 1.
4. A submission must contain at least one item.
5. If a quantity exceeds the item's total catalogue inventory, a warning is shown when the quantity is entered, but the request can still be submitted.
6. On submission, each submitted line gets status "Pending" and is visible to Technical Support Staff and to the submitting Coordinator. All lines in one submission are saved together, or none are.
7. A request is only accepted for an event that is assigned to the submitting Coordinator and is in planning status (QA-22).

#### Decisions taken with the developer

- **Conflict found before planning:** the first draft of AC5 blocked submission above inventory, which contradicted EQ-R1. The developer revised AC5 to warn-and-allow, so EQ-R1 stands and there is no deviation to record.
- **Status is per line, submitted as a batch** (lines share a `submission_id`), not a request-level status. This matches the data model, §6.6 readiness and SCRUM-24.
- **Out of scope this sprint:** notifying tech support, editing or deleting pending lines (EQ-R4), and tech support's sortable queue. Tech support get a read-only list instead.
- AC1 and AC7 are revisited next sprint with the Event Coordinator Lead's assignment queue (§6.5).
- **Don't merge SCRUM-19** (under review) into this branch. Rebase onto `main` once it lands. Because the live project already had SCRUM-19's migration, the developer chose to **wait for SCRUM-19** before applying this story's migration. Once SCRUM-19 merged (PR #40), the branch was rebased onto `main` (`3fff160`): only docs conflicted, plus `events.service.assigned_event`, which both stories had added with the same behaviour, so `main`'s was kept. The §9 assumptions became item 21 and this entry §4.27, because SCRUM-19 had used item 20 and §4.26.
- Five smaller rules had no answer and are recorded as **[Assumption]**s in REQUIREMENTS §9 item 21: one line per item, 50 items at most, "submitting" read as "assigned" coordinator, retired items not requestable, and closed events' lines hidden from tech support.

#### What was built

- **Database** (`20261006120000_equipment_requests.sql`):
  - enum `equipment_request_status`, with all five §6.15 values
  - table `equipment_requests`, with quantity ≥ 1 and technical requirements of 1–1000 characters after trimming, both enforced by the table
  - select-only RLS on the active role (`private.current_user_role()`)
  - `submit_equipment_request`: locks the event, re-checks that it exists and isn't a draft, the assignment and `planning` (with its own outcome for `returned`), then the catalogue. It inserts the batch in one statement and returns an outcome code rather than raising. Only `service_role` can execute it.
- **Backend** (`modules/equipment`):
  - `GET /equipment/catalogue` (coordinator, tech support)
  - `POST /equipment/requests` (coordinator)
  - `GET /equipment/requests/event/{id}` (assigned coordinator)
  - `GET /equipment/requests/pending` (tech support)
  - The assignment check reuses `_assigned_event` through a new public `events.service.assigned_event`.
  - Errors are typed in `core/exceptions.py`.
  - The service checks the catalogue before calling the function, so the 422 can name the offending item. The function checks again under the lock.
- **Frontend:**
  - `features/equipment/` holds the pure rules, `useEquipmentRequestStore` and `useEquipmentQueueStore`.
  - `EquipmentRequestPanel` on `CoordinatorEventView`. The EQ-R1 warning reuses `BauhausInput`'s `flag` prop: a yellow "review this" note, not a red error.
  - `PendingEquipmentRequests` replaces the "No request workflow yet" placeholder in the tech-support dashboard's **Active requests**.
- **Verification assets:**
  - `supabase/verification/equipment_request_checks.sql`, rolled back after it runs
  - `verify_live.py` TC-EQR-001, 002, 004, 008, 009. TC-EQR-002 writes one marked line on fixture `…0202` and deletes it in the same run, as agreed with the developer.
  - `frontend/e2e/equipment.e2e.js`
  - The fixture reset script now also clears request lines.
- **Docs:** `docs/test-cases/equipment.md` (TC-EQR-001–013); REQUIREMENTS §6.15 SCRUM-45 note and §9 item 21; IMPLEMENTATION_MAP (also corrects the stale SCRUM-23/73 entries noted in §4.25); DEFECTS **D19**.

#### Verification

- **Written red first:**
  - `backend/tests/test_equipment_requests_api.py` (62 cases). It failed because the repository functions didn't exist.
  - `features/equipment/__tests__/equipmentRequest.spec.js` (29) and `equipmentRequestStore.spec.js` (8). Both failed because the modules didn't exist.
  - `components/equipment/__tests__/EquipmentRequestPanel.spec.js` (13)
  - three new `techSupportDashboard.spec.js` cases. They failed on the placeholder.
- **Full suites:** `pytest` **574 passed**, including the active-role matrix over the four new routes. `npm test` **46 files, 560 passed**. `npm run build` passed. After the rebase onto SCRUM-19: `pytest` **606 passed**, `npm test` **47 files, 563 passed**, build passed.
- **Live project** (after the rebase): `supabase db push --dry-run` listed only `20261006120000`; it was applied with `supabase db push` and `supabase migration list --linked` matches. `supabase db advisors --linked` reports nothing on the new table or function; its 9 `auth_rls_initplan` warnings are all on the SCRUM-23 write policies (D19), plus the known leaked-password-protection warning.
- **Recorded runs** (commit `3fff160`, servers on 8010/5180):
  - `runs/2026-10-05-2250-api-db-3fff160.md`: **62/62 passed**, including TC-EQR-001, 002, 004, 008, 009 and `equipment_request_checks.sql`. TC-EQR-002 exercised the real PostgREST embeds and deleted its line; the live table was empty afterwards.
  - `runs/2026-10-05-2253-e2e-3fff160.md`: **41 passed, 1 failed**. Both SCRUM-45 specs passed. TC-ROLE-003 failed because `POST /auth/active-role` answered 500 (`httpx.RemoteProtocolError: Server disconnected` in the shared Supabase client), which is D18. In the same run, the coordinator event page's two new equipment reads also answered 500 once during TC-BOOK-008, which still passed. Not re-run to get a pass.
  - Local `node_modules` had no `@playwright/test` (SCRUM-19 added it); `npm install` from the unchanged lockfile and `npx playwright install chromium` fixed that.
- **Manual browser pass** by the developer: TC-EQR-003, 005, 006, 012 and 013 all **passed** (`runs/2026-10-05-2332-manual-a9bd1a9.md`). It submitted five lines on the planning event *test approve*, not on a fixture.
- **Not verified:** a coordinator who isn't assigned to the event, against the live API, because the seed has only one coordinator (`pytest` and `equipment_request_checks.sql` cover it).
- **Noticed, not fixed:**
  - **D19**: the SCRUM-23 equipment tables' write policies don't follow the active role.
  - No data module maps a Supabase outage to 503 (only auth does), so an outage here is a 500, like everywhere else.
  - `TechSupportDashboard`'s maintenance times are formatted in UTC, not Singapore time.

### 4.28. SCRUM-63 — Update venue capacity and facilities information

Built on `feature/scrum-63-edit-venue-details`, branched from `main` at `f9852a8`. The developer pasted the user story and acceptance criteria directly; the Jira MCP was not available in this environment.

**Story.** As a Venue Staff, I want to update a venue's detail, so that I don't get booking requests based on outdated details that I then have to reject or renegotiate.

**Acceptance criteria (as given).**
1. Can edit details for an existing venue.
2. Changes are reflected immediately in future venue searches and suitability checks.
3. Reducing capacity below the expected attendance of an existing tentative/confirmed booking triggers a warning.
4. Previous values remain visible in the venue's change history.

#### Decisions taken with the developer

- **Edit scope: the full profile**, not just capacity and facilities (the title's narrowest reading) — name, location, capacity, per-layout capacity, facilities, accessibility, hours and description. `is_active` is excluded; REQUIREMENTS §6.8 implies that is its own story (SCRUM-64, deactivate/reactivate).
- **Warning scope: the full VC-R2 rule**, not just the capacity-vs-attendance case the acceptance criteria describe. Capacity, a dropped required facility, a dropped preferred layout, or hours that no longer cover a booking's time all warn, each compared against what the edit newly breaks (not a pre-existing mismatch).
- **Added `venues.version` for optimistic concurrency** (DB-5), matching `events.version` — IMPLEMENTATION_MAP flagged that as "the only pattern so far — copy it, don't invent a second scheme."
- These were presented as a short in-chat design (the brainstorming skill's **bounded** path: an existing, well-established module being extended, not a new subsystem) and approved before any code was written.

#### What was built

- **Database** (`20261006130000_venue_edit_and_history.sql` — renamed from an initial `20261006100000` once rebasing onto `main` revealed two migrations, from the now-merged SCRUM-19 and SCRUM-45, with later 2026-10-06 timestamps already live):
  - `venues.version`
  - table `venue_edit_history` (`venue_id`, `actor_id` set null, `before jsonb`, `after jsonb`, `created_at`); select-only RLS, same readers as `venues`
  - `public.update_venue(...)` returning `setof venues` — `security definer`, `service_role` only, same one-transaction shape as `transition_event`: version-checked update, replaces `venue_layouts`/`venue_facilities`, inserts the history row, inserts a `venue_updated_affects_booking` notification per affected event's coordinator
- **Backend** (`modules/venues`):
  - `impact.py` (pure, no I/O): `affected_bookings(before, after, bookings)` — diffs *before* vs *after* venue state per booking and reports only newly-broken rules, so a pre-existing mismatch the edit didn't cause is never reported. Reuses a new shared `search.effective_capacity` (extracted from `search._criteria_reasons`, which previously inlined the same per-layout-capacity lookup VS-R6 already names)
  - `events.service.planning_context_by_id(ids)` / `events.repository.list_planning_context` — the cross-module lookup `venues.service` uses to get each booking's event's `expected_attendance`/`layout_preference`/`facilities_required`/`coordinator_id`, following the same pattern as the existing `names_by_id`
  - `PATCH /venues/{venue_id}` (venue staff only) and `GET /venues/{venue_id}/history` (coordinator or venue staff) — `venues.service.update_venue`/`venue_history`
  - `VenueConflictError` (409) added to `core/exceptions.py`, not as a module-local class (unlike `events.service.EventConflictError`, an existing inconsistency not copied here)
- **Frontend:**
  - `VenueEditView` at `/venues/:id/edit` (venue-staff only route), built from `BauhausInput`/`BauhausCheckboxGroup`
  - `VenueEditWarningModal`, a sibling of `RejectEventModal`, naming the affected events and reasons
  - `useVenueEditStore` (load/submit/loadHistory, mirroring `eventReviewStore`'s stale-response-drop pattern)
  - `venueToEditForm`/`editFormToPayload`/`summariseEditHistoryEntry` added to `venueProfile.js`
  - An **Edit venue** link (venue staff only) and a **History** tab added to `VenueDetailView`
- **Verification assets:** `supabase/verification/venue_edit_checks.sql`, rolled back after it runs; `verify_live.py` DB_SCRIPTS entry; `docs/test-cases/venues.md` TC-VENUE-056–064 plus a Traceability — SCRUM-63 table.

#### A stale fixture found during live verification

The first full `verify_live.py --record` run (before this story's own migration, just after rebasing onto the merged SCRUM-19/45) failed two unrelated cases — TC-BOOK-005 and TC-EQR-008 — both expecting fixture event `e0000000-…-0201` to still be `under_review`. It was found in `planning` with a stray `held` booking on Heritage Hall, most likely left over from an SCRUM-19/45 manual pass that didn't run the reset script afterwards. `supabase/verification/event_review_fixture_reset.sql` (pre-existing, documented exactly for this) fixed it; the re-run passed 63/63. Not this story's bug, but worth recording since it could otherwise read as one.

#### Verification

- **Written red first:** `backend/tests/test_venue_impact.py` (18 cases, failed on the missing module), additions to `backend/tests/test_venues_api.py` (`TestVenueEdit`, `TestVenueEditHistory`), `frontend/src/features/venues/__tests__/venueProfile.spec.js` and a new `venueEditStore.spec.js`.
- **Full suites, after merging the now-updated `main` in:** `pytest` **634 passed**. `npm test` **578 passed** (one `TopBar.spec.js` timeout under full parallel load, confirmed a pure flake by an isolated re-run). `npm run build` passed.
- **Live project:** migration applied with `supabase db push` (`supabase migration list --linked` matches). `venue_edit_checks.sql` passed in a rolled-back transaction, including the RLS checks (coordinator and venue staff read the history, organiser and anon do not). Full `verify_live.py --record`: **63/63 passed** (`runs/2026-10-06-1733-api-db-fd4f351.md`). `npm run test:e2e:record`: **40/42 passed**; the two failures (`TC-EQR-005/006`, `TC-ROLE-003/004` — neither touches venues) were confirmed a parallel-load flake by an isolated re-run (9/9 passed) (`runs/2026-10-06-1745-e2e-fd4f351.md`).
- **Not verified:** no dedicated e2e spec exercises the new edit screen itself (the warning dialog, the confirm round trip, the History tab) — covered by `pytest`, Vitest and the SQL check, but not by Playwright. The manual browser pass (TC-VENUE-056, 057, 060, 062, 063) is the developer's, per root AGENTS.md.
- **Noticed, not fixed:** the IMPLEMENTATION_MAP rows for SCRUM-19 and SCRUM-45 still say "not yet merged" although both are on `main` (PRs #40, #41) — stale, left alone as out of this story's scope.


### 4.29. D20 — Align venue-staff summary cards when text wraps

Built on `fix/venue-dashboard-card-alignment` from current `origin/main` at `37f2d0b`, 2026-10-06. The developer reported unequal summary-card heights with a screenshot and approved equal-height rows with two-line heading/detail space and responsive columns.

**Reproduction and cause.** The new real-browser case TC-VSD-035 failed before the implementation: at 1440px the cards differed by 16px. Grid wrappers filled their row, but the inner `BauhausCard` borders followed their own content heights, and a wrapped heading pushed its figure down. A further boundary check reproduced misaligned figures at 640px because the desktop sidebar squeezed two columns.

**Change.** Reused `BauhausCard` without changing its shared API: `h-full` on these four instances, `min-h-8` / `leading-4` on their labels and details, and one/two/four columns at base/md/xl breakpoints. Minimum heights preserve wrapping and content growth. Existing text, counts, accents and the pending-list link remain intact. REQUIREMENTS §6.21.2 records the approved layout decision; IMPLEMENTATION_MAP and dashboards.md now reference D20/TC-VSD-035.

**Verification.**

- Full frontend unit suite: **578 passed**; production build passed, including after the final breakpoint adjustment.
- Full backend suite: **634 passed**, three dependency deprecation warnings. The initial sandbox run stalled on its first test and was interrupted; the host run completed normally.
- Chromium regression measures actual card heights, number/detail alignment, clipping and page overflow at **1440, 1280, 1100, 768, 640, 375 and 320px**, after sidebar transitions settle. Also checks the existing focus cue does not change the tile height and Enter still opens `#pending-requests`. Desktop screenshot inspected; no page JavaScript errors.
- Final recorded focused browser run: **2/2 passed**, TC-VSD-035 and the existing coordinator dashboard route-denial case TC-RBAC-003 (`runs/2026-10-06-1936-e2e-37f2d0b.md`). A temporary local config disabled global setup only for these read-only cases, with session logout still performed by fixtures; it is not shipped.
- Available live API cases: **40/40 passed** with `--skip-db --record` (`runs/2026-10-06-1933-api-db-37f2d0b.md`). Database-dependent signup and booking cases were skipped explicitly.
- Live Supabase tables and all 21 migrations inspected through MCP. Existing advisor warnings remain: leaked-password protection disabled and nine equipment-policy initplan warnings (D19), plus informational unused indexes. No schema or data changes were made by this fix.

**Not verified.** Both required full live commands were attempted, but the Supabase CLI is absent (`ENOENT`): the full API/database script stopped before recording and Playwright stopped in global setup. Its new run record (`runs/2026-10-06-1932-e2e-37f2d0b.md`) explicitly records the block instead of the reporter's known misleading “0/0 passed” (D17). Full database-dependent verification still needs a configured CLI. The developer was asked to check TC-VSD-035 (desktop alignment), TC-VSD-015 (375px readability) and TC-VSD-034 (hover/focus feel); no manual verdict has been supplied yet. No manual pass is claimed. PR, review, merge and Jira updates remain developer-owned.
