# CR-104 Safety Decision Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Implementer: Codex.** This plan gives requirements, interfaces and tests, not finished code. Write the implementation yourself, test first. Read `AGENTS.md`, `backend/AGENTS.md` and `frontend/AGENTS.md` before starting.

**Goal:** Rework CR-104's Request changes and Reject decisions to the Session 3 rules: request changes resets nothing, and reject flags one venue booking **Safety rejected** (not released). The coordinator clears the flag with **Mark as revised** and sends the event again.

**Architecture:** One new migration replaces `public.safety_return_event` (same signature), adds `safety_rejected` to `public.venue_booking_flag`, and adds `public.mark_safety_revision`. The events module narrows the reject body to one `booking_id` and labels the new flag in readiness. The venues module gets `POST /venue-bookings/{id}/mark-revised`. The frontend changes the officer's Reject form to a single-venue choice and shows a Safety rejected notice with a Mark as revised button on the coordinator's event page.

**Tech Stack:** Postgres (Supabase, plpgsql security-definer RPCs), FastAPI + Pydantic v2, pytest; Vue 3 `<script setup>`, Pinia, Vitest, Playwright; `backend/scripts/verify_live.py`.

**Spec:** `docs/superpowers/specs/2026-10-18-cr-104-safety-decision-rework-design.md` (read it first). The ACs are in Product backlog row 71, quoted in the spec's AC table.

## Global Constraints

- Branch `feature/cr-104-safety-decision-rework` (already created from `main`; spec committed as `56c918d`). Never commit to `main`. Stage files by name.
- Commit messages: `feat(events): … (CR-104)` / `feat(venues): …` / `test(...)` / `docs: …`, with a body explaining *why*. **No attribution lines.**
- **New migration only:** `supabase/migrations/20261018150000_cr104_safety_decision_rework.sql`. Never edit an applied migration. **Do not run `supabase db push`**: run `--dry-run` and stop. The developer pushes.
- Authorise by the **active role**: `require_roles([...])` / `CurrentUser.role`. Never `user_roles` / `CurrentUser.roles`.
- Every new RPC: `security definer`, `set search_path = ''`, `revoke execute … from public, anon, authenticated`, `grant execute … to service_role`.
- `venue_booking_flag` gains exactly the value `safety_rejected`. Its label everywhere is exactly **`Safety rejected`**.
- Booking history `action` values added: `safety_rejected` and `safety_revised`. Labels: `Safety rejected`, `Marked revised`.
- Out of scope: the `preparation` status (68 AC8), cancelling a booking (85), the checklist and organiser-visible comments (CR-108), pick-up (CR-107), replacing a Safety-rejected venue through CR-95's replacement path.
- Coverage: 100% of new and changed lines in `backend/app/` and `frontend/src/` (`docs/CI.md` §4 item 2).
- Backend venv: `/home/jclim/projects/ConnectSphere/backend/.venv/bin/python`. Supabase CLI: `/home/linuxbrew/.linuxbrew/bin/supabase` (prefix commands with `env PATH=/home/linuxbrew/.linuxbrew/bin:/usr/bin:/bin`).

## Review Focus

1. **The officer rejects a booking that is not `approved`, or is already flagged** (Affected/Unsuitable/Safety rejected). Expected: 409, no decision row, no status change. Pinned in Task 1 (SQL) and Task 2 (API).
2. **A Mark as revised request from a coordinator who holds the role but is not the event's assigned coordinator, or who is acting as another role.** Expected: 403, no change. Pinned in Task 3.
3. **Mark as revised while the event is in Safety review or Confirmed** (for example, after the coordinator sent it again with the flag still set, which readiness should already block). Expected: 409 "only in Planning". Pinned in Task 1 and Task 3.
4. **A multi-venue event where one space's booking is rejected.** Expected: readiness names only that space ("<label>: flagged Safety rejected."), and the other space has no message. Pinned in Task 2.
5. **An organiser who reads the event after a rejection.** Expected: no `flag`/`flag_reason` (the existing `_for_role` redaction), so the officer's reason never reaches the organiser. Pinned in Task 2.

---

## File map

