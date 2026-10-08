# SCRUM-82 Send Event for Safety Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **This plan is for Codex.** It states requirements, interfaces, tests and verification, not finished code. Write the implementation yourself, following the patterns named in each task. Test code below is a sketch of the assertions that define "done": adapt it to the file's existing fixtures, but keep every assertion.

**Goal:** The assigned coordinator, acting as coordinator, can send a ready `planning` event to `safety_review`. The page shows what's missing until it's ready, and the organiser and every Safety Officer are notified.

**Architecture:**
- A pure rule module (`events/readiness.py`) decides readiness from the event's booking statuses and its technical status. The coordinator's event read (to show what's missing) and the send endpoint (to enforce it) both use it.
- The send calls a new wrapper RPC, `public.send_event_to_safety_review`. It calls `public.transition_event` (status, version check, history row, organiser notification), then notifies Safety Officers, in one transaction.
- `safety_review` is added to the status lists named in Task 2 and Task 7.

**Tech Stack:**
- Backend: FastAPI 0.115, Pydantic 2.11, supabase-py 2.31 (plain `def` endpoints), pytest 8.3.
- Database: Postgres via Supabase migrations.
- Frontend: Vue 3 `<script setup>`, Pinia, Vitest; Playwright for e2e.

**Spec:** `docs/superpowers/specs/2026-10-08-scrum-82-send-for-safety-check-design.md`. Read it first. Decisions there are settled; don't reopen them.

**Before you start:**
- Branch `feature/scrum-82-send-for-safety-check` (already checked out, groundwork commits `649f569`, `a045864`, spec `7e14ef6`). Never commit to `main`.
- Read `AGENTS.md`, `backend/AGENTS.md`, `frontend/AGENTS.md`, and `docs/IMPLEMENTATION_MAP.md` §5.
- Backend venv: `backend/.venv` (`backend/.venv/bin/python -m pytest`).
- Supabase CLI: `env PATH=/home/linuxbrew/.linuxbrew/bin:/usr/bin:/bin supabase ...`.
- **Never run `supabase db push`.** Stop and ask the developer to run it (Task 3).

## Global Constraints

- Authorise by the session's **active** role: `require_roles(["event_coordinator"])` / `CurrentUser.role`. Never `CurrentUser.roles`, `user_roles` or `profiles.role` for access.
- Endpoints that call Supabase are plain `def`, not `async def`.
- Routers stay thin: no Supabase calls or business rules in `router.py`. Cross-module calls go through the other module's `service.py`, never its `repository.py`.
- Every lifecycle transition goes through `lifecycle.TRANSITIONS` and `transition_event` (here, through the wrapper RPC that calls it).
- No new libraries.
- Coverage floors must hold:
  - backend `fail_under` in `backend/.coveragerc`
  - frontend `thresholds.lines` in `frontend/vite.config.js`
  - 100% of new and changed lines, or list each gap with its reason.
- Messages, exactly as written:
  - Not ready, prefix: `Not ready for safety check: ` followed by the missing items joined with a single space.
  - Missing items, in this order:
    1. `No venue booking is approved.`
    2. `A venue booking is awaiting venue staff approval.`
    3. `A venue booking is under re-review.`
    4. `A venue booking is flagged <Label>.` (Label ∈ `Affected`, `Conflict`, `Unsuitable`, `Expired`, one item per distinct flag, in that order)
    5. `Technical status is not Ready.`
  - Wrong status: `Cannot send to safety an event that is <status with spaces>` (from the existing `EventTransitionError`).
  - Stale: `This event was updated by someone else. Reload.` (existing `STALE_EVENT_MESSAGE`).
  - Organiser notification: `Your event "<name>" is with the Safety Officer for its operational safety check.`
  - Safety Officer notification: `"<name>" is ready for its operational safety check.`
  - Notification type for both: `event_sent_for_safety_check`.
  - UI strings:
    - button `Send for safety check` (aria-label `Send for safety check`)
    - list heading `Not ready for safety check`
    - modal title `Send for safety check?`
    - modal message `The Safety Officer will check the venue and technical arrangements. Venue and equipment can't be requested again while it's in review.`
    - modal confirm `Send`
    - toast `Sent for safety check`
    - block heading `For information`
    - organiser card heading `Arrangements`
    - organiser group description `Events being checked by the Safety Officer.`
- Name test files by module and behaviour, with `SCRUM-82` in the module docstring. Live checks and manual cases start with their case ID (`TC-SAFE-0nn`).

## Review Focus

1. **Two active bookings, one approved and one held** (CR-97 will allow several): the event must be blocked. Pinned in Task 1.
2. **A stale coordinator page:** the page showed ready, but a booking went to `re_review` before the click. The POST answers 409 with the missing items, the page shows the error, **and reloads the event** so the button and list update. Pinned in Task 6.
3. **A double click, or two tabs sending at once:** exactly one send succeeds. The other answers 409 (wrong status or stale) and the RPC is never called twice with success. Pinned in Task 4.
4. **A Safety Officer who is also the assigned coordinator** (holds both roles, sends while acting as coordinator): they get no notification of their own action (NT-R1). The organiser and the other officers still do. Pinned in Task 3's SQL script.
5. **No Safety Officer accounts exist yet** (accounts are granted by hand): the send still succeeds, the organiser is still notified, and nothing errors. Pinned in Task 3's SQL script.

---

### Task 1: Pure readiness rule

**Files:**
- Create: `backend/app/modules/events/readiness.py`
- Modify: `backend/app/modules/events/schemas.py` (add two models)
- Test: `backend/tests/test_safety_readiness.py`

**Interfaces:**
- Consumes: `ReadinessState` from `events/schemas.py` (values `not_required`, `pending`, `ready`, `issue`).
- Produces:
  - `schemas.BookingReadiness(BaseModel)`: `status: str`, `flags: list[str] = []`.
  - `schemas.SafetyReadiness(BaseModel)`: `ready: bool`, `missing: list[str]`.
  - `readiness.ACTIVE_BOOKING_STATUSES: frozenset[str] = {"held", "approved", "re_review"}`.
  - `readiness.FLAG_LABELS: dict[str, str] = {"affected": "Affected", "conflict": "Conflict", "unsuitable": "Unsuitable", "expired": "Expired"}` (insertion order is the message order).
  - `readiness.safety_readiness(bookings: list[BookingReadiness], technical: ReadinessState) -> SafetyReadiness`.

**Requirements:**
- No I/O and no imports from repositories or services. Same style as `events/lifecycle.py`.
- Bookings whose status isn't in `ACTIVE_BOOKING_STATUSES` (`rejected`, `cancelled`, `released`) are ignored entirely, including their flags.
- Rules and messages exactly as in Global Constraints, each message at most once (flag messages once per distinct flag), in the fixed order.
- `ready` is `True` exactly when `missing` is empty.
- An unknown flag string is ignored (only `FLAG_LABELS` keys count). That keeps the seam safe if a flag story adds a value before a label is agreed.

- [ ] **Step 1: Write the failing tests**

```python
"""SCRUM-82: which events are ready for the Operational Safety Check. Pure rules, no I/O."""
import pytest
from app.modules.events.readiness import safety_readiness
from app.modules.events.schemas import BookingReadiness as B, ReadinessState as T

NO_BOOKING = "No venue booking is approved."
HELD = "A venue booking is awaiting venue staff approval."
RE_REVIEW = "A venue booking is under re-review."
TECH = "Technical status is not Ready."

def test_an_approved_booking_and_ready_technical_status_is_ready():
    result = safety_readiness([B(status="approved")], T.ready)
    assert result.ready is True and result.missing == []

def test_not_required_technical_status_counts_as_ready():  # AC3
    assert safety_readiness([B(status="approved")], T.not_required).ready is True

def test_no_booking_at_all_is_not_ready():  # [Assumption] spec §2
    assert safety_readiness([], T.ready).missing == [NO_BOOKING]

@pytest.mark.parametrize("closed", ["rejected", "cancelled", "released"])
def test_closed_bookings_are_ignored(closed):
    assert safety_readiness([B(status=closed)], T.ready).missing == [NO_BOOKING]
    assert safety_readiness([B(status=closed, flags=["affected"]), B(status="approved")], T.ready).ready is True

def test_a_held_booking_blocks():  # AC9
    assert safety_readiness([B(status="held")], T.ready).missing == [HELD]

def test_a_booking_under_re_review_blocks():
    assert safety_readiness([B(status="re_review")], T.ready).missing == [RE_REVIEW]

def test_one_approved_and_one_held_booking_blocks():  # Review Focus 1, CR-97
    assert safety_readiness([B(status="approved"), B(status="held")], T.ready).missing == [HELD]

def test_each_distinct_flag_blocks_once_in_a_fixed_order():  # AC10, AC9 expired
    result = safety_readiness(
        [B(status="approved", flags=["unsuitable", "affected"]), B(status="approved", flags=["affected", "expired"])],
        T.ready,
    )
    assert result.missing == [
        "A venue booking is flagged Affected.",
        "A venue booking is flagged Unsuitable.",
        "A venue booking is flagged Expired.",
    ]

def test_an_unknown_flag_is_ignored():
    assert safety_readiness([B(status="approved", flags=["something_new"])], T.ready).ready is True

@pytest.mark.parametrize("technical", [T.pending, T.issue])
def test_technical_status_other_than_ready_or_not_required_blocks(technical):  # AC1, AC2
    assert safety_readiness([B(status="approved")], technical).missing == [TECH]

def test_every_missing_item_is_listed_in_order():
    result = safety_readiness([B(status="re_review"), B(status="held")], T.issue)
    assert result.missing == [HELD, RE_REVIEW, TECH]
    assert result.ready is False
```

- [ ] **Step 2: Run, confirm it fails on the missing module or models**

Run: `cd backend && .venv/bin/python -m pytest tests/test_safety_readiness.py -v`
Expected: FAIL with `ModuleNotFoundError: app.modules.events.readiness` or `ImportError` for `BookingReadiness`.

- [ ] **Step 3: Implement** the two models and `readiness.py` to the interface above. Module docstring cites REQUIREMENTS §6.6 and SCRUM-82 AC1, AC2, AC9, AC10.

- [ ] **Step 4: Run, confirm it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_safety_readiness.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/events/readiness.py backend/app/modules/events/schemas.py backend/tests/test_safety_readiness.py
git commit -m "feat(events): add the safety check readiness rule (SCRUM-82)" -m "One pure rule shared by the event read and the send, so story 24 and the booking-flag stories each change one place."
```

---

### Task 2: Technical status seam and backend status lists

**Files:**
- Modify: `backend/app/modules/events/service.py` (`ACTIVE_COORDINATOR_STATUSES`, `_action_kind`, new `technical_status`, `coordinator_dashboard`)
- Modify: `backend/app/modules/events/schemas.py` (`COMMENTABLE_STATUSES`)
- Modify: `backend/app/modules/equipment/service.py` (`QUEUE_EVENT_STATUSES`)
- Test: `backend/tests/test_coordinator_dashboard.py`, `backend/tests/test_event_comments_api.py`, `backend/tests/test_equipment_requests_api.py` (add cases), `backend/tests/test_technical_status.py` (new, small)

**Interfaces:**
- Produces: `events.service.technical_status(row: dict) -> ReadinessState`, returning `ReadinessState(row["technical_readiness"])`. Docstring: it is the single reader of an event's technical status, and SCRUM-24 replaces its body with the status derived from equipment lines (spec §9). Task 4 and Task 5 call it.

**Requirements:**
- `ACTIVE_COORDINATOR_STATUSES = ("under_review", "returned", "planning", "safety_review", "confirmed")`. Keep it a tuple, and keep this order: the dashboard sorts by it.
- `_action_kind`: `arrangement_issue` for `planning`, `safety_review` or `confirmed` when the technical status is `issue`.
- `coordinator_dashboard` reads the technical status only through `technical_status(row)`. No other `row["technical_readiness"]` reads remain in `events/service.py` (grep must show only the one inside `technical_status`).
- `COMMENTABLE_STATUSES` gains `EventStatus.safety_review`. The SQL side changes in Task 3; the comment there says they're mirrored.
- `equipment.service.QUEUE_EVENT_STATUSES = ("planning", "safety_review", "confirmed")`.
- Leave equipment request submission and venue booking request rules Planning-only (spec §7).

- [ ] **Step 1: Write the failing tests** (add to the existing files, using their fixtures):
  - `test_coordinator_dashboard.py`:
    - a `safety_review` event assigned to the caller appears in `active_events` with `status == "safety_review"`
    - `list_coordinator_events` is called with a status tuple containing `"safety_review"`
    - a `safety_review` event with `technical_readiness == "issue"` yields one `arrangement_issue` item.
  - `test_technical_status.py`: `technical_status({"technical_readiness": v}) == ReadinessState(v)` for all four values.
  - `test_event_comments_api.py`: the owner and the assigned coordinator can `POST /events/{id}/comments` on a `safety_review` event (201).
  - `test_equipment_requests_api.py`: `GET /equipment/requests/pending` includes a pending line whose event is `safety_review`.
  - Keep an existing case: a `POST /equipment/requests` on a `safety_review` event is still 409.

- [ ] **Step 2: Run, confirm the new cases fail for the expected reason**

Run: `cd backend && .venv/bin/python -m pytest tests/test_coordinator_dashboard.py tests/test_technical_status.py tests/test_event_comments_api.py tests/test_equipment_requests_api.py -v`
Expected: the new cases FAIL (event missing from dashboard, 409 "Comments are closed for a safety review event.", line missing from queue, `ImportError` for `technical_status`).

- [ ] **Step 3: Implement** the list changes and `technical_status`.

- [ ] **Step 4: Run the four files, then the full backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit** (`feat(events): include safety_review in the coordinator, comment and equipment queue lists (SCRUM-82)`, body with the why).

---

### Task 3: Migration — the wrapper RPC and the comment status list

**Files:**
- Create: `supabase/migrations/<YYYYMMDDHHMMSS>_send_event_to_safety_review.sql` (timestamp now; must sort after `20261008150000`)
- Create: `supabase/verification/send_for_safety_check.sql`
- Modify: `backend/scripts/verify_live.py` (register the script in the SQL script list, next to `event_amendment_checks.sql`)

**Interfaces:**
- Produces: `public.send_event_to_safety_review(p_event_id uuid, p_actor_id uuid, p_from_statuses text[], p_to_status text, p_expected_version integer, p_organiser_message text, p_officer_message text) returns setof public.events`. Task 4's repository calls it with exactly these parameter names.

**Requirements:**
- **RPC shape:** model it on `return_event_for_amendment` in `20260924140000_event_amendment_requests.sql`.
  - Use the same `language plpgsql security definer set search_path = ''`.
  - Copy the same grant and revoke statements that file applies to its functions (API-only: no `anon` or `authenticated` execute).
  - Add a `comment on function`.
- **RPC body:**
  - `select * into v_after from public.transition_event(p_event_id, p_actor_id, p_from_statuses, p_to_status, p_expected_version, null, 'event_sent_for_safety_check', p_organiser_message);`
  - `if not found then return; end if;`
  - Insert into `public.notifications (recipient_id, event_id, type, message)` one row per `user_roles.profile_id` with `role = 'safety_officer'` and `profile_id <> p_actor_id`, using `p_officer_message`. Copy the comment block from `request_venue_booking` about held roles vs the active role.
  - `return next v_after;`
- **`public.add_event_comment`:** `create or replace` it with the open-status list `('submitted', 'under_review', 'returned', 'planning', 'safety_review', 'confirmed')`. Copy the current definition from the **live** database, not only the migration file:

  ```bash
  env PATH=/home/linuxbrew/.linuxbrew/bin:/usr/bin:/bin supabase db query --linked "select pg_get_functiondef('public.add_event_comment(uuid,uuid,text,text)'::regprocedure);"
  ```

  Change only the status list. Keep its grants. Note in a comment that it mirrors `COMMENTABLE_STATUSES` (backend) and `comments.js` (frontend).
- **`supabase/verification/send_for_safety_check.sql`:** model it on `event_amendment_checks.sql`.
  - It runs in one transaction and ends with `rollback`.
  - Each check raises with its case ID on failure.
  - It inserts its own throwaway rows inside the transaction and never relies on fixture state.
  - Cases:
    - **TC-SAFE-010:** a `planning` event sent with the right version becomes `safety_review`, `version` + 1, and exactly one `event_status_history` row `planning → safety_review` with `actor_id` = the coordinator (AC1, AC7).
    - **TC-SAFE-011:** notifications. One `event_sent_for_safety_check` row to the organiser with the organiser message, one to each `safety_officer` holder with the officer message, none to the actor. Make the actor also hold `safety_officer` inside the transaction (Review Focus 4).
    - **TC-SAFE-012:** with every `safety_officer` row deleted inside the transaction, the send still returns the event and the organiser is still notified (Review Focus 5).
    - **TC-SAFE-013:** a stale `p_expected_version` and a non-`planning` status each return no row and change nothing (no status, history or notification change).
    - **TC-SAFE-014:** `add_event_comment` on a `safety_review` event returns a row.
    - **TC-SAFE-015:** as roles `anon` and `authenticated`, executing `send_event_to_safety_review` is denied.

- [ ] **Step 1: Write the verification script first.** Run it against the live project before the migration exists to see it fail:

Run: `cd /home/jclim/projects/ConnectSphere && env PATH=/home/linuxbrew/.linuxbrew/bin:/usr/bin:/bin supabase db query --linked -f supabase/verification/send_for_safety_check.sql`
Expected: FAIL, because `function public.send_event_to_safety_review(...) does not exist`. It rolls back, so no data changes.

- [ ] **Step 2: Write the migration.** Show the dry run:

Run: `env PATH=/home/linuxbrew/.linuxbrew/bin:/usr/bin:/bin supabase db push --dry-run`
Expected: only the new migration listed.

- [ ] **Step 3: STOP. Ask the developer to run `supabase db push`.** Don't run it yourself. Continue with Task 4 (mocked tests don't need the database) and come back here once they confirm.

- [ ] **Step 4: After the push, verify.**
  - `supabase migration list --linked` shows the new migration remote.
  - The verification script passes (same command as Step 1, every case reports OK).
  - The Supabase security and performance advisors show nothing new for these functions: `supabase db advisors --linked`, or the Supabase MCP `get_advisors` if available.

- [ ] **Step 5: Commit** the migration, the script and the `verify_live.py` registration (`feat(db): add send_event_to_safety_review and open comments in safety review (SCRUM-82)`).

---

### Task 4: Send endpoint (repository, service, router)

**Files:**
- Modify: `backend/app/modules/events/repository.py`, `service.py`, `router.py`
- Test: `backend/tests/test_send_for_safety_check.py` (new), `backend/tests/test_events_repository.py` (add)

**Interfaces:**
- Consumes: `readiness.safety_readiness`, `schemas.BookingReadiness`, `service.technical_status`, `venues_service.booking_statuses_by_event(event_ids) -> dict[str, list[str]]`, the RPC from Task 3.
- Produces:
  - `repository.send_to_safety_review(event_id: str, actor_id: str, from_statuses: list[str], to_status: str, expected_version: int, *, organiser_message: str, officer_message: str) -> dict | None`. It calls `.rpc("send_event_to_safety_review", {...})` with the Task 3 parameter names and returns the first row or `None`, like `return_event`.
  - `service.send_for_safety_check(event_id: str, coordinator_id: str) -> EventResponse`.
  - `service._safety_readiness_for(row: dict) -> SafetyReadiness`. It builds `BookingReadiness(status=s)` for each status from `booking_statuses_by_event([row["id"]]).get(row["id"], [])`, then calls `safety_readiness(bookings, technical_status(row))`. Task 5 reuses it.
  - Route: `POST /api/v1/events/{event_id}/send-for-safety-check`. No body. 200 `EventResponse`. Guard `EventCoordinator`.

**Requirements:** the service checks, in this order:
1. `_assigned_event`: 404 missing or draft, 403 not assigned.
2. `lifecycle.target("send_to_safety", row["status"])`: 409 wrong status.
3. `_safety_readiness_for(row)`: if not ready, `EventConflictError("Not ready for safety check: " + " ".join(missing))`. The RPC is not called.
4. The repository call with `lifecycle.allowed_from("send_to_safety")`, `"safety_review"`, `row["version"]` and both messages from Global Constraints. `None` means `EventConflictError(STALE_EVENT_MESSAGE)`.

The response is `_to_response(updated)`. The router function is plain `def` and declared next to `/approve`.

- [ ] **Step 1: Write the failing tests.** Reuse the `events` fixture pattern from `tests/test_event_review_api.py`:
  - Patch `repository.get_event`.
  - Patch `repository.send_to_safety_review` with a fake that enforces `status in from_statuses` and version, and records calls.
  - Patch `venues_repository.list_booking_statuses` to return booking rows you control.

```python
"""SCRUM-82: POST /events/{id}/send-for-safety-check, with the repository mocked."""

def send(client, auth_headers, event_id=EVENT_ID):
    return client.post(f"/api/v1/events/{event_id}/send-for-safety-check", headers=auth_headers)

class TestSend:
    def test_a_ready_planning_event_goes_to_safety_review(...):  # AC1
        # store: planning, version 3, technical not_required; bookings: [approved]
        # 200, json status == "safety_review"; one call with from_statuses ["planning"],
        # to_status "safety_review", expected_version 3, organiser_message and officer_message
        # exactly as in Global Constraints (event name "Partner Summit").

    def test_not_ready_is_a_conflict_naming_what_is_missing_and_sends_nothing(...):  # AC2
        # bookings [held], technical "pending" ->
        # 409, detail == "Not ready for safety check: A venue booking is awaiting venue staff approval. Technical status is not Ready."
        # no RPC call

    def test_no_booking_is_a_conflict(...):  # [Assumption]
        # bookings [] -> 409 "Not ready for safety check: No venue booking is approved."

    @pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s not in ("planning", "draft")])
    def test_only_planning_can_be_sent(..., status):  # AC5
        # 409 detail == f"Cannot send to safety an event that is {status.replace('_', ' ')}"; no RPC call
        # ALL_STATUSES must include "safety_review"

    def test_a_draft_is_not_found(...):  # DR-R2
    def test_an_unknown_event_is_not_found(...):
    def test_an_unassigned_coordinator_is_forbidden(...):  # AC5, 403, no RPC call

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee",
                                      "event_coordinator_lead", "safety_officer"])
    def test_other_roles_are_forbidden(..., role):  # AC5, 403

    def test_a_coordinator_acting_as_another_role_is_forbidden(...):  # SCRUM-76
        # copy test_a_coordinator_acting_as_venue_staff_is_forbidden: profile role event_coordinator,
        # session_active_role "safety_officer" -> 403, no RPC call

    def test_a_lost_race_is_a_conflict(...):
        # fake returns None -> 409 "This event was updated by someone else. Reload."

    def test_sending_twice_succeeds_once(...):  # Review Focus 3
        # two sequential POSTs on the same store: first 200, second 409
        # "Cannot send to safety an event that is safety review"; exactly one successful RPC call
