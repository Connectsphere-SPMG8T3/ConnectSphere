# CR-103 / CR-104 Safety review queue and decision: Implementation Plan

> **For agentic workers (Codex):** Implement task by task, in order. Steps use checkbox syntax. This plan states requirements, interfaces and tests; **you write the implementation**. TDD is mandatory: write the failing test, run it, confirm it fails for the right reason (not an import typo), write the minimum code, run it green, commit.

**Goal:** A Safety Officer can see the queue of events in Safety review, open a review page, and approve, request changes to, or reject the safety arrangements; plus a shared `return_to_planning` function other stories call.

**Architecture:** Same modular-monolith pattern as SCRUM-82: pure lifecycle rows, thin router, service logic, repository RPC wrappers, and `security definer` Postgres functions that call `public.transition_event` so status, history, decision row and notifications commit atomically. Officer comments live in a new RLS-restricted table and never reach history or notifications (AUTH-R2).

**Tech Stack:** FastAPI 0.115 + supabase-py 2.31 (pytest 8.3); Vue 3 `<script setup>` + Pinia + Vue Router + Tailwind (Vitest, Playwright); Supabase Postgres migrations. Check pinned versions in `backend/requirements.txt` and `frontend/package.json`.

**Spec:** `docs/superpowers/specs/2026-10-09-cr-103-104-safety-review-decision-design.md`. Read it in full first, plus `AGENTS.md`, `backend/AGENTS.md`, `frontend/AGENTS.md`, and the SCRUM-82 spec and plan (`docs/superpowers/specs|plans/2026-10-08-scrum-82-*`), which this work mirrors. Reuse before building (`docs/IMPLEMENTATION_MAP.md`).

## Global Constraints

- Branch is `feature/cr-104-record-safety-decision`. **Never commit to `main`. Do not push. Do not open a PR. Do not edit the Google Sheets.**
- **Never run `supabase db push` or `apply_migration`.** Write the migration, run `supabase db push --dry-run` if useful, then stop and tell the developer the migration is ready to push (Task 1 handoff). Use `env PATH=/home/linuxbrew/.linuxbrew/bin:/usr/bin:/bin supabase ...` (the CLI is not on the default PATH).
- Authorise by the session's **active role** only: `require_roles(["safety_officer"])` in the API, `private.current_user_role()` in RLS, the store's active `role` in the frontend. Never `user_roles`, `CurrentUser.roles` or `profiles.role`. Every new endpoint gets a raw-request denial test for a multi-role account acting as another role (SCRUM-76).
- The officer's comment is never written to `event_status_history.reason`, to `notifications.message`, or to any response the organiser can read.
- Endpoints that call Supabase are plain `def`. Routers stay thin. Cross-module calls go through the other module's `service.py` only.
- Errors are typed exceptions in `app/core/exceptions.py` or the module's existing ones (`EventNotFoundError`, `EventConflictError`, `EventTransitionError`); stale-version message is `STALE_EVENT_MESSAGE`.
- Mock at the Supabase client seam. Tests never hit live Supabase. Test file docstrings carry the PBI ids (`CR-103`, `CR-104`). Name files by module and behaviour.
- Stage commits by file name, message `type(scope): imperative summary`, body explains why with the PBI id. **No attribution lines.** Never stage `.env`, keys or tokens.
- Coverage: 100% of new and changed lines in `backend/app/` and `frontend/src/`, or list each uncovered line with a reason in the final report.
- New migration timestamp sorts after `20261008150001`. Name it `<UTC YYYYMMDDHHMMSS>_safety_review_decision.sql`.
- Do not change `request_venue_booking`, `readiness.py` rules, or the SCRUM-82 endpoint behaviour.
- Observed facts to rely on: booking status enum is `held, approved, re_review, rejected, cancelled, released`; equipment line enum is `pending, reserved, rejected, re_review, released` (only `pending` is written today); `public.transition_event(p_event_id, p_actor_id, p_from_statuses text[], p_to_status text, p_expected_version int, p_reason text default null, p_notify_type text default null, p_notify_message text default null) returns setof events`, null `p_notify_type` skips the organiser notification, null `p_actor_id` is allowed, it returns no row on a stale version or wrong status.