| File | Change | Task |
|------|--------|------|
| `supabase/migrations/20261018150000_cr104_safety_decision_rework.sql` | Create | 1 |
| `supabase/verification/safety_decision_checks.sql` | Modify: new AC2/AC3 assertions, mark-revised | 1 |
| `backend/app/modules/events/schemas.py` | `SafetyRejectRequest` | 2 |
| `backend/app/modules/events/service.py` | reject path, `_SAFETY_LABELS` | 2 |
| `backend/app/modules/events/readiness.py` | `FLAG_LABELS` | 2 |
| `backend/app/modules/events/lifecycle.py` | comments + TODO(68 AC8) | 2 |
| `backend/tests/test_safety_decisions_api.py`, `test_safety_contracts.py`, readiness tests | Modify/add | 2 |
| `backend/app/modules/venues/{router,service,repository,schemas}.py` | mark-revised | 3 |
| `backend/tests/test_venue_booking_mark_revised_api.py` | Create | 3 |
| `frontend/src/views/events/SafetyReviewView.vue` | Reject radio, copy | 4 |
| `frontend/src/views/__tests__/SafetyViews.spec.js` | Modify | 4 |
| `frontend/src/features/venues/bookingRequest.js` | `safety-rejected` panel state | 5 |
| `frontend/src/features/venues/bookingDecision.js` | history labels | 5 |
| `frontend/src/components/venues/SafetyRejectedNotice.vue` | Create | 5 |
| `frontend/src/views/events/CoordinatorEventView.vue` | render notice, mark revised | 5 |
| `frontend/src/services/api.js`, `frontend/src/features/events/eventReviewStore.js` | API + store action | 5 |
| `backend/scripts/verify_live.py`, `frontend/e2e/safety-decision.e2e.js` | live checks | 6 |
| `docs/test-cases/safety-decisions.md`, `docs/IMPLEMENTATION_MAP.md`, `docs/BUILD_LOG.md`, `docs/REQUIREMENTS.md` | paper trail | 7 |

---

### Task 1: Database: flag value, reworked `safety_return_event`, `mark_safety_revision`

**Files:**
- Create: `supabase/migrations/20261018150000_cr104_safety_decision_rework.sql`
- Modify: `supabase/verification/safety_decision_checks.sql`

**Interfaces:**
- Consumes: the existing `public.safety_return_event(p_event_id uuid, p_actor_id uuid, p_expected_version integer, p_decision text, p_comment text, p_booking_ids uuid[], p_equipment_request_ids uuid[], p_coordinator_message text) returns setof public.events` in `20261009110000_safety_review_decision.sql`, plus `public.transition_event`, `public.venue_booking_history`, `public.event_safety_decisions`.
- Produces:
  - Enum value `public.venue_booking_flag` = `'safety_rejected'`.
  - `public.safety_return_event(...)`, **same signature and grants**, with new behaviour (below).
  - `public.mark_safety_revision(p_booking_id uuid, p_actor_id uuid) returns text`. Outcomes: `'ok' | 'booking_not_found' | 'not_safety_rejected' | 'not_planning' | 'not_assigned'`.

**Requirements: `safety_return_event`**
- Keep the decision validation, the event row lock (`version = p_expected_version and status = 'safety_review' for update`), the ownership checks on ids before and after the row locks, the transition to `planning`, the decision insert and the coordinator notification exactly as they are today.
- `changes_requested`: **do not update** `venue_bookings` or `equipment_requests`. Record the deduplicated ids in `affected_booking_ids` / `affected_equipment_request_ids`; `rejected_venue_ids` = `'{}'`.
- `arrangement_rejected`:
  - `cardinality(dedup booking ids) = 1` and `cardinality(equipment ids) = 0`. Otherwise `raise exception … using errcode = '22023'` (the API never sends anything else, so this is a programming error).
  - After the row lock, the booking must have `event_id = p_event_id`, `status = 'approved'` and `flag is null`. If not, **return no row** before transitioning, so nothing changes.
  - Set `flag = 'safety_rejected'`, `flag_reason = btrim(p_comment)`, `flagged_at = now()`. Leave the status unchanged.
  - Insert `venue_booking_history(booking_id, actor_id, action, from_status, to_status)` = `(id, p_actor_id, 'safety_rejected', 'approved', 'approved')`.
  - Decision row: `affected_booking_ids = {id}`, `affected_equipment_request_ids = '{}'`, `rejected_venue_ids = {that booking's venue_id}`.