```

  Add to `test_events_repository.py`, using the `RpcClient` pattern: `send_to_safety_review` calls `send_event_to_safety_review` with every parameter (`p_event_id`, `p_actor_id`, `p_from_statuses`, `p_to_status`, `p_expected_version`, `p_organiser_message`, `p_officer_message`), and an empty result comes back as `None`.

- [ ] **Step 2: Run, confirm failures are 404/405 for the missing route and AttributeError for the repository function.**

Run: `cd backend && .venv/bin/python -m pytest tests/test_send_for_safety_check.py tests/test_events_repository.py -v`

- [ ] **Step 3: Implement** the repository function, the service function and helper, and the route.

- [ ] **Step 4: Run the two files, then the full suite** (`.venv/bin/python -m pytest -q`). The route matrix test `test_every_protected_endpoint_names_the_roles_it_allows` must still pass.

- [ ] **Step 5: Commit** (`feat(events): send a ready event for its safety check (SCRUM-82)`).

---

### Task 5: Readiness and arrangements on the event read

**Files:**
- Modify: `backend/app/modules/events/schemas.py` (`EventResponse`), `service.py` (`read`)
- Test: `backend/tests/test_send_for_safety_check.py` (add a `TestRead` class)

**Interfaces:**
- Consumes: `service._safety_readiness_for(row)` (Task 4), `venues_service.active_booking_for_event(event_id)`.
- Produces: `EventResponse.safety_readiness: SafetyReadiness | None = None`. The frontend (Task 6) reads `event.safety_readiness.ready` and `event.safety_readiness.missing`.

**Requirements:**
- In `read`:
  - When the role is `event_coordinator` and the status is `planning`, set `response.safety_readiness = _safety_readiness_for(row)`. For any other status or role it stays `None`, and the bookings query must not run.
  - When the role is `event_organiser` and the status is `confirmed`, set `response.venue_booking` from `active_booking_for_event` (AC8). The organiser gets no `venue_booking` on any other status.
  - Coordinators keep getting `venue_booking` on every status, as today.

- [ ] **Step 1: Write the failing tests:**
  - The coordinator reading a `planning` event with bookings `[held]` gets `safety_readiness == {"ready": False, "missing": ["A venue booking is awaiting venue staff approval."]}`.
  - The same event with `[approved]` gets `{"ready": True, "missing": []}`.
  - The coordinator on `under_review` gets `safety_readiness is None`, and the booking-status fake is not called.
  - The organiser on `planning` gets `safety_readiness is None` and `venue_booking is None`.
  - The organiser on `confirmed` gets `venue_booking` with `venue_name` and `status`.

- [ ] **Step 2: Run, confirm they fail** (`KeyError`/`None` mismatches).

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Full backend suite with coverage:** `cd backend && .venv/bin/python -m pytest --cov -q`. Expected: PASS, above the floor.

- [ ] **Step 5: Commit** (`feat(events): show safety check readiness and confirmed arrangements on the event read (SCRUM-82)`).

---

### Task 6: Coordinator page — send for safety check

**Files:**
- Modify: `frontend/src/services/api.js`, `frontend/src/features/events/eventReviewStore.js`, `frontend/src/views/events/CoordinatorEventView.vue`
- Test: `frontend/src/features/events/__tests__/eventReviewStore.spec.js`, `frontend/src/views/__tests__/CoordinatorEventView.spec.js`

**Interfaces:**
- Consumes: `POST /events/{id}/send-for-safety-check`. `EventResponse.safety_readiness` is `{ready, missing}` or `null`.
- Produces:
  - `eventsApi.sendForSafetyCheck(eventId, token)`.
  - `canSendForSafetyCheck(event)`: true only when `event?.status === "planning"` and `event.safety_readiness?.ready === true`.
  - Store action `sendForSafetyCheck()`.

**Requirements:**
- **The store action** goes through `act()`, so history refreshes (AC7).
- **On failure,** it keeps `this.error`, then **reloads the event** with `load(this.event.id)` so a stale page updates its button and list (Review Focus 2). It still rethrows, so the view keeps its toast logic.
- **The button:**
  - It shows whenever `event.status === "planning"`, in the header action row alongside Reject.
  - It's disabled when `!canSendForSafetyCheck(event)` or `review.isActing`.
  - When disabled because not ready, a list headed `Not ready for safety check` shows each `missing` item, with `aria-describedby` from the button to the list's id.
- **Ready path:** clicking opens `ConfirmModal` with the strings in Global Constraints. Confirming calls the store, shows the toast `Sent for safety check`, and the badge shows `Safety review`.
- **Errors** show in the page's existing alert.
- **The `For information` block** is visible on `planning` events. It shows registration enabled or not, capacity, opens and closes (formatted with the existing `displayDateTime` helper and the event timezone). It never changes the button.
- **No coordinator action buttons on `safety_review`.**

- [ ] **Step 1: Write the failing tests:**
  - Store:
    - the `canSendForSafetyCheck` truth table (planning+ready, planning+not ready, planning+null, safety_review+ready)
    - `sendForSafetyCheck` calls `eventsApi.sendForSafetyCheck("event-1", token)`, sets `event` and refreshes history
    - on rejection it sets `error`, calls `eventsApi.get` again and rethrows.
  - View (add `sendForSafetyCheck: vi.fn()` to the mocked `eventsApi`):
    - **Planning, not ready** (`{ready:false, missing:["A venue booking is awaiting venue staff approval.","Technical status is not Ready."]}`): the button is disabled; both items are visible under `Not ready for safety check`; the button's `aria-describedby` matches the list's id.
    - **Planning, ready:** click opens the modal with the exact title and message; Send calls the API once; the toast text appears; the badge reads `Safety review`; the send button is gone.
    - **API rejects with 409:** the error text is shown and `eventsApi.get` is called a second time.
    - **`under_review` and `safety_review`:** no send button.
    - **The For information block:** with `registration_enabled: true, registration_capacity: 80` it shows `80`; with `false` it shows `Not enabled`.

- [ ] **Step 2: Run, confirm they fail.**

Run: `cd frontend && npx vitest run src/features/events/__tests__/eventReviewStore.spec.js src/views/__tests__/CoordinatorEventView.spec.js`

- [ ] **Step 3: Implement.** Follow `frontend/AGENTS.md` and the existing view's components (`BauhausButton`, `ConfirmModal`, `BauhausCard`).

- [ ] **Step 4: Run the two files, then `npm run test:coverage`.** Expected: PASS above the floor.

- [ ] **Step 5: Commit** (`feat(events): send for safety check from the coordinator's event page (SCRUM-82)`).