## Review Focus

Failure modes the spec implies that no acceptance criterion tests directly; each has a test in the owning task.

1. A comment/reason that is empty, whitespace-only, or over 1000 characters → 422 (Task 4).
2. `booking_ids` / `equipment_request_ids` that belong to a different event, are duplicated, or are unknown → refused with 422 and nothing changes (Task 4).
3. Approving while an active booking is `held`/`re_review`/missing, or when the arrangements changed after the officer opened the page (event version unchanged) → 409, no transition, no notification (Tasks 1 and 4).
4. Two officers deciding at once, or a decision after `return_to_planning` already ran → exactly one decision row and one transition; the loser gets 409 (Tasks 1 and 4).
5. The organiser's event read, history, and notifications never contain the officer's comment (Tasks 1, 5 and 8).

---

### Task 1: Migration and database verification

**Files:**
- Create: `supabase/migrations/<timestamp>_safety_review_decision.sql`
- Create: `supabase/verification/safety_decision_checks.sql`

**Interfaces — Produces** (later tasks call these through the repository, names exact):
- Table `public.event_safety_decisions(id uuid pk default gen_random_uuid(), event_id uuid not null references public.events(id) on delete cascade, decision text not null check (decision in ('approved','changes_requested','arrangement_rejected','withdrawn')), comment text, reason_code text, affected_booking_ids uuid[] not null default '{}', affected_equipment_request_ids uuid[] not null default '{}', rejected_venue_ids uuid[] not null default '{}', decided_by uuid references public.profiles(id) on delete set null, decided_at timestamptz not null default now())`. Check: `comment` is 1–1000 chars after trim when present, and required (non-null) for `changes_requested` and `arrangement_rejected`; `reason_code` required for `withdrawn`, null otherwise. Index `(event_id, decided_at desc)`. RLS on, **select-only**: the event's assigned coordinator (`events.coordinator_id = auth.uid()` and `private.current_user_role() = 'event_coordinator'`) or `private.current_user_role() = 'safety_officer'`. No insert/update/delete policy.
- `public.safety_approve_event(p_event_id uuid, p_actor_id uuid, p_expected_version integer, p_comment text, p_organiser_message text, p_staff_message text) returns setof public.events`
- `public.safety_return_event(p_event_id uuid, p_actor_id uuid, p_expected_version integer, p_decision text, p_comment text, p_booking_ids uuid[], p_equipment_request_ids uuid[], p_coordinator_message text) returns setof public.events`
- `public.return_event_to_planning(p_event_id uuid, p_expected_version integer, p_from_status text, p_reason_code text, p_coordinator_message text, p_officer_message text) returns setof public.events`
- All three: `language plpgsql security definer set search_path = ''`; `revoke execute ... from public, anon, authenticated; grant execute ... to service_role;`. Same shape as `send_event_to_safety_review` (`supabase/migrations/20261008150001_send_event_to_safety_review.sql`).

