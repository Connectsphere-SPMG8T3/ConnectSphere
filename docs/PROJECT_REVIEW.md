# ConnectSphere — Design Review, Backlog Gap Analysis & Release Plan

**Reviewed on:** 13 Sep 2026, day 6 of Sprint 1 (8–22 Sep).
**Inputs:** the codebase on `main` (`eac61de`); the live Supabase project; all 58 Jira issues in project SCRUM; the Week 1 Customer Briefing; the Week 4 Project Instructions; the **Session 1 Clarification Answers (G8)**, cited as `QA-<row>`; and the prof's two Q&A answers ("changes can happen anytime"; "non-core Week 1 features stay in the backlog at low priority").
**Companion document:** [`REQUIREMENTS.md`](REQUIREMENTS.md) holds the C4 model, the target domain model, and the behaviour specs referenced below as §x.y.

---

## Part A — Design & framework review

### A1. What's already good (keep it)

- **Modular monolith with clear module seams.** Each module follows the `auth` pattern (router, schemas, service, dependencies). This is the right size for 6 developers over 4 sprints, and it's easy to defend in the Week 13 Q&A.
- **Authentication is delegated to Supabase Auth.** Nobody hand-rolls password handling. Tokens are verified via JWKS (`get_claims`), which survives Supabase's key rotation.
- **Real verification against live Supabase** found five integration bugs that mocks had hidden. These are recorded in SCENARIO.md §4.1, which is strong process evidence.
- **Migrations-only schema changes with RLS enabled**, an `updated_at` trigger, and role-change protection.
- **Documentation and traceability are ahead of most teams:** SETUP, SCENARIO, and TEST_CASES all exist.

### A2. Defects found in this review (verified, not theoretical)

> **Numbering note:** two different defects were both filed as **D8** (migration drift, and fabricated dashboard metrics). Both are kept as written rather than renumbered, since they are cited by those names elsewhere in the docs; new defects continue from D9.

> **Status (13 Sep 2026):** D1–D6 are **fixed** on branch `fix/auth-security-bugs`. The database migration `20260913120749` is already applied to the live project. Reproduction, root cause, and verification for each defect are in `docs/SCENARIO.md` §4.2. D1 turned out to be broader than first described: the shared client also silently auto-refreshed (and so rotated) the last signed-in user's token. Still open: **D7** (SCRUM-50 `communication_preferences` column, left to the story owner) and the leaked-password-protection dashboard toggle.

