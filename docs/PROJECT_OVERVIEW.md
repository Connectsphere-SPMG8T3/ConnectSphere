# ConnectSphere — Project Overview

**Who the customer is, what the first release must do, and why the system is built the way it is.**

This file holds the course context, the customer briefing, the first-release scope, and the reasoning behind the architecture, design system and database. It is stable reference material: change it only when the customer or the team's architecture actually changes.

- What each story actually built, in order: [`BUILD_LOG.md`](BUILD_LOG.md). The log was §4 of this file when it was `SCENARIO.md`, so the numbering below skips §4; references such as "§2.3" or "§5" made before the split still point at the right section.
- What the system *should* do: [`REQUIREMENTS.md`](REQUIREMENTS.md). What exists now: [`IMPLEMENTATION_MAP.md`](IMPLEMENTATION_MAP.md).

Sources for this document: `IS212 (AY2026/27, T1) — Scrum Project Instructions` (Week 4), `IS212 — Customer Briefing: Event Planning and Venue Booking System` (Week 1), Jira exports for individual issues (e.g. `SCRUM-48`) from Sprints 1–2, and the team's Product backlog sheet from Sprint 3.

## 1. Course context

This repository is the codebase for an **IS212 (Software Project Management) team project**: a term-long exercise in running an agile (Scrum) software project against a simulated customer, ConnectSphere. The grading rubric (Week 4 instructions) weighs the Scrum *process* — sprint evidence, estimation, backlog quality, retrospectives — at least as heavily as the delivered software, and explicitly penalises "an AI-generated solution that you cannot explain/justify." Practically, this means:

- Every change in this repo should be traceable back to a specific backlog item (a PBI such as `SCRUM-48` or `CR-99` in the Product backlog sheet) and, ultimately, back to a piece of the customer briefing.
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
| 1 | User Authorisation and Authentication | Secure access; visibility/functionality scoped by role — epic `SCRUM-7`; see [`BUILD_LOG.md`](BUILD_LOG.md) for which stories under it are done. |
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

Which of the 20 features have implementation, story by story, is in [`IMPLEMENTATION_MAP.md`](IMPLEMENTATION_MAP.md) §1; how each was built is in [`BUILD_LOG.md`](BUILD_LOG.md). Do not assume a feature's domain logic exists until one of those says so.

`frontend/src/features/events/` contains coordinator-dashboard presentation logic, while the SCRUM-8 request implementation lives in `backend/app/modules/events/` and `frontend/src/stores/events.js` / `frontend/src/views/events/`. Coordinator assignment, reassignment, and submission notifications remain separate SCRUM-12 / SCRUM-68 scope.

## 5. Architecture: modular monolith

- **`backend/`** — Python FastAPI. Each domain lives in its own package under `app/modules/<domain>/` with a consistent internal shape (`router.py`, `schemas.py`, `service.py`, optionally `dependencies.py`), sharing a common `app/core/` (config, security, exceptions) and `app/db/` (Supabase client factories). Modules talk to each other only through service-layer function calls, never by reaching into another module's internals — the `auth` module's `dependencies.py` re-exports `app.core.security` deliberately, so other future modules depend on `app.modules.auth.dependencies` rather than on `app.core` directly.
- **`frontend/`** — Vue 3 (Composition API, `<script setup>`), Vite, Pinia, Vue Router. Route guards in `src/router/index.js` handle both `requiresAuth` and per-route `allowedRoles`.
- **`supabase/`** — Postgres schema (migrations) and seed data. Supabase Auth (`auth.users`) owns credentials; `public.profiles` owns ConnectSphere-specific attributes (role, department, organisation), kept in sync by a `handle_new_user()` trigger — this is a deliberate 3NF split rather than duplicating auth data.
- **`mcp/`** — Supabase MCP server config for project `vuiryrzzyfecjqftwicj`, so an AI assistant can inspect the live schema/logs/advisors directly.

This architecture choice is a direct response to the customer briefing's **maintainability** NFR (§2.3): future functionality and business rules — features 2–20 — need to be addable as new modules without rebuilding features 1's auth layer, and without those new modules being able to bypass the access control already built here.

### Why the backend never re-implements password checking

`app/modules/auth/service.py` calls Supabase's GoTrue API (`sign_in_with_password`) rather than checking a password hash itself. On success it gets back a Supabase-issued JWT, which `app/core/security.py` then verifies on every subsequent authenticated request via the Supabase SDK's `get_claims()` — this checks the token's signature and expiry against the project's published JWKS (fetched once and cached locally), so it works whether the project signs sessions with the legacy HS256 shared secret or the current asymmetric ES256 signing keys, without the backend hardcoding either. (`get_claims` does not itself check the `aud` claim, so `decode_access_token` verifies that explicitly.) This still avoids a live call to Supabase on the *common* path (only the first request after startup or JWKS-cache expiry triggers a fetch), while trusting Supabase as the single source of truth for "is this password correct" and "is this token genuinely ours."