---

### Task 7: Frontend status lists and the organiser's view

**Files:**
- Modify: `frontend/src/features/events/dashboard.js` (`ACTIVE_COORDINATOR_STATUSES`, `readinessGaps`), `frontend/src/features/events/comments.js` (`COMMENTABLE_STATUSES`), `frontend/src/features/events/organiserDashboard.js` (`summariseOrganiserEvents`, `groupOrganiserActiveEvents`), `frontend/src/views/events/EventDetailView.vue`
- Test: `frontend/src/features/events/__tests__/dashboard.spec.js`, `comments.spec.js`, `organiserDashboard.spec.js`, `frontend/src/views/__tests__/EventDetailView.spec.js`

**Requirements:**
- **Coordinator dashboard lists:**
  - `ACTIVE_COORDINATOR_STATUSES = ["under_review", "returned", "planning", "safety_review", "confirmed"]`, the same order as the backend.
  - `readinessGaps` includes `safety_review` events.
- **`COMMENTABLE_STATUSES`** gains `"safety_review"`.
- **Organiser dashboard:**
  - `summariseOrganiserEvents` returns `myEvents.safetyReview`, included in `myEvents.total`.
  - `groupOrganiserActiveEvents` gets a `safety_review` group between `planning` and `confirmed`: label `STATUS_LABELS.safety_review`, description `Events being checked by the Safety Officer.`.
  - Check `OrganiserDashboard.vue` renders the new count wherever the others are rendered. If it lists the counts explicitly, add Safety review there and cover it in `src/views/__tests__/OrganiserDashboard.spec.js`.
