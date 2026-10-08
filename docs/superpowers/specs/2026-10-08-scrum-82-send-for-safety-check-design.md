# SCRUM-82 — Send event for safety check once essential arrangements are approved: design

_Date: 2026-10-08 · Branch: `feature/scrum-82-send-for-safety-check` · Epic: Event status management · Sprint 3 · Priority 3 · 3 SP_

## 1. Story and acceptance criteria (Product backlog sheet, row 82, read 8 Oct)

> As an Event Coordinator, I want to send an event for its Operational Safety Check once its venue and technical arrangements are approved, so that the Safety Officer can review it and, on approval, the event is confirmed and attendees can register.

- **AC1** [W7 CR-06] Given an event in Planning that is assigned to me, where every active venue booking is approved and the event's technical status is Ready or Not required (24), when I select Send for safety check, then its status becomes Safety review and Safety Officers are notified.
- **AC2** If any of those items is not ready, Send for safety check is unavailable and a direct request is blocked, naming what is missing (for example "Technical status is not Ready"). There is no override (QA-17, QA-49, QA-106, QA-118).
- **AC3** An event with no equipment lines has technical status Not required (24 AC11), so it is not blocked by the technical check (QA2-12).
- **AC4** The programme and registration setup are shown for information but don't block sending for safety check (QA-17, QA-133).
- **AC5** [W7 CR-06] Send for safety check is available only from Planning, and only to the assigned coordinator acting as coordinator. Every other status or caller is blocked. The coordinator can no longer confirm an event directly.
- **AC6** [W7 CR-06] Confirmed is reached only through Safety Officer approval (CR-104), which notifies the organiser, venue staff and technical support (W1 §6).
- **AC7** Sending for safety check, who did it, and when are recorded in the event history (QA-70).
- **AC8** The organiser can see the confirmed arrangements once the event is Confirmed (W1 Step 10).
- **AC9** [W7 CR-03, CR-04] Every active venue booking on the event must be approved. An expired hold never counts as approved.
- **AC10** [W7 CR-01, CR-02] A venue booking flagged Affected (venue unavailable, CR-95), Conflict or Unsuitable (after a venue change, CR-94) counts as not ready.

The criteria match `docs/proposals/week7-customer-changes.md` §3 word for word.

**Already built (groundwork, commits `649f569`, `a045864`):** `safety_review` in `public.event_status` (migration `20261008150000`, applied live 2026-10-08), `EventStatus.safety_review`, the five rows in `events/lifecycle.py` `TRANSITIONS` (`send_to_safety`, `safety_approve`, `safety_request_changes`, `safety_reject`, `safety_withdraw`), the "Safety review" label and description in `features/events/dashboard.js`, REQUIREMENTS §5 and §9 item 22.

## 2. Decisions

| Decision | Choice | Label |
|---|---|---|
| Technical status until 24 lands | Read `events.technical_readiness` as it is, through one function (`events.service.technical_status`). Nothing writes the column today and it defaults to `not_required`, so the technical check passes for every event until 24 derives the status from equipment lines. The function's contract is agreed with Eileen (§9). | [Team decision] |
| An event with no active venue booking | Not ready: "No venue booking is approved." At least one active booking is required, and every active booking must be `approved`. | [Assumption], REQUIREMENTS §9 |
| Where the readiness check runs | In Python, in a pure module both the read and the send use; then a wrapper RPC does the transition and notifications atomically. The check-then-act race is accepted and recorded (§5). | [Team decision] |
| How the page learns what is missing | `safety_readiness` on the coordinator's `GET /events/{id}`, computed by the same function as the send | [Team decision] |
| Notify the organiser | Yes, as well as Safety Officers. Every other coordinator transition notifies the organiser (approve, reject, return), and W1 §2 names organisers not knowing where their event stands. | [Team decision], REQUIREMENTS §5 |
| Safety Officers notified | Every account holding `safety_officer` in `user_roles`, except the actor (NT-R1). Held roles, not the active one: a notification grants no access (the `venue_booking_requested` pattern). | follows SCRUM-19 |
| Programme in AC4 | There is no programme data. Programmes arrive as attachments with story 89 (non-core, no sprint). 82 shows the registration setup only. | dependency on 89 |
| Booking flags (AC9, AC10) | No flag columns exist yet. The rule takes a `flags` list per booking that is always empty today; CR-94, CR-95 and CR-99 fill it using the agreed names `affected`, `conflict`, `unsuitable`, `expired`. | dependency on Xuan Wei's stories |
| `safety_review` as a cancellation source | Not built. Flagged for 84. | out of scope |

