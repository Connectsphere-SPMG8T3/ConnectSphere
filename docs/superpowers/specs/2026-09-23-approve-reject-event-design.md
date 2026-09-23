# Design: approve and reject an event request (SCRUM-34, SCRUM-52)

**Date:** 2026-09-23 · **Epic:** SCRUM-11 Event Review and Approval · **Sprint:** SCRUM Sprint 2
**Branch:** `feature/scrum-34-52-approve-reject`

## 1. Goal

The assigned Event Coordinator can **approve** an under-review request, which moves it to `planning` (initial feasibility decision, not confirmation), or **reject** it with a mandatory reason, which closes it permanently. Each decision is recorded in the event's status history, visible in the UI, and the organiser is notified.

## 2. Acceptance criteria and rules

### SCRUM-34: Approve (Jira text, verbatim)

1. **Given** an event in *Under review* that is assigned to me, **when** I approve it, **then** its status becomes **Planning**. Approval is the initial feasibility decision (W1 Step 5, QA-23, QA2-8). It is **not** confirmation.
2. Approve is available **only** when the status is *Under review*. Approving an event that is Returned, Submitted, Planning, Confirmed, Rejected, Cancelled or Completed is blocked with "Cannot approve an event that is <status>" (QA-22).
3. Only the **assigned** coordinator can approve. Any other coordinator, any other role, and a user who holds the coordinator role but is currently acting as a different role all get *Forbidden*.
4. The organiser is notified of the approval. The coordinator isn't notified of their own action.
5. The approval, who made it, and when are recorded in the event history and visible in the UI (QA-70).
6. Approving does not book a venue or reserve equipment. Confirming the event is a separate, later step.

### SCRUM-52: Reject (the settled rules, which the Jira rewrite carries)

1. Reject requires a reason. A blank or whitespace-only reason is blocked.
2. Reject is allowed from `under_review` **or** `planning` only, which means before confirmation. A confirmed event is cancelled instead (QA2-6, LC-R5). Anything else returns 409 "Cannot reject an event that is <status>".
3. Only the assigned coordinator can reject. The Forbidden cases are the same as SCRUM-34 AC3.
4. A rejected request is closed and can't be edited or resubmitted (QA-34, QA-95).
5. Rejecting from `planning` releases the event's venue holds (`held`, `approved` and `re_review` bookings become `released`) in the same transaction (QA2-13, REQUIREMENTS §7).
6. The organiser is notified with the reason. The actor is not notified (NT-R1).
7. The rejection, its reason, who made it, and when are recorded in the history, and the organiser and the assigned coordinator can both see them.

## 3. Data layer: one migration

### `public.event_status_history`
Reconciled from `docs/proposals/core-events-schema.sql` §4 against the live `events` table.

| Column | Type |
|---|---|
| `id` | `uuid` PK, `gen_random_uuid()` |
| `event_id` | `uuid not null` → `events(id) on delete cascade` |
| `from_status` | `event_status null` |
| `to_status` | `event_status not null` |
| `actor_id` | `uuid null` → `profiles(id) on delete set null` |
| `reason` | `text null` |
| `at` | `timestamptz not null default now()` |

Index: `(event_id, at desc)`. This is the single home of the rejection reason. `events` does not get a `rejection_reason` column.

### `public.notifications`
| Column | Type |
|---|---|
| `id` | `uuid` PK |
| `recipient_id` | `uuid not null` → `profiles(id) on delete cascade` |
| `event_id` | `uuid null` → `events(id) on delete cascade` |
| `type` | `text not null` (`event_approved`, `event_rejected`) |
| `message` | `text not null` |
| `read_at` | `timestamptz null` |
| `created_at` | `timestamptz not null default now()` |

Index: `(recipient_id, read_at, created_at desc)`, for the future bell. **Write only in this branch:** no read endpoint and no UI. Delivery belongs to the SCRUM-27 stories (69, 53).

### RLS
Both tables have RLS enabled and deny by default. It is a safety net, because the API uses the secret key.
- `event_status_history` select: the event's organiser, or its assigned coordinator while the active role is `event_coordinator` (`private.current_user_role()`).
- `notifications` select: `recipient_id = auth.uid()`.
- No insert, update or delete policies. Writes happen only through the function below.

### `public.transition_event(...)`, called via `.rpc()`
```
transition_event(
  p_event_id uuid, p_actor_id uuid,
  p_from_statuses event_status[], p_to_status event_status,
  p_expected_version int, p_reason text,
  p_notify_type text, p_notify_message text
) returns setof events
```
- `security definer`, `set search_path = ''`. `execute` is revoked from `public`, `anon` and `authenticated`, and granted to `service_role` only.
- In one transaction:
  1. `update events set status = p_to_status, version = version + 1 where id = p_event_id and version = p_expected_version and status = any(p_from_statuses)`. If no row matches, return an empty set (the service maps this to 409).
  2. Insert `event_status_history (event_id, from_status, to_status, actor_id, reason)`.
  3. If `p_to_status = 'rejected'`: `update venue_bookings set status = 'released' where event_id = p_event_id and status in ('held','approved','re_review')`. Equipment reservations are a **documented hook**, because SCRUM-24's reserve flow isn't built.
  4. If `p_notify_type` is not null and the organiser is not the actor, insert a notification for the organiser.
- Generic by design: SCRUM-12 (`submitted → under_review`) and SCRUM-33 (return and resubmit) reuse it.

## 4. Backend (`backend/app/modules/events/`)