**Behaviour required** (spec §4):
- `safety_approve_event`: `safety_review → confirmed` via `transition_event(..., p_reason null, 'event_safety_approved', p_organiser_message)`. **Before** the transition, lock the event row and require at least one active booking (`held/approved/re_review`) and every active booking `approved`; otherwise return no row and change nothing. After the transition: insert one `approved` decision row; notify (type `event_safety_approved`, `p_staff_message` to staff, the organiser already notified by `transition_event`) the assigned coordinator, every `user_roles.role = 'venue_staff'` holder and every `'tech_support'` holder, **deduplicated** against each other and against the organiser, never the actor.
- `safety_return_event`: `safety_review → planning`, `p_decision` must be `changes_requested` or `arrangement_rejected` (else raise). Every id in `p_booking_ids` must be a booking of this event and every id in `p_equipment_request_ids` an equipment line of this event, else return no row and change nothing. `changes_requested`: those `approved` bookings → `re_review`, those equipment lines → `re_review`. `arrangement_rejected`: those bookings → `released` (store their `venue_id`s in `rejected_venue_ids`), those equipment lines → `rejected`. `transition_event` is called with a **null** notify type and a **null** reason. Insert the decision row. Notify only the assigned coordinator (type `event_safety_changes_requested` / `event_safety_arrangement_rejected`, `p_coordinator_message`). Do not notify the organiser.
- `return_event_to_planning`: `p_from_status` is `safety_review` or `confirmed` (else raise); transition to `planning` with a null actor, null reason, null notify type. Insert a `withdrawn` decision row with `reason_code` and a null `decided_by`. Notify the assigned coordinator (type `event_returned_to_planning`, `p_coordinator_message`), and, only when `p_from_status = 'safety_review'`, every `safety_officer` role holder (`p_officer_message`). Changes no bookings or equipment.
- `p_comment` is stored in the decision row only; it must not appear in the history row or any notification.

- [ ] **Step 1: Write `supabase/verification/safety_decision_checks.sql` first** (model it on `send_for_safety_check.sql`: one transaction, fixtures inside, `rollback` at the end, `raise exception` on any failed expectation). It must cover: approve with all-`approved` bookings succeeds and writes one history row (no reason), one `approved` decision, recipients deduplicated with no actor; approve with a `held` booking, with no booking, and with a stale version each return no row and change nothing; `safety_return_event` request-changes → `re_review` on exactly the listed ids, reject → `released` with `rejected_venue_ids` set, foreign/unknown ids return no row; invalid `p_decision` raises; `return_event_to_planning` works from both `safety_review` and `confirmed`, refuses (raises) from other statuses, notifies officers only when leaving review; no history `reason` or `notifications.message` ever contains the comment text; RLS: an organiser session, an unassigned coordinator session and a `venue_staff` session select zero rows from `event_safety_decisions`, the assigned coordinator and a `safety_officer` session select the rows (set `request.jwt.claims` and the active role the way `event_comment_checks.sql` does for its RLS cases).
- [ ] **Step 2: Write the migration** to satisfy the script.
- [ ] **Step 3: Run `supabase db push --dry-run`** and confirm it lists only this migration. **Do not push.** (Running the verification script needs the migration applied; that happens after the developer pushes. Until then, check the SQL parses with `psql --set ON_ERROR_STOP=1 -f` against a scratch transaction only if a local database exists; otherwise state it is unverified.)
- [ ] **Step 4: Commit** `feat(db): add safety decision table and wrapper RPCs (CR-104)`.
- [ ] **Step 5: Hand off.** Tell the developer: migration ready, run `supabase db push`, then run `safety_decision_checks.sql` through `execute_sql` or `supabase db query --linked -f`, then `supabase migration list --linked` and the advisors. Continue with Task 2 meanwhile; everything after this mocks the database.

---

### Task 2: Lifecycle row, schemas and repository wrappers

**Files:**
- Modify: `backend/app/modules/events/lifecycle.py`, `schemas.py`, `repository.py`
- Test: `backend/tests/test_event_lifecycle.py` (extend), `backend/tests/test_events_repository.py` (extend)