## 3. Approach

1. A pure rule, `events/readiness.py`, takes the event's booking statuses (with flags) and its technical status and returns `{ready, missing}`.
2. `events.service.send_for_safety_check` checks the caller, the status, then readiness, and calls `public.send_event_to_safety_review`.
3. That RPC calls `public.transition_event` (status, optimistic-concurrency check, history row with actor and time, organiser notification), then notifies every Safety Officer, in one transaction (NT-R3).
4. The coordinator's event read carries the same readiness result, so the page disables the button and lists what's missing.

Rejected alternatives: re-checking readiness inside the RPC under row locks (two copies of the rules, so 24 and the flag stories would each change both); doing it all in SQL like `request_venue_booking` (24's derived status would have to be SQL, and the rules couldn't be unit-tested in CI, which has no database).

## 4. Database

New migration `supabase/migrations/<YYYYMMDDHHMMSS>_send_event_to_safety_review.sql`, timestamped when it is created (it must sort after `20261008150000`):

- **`public.send_event_to_safety_review(p_event_id uuid, p_actor_id uuid, p_from_statuses text[], p_to_status text, p_expected_version integer, p_organiser_message text, p_officer_message text) returns setof public.events`**
  - `language plpgsql security definer set search_path = ''`, the same grants as `return_event_for_amendment` (API-only).
  - Calls `public.transition_event(p_event_id, p_actor_id, p_from_statuses, p_to_status, p_expected_version, null, 'event_sent_for_safety_check', p_organiser_message)`. If that returns no row (wrong status or stale version), returns nothing.
  - Otherwise inserts one `notifications` row of type `event_sent_for_safety_check` with `p_officer_message` for each `user_roles.profile_id` where `role = 'safety_officer'` and `profile_id <> p_actor_id`, then returns the updated event.
- **`public.add_event_comment`:** its open-status list gains `safety_review` (it must stay in step with `COMMENTABLE_STATUSES`).

No new table. The history row comes from `transition_event`.

Applying it: `supabase db push --dry-run` is shown to the developer, who runs the push. Afterwards `supabase migration list --linked` and the Supabase advisors are checked.

## 5. Backend (`backend/app/modules/events/`)

**`readiness.py` (new, pure, no I/O)**

- `ACTIVE_BOOKING_STATUSES = {"held", "approved", "re_review"}`.
- `safety_readiness(bookings: list[BookingReadiness], technical: ReadinessState) -> SafetyReadiness`, where `BookingReadiness` is `{status: str, flags: list[str] = []}` and `SafetyReadiness` is `{ready: bool, missing: list[str]}`.
- Rules, each adding at most one message, in this order:

| Condition | Message |
|---|---|
| No active booking | "No venue booking is approved." |
| Any active booking `held` | "A venue booking is awaiting venue staff approval." |
| Any active booking `re_review` | "A venue booking is under re-review." |
| Any active booking with a flag | "A venue booking is flagged <Affected / Conflict / Unsuitable / Expired>." (one message per distinct flag) |
| Technical status is neither `ready` nor `not_required` | "Technical status is not Ready." |

- `ready` is `not missing`. Registration and programme are never inputs (AC4).

**`service.py`**

- `technical_status(row: dict) -> ReadinessState` returns `ReadinessState(row["technical_readiness"])`. It is the only reader of technical readiness: `coordinator_dashboard` switches to it too. 24 replaces its body.
- `send_for_safety_check(event_id: str, coordinator_id: str) -> EventResponse`, in order:
  1. `_assigned_event` → 404 missing or draft, 403 not the assigned coordinator.
  2. `lifecycle.target("send_to_safety", row["status"])` → 409 "Cannot send to safety an event that is <status>".
  3. Bookings from `venues_service.booking_statuses_by_event([event_id])` (every status; the rule filters), technical from `technical_status(row)`. If not ready → `EventConflictError("Not ready for safety check: " + " ".join(missing))`.
  4. `repository.send_to_safety_review(...)` with both messages. No row → `EventConflictError(STALE_EVENT_MESSAGE)`.
  - Organiser message: `Your event "<name>" is with the Safety Officer for its operational safety check.`
  - Officer message: `"<name>" is ready for its operational safety check.`
- `read(...)`: for `event_coordinator` on a `planning` event, sets `response.safety_readiness`; `null` otherwise. For `event_organiser` on a `confirmed` event, sets `response.venue_booking` (AC8); coordinators keep getting it on every status as today.
- Status lists (§7).