- **`EventDetailView` (organiser):**
  - On `confirmed`, an `Arrangements` card shows the venue name (from `venue_booking.venue_name`), its booking status via `BOOKING_STATUS_LABELS`, and the technical status as plain words: `ready` → `Ready`, `not_required` → `Not required`, `pending` → `Pending`, `issue` → `Issue`.
  - No card on any other status.
  - No preparation notes.
  - On `safety_review` the page shows the organiser-facing status description used in the dashboard group.

- [ ] **Step 1: Write the failing tests** for each list change, the organiser count and group, and the card's presence on `confirmed` and absence on `planning` and `safety_review`.
- [ ] **Step 2: Run, confirm they fail.** `cd frontend && npx vitest run src/features/events src/views/__tests__/EventDetailView.spec.js src/views/__tests__/OrganiserDashboard.spec.js`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: `npm run test:coverage`, then `npm run build`** (with `.env` present). Expected: PASS.
- [ ] **Step 5: Commit** (`feat(events): show safety review on dashboards and confirmed arrangements to the organiser (SCRUM-82)`).

---

### Task 8: Live checks, e2e and manual test cases

**Files:**
- Modify: `backend/scripts/verify_live.py`
- Create: `frontend/e2e/safety-check.e2e.js`
- Modify: `docs/test-cases/events.md` (new section `## Send for safety check (SCRUM-82)`), `docs/test-cases/README.md` if it indexes prefixes