- Header comment cites CR-104 AC2/AC3, QA3-46, QA3-47, SF-R3/SF-R4, LC-R7.

**Requirements: `mark_safety_revision`**
- Lock the booking row (`for update`), then the event row. Check in this order: booking missing → `booking_not_found`; `flag is distinct from 'safety_rejected'` → `not_safety_rejected`; event `coordinator_id is distinct from p_actor_id` → `not_assigned`; event `status <> 'planning'` → `not_planning`.
- On `ok`: clear `flag`, `flag_reason` and `flagged_at` (all three, to satisfy `venue_bookings_flag_consistent`); insert history `(id, p_actor_id, 'safety_revised', status, status)`. No notification **[Assumption]**. No event version bump.
- `comment on function` naming CR-104 AC3/AC4 and "API-only".
- Update `comment on column public.venue_bookings.flag` to list `safety_rejected (CR-104: the Safety Officer rejected this venue for the event; cleared by the coordinator's Mark as revised)`.
- **Enum caveat:** `alter type … add value` must be the first statement. No top-level statement may use the `'safety_rejected'` literal (function bodies are fine, because plpgsql resolves them at run time).

- [ ] **Step 1: Write the failing verification first.** In `safety_decision_checks.sql`:
  - Replace the old `re_review` / `released` / equipment `rejected` assertions.
  - Update the preflight to also require `to_regprocedure('public.mark_safety_revision(uuid,uuid)')` and the enum value (`select 1 from pg_enum e join pg_type t on t.oid = e.enumtypid where t.typname = 'venue_booking_flag' and e.enumlabel = 'safety_rejected'`). Raise `'SAFETY FAIL: …'` otherwise, so running it before the migration fails for the right reason.
  - Add fixtures with the existing pattern (random ids, `safety_fixture` keys) and these assertions, each raising `SAFETY FAIL: <what>` on failure:
    - `changes`: after `changes_requested` naming an approved booking and a reserved line, both statuses are unchanged, the event is `planning`, the decision row holds both ids, and the coordinator has one `event_safety_changes_requested` notification.
    - `reject`: after `arrangement_rejected` naming one approved booking, its status is still `approved`, `flag = 'safety_rejected'` and `flag_reason` = the trimmed reason. There is one history row `safety_rejected`. The equipment line is untouched. `rejected_venue_ids = {venue}` and the event is `planning`.
    - `reject_multi` (two bookings on two event spaces): rejecting one leaves the other `approved` with `flag is null`.
    - `reject_held` / `reject_flagged`: returns 0 rows; the event is still `safety_review` with no decision row.
    - Two booking ids passed to `arrangement_rejected` raise SQLSTATE `22023`.
    - `mark_safety_revision`: `ok` clears all three flag columns and writes one `safety_revised` history row. A second call → `not_safety_rejected`. Another coordinator → `not_assigned`. Event in `safety_review` → `not_planning`. A random id → `booking_not_found`.
  - Keep the file's `begin; … rollback;` shape so it leaves no data.
