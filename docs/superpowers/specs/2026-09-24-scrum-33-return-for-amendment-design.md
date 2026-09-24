# Design: return an event request for amendment (SCRUM-33)

**Date:** 2026-09-24 · **Epic:** SCRUM-11 Event Review and Approval · **Sprint:** SCRUM Sprint 2
**Branch:** `feature/scrum-33-return-for-amendment` (stacked on `chore/split-test-cases`; merge that first)

## 1. Goal

The assigned Event Coordinator can **return** an under-review request to its organiser with a message and, optionally, the fields that need changing. The organiser sees the message with those fields highlighted, edits the same request (any field), and **resubmits** it with a note. It goes back to `under_review` with the **same coordinator**. Both steps are recorded in the event's status history, and the other party is notified each time. A request can be returned any number of times.

This replaces SCRUM-33's original "clarification thread the coordinator marks resolved" model, which contradicts the customer's answers (QA-22, QA-34, QA-77; REQUIREMENTS §6.4; PROJECT_REVIEW §B2a).

## 2. Acceptance criteria

Agreed with the developer on 2026-09-24. **The Jira description still shows the old text and needs updating to this list**, with a comment citing QA-22 and QA-77.

1. **Given** an under-review event assigned to me, **when** I return it with a message and flag fields (e.g. expected attendance), **then** the status is `returned` and the organiser is notified.
2. The organiser sees my message, with the flagged fields highlighted on their request.
3. **Given** a returned request, **when** the organiser edits any field and resubmits with a note, **then** the status goes back to `under_review` with the **same coordinator**, and I'm notified.
4. Every return and resubmission is recorded in the event history. A request can be returned more than once.
5. The return message is required: an empty or whitespace-only message is blocked.
6. Only the assigned coordinator can return, and only the owning organiser can resubmit. Others get 403/404.
7. Approve or reject while `returned` → 409.

**Rules carried from REQUIREMENTS:**
- The resubmission note is required: the §5 transition table lists it as the guard on `returned → under_review`.
- A resubmitted request must still pass submission validation ("basic info still complete", §5).
- **[Assumption]** The return message and the resubmission note are each capped at **1000 characters**, checked on the raw value, the same as the rejection reason. Recorded in REQUIREMENTS §9.

**Moved out of this story:** §6.4 also says no venue booking can be created while `returned` ("Requirements are still being amended."). No booking-creation endpoint exists yet, so this guard belongs to the story that builds booking creation. It is recorded in REQUIREMENTS §6.4 and IMPLEMENTATION_MAP.

## 3. Data layer: one migration

`supabase/migrations/20260924140000_event_amendment_requests.sql`

### `public.amendment_requests`

Matches the REQUIREMENTS §4 ERD. It has no `organiser_id` or `coordinator_id`: both are on `events`, and `event_status_history.actor_id` already records who returned the request.

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | `gen_random_uuid()` |
| `event_id` | `uuid` not null | FK `events(id)` on delete cascade |
| `message` | `text` not null | check: `length(btrim(message)) > 0` |
| `flagged_fields` | `text[]` not null | default `'{}'` |
| `returned_at` | `timestamptz` not null | default `now()` |
| `resubmission_note` | `text` null | set on resubmission |
| `resubmitted_at` | `timestamptz` null | set on resubmission |

- Check: `resubmission_note` and `resubmitted_at` are either both null or both set.
- Partial unique index on `(event_id) where resubmitted_at is null`: at most **one open** amendment per event. Each return adds a new row, so every round is kept.
- Index on `(event_id, returned_at desc)`.
- The flaggable field names are validated by the API (`EventField` enum, §4). The database doesn't duplicate that list.

### RLS

The table has RLS enabled and a single `select` policy that mirrors `event_status_history`'s: allowed when the event's organiser is acting as `event_organiser`, or its assigned coordinator is acting as `event_coordinator` (`private.current_user_role()`). There are no insert, update or delete policies, so only the API writes. This is a safety net: the API uses the secret key.