**Interfaces — Produces:**
- `lifecycle.TRANSITIONS["approved_change"] = (frozenset({EventStatus.confirmed}), EventStatus.planning)`. Update the module comment; `safety_approve`, `safety_request_changes`, `safety_reject`, `safety_withdraw` are unchanged.
- Schemas in `schemas.py`:
  - `SafetyApproveRequest(comment: str | None = None)`; `SafetyChangesRequest(comment: str, booking_ids: list[UUID] = [], equipment_request_ids: list[UUID] = [])`; `SafetyRejectRequest(reason: str, booking_ids: list[UUID] = [], equipment_request_ids: list[UUID] = [])`. Strings are stripped; required ones must be 1–1000 characters after stripping (422 otherwise); id lists are de-duplicated preserving order.
  - `SafetyDecisionKind` str enum: `approved`, `changes_requested`, `arrangement_rejected`, `withdrawn`.
  - `ReturnReason` str enum: `arrangement_flagged`, `booking_cancelled`, `technical_not_ready`, `approved_details_changed`.
  - `SafetyDecision {id, decision, comment: str | None, reason_code: ReturnReason | None, affected_booking_ids: list[UUID], affected_equipment_request_ids: list[UUID], rejected_venue_ids: list[UUID], decided_by_name: str | None, decided_at: datetime}`.
  - `SafetyDecisionSummary {decision, reason_label: str, decided_at}` (no comment). `EventResponse` gains `latest_safety_decision: SafetyDecision | SafetyDecisionSummary | None = None`.
- Repository, same style as `send_to_safety_review` (`.rpc(...)`, `None` when the RPC returns no row): `safety_approve(event_id, actor_id, expected_version, *, comment, organiser_message, staff_message) -> dict | None`; `safety_return(event_id, actor_id, expected_version, *, decision, comment, booking_ids, equipment_request_ids, coordinator_message) -> dict | None`; `return_to_planning(event_id, expected_version, *, from_status, reason_code, coordinator_message, officer_message) -> dict | None`; `list_safety_decisions(event_id) -> list[dict]` newest first with the decider's `full_name` embedded; `list_safety_queue() -> list[dict]` events in `safety_review` with their organiser name and `entered_review_at` (the latest history row with `to_status = 'safety_review'`).

- [ ] **Step 1: Write failing tests**: `target("approved_change", "confirmed")` is `planning` and raises `EventTransitionError` from every other status; `allowed_from("approved_change") == ["confirmed"]`; each request schema rejects blank, whitespace-only and 1001-character required text and de-duplicates ids; each repository wrapper passes the exact RPC name and parameter names and returns `None` on an empty result (mock the client like `test_events_repository.py` does).
- [ ] **Step 2: Run, confirm fail.** **Step 3: Implement.** **Step 4: Run, confirm pass.**
- [ ] **Step 5: Commit** `feat(events): add lifecycle row, schemas and RPC wrappers for the safety decision (CR-104)`.

---

### Task 3: `return_to_planning` — the shared function

**Files:**
- Modify: `backend/app/modules/events/service.py`
- Test: `backend/tests/test_return_to_planning.py` (create)

**Interfaces — Consumes:** Task 2 lifecycle row, `ReturnReason`, `repository.return_to_planning`.
**Interfaces — Produces** (teammates call this; the signature is a contract, do not change it):
`return_to_planning(event_id: str, *, reason_code: ReturnReason, message: str | None = None, actor_id: str | None = None) -> EventResponse | None`

**Behaviour required:**
- Loads the event; a missing event or a draft returns `None` (callers must not crash a booking cancellation).
- Event not in `safety_review` or `confirmed` → returns `None`, calls nothing.
- `safety_review` uses action `safety_withdraw`, `confirmed` uses `approved_change`; sources and target come from `lifecycle`, not literals.
- Passes the event's current `version`; an empty RPC result (a concurrent decision already moved the event) → returns `None`, not an error.
- Coordinator message is fixed text per `reason_code` including the event name, never the free-form `message`; officer message likewise. `message` is accepted for the caller's own audit context only and is not stored or sent anywhere (state this in the docstring).
- `actor_id` is accepted for interface stability and ignored by the RPC (system action); it is not written to the decision row.