**Requirements:**
- **`verify_live.py`**, using the existing `@check` pattern. These checks never change data.
  - **TC-SAFE-001:** as organiser, venue staff and tech support, `POST /events/e0000000-0000-4000-8000-000000000202/send-for-safety-check` → 403 each.
  - **TC-SAFE-002:** as the seeded coordinator (assigned to `…0202`, which is `planning` with booking `d0000000-…-0201` `held`) → 409 whose detail contains `A venue booking is awaiting venue staff approval.`. Skip with a clear message if the fixture has drifted (status not `planning`), and point at `supabase/verification/event_review_fixture_reset.sql`.
  - **TC-SAFE-003:** as the coordinator, `GET /events/…0202` has `safety_readiness.ready == false` and the same missing item.
- **`frontend/e2e/safety-check.e2e.js`** (Playwright, existing `support/` helpers, logs out its session):
  - **TC-SAFE-004:** the coordinator opens `/coordinator/events/e0000000-0000-4000-8000-000000000202`. `Send for safety check` is disabled, and `Not ready for safety check` lists the held-booking item. No click on anything that changes data.
- **Manual cases** in `docs/test-cases/events.md`, following the existing table columns (ID, story/AC, precondition, steps, data, expected, priority, plus the Type, Created and Last run columns per `docs/test-cases/README.md`):
  - TC-SAFE-001 to 004: the automated ones above, Type automated.
  - TC-SAFE-010 to 015: the SQL script cases from Task 3.
  - **TC-SAFE-020:** the happy path in the browser (manual, changes shared data: needs an approved booking, so set one up on a throwaway event and say how to reset).
  - **TC-SAFE-021:** history shows the entry with the actor, for coordinator and organiser (AC7).
  - **TC-SAFE-022:** modal wording and toast.
  - **TC-SAFE-023:** phone-width layout of the button, list and For information block.
  - **TC-SAFE-024:** the organiser's Arrangements card on a seeded or temporarily confirmed event (AC8).
  - **TC-SAFE-025:** the coordinator and organiser dashboards show a Safety review group.
  - **TC-SAFE-026:** no coordinator action can confirm an event (AC5, AC6).