**`schemas.py`:** `SafetyReadiness`, `BookingReadiness`; `EventResponse.safety_readiness: SafetyReadiness | None = None`; `COMMENTABLE_STATUSES` gains `safety_review`.

**`repository.py`:** `send_to_safety_review(event_id, actor_id, from_statuses, to_status, expected_version, organiser_message, officer_message) -> dict | None` through `.rpc("send_event_to_safety_review", ...)`, same shape as `return_event`.

**`router.py`:** `POST /events/{event_id}/send-for-safety-check`, guard `EventCoordinator` (`require_roles(["event_coordinator"])`, the active role), no body, returns `EventResponse`. Plain `def`.

**Known race (recorded in IMPLEMENTATION_MAP §5):** booking and equipment decisions don't bump `events.version`, so a booking can stop being approved between the readiness check and the RPC. The window is milliseconds; the designed recovery is CR-104 AC10 (`safety_withdraw`, back to Planning when an arrangement stops being ready during review).

## 6. Frontend (`frontend/src/`)

- **`services/api.js`:** `eventsApi.sendForSafetyCheck(eventId, token)` → `POST /events/{id}/send-for-safety-check`.
- **`features/events/eventReviewStore.js`:** `canSendForSafetyCheck(event)` (status `planning` and `event.safety_readiness?.ready`); action `sendForSafetyCheck()` through `act()`, which refreshes the history (AC7 visible at once).
- **`views/events/CoordinatorEventView.vue`:**
  - On a `planning` event, a **Send for safety check** button in the header action row.
  - Not ready: the button is disabled, and a "Not ready for safety check" list under it shows `safety_readiness.missing` verbatim, linked by `aria-describedby`.
  - Ready: the button opens `ConfirmModal` — title "Send for safety check?", message "The Safety Officer will check the venue and technical arrangements. Venue and equipment can't be requested again while it's in review.", confirm label "Send". Success toast: "Sent for safety check". A 409 (stale page) shows in the page alert.
  - A **For information** block shows the registration setup (enabled or not, capacity, opening and closing times). It never affects the button (AC4).
- **`views/events/EventDetailView.vue` (organiser):** when `confirmed`, an **Arrangements** card with the venue name and booking status, and the technical status (AC8). No internal preparation notes (AUTH-R2). An organiser-facing description for `safety_review`.
- Status lists (§7).

## 7. Status lists

| List | Location | `safety_review` |
|---|---|---|
| `ACTIVE_COORDINATOR_STATUSES` | `events/service.py`, `features/events/dashboard.js` | Added between `planning` and `confirmed` (dashboard filter and groups follow) |
| `arrangement_issue` statuses | `events/service.py` `_action_kind` | Added |
| `readinessGaps` statuses | `features/events/dashboard.js` | Added |
| `COMMENTABLE_STATUSES` | `events/schemas.py`, `features/events/comments.js`, `add_event_comment` | Added, all three |
| Organiser dashboard counts and groups | `features/events/organiserDashboard.js` | Own count and group: label from `STATUS_LABELS`, description "Events being checked by the Safety Officer." |
| `QUEUE_EVENT_STATUSES` (tech-support pending lines) | `equipment/service.py` | Added |
| Equipment request submission, venue booking request | `equipment/service.py`, `request_venue_booking` | Not added: Planning only |
| `reject` sources | `events/lifecycle.py` | Not added: the Safety Officer decides during review (CR-104) |
| Cancellation sources | 84, not built | Not added; flagged |

## 8. Testing (TDD: each test written and seen failing first)