- [ ] **Step 1: Write failing tests**: parametrised over the two source statuses (right lifecycle action and `from_status` passed to the repository); parametrised over all four reason codes (messages contain the event name, differ per code, never contain the caller's `message`); `None` for each of `draft`, `under_review`, `returned`, `planning`, `rejected`, a missing event; stale RPC result → `None`; `officer_message` is the fixed text when the source is `safety_review` and `None` when it is `confirmed` (assert both).
- [ ] **Step 2–4: red, implement, green.** **Step 5: Commit** `feat(events): add return_to_planning for arrangements that stop being ready (CR-104)`.

---

### Task 4: Decision endpoints

**Files:**
- Modify: `backend/app/modules/events/service.py`, `router.py`; `backend/app/modules/venues/service.py` and `equipment/service.py` only to add the two small read functions below
- Test: `backend/tests/test_safety_decisions_api.py` (create)

**Interfaces — Consumes:** Task 2 repository and schemas.
**Interfaces — Produces:**
- Router: `SafetyOfficer = Annotated[CurrentUser, Depends(require_roles(["safety_officer"]))]`; `POST /events/{event_id}/safety-approve` (body `SafetyApproveRequest`, optional), `POST /events/{event_id}/safety-request-changes` (`SafetyChangesRequest`), `POST /events/{event_id}/safety-reject` (`SafetyRejectRequest`); each returns `EventResponse`, plain `def`.
- Service: `safety_approve(event_id, officer_id, body) -> EventResponse`, `safety_request_changes(...)`, `safety_reject(...)`.
- `venues.service.event_booking_ids(event_id: str) -> set[str]` and `equipment.service.event_request_ids(event_id: str) -> set[str]` (every booking / equipment line id of the event, any status), used only to validate the officer's id lists. Check `IMPLEMENTATION_MAP` first; extend an existing function if one already returns these.

**Behaviour required:**
- Event missing or draft → 404; the officer needs no assignment. Status not `safety_review` → 409 `Cannot <action> an event that is <status>` via `lifecycle.target` (`safety_approve`, `safety_request_changes`, `safety_reject`).
- Request-changes / reject: each id in the lists must be in `event_booking_ids` / `event_request_ids`, else **422** `Unknown booking or equipment line for this event` and **no RPC call**.
- Approve: before the RPC, if `safety_readiness` (existing `_safety_readiness_for`) says not ready → 409 `Not ready for approval: <missing>` and no RPC. After an empty RPC result, re-read readiness: not ready → the same 409; otherwise `STALE_EVENT_MESSAGE`.
- Messages are fixed text (spec §7) plus the event name; the comment goes only into the RPC's comment parameter, never into any message.
- Responses are `EventResponse` of the updated event with `latest_safety_decision` unset.

- [ ] **Step 1: Write failing tests** (model on `test_send_for_safety_check.py`: same `state` fixture style, `authenticate_as`, mock the repository functions): happy path for each endpoint (right repository call with version, comment, ids, fixed messages; response status `confirmed` / `planning`); 404 missing and draft; 409 for every status except `safety_review` (parametrised); 409 stale (`None` from the repository); 409 not-ready approve naming the missing items with the RPC not called; 409 on an empty approve RPC result when readiness has since failed; 422 for blank, whitespace-only and 1001-character comment/reason; 422 for a foreign booking id, a foreign equipment id and an unknown id, with the repository not called; duplicate ids sent once; 403 for each of organiser, coordinator, venue staff, tech support, attendee and Lead; 403 for an account holding `safety_officer` whose **active** role is another, via a raw request; a second identical request after success answers 409; the comment text never appears in any message passed to the repository (assert on the captured arguments).
- [ ] **Step 2–4: red, implement, green.** The existing route-matrix test must still pass and cover the new routes (add them to its table if it is data-driven).
- [ ] **Step 5: Commit** `feat(events): add Safety Officer approve, request-changes and reject endpoints (CR-104)`.

---

### Task 5: Queue, review page, decision history and event-read changes

**Files:**
- Modify: `backend/app/modules/events/service.py`, `router.py`, `schemas.py`; `venues/service.py` and `equipment/service.py` for the read functions below
- Test: `backend/tests/test_safety_queue_and_review.py` (create); extend `backend/tests/test_events_api.py` for the event-read assertions

**Interfaces — Produces:**
- `GET /events/safety-queue` (SafetyOfficer; **declared above `/{event_id}`** like the coordinator dashboard) → `SafetyQueueResponse {items: list[SafetyQueueItem]}`; `SafetyQueueItem {event_id, name, organiser_name, starts_at, expected_attendance, entered_review_at}`. Ordered by `entered_review_at` ascending, event id as tie-breaker.
- `GET /events/{event_id}/safety-review` (SafetyOfficer) → `SafetyReviewResponse {event: {id, name, organiser_name, coordinator_name: str | None, starts_at, ends_at, expected_attendance, accessibility_needs, registration: {enabled, capacity, opens_at, closes_at}}, venues: list[{booking_id, venue_id, venue_name, booking_status, capacity, layouts, accessibility_features, attendance_to_capacity: float | None, emergency_access: None, restrictions: None}], equipment_lines: list[{id, equipment_name, quantity, status}], exit_confirmation: None, decisions: list[SafetyDecision]}`. 404 unless the event exists, is not a draft, and is in `safety_review`. `emergency_access`, `restrictions` and `exit_confirmation` are always `null` for now (CR-100, story 24).
- `GET /events/{event_id}/safety-decisions` → `list[SafetyDecision]` newest first, for the assigned `event_coordinator` or a `safety_officer`, by the **active** role; the organiser, other coordinators and every other role get 403 (a coordinator who is not assigned: 403).
- `venues.service.event_bookings_with_venues(event_id) -> list[dict]` (booking id, status, venue id/name/capacity/layouts/accessibility features) and `equipment.service.event_lines(event_id) -> list[dict]`; reuse what exists before adding.
- `service.read(...)`: coordinator on a `planning` event → `latest_safety_decision` is the full `SafetyDecision` (with comment); organiser on `planning`, `safety_review` or `confirmed` → `SafetyDecisionSummary` with a fixed `reason_label` (spec §7) and **no comment**; every other role/status → `None`. `GET /events/{id}/history` is unchanged and must not contain comments.

- [ ] **Step 1: Write failing tests**: queue oldest first by latest entry into review; a resubmitted event moves to the back; equal times sorted by id; empty queue; excludes events in other statuses; 403 matrix on all three new GETs including the multi-role raw request; review payload shape with the three `null` fields and `attendance_to_capacity` (attendance ÷ capacity, `None` when capacity is zero or attendance missing); review 404 for a missing event, a draft and an event not in review; decisions read refuses the organiser and an unassigned coordinator, allows the assigned coordinator and an officer; event read matrix for `latest_safety_decision` (full for coordinator, label only for organiser, none elsewhere); **leakage**: seed a decision whose comment is a unique marker string, then assert the marker is absent from the organiser's event read, the organiser's history read, and the JSON of every response the organiser can reach.
- [ ] **Step 2–4: red, implement, green.**
- [ ] **Step 5: Commit** `feat(events): add safety queue, review page and decision history reads (CR-103)`.

---

### Task 6: Frontend API client and store

**Files:**
- Modify: `frontend/src/services/api.js`
- Create: `frontend/src/features/events/safetyDecisionStore.js`
- Test: `frontend/src/features/events/__tests__/safetyDecisionStore.spec.js`, extend `frontend/src/services/__tests__/` (the existing api spec) if one covers `eventsApi`

(Do not touch the existing `safetyReview.js`/`safetyReview.spec.js` from SCRUM-82; this store is named differently on purpose.)

**Interfaces — Produces:**
- `eventsApi.safetyQueue(token)`, `safetyReview(eventId, token)`, `safetyDecisions(eventId, token)`, `safetyApprove(eventId, body, token)`, `safetyRequestChanges(eventId, body, token)`, `safetyReject(eventId, body, token)`.
- Pinia store `useSafetyDecisionStore` with state `queue`, `review`, `decisions`, `loading`, `error`, and actions `loadQueue()`, `loadReview(eventId)`, `decide(kind, eventId, payload)` where `kind` is `approve | requestChanges | reject`. Follow `eventReviewStore.js` (its `act()` pattern, token handling, error surfacing, 409 text preserved).

- [ ] **Step 1: Write failing tests**: each api function's method, path, body and bearer header; `loadQueue`/`loadReview` fill state and clear stale data on failure; `decide` posts the right endpoint per kind, refreshes the review/queue, and keeps the server's 409/422 message in `error`; nothing is sent when no token.
- [ ] **Step 2–4: red, implement, green.** **Step 5: Commit** `feat(frontend): add Safety Officer API client and store (CR-103, CR-104)`.

---

### Task 7: Queue page and review page

**Files:**
- Modify: `frontend/src/views/dashboards/SafetyDashboard.vue`, `frontend/src/router/index.js`
- Create: `frontend/src/views/events/SafetyReviewView.vue`
- Test: `frontend/src/views/__tests__/` (new specs for both views), `frontend/src/router/__tests__/activeRoleAccess.spec.js` (extend)

Read `frontend/AGENTS.md` and reuse the design-system components (`ConfirmModal`, `Bauhaus*` inputs, existing badges). Match `CoordinatorEventView.vue` for layout and wording style.

**Behaviour required:**
- `SafetyDashboard`: replaces the placeholder body with the queue (event name linked to its review, organiser, start, attendance, "Waiting since" with the entered-review time), oldest first, with an empty state "No events are waiting for a safety check." and a loading and error state.
- Route `/safety/events/:id`, name `safety-review`, `meta: { requiresAuth: true, allowedRoles: ["safety_officer"] }` using the active role like the existing safety route.
- `SafetyReviewView`: shows the event summary and the event's accessibility needs; for each venue its capacity, layouts, accessibility features and attendance against capacity; **"Not recorded"** for emergency access, restrictions and exit confirmation; the equipment lines (or "No equipment requested"); earlier decisions with who and when; a decision panel: a comment box with the hint "Record any crowd-movement concerns here.", checkboxes for the event's bookings and equipment lines (labelled by venue/equipment name), and **Approve**, **Request changes**, **Reject** buttons. Request changes and Reject are disabled until the comment is non-blank; each opens `ConfirmModal` (titles "Approve this event?", "Request changes?", "Reject the safety arrangement?"; the reject message says the arrangement must be replaced and the event itself is not rejected). Success returns to the queue with a toast ("Event approved", "Changes requested", "Arrangement rejected"); a 409/422 shows in the page alert. Phone width is usable (no horizontal scroll).

- [ ] **Step 1: Write failing tests** for: queue rows, order as returned, empty/loading/error states, link target; review page rendering of every field including the three "Not recorded" labels and "No equipment requested"; comment required for the two returning decisions; ticked ids are sent; modal text and confirm labels; toast and redirect on success; 409 shown; route guard denies every non-`safety_officer` active role, including an account that also holds `safety_officer` while acting as another role (extend `activeRoleAccess.spec.js`).
- [ ] **Step 2–4: red, implement, green.** **Step 5: Commit** `feat(frontend): add the Safety Officer queue and review page (CR-103, CR-104)`.

---

### Task 8: Coordinator banner and organiser line

**Files:**
- Modify: `frontend/src/views/events/CoordinatorEventView.vue`, `EventDetailView.vue`; `frontend/src/features/events/eventReviewStore.js` only if the decision needs loading there
- Test: extend the existing specs for both views (`frontend/src/views/__tests__/`)

**Behaviour required:**
- Coordinator, event in `planning` with `latest_safety_decision`: a "Safety Officer's decision" banner with the decision label, the comment, who/when, and the affected arrangements; a released booking shows "Rejected by the Safety Officer" beside it. The full decision list comes from `GET /events/{id}/safety-decisions` (add the api function and store call).
- Organiser: one plain line from `latest_safety_decision.reason_label` on `planning`, `safety_review` and `confirmed`; **nothing else**, never a comment.

- [ ] **Step 1: Write failing tests**: banner content and absence for other statuses/roles; the organiser view renders `reason_label` and never renders a `comment` even if the response object carries one (guard against a future backend leak by asserting the template ignores it).
- [ ] **Step 2–4: red, implement, green.** **Step 5: Commit** `feat(frontend): show the safety decision to the coordinator and a plain reason to the organiser (CR-104)`.

---

### Task 9: Live checks, test cases and the paper trail

**Files:**
- Modify: `backend/scripts/verify_live.py`, `frontend/e2e/` (extend `safety-check.e2e.js` or add a file), `docs/IMPLEMENTATION_MAP.md`, `docs/BUILD_LOG.md`, `docs/REQUIREMENTS.md`, `docs/test-cases/<area>.md`
- Create: `docs/test-cases/` entries for the Safety Officer area (read `docs/test-cases/README.md` for the format)

- [ ] **Step 1: Automate what a script can**, case ID first in each check name (`backend/scripts/verify_live.py`): 403 for every non-officer role on each new endpoint; 404 for a missing event; 409 for a fixture event not in `safety_review`; 422 for a blank comment. **No check may change seeded or shared data.** `frontend/e2e/`: the route guard for non-officers, and the queue's empty state if a Safety Officer account exists. No Safety Officer account exists in the live project yet; accounts are granted by hand (`docs/SETUP.md`, "Grant a staff role"). Checks that need one stay manual or are listed as not verified.
- [ ] **Step 2: Run the full suites**: `pytest` from `backend/` and `npm run test:coverage` from `frontend/`; fix failures in your own code; report coverage gaps line by line. Run `python scripts/verify_live.py --record` and `npm run test:e2e:record` only if both servers can run on spare ports (see `AGENTS.md`, "Live checks"); a failure is a finding, never something to re-run until green. Do not reset the fixture; ask the developer.
- [ ] **Step 3: Docs.** `IMPLEMENTATION_MAP.md`: status table rows for CR-103 (AC1–4, AC6) and CR-104, the endpoints, `event_safety_decisions`, the three RPCs, `return_to_planning` and its contract (copy §9 of the spec), the reuse tables, the residual technical-status race, and a prominent "no callers wired: CR-104 AC6 and AC10 complete only as CR-94, CR-95, 85, 24, 37 call `return_to_planning`" note; replace the `SafetyDashboard` placeholder note; replace "Last updated". `BUILD_LOG.md` §4: append entries for CR-104 and CR-103. `REQUIREMENTS.md`: the five lifecycle rows, the decision-visibility rule (AUTH-R2), §9 items (AC3 consult, same-venue, CR-100, 24). `docs/test-cases/`: manual cases traced to each AC with Type, Created and Last run; mark cases needing a Safety Officer account.
- [ ] **Step 4: Commit** the docs and checks (`docs: ...`, `test(live): ...`, separately), then write the final report: what changed, how verified, **what was not verified** (the database script until the developer pushes the migration, anything needing a live Safety Officer account, CR-100/24 fields, AC6/AC10 end to end), follow-ups, and the items only the developer can do (migration push, the manual browser pass, the PR, review, PO acceptance, merge, setting the PBIs to Done).

---

## Self-review notes

- Spec coverage: §1 delivery boundary → Task 3 and Task 9 docs; §3 decisions → Tasks 1, 4, 5; §4 database → Task 1; §5 backend → Tasks 2–5; §6 frontend → Tasks 6–8; §7 plain reasons → Tasks 5 and 8; §8 testing → each task plus Task 9; §9 contract → Task 3 and Task 9; §10 paper trail → Task 9.
- Names used across tasks: `SafetyDecision`, `SafetyDecisionSummary`, `ReturnReason`, `SafetyChangesRequest`, `SafetyRejectRequest`, `repository.safety_approve|safety_return|return_to_planning|list_safety_decisions|list_safety_queue`, `service.return_to_planning`, `venues.service.event_booking_ids|event_bookings_with_venues`, `equipment.service.event_request_ids|event_lines`, `useSafetyDecisionStore`. Keep them identical.
- No open choices are left to the implementer.