- Every AC1–AC10 is traced to at least one case. AC3, AC9 `expired` and AC10 note that end-to-end checks wait for 24, CR-99 and CR-94/95.

- [ ] **Step 1: Write the checks and the e2e spec.**
- [ ] **Step 2: Run them against servers on this branch with recording on.** If the developer's servers use 8000/5173, use spare ports and pass `--api` / `E2E_BASE_URL` / `E2E_API_URL`.
  - First ask the developer before running the fixture reset (`event_review_fixture_reset.sql`, per the environment memory) if `…0202` has drifted.
  - `cd backend && .venv/bin/python scripts/verify_live.py --record`
  - `cd frontend && npm run test:e2e:record`

  Expected: all pass. A failure is a finding to report, never something to re-run until it passes.
- [ ] **Step 3: Commit** the checks, the spec, the test cases and the run logs in `docs/test-cases/runs/`.

---

### Task 9: Paper trail, full verification, handback

**Files:**
- Modify: `docs/IMPLEMENTATION_MAP.md`, `docs/BUILD_LOG.md`, `docs/REQUIREMENTS.md`

**Requirements:**
- **`docs/IMPLEMENTATION_MAP.md`:**
  - **Status table:** a row for 82.
  - **Endpoints table:** `POST /events/{event_id}/send-for-safety-check`, with every status code and message, and `safety_readiness` on the coordinator's `GET /events/{id}` plus the organiser's `venue_booking` on `confirmed`.
  - **Reuse tables:** `events/readiness.py`, `service.technical_status` (the 24 seam), `public.send_event_to_safety_review`, and the new notification type.
  - **§5 "Know before you build":**
    - Replace the "`safety_review` is a status, but most status lists don't include it yet" note with what each list now does.
    - Add the check-then-act race note (spec §5; recovery is CR-104 AC10).
    - Add that `safety_review` is not yet a cancellation source (for 84).
    - Add that the flag seam expects `affected`, `conflict`, `unsuitable`, `expired`.
    - Add that `technical_readiness` is unwritten until 24.
    - Add `event_sent_for_safety_check` to the notification types list.
  - **"Last updated":** replace the line with this change.