- [ ] **Step 2: Confirm RED.** Run `env PATH=/home/linuxbrew/.linuxbrew/bin:/usr/bin:/bin supabase db query --linked -f supabase/verification/safety_decision_checks.sql` (or the way `verify_live.py` runs its SQL files; check `backend/scripts/verify_live.py` around line 97). Expected: `SAFETY FAIL: …interfaces are missing`.
- [ ] **Step 3: Write the migration** to the requirements above.
- [ ] **Step 4: Dry run.** `env PATH=/home/linuxbrew/.linuxbrew/bin:/usr/bin:/bin supabase db push --dry-run`. Expected: only `20261018150000_cr104_safety_decision_rework.sql` is pending (plus `20261018140000_…` if it's still unpushed: report which). **Stop and tell the developer to push.** After the push, re-run Step 2's command. Expected: no `SAFETY FAIL`.
- [ ] **Step 5: Commit** `supabase/migrations/20261018150000_cr104_safety_decision_rework.sql supabase/verification/safety_decision_checks.sql`, with the message `feat(events): safety rejection flags the venue booking instead of releasing it (CR-104)`.

---

### Task 2: Events API: reject names one booking; readiness labels Safety rejected; AC6 TODO

**Files:**
- Modify: `backend/app/modules/events/schemas.py` (`SafetyRejectRequest`, around line 327)
- Modify: `backend/app/modules/events/service.py` (`_SAFETY_LABELS` around line 829, `_safety_return` / `safety_reject` around lines 866–892)
- Modify: `backend/app/modules/events/readiness.py` (`FLAG_LABELS`)
- Modify: `backend/app/modules/events/lifecycle.py` (comments on `safety_request_changes`, `safety_reject` and `approved_change`)
- Test: `backend/tests/test_safety_decisions_api.py`, `backend/tests/test_safety_contracts.py`, and the readiness unit tests (find them with `grep -ln safety_readiness backend/tests`)

**Interfaces:**
- Consumes: Task 1's `safety_return_event` behaviour. Its no-row result means "stale, or the booking can't be rejected".
- Produces:
  - `class SafetyRejectRequest(BaseModel)`: `reason: str` (1–1000, stripped before validation, as today) and `booking_id: UUID`. It does **not** inherit `SafetyArrangementIds`, and unknown fields stay ignored as in the existing models.
  - `readiness.FLAG_LABELS["safety_rejected"] == "Safety rejected"`.
  - `service._SAFETY_LABELS["arrangement_rejected"] == "The Safety Officer rejected a venue for this event; its booking is flagged Safety rejected."`.
  - The 409 message for a reject no-row result: `"This venue booking can't be rejected: it must be approved and not already flagged, or the event changed. Reload and try again."` (constant `SAFETY_REJECT_REFUSED_MESSAGE` in `service.py`).

**Requirements**
- `safety_reject` calls `repository.safety_return(..., decision="arrangement_rejected", booking_ids=[str(body.booking_id)], equipment_request_ids=[])`.
- If `booking_id ∉ venues_service.event_booking_ids(event_id)`, raise `UnknownEventArrangementError` (422, the existing message) before the RPC.
- If the RPC returns no row → always 409 `SAFETY_REJECT_REFUSED_MESSAGE` (it already covers "or the event changed"). Don't re-read the event to tell the two apart. Update the existing `test_stale` reject case to expect this message; approve and request changes keep `STALE_EVENT_MESSAGE`.
- Request changes is unchanged in the API.
- `lifecycle.TRANSITIONS["approved_change"]` stays `({confirmed}, planning)`. Add the comment `# TODO(68 AC8): add EventStatus.preparation once it exists (CR-104 AC6, QA3-16).`

- [ ] **Step 1: Write the failing tests.** Update `CASES` in `test_safety_decisions_api.py` to give the reject body `{'reason': '  PRIVATE-MARKER  ', 'booking_id': BOOKING}`, and update `test_foreign_ids` (reject now sends `booking_id: FOREIGN`). Then add:

```python
def test_reject_sends_exactly_the_named_booking(client, auth_headers, authenticate_as, state):
    authenticate_as('safety_officer')
    result = post(client, auth_headers, 'safety-reject', {'reason': 'Exits blocked', 'booking_id': BOOKING})
    assert result.status_code == 200
    (_, kwargs), = state['calls']
    assert kwargs['booking_ids'] == [BOOKING] and kwargs['equipment_request_ids'] == []
    assert kwargs['decision'] == 'arrangement_rejected'

@pytest.mark.parametrize('body', [{'reason': 'x'}, {'reason': 'x', 'booking_id': 'not-a-uuid'}])
def test_reject_requires_one_booking_id(client, auth_headers, authenticate_as, state, body):
    authenticate_as('safety_officer')
    assert post(client, auth_headers, 'safety-reject', body).status_code == 422
    assert not state['calls']

def test_reject_refused_by_database_is_409_with_reason(client, auth_headers, authenticate_as, state):
    authenticate_as('safety_officer')
    state['stale'] = True   # RPC returns no row (stale, or the booking can't be rejected)
    result = post(client, auth_headers, 'safety-reject', {'reason': 'x', 'booking_id': BOOKING})
    assert result.status_code == 409
    assert result.json()['detail'].startswith("This venue booking can't be rejected")

def test_changes_requested_body_unchanged(client, auth_headers, authenticate_as, state):
    authenticate_as('safety_officer')
    result = post(client, auth_headers, 'safety-request-changes',
                  {'comment': 'Move the stage', 'booking_ids': [BOOKING], 'equipment_request_ids': [LINE]})
    assert result.status_code == 200
    (_, kwargs), = state['calls']
    assert kwargs['decision'] == 'changes_requested'
```

  Readiness unit tests (pure functions):

```python
def test_safety_rejected_booking_is_not_ready_event_wide():
    result = safety_readiness([BookingReadiness(status='approved', flags=['safety_rejected'])], ReadinessState.ready)
    assert result.ready is False
    assert "A venue booking is flagged Safety rejected." in result.missing

def test_only_the_rejected_space_is_reported():
    spaces = [SpaceReadiness(label='Hall A', bookings=[BookingReadiness(status='approved', flags=['safety_rejected'])]),
              SpaceReadiness(label='Hall B', bookings=[BookingReadiness(status='approved')])]
    result = safety_readiness([], ReadinessState.ready, spaces)
    assert result.missing == ['Hall A: flagged Safety rejected.']
```

  Lifecycle (AC6 TODO pin):

```python
def test_approved_change_sources_until_68_lands():
    # CR-104 AC6: add `preparation` here when 68 AC8 creates it.
    assert lifecycle.allowed_from('approved_change') == ['confirmed']
    assert 'preparation' not in {s.value for s in EventStatus}
```

  Organiser redaction (Review Focus 5): in the existing event-read tests (`grep -ln "_for_role\|flag_reason" backend/tests`), add a case where a booking has `flag='safety_rejected'`. Reading as `event_organiser` returns `flag is None and flag_reason is None`; reading as `event_coordinator` returns both.
- [ ] **Step 2: Run them and confirm they fail for the right reason.** `cd backend && .venv/bin/python -m pytest tests/test_safety_decisions_api.py <readiness test file> -q`. Expected failures: 422 on the new body (the schema still wants `booking_ids`), and a missing `Safety rejected` label.
- [ ] **Step 3: Implement** to the requirements.
- [ ] **Step 4: Run the full suite.** `cd backend && .venv/bin/python -m pytest -q`. Expected: all pass, with no test left expecting `re_review`/`released` from a safety decision.
- [ ] **Step 5: Commit**, with the message `feat(events): reject names one venue booking and readiness reports Safety rejected (CR-104)`.

---

### Task 3: Venues API: `POST /venue-bookings/{id}/mark-revised`

**Files:**
- Modify: `backend/app/modules/venues/router.py`. Add `CoordinatorOnly = Annotated[CurrentUser, Depends(require_roles(["event_coordinator"]))]` if no such alias exists, and add the route beside `restore_venue_booking`.
- Modify: `backend/app/modules/venues/repository.py` (`mark_safety_revision(booking_id, actor_id) -> str`, calling the RPC and returning the outcome text)
- Modify: `backend/app/modules/venues/service.py` (`mark_safety_revision(booking_id: str, actor_id: str) -> VenueBookingDetail`)
- Create: `backend/tests/test_venue_booking_mark_revised_api.py`. Reuse the fixtures from `tests/test_venue_booking_reject_api.py` the way `test_venue_booking_restore_api.py` does.

**Interfaces:**
- Consumes: Task 1's `public.mark_safety_revision` outcomes.
- Produces: `POST /api/v1/venue-bookings/{booking_id}/mark-revised` with no body. Responses:
  - 200: `VenueBookingDetail` with `flag: null`
  - 404 `booking_not_found` (`BookingNotFoundError`)
  - 403 `not_assigned` (`NotAssignedCoordinatorError`, or the venues module's equivalent; reuse, don't add a new class unless none exists)
  - 409 `not_safety_rejected`: "This booking isn't flagged Safety rejected."
  - 409 `not_planning`: "A booking can be marked revised only while the event is in Planning."

  409s use `BookingDecisionConflictError`, through a `MARK_REVISED_REFUSALS` dict like `RESTORE_REFUSALS`.

- [ ] **Step 1: Write the failing tests.** Use a `revising` fixture modelled on `restoring`: it monkeypatches `venues_repository.mark_safety_revision` to record calls, return `bookings["outcome"]`, and on `ok` clear the fake booking's flag. Tests:
  - `test_assigned_coordinator_marks_revised_and_sees_it_unflagged`: 200, the call recorded as `(BOOKING_ID, COORDINATOR_ID)`, `flag is None`.
  - `test_outcomes_map_to_status`, parametrized over `[('booking_not_found', 404), ('not_assigned', 403), ('not_safety_rejected', 409), ('not_planning', 409)]`.
  - `test_other_active_roles_are_denied`, parametrized over `['venue_staff', 'safety_officer', 'event_organiser', 'tech_support', 'attendee', 'event_coordinator_lead']`: 403, and the RPC is never called.
  - `test_holding_coordinator_role_but_acting_as_venue_staff_is_denied`. Use the `acting_as_another_role` helper from `tests/test_event_comments_api.py` (SCRUM-76 pattern): 403, RPC not called.
  - `test_unauthenticated_is_401`.
- [ ] **Step 2: Run them; they fail with 404/405** (no route yet).
- [ ] **Step 3: Implement.** The docstring cites CR-104 AC3/AC4 and the [Team decision].
- [ ] **Step 4: Run the full suite** (`.venv/bin/python -m pytest -q`). Expected: all green.
- [ ] **Step 5: Commit**, with the message `feat(venues): coordinator marks a Safety-rejected booking revised (CR-104)`.

---

### Task 4: Safety Officer's form: Reject picks one venue; corrected copy

**Files:**
- Modify: `frontend/src/views/events/SafetyReviewView.vue`
- Modify: `frontend/src/features/events/safetyDecisionStore.js` (only if the payload is built there)
- Test: `frontend/src/views/__tests__/SafetyViews.spec.js`

**Interfaces:**
- Consumes: Task 2's reject body `{ reason, booking_id }`; request changes stays `{ comment, booking_ids, equipment_request_ids }`.
- Produces: no new exports.

**Requirements**
- Keep the existing checkboxes for Request changes under the heading **"Arrangements this concerns (optional)"**.
- Add a radio group headed **"Venue to reject (required for Reject)"**, one option per `review.venues` entry, valued by `venue.booking_id` and labelled by `venue.venue_name`. Disable an option whose `booking_status !== 'approved'`.
- The Reject button is disabled until the text is non-blank **and** a venue is selected.
- Dialog copy (exact):
  - requestChanges.message: `"The event returns to Planning. No booking or equipment changes status; the coordinator decides what to change."`
  - reject.title: `"Reject this venue for the event?"`
  - reject.message: `"The event returns to Planning and this venue's booking is flagged Safety rejected. It is not released, and the event itself is not rejected."`
  - reject.toast: `"Venue rejected"`
- After a decision, reset the radio selection along with the existing refs.
- Phone width: the radio list stacks, with no horizontal scroll (matching the existing checkbox markup).

- [ ] **Step 1: Write the failing tests** in `SafetyViews.spec.js`, following the file's existing mount and mocking pattern:
  - The Reject button is disabled with a reason but no venue, and enabled once a venue radio is chosen.
  - Confirming Reject calls `safetyReject(eventId, { reason: 'Exits blocked', booking_id: 'booking-1' }, token)`. Assert the exact payload, with no `booking_ids` or `equipment_request_ids` keys.
  - Request changes still sends the ticked ids under `booking_ids`/`equipment_request_ids`.
  - The two dialog messages render the exact strings above.
  - A venue whose `booking_status` is `held` has its radio disabled.
  - Update or remove the existing assertions that expect the old copy ("must be replaced", "need re-review").
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/views/__tests__/SafetyViews.spec.js`. Expected: the new tests fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npm run test:coverage`. Expected: all pass, and changed lines covered.
- [ ] **Step 5: Commit**, with the message `feat(events): Safety Officer rejects one named venue (CR-104)`.

---

### Task 5: Coordinator sees Safety rejected on the booking and marks it revised

**Files:**
- Modify: `frontend/src/features/venues/bookingRequest.js` (`venuePanelState` and a new `safetyRejectedPanelState`)
- Modify: `frontend/src/features/venues/bookingDecision.js` (`HISTORY_ACTION_LABELS`)
- Create: `frontend/src/components/venues/SafetyRejectedNotice.vue`
- Modify: `frontend/src/views/events/CoordinatorEventView.vue` (the per-space panels around line 305 and the single-venue panel around line 343)
- Modify: `frontend/src/services/api.js` (`venueBookingsApi.markRevised`)
- Modify: `frontend/src/features/events/eventReviewStore.js` (`markBookingRevised(bookingId)`)
- Tests: `frontend/src/features/venues/__tests__/bookingRequest.spec.js`, a new `frontend/src/components/venues/__tests__/SafetyRejectedNotice.spec.js`, `frontend/src/views/__tests__/CoordinatorEventView.spec.js`, and the `bookingDecision` spec

**Interfaces:**
- Consumes: Task 3's endpoint; the event payload's `venue_bookings[]` items (`id`, `status`, `flag`, `flag_reason`, `event_space_request_id`), which the coordinator already receives unredacted.
- Produces:
  - `venueBookingsApi.markRevised(bookingId, token)`, which POSTs `/venue-bookings/{id}/mark-revised`.
  - `venuePanelState(event, space)` returns `{ kind: "safety-rejected", booking, reason, canMarkRevised }` when a booking in scope has `flag === "safety_rejected"` and a status in `["held", "approved"]`. This is checked **before** the affected state. `canMarkRevised = event.status === "planning"`.
  - `SafetyRejectedNotice` props `{ reason: String, canMarkRevised: Boolean, busy: Boolean }`, emitting `mark-revised`. It renders `data-testid="venue-safety-rejected"`, a badge with the exact text `Safety rejected`, the reason, the line `"Revise the arrangement with venue staff, then mark it revised and send the event for safety check again."`, and a button `Mark as revised` (only when `canMarkRevised`, disabled while `busy`). Style it like `AffectedBookingNotice.vue`.
  - Store: `markBookingRevised(bookingId)` calls the API, then `load(event.id)`, using the store's existing `isActing`/error handling. On 409, show the API's detail.
  - `HISTORY_ACTION_LABELS` gains `safety_rejected: "Safety rejected"` and `safety_revised: "Marked revised"`.
- View: after success, toast `"Marked revised. Send the event for safety check when everything is ready."`.

- [ ] **Step 1: Write the failing tests:**
  - `bookingRequest.spec.js`: a safety-rejected approved booking in a planning event gives `{kind: 'safety-rejected', canMarkRevised: true, reason}`. In a `safety_review` event, `canMarkRevised` is false. With two spaces, only the rejected space's panel is `safety-rejected` and the other is `booked`. A `released` booking with the flag is not `safety-rejected`.
  - `SafetyRejectedNotice.spec.js`: renders the badge, the reason and the guidance line. The button is hidden when `canMarkRevised` is false, disabled when `busy`, and emits `mark-revised` on click.
  - `CoordinatorEventView.spec.js`: with a mocked event that has a safety-rejected booking, the notice appears in the venue panel, and clicking calls `venueBookingsApi.markRevised('<id>', token)` and reloads the event. The multi-space variant shows the notice only under the rejected space.
  - `bookingDecision` spec: `historyActionLabel('safety_revised') === 'Marked revised'`.
- [ ] **Step 2: Run** `npx vitest run` on these files. Expected: they fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npm run test:coverage` and `npm run lint` if the project defines it. Expected: all green.
- [ ] **Step 5: Commit**, with the message `feat(events): coordinator sees Safety rejected on the booking and marks it revised (CR-104)`.

---

### Task 6: Live checks

**Files:**
- Modify: `backend/scripts/verify_live.py`
- Modify: `frontend/e2e/safety-decision.e2e.js` (only for checks that fit; most behaviour is API/DB)

**Requirements**
- Update or replace any existing check that asserts the old `re_review`/`released` outcome (search `verify_live.py` for `TC-SDEC-010` and `TC-SDEC-011`).
- Add checks named with their case ID first:
  - `TC-SDEC-016`: extend it so `POST /safety-reject` with `booking_ids` and no `booking_id` → 422 (uses the missing-UUID event, so no data changes).
  - `TC-SDEC-022` "Mark as revised is refused for every non-coordinator active role": POST to a random UUID booking as each shared non-coordinator session → 403.
  - `TC-SDEC-023` "Mark as revised on a missing booking → 404", as the coordinator session.
- The full reject → flag → mark revised → send again flow changes shared data, so it stays in the SQL verification (Task 1) and the manual pass. Don't build it on seeded events.
- Register the updated `safety_decision_checks.sql` description string at around line 98 (`"TC-SDEC-003, 009–011, 015–017, 024, 025 (database half)"`).

- [ ] **Step 1:** Write the checks, run `python scripts/verify_live.py --only TC-SDEC-022` (or the script's filter flag: check `--help`) against a backend running **this branch on a spare port** (`uvicorn app.main:app --port 8010`, `--api http://localhost:8010`). Expected before Task 3 is merged in: 404/405. After: 403.
- [ ] **Step 2: Commit**, with the message `test(live): CR-104 rework live checks`.

---

### Task 7: Paper trail

**Files:** `docs/test-cases/safety-decisions.md`, `docs/IMPLEMENTATION_MAP.md`, `docs/BUILD_LOG.md`, `docs/REQUIREMENTS.md`

**Requirements**
- `safety-decisions.md`:
  - Rewrite **TC-SDEC-010** (request changes changes no booking or line; the coordinator alone is notified) and **TC-SDEC-011** (reject flags one booking Safety rejected, which is not released, and the event goes to Planning, not Rejected).
  - Add **TC-SDEC-022** (mark-revised role denial, Automated), **TC-SDEC-023** (404, Automated), **TC-SDEC-024** (reject a held or already-flagged booking → 409, Automated via SQL), **TC-SDEC-025** (multi-venue: other space stays ready, Automated via SQL plus a manual look), **TC-SDEC-026** (mark revised then send again, end to end, Manual), **TC-SDEC-027** (officer form: radio, copy, phone width, Manual), **TC-SDEC-028** (coordinator notice wording and layout at 375px, Manual) and **TC-SDEC-029** (organiser sees no flag or reason, Manual).
  - Use the Type, Created (2026-10-18) and Last run columns. Update the AC trace table for AC1–AC4 and AC6.
- `IMPLEMENTATION_MAP.md`:
  - Status row for CR-104 (rework on this branch; migration `20261018150000` pending push).
  - Booking flag contract: add `safety_rejected`, set by `safety_return_event`, cleared only by `mark_safety_revision`, and first flag wins, so a Safety-rejected booking isn't flagged Affected later.
  - Reuse table: `mark_safety_revision`, `SafetyRejectedNotice`, `venueBookingsApi.markRevised`.
  - Replace the Session 3 "Safety decisions (CR-104)" bullet and the **CR-104-R** mention (around line 359–362) with the built state.
  - Know-before-you-build: 85 must handle cancelling a Safety-rejected booking so that a replacement can take the space's slot; 68 AC8 must add `preparation` to `approved_change`.
  - Replace the "Last updated" line.
- `BUILD_LOG.md` §4: append a CR-104 rework entry using the template. Say it reworks PR #50 after Session 3 and is not a defect fix.
- `REQUIREMENTS.md`:
  - §6.6.1 `safety_reject` row: add Mark as revised as a **[Team decision]**.
  - §9 item 33: the coordinator revises (Mark as revised) or cancels (85).
  - Add an **[Assumption]**: Mark as revised sends no notification, and venue staff can read the reason on the booking page (internal staff, SF-R6). Add it to §9.
  - Fix the §5 "Status (groundwork…)" note so it no longer says CR-104 is unwired for the decision behaviour.
- Re-grep for "Preparation stage" in `frontend/src`, `docs` (excluding `docs/prompts`) and `backend/app`. Remove any wording that describes Confirmed as Preparation.

- [ ] **Step 1:** Make the edits. **Step 2:** Commit with the message `docs: record the CR-104 rework, Mark as revised and test cases TC-SDEC-022 to 029`.

---

## After Codex: Claude's verification (not Codex's)

1. Review each task's diff against this plan and the spec.
2. Full `pytest` and `npm run test:coverage`.
3. After the developer pushes the migration: SQL verification, `get_advisors` (security + performance), `verify_live.py --record`, `npm run test:e2e:record`.
4. Ask the developer for the manual pass on TC-SDEC-011, 025–029.
5. Record the runs, then write the final report against `docs/DEFINITION_OF_DONE.md`.