### Functions, called via `.rpc()`, `service_role` only

Both functions are `security definer`, `set search_path = ''`, return `setof public.events`, and have execute revoked from `public, anon, authenticated` and granted to `service_role`. Each runs in one transaction. **`transition_event` does not change**, so approve, reject and submit are untouched.

**`public.return_event_for_amendment(p_event_id, p_actor_id, p_from_statuses text[], p_to_status text, p_expected_version, p_message, p_flagged_fields text[], p_notify_message)`**
1. Calls `public.transition_event(...)` with `p_reason = p_message` and `p_notify_type = 'event_returned'`. That function notifies the organiser.
2. If no row comes back (stale version or wrong status), it returns nothing, and the API answers 409.
3. Otherwise it inserts the `amendment_requests` row and returns the event.

**`public.resubmit_event(p_event_id, p_actor_id, p_from_statuses, p_to_status, p_expected_version, p_note, p_notify_message)`**
1. Calls `public.transition_event(...)` with `p_reason = p_note` and no notification, because `transition_event` can only notify the organiser.
2. If no row comes back, it returns nothing.
3. Otherwise it sets `resubmission_note` and `resubmitted_at = now()` on the open amendment row.
4. It inserts a notification for the event's `coordinator_id`, type `event_resubmitted`, unless that is null or the actor.
5. It returns the event.

The allowed statuses come from `lifecycle.py`, which stays the single source of transition rules. The message and note go in as the history `reason`, so the existing history timeline shows them without any UI change.

## 4. Backend (`backend/app/modules/events/`)

### `lifecycle.py`

```python
"return": (frozenset({EventStatus.under_review}), EventStatus.returned),
"resubmit": (frozenset({EventStatus.returned}), EventStatus.under_review),
```

Approve (`under_review` only) and reject (`under_review`, `planning`) already exclude `returned`, which gives AC7. Tests lock that in.

### Schemas

- **`EventField`** (str enum): the 15 fields of `EventUpdateRequest`, from `name` through `registration_closes_at`.
- **`AMENDMENT_TEXT_MAX_LENGTH = 1000`**.
- **`EventReturnRequest`**: `message: str` (non-blank, trimmed, max length checked on the raw value, same validator shape as `EventRejectRequest.reason`) and `flagged_fields: list[EventField] = []` (duplicates removed, order kept).
- **`EventResubmitRequest(EventUpdateRequest)`**: adds `resubmission_note: str` with the same rules as `message`.
- **`AmendmentRequest`**: `id`, `message`, `flagged_fields: list[EventField]`, `returned_at`.
- **`EventResponse`** gains `amendment: AmendmentRequest | None = None`.

### Endpoints (plain `def`, thin router)

| Endpoint | Guard alias | Service |
|---|---|---|
| `POST /events/{id}/return` | `EventCoordinator` | `service.return_for_amendment(id, user.id, body)` |
| `POST /events/{id}/resubmit` | `EventOrganiser` | `service.resubmit(id, user.id, body)` |

### Service

- **`return_for_amendment`:**
  1. `_assigned_event` gives 404 for a draft or a missing event, and 403 if the caller isn't the assigned coordinator.
  2. `lifecycle.target("return", status)` gives 409: "Cannot return an event that is <status>".
  3. It calls `repository.return_event(...)`. An empty result is a stale event: 409 with `STALE_EVENT_MESSAGE`.
  4. It responds with `amendment` filled in.
- **`resubmit`:**
  1. `_owned_event` gives 404 if the caller isn't the owner.
  2. `lifecycle.target("resubmit", status)` gives 409.
  3. It merges the body's field edits (excluding the note) into the row and runs `_validate_submission`, which gives 422.
  4. If there are edits, it calls `repository.update_event` with the version check. A conflict gives 409.
  5. It calls `repository.resubmit_event(...)`. An empty result gives 409.

  This mirrors `submit`.