- **`docs/BUILD_LOG.md` §4:** append an 82 entry using the existing template. Never edit past entries.
- **`docs/REQUIREMENTS.md`:**
  - **§5 transition table, `planning → safety_review` row:** notify the organiser and Safety Officers, the organiser part as **[Team decision]** with the reason from the spec.
  - **§5 status paragraph:** replace "no endpoint uses them yet" for `send_to_safety`.
  - **§6.6:** readiness table (venue rule, technical status through `technical_status`, programme from story 89); RD-R1 reworded from "Confirm" to "Send for safety check"; the two acceptance criteria about confirming reworded for sending (the confirmation one now belongs to CR-104).
  - **§9:** new items: the no-booking **[Assumption]**, and the technical-status gap until 24.
- **Full verification:**
  - `cd backend && .venv/bin/python -m pytest --cov -q`
  - `cd frontend && npm run test:coverage && npm run build`

  Both green. Report the counts (the previous baseline was pytest 699, vitest 585).
- **Commit** (`docs(events): record send for safety check in the map, log and requirements (SCRUM-82)`).
- **Then STOP and hand back.** Don't push, open a PR, edit the backlog sheet or change any status. Report:
  - **What changed**, per task, with commits.
  - **How it was verified:** test counts, coverage, live run log paths.
  - **What wasn't verified:** the manual cases TC-SAFE-020 to 026 await the developer's browser pass; AC3, AC9 `expired` and AC10 can't be shown end to end until 24, CR-99 and CR-94/95 land; AC6 is CR-104's.
  - **Follow-ups:** send spec §9 to Eileen; flag `safety_review` as a cancellation source for 84; suggest moving 82 to In Progress in the backlog sheet.