| # | Severity | Finding | Evidence | Fix |
|---|---|---|---|---|
| **D1** | **Critical** | **Logout signs out the wrong user.** `get_supabase_anon_client()` is `@lru_cache`'d, so one client instance is shared by every request. `sign_in_with_password` stores that user's session *inside* the shared client, and `logout()` calls `anon_client.auth.sign_out()`, which revokes the stored session with `scope="global"`. When user A logs out, the session revoked is that of **whoever last logged in through the API** (on all their devices). The `access_token` argument to `service.logout()` is never used. | `backend/app/db/supabase.py:8`, `backend/app/modules/auth/service.py:52-60`; `supabase_auth/_sync/gotrue_client.py:779-798` (sign_out reads `self.get_session()`) | Create a **fresh, non-persisting client per sign-in** (`ClientOptions(persist_session=False, auto_refresh_token=False)`). Log out with `admin_client.auth.admin.sign_out(access_token, "local")`. Add a regression test in which two users log in and one logs out. |
| **D2** | **Critical (security)** | **Anyone can self-register as internal staff.** Sign-up is enabled on the project (`disable_signup=false`), and the `handle_new_user()` trigger copies `raw_user_meta_data->>'role'` into `profiles.role`. The publishable key ships in the browser bundle, so `supabase.auth.signUp({ email, password, options: { data: { role: 'event_coordinator' } } })` creates a coordinator after one email confirmation. | `supabase/migrations/20260912000001_init_auth_and_profiles.sql:87`; `GET /auth/v1/settings` → `disable_signup: false` | Follow-up migration: accept **only `event_organiser` or `attendee`** from sign-up metadata and default anything else to `attendee`. The customer confirmed that external users self-register and that staff are system defaults with no admin role (QA-3, QA-4). Staff accounts are created only by seed or migration. Revoke `EXECUTE` on `handle_new_user` from `anon, authenticated`. |
| **D3** | **High** | **The RLS policy recurses infinitely.** The `profiles_select_internal_staff` policy queries `public.profiles` from inside a `profiles` policy. Any query made with a user's JWT fails with `42P17 infinite recursion detected in policy for relation "profiles"`. It hasn't surfaced only because the API uses the secret key, which bypasses RLS. Every future table whose policies check the caller's role will hit the same problem. | Reproduced with `set local role authenticated` plus JWT claims → error 42P17 | Add a `security definer` helper, `public.current_user_role()`, with `set search_path = ''`, and use `(select public.current_user_role())` in policies. Apply the same pattern to all new tables. |
| **D4** | **High** | **Sessions die after 1 hour.** The API returns a `refresh_token`, but the SPA discards it (`stores/auth.js` stores only `access_token`). When the JWT expires, the next navigation fails `/auth/me`, and the user is dropped to the login page mid-task. This will happen during the Week 13 demo. | `frontend/src/stores/auth.js:58-61` | Persist the refresh token. Add `POST /auth/refresh`. In the API client, on `401`, refresh once and retry (REQUIREMENTS §6.1). |
| **D5** | Medium | **Synchronous Supabase calls run inside `async def` endpoints.** `supabase-py`'s sync client blocks the event loop, so under concurrent load all requests queue behind one network call. | `auth/router.py`, `core/security.py:57` | Declare endpoints and dependencies that call the sync client as plain `def` (FastAPI runs those in a threadpool), or switch to `acreate_client`. |
| **D8** | Medium | **Live migration history drifted from the files.** `supabase migration list --linked` showed `20260912000001` (initial auth/profiles) as *not* applied on the live project although its schema was, so `supabase db push` would have re-run it and failed on `create type user_role`. Found while pushing the SCRUM-39 migration. | `supabase migration list --linked` (15 Sep 2026) | **Fixed on `feature/scrum-39-venue-search`:** `supabase migration repair --status applied 20260912000001`. Check `supabase migration list --linked` before every push; apply SQL to the live project only through `supabase db push`. |
| D6 | Low | Supabase advisors: mutable `search_path` on `set_updated_at` and `prevent_self_role_change` ([lint 0011](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable)); `handle_new_user` executable via RPC by `anon` and `authenticated` ([0028](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable) / [0029](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable)); per-row `auth.uid()` re-evaluation ([0003](https://supabase.com/docs/guides/database/database-linter?lint=0003_auth_rls_initplan)); multiple permissive policies ([0006](https://supabase.com/docs/guides/database/database-linter?lint=0006_multiple_permissive_policies)); leaked-password protection disabled ([docs](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)). | `get_advisors` output, 13 Sep | Fold into the same follow-up migration as D2 and D3. Toggle leaked-password protection in the dashboard. |
| **D8** | Medium | **Dashboards displayed fabricated metrics as if they were real.** `CoordinatorDashboard.vue` hardcoded "Requests Awaiting Review: 5", "Venues to Coordinate: 4", "Events in Progress: 9" against a database containing no events at all. A grader or customer viewing the demo would have been shown invented figures presented as system data — and the numbers would have stayed wrong once real data arrived. The other four role dashboards carry the same pattern and are **still unfixed**. | `frontend/src/views/dashboards/CoordinatorDashboard.vue:7-11` (before fix); live schema exposes only `profiles` | **Coordinator dashboard fixed** on `feature/scrum-72-coordinator-dashboard` (SCENARIO §4.5): metrics now come from a store, and empty states distinguish *loading* from *not built yet* from *genuinely clear*. **Venue Staff dashboard fixed** on `feature/scrum-70-venue-staff-dashboard` (SCENARIO §4.9): the hardcoded 12/6/2 are gone and every figure is derived from `GET /venues/dashboard/venue-staff` against real seeded data, with a regression test asserting the removed strings are absent. **Still outstanding:** the Organiser, Tech Support and Attendee dashboards (SCRUM-71, 73 and the missing attendee story). |
| **D9** | **High** | **The SPA did not build.** `frontend/src/stores/events.js` imported `@/stores/venues`, which SCRUM-70 moved to `features/venues/venueSearchStore.js` while SCRUM-8 was in flight; the branches merged without the import being repointed. `npm run build` failed outright (`Could not load .../src/stores/venues`) and `src/stores/__tests__/events.spec.js` failed to collect, so `npm test` was red on `main`. Any organiser-facing screen (`EventRequestView`, `EventDetailView`, `OrganiserDashboard`) would have been unreachable in a deployed build. | `npx vite build` and `npx vitest run` on `main` at `998097d` | **Fixed on `feature/scrum-67-view-venue-details`:** the import now points at `@/features/venues/venueSearchStore`. Two follow-ups: `stores/events.js` is itself a domain store sitting outside `features/` against the team's own rule (`frontend/AGENTS.md`), and a green `npm run build` should be a merge gate so a move like this cannot land broken again. |
| D7 | Low | **SCRUM-50 can't meet its acceptance criteria.** The criteria require "communication preferences", but `profiles` has no such column. | Migration vs. SCRUM-50 description | Add `communication_preferences jsonb` in a migration before SCRUM-50 is marked Done. |
| **D10** | Low–Medium | **An unhandled server error reaches the browser as a CORS failure instead of a 500,** including a transient dropped database connection. The error propagates past Starlette's `CORSMiddleware`, so the response carries no `Access-Control-Allow-Origin` header and the browser reports a CORS / "Failed to fetch" error rather than surfacing the actual status. Any server error then looks like a dead backend rather than a handled failure, which is misleading during grading/demo and slows down debugging a real outage. | Observed during Task 9's real-system verification of SCRUM-34/52 (a transient `httpx.RemoteProtocolError: Server disconnected` from an idle Supabase connection); `docs/IMPLEMENTATION_MAP.md` §5 | Add an exception handler/middleware ordering that keeps CORS headers on a 500 response, and consider retrying an idempotent read once when the underlying connection drops. |

### A3. Design improvements, prioritised for the change-heavy customer

The rubric's "Excellent" system-design descriptor is *"well-justified trade-offs that support change"*, and the customer confirmed that change can happen at any time. The improvements below are ordered by how much future rework each one avoids.

1. **Put integrity guarantees in the database before building bookings, reservations, or registrations.**
   The customer wants double-booking to be *impossible*, first-come-first-served, with no staff override (QA-10, QA-113). They also want a **pending request to hold the venue exclusively** (QA-6). Check-then-insert over PostgREST races: two coordinators requesting the same slot at the same moment would both succeed. Instead:
   - use a GiST exclusion constraint on `tstzrange` over held, approved, and re-review bookings (DB-1), with zero turnaround (QA-28);
   - use `SECURITY DEFINER` SQL functions with row locks for `reserve_equipment` and `register_attendee` (DB-3, DB-4);
   - use optimistic locking (`version`) on events (DB-5).

   This is the single most important design decision for Sprints 2–3, and it gives the team a strong answer to "how do you prevent double-booking?" in the Q&A (REQUIREMENTS §4).
2. **Centralise the event lifecycle in one state machine** (`events/lifecycle.py`, REQUIREMENTS §5). Right now the status rules are scattered across 6 Jira stories (65, 68, 34, 52, …). If each developer writes their own `if status == ...` checks, status handling will drift apart. One transition table provides the guards, the history, and a single file to change when the customer renames or adds a status.
3. **Use in-process domain events for side effects** (Observer pattern). Services publish events such as `EventApproved` or `EventCancelled`, and the `notifications`, `audit`, `venues`, and `equipment` modules subscribe. Without this, every story's service ends up calling notifications, audit, bookings, and so on directly, and the §7 cross-feature rules become tangled. A roughly 30-line synchronous dispatcher is enough, with no message broker required.
4. **Add a policy layer for relationship-based authorisation.** `require_roles` answers "is this user a coordinator?" but not "is this user *this event's* coordinator?". Add `policies.py` per module (for example, `ensure_event_visible_to(user, event)`) and a parametrised authorisation-matrix test (REQUIREMENTS §2). Because the API bypasses RLS, these checks are the real security boundary, so they need tests.
5. **Add a repository layer** (`repository.py` per module). Today's tests mock `.table().select().eq().maybe_single().execute()` chains, which break whenever a query changes and make the 100% coverage target painful. With repositories, services can be tested against in-memory fakes, and only the repositories need integration tests against a real database.
6. **Make business rules configurable rather than hard-coded:** field classification (ordinary vs significant), suitability rules as pluggable classes (Strategy pattern, §6.11), the coordinator assignment policy, and status display labels. Session 1 already showed why: turnaround time was dropped (QA-28), and the customer reconciled "approved" vs "confirmed" (QA-18, QA-56). Each change should touch one file.
   - **Never auto-un-book.** The customer's rule is "the system detects and notifies; staff decide" (QA-2, QA-26, QA-117). Implement significant changes as a `re_review` state on bookings and equipment lines, not as releases (REQUIREMENTS §7).
7. **Maintain a single source of truth for enums.** Roles and statuses are currently duplicated in SQL, Python strings, and JavaScript. Generate them from the database (`supabase gen types`) or keep one `constants` module per side, with a test asserting that both sides match.
8. **Restructure the frontend around features** (`src/features/events|venues|equipment|registrations|notifications`, each with views, a store, and a service), mirroring the backend modules. Dashboards then only *compose* widgets from those features (REQUIREMENTS §3.4). *(Update: the `src/features/` restructure is under way, and the "no tests at all" state this review recorded no longer holds — Vitest is configured and 312 specs pass across 23 files. Still outstanding: one Playwright end-to-end run of the reference workflow.)*
9. **Add CI now, not in Sprint 4.** CI is graded ("basic CI pipeline used *during* development"). **Largely done** on `chore/ci-pipeline` — `.github/workflows/ci.yml` runs on every PR into `main` and on `main` after a merge:
   - `pytest` (backend) — **done**
   - Vitest via `npm test` (frontend) — **done**; the suite the original recommendation assumed did not exist now has 312 specs
   - `npm ci && npm run build` — **done**
   - `ruff` — **not done**, deliberately deferred: it has never run over this codebase, so turning it on blocking would have held the pipeline red on an unbounded cleanup. Its own chore branch.
   - `pytest --cov` coverage reporting — **not done**; `pytest-cov` is still unpinned, and no threshold has been agreed (see `DEFINITION_OF_DONE.md`, "Not yet enforceable").

   The run history is free evidence.
10. **Stop migrating the live project directly.** Six people applying migrations to one shared database will collide. Use the Supabase CLI locally (`supabase start`) or Supabase branching per PR. Only merged migrations go to the shared project, and seeds must be idempotent.
11. **Add a `client_organisations` table now.** "Organisers must not see other clients' events" and the Client Management feature both depend on it. Adding it before `events` exists costs almost nothing; retrofitting it later costs a migration plus backfill.

---

## Part B — Jira backlog gap analysis

### B1. Coverage of the 20 core features

Legend for the "Story quality" column:
- **Good:** user-story format with testable acceptance criteria.
- **Weak:** vague acceptance criteria or missing edge cases.
- **Raw:** requirement text pasted in, no user story, no acceptance criteria.
- **None:** no story exists.

| # | Core feature | Jira epic | Stories | Story quality | Main gaps |
|---|---|---|---|---|---|
| 1 | Authorisation & authentication | SCRUM-7 | 48 ✔, 50, (70–73 misfiled here) | Good / Weak | No story for **relationship-based access**, logout, session expiry/refresh, or account provisioning. SCRUM-48 says "username" but we implemented email (needs a recorded decision). Dashboards 70–73 aren't auth. |
| 2 | Event request creation | **none** | SCRUM-8 (Story, no epic) | **Implemented** | Implemented on `feature/scrum-8-event-request` with draft, submission, validation, detail retrieval, and event-timezone coverage. Coordinator assignment and notifications remain SCRUM-12 / SCRUM-68 scope. |
| 3 | Draft event requests | **none** | SCRUM-9, SCRUM-65 (overlap) | Raw / Weak | Duplicated between 9 and 65. No "drafts invisible to staff" rule, no delete-draft behaviour. |
| 4 | Event review & approval | SCRUM-11 | 33, 34, 49, 52 | Good | **Missing the organiser side.** The customer's model is *return for amendment*: the organiser edits the same request and resubmits (QA-22, QA-77). SCRUM-33 instead describes a clarification thread the coordinator "marks resolved". No story covers "planning only after requirements gathered" (QA-22) or feasibility criteria (QA-23). |
| 5 | Coordinator assignment | **none** | SCRUM-12 (Story), 68 | Raw | The customer answered: **automatic, by load, at most one coordinator** (QA-5, QA-54, QA-79), but SCRUM-12 has no acceptance criteria reflecting this. **No reassignment story** (required by W4). Load balancing under simultaneous submissions isn't covered. |
| 6 | Event status management | SCRUM-13 | 65, 68 | Weak | Only 2 of ~11 transitions have stories. **No return/resubmit, confirmation (readiness, no override, QA-118), cancellation-request approval (QA-12), or completion stories.** No "invalid transitions are blocked" criterion. The status set needs reconciling (QA-18 vs QA-56; REQUIREMENTS §5). |
| 7 | Event information management | SCRUM-14 | 62, 61 (comments, non-core) | Weak | **The core point — ordinary vs significant edits — has no story.** No edit story at all, no concurrent-edit handling. SCRUM-61 title typo ("Commend"). |
| 8 | Venue catalogue | SCRUM-15 | 63, 64, 67, 39 (misnamed) | Good | **No "add venue" story** (the catalogue can't be populated through the UI; SCRUM-39 seeds 8 venues). SCRUM-39 is titled "View Venue Catalogue" but its acceptance criteria describe *search, filter, availability, and turnaround buffers*. **Built as one story on `feature/scrum-39-venue-search`** (SCENARIO §4.4); the buffer criterion was dropped (QA-28) and must be removed in Jira. |
| 9 | Venue availability calendar | SCRUM-16 | 57, 51, 54 | Good | 57 is written for venue staff only, but the core feature says "authorised internal users" (coordinators too). |
| 10 | Venue search & filtering | **none** | (inside SCRUM-39) | – | Delivered inside SCRUM-39 (REQUIREMENTS §6.10, VS-R1–R7). No separate story needed; the `event_id` pre-fill waits for SCRUM-8. |
| 11 | Venue suitability checking | **none** | SCRUM-18 (**Task**) | **Raw** | Typed as a task, no acceptance criteria, no rules table (§6.11), no boundary cases (attendance = capacity). |
| 12 | Venue booking request | **none** | SCRUM-19 (Story) | **Raw** | No acceptance criteria. The customer answered the key rules: **a pending request is an exclusive tentative hold** (QA-6), first-come-first-served (QA-10), and one venue per event (QA-116). None of this is in Jira yet. |
| 13 | Venue booking approval | SCRUM-20 | 36, 38, 47 | **Good** (best in backlog) | 36 should re-check conflicts at approval time, including concurrent approvals. |
| 14 | Booking conflict detection | **none** | SCRUM-21 (**Task**) | **Raw** | The hardest correctness rule has no acceptance criteria. Now answered: impossible, no override, holds count, zero turnaround (QA-6, QA-10, QA-28, QA-62, QA-113). Half-open intervals, blocks, and concurrency still need testable criteria (§6.14). |
| 15 | Equipment request management | SCRUM-22 | 45, 40, 41, 44 | Weak | 41's acceptance criteria are one line. No equipment catalogue story, although 45 depends on one. |
| 16 | Equipment availability checking | (under 22) | SCRUM-23 | Weak | Acceptance criteria ignore **date/time overlap** and **maintenance status**, which is the whole point of the feature. Typos. Scheduled in Sprint 1 although it depends on reservations (feature 17). |
| 17 | Equipment reservation | (under 22) | SCRUM-24 (**Task**) | **Raw** | No acceptance criteria. Now answered: **all or nothing** (QA-125), freed on cancellation (QA-33), never auto-released on change (QA-2), no substitution on breakdown (QA-31). |
| 18 | Attendee registration | SCRUM-25 | 43, 55, 56, 35, 59, 58 (.ics, non-core) | Weak / Good | **No "browse events open for registration" story.** No story for the **registration window configured by the organiser** (QA-89). Capacity concurrency not covered (QA-107). The waitlist behaviour is clarified (no auto-promotion, invite the next attendee, QA-30) but is non-core. 55, 56, 58, 59 are typed as Tasks. |
| 19 | Event change requests | SCRUM-26 | 32, 37 | Good | SCRUM-37's "awaiting re-confirmation" matches the customer's re-review rule (QA-2, QA-32). **Missing:** the **cancellation request → coordinator approval** flow (QA-12), attendee notification (QA-114, QA-124), and the list of significant fields (QA-13, QA-66). |
| 20 | Notification system | SCRUM-27 | 69, 53 (Task) | Weak | **No in-app notification centre story** (bell, list, mark read). The channel is the team's choice (QA-11), so 69's email and SMS can be moved to a low-priority follow-up story. |

**Summary:**
- Only **11 of the 20 core features have an epic**.
- **7 core features are raw requirement text** with no user story or acceptance criteria (2, 3, 5, 11, 12, 14, 17).
- **3 are unrepresented or buried** in another story (7's core rule, 10, and the confirmation and cancellation part of 6).

### B2. Missing stories to create (core-critical)

Proposed epic in brackets; acceptance criteria to copy from REQUIREMENTS.

1. **[Auth]** Sign up as an Event Organiser or Attendee; staff accounts are system defaults (QA-3, QA-4; §2.1).
2. **[Auth]** Relationship-based access: "As an organiser, I can only see my own events" (QA-25, QA-87; §2.2).
3. **[Auth]** Log out safely and keep my session alive (refresh). Covers D1 and D4 (§6.1).
4. **[Assignment]** The system auto-assigns the least-loaded coordinator on submission (QA-5, QA-54; §6.5). *Rewrite SCRUM-12 as this.*
5. **[Assignment]** Hand over an event to another coordinator (W4; §6.5 AS-R4).
6. **[Review]** Return a request for amendment, then the organiser edits and resubmits (QA-22, QA-77; §6.4). *Replace SCRUM-33's "mark resolved" model.*
7. **[Status]** Tech support mark technical readiness; the coordinator confirms only when venue and technical arrangements are complete, with no override (QA-17, QA-118, QA-128; §6.6).
8. **[Change Requests]** The organiser requests cancellation; the coordinator approves; arrangements are freed and attendees notified (QA-12, QA-33, QA-114; §6.19).
9. **[Change Requests]** Venue staff and tech support re-review arrangements after a significant change, with no automatic un-booking (QA-2, QA-32; §6.19).
10. **[Status]** Mark an event completed (§5).
11. **[Info Mgmt]** Edit event information: ordinary vs significant fields (QA-13, QA-66, QA-81; §6.7).
12. **[Info Mgmt]** View the event's change history in the UI (QA-70; §6.7). *This is required by the customer, not optional.*
13. **[Venue Catalogue]** Add a new venue (§6.8).
14. **[Venue Search]** Search and filter venues for an event (split out of SCRUM-39) (§6.10).
15. **[Equipment]** View the equipment catalogue and record outages (maintenance, damage) (§6.16).
16. **[Registration]** Organiser configures registration capacity and open/close dates (QA-89; §6.18).
17. **[Registration]** Browse events open for registration (§6.18).
18. **[Notifications]** In-app notification centre (QA-11; §6.20).
19. **[Enabler / tech]** CI pipeline; core schema migration; domain event dispatcher; lifecycle state machine; D1–D3 fix migration.

### B2a. Existing stories that now contradict the Session 1 answers

Update these in Jira, and leave a comment on each, for example: *"Updated after Session 1 Q&A (QA-28): turnaround assumed zero."* This comment trail is exactly the "responded to changed requirements" evidence the rubric asks for.

| Story | Current text | Customer answer | Update to |
|---|---|---|---|
| SCRUM-39 | "Automatically incorporates setup, reset, and turnaround buffers" | Turnaround is zero / ignored (QA-28, QA-82, QA-93, QA-103) | **Done in code (SCENARIO §4.4).** Remove the buffer criterion in Jira with the comment "Updated after Session 1 Q&A (QA-28): turnaround assumed zero"; add "excluded venues are revealed with their reasons". |
| SCRUM-12 | Raw text; implies someone assigns | Automatic assignment by load, max 1 coordinator (QA-5, QA-54, QA-79) | §6.5 acceptance criteria |
| SCRUM-33 | Clarification thread the coordinator "marks as resolved" | Request is **returned**; organiser edits the same request and resubmits (QA-22, QA-77) | §6.4 return/resubmit criteria |
| SCRUM-34 | "Approve available only when no unresolved clarification requests" | Approve is possible only in `under_review`; planning starts after requirements are gathered (QA-22) | **Done in Jira (2026-09-23).** Approve → `planning`, labelled "Planning" (§5, QA2-8); final confirmation split out as SCRUM-82 |
| SCRUM-36 | "Once approved, the venue is no longer shown as available" | The venue is already unavailable from the moment of the **pending request** (tentative hold, QA-6) | Move the exclusivity criterion to request time (§6.12) |
| SCRUM-45 / SCRUM-41 | Status "arranged" / "not available" | Fulfilled completely or rejected; no partial fulfilment (QA-125) | `reserved` / `rejected` with a reason (§6.15) |
| SCRUM-43 | "Registration form open only for confirmed events" | Also within **organiser-configured open/close dates**; stops at capacity (QA-89, QA-107) | §6.18 RG-R1, RG-R2 |
| SCRUM-69 | Users opt for email, SMS, or in-app | Channel is the team's choice (QA-11) | Release 1: in-app; email story at Low priority |
| SCRUM-70 | "Venues the Venue Staff member manages" | Staff allocation to venues is not tracked (QA-44) | All venues; staff work as one pool (§2.2 AUTH-R5). **Resolved and built this way** on `feature/scrum-70-venue-staff-dashboard`; the dashboard is headed "All venues" and states the reason (SCENARIO §4.9) |
| SCRUM-32 | "Organiser can propose modifications to any event details" | Also covers **cancellation requests**, approved by the coordinator (QA-12) | Add a cancellation criterion (§6.19) |
| SCRUM-8 | Implemented on `feature/scrum-8-event-request` | Request creation, drafts, validated submission, submitted detail retrieval, and event-local timezone handling. Coordinator assignment and notifications are separate SCRUM-12 / SCRUM-68 scope. | §6.2 field table; SCENARIO §4.9 |

### B3. Backlog hygiene issues (visible to graders in the exported backlog)

- **Every one of the 58 issues is "To Do"**, including SCRUM-48, which is merged to `main`. The Sprint 1 burndown is therefore flat. Update statuses daily, because the burndown and board screenshots are graded evidence.
- **Only 9 of 47 non-epic items are estimated**, all of them in Sprint 1. The rubric's estimation criterion expects estimates on upcoming candidates too. Run planning poker on the Sprint 2 candidates in Part C and record the result (a photo, screenshot, or spreadsheet).
- **Issue types are inconsistent.** User stories are typed as Task (18, 21, 24, 53, 55, 56, 58, 59), and core features are split between Story, Task, and Epic. Recommendation: one **Epic per core feature**, **Stories** for user-facing value, and **Sub-tasks** for technical work under a story.
- **7 items have no epic:** 8, 9, 12, 18, 19, 21, 66.
- **Many stories lack acceptance criteria**, and those that have them rarely use Given/When/Then or cover edge cases. The rubric's "Excellent" user-story descriptor explicitly mentions *edge cases and changed requirements*.
- **The dashboard stories (70–73) are under the Auth epic.** Create a "Role-Based Dashboard" epic. There is **no attendee dashboard story**, although the route exists.
- **The Sprint 1 goal** ("complete user management…") doesn't match its contents (venues, equipment, event creation). Sprint goals should be one coherent outcome.
- **Changed requirements aren't traceable.** When the customer clarifies something, add a Jira comment ("Clarified in Q&A 15 Sep: …") and update the acceptance criteria. This is direct evidence for the "responded to changes" question in Week 13.
- **Typos** in 23, 61, and 73, which show up in the exported deliverable.

### B4. Sprint 1 risks (act this week)

| Risk | Stories | Mitigation |
|---|---|---|
| Dashboards are built before their data exists | 70, 71, 72, 73 | Re-scope with the PO (don't silently drop): **shell plus the first widget whose data exists**, with empty states for the rest (§6.21). Record the re-scope in Jira comments. |
| Equipment availability depends on reservations and a catalogue that don't exist | 23 | Deliver the availability *calculation* (pure function plus tests) against the target schema; wire it to real data in Sprint 3. Or swap it with "View equipment catalogue". |
| SCRUM-39 is three features in 3 points, and contradicts QA-28 | 39 | ~~Split~~ **Delivered whole** on `feature/scrum-39-venue-search`: catalogue + search/filter + availability, with the DB-1 exclusion constraint landed early for SCRUM-19/21. Buffer criterion dropped. |
| Three people will invent three incompatible schemas | 8, 39, 23 | **One shared core-schema migration first** (events, venues, equipment tables from REQUIREMENTS §4), reviewed by the whole team before anyone builds on it. |
| SCRUM-50 acceptance criteria can't be met | 50 | Add the `communication_preferences` column (D7). |

---

## Part C — Release roadmap & detailed next-sprint plan

### C1. Constraints

- **4 sprints total**, each 2 weeks. Sprint 1 runs 8–22 Sep. **[Assumed dates, check against the academic calendar and recess week]** Sprint 2 runs 22 Sep–6 Oct, Sprint 3 runs 6–20 Oct, and Sprint 4 runs 20 Oct to the first week of November. The final sprint must end by Friday of Week 12.
- **Sprint 4 is the "showcase sprint".** It should demonstrate the process at its best, so plan it **lighter** than Sprint 3 and leave room for integration, end-to-end hardening, and recorded ceremonies. Don't back-load features into it.
- **The Week 7 process consultation** falls around the end of Sprint 2. Bring the Sprint 1 retrospective actions and the Sprint 2 burndown.
- **Velocity is unknown until Sprint 1 closes.** Sprint 1 committed 27 SP across 6 developers. The Sprint 2 list below is **ordered with a cut line**; commit up to the team's *actual* Sprint 1 completed points, plus at most about 20%.
- **Three parallel streams** of 2 developers each keep hand-offs low:
  - **Stream A:** event workflow
  - **Stream B:** venues and bookings
  - **Stream C:** equipment, registration, notifications, and cross-cutting work

### C2. Roadmap across the 4 sprints

| Sprint | Goal | Stream A (Events) | Stream B (Venues) | Stream C (Equipment / Registration / Cross-cutting) |
|---|---|---|---|---|
| **1** (now → 22 Sep) | *Users log in securely and land on a role dashboard; the shared data foundation is in place* | 48 ✔, 50 (+D7), 71 shell, 8 (create form) | 39a view catalogue, 70 shell | 23 (pure availability function), 72/73 shells. **Plus:** D1–D3 fixes, CI pipeline, core schema migration |
| **2** (22 Sep → 6 Oct) | *An organiser can sign up, draft and submit a request that is auto-assigned to a coordinator for review; coordinators can find suitable venues; everyone is notified* | Organiser/attendee sign-up, 9, 8 (submit), lifecycle state machine, 12 auto-assignment, 49 review details, change history (data + tab) | 39b search and filter, 18 suitability, add venue, 63 update venue | Notification centre, equipment catalogue and outages, 45 equipment request, 40 request queue |
| **3** (6 Oct → 20 Oct) | *An approved event gets an exclusive venue hold approved and its equipment fully reserved, and can be confirmed* | 33 return and resubmit, 34 approve, 52 reject, hand over, technical readiness and confirm, 62 planning details | 19 booking request as tentative hold (DB-1), 21 conflict detection, 36/38 approve/reject, 47 booking list, 57 calendar, 51 block | 23 wire-up, 24 reserve all-or-nothing (DB-4), 41 update status, 44 modify; registration settings, 43 register, 56 my registrations |
| **4** (20 Oct → Wk 12) *showcase* | *Changes and cancellations flow through re-review and release consistently, with everyone notified* | 32 change and cancellation requests, 37 process with impact preview, significant-edit rules, complete event | Venue re-review after change, 54 shorten block, 64 deactivate, "venue changed/blocked" flags, 70/72 dashboards finished | Equipment re-review, outage flags, 55 withdraw, 35/59 registration views, browse events, 53 change notifications; end-to-end workflow test, coverage gaps, final evidence |

Everything in REQUIREMENTS §8 (P3) stays in the backlog at Low priority and is pulled in only if a sprint finishes early.

### C3. Immediately — the rest of Sprint 1 (13–22 Sep)

SCRUM-48 is done, so **Jie Ching has spare capacity** for the rest of the sprint. The highest-leverage use of that time is unblocking the other five developers:

1. **Move SCRUM-48 to Done.** Add a comment linking PR #1 and noting the email-vs-username decision.
2. **Fix D1 to D3 and D6** in one PR: a per-request auth client, correct logout, a trigger that accepts only `event_organiser`/`attendee` from sign-up (QA-3, QA-4), the `current_user_role()` helper that removes the RLS recursion, and `search_path` fixes. Add regression tests. Log it as a Sprint 1 bug with sub-tasks.
3. **Update the 11 contradicted stories in B2a** and comment on each with its QA citation. This takes about 30 minutes and is high-value evidence.
4. ~~**Add a CI pipeline** (GitHub Actions: ruff, pytest with coverage, frontend build).~~ **Done** on `chore/ci-pipeline` — `.github/workflows/ci.yml` runs pytest, Vitest and the frontend build on every PR. Ruff and coverage reporting were deferred; see Part A item 9.
5. **Draft the core schema migration** (`client_organisations`, `events`, `event_status_history`, `amendment_requests`, `change_requests`, `venues` with layouts and facilities, `venue_bookings` with the exclusion constraint over held/approved/re_review, `venue_blocks`, `equipment_types`, `equipment_outages`, `equipment_requests`, `equipment_reservations`, `registrations`, `notifications`, `change_history`) per REQUIREMENTS §4. **Review it with the whole team at stand-up before merging.**
6. Add the domain event dispatcher skeleton (`core/events.py`) and a per-module `repository.py` pattern to the `auth` module, so others copy the pattern rather than invent one.
7. Bring REQUIREMENTS §9 (9 remaining open questions, including the approved-vs-confirmed contradiction) to the next customer Q&A.

### C4. Sprint 2 plan (22 Sep – 6 Oct)

**Proposed sprint goal:** *"An Event Organiser can sign up, draft and submit an event request that the system automatically assigns to an Event Coordinator for review; coordinators can search for suitable venues; and all parties receive in-app notifications of these steps."*

**Candidate backlog in priority order.** Suggested story points seed planning poker only; re-estimate as a team.

| Order | Key | Story | Stream | Suggested SP | Running total | Acceptance criteria source | Depends on |
|---|---|---|---|---|---|---|---|
| 1 | NEW | Event lifecycle state machine + status history (enabler) | A | 3 | 3 | §5 | Core schema (S1) |
| 2 | NEW | Sign up as Event Organiser or Attendee | A | 2 | 5 | §2.1, §6.1 | D2 fix (S1) |
| 3 | SCRUM-9 (+65 merged) | Save and edit draft event requests | A | 3 | 8 | §6.3 | 1 |
| 4 | SCRUM-8 | Submit event request with validation | A | 3 | 11 | §6.2 | 3 |
| 5 | SCRUM-12 (+68 merged) | Auto-assign least-loaded coordinator on submission | A | 3 | 14 | §6.5 | 4 |
| 6 | NEW | In-app notification centre (bell, list, mark read) + dispatcher wiring | C | 5 | 19 | §6.20 | Dispatcher (S1) |
| 7 | SCRUM-49 | Review submitted event request details | A | 2 | 21 | §6.4 | 5 |
| 8 | SCRUM-18 | Venue suitability checking (rule engine) | B | 3 | 24 | §6.11 | 39a (S1) |
| 9 | NEW (39b) | Search and filter venues for an event | B | 5 | **29** | §6.10 | 8 |
| ─ | | **Likely cut line (≈ Sprint 1 velocity + ~10%)** | | | | | |
| 10 | NEW | Change history: record + History tab | C | 3 | 32 | §6.7, QA-70 | 1 |
| 11 | NEW | Add a new venue (venue staff) | B | 3 | 35 | §6.8 | – |
| 12 | NEW | Equipment catalogue view + record outages | C | 2 | 37 | §6.16 | Schema |
| 13 | SCRUM-45 | Record and submit an equipment request | C | 3 | 40 | §6.15 | 12, and a planning-status event (Sprint 3) or seeded data |
| 14 | SCRUM-63 | Update venue details (with affected-booking warning) | B | 3 | 43 | §6.8 | 11 |
| 15 | SCRUM-40 | Tech support equipment request queue | C | 2 | 45 | §6.15 | 13 |

**Why this order:**
- Items 1–7 form the thin vertical slice (sign up → draft → submit → auto-assign → notify → review) that Sprint 3's return, approval, and booking work needs.
- Items 8–9 run in parallel on Stream B with no dependency on Stream A.
- Item 10 sits just below the cut line only because its *data capture* can ride along with item 1's status history. Pull it above the line if velocity allows: the customer explicitly wants history in the UI (QA-70).
- Items 11–15 are safe to move to Sprint 3 without breaking the goal.

**Example task breakdown** (repeat the pattern for every story during planning). For SCRUM-8, "Submit event request":
- Migration check: event fields and constraints exist (DB).
- `events/schemas.py` submit schema with the field validators from §6.2.
- `events/service.submit()` → `lifecycle.transition(draft→submitted)` → publish `EventSubmitted`.
- `events/policies.ensure_owner()`.
- Router `POST /events/{id}/submit` returning `409` on the wrong status.
- Unit tests for validation boundaries (attendance 0/1, `ends_at` = `starts_at`, past start).
- Integration test for submit, including a second submit returning `409`.
- Vue: request form submit, a field error summary, and a status badge.
- Manual test cases TC-EVT-0xx in TEST_CASES.md, linked to the Jira key.
- SCENARIO.md log entry.

**Definition of Done** — the checklist this review proposed now lives in [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md), consolidated with the one in root `AGENTS.md` so the project has a single version. Agree on it at planning and paste it into the Jira board description. Two items from this review are parked in that file's "Not yet enforceable" table until the tooling exists: **CI green on the PR** (there is no CI) and **100% line coverage on new domain code** (no coverage tooling). Everything else applies as written, including the two this review added and `AGENTS.md` never had: **a teammate review on every PR**, and **moving the Jira issue to Done with the PR linked**.

**Sprint 2 risks:**
- The notification centre (item 6) touches every module. Build the dispatcher contract on day 1 so other stories can publish events before the UI is ready.
- Venue search performance with range overlap: add GiST indexes in the schema migration.
- Customer answers to REQUIREMENTS §9 (Q1 statuses, Q2 reassignment, Q6 organiser edits) may change items 1, 5, and 7. Keep acceptance criteria editable, and record every change as a Jira comment citing the Q&A row.

**Scrum evidence to capture in Sprint 2** (graded deliverable 4):
- Planning: sprint goal, committed backlog screenshot, planning-poker record.
- Daily: board screenshot at least 2–3 times per week; burndown at the end.
- Review: a demo of the thin slice (sign up → draft → submit → auto-assign → notify → review), plus customer feedback captured as backlog changes.
- Retrospective: a board with actions, and in Sprint 3's retrospective an explicit check of whether Sprint 2's actions were done ("inspect and adapt" evidence).
- Week 7 consultation: bring the Sprint 1 and Sprint 2 burndowns and retrospective actions.