- **`read`** fills `amendment` from `repository.get_open_amendment(event_id)` when the status is `returned`. List responses leave it `null`.
- **Notification text:**
  - Return: `'Your event "<name>" was returned for amendment: <message>'`
  - Resubmit: `'"<name>" was amended and resubmitted: <note>'`

### Repository

`return_event(...)` and `resubmit_event(...)` wrap the RPCs, in the same shape as `transition_event`. `get_open_amendment(event_id)` selects the row where `resubmitted_at is null`, returning `dict | None`.

### Authorisation (the active role only, per the root AGENTS.md)

- `/return`: the organiser gets 403. A coordinator who isn't assigned gets 403. An account holding `event_coordinator` while acting as another role gets 403.
- `/resubmit`: the coordinator gets 403. An organiser who isn't the owner gets 404. An account holding `event_organiser` while acting as another role gets 403.
- `test_active_role_access.py` picks up both new routes automatically.

## 5. Frontend (`frontend/src/`)

### Shared: `features/events/amendment.js`

- **`EVENT_FIELD_LABELS`:** the API field names mapped to the form's own labels, in form order. For example, `expected_attendance` is "Expected attendance" and `starts_at` is "Proposed date and start time".
- **`FORM_INPUTS_BY_FIELD`:** the form inputs each API field highlights. `starts_at` covers the date and start-time inputs, `ends_at` covers the end-time input, and `event_timezone` covers the timezone select.
- **`canReturn(status)`** returns `status === "under_review"`. It lives in `eventReviewStore.js` alongside `canApprove` and `canReject`.
- **`AMENDMENT_TEXT_MAX_LENGTH = 1000`**, mirroring the API.

### Common inputs: an optional `flag` prop

`BauhausInput`, `BauhausSelect` and `BauhausCheckboxGroup` gain an optional `flag` string prop. When set:
- the field gets a distinct outline;
- the text appears under it, for example "Flagged by coordinator";
- the text is linked with `aria-describedby`.

It is separate from `error`: a flag is a request to review the field, not a validation failure, and both can show at once. The description `<textarea>` in `EventRequestView` gets the same treatment inline.

### API client and stores

- `eventsApi.returnForAmendment(id, {message, flagged_fields}, token)` and `eventsApi.resubmit(id, payload, token)`.
- `eventReviewStore.returnForAmendment(message, flaggedFields)` runs through the existing `act()`, which reloads the history afterwards.
- The organiser store (`stores/events.js`) gets `resubmit(id, form, note)` and `loadOne(id)`, which fetches `GET /events/{id}` so the amendment is available.

### Coordinator: `views/events/CoordinatorEventView.vue`

- A **"Return for amendment"** button, shown when `canReturn`.
- It opens a new **`components/events/ReturnEventModal.vue`**, a sibling of `RejectEventModal`. The modal has:
  - a required message with a 1000-character counter;
  - a `BauhausCheckboxGroup` of `EVENT_FIELD_LABELS`;
  - confirm, which stays disabled while the message is blank.
- On success it shows the toast "Returned to organiser". The page then shows the `returned` status and an `AmendmentBanner` (coordinator wording: "Waiting for the organiser to amend").

### Organiser

- **Dashboard:** the `amend` action routes to `event-new` with `query.id`, the same as `continue_draft`.
- **`EventRequestView`** also opens `returned` events, loaded through `loadOne`. In returned mode:
  - The heading reads "Amend your request".
  - A new **`components/events/AmendmentBanner.vue`** shows when the request was returned, the message and the flagged fields as a list. It doesn't name the coordinator: `EventResponse` carries only `coordinator_id`, and the history panel already shows who returned it.
  - Flagged inputs get the `flag` prop.
  - "Save draft" becomes "Save changes", which still sends a PATCH (the API allows it while `returned`).
  - "Submit request" becomes **"Resubmit"**. It opens a new **`ResubmitEventModal.vue`** with a required note (1000-character counter), then calls `eventsStore.resubmit`, shows the toast "Request resubmitted" and routes to the dashboard.
  - Client-side submission validation applies, the same as for submit.
