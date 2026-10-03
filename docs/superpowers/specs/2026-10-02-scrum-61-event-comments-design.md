# SCRUM-61 — Comment and discuss on my event: design

_Date: 2026-10-02 · Branch: `feature/scrum-61-event-comments` · Epic: SCRUM-14 Event Information Management · Sprint 2_

## 1. Story and acceptance criteria (from Jira)

> As an Event Organiser, I want to add comments and questions to my event record, so that planning conversations are retained alongside the event rather than scattered across email.

- **AC1** Organiser and authorised staff can add comments/questions to an event record.
- **AC2** Each comment records the contributor and timestamp.
- **AC3** Relevant parties are notified of new comments.
- **AC4** All discussions are stored as part of the event history.

Customer context: QA2-27 names comments attached to the event record as the organiser–coordinator channel, and lets the coordinator record offline conversations manually. @mentions and resolve are optional (QA-131, QA-132). Comments never block progression (QA-133). REQUIREMENTS §8 already names the table `event_comments`. This story answers §9 Q12: comments are in release 1.

## 2. Decisions

| Decision | Choice | Label |
|---|---|---|
| Who may read and post ("authorised staff") | The event's owning organiser and its assigned coordinator, each acting in that role. Same readers as `event_status_history` | [Team decision], QA2-27 |
| Notifications (AC3) | Write a `comment_added` row to `notifications` for the other party. No read API or bell; that remains SCRUM-27 | [Team decision] |
| Relation to history (AC4) | A separate, permanent "Discussion" thread stored in `event_comments`, shown beside the status timeline. No merged change log; that remains SCRUM-62 | [Team decision] |
| When posting is allowed | Non-draft, non-closed statuses: `submitted`, `under_review`, `returned`, `planning`, `confirmed`. `rejected`, `cancelled`, `completed`: thread visible, posting refused (409). `draft`: no thread (404 to coordinators, as everywhere) | [Team decision] |
| Body | Plain text, trimmed, 1–1000 characters, matching the reject reason and return message caps | [Assumption] |
| Editing and deleting | Not allowed; comments are append-only so the record stays trustworthy | [Team decision] |
| @mentions, resolve | Not built (optional per QA-131/132) | — |
| Offline conversations (QA2-27) | Recorded by the coordinator as an ordinary comment; no special type | [Team decision] |
| No coordinator assigned yet | The organiser may still post; nobody is notified | [Assumption] |

## 3. Approach

The comment and its notification are written by one `security definer` database function, in one transaction, called only by the backend (`service_role`). This follows `transition_event`, `return_event_for_amendment` and `resubmit_event`: both rows are saved or neither is, and the database clock sets the timestamp.

Rejected alternatives: two separate inserts from the service (a failure between them leaves a comment that notified no one, breaking AC3); an insert trigger that writes the notification (atomic, but hides notification logic from the backend; the project reserves triggers for the creation history row).

## 4. Database

New migration `supabase/migrations/<timestamp>_event_comments.sql`:

- **Table `public.event_comments`**
  - `id uuid primary key default gen_random_uuid()`
  - `event_id uuid not null references public.events (id) on delete cascade`
  - `author_id uuid references public.profiles (id) on delete set null` (named FK, so the API can embed the author)
  - `body text not null`, check `length(btrim(body)) between 1 and 1000`
  - `created_at timestamptz not null default now()`
  - index `(event_id, created_at)`
- **RLS** enabled, deny by default. One `select` policy: the event's organiser acting as `event_organiser`, or its assigned coordinator acting as `event_coordinator` (`private.current_user_role()`), identical in shape to `event_status_history_select_owner_or_assigned_coordinator`. No insert, update or delete policy.
- **Function `public.add_event_comment(p_event_id uuid, p_author_id uuid, p_body text) returns public.event_comments`**
  - `security definer`, `set search_path = ''`; `execute` revoked from `public`, `anon`, `authenticated`; granted to `service_role` only.
  - Locks the event row, raises if it doesn't exist, is a `draft`, or is `rejected`/`cancelled`/`completed` (a distinct error the repository maps to 409).
  - Inserts the comment (trimmed body).
  - Inserts a `notifications` row of type `comment_added` for the other party: organiser → assigned coordinator, coordinator → organiser. Skipped when the recipient is null or is the author.
  - Returns the inserted row.
- Authorisation of the caller (owner or assigned coordinator) is checked in the service before the call, as with `transition_event`.

## 5. Backend (`backend/app/modules/events/`)

| Endpoint | Guard | Behaviour |
|---|---|---|
| `GET /events/{event_id}/comments` | `event_organiser` (owner) or `event_coordinator` (assigned) | Oldest-first list of `{id, body, created_at, author: {id, full_name, role}}`. 404 for a non-owning organiser, 403 for a non-assigned coordinator, 404 to every coordinator on a draft. Empty list on a draft for its organiser |
| `POST /events/{event_id}/comments` | same | Body `EventCommentCreate {body}` (stripped, required, max 1000). 201 with the created comment. 422 blank/overlong; 409 `"Comments are closed for a <status> event"` on a closed event, and on a draft for its organiser; same 403/404 as `GET` |