**Backend (pytest, mocked at the Supabase client seam)**
- `tests/test_safety_readiness.py`: zero bookings; `held` and `re_review` block; `rejected`, `cancelled`, `released` ignored; one approved plus one held blocks; a flagged booking blocks (one message per distinct flag); technical `pending` and `issue` block, `ready` and `not_required` pass; several missing items in the fixed order; the result never depends on registration fields.
- `tests/test_send_for_safety_check.py`: happy path (RPC called with `["planning"]`, `safety_review`, the row's version and both messages; response status `safety_review`); 404 missing and draft; 403 unassigned coordinator; 403 for organiser, venue staff, tech support, attendee, Lead and Safety Officer; 403 for an account holding `event_coordinator` whose active role is another (raw request, SCRUM-76); 409 from every status except `planning`; 409 naming the missing items (RPC not called); 409 stale on an empty RPC result.
- Event read: `safety_readiness` present for the coordinator on `planning`, `null` on other statuses and for the organiser; organiser gets `venue_booking` only on `confirmed`.
- Status lists: coordinator dashboard lists a `safety_review` event and raises `arrangement_issue` on it; a comment on a `safety_review` event is accepted; tech-support queue keeps its pending lines.
- `technical_status` is the dashboard's source (dashboard tests still pass through it).
- The route-matrix test covers the new endpoint's guard automatically.

**Frontend (Vitest)**
- Store: `canSendForSafetyCheck` truth table; `sendForSafetyCheck` posts, updates the event and refreshes history; failure keeps the error.
- `CoordinatorEventView`: disabled button with the missing list and `aria-describedby`; enabled button → modal → send → toast; no button outside `planning`; the For information block.
- `EventDetailView`: Arrangements card only on `confirmed`.
- `comments.js`, `dashboard.js` (`ACTIVE_COORDINATOR_STATUSES`, `readinessGaps`), `organiserDashboard.js` (count and group).

**Database:** `supabase/verification/send_for_safety_check.sql` (rolled back): sending a fixture `planning` event sets `safety_review`; one history row with the actor; one notification to the organiser and one to each Safety Officer, none to the actor; a stale version returns no row and changes nothing; `add_event_comment` accepts a `safety_review` event.

**Live checks (recorded)**
- `backend/scripts/verify_live.py`: 403 for non-coordinator roles; 409 naming the missing items for a not-ready fixture event (no data changes); runs the SQL script above.
- `frontend/e2e/`: the disabled button and its reasons on a fixture `planning` event.
- The successful send changes shared data: covered by the rolled-back SQL script and a manual case.

Full suites (`pytest`, `npm run test:coverage`) green before done, coverage floors held.

## 9. Contract to agree with Eileen (24)

Text to send her (the developer sends it; the agent doesn't contact teammates):

> 82 reads an event's technical status through one function: `events.service.technical_status(row) -> ReadinessState`, values `not_required`, `pending`, `ready`, `issue`. Today it returns `events.technical_readiness`, which nothing writes, so every event reads `not_required`. When 24 derives the status from equipment lines (24 AC11: no lines → Not required), please replace that function's body (or have it call your equipment-service function) rather than reading the column elsewhere. 82 treats `ready` and `not_required` as ready; `pending` and `issue` block with "Technical status is not Ready." The coordinator dashboard uses the same function.

## 10. Manual cases and traceability

New cases in `docs/test-cases/` (events area), each with Type, Created and Last run:

| AC | Covered by |
|---|---|
| AC1 | Send happy path (manual + SQL script); notifications in the SQL script |
| AC2 | Readiness unit tests; 409 API tests; live 409 check; e2e disabled button |
| AC3 | Unit test: `not_required` passes; until 24, stated as not verifiable end to end |
| AC4 | Unit test; manual: For information block |
| AC5 | API tests (statuses, roles, active role); no confirm endpoint exists |
| AC6 | Delivered by CR-104; here only the absence of any coordinator confirm path |
| AC7 | SQL script history row; manual: history shows the entry |
| AC8 | Vitest; manual with a seeded confirmed event |
| AC9 | Unit tests (`held`, `re_review`); `expired` via the flag seam once CR-99 lands |
| AC10 | Unit tests via the flag seam; end to end once CR-94 and CR-95 land |

Manual browser pass for the developer: the coordinator page at desktop and phone width (button, missing list, modal wording, toast), the organiser's Arrangements card, the organiser and coordinator dashboards' Safety review group.

## 11. Paper trail

- `docs/IMPLEMENTATION_MAP.md`: the endpoint, the RPC, `readiness.py`, the `technical_status` seam, `safety_readiness` on the read, the race note, `safety_review` not a cancellation source (for 84); replace the existing "`safety_review` is a status, but most status lists don't include it yet" note; status table; "Last updated".
- `docs/BUILD_LOG.md` §4: the 82 entry.
- `docs/REQUIREMENTS.md`: §5 transition row gains the organiser notification [Team decision]; §6.6 readiness table (venue rule, technical seam, programme from 89) and RD-R1 reworded from "Confirm" to "Send for safety check"; the §6.6 acceptance criteria about confirming reworded for the safety check; §9 gains the no-booking [Assumption] and the technical-status gap until 24.
- `docs/test-cases/` and the run logs under `docs/test-cases/runs/`.

## 12. Out of scope

- The Safety Officer's decisions and Confirmed (CR-104), the review queue (CR-103).
- Booking flags and hold expiry (CR-94, CR-95, CR-99); derived technical status (24).
- Cancelling from `safety_review` (84).
- A notification read API or bell (SCRUM-53, 69).
- Programme documents (89).
