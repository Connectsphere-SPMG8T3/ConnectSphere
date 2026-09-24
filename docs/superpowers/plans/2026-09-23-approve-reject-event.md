# Approve and Reject Event Requests: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the assigned Event Coordinator approve an under-review request into `planning` (SCRUM-34), or reject it with a mandatory reason (SCRUM-52). Each decision is recorded in the event's status history, visible in the UI, and notified to the organiser.

**Architecture:**
- A pure state-machine table (`events/lifecycle.py`) decides which transitions are allowed.
- One Postgres function, `transition_event`, called through `.rpc()`, does the status change, history row, venue-hold release and organiser notification in a single transaction.
- The FastAPI `events` module adds coordinator endpoints guarded by the active role and the assigned-coordinator relationship.
- The SPA adds a minimal coordinator review page and shows history and the rejection reason on the organiser's event page.

**Tech stack:**
- Backend: FastAPI 0.115, Pydantic 2.11, supabase-py 2.31 (PostgREST and `.rpc()`), pytest.
- Database: Postgres on Supabase (project `vuiryrzzyfecjqftwicj`).
- Frontend: Vue 3 `<script setup>`, Pinia, Vue Router 4, Tailwind 3, Vitest 3 with jsdom. There is no `@vue/test-utils`: specs mount with `createApp`.

**Spec:** `docs/superpowers/specs/2026-09-23-approve-reject-event-design.md`

## Global Constraints

- Branch `feature/scrum-34-52-approve-reject`. Never commit to `main`. Stage files by name. Commit messages use the `feat(events): …` or `test(events): …` style, with a *why* body citing SCRUM-34 / SCRUM-52, and no attribution lines.
- **Authorise by the session's active role:** `require_roles([...])` / `CurrentUser.role` in the API, and `private.current_user_role()` in RLS. Never `user_roles`, `CurrentUser.roles` or `profiles.role`.
- Wrong active role → **403**. Unknown event → **404**. Coordinator not assigned → **403**. Organiser who doesn't own the event → **404** (unchanged).
- Blocked transition → **409** with the exact detail `Cannot <action> an event that is <status with underscores as spaces>`, e.g. `Cannot approve an event that is under review` (LC-R1, no trailing period).
- Lost optimistic-lock race → **409** `This event was updated by someone else. Reload.` (IM-R3).
- Rejection reason: stripped. Blank or whitespace-only → 422. Max **1000** characters, labelled **[Assumption]**.
- Notification text:
  - Approve: `Your event "<name>" passed its initial review and is now in planning.`
  - Reject: `Your event "<name>" was rejected: <reason>`
  - Recipient: the organiser only, and never the actor (NT-R1).
- Endpoints that call Supabase are plain `def`, not `async def`.
- New HTTP exceptions go in `app/core/exceptions.py`.
- Every status shown in the UI comes from `STATUS_LABELS` (`features/events/dashboard.js`). Only `confirmed` may read as "approved".
- Frontend domain stores go in `features/events/`, not `stores/`.
- Occupying venue booking statuses are `held`, `approved`, `re_review`. Rejection sets them to `released`.
- Seeded ids:
  - Organiser Olivia Tan: `a0000000-0000-4000-8000-000000000001`
  - Coordinator Marcus Lim: `a0000000-0000-4000-8000-000000000002`
  - Password for every seeded account: `Cs1234`

---

## File map

| File | Responsibility |
|---|---|
| `supabase/migrations/20260923120000_event_review_history_and_notifications.sql` (new) | `event_status_history`, `notifications`, RLS, `transition_event` RPC |
| `supabase/verification/event_review_checks.sql` (new) | Structural and behavioural checks run against the live DB |
| `supabase/seed.sql` (modify) | Review fixtures: an `under_review` event and a `planning` event (with a held booking), both assigned to Marcus |
| `backend/app/core/exceptions.py` (modify) | `EventTransitionError` (409), `NotAssignedCoordinatorError` (403) |
| `backend/app/modules/events/lifecycle.py` (new) | Pure transition table: `TRANSITIONS`, `allowed_from`, `target` |
| `backend/app/modules/events/schemas.py` (modify) | `EventRejectRequest`, `HistoryActor`, `EventHistoryEntry`, `EventHistoryResponse` |
| `backend/app/modules/events/repository.py` (modify) | `transition_event` (RPC wrapper), `list_status_history` |
| `backend/app/modules/events/service.py` (modify) | `approve`, `reject`, `history`, a role-aware `read`, `_assigned_event`, `_visible_event` |
| `backend/app/modules/events/router.py` (modify) | `POST /{id}/approve`, `POST /{id}/reject`, `GET /{id}/history`, broadened `GET /{id}` |
| `backend/tests/test_event_lifecycle.py` (new) | Pure lifecycle tests |
| `backend/tests/test_event_review_api.py` (new) | API tests for approve, reject, history and the coordinator read |
| `frontend/src/services/api.js` (modify) | `eventsApi.approve`, `reject`, `history` |
| `frontend/src/features/events/eventReviewStore.js` (new) | `useEventReviewStore`, `canApprove`, `canReject`, `REJECT_REASON_MAX_LENGTH` |
| `frontend/src/components/events/RejectEventModal.vue` (new) | Required-reason modal |
| `frontend/src/components/events/EventStatusHistory.vue` (new) | Newest-first history list |
| `frontend/src/views/events/CoordinatorEventView.vue` (new) | Coordinator review page |
| `frontend/src/router/index.js` (modify) | Route `coordinator-event` at `/coordinator/events/:id` |
| `frontend/src/views/events/EventDetailView.vue` (modify) | Rejection reason and history for the organiser |
| Specs under `frontend/src/**/__tests__/` | See each task |
| Docs | `IMPLEMENTATION_MAP.md`, `SCENARIO.md` §4, `TEST_CASES.md`, `REQUIREMENTS.md` |

---

### Task 1: Database: history, notifications, `transition_event` RPC, review fixtures

**Files:**
- Create: `supabase/verification/event_review_checks.sql`
- Create: `supabase/migrations/20260923120000_event_review_history_and_notifications.sql`
- Modify: `supabase/seed.sql` (append a section after the SCRUM-39 venue bookings insert)

**Interfaces:**
- Produces: the RPC `public.transition_event(p_event_id uuid, p_actor_id uuid, p_from_statuses text[], p_to_status text, p_expected_version integer, p_reason text default null, p_notify_type text default null, p_notify_message text default null) returns setof public.events`. It returns an empty set when the event isn't at `p_expected_version` or isn't in one of `p_from_statuses`.
- Produces: the FK name `event_status_history_actor_id_fkey`, used by the PostgREST embed in Task 3.
- Produces: fixture events `e0000000-0000-4000-8000-000000000201` (`under_review`) and `…0202` (`planning`, with held booking `d0000000-0000-4000-8000-000000000201`), both with `coordinator_id = a0000000-…0002`.

- [ ] **Step 1: Write the failing verification script**

`supabase/verification/event_review_checks.sql`:
```sql
-- SCRUM-34 / SCRUM-52: status history, notifications and transition_event.
-- Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`. Every row
-- should read `ok = true`. The behavioural block runs inside a transaction that
-- is rolled back, so it leaves no trace.

select 'event_status_history exists' as check, to_regclass('public.event_status_history') is not null as ok
union all
select 'notifications exists', to_regclass('public.notifications') is not null
union all
select 'RLS on event_status_history', relrowsecurity from pg_class where oid = 'public.event_status_history'::regclass
union all
select 'RLS on notifications', relrowsecurity from pg_class where oid = 'public.notifications'::regclass
union all
select 'transition_event exists', to_regprocedure(
    'public.transition_event(uuid, uuid, text[], text, integer, text, text, text)') is not null
union all
select 'authenticated cannot execute transition_event', not has_function_privilege(
    'authenticated', 'public.transition_event(uuid, uuid, text[], text, integer, text, text, text)', 'execute')
union all
select 'anon cannot execute transition_event', not has_function_privilege(
    'anon', 'public.transition_event(uuid, uuid, text[], text, integer, text, text, text)', 'execute')
union all
select 'service_role can execute transition_event', has_function_privilege(
    'service_role', 'public.transition_event(uuid, uuid, text[], text, integer, text, text, text)', 'execute');
```

- [ ] **Step 2: Run it and confirm it fails**

Run it through the Supabase MCP `execute_sql` (or `psql`).
Expected: an error `function public.transition_event… does not exist`, or rows with `ok = false`, because nothing exists yet.

- [ ] **Step 3: Write the migration**

`supabase/migrations/20260923120000_event_review_history_and_notifications.sql`:
```sql
-- =============================================================================
-- ConnectSphere - SCRUM-34 (approve) and SCRUM-52 (reject)
--
-- event_status_history: every lifecycle transition, visible in the UI (LC-R2, QA-70).
-- notifications: in-app notices, written here; delivery UI is SCRUM-27 (69, 53).
-- transition_event: the one place a lifecycle transition is written, so the
-- status change, its history row, any hold release and the notification commit
-- together (NT-R3). Called by the API through .rpc() (ADR-0002). Reused by
-- SCRUM-12 and SCRUM-33 for their transitions.
-- =============================================================================

create table public.event_status_history (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null,
    from_status public.event_status null,
    to_status public.event_status not null,
    actor_id uuid null,
    reason text null,
    at timestamptz not null default now(),
    constraint event_status_history_event_id_fkey
        foreign key (event_id) references public.events (id) on delete cascade,
    constraint event_status_history_actor_id_fkey
        foreign key (actor_id) references public.profiles (id) on delete set null
);

comment on table public.event_status_history is
    'Append-only record of every event status transition (LC-R2). Written only by public.transition_event.';

create index event_status_history_event_at_idx on public.event_status_history (event_id, at desc);
create index event_status_history_actor_id_idx on public.event_status_history (actor_id);

create table public.notifications (
    id uuid primary key default gen_random_uuid(),
    recipient_id uuid not null references public.profiles (id) on delete cascade,
    event_id uuid null references public.events (id) on delete cascade,
    type text not null,
    message text not null,
    read_at timestamptz null,
    created_at timestamptz not null default now(),
    constraint notifications_type_not_blank check (length(btrim(type)) > 0),
    constraint notifications_message_not_blank check (length(btrim(message)) > 0)
);

comment on table public.notifications is
    'In-app notifications (REQUIREMENTS 6.20). The actor is never a recipient of their own action (NT-R1).';