- **`EventDetailView`**, when the event is `returned`, shows the `AmendmentBanner` and an "Amend and resubmit" button that opens the form.

## 6. Out of scope

- The notification bell and read API (SCRUM-27). The rows are written, but no UI displays them yet.
- Blocking venue bookings while `returned`. There's no booking-creation endpoint yet (§2).
- Coordinator dashboard "resubmitted" items (SCRUM-72). The dashboard's endpoint doesn't exist yet.
- Refactoring `RejectEventModal` into a shared base. The new modals are siblings; extract a base only if a fourth one is needed.

## 7. Tests and verification

Test-driven: each test is written first and seen failing for the right reason.

**Backend (`pytest`)**
- `test_event_lifecycle.py`: return and resubmit transitions, and every blocked starting status. Approve and reject from `returned` are blocked.
- `test_event_amendment_api.py` (new):
  - return: happy path (RPC arguments, notification text, response `amendment`); blank, whitespace-only, missing and over-1000 message gives 422; unknown field gives 422; flagged fields are de-duplicated; wrong status gives 409; stale gives 409; unassigned coordinator gives 403; organiser gives 403; acting as another role gives 403; draft gives 404.
  - resubmit: happy path with edits and note; note missing or blank gives 422; edits that break validation give 422 and no RPC is called; not `returned` gives 409; stale gives 409; not the owner gives 404; coordinator gives 403.
  - read: `amendment` is filled only while `returned`.
- `test_events_repository.py`: the RPC wrappers' parameters and `get_open_amendment`'s query.

**Database:** `supabase/verification/event_amendment_checks.sql`, rolled back, run against the real functions:
- return then resubmit then return: two amendment rows, one open;
- a second open row is refused;
- history rows carry the message and the note;
- the organiser is notified on return and the coordinator on resubmit, never the actor;
- stale version: nothing changes;
- RLS: the owner and the assigned coordinator see the rows, another organiser, another coordinator and `anon` see none.

**Frontend (Vitest):**
- `ReturnEventModal.spec.js` and `ResubmitEventModal.spec.js`: required text, the counter, the payload.
- `amendment.spec.js`: the labels and the field-to-input mapping.
- `eventReviewStore.spec.js`: `returnForAmendment`.
- `stores/events` spec: `resubmit`, `loadOne`.
- `CoordinatorEventView.spec.js`: the Return button only when `under_review`.
- `EventDetailView.spec.js`: banner and amend button when `returned`.
- A new `EventRequestView` returned-mode spec: heading, banner, flags, Resubmit flow.
- `organiserDashboard` specs: amend routing.
- Common input specs: the `flag` prop.

**Real system**
- Apply the migration to the live project, with no new advisor warnings.
- Run the verification SQL.
- Run uvicorn and send real HTTP requests for the flow and the denial cases.
- Go through the full flow in the browser with the console checked: the coordinator returns the request with flags, the organiser sees the banner and highlights, edits, and resubmits with a note, and the coordinator sees `under_review` with both history entries.
- Run the full `pytest` and Vitest suites.

## 8. Paper trail

- `docs/test-cases/events.md`: a new "Return for amendment (SCRUM-33)" section (TC-AMD-*) with traceability. Update TC-ORG-005 in `dashboards.md` to the new amend route.
- `docs/IMPLEMENTATION_MAP.md`:
  - the two endpoints, the table and functions, the `EventResponse.amendment` change;
  - `ReturnEventModal`, `ResubmitEventModal`, `AmendmentBanner`, `amendment.js`, the `flag` prop;
  - the note about the booking guard;
  - the "Last updated" line.
- `docs/SCENARIO.md` §4: a new entry for SCRUM-33.
- `docs/REQUIREMENTS.md`: the 1000-character [Assumption] in §9, and in §6.4 the note that the booking block depends on the booking-creation story.
- `docs/PROJECT_REVIEW.md` §B2a: SCRUM-33 is done in code, and the Jira text is pending.
- Jira: ask about moving SCRUM-33 to In Review when the PR opens.