### `lifecycle.py` (pure, no I/O)
- `TRANSITIONS = {"approve": ({under_review}, planning), "reject": ({under_review, planning}, rejected)}`.
- `target(action, status) -> EventStatus` raises `EventTransitionError("Cannot <action> an event that is <status with spaces>")`.

### Endpoints (plain `def`)
| Method and path | Guard | Behaviour |
|---|---|---|
| `POST /events/{id}/approve` | `require_roles(["event_coordinator"])` | assigned check, then lifecycle, then RPC. 200 `EventResponse` |
| `POST /events/{id}/reject` | same | body `EventRejectRequest {reason}`. The reason is stripped; blank gives 422; max 1000 chars **[Assumption]** |
| `GET /events/{id}/history` | `require_roles(["event_organiser","event_coordinator"])` | organiser must own it; coordinator must be assigned. Newest first, with actor name |
| `GET /events/{id}` | broadened to `event_organiser` (owner) and `event_coordinator` (assigned) | organiser behaviour is unchanged |

### Authorisation
- Wrong active role: 403 (`require_roles`). This includes a coordinator-holding account acting as `venue_staff` (SCRUM-76).
- Unknown event: 404.
- Coordinator not assigned: **403**, per AC3. This deliberately departs from the organiser "404, not 403" shape: coordinators may already search every non-draft event (QA-87), so a 403 reveals nothing new.
- Organiser who doesn't own the event: 404, unchanged.
- RPC returns no row (lost race): 409 "This event was updated by someone else. Reload." (IM-R3).

### Errors
`EventTransitionError` (409) and `NotAssignedCoordinatorError` (403) go in `app/core/exceptions.py`. The existing events-local exceptions are left alone (out of scope).

### Notification text
- Approve: `Your event "<name>" passed its initial review and is now in planning.`
- Reject: `Your event "<name>" was rejected: <reason>`

### Schemas
`EventRejectRequest`, `EventHistoryEntry {id, from_status, to_status, actor: {id, full_name} | null, reason, at}`, `EventHistoryResponse {entries}`.

## 5. Frontend (`frontend/src/`)

- **Route** `/coordinator/events/:id`, `meta.allowedRoles: ['event_coordinator']`, → `views/events/CoordinatorEventView.vue`: details, status badge (`STATUS_LABELS`), Approve (via `ConfirmModal`), Reject (via `RejectEventModal`), and history. Buttons show only in the statuses where the action is allowed. The API remains the enforcement point.
- `components/events/RejectEventModal.vue`: a required reason textarea; confirm is disabled while the reason is blank or whitespace; a counter up to 1000.
- `components/events/EventStatusHistory.vue`: newest-first list, labels from `STATUS_LABELS`. Reused on the organiser's `EventDetailView`, which also shows the rejection reason prominently when rejected. There's no resubmit action, since editing a rejected event is already blocked.
- `features/events/eventReviewStore.js`: `load(id)`, `approve()`, `reject(reason)`, `loadHistory()`.
- `services/api.js`: `eventsApi.approve`, `eventsApi.reject`, `eventsApi.history`.
- **Known gap:** coordinators have no list of assigned events until the SCRUM-72 dashboard endpoint exists, so the page is reached by URL. Once that endpoint lands, the dashboard's action items should link here.

## 6. Out of scope
- The notifications read API and bell UI (SCRUM-27: 69, 53).
- `change_history` (SCRUM-62; LC-R2's second table).
- The `core.events` dispatcher from REQUIREMENTS §3.3. It isn't adopted yet; the RPC writes history and notifications directly. This deviation is recorded in REQUIREMENTS.
- Coordinator auto-assignment (SCRUM-12), return for amendment (SCRUM-33), confirmation (SCRUM-82), the coordinator dashboard endpoint (SCRUM-72).
- Releasing equipment reservations (a hook only).

## 7. Tests and verification
- **Pure:** `tests/test_event_lifecycle.py` covers every allowed and blocked status for both actions, and the exact LC-R1 messages.
- **API (mocked repository):** `tests/test_event_review_api.py` covers:
  - happy paths, with the RPC called with the right arguments
  - 409 per blocked status
  - 403 for a non-assigned coordinator
  - 403 for each other role
  - 403 for a coordinator-holding account acting as venue staff
  - 404 for an unknown id
  - 422 for a blank, whitespace or overlong reason
  - 409 when the RPC returns nothing
  - history access for the owner and the assigned coordinator, and denial for the rest
  - the coordinator read on `GET /events/{id}`

  `test_active_role_access.py` covers the new routes automatically.
- **Vitest:** `RejectEventModal` (disabled states), `eventReviewStore`, `EventStatusHistory`, and the route matrix.
- **Real system:**
  - `supabase migration list --linked`, then apply.
  - Seed an `under_review` event assigned to `coordinator@connectsphere.dev`, and a `planning` one with a held booking.
  - Real HTTP approve and reject.
  - Check the history and notification rows, that no notification went to the actor, and that the booking is `released`.
  - Call the RPC as `authenticated` and confirm it is refused.
  - Check the advisors.
  - Run the browser flow with Playwright, checking the console.
- The full `pytest` and `npm test` suites pass.

## 8. Paper trail
- IMPLEMENTATION_MAP: the new tables, the RPC, endpoints, components, the 403 note, and "Last updated".
- A SCENARIO §4 entry per story.
- TEST_CASES TC-REV-xxx.
- REQUIREMENTS: the reason-length [Assumption] and the §3.3 deviation.
- Jira: the SCRUM-52 rewrite (shown before saving), plus a status question for each story.