create index notifications_recipient_unread_idx on public.notifications (recipient_id, read_at, created_at desc);
create index notifications_event_id_idx on public.notifications (event_id);

alter table public.event_status_history enable row level security;
alter table public.notifications enable row level security;

-- Safety net only: the API uses the secret key. The organiser acting as
-- organiser, or the assigned coordinator acting as coordinator, may read.
create policy "event_status_history_select_owner_or_assigned_coordinator"
    on public.event_status_history
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.events e
            where e.id = event_status_history.event_id
              and (
                  (e.organiser_id = (select auth.uid())
                   and (select private.current_user_role()) = 'event_organiser')
                  or (e.coordinator_id = (select auth.uid())
                      and (select private.current_user_role()) = 'event_coordinator')
              )
        )
    );

create policy "notifications_select_own"
    on public.notifications
    for select
    to authenticated
    using (recipient_id = (select auth.uid()));

create or replace function public.transition_event(
    p_event_id uuid,
    p_actor_id uuid,
    p_from_statuses text[],
    p_to_status text,
    p_expected_version integer,
    p_reason text default null,
    p_notify_type text default null,
    p_notify_message text default null
)
returns setof public.events
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_before public.events;
    v_after public.events;
begin
    select *
      into v_before
      from public.events
     where id = p_event_id
       and version = p_expected_version
       and status::text = any (p_from_statuses)
       for update;

    if not found then
        return;
    end if;

    update public.events
       set status = p_to_status::public.event_status,
           version = version + 1
     where id = p_event_id
    returning * into v_after;

    insert into public.event_status_history (event_id, from_status, to_status, actor_id, reason)
    values (p_event_id, v_before.status, v_after.status, p_actor_id, nullif(btrim(p_reason), ''));

    -- A rejected event must stop occupying its venue (QA2-13). Equipment
    -- reservations are released here too once SCRUM-24 builds reserving.
    if v_after.status = 'rejected' then
        update public.venue_bookings
           set status = 'released'
         where event_id = p_event_id
           and status in ('held', 'approved', 're_review');
    end if;

    if p_notify_type is not null and v_after.organiser_id is distinct from p_actor_id then
        insert into public.notifications (recipient_id, event_id, type, message)
        values (v_after.organiser_id, p_event_id, p_notify_type, p_notify_message);
    end if;

    return next v_after;
end;
$$;

comment on function public.transition_event is
    'Atomically moves an event between lifecycle statuses, records history, releases venue holds on rejection, and notifies the organiser (never the actor). API-only.';

revoke execute on function public.transition_event(uuid, uuid, text[], text, integer, text, text, text)
    from public, anon, authenticated;
grant execute on function public.transition_event(uuid, uuid, text[], text, integer, text, text, text)
    to service_role;
```

- [ ] **Step 4: Append the review fixtures to `supabase/seed.sql`**

Append at the end of the file:
```sql
-- =============================================================================
-- SCRUM-34 / SCRUM-52: requests assigned to Marcus Lim (coordinator) so approve
-- and reject can be exercised before SCRUM-12's auto-assignment exists. 0202 is
-- in planning with a held booking, to show rejection releasing it (QA2-13).
-- =============================================================================

insert into public.events (
    id, organiser_id, coordinator_id, status, name, purpose, starts_at, ends_at,
    expected_attendance, layout_preference, submitted_at
)
values
    ('e0000000-0000-4000-8000-000000000201', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'under_review', 'Review Fixture: Partner Summit',
     'Approve/reject fixture', '2026-11-12 10:00+08', '2026-11-12 12:00+08', 12, 'boardroom', now()),
    ('e0000000-0000-4000-8000-000000000202', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'planning', 'Review Fixture: Year-End Dinner',
     'Approve/reject fixture', '2026-11-13 10:00+08', '2026-11-13 12:00+08', 12, 'boardroom', now())
on conflict (id) do nothing;

insert into public.venue_bookings (id, event_id, venue_id, occupied_period, status, created_at)
values
    ('d0000000-0000-4000-8000-000000000201', 'e0000000-0000-4000-8000-000000000202',
     'b0000000-0000-4000-8000-000000000004', tstzrange('2026-11-13 10:00+08', '2026-11-13 12:00+08', '[)'),
     'held', now())
on conflict (id) do nothing;
```

- [ ] **Step 5: Apply to the live project** (shared DB; this is the approved spec's step)

From the repo root, run `supabase migration list --linked`. Every local file must show a matching remote version before pushing (PROJECT_REVIEW D8 migration drift). Then run `supabase db push`.
If the CLI isn't linked on this machine, use the Supabase MCP `apply_migration` with name `event_review_history_and_notifications`. Then rename its ledger row to `20260923120000`, as was done for `20260920100000` (IMPLEMENTATION_MAP §4):
```sql
update supabase_migrations.schema_migrations set version = '20260923120000'
 where name = 'event_review_history_and_notifications';
```
Then run the Step 4 fixture SQL through MCP `execute_sql`, so the live DB has the fixtures.

- [ ] **Step 6: Re-run the verification script and confirm every row is `ok = true`**

Then run this behavioural check, which rolls back:
```sql
begin;
select status, version from public.transition_event(
  'e0000000-0000-4000-8000-000000000202', 'a0000000-0000-4000-8000-000000000002',
  array['under_review','planning'], 'rejected',
  (select version from public.events where id = 'e0000000-0000-4000-8000-000000000202'),
  '  Venue unavailable  ', 'event_rejected', 'Your event "Review Fixture: Year-End Dinner" was rejected: Venue unavailable');
select to_status, reason from public.event_status_history where event_id = 'e0000000-0000-4000-8000-000000000202';
select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000000201';
select recipient_id, type from public.notifications where event_id = 'e0000000-0000-4000-8000-000000000202';
rollback;
```
Expected:
- `rejected` with the version bumped
- a history row with `reason = 'Venue unavailable'` (trimmed)
- the booking now `released`
- one notification to `a0000000-…0001`

Also run the MCP `get_advisors` for security and for performance. There must be no new advisory on the two tables or the function.

- [ ] **Step 7: Commit**

```bash
git add supabase/migrations/20260923120000_event_review_history_and_notifications.sql supabase/verification/event_review_checks.sql supabase/seed.sql
git commit -m "feat(events): add status history, notifications and transition_event RPC

SCRUM-34/SCRUM-52 need approve and reject to change the status, record who did
it (QA-70) and notify the organiser as one unit (NT-R3). PostgREST cannot span
tables in one transaction, so a service_role-only SQL function does all three
writes, and releases venue holds when an event is rejected (QA2-13)."
```

---

### Task 2: Pure lifecycle and transition exceptions

**Files:**
- Create: `backend/app/modules/events/lifecycle.py`
- Modify: `backend/app/core/exceptions.py` (append two classes)
- Test: `backend/tests/test_event_lifecycle.py`

**Interfaces:**
- Produces: `lifecycle.TRANSITIONS: dict[str, tuple[frozenset[EventStatus], EventStatus]]`, `lifecycle.allowed_from(action: str) -> list[str]` (sorted status values), and `lifecycle.target(action: str, current: str | EventStatus) -> EventStatus`, which raises `EventTransitionError`.
- Produces: `EventTransitionError(action: str, current_status: str)` → 409 with detail `Cannot {action} an event that is {status with spaces}`. `NotAssignedCoordinatorError()` → 403 with detail `Only the event's assigned coordinator can do this.`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_event_lifecycle.py`:
```python
"""The event lifecycle table for SCRUM-34 (approve) and SCRUM-52 (reject), REQUIREMENTS §5."""

import pytest

from app.core.exceptions import EventTransitionError
from app.modules.events import lifecycle
from app.modules.events.schemas import EventStatus

ALL_STATUSES = [status.value for status in EventStatus]


def test_approve_moves_under_review_to_planning():
    assert lifecycle.target("approve", "under_review") == EventStatus.planning


@pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s != "under_review"])
def test_approve_is_blocked_from_every_other_status(status):
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target("approve", status)

    assert raised.value.status_code == 409
    assert raised.value.detail == f"Cannot approve an event that is {status.replace('_', ' ')}"


@pytest.mark.parametrize("status", ["under_review", "planning"])
def test_reject_is_allowed_before_confirmation(status):
    assert lifecycle.target("reject", status) == EventStatus.rejected


@pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s not in ("under_review", "planning")])
def test_reject_is_blocked_from_every_other_status(status):
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target("reject", status)

    assert raised.value.status_code == 409
    assert raised.value.detail == f"Cannot reject an event that is {status.replace('_', ' ')}"


def test_target_accepts_the_enum_as_well_as_its_value():
    assert lifecycle.target("approve", EventStatus.under_review) == EventStatus.planning


def test_allowed_from_lists_source_statuses_for_the_rpc():
    assert lifecycle.allowed_from("approve") == ["under_review"]
    assert lifecycle.allowed_from("reject") == ["planning", "under_review"]


def test_the_blocked_message_names_the_status_in_words():
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target("approve", "returned")

    assert raised.value.detail == "Cannot approve an event that is returned"
```

- [ ] **Step 2: Run it and confirm it fails**

Run from `backend/`: `pytest tests/test_event_lifecycle.py -v`
Expected: collection error `ImportError: cannot import name 'EventTransitionError' from 'app.core.exceptions'`.

- [ ] **Step 3: Implement**

Append to `backend/app/core/exceptions.py`:
```python
class EventTransitionError(HTTPException):
    """A lifecycle action the event's current status does not allow (LC-R1)."""

    def __init__(self, action: str, current_status: str) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot {action} an event that is {current_status.replace('_', ' ')}",
        )


class NotAssignedCoordinatorError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the event's assigned coordinator can do this.",
        )
```

Create `backend/app/modules/events/lifecycle.py`:
```python
"""Which lifecycle actions each event status allows (REQUIREMENTS §5). Pure: no I/O.

One row per coordinator action. SCRUM-12 (assign) and SCRUM-33 (return,
resubmit) add their rows here rather than checking statuses inline.
"""

from app.core.exceptions import EventTransitionError
from app.modules.events.schemas import EventStatus

TRANSITIONS: dict[str, tuple[frozenset[EventStatus], EventStatus]] = {
    # Initial feasibility decision, not confirmation (SCRUM-34, QA2-8).
    "approve": (frozenset({EventStatus.under_review}), EventStatus.planning),
    # Only before confirmation; a confirmed event is cancelled instead (QA2-6).
    "reject": (frozenset({EventStatus.under_review, EventStatus.planning}), EventStatus.rejected),
}


def allowed_from(action: str) -> list[str]:
    sources, _ = TRANSITIONS[action]
    return sorted(status.value for status in sources)


def target(action: str, current: str | EventStatus) -> EventStatus:
    sources, destination = TRANSITIONS[action]
    current_status = EventStatus(current)
    if current_status not in sources:
        raise EventTransitionError(action, current_status.value)
    return destination
```

