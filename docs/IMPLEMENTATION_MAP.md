# Implementation Map

**What exists right now, and what to know before building on it.**

This file describes the **current state** of the codebase, so a developer (or AI agent) starting a new story can see what to reuse and what to watch out for. It is edited in place: when something changes, update or remove the entry.

- For the *history* of how each story was built, see `docs/SCENARIO.md` §4 (append-only).
- For *what the system should do*, see `docs/REQUIREMENTS.md`.

**Update this file after implementing anything that changes what exists** (see root `AGENTS.md`, "Keep the paper trail current").

_Last updated: 2026-09-19. Reflects `main` at `eb6bf55` (after PR #13), plus unmerged branches listed in §6, plus the in-progress `feature/scrum-70-venue-staff-dashboard` branch described below._

---

## 1. Status by story (on `main`)

| Story | Status | Backend | Frontend | Database |
|---|---|---|---|---|
| SCRUM-48 Basic user authentication | Done | `modules/auth` | `LoginView`, `stores/auth.js`, router guards | `profiles` |
| SCRUM-50 See my own profile | Done in Jira; see open defect D7 in §5 | `GET /auth/me` | `ProfileView` (also lists every held role for a multi-role account — see SCRUM-78 below) | `profiles` |
| SCRUM-74 View assigned roles in nav dropdown, SCRUM-75 Select active role from nav dropdown | On `feature/scrum-74-75-role-switcher` (ACC-R4) | `POST /auth/active-role`, `roles` on `ProfileResponse`, session-scoped active role in `get_current_user` | Role switcher in `Nav.vue`, `roles`/`hasMultipleRoles`/`setActiveRole` in `stores/auth.js` | `user_roles`, `session_active_roles` |
| SCRUM-78 View all assigned roles on profile page | On `feature/scrum-74-75-role-switcher` (ACC-R4); implemented ahead of ticket creation during SCRUM-74/75's code review, ticket opened retroactively for traceability | none (reuses `roles` on `ProfileResponse`) | "All Roles" section in `ProfileView.vue`, shown only via `authStore.hasMultipleRoles` | none (reuses `user_roles`) |
| SCRUM-39 View venue catalogue | Done | `modules/venues` | `views/venues/`, `features/venues/venueSearchStore.js`, `components/venues/` | venue tables |
| SCRUM-72 Event Coordinator dashboard | Frontend done. **No backend endpoint yet**, so widgets show empty states | none | `CoordinatorDashboard`, `features/events/` | none |
| SCRUM-70 Venue Staff dashboard | On `feature/scrum-70-venue-staff-dashboard`. **Fully data-driven** — the first dashboard that is | `GET /venues/dashboard/venue-staff` | `VenueStaffDashboard`, `features/venues/`, `components/venues/VenueCalendar.vue`, `/bookings/:id` stub | `venues`, `venue_blocks`, `venue_bookings` |
| SCRUM-71, 73 and the attendee dashboard | Placeholder shells only (~40 lines each), still showing hardcoded metrics (D8) | none | `views/dashboards/*Dashboard.vue` | none |
| SCRUM-8 Event request creation | On an unmerged branch (§6) | — | — | — |
| SCRUM-70, 71, 73 and the attendee dashboard | Placeholder shells only (~40 lines each) | none | `views/dashboards/*Dashboard.vue` | none |
| SCRUM-8 Event request creation | Implemented on `feature/scrum-8-event-request`; pending merge | `modules/events`: draft, read, update, discard, and submit endpoints with validation | `EventRequestView`, `EventDetailView`, organiser request navigation, timezone-aware event form | `events` table plus corrective registration-boundary and event-timezone migrations |
| SCRUM-23 Equipment availability | On an unmerged branch (§6); PRs #4 and #5/#6 closed | — | — | — |

## 2. Backend (`backend/app/`)

### Endpoints (all under `/api/v1`)

| Method and path | Guard | What it does |
|---|---|---|
| `POST /auth/login` | public | Signs in and returns tokens and profile (`role` = this session's active role, `roles` = every role the account holds) |
| `POST /auth/refresh` | public (refresh token) | Rotates the session |
| `GET /auth/me` | authenticated | Returns the current user's profile, including `roles` |
| `POST /auth/active-role` | authenticated | Switches the caller's session to a role it holds (SCRUM-75); 403 if the role isn't in `user_roles` |
| `POST /auth/logout` | authenticated | Revokes only the caller's session |
| `GET /venues` | `event_coordinator`, `venue_staff` | Searches the catalogue. Each criterion is strict. `starts_at`/`ends_at` adds an availability check, and `include_excluded=true` also returns ruled-out venues with reasons |
| `GET /venues/{venue_id}` | `event_coordinator`, `venue_staff` | Returns one venue with its upcoming blocks and occupying bookings |
| `GET /venues/dashboard/venue-staff` | `venue_staff` only | The venue-staff work queue across **every** venue (AUTH-R5): pending holds oldest-first, bookings in re-review, active and upcoming blocks, and the venue catalogue. Declared **above** `/{venue_id}`, which is typed `UUID` and would answer 422 rather than fall through |

`modules/events/` and `modules/equipment/` are empty packages (`__init__.py` only). Build inside them rather than creating new top-level modules.

### Reusable building blocks

| Need | Use | Location |
|---|---|---|
| Current user (verified JWT plus profile row) | `get_current_user`, `CurrentUser` (`role` is this session's active role, not necessarily `profiles.role`) | defined in `app/core/security.py`; **import from `app.modules.auth.dependencies`** |
| Role gate | `require_roles([...])`, wrapped in a named alias per access level (e.g. `VenueReader`) | same as above; pattern in `venues/router.py` — checks the session's active role |
| Session-scoped active role (SCRUM-75) | `resolve_active_role(admin_client, session_id, default_role)` | `app/core/security.py` |
| Role membership and switching (ACC-R4, SCRUM-74/75) | `get_roles(profile_id)`, `set_active_role(current_user, role)` | `modules/auth/service.py` |
| Typed HTTP errors | `InvalidCredentialsError` (401), `InvalidOrExpiredTokenError` (401), `InsufficientRoleError` (403), `RoleNotAssignedError` (403), `ProfileNotFoundError` (404), `VenueNotFoundError` (404), `AuthServiceUnavailableError` (503) | `app/core/exceptions.py` |
| Supabase clients | `get_supabase_admin_client()` (secret key, bypasses RLS), `get_supabase_anon_client()` (stateless calls), `create_auth_client()` (fresh client for sign-in/refresh) | `app/db/supabase.py` |
| Settings | `get_settings()`: `supabase_url`, `supabase_publishable_key`, `supabase_secret_key`, `api_v1_prefix`, `backend_cors_origins` | `app/core/config.py` |
| Venue period and occupancy types | `Period`, `Occupant`, `BlockSummary`, `BookingSummary`, `VenueSummary` | `venues/schemas.py` |
| Venue enums (Python) | `VenueLayout`, `Facility`, `AccessibilityFeature`, `Availability`, `ReasonCode`, plus the `label()` display helper | `venues/schemas.py` |
| Availability and suitability rules (pure, no I/O) | `evaluate(venue, criteria, occupants)` for one venue, `search(venues, criteria, occupants_by_venue)` for the catalogue, `OCCUPYING_STATUSES` (`held`, `approved`, `re_review`) | `venues/search.py` |
| Venue data access | `list_venues`, `get_venue`, `list_occupants(period)`, `list_upcoming_blocks`, `list_upcoming_bookings` | `venues/repository.py` |
| Venue service (the entry point other modules should call) | `search_venues(criteria)`, `get_venue(venue_id)` | `venues/service.py` |
| Test fixtures | `client` (FastAPI `TestClient`), `auth_headers`, and fake Supabase env vars | `backend/tests/conftest.py` |

## 3. Frontend (`frontend/src/`)

### Routes

| Path | Allowed roles | View |
|---|---|---|
| `/login` | public | `LoginView` |
| `/profile/me` | any signed-in user | `ProfileView` |
| `/dashboard/organiser`, `/coordinator`, `/venue-staff`, `/tech-support`, `/attendee` | that role (`meta.allowedRoles`) | `views/dashboards/*Dashboard.vue` |
| `/venues`, `/venues/:id` | `event_coordinator`, `venue_staff` | `views/venues/VenueSearchView`, `VenueDetailView` |

### Design-system components (`components/common/`)

| Component | Props and events |
|---|---|
| `BauhausButton` | `variant`: `primary` (red), `secondary` (blue), `yellow`, `outline`; `type`, `disabled`, `fullWidth`; default slot |
| `BauhausCard` | `background`: `white`, `red`, `blue`, `yellow`; `accent`: `circle`, `square`, `triangle`, `none`; `accentColor`; default slot |
| `BauhausInput` | `v-model`, `label` (required), `type`, `placeholder`, `error`, `autocomplete` |
| `BauhausSelect` | `v-model`, `label` (required), `options: [{ value, label }]`, `placeholder` (defaults to "Any") |
| `BauhausCheckboxGroup` | `v-model` (array), `label` (required), `options: [{ value, label }]` |
| `BauhausEmptyState` | `title` (required), `detail` |
| `BrandMark` | no props; the ConnectSphere logo mark (36px square). Used by `Nav` and, on small screens, `TopBar` |
| `Nav.vue` (docs previously called this `BauhausNavbar`, which doesn't exist as a file — corrected here) | no props; the left sidebar nav (its mobile open/close button lives in `TopBar`). Shows the brand, Dashboard/Venues links, a role switcher (`BauhausSelect`, only when the profile holds 2+ roles — SCRUM-74/75), Profile, and logout |
| `TopBar.vue` | no props; the sticky header above every signed-in page (rendered by `App.vue` alongside `Nav`). Shows the `BrandMark` (small screens only, where the sidebar is a drawer), "Hello <first name>" above today's date, the sidebar toggle on mobile, a notifications bell (empty-state panel — no notifications backend yet), and a search box that runs a venue search by location, offered only to the roles allowed on `/venues` |

### Other reusable pieces

| Need | Use | Location |
|---|---|---|
| Sidebar collapse (desktop, persisted) and drawer open/close (mobile) | `useSidebarState()` → `isCollapsed`, `isMobileOpen` | `composables/useSidebarState.js` |
| Friendly date for headers ("8th May 2025") | `formatFriendlyDate(date)`, `ordinalSuffix(day)` | `components/common/dateFormat.js` |
| Venue search form and result card | `VenueCriteriaForm` (`criteria`, `errors`; emits `submit`, `reset`), `VenueResultCard` (`result`) | `components/venues/` |
| API calls | `authApi`, `venuesApi`, `eventsApi`, `ApiError` | `services/api.js` |
| Session, current user, role → dashboard route, role labels, role switching | `useAuthStore` (`roles`, `hasMultipleRoles`, `setActiveRole(role)`), `ROLE_DASHBOARD_ROUTES`, `ROLE_LABELS` | `stores/auth.js` |
| Venue option lists and search state | `LAYOUTS`, `FACILITIES`, `ACCESSIBILITY_FEATURES`, `emptyCriteria()`, `criteriaToParams(criteria)`, `useVenuesStore` | `features/venues/venueSearchStore.js` |
| Singapore-time arithmetic (deciding *which day* an instant falls on) | `singaporeDayKey(instant)`, `startOfSingaporeDayUtc(key)`, `toSingaporeIso(date, time)`, `SINGAPORE_OFFSET_MS` | `features/venues/singaporeTime.js` |
| Month- and week-grid construction, and placing periods on days | `buildMonthGrid`, `buildWeekGrid`, `singaporeDayKeysCovered`, `itemDayRange`, `toCalendarItems`, `defaultMonth`, `defaultWeekKey`, `shiftMonth`, `shiftWeekKey`, `startOfWeekKey`, `canGoPrev`, `canGoPrevWeek`, `CALENDAR_KINDS` | `features/venues/calendar.js` |
| Exporting a calendar as .ics | `toIcsCalendar(items, {now})`, `icsFilename(now)`, plus `escapeIcsText` / `foldIcsLine` / `toIcsStamp` — hand-written RFC 5545, no dependency | `features/venues/ics.js` |
| Packing multi-day items into calendar bars | `layoutWeekSegments(cells, {maxLanes})`, `toWeekRows(grid, {maxLanes})` — greedy lane assignment, with per-day overflow counts so nothing is silently dropped | `features/venues/calendar.js` |
| Venue-staff dashboard logic (pure functions) | `summariseVenueStaffDashboard`, `sortPendingHoldsOldestFirst`, `waitingDays`, `formatEventReference`, `venueStatuses`, `BLOCK_REASON_LABELS`, `BOOKING_STATUS_LABELS` | `features/venues/dashboard.js` |
| Venue-staff dashboard state | `useVenueStaffDashboardStore` | `features/venues/venueStaffDashboardStore.js` |
| Calendar over blocks and bookings, month or week | `VenueCalendar` (`items`, `hasSettled`, `today`) — built for SCRUM-70, intended for SCRUM-16's per-venue calendar too. Both grids share one cell shape, so the component renders either from one set of rules | `components/venues/VenueCalendar.vue` |
| Event status labels and dashboard logic (pure functions) | `STATUS_LABELS`, `STATUS_DESCRIPTIONS`, `ACTIVE_COORDINATOR_STATUSES`, `ACTION_KINDS`, `actionKindMeta`, `prioritiseActionItems`, `summariseActionItems`, `groupActiveEventsByStatus`, `countByStatus`, `outstandingReadiness`, `readinessGaps` | `features/events/dashboard.js` |
| Coordinator dashboard state | `useCoordinatorDashboardStore`; the header comment documents the response shape the future events endpoint must return | `features/events/store.js` |

Vitest specs live in `__tests__/` folders next to the code: router, `stores/auth`, `features/venues` (search store, calendar, dashboard logic, dashboard store), `features/events`, venue search and the venue-staff dashboard view.

## 4. Database (`supabase/migrations/`)

| Migration | Adds |
|---|---|
| `20260912000001_init_auth_and_profiles.sql` | `user_role` enum; `profiles`; functions `set_updated_at()`, `handle_new_user()`, `prevent_self_role_change()` |
| `20260913120749_fix_auth_security_defects.sql` | `private.current_user_role()` (use it in RLS policies instead of querying `profiles`); hardened `handle_new_user()` |
| `20260915090000_venues_catalogue_and_availability.sql` | enums `venue_layout`, `facility`, `accessibility_feature`, `venue_booking_status`, `venue_block_reason`; tables `venues`, `venue_layouts`, `venue_facilities`, `venue_blocks`, `venue_bookings` (with the `venue_bookings_no_overlap` exclusion constraint) |
| `20260917000000_role_switching.sql` | tables `user_roles` (roles an account holds, ACC-R4) and `session_active_roles` (the role a login session is currently acting as, keyed by the JWT `session_id` claim, SCRUM-75); updates `handle_new_user()` to seed `user_roles` |
| `20260918000000_session_active_roles_fk_user_roles.sql` | composite FK `session_active_roles (profile_id, role) references user_roles (profile_id, role) on delete cascade`, so revoking a role via direct SQL immediately invalidates any session acting as it, instead of leaving it valid until logout/expiry; replaces the single-column `profile_id` index with a covering `(profile_id, role)` one |
| `20260919000000_profiles_role_requires_user_roles_membership.sql` | deferred composite FK `profiles (id, role) references user_roles (profile_id, role)`, closing the same revocation gap for the common case the previous migration didn't cover — a session that never switched, whose `profiles.role` default was revoked; a covering `(id, role)` index |

Verification scripts are in `supabase/verification/` (`auth_security_checks.sql`, `venue_schema_checks.sql`). Seeded test accounts, one per role with password `Cs1234`, are in `supabase/seed.sql`; `coordinator@connectsphere.dev` additionally holds `venue_staff` in `user_roles` (SCRUM-74/75), so it's the account to use for exercising the role switcher and the profile page's "All Roles" section (SCRUM-78). Granting a role beyond signup has no in-app path yet — it's a direct SQL insert into `user_roles`, done by a system admin.

## 5. Know before you build

**Architecture and conventions**

- **Data access is through the Supabase client only.** `app/db/session.py` is a placeholder seam for a future direct-SQL session. Adopting SQLAlchemy or a direct Postgres connection is a project-wide change, so confirm with the team first (see §6 for a branch that does this).
- **Occupied periods are half-open `[starts_at, ends_at)`.** A booking ending at 12:00 doesn't conflict with one starting at 12:00. Double-booking is prevented in the database by `venue_bookings_no_overlap`, not by application checks. Terms like Hold, Block, Availability, and Suitability are defined in `CONTEXT.md`.
- **Reuse the venue enums** (`venue_layout`, `facility`, `accessibility_feature`) in any new table that describes event requirements. Don't define parallel ones.
- **Two dashboards are data-driven: coordinator (SCRUM-72) and venue staff (SCRUM-70).** Organiser, tech support and attendee are still shells with hardcoded metrics (PROJECT_REVIEW D8). Follow the same pattern — a store plus honest empty states — and never hardcode a metric. SCRUM-70 is the better model of the two, because its data actually exists.
- **Frontend domain stores go in `features/<domain>/`** (team decision, `frontend/AGENTS.md` "Where stores go"). This is now done everywhere: SCRUM-70 moved the last legacy store, and `stores/` holds only `auth.js`. A domain with more than one store names each file after the store (`venueSearchStore.js`, `venueStaffDashboardStore.js`).

**Traps already hit**

- **Supabase SDK:** use `create_auth_client()` for sign-in and refresh, and import exceptions from `supabase_auth.errors`, not `gotrue.errors` (`docs/SCENARIO.md` §5).
- **Endpoints that call Supabase are plain `def`.** supabase-py is synchronous, and `async def` blocks the event loop (PROJECT_REVIEW D5).
- **A PostgREST embed must name its constraint when the table has two FKs to the same target.** `venue_bookings` points at `venues` twice — `venue_id` and `suggested_venue_id` — so a bare `venues(name)` fails the *whole query* with `PGRST201`. Use `venues!venue_bookings_venue_id_fkey(name)`. Mocked tests cannot catch this; it only appears against a real database (SCRUM-70).
- **Mapping a half-open period onto calendar days uses `endsAt − 1ms`.** The last instant inside `[start, end)` is `end − ε`, so a block ending at midnight must not mark that day (§6.14, CAL-R2). `features/venues/calendar.js` does this once — don't re-derive it.
- **Never slice a raw ISO string to get a day key.** The same instant serialises as both `...T16:00:00Z` and `...T00:00:00+08:00`, which slice to different days. Use `singaporeDayKey`, which works from the instant.
- **The venue-staff dashboard payload is upcoming-only**, so its calendar cannot page back before the current month — every earlier month would be empty by construction rather than in fact.
- **`event_name` on the venue-staff dashboard is a declared-but-null contract field** waiting on SCRUM-8's `events` table. Fill it there; the SPA already falls back to a short id.
- **RLS policies must not query their own table.** It recurses (`42P17`), so use `private.current_user_role()`.
- **The live migration history has drifted from the files before.** Run `supabase migration list --linked` before every `supabase db push` (PROJECT_REVIEW D8, migration drift).
- **Never commit `supabase/.temp/` or `supabase/.branches/`.** They're gitignored now. `.temp/` holds generated local secrets, which is how PRs #4 and #6 failed the GitGuardian check.

**Still open**

- **D7:** SCRUM-50's acceptance criteria require communication preferences, but `profiles` has no such column.
- Leaked-password protection is still disabled in the Supabase dashboard.
- `venue_bookings.event_id` is a plain `uuid` with no foreign key until an `events` table lands (§6).

## 6. In flight: unmerged branches (check before touching these areas)

These aren't on `main`, but whoever builds nearby will collide with them. Remove each entry once its branch is merged or abandoned.

| Branch | Jira assignee | Adds | Watch out for |
|---|---|---|---|
| `feature/SCRUM-23-equipment-availability` and `feature/SCRUM-73-tech-support-dashboard` (PRs #4, #5, #6 closed) | Tan Qiao Wen Eileen | Migration `20260914100000_equipment_availability.sql`: `equipment`, `equipment_unavailability`, `equipment_reservations`. An `equipment` module, a `TechSupportDashboard` UI, and **SQLAlchemy** (`db/models.py`, `get_db()` in `db/session.py`, a `database_url` setting) | **Diverges from the Supabase-client-only data access** used everywhere else, so the team needs to agree before merging. Its migration timestamp (`20260914…`) is **earlier** than the venues migration already on `main` (`20260915…`), so `supabase db push` will reject it unless it's renamed to a later timestamp. Both branches still contain the committed `supabase/.temp` secrets file in their history. |