- `schemas.py`: `EventCommentCreate`, `EventCommentAuthor`, `EventCommentResponse`.
- `service.py`: `comments(event_id, user_id, role)` and `add_comment(event_id, user_id, role, body)`, reusing the existing visibility helpers (`_owned_event` for organisers, `_assigned_event` for coordinators) exactly as `service.history` does. `author.role` is the role the author holds on this event (organiser or coordinator), derived from the event, not from `profiles.role`.
- `repository.py`: `list_comments(event_id)` (embeds `profiles` via the named FK), `add_comment(event_id, author_id, body)` (RPC wrapper).
- `core/exceptions.py`: `CommentsClosedError` (409).
- `router.py`: both routes with `require_roles`, so the active-role matrix test covers them.

## 6. Frontend (`frontend/src/`)

- `services/api.js`: `eventsApi.listComments(id)`, `eventsApi.addComment(id, body)`.
- `features/events/eventCommentsStore.js`: Pinia store `useEventCommentsStore` with `load(eventId)`, `post(body)`, `comments`, `loading`, `posting`, `error`. Tags state with its event id and drops superseded responses after every `await`, like `useEventReviewStore`.
- `features/events/comments.js` (pure): `COMMENT_MAX_LENGTH = 1000`, `CLOSED_STATUSES`, `canPost(status)`, `validateComment(body)`.
- `components/events/EventDiscussion.vue`: props `eventId`, `status`. Shows the thread oldest-first (author name, role label, time in SGT via the existing date helpers), an empty state (`BauhausEmptyState`), a textarea with a live 1000-character counter, and a Post button disabled while invalid or posting. On a closed status, the composer is replaced by a read-only note. Errors go to the inline error area; success clears the box and appends the comment.
- Mounted on `views/events/EventDetailView.vue` (organiser, hidden on drafts) and `views/events/CoordinatorEventView.vue`, beside `EventStatusHistory`.

## 7. Testing (TDD: each test written and seen failing first)

- **pytest** (`backend/tests/test_event_comments_api.py`, repository mocked):
  - organiser and assigned coordinator can list and post
  - blank, whitespace-only and 1001-character bodies → 422; exactly 1000 → 201
  - posting to `rejected`/`cancelled`/`completed` → 409; listing still works
  - another organiser → 404; non-assigned coordinator → 403; any coordinator on a draft → 404
  - venue staff, tech support, attendee → 403; the coordinator account acting as venue staff → 403, an organiser acting as attendee → 403 (SCRUM-76)
  - `test_active_role_access.py` stays green with the new routes
- **SQL** (`supabase/verification/event_comment_checks.sql`, rolled back): a comment writes exactly one notification to the right recipient in each direction; none when no coordinator is assigned; draft and closed events are refused; RLS hides comments from unrelated users and from a coordinator acting as another role; no update or delete is possible as `authenticated`; `created_at` comes from the database.
- **Vitest**: `comments.js` rules; `eventCommentsStore` (load, post, superseded responses); `EventDiscussion.spec.js` (rendering, empty state, counter, disabled and read-only states, error display); the two views mount it.
- **Live checks**: `verify_live.py` cases for listing and the 403/404 denials. Posting to a seeded event changes shared data, so those cases stay manual.

## 8. Manual cases and traceability

New section in `docs/test-cases/events.md`, prefix `TC-CMT`.

| Acceptance criterion | Manual cases | Automated equivalent |
|---|---|---|
| AC1 organiser and authorised staff can add comments | TC-CMT-001 organiser posts; TC-CMT-002 assigned coordinator posts; TC-CMT-003 blank/whitespace/over-1000 refused; TC-CMT-004 closed event read-only; TC-CMT-005 no thread on a draft | pytest happy paths, 422 and 409 cases; `EventDiscussion.spec.js` |
| AC1 (denials) nobody else reads or posts | TC-CMT-006 other organiser 404; TC-CMT-007 non-assigned coordinator 403; TC-CMT-008 other roles 403, incl. coordinator acting as venue staff | pytest denial tests; `test_active_role_access.py`; `event_comment_checks.sql` (RLS); `verify_live.py` |
| AC2 contributor and timestamp recorded | TC-CMT-009 author name, role and SGT time shown | pytest response shape; `event_comment_checks.sql` (`created_at` default); Vitest rendering |
| AC3 relevant parties notified | TC-CMT-010 organiser ↔ coordinator notification; TC-CMT-011 none when unassigned | `event_comment_checks.sql` |
| AC4 stored as part of event history | TC-CMT-012 thread persists across reload, oldest first; TC-CMT-013 comments cannot be edited or deleted | `event_comment_checks.sql`; pytest ordering |

Manual pass for the developer: TC-CMT-001, 002, 012 (change shared data), plus layout at phone width and wording on both event pages.

## 9. Paper trail

- `docs/REQUIREMENTS.md`: §8 comments row (decisions above, labelled); §9 Q12 answered; the 1000-character [Assumption] added to §9.
- `docs/IMPLEMENTATION_MAP.md`: status row, endpoints, reusable pieces, migration row, "know before you build" note (notification type `comment_added`); also correct SCRUM-33/34/52, which are merged but listed as unmerged.
- `docs/BUILD_LOG.md` §4 entry; `docs/test-cases/events.md` section; run logs in `docs/test-cases/runs/`.

## 10. Out of scope

Notification bell and read API (SCRUM-27); unified change log (SCRUM-62); comments from venue staff and tech support (revisit when bookings and equipment requests link them to an event); editing, deleting, @mentions, resolve, attachments.