One thing worth knowing if you're extending this: `supabase-py`'s exception classes live in the `supabase_auth` package at runtime — the older `gotrue` package name still exists (installed as a dependency of `supabase-py`) but defines a **separate, unrelated set of exception classes** that happen to share the same names (`AuthApiError`, `AuthInvalidJwtError`, etc.). Importing from `gotrue.errors` instead of `supabase_auth.errors` will silently fail to catch real runtime errors — code will type-check and pass mocked tests (if the tests import from the same wrong module) while still 500ing in production. Always import Supabase auth exceptions from `supabase_auth.errors`.

A second SDK trap (`BUILD_LOG.md` §4.2, `DEFECTS.md` D1): supabase-py keeps the session from `sign_in_with_password`/`refresh_session` **on the client instance** and auto-refreshes it in the background. Never call those on a cached/shared client — use `app.db.supabase.create_auth_client()`, which returns a fresh client with persistence and auto-refresh disabled. The shared publishable-key client is only for stateless calls that take the token explicitly (`get_claims(token)`, `auth.admin.sign_out(token, scope)`).

### Why role checks need a profile lookup, not just the JWT

A Supabase JWT's own `role` claim is the Postgres role (`authenticated`), not a ConnectSphere business role. `get_current_user` in `app/core/security.py` therefore always fetches the corresponding `public.profiles` row (via the service-role client, bypassing RLS since the backend has already verified the caller's identity) to get `role`, `full_name`, etc. `require_roles([...])` builds on top of that.

## 6. Design system: Bauhaus constructivist modernism

The frontend deliberately avoids generic UI-kit aesthetics in favour of a strict, opinionated system:

- **Palette:** off-white canvas (`#F0F0F0`), stark black ink (`#121212`), and three primaries — red (`#D02020`), blue (`#1040C0`), yellow (`#F0C020`) — plus a muted grey (`#E0E0E0`).
- **Typography:** `Outfit` (weights 400/500/700/900), set for long reading sessions since 2026-10-21: sentence case, normal letter spacing, nothing below 12px, `font-bold` as the heaviest weight (headlines `font-bold leading-tight`, labels `text-sm font-medium`). It replaced the original all-caps Bauhaus labels; `frontend/AGENTS.md` "Type" has the rule.
- **Radii:** binary only — `rounded-none` or `rounded-full`. No soft corners anywhere.
- **Shadows:** hard offset shadows (`shadow-hard` / `shadow-hard-lg`, mapped to `4px_4px_0px_0px_#121212` / `8px_8px_0px_0px_#121212`), with buttons pressing flat on `:active`.
- **Components** (`frontend/src/components/common/`): `BauhausButton`, `BauhausCard` (with a geometric corner accent — circle, square, or triangle), `BauhausInput` (with validation error states), `Nav.vue` (the sidebar: brand mark, role badge, logout), plus the smaller shared pieces alongside them.

These tokens live in `frontend/tailwind.config.js` and `frontend/src/assets/main.css`. Note that Tailwind's JIT scanner needs fully static class names — `BauhausCard`'s accent colour is resolved through a lookup object (`accentBgClasses` / `accentBorderClasses`) rather than a dynamic `bg-${accentColor}` string, since the latter would be invisible to Tailwind's build-time scan and silently produce no styles.

This design system is a project-specific/team choice (matching the customer briefing's generic "should be desktop- and mobile-friendly" and "presented clearly" requirements, §2.3), not something specified by the customer briefing itself.

## 7. Database design principles

- 3NF normalisation: auth credentials in `auth.users`, domain attributes in `public.profiles`.
- Surrogate UUID primary keys throughout (`profiles.id` is also a foreign key to `auth.users.id`, cascading on delete).
- `user_role` is a Postgres enum (`event_organiser`, `event_coordinator`, `venue_staff`, `tech_support`, `attendee`), not a free-text column.
- B-tree indexes on `profiles(role)` and `profiles(email)` for the lookups the auth flow performs on every request.
- Row Level Security is enabled on `profiles`: users can read/update their own row; internal staff (`event_coordinator`, `venue_staff`, `tech_support`) can read every profile (for cross-role coordination); a trigger explicitly blocks users from changing their own `role` column, since role elevation must go through a privileged path in a future story, not self-service.
- A policy must never query its own table (that recurses, `42P17`): role checks inside policies use the `private.current_user_role()` security-definer helper, and per-request functions are wrapped as `(select auth.uid())`. Security-definer functions pin `search_path = ''` and are not callable via RPC (`BUILD_LOG.md` §4.2).
- Sign-up metadata is client-controlled: `handle_new_user()` only accepts the external roles `event_organiser` and `attendee` from it; staff roles are set by seed/migration only (`BUILD_LOG.md` §4.2, QA-3/QA-4).