- [ ] **Step 4: Run and confirm it passes**

Run: `pytest tests/test_event_lifecycle.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/events/lifecycle.py backend/app/core/exceptions.py backend/tests/test_event_lifecycle.py
git commit -m "feat(events): add lifecycle table for approve and reject

SCRUM-34/SCRUM-52: one pure table decides which statuses allow each action, so
blocked transitions answer 409 'Cannot <action> an event that is <status>'
(LC-R1) consistently, and SCRUM-12/33 extend the table instead of re-checking."
```

---

### Task 3: Approve and reject endpoints

**Files:**
- Modify: `backend/app/modules/events/schemas.py`, `repository.py`, `service.py`, `router.py`
- Test: `backend/tests/test_event_review_api.py`

**Interfaces:**
- Consumes: `lifecycle.target`, `lifecycle.allowed_from`, `EventTransitionError`, `NotAssignedCoordinatorError`, and the Task 1 RPC.
- Produces:
  - `repository.transition_event(event_id: str, actor_id: str, from_statuses: list[str], to_status: str, expected_version: int, reason: str | None = None, notify_type: str | None = None, notify_message: str | None = None) -> dict | None`
  - `service.approve(event_id: str, coordinator_id: str) -> EventResponse`
  - `service.reject(event_id: str, coordinator_id: str, reason: str) -> EventResponse`
  - `service._assigned_event(event_id: str, coordinator_id: str) -> dict`
  - `schemas.EventRejectRequest {reason: str}`
  - Routes `POST /api/v1/events/{event_id}/approve` and `POST /api/v1/events/{event_id}/reject`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_event_review_api.py`:
```python
"""SCRUM-34 approve and SCRUM-52 reject, through the HTTP API with the repository mocked."""

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.modules.events import repository
from tests.conftest import make_table_mock

ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_COORDINATOR_ID = "a0000000-0000-4000-8000-000000000009"
EVENT_ID = "e0000000-0000-4000-8000-000000000201"
MISSING_EVENT_ID = "e0000000-0000-4000-8000-0000000009ff"
ALL_STATUSES = ["draft", "submitted", "under_review", "returned", "planning",
                "confirmed", "rejected", "cancelled", "completed"]


def event_row(status="under_review", coordinator_id=COORDINATOR_ID):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": coordinator_id,
        "status": status, "event_timezone": "Asia/Singapore", "name": "Partner Summit",
        "purpose": "Quarterly partner meeting", "description": None,
        "starts_at": "2026-11-12T10:00:00+08:00", "ends_at": "2026-11-12T12:00:00+08:00",
        "expected_attendance": 12, "layout_preference": "boardroom", "facilities_required": [],
        "accessibility_needs": None, "preliminary_equipment_needs": None,
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "technical_readiness": "not_required", "submitted_at": now, "version": 3,
        "created_at": now, "updated_at": now,
    }


@pytest.fixture()
def events(monkeypatch):
    """An in-memory events table plus a fake transition_event with the RPC's guards."""
    store = {EVENT_ID: event_row()}
    calls = []

    def get_event(event_id):
        return deepcopy(store.get(event_id))

    def transition_event(event_id, actor_id, from_statuses, to_status, expected_version,
                         reason=None, notify_type=None, notify_message=None):
        calls.append({
            "event_id": event_id, "actor_id": actor_id, "from_statuses": from_statuses,
            "to_status": to_status, "expected_version": expected_version, "reason": reason,
            "notify_type": notify_type, "notify_message": notify_message,
        })
        row = store.get(event_id)
        if row is None or row["version"] != expected_version or row["status"] not in from_statuses:
            return None
        row.update(status=to_status, version=row["version"] + 1)
        return deepcopy(row)

    monkeypatch.setattr(repository, "get_event", get_event)
    monkeypatch.setattr(repository, "transition_event", transition_event)
    return {"store": store, "calls": calls}


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role, user_id=COORDINATOR_ID):
        return authenticate_as(role, user_id=user_id)
    return _act_as


def approve(client, auth_headers, event_id=EVENT_ID):
    return client.post(f"/api/v1/events/{event_id}/approve", headers=auth_headers)


def reject(client, auth_headers, reason="Venue unavailable on that date", event_id=EVENT_ID):
    return client.post(f"/api/v1/events/{event_id}/reject", json={"reason": reason}, headers=auth_headers)


