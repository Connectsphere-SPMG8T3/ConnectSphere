# CR-103 (AC1–4, AC6) and CR-104 — Safety review queue and the operational safety decision: design

_Date: 2026-10-09 · Branch: `feature/cr-103-cr-104-safety-review-decision` · Epic: Event status management · Sprint 3 · Priority 2 · 2 SP each · Assignee: Jie Ching_

## 1. Stories and acceptance criteria (Product backlog sheet, rows 70 and 71, read 9 Oct)

**CR-103 Safety review queue** (IN PROGRESS; AC5, the Safety Officer role, merged in PR #47)

- **AC1** Events sent for safety check (82) appear in the Safety Officer's queue, oldest first.
- **AC2** The review page shows expected attendance and, for each venue, its capacity, layout, accessibility, emergency access and known restrictions (CR-100).
- **AC3** It also shows the equipment list and the Technical Support Staff confirmation that equipment does not block exits (24 AC10).
- **AC4** Only users acting as Safety Officer can view the queue. Others get 403.
- **AC6** The review page also shows the event's own accessibility requirements. Crowd movement is assessed from attendance against each venue's capacity and layout, its emergency access and the exit confirmation; the Safety Officer records any crowd-movement concerns in the decision comment (CR-104).

**CR-104 Record the operational safety decision** (moved TO DO → IN PROGRESS on 9 Oct)

- **AC1** Approve: Confirmed; organiser, coordinator, venue staff and technical support are notified.
- **AC2** Request changes (comment required): back to Planning, the affected venue or equipment arrangements are marked for re-review, the coordinator is notified.
- **AC3** Reject the safety arrangement (reason required): back to Planning, the rejected arrangements must be replaced (for example a different venue), not just adjusted. The coordinator is notified. The event itself is not rejected. **To confirm at the project consult.**
- **AC4** After changes or a rejection, the coordinator sends the event for safety check again (82).
- **AC5** An event cannot be Confirmed without Safety Officer approval, including by a direct API call.
- **AC6** A change to attendance, venue or equipment after approval (37) returns the event to Planning.
- **AC7** Every decision, comment, who made it and when are recorded in the event history.
- **AC8** Only users acting as Safety Officer can decide. Others get 403.
- **AC9** The Safety Officer always responds: no timeout or escalation.
- **AC10** If an arrangement stops being ready while the event is in Safety review (booking flagged by CR-94/95, cancelled by 85, technical status leaves Ready), the event returns to Planning, leaves the queue, and the coordinator and Safety Officers are notified.

The ACs match `docs/proposals/week7-customer-changes.md` §3.

**Delivery boundary (decided 9 Oct, [Team decision]).** CR-104 AC6 and AC10 depend on stories nobody has started (CR-94, CR-95, 85, 24, 37). This work delivers the shared function `events.service.return_to_planning` and its `safety_review` and `confirmed` paths, fully tested, with **no callers wired**. AC6 and AC10 are complete only as each caller lands; the final report says so and does not claim them done. CR-103 AC2 (emergency access, restrictions) and AC3 (equipment list, exit confirmation) show "Not recorded" until CR-100 and 24 land.

## 2. Already in place (SCRUM-82, PR #48)

`safety_review` status; `POST /events/{id}/send-for-safety-check`; `events/readiness.py`; the seam `events.service.technical_status(row)`; RPC `send_event_to_safety_review`; `lifecycle.TRANSITIONS` rows `safety_approve` (→ confirmed), `safety_request_changes`, `safety_reject`, `safety_withdraw` (→ planning), none used yet; the Safety Officer role, route `/dashboard/safety` and a placeholder `SafetyDashboard.vue` (PR #47). `transition_event` takes statuses as text, checks `status = any(from)` and `version = expected` under `for update`, writes the history row (`actor_id` may be null) and notifies only the organiser when a notify type is given (null skips it). It releases bookings only on a `rejected` outcome.

## 3. Decisions

| Decision | Choice | Label |
|---|---|---|
| Where the officer's comment lives | New table `event_safety_decisions`, readable only by the assigned coordinator and Safety Officers. It is **never** copied into `event_status_history.reason` or into a notification: the organiser can read history and notifications (AUTH-R2). | [Team decision] |
| What the organiser sees | Status plus a fixed plain-language reason per decision (see §7), never the comment | AUTH-R2 |
| "Marked for re-review" (AC2) | The officer ticks the affected bookings and equipment lines by record. Ticked `approved` bookings → `re_review`; ticked `reserved` equipment lines → `re_review`. Unticked arrangements stay as they are. Today only `pending` equipment lines exist (24 isn't built), so the equipment part changes nothing until 24 lands. (As built: a ticked `pending` line is left as it is on request-changes, because only a reservation can be re-reviewed; on reject, `pending`, `reserved` and `re_review` lines → `rejected`.) | [Team decision] |
| "Reject the safety arrangement" (AC3) | Ticked bookings → `released`; ticked equipment lines → `rejected`. The event returns to Planning and is not rejected. Awaiting the consult. | [Assumption], REQUIREMENTS §9 |
| Same venue booked again after a rejection | Not blocked. The decision row records the rejected booking ids and venue ids, and the coordinator's page shows "Rejected by the Safety Officer" beside them. Enforcing a different venue would change `request_venue_booking` (SCRUM-19) and AC3 itself is unconfirmed. | [Assumption], §9 |
| Notified on approval (AC1) | Organiser (through `transition_event`), the assigned coordinator, every `venue_staff` holder and every `tech_support` holder, deduplicated, never the actor. Held roles, not the active one: a notification grants no access (the `venue_booking_requested` pattern). | [Team decision] |
| Race between reading and approving | `bookings` and `equipment_requests` changes do not bump `events.version`. The approval wrapper therefore locks the event row and re-checks in SQL that at least one active booking exists and every active booking is `approved`, else it returns nothing and the API answers 409 naming the cause. Technical status is still checked in Python through `technical_status`; that small race stays until 24 derives it, and is recorded in `IMPLEMENTATION_MAP` §5. | [Team decision] |
| Two officers deciding at once | Serialised by `transition_event`'s lock plus the version and source-status checks. The loser gets 409 (LC-R1). A decision row is written only after the transition succeeded. | |
| Queue order | The latest history entry with `to_status = 'safety_review'` for each event, oldest first, event id as tie-breaker (a resubmitted event re-queues at its new time). | [Team decision] |
| Officer access to events | Read-only: no edit, no comment, no booking (Q5) | [Assumption] |
| Crowd movement (CR-103 AC6) | No new field. The page shows attendance against each venue's capacity and layout; the officer's concerns go in the decision comment. | [Team decision] (sheet) |
| Wrapper design | Three RPCs with fixed source and target statuses; no configurable transition parameters. | simplicity |

## 4. Database — one migration, `supabase/migrations/<YYYYMMDDHHMMSS>_safety_review_decision.sql`

Timestamped when created; it must sort after `20261008150001`.

**Table `public.event_safety_decisions`:** `id uuid pk`, `event_id` → `events` on delete cascade, `decision` (check in `approved`, `changes_requested`, `arrangement_rejected`, `withdrawn`), `comment text` (1–1000 chars after trim; null allowed only for `approved` and `withdrawn`), `reason_code text` (set only for `withdrawn`), `affected_booking_ids uuid[]`, `affected_equipment_request_ids uuid[]`, `rejected_venue_ids uuid[]`, `decided_by` → `profiles` on delete set null (null for system withdrawals), `decided_at timestamptz default now()`. Index `(event_id, decided_at desc)`. RLS on, select-only: the event's assigned coordinator, or a caller whose `private.current_user_role()` is `safety_officer`. No insert, update or delete policy; writes go only through the RPCs. Nothing else (the organiser included) can select it.

**RPCs** (`security definer`, `set search_path = ''`, `execute` revoked from `public`/`anon`/`authenticated`, granted to `service_role`, all in the pattern of `send_event_to_safety_review`). Each calls `public.transition_event` with fixed statuses and `p_notify_type = null`, and returns nothing if that returns no row (stale version or wrong status).

- `safety_approve_event(p_event_id, p_actor_id, p_expected_version, p_comment, p_organiser_message, p_staff_message)`: `safety_review → confirmed`. Before the transition, under the event row lock, checks the booking rule above and returns nothing if it fails. Then the history row (no reason), the `approved` decision row, and notifications to the organiser, coordinator, `venue_staff` and `tech_support` holders (deduplicated, minus the actor), type `event_safety_approved`.
- `safety_return_event(p_event_id, p_actor_id, p_expected_version, p_decision, p_comment, p_booking_ids uuid[], p_equipment_request_ids uuid[], p_coordinator_message)`: `safety_review → planning`. `p_decision` is `changes_requested` or `arrangement_rejected`. Only ids that belong to the event are touched; any other id makes the call return nothing. Request changes: those `approved` bookings → `re_review`, those `reserved` equipment lines → `re_review`. Reject: those bookings → `released` (and their venue ids stored), those equipment lines → `rejected`. Decision row; coordinator notified (`event_safety_changes_requested` / `event_safety_arrangement_rejected`); the organiser is not notified, since the arrangements are the coordinator's to fix.
- `return_event_to_planning(p_event_id, p_expected_version, p_from_status, p_reason_code, p_coordinator_message, p_officer_message)`: `safety_review` or `confirmed` → `planning`, actor null. History row (no reason), `withdrawn` decision row with the reason code, coordinator notified (`event_returned_to_planning`), and every Safety Officer too when `p_from_status` was `safety_review`. It does not change bookings or equipment: the caller's own story has already changed them.

**Verification script** `supabase/verification/safety_decision_checks.sql` (rolled back), §9.

Applying it: `supabase db push --dry-run` is shown to the developer, who runs the push (per `live-check-environment-quirks`). Afterwards `supabase migration list --linked` and the Supabase advisors are checked.

## 5. Backend (`backend/app/modules/events/`)

**`lifecycle.py`:** new row `approved_change`: `confirmed → planning` (CR-104 AC6). The other four `safety_*` rows are now used.

**`schemas.py`:** `SafetyApproveRequest {comment: str | None}`; `SafetyChangesRequest {comment (required, stripped, ≤ 1000), booking_ids: list[UUID], equipment_request_ids: list[UUID]}`; `SafetyRejectRequest` (same shape, the field named `reason`); `SafetyDecision {id, decision, comment, reason_code, affected_booking_ids, affected_equipment_request_ids, rejected_venue_ids, decided_by_name, decided_at}`; `SafetyQueueItem`, `SafetyQueueResponse`; `SafetyReviewResponse` (§ below); `EventResponse.latest_safety_decision: SafetyDecisionSummary | None` (decision, `reason_label`, `decided_at`; **no comment**) for the organiser and `SafetyDecision` for the coordinator.

**`repository.py`:** `safety_approve(...)`, `safety_return(...)`, `return_to_planning(...)` through `.rpc(...)`, `None` when stale, same shape as `send_to_safety_review`; `list_safety_queue()`, `list_safety_decisions(event_id)`.

**`service.py`:**

- `safety_approve(event_id, officer_id, body) -> EventResponse`, `safety_request_changes(...)`, `safety_reject(...)`. Each: load the event (404 missing or draft; the officer needs no assignment), `lifecycle.target(action, status)` (409 `Cannot <action> an event that is <status>`), call the RPC, no row → 409. For approve, the 409 distinguishes "arrangements changed since you opened it, reload" from the stale-version message by re-reading readiness after an empty result.
- `return_to_planning(event_id, *, reason_code: ReturnReason, message: str | None = None, actor_id: str | None = None) -> EventResponse | None`. **The contract teammates call.** Loads the event; returns `None` if it is not in `safety_review` or `confirmed` (nothing to do, no error); picks `safety_withdraw` or `approved_change`; calls the RPC. `ReturnReason` is `arrangement_flagged`, `booking_cancelled`, `technical_not_ready`, `approved_details_changed`, each with a fixed coordinator message and a fixed officer message. No caller is wired by this work.
- `safety_queue() -> SafetyQueueResponse`, oldest first by latest entry into review.
- `safety_review(event_id) -> SafetyReviewResponse`: the event's name, organiser name, coordinator name, times, `expected_attendance`, `accessibility_needs`, `registration` for information, the active booking(s) with the venue's capacity, layouts, accessibility features and `attendance_to_capacity` (a ratio computed here, never stored), `emergency_access` and `restrictions` as `null` (the UI shows "Not recorded", CR-100), `equipment_lines` (every line with its status; empty list today shows "No equipment requested"), `exit_confirmation` as `null` ("Not recorded", 24 AC10), and the decisions list.
- `safety_decisions(event_id, user_id, role)`: coordinators (assigned only) and Safety Officers; the organiser has no such read.
- `read(...)` for the coordinator sets `latest_safety_decision` (full) on `planning`; for the organiser it sets the label-only summary on `planning`, `safety_review` and `confirmed`.

**`router.py`** (plain `def`, guard alias `SafetyOfficer = Annotated[CurrentUser, Depends(require_roles(["safety_officer"]))]`, the active role):

| Endpoint | Guard | Notes |
|---|---|---|
| `GET /events/safety-queue` | SafetyOfficer | declared above `/{event_id}` |
| `GET /events/{event_id}/safety-review` | SafetyOfficer | 404 unless the event is `safety_review` |
| `GET /events/{event_id}/safety-decisions` | `event_coordinator` (assigned) or SafetyOfficer | never the organiser |
| `POST /events/{event_id}/safety-approve` | SafetyOfficer | 200 `EventResponse` |
| `POST /events/{event_id}/safety-request-changes` | SafetyOfficer | 422 on a blank comment |
| `POST /events/{event_id}/safety-reject` | SafetyOfficer | 422 on a blank reason |

Idempotency: a second decision on the same version gets 409 with `Cannot <action> an event that is <status>`.

## 6. Frontend (`frontend/src/`)

- **`services/api.js`:** `eventsApi.safetyQueue`, `safetyReview`, `safetyDecisions`, `safetyApprove`, `safetyRequestChanges`, `safetyReject`.
- **`features/events/safetyReviewStore.js`** (Pinia): queue, review, decisions, `decide(kind, payload)` through the same `act()` pattern as `eventReviewStore`.
- **`views/dashboards/SafetyDashboard.vue`:** the placeholder body becomes the queue (event name, organiser, start, attendance, waiting time, link to the review), oldest first, with an empty state.
- **`views/events/SafetyReviewView.vue`** (route `/safety/events/:id`, `allowedRoles: ["safety_officer"]`): event summary and accessibility needs; per-venue block with capacity, layout, accessibility, attendance-to-capacity; "Not recorded" for emergency access, restrictions and exit confirmation; equipment lines; earlier decisions; a decision panel with a comment box (hint: "Record any crowd-movement concerns here"), checkboxes for the event's bookings and equipment lines, and Approve / Request changes / Reject through `ConfirmModal`. Request changes and Reject need the comment.
- **`CoordinatorEventView.vue`:** a "Safety Officer's decision" banner on a `planning` event carrying a decision, with the comment and the affected arrangements; a "Rejected by the Safety Officer" note beside a released booking.
- **`EventDetailView.vue` (organiser):** a plain line from `reason_label`, never a comment.
- **Router and `Nav.vue`:** the new route's guard on the active role; no new nav entry beyond the dashboard link.

## 7. Plain reasons (organiser) and fixed messages

| Decision | Organiser sees |
|---|---|
| `approved` | "Approved by the Safety Officer." |
| `changes_requested` | "The Safety Officer asked for changes to the arrangements." |
| `arrangement_rejected` | "The Safety Officer did not accept an arrangement; it must be replaced." |
| `withdrawn` | "An arrangement changed, so the event went back to planning." |

Notification messages use the same fixed text with the event name, never the comment.

## 8. Testing (TDD: each test written and seen failing first)

**Backend (pytest, mocked at the Supabase client seam)**

- `test_safety_decisions_api.py`: each decision's happy path (RPC called with the fixed statuses, version, ids); 404 missing and draft; 409 from every status but `safety_review`; 409 on a stale version; 422 blank comment or reason; 403 for organiser, coordinator, venue staff, tech support, attendee and Lead; 403 for an account holding `safety_officer` whose active role is another (raw request, SCRUM-76); an id that is not the event's is refused; a second decision answers 409.
- `test_safety_queue_and_review.py`: oldest first by latest entry into review, a resubmitted event re-queues, tie-breaker; review payload with "Not recorded" fields as `null`; 403 matrix; 404 for an event not in review.
- `test_return_to_planning.py`: both source statuses call the right RPC; any other status returns `None` and calls nothing; each reason code's fixed messages; stale version.
- Leakage: the organiser's read, history and notification messages never contain the comment; the decisions read refuses the organiser.
- The route-matrix test covers each new endpoint's guard.

**Frontend (Vitest):** store; `SafetyDashboard` queue and empty state; `SafetyReviewView` (Not recorded fields, comment required, modal, affected ticks); the coordinator banner; the organiser line; the route guard denial for other active roles.

**Database:** `supabase/verification/safety_decision_checks.sql` (rolled back): approve with an `approved` booking, with a `held` booking (returns nothing), with a missing booking; request changes → `re_review`; reject → `released` and the venue ids stored; foreign ids refused; `return_to_planning` from both statuses and from a wrong status; no `reason` on any history row; one decision row per call; recipients deduplicated and the actor excluded; RLS: the organiser, an unassigned coordinator and venue staff select no decision rows, the assigned coordinator and a Safety Officer do.

**Live checks (recorded)**

- `backend/scripts/verify_live.py`: 403 for the other roles on every new endpoint; 404 and 409 paths that change no data; runs the SQL script.
- `frontend/e2e/`: the route guard and the queue's empty state, if a Safety Officer account exists.
- No Safety Officer account exists in the live project yet; the account is granted by hand (`docs/SETUP.md`, "Grant a staff role"). Checks that need one are listed as not verified or run once the developer has created it.

Full suites (`pytest`, `npm run test:coverage`) green, coverage floors held.

## 9. Open items

- **Project consult:** AC3, the meaning of "reject the safety arrangement" (REQUIREMENTS §9).
- **CR-100 (unowned):** emergency access and restrictions.
- **24 (Eileen):** the exit confirmation, the derived technical status, and that clearing the confirmation calls `return_to_planning`.
- **84:** `safety_review` as a cancellation source.
- **Notification read API / bell:** 53, 69. Notifications are written, not yet shown.

### Contract for teammates (the developer sends it; the agent contacts no one)

> `events.service.return_to_planning(event_id, *, reason_code, message=None, actor_id=None)` sends an event in Safety review or Confirmed back to Planning in one transaction (history row, coordinator notification, plus the Safety Officers when it leaves review). It returns `None`, and does nothing, if the event is in any other status, so you don't need to check the status first. Call it after you have already changed your own records (flagged the booking, cancelled it, cleared the exit check). `reason_code` is one of `arrangement_flagged` (CR-94, CR-95), `booking_cancelled` (85), `technical_not_ready` (24), `approved_details_changed` (37). It writes no comment of its own, and nothing from your records reaches the organiser. If Supabase is unreachable it raises `EventServiceUnavailableError` (HTTP 503) instead of returning `None`, so call it after your own change has committed and decide whether your caller should catch that error; a failed call leaves the event where it was. It exists on `main` once CR-104 merges; the first merge to call it should use that exact signature.

## 10. Paper trail

- `docs/IMPLEMENTATION_MAP.md`: the endpoints, the table, the three RPCs, `return_to_planning` and its contract, the status table, the residual technical-status race, the "no callers wired" note for AC6 and AC10, the updated "Last updated" line; the `SafetyDashboard` note ("the CR-103 queue replaces the safety page's body") resolved.
- `docs/BUILD_LOG.md` §4: entries for CR-104 and CR-103.
- `docs/REQUIREMENTS.md`: the transitions for `safety_approve`, `safety_request_changes`, `safety_reject`, `safety_withdraw`, `approved_change`; the decision-visibility rule (AUTH-R2); §9 gains the same-venue and consult items.
- `docs/test-cases/` (events and Safety Officer areas) with Type, Created and Last run; run logs under `docs/test-cases/runs/`.

Manual browser pass for the developer: the queue and review page at desktop and phone width (wording, "Not recorded" labels, comment hint, modal text), the coordinator banner, the organiser's plain line, and that the organiser never sees a comment.

## 11. Out of scope

- Wiring callers of `return_to_planning` (CR-94, CR-95, 85, 24, 37).
- CR-100's venue fields; 24's equipment reservation, derived technical status and exit confirmation.
- Blocking the same venue after a rejection; cancellation from Safety review (84).
- A notification read API or bell.