class TestApprove:
    def test_assigned_coordinator_moves_under_review_event_to_planning(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        response = approve(client, auth_headers)

        assert response.status_code == 200
        assert response.json()["status"] == "planning"
        [call] = events["calls"]
        assert call["actor_id"] == COORDINATOR_ID
        assert call["from_statuses"] == ["under_review"]
        assert call["to_status"] == "planning"
        assert call["expected_version"] == 3
        assert call["reason"] is None

    def test_approval_notifies_the_organiser(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        approve(client, auth_headers)

        [call] = events["calls"]
        assert call["notify_type"] == "event_approved"
        assert call["notify_message"] == 'Your event "Partner Summit" passed its initial review and is now in planning.'

    @pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s != "under_review"])
    def test_approve_is_blocked_unless_under_review(self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as("event_coordinator")

        response = approve(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Cannot approve an event that is {status.replace('_', ' ')}"
        assert events["calls"] == []

    def test_a_coordinator_who_is_not_assigned_is_forbidden(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", user_id=OTHER_COORDINATOR_ID)

        response = approve(client, auth_headers)

        assert response.status_code == 403
        assert events["calls"] == []

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, events, role):
        act_as(role)

        assert approve(client, auth_headers).status_code == 403
        assert events["calls"] == []

    def test_unknown_event_is_not_found(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        assert approve(client, auth_headers, event_id=MISSING_EVENT_ID).status_code == 404

    def test_a_lost_race_is_a_conflict(self, client, auth_headers, act_as, events, monkeypatch):
        monkeypatch.setattr(repository, "transition_event", lambda *args, **kwargs: None)
        act_as("event_coordinator")

        response = approve(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "This event was updated by someone else. Reload."


class TestReject:
    @pytest.mark.parametrize("status", ["under_review", "planning"])
    def test_assigned_coordinator_rejects_before_confirmation(self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as("event_coordinator")

        response = reject(client, auth_headers, reason="  Venue unavailable on that date  ")

        assert response.status_code == 200
        assert response.json()["status"] == "rejected"
        [call] = events["calls"]
        assert call["from_statuses"] == ["planning", "under_review"]
        assert call["to_status"] == "rejected"
        assert call["reason"] == "Venue unavailable on that date"
        assert call["notify_type"] == "event_rejected"
        assert call["notify_message"] == 'Your event "Partner Summit" was rejected: Venue unavailable on that date'

    @pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s not in ("under_review", "planning")])
    def test_reject_is_blocked_outside_under_review_and_planning(self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as("event_coordinator")

        response = reject(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Cannot reject an event that is {status.replace('_', ' ')}"
        assert events["calls"] == []

    @pytest.mark.parametrize("reason", ["", "   ", "\n\t "])
    def test_a_blank_reason_is_rejected(self, client, auth_headers, act_as, events, reason):
        act_as("event_coordinator")

        assert reject(client, auth_headers, reason=reason).status_code == 422
        assert events["calls"] == []

    def test_a_missing_reason_is_rejected(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        response = client.post(f"/api/v1/events/{EVENT_ID}/reject", json={}, headers=auth_headers)

        assert response.status_code == 422
        assert events["calls"] == []

    def test_a_reason_over_1000_characters_is_rejected(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        assert reject(client, auth_headers, reason="x" * 1001).status_code == 422
        assert reject(client, auth_headers, reason="x" * 1000).status_code == 200

    def test_a_coordinator_who_is_not_assigned_is_forbidden(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", user_id=OTHER_COORDINATOR_ID)

        assert reject(client, auth_headers).status_code == 403
        assert events["calls"] == []

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, events, role):
        act_as(role)

        assert reject(client, auth_headers).status_code == 403
        assert events["calls"] == []


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_a_coordinator_acting_as_venue_staff_is_forbidden(client, auth_headers, monkeypatch, events, action):
    """SCRUM-76: holding the coordinator role is not enough; the session must be acting as it."""
    profile = {
        "id": COORDINATOR_ID, "email": "coordinator@connectsphere.dev", "full_name": "Marcus Lim",
        "role": "event_coordinator", "organisation_name": None, "department": None, "phone_number": None,
    }
    anon_client = MagicMock()
    anon_client.auth.get_claims.return_value = {"claims": {
        "sub": COORDINATOR_ID, "aud": "authenticated", "email": profile["email"],
        "session_id": "22222222-2222-2222-2222-222222222222",
    }}
    monkeypatch.setattr("app.core.security.get_supabase_anon_client", lambda: anon_client)
    monkeypatch.setattr(
        "app.core.security.get_supabase_admin_client",
        lambda: make_table_mock(profile, session_active_role={"role": "venue_staff"}),
    )

    response = client.post(f"/api/v1/events/{EVENT_ID}/{action}", json={"reason": "No venue"}, headers=auth_headers)

    assert response.status_code == 403
    assert events["calls"] == []
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `pytest tests/test_event_review_api.py -v`
Expected: FAIL. The fixture's `monkeypatch.setattr(repository, "transition_event", …)` raises `AttributeError: … has no attribute 'transition_event'`.

- [ ] **Step 3: Implement**

`schemas.py`: append the following (`field_validator` and `Field` are already imported):
```python
REJECT_REASON_MAX_LENGTH = 1000  # [Assumption] REQUIREMENTS §9; no customer limit given


class EventRejectRequest(BaseModel):
    reason: str = Field(max_length=REJECT_REASON_MAX_LENGTH)

    @field_validator("reason")
    @classmethod
    def reason_is_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("A rejection reason is required.")
        return stripped
```

`repository.py`: append:
```python
def transition_event(
    event_id: str,
    actor_id: str,
    from_statuses: list[str],
    to_status: str,
    expected_version: int,
    reason: str | None = None,
    notify_type: str | None = None,
    notify_message: str | None = None,
) -> dict | None:
    """Run `public.transition_event`: status, history, hold release and notification in
    one transaction. Returns the updated row, or None when the event had moved on
    (another version or status), which the service reports as 409."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "transition_event",
            {
                "p_event_id": event_id,
                "p_actor_id": actor_id,
                "p_from_statuses": from_statuses,
                "p_to_status": to_status,
                "p_expected_version": expected_version,
                "p_reason": reason,
                "p_notify_type": notify_type,
                "p_notify_message": notify_message,
            },
        )
        .execute()
    )
    rows = response.data or [] if response else []
    return rows[0] if rows else None
```

`service.py`:
- Change the imports to add `from app.core.exceptions import NotAssignedCoordinatorError` and `from app.modules.events import lifecycle, repository`.
- Add `EventRejectRequest` to the schemas import.
- Add below `_owned_event`:
```python
STALE_EVENT_MESSAGE = "This event was updated by someone else. Reload."


def _assigned_event(event_id: str, coordinator_id: str) -> dict:
    """The event, if the caller is its assigned coordinator. Unlike `_owned_event`,
    a coordinator who isn't assigned gets 403, not 404: coordinators may already
    search every non-draft event (QA-87), so the 403 confirms nothing new, and
    SCRUM-34/52 name the case Forbidden."""
    row = repository.get_event(event_id)
    if not row:
        raise EventNotFoundError()
    if row.get("coordinator_id") != coordinator_id:
        raise NotAssignedCoordinatorError()
    return row


def _transition(row: dict, actor_id: str, action: str, *, reason: str | None,
                notify_type: str, notify_message: str) -> EventResponse:
    to_status = lifecycle.target(action, row["status"])
    updated = repository.transition_event(
        row["id"], actor_id, lifecycle.allowed_from(action), to_status.value, row["version"],
        reason=reason, notify_type=notify_type, notify_message=notify_message,
    )
    if not updated:
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return _to_response(updated)


def approve(event_id: str, coordinator_id: str) -> EventResponse:
    row = _assigned_event(event_id, coordinator_id)
    return _transition(
        row, coordinator_id, "approve", reason=None, notify_type="event_approved",
        notify_message=f'Your event "{row["name"]}" passed its initial review and is now in planning.',
    )


def reject(event_id: str, coordinator_id: str, reason: str) -> EventResponse:
    row = _assigned_event(event_id, coordinator_id)
    return _transition(
        row, coordinator_id, "reject", reason=reason, notify_type="event_rejected",
        notify_message=f'Your event "{row["name"]}" was rejected: {reason}',
    )
```

`router.py`:
- Import `EventRejectRequest`.
- Add `EventCoordinator = Annotated[CurrentUser, Depends(require_roles(["event_coordinator"]))]`.
- Append:
```python
@router.post("/{event_id}/approve", response_model=EventResponse)
def approve_event(event_id: UUID, current_user: EventCoordinator) -> EventResponse:
    return service.approve(str(event_id), current_user.id)


@router.post("/{event_id}/reject", response_model=EventResponse)
def reject_event(event_id: UUID, body: EventRejectRequest, current_user: EventCoordinator) -> EventResponse:
    return service.reject(str(event_id), current_user.id, body.reason)
```

- [ ] **Step 4: Run and confirm they pass**

Run: `pytest tests/test_event_review_api.py tests/test_event_lifecycle.py tests/test_active_role_access.py -v`
Expected: all PASS. The active-role matrix now includes both new routes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/events/schemas.py backend/app/modules/events/repository.py backend/app/modules/events/service.py backend/app/modules/events/router.py backend/tests/test_event_review_api.py
git commit -m "feat(events): let the assigned coordinator approve or reject a request

SCRUM-34 moves under_review to planning; SCRUM-52 rejects from under_review or
planning with a required, trimmed reason. Only the assigned coordinator acting
as coordinator may do either (403 otherwise), and both go through the
transition_event RPC so history and the organiser's notification commit with
the status change."
```

---

### Task 4: Status history endpoint and coordinator read of an event

**Files:**
- Modify: `backend/app/modules/events/schemas.py`, `repository.py`, `service.py`, `router.py`
- Test: `backend/tests/test_event_review_api.py` (append)

**Interfaces:**
- Consumes: `_assigned_event`, `_owned_event`.
- Produces:
  - `repository.list_status_history(event_id: str) -> list[dict]`. Each row: `id, from_status, to_status, reason, at, actor {id, full_name} | None`.
  - `service.read(event_id: str, user_id: str, role: str) -> EventResponse`
  - `service.history(event_id: str, user_id: str, role: str) -> EventHistoryResponse`
  - Routes: `GET /api/v1/events/{event_id}/history` and a broadened `GET /api/v1/events/{event_id}`
  - The response JSON is `{"entries": [{"id", "from_status", "to_status", "actor": {"id", "full_name"} | null, "reason", "at"}]}`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_event_review_api.py`:
```python
HISTORY_ROWS = [
    {"id": "h2", "from_status": "under_review", "to_status": "rejected", "reason": "Venue unavailable",
     "at": "2026-09-24T03:00:00+00:00", "actor": {"id": COORDINATOR_ID, "full_name": "Marcus Lim"}},
    {"id": "h1", "from_status": "submitted", "to_status": "under_review", "reason": None,
     "at": "2026-09-23T03:00:00+00:00", "actor": None},
]


@pytest.fixture()
def history(monkeypatch, events):
    monkeypatch.setattr(repository, "list_status_history", lambda event_id: deepcopy(HISTORY_ROWS))


class TestHistory:
    def test_the_owner_sees_the_history_newest_first(self, client, auth_headers, act_as, history):
        act_as("event_organiser", user_id=ORGANISER_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers)

        assert response.status_code == 200
        entries = response.json()["entries"]
        assert [entry["id"] for entry in entries] == ["h2", "h1"]
        assert entries[0]["reason"] == "Venue unavailable"
        assert entries[0]["actor"] == {"id": COORDINATOR_ID, "full_name": "Marcus Lim"}
        assert entries[1]["actor"] is None

    def test_the_assigned_coordinator_sees_the_history(self, client, auth_headers, act_as, history):
        act_as("event_coordinator")

        assert client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers).status_code == 200

    def test_another_organiser_gets_not_found(self, client, auth_headers, act_as, history):
        act_as("event_organiser", user_id="a0000000-0000-4000-8000-0000000000aa")

        assert client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers).status_code == 404

    def test_an_unassigned_coordinator_is_forbidden(self, client, auth_headers, act_as, history):
        act_as("event_coordinator", user_id=OTHER_COORDINATOR_ID)

        assert client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers).status_code == 403

    @pytest.mark.parametrize("role", ["venue_staff", "tech_support", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, history, role):
        act_as(role)

        assert client.get(f"/api/v1/events/{EVENT_ID}/history", headers=auth_headers).status_code == 403


class TestCoordinatorRead:
    def test_the_assigned_coordinator_can_read_the_event(self, client, auth_headers, act_as, events):
        act_as("event_coordinator")

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["id"] == EVENT_ID

    def test_an_unassigned_coordinator_is_forbidden(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", user_id=OTHER_COORDINATOR_ID)

        assert client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers).status_code == 403

    def test_the_owner_can_still_read_the_event(self, client, auth_headers, act_as, events):
        act_as("event_organiser", user_id=ORGANISER_ID)

        assert client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers).status_code == 200


def test_a_rejected_event_cannot_be_edited_by_its_organiser(client, auth_headers, act_as, events):
    """SCRUM-52: a rejected request is closed (QA-34, QA-95)."""
    events["store"][EVENT_ID]["status"] = "rejected"
    act_as("event_organiser", user_id=ORGANISER_ID)

    response = client.patch(f"/api/v1/events/{EVENT_ID}", json={"name": "Try again"}, headers=auth_headers)

    assert response.status_code == 409
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `pytest tests/test_event_review_api.py -v -k "History or CoordinatorRead or rejected_event"`
Expected: the `history` fixture raises `AttributeError: … no attribute 'list_status_history'`. `TestCoordinatorRead` coordinator cases get 403 from `require_roles(["event_organiser"])`, so `test_the_assigned_coordinator_can_read_the_event` fails. The rejected-edit test already passes (existing behaviour), which is expected: it pins the AC.

- [ ] **Step 3: Implement**

`schemas.py`: append:
```python
class HistoryActor(BaseModel):
    id: str
    full_name: str


class EventHistoryEntry(BaseModel):
    id: str
    from_status: EventStatus | None = None
    to_status: EventStatus
    actor: HistoryActor | None = None
    reason: str | None = None
    at: datetime


class EventHistoryResponse(BaseModel):
    entries: list[EventHistoryEntry]
```

`repository.py`: append:
```python
def list_status_history(event_id: str) -> list[dict]:
    """Newest first. The actor is embedded through the FK named in the migration."""
    response = (
        get_supabase_admin_client()
        .table("event_status_history")
        .select("id, from_status, to_status, reason, at, actor:profiles!event_status_history_actor_id_fkey(id, full_name)")
        .eq("event_id", event_id)
        .order("at", desc=True)
        .execute()
    )
    return response.data or []
```

`service.py`:
- Add `EventHistoryEntry, EventHistoryResponse` to the schemas import.
- Replace `read` and add `_visible_event` and `history`:
```python
def _visible_event(event_id: str, user_id: str, role: str) -> dict:
    """Organisers see their own events (404 otherwise); coordinators see the events
    assigned to them (403 otherwise). The router's role gate admits no one else."""
    if role == "event_coordinator":
        return _assigned_event(event_id, user_id)
    return _owned_event(event_id, user_id)


def read(event_id: str, user_id: str, role: str = "event_organiser") -> EventResponse:
    return _to_response(_visible_event(event_id, user_id, role))


def history(event_id: str, user_id: str, role: str) -> EventHistoryResponse:
    _visible_event(event_id, user_id, role)
    return EventHistoryResponse(
        entries=[EventHistoryEntry(**row) for row in repository.list_status_history(event_id)]
    )
```

`router.py`:
- Add `EventParticipant = Annotated[CurrentUser, Depends(require_roles(["event_organiser", "event_coordinator"]))]`.
- Import `EventHistoryResponse`.
- Change `read_event` to:
```python
@router.get("/{event_id}", response_model=EventResponse)
def read_event(event_id: UUID, current_user: EventParticipant) -> EventResponse:
    return service.read(str(event_id), current_user.id, current_user.role)


@router.get("/{event_id}/history", response_model=EventHistoryResponse)
def read_event_history(event_id: UUID, current_user: EventParticipant) -> EventHistoryResponse:
    return service.history(str(event_id), current_user.id, current_user.role)
```

- [ ] **Step 4: Run the full backend suite**

Run: `pytest` (from `backend/`)
Expected: all PASS, including `test_events_api.py`: organiser reads are unchanged, and `test_an_organiser_cannot_read_another_organisers_event` is still 404.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/events/schemas.py backend/app/modules/events/repository.py backend/app/modules/events/service.py backend/app/modules/events/router.py backend/tests/test_event_review_api.py
git commit -m "feat(events): serve status history and let the assigned coordinator read an event

SCRUM-34/52 require each decision, who made it and when to be visible in the UI
(QA-70), and the coordinator's review page needs to read the event it acts on.
Both are limited to the owner organiser and the assigned coordinator."
```

---

### Task 5: Frontend API and review store

**Files:**
- Modify: `frontend/src/services/api.js` (inside `eventsApi`)
- Create: `frontend/src/features/events/eventReviewStore.js`
- Test: `frontend/src/features/events/__tests__/eventReviewStore.spec.js`

**Interfaces:**
- Produces:
  - `eventsApi.approve(eventId, token)`, `eventsApi.reject(eventId, reason, token)`, `eventsApi.history(eventId, token)`
  - `canApprove(status) -> boolean`, `canReject(status) -> boolean`, `REJECT_REASON_MAX_LENGTH = 1000`
  - `useEventReviewStore()` with state `{ event, history, isLoading, isActing, error }` (`event` is the raw snake_case API response) and actions `load(eventId)`, `loadHistory(eventId)`, `approve()`, `reject(reason)`. `approve` and `reject` throw on failure after setting `error`.

- [ ] **Step 1: Write the failing test**

`frontend/src/features/events/__tests__/eventReviewStore.spec.js`:
```js
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { canApprove, canReject, REJECT_REASON_MAX_LENGTH, useEventReviewStore } from "@/features/events/eventReviewStore";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  eventsApi: { get: vi.fn(), history: vi.fn(), approve: vi.fn(), reject: vi.fn() },
}));

const EVENT = { id: "event-1", name: "Partner Summit", status: "under_review", version: 3 };
const ENTRY = { id: "h1", from_status: "under_review", to_status: "planning", actor: { id: "c1", full_name: "Marcus Lim" }, reason: null, at: "2026-09-24T03:00:00Z" };

function signedInCoordinator() {
  const auth = useAuthStore();
  auth.token = "access-token";
  auth.profile = { id: "c1", role: "event_coordinator", full_name: "Marcus Lim" };
}

describe("canApprove / canReject", () => {
  it("allows approve only from under_review (SCRUM-34)", () => {
    expect(canApprove("under_review")).toBe(true);
    for (const status of ["draft", "submitted", "returned", "planning", "confirmed", "rejected", "cancelled", "completed"]) {
      expect(canApprove(status)).toBe(false);
    }
  });

  it("allows reject from under_review or planning only (SCRUM-52)", () => {
    expect(canReject("under_review")).toBe(true);
    expect(canReject("planning")).toBe(true);
    for (const status of ["draft", "submitted", "returned", "confirmed", "rejected", "cancelled", "completed"]) {
      expect(canReject(status)).toBe(false);
    }
  });

  it("caps the reason at the API's 1000 characters", () => {
    expect(REJECT_REASON_MAX_LENGTH).toBe(1000);
  });
});

describe("useEventReviewStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    signedInCoordinator();
  });

  it("loads the event and its history", async () => {
    eventsApi.get.mockResolvedValue(EVENT);
    eventsApi.history.mockResolvedValue({ entries: [ENTRY] });
    const store = useEventReviewStore();

    await store.load("event-1");

    expect(eventsApi.get).toHaveBeenCalledWith("event-1", "access-token");
    expect(store.event).toEqual(EVENT);
    expect(store.history).toEqual([ENTRY]);
    expect(store.error).toBeNull();
  });

  it("approves, then shows the new status and refreshed history", async () => {
    eventsApi.get.mockResolvedValue(EVENT);
    eventsApi.history.mockResolvedValue({ entries: [] });
    const store = useEventReviewStore();
    await store.load("event-1");
    eventsApi.approve.mockResolvedValue({ ...EVENT, status: "planning", version: 4 });
    eventsApi.history.mockResolvedValue({ entries: [ENTRY] });

    await store.approve();

    expect(eventsApi.approve).toHaveBeenCalledWith("event-1", "access-token");
    expect(store.event.status).toBe("planning");
    expect(store.history).toEqual([ENTRY]);
    expect(store.isActing).toBe(false);
  });

  it("sends a trimmed reason when rejecting", async () => {
    eventsApi.get.mockResolvedValue(EVENT);
    eventsApi.history.mockResolvedValue({ entries: [] });
    const store = useEventReviewStore();
    await store.load("event-1");
    eventsApi.reject.mockResolvedValue({ ...EVENT, status: "rejected" });

    await store.reject("  Venue unavailable  ");

    expect(eventsApi.reject).toHaveBeenCalledWith("event-1", "Venue unavailable", "access-token");
    expect(store.event.status).toBe("rejected");
  });

  it("keeps the event and reports the API's message when an action fails", async () => {
    eventsApi.get.mockResolvedValue(EVENT);
    eventsApi.history.mockResolvedValue({ entries: [] });
    const store = useEventReviewStore();
    await store.load("event-1");
    eventsApi.approve.mockRejectedValue(new ApiError("Cannot approve an event that is returned", 409));

    await expect(store.approve()).rejects.toThrow("Cannot approve an event that is returned");

    expect(store.error).toBe("Cannot approve an event that is returned");
    expect(store.event.status).toBe("under_review");
    expect(store.isActing).toBe(false);
  });

  it("reports a load failure", async () => {
    eventsApi.get.mockRejectedValue(new ApiError("Only the event's assigned coordinator can do this.", 403));
    eventsApi.history.mockResolvedValue({ entries: [] });
    const store = useEventReviewStore();

    await store.load("event-1");

    expect(store.event).toBeNull();
    expect(store.error).toBe("Only the event's assigned coordinator can do this.");
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run from `frontend/`: `npx vitest run src/features/events/__tests__/eventReviewStore.spec.js`
Expected: FAIL with `Failed to resolve import "@/features/events/eventReviewStore"`.

- [ ] **Step 3: Implement**

`api.js`: add inside `eventsApi` after `submit`:
```js
  // SCRUM-34/52: the assigned coordinator's decisions, and the history they leave.
  approve(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/approve`, { method: "POST", token });
  },
  reject(eventId, reason, token) {
    return request(`/events/${encodeURIComponent(eventId)}/reject`, { method: "POST", body: { reason }, token });
  },
  history(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/history`, { token });
  },
```

`frontend/src/features/events/eventReviewStore.js`:
```js
import { defineStore } from "pinia";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// Mirrors the API's REJECT_REASON_MAX_LENGTH ([Assumption], REQUIREMENTS §9).
export const REJECT_REASON_MAX_LENGTH = 1000;

// Which buttons to offer. The API is the enforcement point (lifecycle.py); these
// only avoid offering an action that would answer 409.
export function canApprove(status) {
  return status === "under_review";
}

export function canReject(status) {
  return status === "under_review" || status === "planning";
}

/**
 * The event a coordinator is reviewing (SCRUM-34 approve, SCRUM-52 reject) and its
 * status history. `loadHistory` is also used by the organiser's event page.
 */
export const useEventReviewStore = defineStore("eventReview", {
  state: () => ({ event: null, history: [], isLoading: false, isActing: false, error: null }),

  actions: {
    async load(eventId) {
      const auth = useAuthStore();
      this.isLoading = true;
      this.error = null;
      try {
        const [event, history] = await Promise.all([
          auth.withSession((token) => eventsApi.get(eventId, token)),
          auth.withSession((token) => eventsApi.history(eventId, token)),
        ]);
        this.event = event;
        this.history = history?.entries ?? [];
      } catch (error) {
        this.event = null;
        this.history = [];
        this.error = error.message;
      } finally {
        this.isLoading = false;
      }
    },

    async loadHistory(eventId) {
      const auth = useAuthStore();
      const response = await auth.withSession((token) => eventsApi.history(eventId, token));
      this.history = response?.entries ?? [];
      return this.history;
    },

    async approve() {
      return this.act((token) => eventsApi.approve(this.event.id, token));
    },

    async reject(reason) {
      return this.act((token) => eventsApi.reject(this.event.id, reason.trim(), token));
    },

    async act(call) {
      const auth = useAuthStore();
      this.isActing = true;
      this.error = null;
      try {
        this.event = await auth.withSession(call);
        await this.loadHistory(this.event.id);
        return this.event;
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.isActing = false;
      }
    },
  },
});
```

- [ ] **Step 4: Run and confirm it passes**

Run: `npx vitest run src/features/events/__tests__/eventReviewStore.spec.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api.js frontend/src/features/events/eventReviewStore.js frontend/src/features/events/__tests__/eventReviewStore.spec.js
git commit -m "feat(events): add the review store for approving and rejecting requests

SCRUM-34/52: the coordinator's page and the organiser's page both need the
event's history, and the coordinator's decisions must refresh it. The store
keeps the API response as-is and offers only the actions the status allows."
```

---

### Task 6: `RejectEventModal` and `EventStatusHistory` components

**Files:**
- Create: `frontend/src/components/events/RejectEventModal.vue`
- Create: `frontend/src/components/events/EventStatusHistory.vue`
- Test: `frontend/src/components/events/__tests__/RejectEventModal.spec.js`, `frontend/src/components/events/__tests__/EventStatusHistory.spec.js`

**Interfaces:**
- Consumes: `REJECT_REASON_MAX_LENGTH` (Task 5), `STATUS_LABELS` (`features/events/dashboard.js`), `BauhausButton`.
- Produces:
  - `<RejectEventModal :open :event-name :busy :error @confirm="(reason: string) => …" @cancel>`. It emits `confirm` with the trimmed reason, and resets the text each time it opens.
  - `<EventStatusHistory :entries>`, where `entries` has the shape of the history API response.

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/events/__tests__/RejectEventModal.spec.js`:
```js
import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import RejectEventModal from "@/components/events/RejectEventModal.vue";

const mounted = [];

async function mountModal(props = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(RejectEventModal, { open: true, eventName: "Partner Summit", onConfirm, onCancel, ...props }),
  });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return { onConfirm, onCancel };
}

function typeReason(text) {
  const textarea = document.querySelector("textarea");
  textarea.value = text;
  textarea.dispatchEvent(new Event("input"));
  return nextTick();
}

const confirmButton = () => document.querySelector('button[aria-label="Reject request"]');

describe("RejectEventModal (SCRUM-52)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("names the event and asks for a reason", async () => {
    await mountModal();

    expect(document.body.textContent).toContain("Partner Summit");
    expect(document.querySelector("textarea").getAttribute("maxlength")).toBe("1000");
  });

  it("cannot be confirmed without a reason", async () => {
    await mountModal();

    expect(confirmButton().disabled).toBe(true);
  });

  it("cannot be confirmed with a whitespace-only reason", async () => {
    await mountModal();
    await typeReason("   \n  ");

    expect(confirmButton().disabled).toBe(true);
  });

  it("emits the trimmed reason on confirm", async () => {
    const { onConfirm } = await mountModal();
    await typeReason("  Venue unavailable on that date  ");

    confirmButton().click();

    expect(onConfirm).toHaveBeenCalledWith("Venue unavailable on that date");
  });

  it("shows how many characters are used", async () => {
    await mountModal();
    await typeReason("Venue unavailable");

    expect(document.body.textContent).toContain("17 / 1000");
  });

  it("is disabled while the request is in flight", async () => {
    await mountModal({ busy: true });
    await typeReason("Venue unavailable");

    expect(confirmButton().disabled).toBe(true);
  });

  it("shows the API's error", async () => {
    await mountModal({ error: "Cannot reject an event that is confirmed" });

    expect(document.querySelector('[role="alert"]').textContent).toContain("Cannot reject an event that is confirmed");
  });

  it("emits cancel", async () => {
    const { onCancel } = await mountModal();

    document.querySelector('button[aria-label="Cancel"]').click();

    expect(onCancel).toHaveBeenCalled();
  });
});
```

`frontend/src/components/events/__tests__/EventStatusHistory.spec.js`:
```js
import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import EventStatusHistory from "@/components/events/EventStatusHistory.vue";

const mounted = [];

async function mountHistory(entries) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(EventStatusHistory, { entries }) });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el;
}

describe("EventStatusHistory (QA-70)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("lists each change with its label, who made it, when and why", async () => {
    const el = await mountHistory([
      { id: "h2", from_status: "under_review", to_status: "rejected", reason: "Venue unavailable",
        at: "2026-09-24T06:05:00Z", actor: { id: "c1", full_name: "Marcus Lim" } },
      { id: "h1", from_status: "under_review", to_status: "planning", reason: null,
        at: "2026-09-23T03:00:00Z", actor: { id: "c1", full_name: "Marcus Lim" } },
    ]);

    const items = el.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain("Rejected");
    expect(items[0].textContent).toContain("Marcus Lim");
    expect(items[0].textContent).toContain("Venue unavailable");
    expect(items[0].textContent).toContain("24 Sept 2026");
    expect(items[1].textContent).toContain("Planning");
  });

  it("never calls planning 'approved' (QA2-8)", async () => {
    const el = await mountHistory([
      { id: "h1", from_status: "under_review", to_status: "planning", reason: null,
        at: "2026-09-23T03:00:00Z", actor: { id: "c1", full_name: "Marcus Lim" } },
    ]);

    expect(el.textContent.toLowerCase()).not.toContain("approved");
  });

  it("names a removed account honestly", async () => {
    const el = await mountHistory([
      { id: "h1", from_status: null, to_status: "under_review", reason: null, at: "2026-09-23T03:00:00Z", actor: null },
    ]);

    expect(el.textContent).toContain("Unknown user");
  });

  it("says so when there is no history yet", async () => {
    const el = await mountHistory([]);

    expect(el.textContent).toContain("No status changes recorded yet.");
  });
});
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `npx vitest run src/components/events`
Expected: FAIL with `Failed to resolve import "@/components/events/RejectEventModal.vue"`.

- [ ] **Step 3: Implement**

`frontend/src/components/events/RejectEventModal.vue`:
```vue
<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import { REJECT_REASON_MAX_LENGTH } from "@/features/events/eventReviewStore";

const props = defineProps({
  open: { type: Boolean, default: false },
  eventName: { type: String, required: true },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const emit = defineEmits(["confirm", "cancel"]);

const reason = ref("");
const trimmed = computed(() => reason.value.trim());
const canConfirm = computed(() => trimmed.value.length > 0 && !props.busy);

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) reason.value = "";
  },
);

function confirm() {
  if (canConfirm.value) emit("confirm", trimmed.value);
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="props.open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 px-4 py-6"
      role="presentation"
      @click.self="emit('cancel')"
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="reject-modal-title"
        class="w-full max-w-lg border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <h2 id="reject-modal-title" class="text-2xl font-black uppercase leading-tight tracking-tight">Reject this request?</h2>
        <p class="mt-4 text-base font-medium">
          "{{ props.eventName }}" will be closed and can't be resubmitted. The organiser will see your reason.
        </p>
        <label for="reject-reason" class="mt-6 block text-xs font-bold uppercase tracking-widest text-ink/70">Reason (required)</label>
        <textarea
          id="reject-reason"
          v-model="reason"
          rows="4"
          :maxlength="REJECT_REASON_MAX_LENGTH"
          class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
        ></textarea>
        <p class="mt-1 text-right text-xs font-bold text-ink/70">{{ reason.length }} / {{ REJECT_REASON_MAX_LENGTH }}</p>
        <p
          v-if="props.error"
          role="alert"
          class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas"
        >
          {{ props.error }}
        </p>
        <div class="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <BauhausButton type="button" variant="outline" aria-label="Cancel" @click="emit('cancel')">Cancel</BauhausButton>
          <BauhausButton type="button" variant="primary" aria-label="Reject request" :disabled="!canConfirm" @click="confirm">
            Reject request
          </BauhausButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
```

`frontend/src/components/events/EventStatusHistory.vue`:
```vue
<script setup>
import { STATUS_LABELS } from "@/features/events/dashboard";

defineProps({
  entries: { type: Array, required: true },
});

const formatter = new Intl.DateTimeFormat("en-SG", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Singapore",
});

function label(status) {
  return STATUS_LABELS[status] ?? status;
}
</script>

<template>
  <p v-if="!entries.length" class="text-sm font-medium text-ink/70">No status changes recorded yet.</p>
  <ol v-else class="space-y-4">
    <li v-for="entry in entries" :key="entry.id" class="border-l-4 border-ink pl-4">
      <p class="text-sm font-black uppercase tracking-wide">{{ label(entry.to_status) }}</p>
      <p class="text-xs font-bold text-ink/70">
        by {{ entry.actor?.full_name ?? "Unknown user" }} · {{ formatter.format(new Date(entry.at)) }}
      </p>
      <p v-if="entry.reason" class="mt-1 whitespace-pre-wrap text-sm font-medium">{{ entry.reason }}</p>
    </li>
  </ol>
</template>
```

- [ ] **Step 4: Run and confirm they pass**

Run: `npx vitest run src/components/events`
Expected: PASS. If the date assertion fails because of how ICU in Node renders "Sept" versus "Sep", assert against the output of `new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeZone: "Asia/Singapore" }).format(new Date("2026-09-24T06:05:00Z"))` computed in the test, instead of the literal string.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/events
git commit -m "feat(events): add reject-reason modal and status history list

SCRUM-52 requires a reason before rejecting, so the confirm stays disabled until
there is non-blank text; SCRUM-34/52 require the decision, actor and time to be
visible (QA-70), shown with the same status labels as the dashboards."
```

---

### Task 7: The coordinator review page and route

**Files:**
- Create: `frontend/src/views/events/CoordinatorEventView.vue`
- Modify: `frontend/src/router/index.js` (add a route after `dashboard-coordinator`)
- Test: `frontend/src/views/__tests__/CoordinatorEventView.spec.js`

**Interfaces:**
- Consumes: `useEventReviewStore`, `canApprove`, `canReject`, `RejectEventModal`, `EventStatusHistory`, `ConfirmModal`, `STATUS_LABELS`, `showToast`.
- Produces: the route `{ path: "/coordinator/events/:id", name: "coordinator-event", meta: { requiresAuth: true, allowedRoles: ["event_coordinator"] } }`.

- [ ] **Step 1: Write the failing test**

`frontend/src/views/__tests__/CoordinatorEventView.spec.js`:
```js
import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { get: vi.fn(), history: vi.fn(), approve: vi.fn(), reject: vi.fn() },
}));

function eventResponse(overrides = {}) {
  return {
    id: "event-1", name: "Partner Summit", status: "under_review", version: 3,
    event_timezone: "Asia/Singapore", purpose: "Quarterly partner meeting", description: null,
    starts_at: "2026-11-12T02:00:00Z", ends_at: "2026-11-12T04:00:00Z", expected_attendance: 12,
    layout_preference: "boardroom", facilities_required: [], accessibility_needs: null,
    preliminary_equipment_needs: null, coordinator_id: "c1", organiser_id: "o1",
    ...overrides,
  };
}

const mountedApps = [];

async function mountView(response) {
  eventsApi.get.mockResolvedValue(response);
  eventsApi.history.mockResolvedValue({ entries: [] });
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "c1", full_name: "Marcus Lim", role: "event_coordinator" };
  auth.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "coordinator-event", params: { id: response.id } });
  const { default: View } = await import("@/views/events/CoordinatorEventView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await vi.waitFor(() => expect(el.textContent).toContain(response.name));
  await nextTick();
  return el;
}

const button = (label) => document.querySelector(`button[aria-label="${label}"]`);

describe("CoordinatorEventView (SCRUM-34, SCRUM-52)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("offers approve and reject for a request under review", async () => {
    const el = await mountView(eventResponse());

    expect(el.textContent).toContain("Under review");
    expect(button("Approve request")).not.toBeNull();
    expect(button("Open reject dialog")).not.toBeNull();
  });

  it("offers only reject while planning", async () => {
    await mountView(eventResponse({ status: "planning" }));

    expect(button("Approve request")).toBeNull();
    expect(button("Open reject dialog")).not.toBeNull();
  });

  it.each(["returned", "confirmed", "rejected", "cancelled", "completed", "submitted"])(
    "offers no decision when the request is %s",
    async (status) => {
      await mountView(eventResponse({ status }));

      expect(button("Approve request")).toBeNull();
      expect(button("Open reject dialog")).toBeNull();
    },
  );

  it("approves after confirmation and shows Planning", async () => {
    const el = await mountView(eventResponse());
    eventsApi.approve.mockResolvedValue(eventResponse({ status: "planning", version: 4 }));

    button("Approve request").click();
    await nextTick();
    expect(document.body.textContent).toContain("This does not confirm the event");
    button("Approve").click();

    await vi.waitFor(() => expect(eventsApi.approve).toHaveBeenCalledWith("event-1", "access"));
    await vi.waitFor(() => expect(el.textContent).toContain("Planning"));
    expect(button("Approve request")).toBeNull();
  });

  it("rejects with the typed reason", async () => {
    const el = await mountView(eventResponse());
    eventsApi.reject.mockResolvedValue(eventResponse({ status: "rejected", version: 4 }));

    button("Open reject dialog").click();
    await nextTick();
    const textarea = document.querySelector("textarea");
    textarea.value = "Venue unavailable";
    textarea.dispatchEvent(new Event("input"));
    await nextTick();
    button("Reject request").click();

    await vi.waitFor(() => expect(eventsApi.reject).toHaveBeenCalledWith("event-1", "Venue unavailable", "access"));
    await vi.waitFor(() => expect(el.textContent).toContain("Rejected"));
  });

  it("shows why the page can't load", async () => {
    eventsApi.get.mockRejectedValue(Object.assign(new Error("Only the event's assigned coordinator can do this."), { status: 403 }));
    eventsApi.history.mockResolvedValue({ entries: [] });
    const pinia = createPinia();
    setActivePinia(pinia);
    const auth = useAuthStore();
    auth.token = "access";
    auth.profile = { id: "c9", full_name: "Other", role: "event_coordinator" };
    auth.sessionVerified = true;
    const { default: router } = await import("@/router");
    await router.push({ name: "coordinator-event", params: { id: "event-1" } });
    const { default: View } = await import("@/views/events/CoordinatorEventView.vue");
    const el = document.createElement("div");
    document.body.appendChild(el);
    const app = createApp(View).use(pinia).use(router);
    app.mount(el);
    mountedApps.push(app);

    await vi.waitFor(() => expect(el.querySelector('[role="alert"]').textContent).toContain("assigned coordinator"));
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/views/__tests__/CoordinatorEventView.spec.js`
Expected: FAIL with `No match for {"name":"coordinator-event",…}`, thrown by `router.push`.

- [ ] **Step 3: Implement**

`router/index.js`: insert after the `dashboard-coordinator` route:
```js
  {
    // SCRUM-34/52: the assigned coordinator's review page. SCRUM-49 extends it
    // with the full review details; the API enforces "assigned" (403 otherwise).
    path: "/coordinator/events/:id",
    name: "coordinator-event",
    component: () => import("@/views/events/CoordinatorEventView.vue"),
    meta: { requiresAuth: true, allowedRoles: ["event_coordinator"] },
  },
```

`frontend/src/views/events/CoordinatorEventView.vue`:
```vue
<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import ConfirmModal from "@/components/common/ConfirmModal.vue";
import EventStatusHistory from "@/components/events/EventStatusHistory.vue";
import RejectEventModal from "@/components/events/RejectEventModal.vue";
import { showToast } from "@/composables/useToast";
import { STATUS_LABELS } from "@/features/events/dashboard";
import { canApprove, canReject, useEventReviewStore } from "@/features/events/eventReviewStore";

const route = useRoute();
const router = useRouter();
const review = useEventReviewStore();

const isApproveOpen = ref(false);
const isRejectOpen = ref(false);

const event = computed(() => review.event);
const statusLabel = computed(() => STATUS_LABELS[event.value?.status] ?? event.value?.status);
const showApprove = computed(() => canApprove(event.value?.status));
const showReject = computed(() => canReject(event.value?.status));

function displayDateTime(value, timeZone) {
  if (!value) return "Not provided";
  return new Intl.DateTimeFormat("en-SG", { dateStyle: "full", timeStyle: "short", timeZone }).format(new Date(value));
}

function displayValue(value) {
  return value || "Not provided";
}

async function confirmApprove() {
  isApproveOpen.value = false;
  try {
    await review.approve();
    showToast("Request approved: now in Planning");
  } catch {
    // review.error is shown in the page's alert.
  }
}

async function confirmReject(reason) {
  try {
    await review.reject(reason);
    isRejectOpen.value = false;
    showToast("Request rejected");
  } catch {
    // Kept open so the coordinator sees the error beside their reason.
  }
}

onMounted(() => review.load(route.params.id));
</script>

<template>
  <main class="mx-auto max-w-6xl px-4 py-12 sm:px-8">
    <div class="mb-8 flex flex-wrap items-center justify-between gap-4">
      <BauhausButton variant="outline" @click="router.push({ name: 'dashboard-coordinator' })">Back to dashboard</BauhausButton>
      <p v-if="event" class="text-xs font-bold uppercase tracking-widest text-ink/70">Request {{ event.id }}</p>
    </div>

    <p
      v-if="review.error && !isRejectOpen"
      role="alert"
      class="mb-6 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold uppercase tracking-wide text-canvas shadow-hard sm:border-4"
    >
      {{ review.error }}
    </p>

    <template v-if="event">
      <BauhausCard background="yellow" accent="square" accent-color="bauhaus-red" class="mb-8">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p class="text-xs font-bold uppercase tracking-widest opacity-80">Event request</p>
            <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">{{ event.name }}</h1>
          </div>
          <p class="border-2 border-ink bg-canvas px-3 py-2 text-xs font-black uppercase tracking-widest shadow-hard">{{ statusLabel }}</p>
        </div>
        <div v-if="showApprove || showReject" class="mt-6 flex flex-wrap gap-3">
          <BauhausButton
            v-if="showApprove"
            variant="secondary"
            aria-label="Approve request"
            :disabled="review.isActing"
            @click="isApproveOpen = true"
          >
            Approve
          </BauhausButton>
          <BauhausButton
            v-if="showReject"
            variant="primary"
            aria-label="Open reject dialog"
            :disabled="review.isActing"
            @click="review.error = null; isRejectOpen = true"
          >
            Reject
          </BauhausButton>
        </div>
      </BauhausCard>

      <div class="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
        <BauhausCard background="white" accent="none">
          <h2 class="text-2xl font-black uppercase tracking-tight">Request details</h2>
          <dl class="mt-6 grid gap-5 sm:grid-cols-2">
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Purpose</dt><dd class="mt-1 font-medium">{{ displayValue(event.purpose) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Expected attendance</dt><dd class="mt-1 font-medium">{{ displayValue(event.expected_attendance) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Starts</dt><dd class="mt-1 font-medium">{{ displayDateTime(event.starts_at, event.event_timezone) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Ends</dt><dd class="mt-1 font-medium">{{ displayDateTime(event.ends_at, event.event_timezone) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Preferred layout</dt><dd class="mt-1 font-medium">{{ displayValue(event.layout_preference) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Facilities</dt><dd class="mt-1 font-medium">{{ event.facilities_required?.length ? event.facilities_required.join(", ") : "None specified" }}</dd></div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Accessibility needs</dt><dd class="mt-1 font-medium">{{ displayValue(event.accessibility_needs) }}</dd></div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Equipment needs</dt><dd class="mt-1 font-medium">{{ displayValue(event.preliminary_equipment_needs) }}</dd></div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Description</dt><dd class="mt-1 whitespace-pre-wrap font-medium">{{ displayValue(event.description) }}</dd></div>
          </dl>
        </BauhausCard>

        <BauhausCard background="white" accent="none">
          <h2 class="mb-6 text-2xl font-black uppercase tracking-tight">History</h2>
          <EventStatusHistory :entries="review.history" />
        </BauhausCard>
      </div>
    </template>

    <p v-else-if="review.isLoading" class="text-sm font-bold uppercase tracking-widest text-ink/70">Loading request…</p>

    <ConfirmModal
      :open="isApproveOpen"
      title="Approve this request?"
      message="It moves to Planning so venue and equipment planning can begin. This does not confirm the event."
      confirm-label="Approve"
      cancel-label="Cancel"
      @confirm="confirmApprove"
      @stay="isApproveOpen = false"
    />
    <RejectEventModal
      v-if="event"
      :open="isRejectOpen"
      :event-name="event.name"
      :busy="review.isActing"
      :error="isRejectOpen ? review.error : null"
      @confirm="confirmReject"
      @cancel="isRejectOpen = false"
    />
  </main>
</template>
```

- [ ] **Step 4: Run it and the route matrix, and confirm they pass**

Run: `npx vitest run src/views/__tests__/CoordinatorEventView.spec.js src/router/__tests__`
Expected: PASS. `activeRoleAccess.spec.js` picks up `coordinator-event` and proves that every role except `event_coordinator` is redirected, including an account that holds the coordinator role but is acting as another.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/events/CoordinatorEventView.vue frontend/src/router/index.js frontend/src/views/__tests__/CoordinatorEventView.spec.js
git commit -m "feat(events): add the coordinator's review page with approve and reject

SCRUM-34/52: the assigned coordinator needs a screen to decide on a request.
Approve asks for confirmation and says it is not the final confirmation;
reject requires a reason. SCRUM-49 extends this page with the full review."
```

---

### Task 8: The organiser sees the rejection reason and history

**Files:**
- Modify: `frontend/src/views/events/EventDetailView.vue`
- Test: `frontend/src/views/__tests__/EventDetailView.spec.js` (extend the mock and add cases)

**Interfaces:**
- Consumes: `useEventReviewStore().loadHistory(eventId)` and `.history`, and `EventStatusHistory`.

- [ ] **Step 1: Write the failing tests**

In `EventDetailView.spec.js`:
- Add `history: vi.fn()` to the mocked `eventsApi` object.
- In `mountDetail`, add as its first line `eventsApi.history.mockResolvedValue(historyResponse);`, and give the function a second parameter `historyResponse = { entries: [] }`.
- Append:
```js
describe("EventDetailView decision and history (SCRUM-34, SCRUM-52)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  const rejection = {
    id: "h2", from_status: "under_review", to_status: "rejected", reason: "Venue unavailable on that date",
    at: "2026-09-24T06:05:00Z", actor: { id: "c1", full_name: "Marcus Lim" },
  };

  it("shows the organiser why their request was rejected", async () => {
    const el = await mountDetail(eventResponse({ status: "rejected" }), { entries: [rejection] });

    await vi.waitFor(() => expect(el.querySelector('[data-testid="rejection-notice"]')).not.toBeNull());
    const notice = el.querySelector('[data-testid="rejection-notice"]');
    expect(notice.textContent).toContain("Venue unavailable on that date");
    expect(notice.textContent).toContain("can't be resubmitted");
  });

  it("offers no resubmit or edit action on a rejected request", async () => {
    const el = await mountDetail(eventResponse({ status: "rejected" }), { entries: [rejection] });

    expect(el.textContent).not.toMatch(/resubmit request|edit request/i);
  });

  it("lists the status history", async () => {
    const el = await mountDetail(eventResponse({ status: "planning" }), {
      entries: [{ id: "h1", from_status: "under_review", to_status: "planning", reason: null,
        at: "2026-09-23T03:00:00Z", actor: { id: "c1", full_name: "Marcus Lim" } }],
    });

    await vi.waitFor(() => expect(el.textContent).toContain("Marcus Lim"));
    expect(el.textContent).toContain("History");
  });

  it("shows no rejection notice for an event that isn't rejected", async () => {
    const el = await mountDetail(eventResponse({ status: "under_review" }));

    expect(el.querySelector('[data-testid="rejection-notice"]')).toBeNull();
  });
});
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `npx vitest run src/views/__tests__/EventDetailView.spec.js`
Expected: the new cases FAIL (`rejection-notice` not found, no "History" text). The existing cases still PASS.

- [ ] **Step 3: Implement**

In `EventDetailView.vue` `<script setup>`, add:
```js
import EventStatusHistory from "@/components/events/EventStatusHistory.vue";
import { useEventReviewStore } from "@/features/events/eventReviewStore";

const review = useEventReviewStore();
const rejection = computed(() =>
  event.value?.status === "rejected" ? review.history.find((entry) => entry.to_status === "rejected") ?? null : null,
);
```
Change `onMounted` to:
```js
onMounted(async () => {
  try {
    await eventsStore.get(route.params.id);
  } catch {
    return;
  }
  try {
    await review.loadHistory(route.params.id);
  } catch {
    // History is supplementary; the request details still render without it.
  }
});
```
In the template, directly after the yellow header `BauhausCard`, add:
```vue
      <BauhausCard v-if="event.status === 'rejected'" background="red" accent="none" class="mb-8" data-testid="rejection-notice">
        <h2 class="text-2xl font-black uppercase tracking-tight">This request was rejected</h2>
        <p v-if="rejection?.reason" class="mt-3 whitespace-pre-wrap font-medium">{{ rejection.reason }}</p>
        <p class="mt-3 text-sm font-bold">It is closed and can't be resubmitted. Start a new request if your plans change.</p>
      </BauhausCard>
```
At the end of the right-hand column, after the last card inside `<div class="grid …">`, add:
```vue
        <BauhausCard background="white" accent="none">
          <h2 class="mb-6 text-2xl font-black uppercase tracking-tight">History</h2>
          <EventStatusHistory :entries="review.history" />
        </BauhausCard>
```
If `BauhausCard` doesn't forward `data-testid` (check whether it uses `inheritAttrs: false`), wrap the card in `<div data-testid="rejection-notice">`.

- [ ] **Step 4: Run the whole frontend suite and the build**

Run: `npm test && npm run build` (from `frontend/`)
Expected: every spec passes, and the build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/events/EventDetailView.vue frontend/src/views/__tests__/EventDetailView.spec.js
git commit -m "feat(events): show organisers the rejection reason and status history

SCRUM-52: the organiser must see the decision and its reason, and know the
request is closed (QA-34, QA-95). SCRUM-34/52: the history of decisions is
visible to them (QA-70)."
```

---

### Task 9: Real-system verification

No new code. This proves the integration boundaries that mocks can't: PostgREST `.rpc()` argument casting, the history embed's FK name, RLS, and the browser.

- [ ] **Step 1: Reset the fixtures, then start the backend**

Run the fixture reset through the MCP `execute_sql`:
```sql
update public.events set status = 'under_review' where id = 'e0000000-0000-4000-8000-000000000201';
update public.events set status = 'planning' where id = 'e0000000-0000-4000-8000-000000000202';
update public.venue_bookings set status = 'held' where id = 'd0000000-0000-4000-8000-000000000201';
```
Start the backend from `backend/`: `uvicorn app.main:app --reload --port 8000` (run in the background).

- [ ] **Step 2: Run real HTTP checks**

These use `curl` from bash. Log in as `coordinator@connectsphere.dev` / `Cs1234` via `POST /api/v1/auth/login` and keep the `access_token`. Then check:

| Request | Expected |
|---|---|
| `POST /events/e0000000-0000-4000-8000-000000000201/approve` | 200 `"status":"planning"` |
| the same again | 409 `Cannot approve an event that is planning` |
| `POST /events/…0202/reject` `{"reason":"   "}` | 422 |
| `POST /events/…0202/reject` `{"reason":"Venue unavailable"}` | 200 `"status":"rejected"` |
| `GET /events/…0202/history` | the entry with `actor.full_name = "Marcus Lim"` and the reason. **This proves the embed's FK name.** |
| `POST /auth/active-role` `{"role":"venue_staff"}`, then approve 0201 | 403 |
| Log in as `organiser@…`, `GET /events/…0202/history` | 200. Approve gives 403 |

- [ ] **Step 3: Check the database as the real roles**

Through `execute_sql`:
```sql
select type, recipient_id, message from public.notifications
 where event_id in ('e0000000-0000-4000-8000-000000000201','e0000000-0000-4000-8000-000000000202');
select status from public.venue_bookings where id = 'd0000000-0000-4000-8000-000000000201';
```
Expected: two notifications, both with `recipient_id = a0000000-…0001` (the organiser, not the coordinator), and the booking `released`.

The RPC must be refused to the `authenticated` role:
```sql
begin; set local role authenticated;
select * from public.transition_event('e0000000-0000-4000-8000-000000000201', null, array['planning'], 'rejected', 1);
rollback;
```
Expected: `permission denied for function transition_event`.

Then run the MCP `get_advisors` (security and performance) once more.

- [ ] **Step 4: Browser check with the Playwright MCP**

- Start the frontend: `npm run dev` from `frontend/`, in the background.
- Reset the fixtures as in Step 1.
- As the coordinator, open `http://localhost:5173/coordinator/events/e0000000-0000-4000-8000-000000000201`:
  - Approve, confirm, and see "Planning" and the history entry.
  - Open 0202 and reject with a reason. The whitespace-only reason keeps the button disabled.
- As the organiser, open `/events/e0000000-0000-4000-8000-000000000202` and see the rejection notice and history.
- Check `browser_console_messages` for errors on each page.

- [ ] **Step 5: Reset the fixtures** (Step 1 SQL) so teammates find them usable, and stop the dev servers.

---

### Task 10: Paper trail

**Files:** `docs/IMPLEMENTATION_MAP.md`, `docs/SCENARIO.md`, `docs/TEST_CASES.md`, `docs/REQUIREMENTS.md`

- [ ] **Step 1: `IMPLEMENTATION_MAP.md` (edit in place)**
  - "Last updated" line: 2026-09-23, SCRUM-34/52 on `feature/scrum-34-52-approve-reject`.
  - §1: add rows for SCRUM-34 and SCRUM-52.
  - §2 endpoints: add the approve, reject and history rows, and change the `GET /events/{event_id}` guard to "`event_organiser` (owner, 404 otherwise) or `event_coordinator` (assigned, 403 otherwise)".
  - §2 building blocks: `lifecycle.TRANSITIONS`/`target`/`allowed_from`, `repository.transition_event` (RPC), `list_status_history`, `EventTransitionError`, `NotAssignedCoordinatorError`.
  - §3: the route `/coordinator/events/:id`, `RejectEventModal`, `EventStatusHistory`, `eventReviewStore`.
  - §4: the migration row, and `event_review_checks.sql` in the verification scripts.
  - §5 "Know before you build":
    - (a) Every lifecycle transition must go through `transition_event` and a `lifecycle.TRANSITIONS` row. SCRUM-12 and 33 add rows, not new write paths.
    - (b) A coordinator who isn't assigned gets 403, not 404, and why.
    - (c) `notifications` is written but has no read API or bell yet (SCRUM-27).
    - (d) The coordinator page is reachable only by URL until the SCRUM-72 dashboard endpoint exists.
    - (e) Equipment reservations are not released on rejection yet (hook in `transition_event`).
    - (f) Fixture events 0201 and 0202 exist for review testing.
- [ ] **Step 2: `SCENARIO.md` §4:** append one entry per story following the existing template, quoting each Jira description verbatim. Never edit past entries.
- [ ] **Step 3: `TEST_CASES.md`:** add `TC-REV-001…`, one per acceptance criterion of SCRUM-34 and SCRUM-52, each traced to its automated test or the Task 9 manual step.
- [ ] **Step 4: `REQUIREMENTS.md`:**
  - §6.4: add the rejection-reason max length of 1000 **[Assumption]**, with the reason, plus a §9 open-question entry.
  - §3.3 module rules: a status note saying the `core.events` dispatcher isn't adopted, and that transitions write history and notifications directly through `transition_event`.
  - §6.4 edge cases: add "a non-assigned coordinator gets 403" (already there; confirm).
- [ ] **Step 5: Commit**

```bash
git add docs/IMPLEMENTATION_MAP.md docs/SCENARIO.md docs/TEST_CASES.md docs/REQUIREMENTS.md
git commit -m "docs(events): record approve and reject for SCRUM-34 and SCRUM-52

Updates the map with the lifecycle RPC and new endpoints, logs both stories,
traces each acceptance criterion to a test case, and records the reason-length
assumption and the dispatcher deviation."
```

- [ ] **Step 6: Final report to the developer**

Cover: what changed, how it was verified (Task 9 results), and what **wasn't** verified. Follow-ups:
- the notifications UI
- releasing equipment reservations
- the dashboard link
- SCRUM-12 must call `transition_event`

Remind them that PR, review, merge and Jira Done are theirs, and ask about moving both stories to **In Review** when a PR is opened.
