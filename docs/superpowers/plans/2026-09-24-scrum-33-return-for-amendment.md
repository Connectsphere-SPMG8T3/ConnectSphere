# Return an Event Request for Amendment (SCRUM-33) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The assigned coordinator returns an under-review request with a message and flagged fields; the organiser amends the same request on the existing form and resubmits it with a note, back to the same coordinator. Both steps are recorded in history and notify the other party.

**Architecture:** A new `amendment_requests` table plus two `security definer` SQL functions that wrap the existing `public.transition_event`, so status, history, amendment row and notification commit together. The `events` module gets two lifecycle rows, two endpoints (`/return`, `/resubmit`) and an `amendment` field on single-event responses. On the frontend, the coordinator returns the request from `CoordinatorEventView` through a new modal. The organiser amends in `EventRequestView`, which gains a returned mode with a banner, highlighted fields and a Resubmit modal.

**Tech Stack:** Supabase Postgres (plpgsql, RLS), FastAPI 0.115 + Pydantic 2.11 + supabase-py 2.31, pytest 8.3; Vue 3.4 (`<script setup>`), Pinia, Vue Router, Tailwind, Vitest 3.2.

**Spec:** `docs/superpowers/specs/2026-09-24-scrum-33-return-for-amendment-design.md`

## Global Constraints

- Branch: `feature/scrum-33-return-for-amendment`, stacked on `chore/split-test-cases` (PR #29). Never commit to `main`.
- Authorise by the session's **active** role only: `require_roles` / `EventCoordinator` / `EventOrganiser` aliases in the API, `private.current_user_role()` in RLS.
- Endpoints that call Supabase are plain `def`. Routers stay thin: no Supabase calls or rules in `router.py`.
- Schema changes only through `supabase/migrations/`. Apply to the live project (`vuiryrzzyfecjqftwicj`) with the Supabase MCP `apply_migration`, never ad-hoc DDL.
- Return message and resubmission note: required, trimmed, then capped at **1000** characters (`AMENDMENT_TEXT_MAX_LENGTH`), exactly like `EventRejectRequest.reason`. **[Assumption]**
- 409 message for a disallowed transition comes from `EventTransitionError`: `"Cannot return an event that is <status with spaces>"`, `"Cannot resubmit an event that is <status with spaces>"`. Lost race: `"This event was updated by someone else. Reload."`
- Notification types: `event_returned` (to the organiser), `event_resubmitted` (to the coordinator). Never notify the actor.
- Notification text: `'Your event "<name>" was returned for amendment: <message>'` and `'"<name>" was amended and resubmitted: <note>'`.
- UI copy: button "Return for amendment"; toasts "Returned to organiser", "Changes saved", "Request resubmitted"; flag text "Flagged by coordinator"; organiser heading "Amend your request"; submit button "Resubmit".
- TDD: every test is written first and seen failing for the right reason before the code that passes it.
- Commit messages: imperative summary (`feat(events): …`), a *why* body, and the key `SCRUM-33`. No attribution lines.

## Review Focus

- **The event date passes while the request sits in `returned`.** Resubmitting must answer 422 "Event date must be after today." and leave it `returned`, not resubmit a past event. Test in Task 4.
- **Edits save but the resubmit loses a race.** The PATCH succeeds, then the RPC finds the version moved. The organiser must get 409 and the event stays `returned` with the edits kept, never a half-resubmitted state. Test in Task 4.
- **A `returned` event with no amendment row** (returned before this migration, or set by SQL). `GET` must answer `amendment: null`, the form must still open without a banner, and Resubmit must still work. Tests in Tasks 4 and 9.
- **A flagged field name the client doesn't know** (API and SPA deployed out of step). The banner must show a readable fallback label instead of crashing or showing nothing. Test in Task 5.
- **"Save changes" on a returned request** must keep the coordinator's banner and highlights. The PATCH response has to carry `amendment`, or the organiser loses the message after the first save. Tests in Tasks 4 and 9.

---

### Task 1: Database — `amendment_requests`, return and resubmit functions

**Files:**
- Create: `supabase/verification/event_amendment_checks.sql`
- Create: `supabase/migrations/20260924140000_event_amendment_requests.sql`

**Interfaces:**
- Produces: table `public.amendment_requests(id, event_id, message, flagged_fields text[], returned_at, resubmission_note, resubmitted_at)`.
- Produces: `public.return_event_for_amendment(p_event_id uuid, p_actor_id uuid, p_from_statuses text[], p_to_status text, p_expected_version integer, p_message text, p_flagged_fields text[], p_notify_message text) returns setof public.events`.
- Produces: `public.resubmit_event(p_event_id uuid, p_actor_id uuid, p_from_statuses text[], p_to_status text, p_expected_version integer, p_note text, p_notify_message text) returns setof public.events`.

- [ ] **Step 1: Write the failing verification script**

Create `supabase/verification/event_amendment_checks.sql`:

```sql
-- SCRUM-33 return for amendment: the real functions, table constraints and RLS.
-- Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`. Raises on
-- the first failure and prints AMENDMENT CHECKS PASSED otherwise. Everything
-- runs inside `begin; ... rollback;`, so the throwaway event leaves no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002) and venue staff (…0003).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name)
values ('e0000000-0000-4000-8000-0000000003a1', 'a0000000-0000-4000-8000-000000000001',
        'a0000000-0000-4000-8000-000000000002', 'under_review', 'Amendment check (rolled back)');

do $$
declare
    v_event uuid := 'e0000000-0000-4000-8000-0000000003a1';
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_row public.events;
    v_rows integer;
begin
    select * into v_row from public.events where id = v_event;

    -- Return.
    select * into v_row from public.return_event_for_amendment(
        v_event, v_coordinator, array['under_review'], 'returned', v_row.version,
        '  Please confirm the attendance  ', array['expected_attendance'],
        'Your event "Amendment check (rolled back)" was returned for amendment: Please confirm the attendance');
    if v_row.status is distinct from 'returned' then
        raise exception 'AMENDMENT FAIL: return did not move the event to returned (got %)', v_row.status;
    end if;

    select count(*) into v_rows from public.amendment_requests
     where event_id = v_event and resubmitted_at is null
       and message = 'Please confirm the attendance' and flagged_fields = array['expected_attendance'];
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: return did not open one trimmed amendment row'; end if;

    select count(*) into v_rows from public.event_status_history
     where event_id = v_event and from_status = 'under_review' and to_status = 'returned'
       and actor_id = v_coordinator and reason = 'Please confirm the attendance';
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: return is not in history with its message'; end if;

    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'event_returned' and recipient_id = v_organiser;
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: the organiser was not notified of the return'; end if;

    -- A second open amendment for the same event is refused.
    begin
        insert into public.amendment_requests (event_id, message) values (v_event, 'second open row');
        raise exception 'AMENDMENT FAIL: a second open amendment was accepted';
    exception when unique_violation then null;
    end;

    -- A blank message is refused by the table itself.
    begin
        update public.amendment_requests set message = '   ' where event_id = v_event;
        raise exception 'AMENDMENT FAIL: a blank message was accepted';
    exception when check_violation then null;
    end;

    -- A stale version changes nothing.
    select count(*) into v_rows from public.resubmit_event(
        v_event, v_organiser, array['returned'], 'under_review', v_row.version - 1, 'note', 'msg');
    if v_rows <> 0 then raise exception 'AMENDMENT FAIL: a stale resubmit returned a row'; end if;
    if (select status from public.events where id = v_event) is distinct from 'returned' then
        raise exception 'AMENDMENT FAIL: a stale resubmit changed the status';
    end if;

    -- Resubmit.
    select * into v_row from public.resubmit_event(
        v_event, v_organiser, array['returned'], 'under_review', v_row.version,
        '  Attendance is now 40  ', '"Amendment check (rolled back)" was amended and resubmitted: Attendance is now 40');
    if v_row.status is distinct from 'under_review' or v_row.coordinator_id is distinct from v_coordinator then
        raise exception 'AMENDMENT FAIL: resubmit did not return the event to the same coordinator';
    end if;

    select count(*) into v_rows from public.amendment_requests
     where event_id = v_event and resubmitted_at is not null and resubmission_note = 'Attendance is now 40';
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: resubmit did not close the amendment with its note'; end if;

    select count(*) into v_rows from public.event_status_history
     where event_id = v_event and from_status = 'returned' and to_status = 'under_review'
       and actor_id = v_organiser and reason = 'Attendance is now 40';
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: resubmission is not in history with its note'; end if;

    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'event_resubmitted' and recipient_id = v_coordinator;
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: the coordinator was not notified of the resubmission'; end if;

    select count(*) into v_rows from public.notifications
     where event_id = v_event and recipient_id = v_organiser and type = 'event_resubmitted';
    if v_rows <> 0 then raise exception 'AMENDMENT FAIL: the organiser was notified of their own resubmission'; end if;

    -- Return again: a second round, one open.
    select * into v_row from public.return_event_for_amendment(
        v_event, v_coordinator, array['under_review'], 'returned', v_row.version,
        'Also add the timezone', array[]::text[], 'msg');
    select count(*) into v_rows from public.amendment_requests where event_id = v_event;
    if v_rows <> 2 then raise exception 'AMENDMENT FAIL: a second return did not add a second row'; end if;
    select count(*) into v_rows from public.amendment_requests where event_id = v_event and resubmitted_at is null;
    if v_rows <> 1 then raise exception 'AMENDMENT FAIL: more than one amendment is open'; end if;

    -- API-only: not callable by signed-in users.
    if has_function_privilege('authenticated', 'public.return_event_for_amendment(uuid, uuid, text[], text, integer, text, text[], text)', 'execute')
       or has_function_privilege('authenticated', 'public.resubmit_event(uuid, uuid, text[], text, integer, text, text)', 'execute') then
        raise exception 'AMENDMENT FAIL: authenticated can execute the amendment functions';
    end if;
end $$;

-- RLS: the owning organiser, acting as organiser, sees both rounds.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.amendment_requests where event_id = 'e0000000-0000-4000-8000-0000000003a1') <> 2 then
        raise exception 'AMENDMENT FAIL: the owning organiser cannot read the amendments';
    end if;
end $$;
reset role;

-- RLS: the assigned coordinator, acting as coordinator, sees both rounds.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.amendment_requests where event_id = 'e0000000-0000-4000-8000-0000000003a1') <> 2 then
        raise exception 'AMENDMENT FAIL: the assigned coordinator cannot read the amendments';
    end if;
end $$;
reset role;

-- RLS: an unrelated staff member sees nothing.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000003","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if exists (select 1 from public.amendment_requests) then
        raise exception 'AMENDMENT FAIL: venue staff can read amendment requests';
    end if;
end $$;
reset role;

-- RLS: anonymous callers see nothing.
set local role anon;
do $$
begin
    if exists (select 1 from public.amendment_requests) then
        raise exception 'AMENDMENT FAIL: anon can read amendment requests';
    end if;
end $$;
reset role;

select 'AMENDMENT CHECKS PASSED' as result;

rollback;
```

- [ ] **Step 2: Run it against the live project and confirm it fails for the right reason**

Run the file's contents with the Supabase MCP `execute_sql`.
Expected: an error that `public.return_event_for_amendment` does not exist, or that the relation `public.amendment_requests` does not exist. Not a syntax error in the script.

- [ ] **Step 3: Write the migration**

Create `supabase/migrations/20260924140000_event_amendment_requests.sql`:

```sql
-- =============================================================================
-- ConnectSphere - SCRUM-33 return an event request for amendment
--
-- amendment_requests: one row per return (message + flagged fields), closed by
-- the organiser's resubmission note (REQUIREMENTS 4, 6.4; QA-22, QA-77).
-- return_event_for_amendment / resubmit_event: wrap transition_event so the
-- status change, its history row, the amendment row and the notification commit
-- together (NT-R3). transition_event itself is unchanged. API-only (ADR-0002).
-- =============================================================================

create table public.amendment_requests (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null,
    message text not null,
    flagged_fields text[] not null default '{}',
    returned_at timestamptz not null default now(),
    resubmission_note text null,
    resubmitted_at timestamptz null,
    constraint amendment_requests_event_id_fkey
        foreign key (event_id) references public.events (id) on delete cascade,
    constraint amendment_requests_message_not_blank check (length(btrim(message)) > 0),
    constraint amendment_requests_resubmission_complete
        check ((resubmission_note is null) = (resubmitted_at is null))
);

comment on table public.amendment_requests is
    'Each return of an event for amendment (REQUIREMENTS 6.4). At most one open (not yet resubmitted) row per event. Written only by return_event_for_amendment and resubmit_event.';

create unique index amendment_requests_one_open_per_event_idx
    on public.amendment_requests (event_id) where resubmitted_at is null;
create index amendment_requests_event_returned_at_idx
    on public.amendment_requests (event_id, returned_at desc);

alter table public.amendment_requests enable row level security;

-- Safety net only: the API uses the secret key. Same readers as event_status_history.
create policy "amendment_requests_select_owner_or_assigned_coordinator"
    on public.amendment_requests
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.events e
            where e.id = amendment_requests.event_id
              and (
                  (e.organiser_id = (select auth.uid())
                   and (select private.current_user_role()) = 'event_organiser')
                  or (e.coordinator_id = (select auth.uid())
                      and (select private.current_user_role()) = 'event_coordinator')
              )
        )
    );

create or replace function public.return_event_for_amendment(
    p_event_id uuid,
    p_actor_id uuid,
    p_from_statuses text[],
    p_to_status text,
    p_expected_version integer,
    p_message text,
    p_flagged_fields text[],
    p_notify_message text
)
returns setof public.events
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_after public.events;
begin
    -- transition_event records the message as the history reason and notifies the organiser.
    select * into v_after
      from public.transition_event(p_event_id, p_actor_id, p_from_statuses, p_to_status,
                                   p_expected_version, p_message, 'event_returned', p_notify_message);
    if not found then
        return;
    end if;

    insert into public.amendment_requests (event_id, message, flagged_fields)
    values (p_event_id, btrim(p_message), coalesce(p_flagged_fields, '{}'));

    return next v_after;
end;
$$;

comment on function public.return_event_for_amendment is
    'Returns an event for amendment: status, history (message as reason), organiser notification and the amendment row, atomically. API-only.';

create or replace function public.resubmit_event(
    p_event_id uuid,
    p_actor_id uuid,
    p_from_statuses text[],
    p_to_status text,
    p_expected_version integer,
    p_note text,
    p_notify_message text
)
returns setof public.events
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_after public.events;
begin
    -- No notification here: transition_event can only notify the organiser, who is the actor.
    select * into v_after
      from public.transition_event(p_event_id, p_actor_id, p_from_statuses, p_to_status,
                                   p_expected_version, p_note, null, null);
    if not found then
        return;
    end if;

    update public.amendment_requests
       set resubmission_note = btrim(p_note),
           resubmitted_at = now()
     where event_id = p_event_id
       and resubmitted_at is null;

    if v_after.coordinator_id is not null and v_after.coordinator_id is distinct from p_actor_id then
        insert into public.notifications (recipient_id, event_id, type, message)
        values (v_after.coordinator_id, p_event_id, 'event_resubmitted', p_notify_message);
    end if;

    return next v_after;
end;
$$;

comment on function public.resubmit_event is
    'Resubmits a returned event to the same coordinator: status, history (note as reason), closes the open amendment and notifies the coordinator, atomically. API-only.';

revoke execute on function public.return_event_for_amendment(uuid, uuid, text[], text, integer, text, text[], text)
    from public, anon, authenticated;
grant execute on function public.return_event_for_amendment(uuid, uuid, text[], text, integer, text, text[], text)
    to service_role;
revoke execute on function public.resubmit_event(uuid, uuid, text[], text, integer, text, text)
    from public, anon, authenticated;
grant execute on function public.resubmit_event(uuid, uuid, text[], text, integer, text, text)
    to service_role;
```

- [ ] **Step 4: Apply the migration to the live project**

Use the Supabase MCP `apply_migration` with name `event_amendment_requests` and the file's SQL. Then run `list_migrations` and confirm it appears.

- [ ] **Step 5: Run the verification script and confirm it passes**

Run `supabase/verification/event_amendment_checks.sql` with `execute_sql`.
Expected: one row, `AMENDMENT CHECKS PASSED`.

- [ ] **Step 6: Check the advisors**

Run `get_advisors` for `security` and `performance`.
Expected: nothing new naming `amendment_requests`, `return_event_for_amendment` or `resubmit_event`. In particular: no `unindexed_foreign_keys` (the `(event_id, returned_at)` index covers the FK), no `function_search_path_mutable`, and no `security_definer_function_executable`.

- [ ] **Step 7: Commit**

```bash
git add supabase/migrations/20260924140000_event_amendment_requests.sql supabase/verification/event_amendment_checks.sql
git commit -m "feat(events): store amendment requests and add return/resubmit functions

A returned request needs its message and flagged fields kept until the
organiser resubmits, and every round kept for history (QA-22, QA-77). The
two functions wrap transition_event so status, history, the amendment row
and the notification commit together; transition_event is unchanged, so
approve, reject and submit are unaffected.

SCRUM-33"
```

---

### Task 2: Lifecycle rows for return and resubmit

**Files:**
- Modify: `backend/app/modules/events/lifecycle.py:3-17`
- Test: `backend/tests/test_event_lifecycle.py`

**Interfaces:**
- Produces: `lifecycle.target("return", status)` → `EventStatus.returned`; `lifecycle.target("resubmit", status)` → `EventStatus.under_review`; `lifecycle.allowed_from("return") == ["under_review"]`; `lifecycle.allowed_from("resubmit") == ["returned"]`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_event_lifecycle.py`:

```python
def test_return_moves_under_review_to_returned():
    """SCRUM-33: the coordinator returns a request for amendment (QA-22)."""
    assert lifecycle.target("return", "under_review") == EventStatus.returned


@pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s != "under_review"])
def test_return_is_blocked_from_every_other_status(status):
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target("return", status)

    assert raised.value.status_code == 409
    assert raised.value.detail == f"Cannot return an event that is {status.replace('_', ' ')}"


def test_resubmit_moves_returned_back_to_under_review():
    """SCRUM-33: the organiser resubmits to the same coordinator (QA-77)."""
    assert lifecycle.target("resubmit", "returned") == EventStatus.under_review


@pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s != "returned"])
def test_resubmit_is_blocked_from_every_other_status(status):
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target("resubmit", status)

    assert raised.value.detail == f"Cannot resubmit an event that is {status.replace('_', ' ')}"


def test_allowed_from_lists_the_amendment_sources_for_the_rpc():
    assert lifecycle.allowed_from("return") == ["under_review"]
    assert lifecycle.allowed_from("resubmit") == ["returned"]


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_a_returned_event_cannot_be_approved_or_rejected(action):
    """SCRUM-33 AC7: the decision waits for the organiser's resubmission."""
    with pytest.raises(EventTransitionError) as raised:
        lifecycle.target(action, "returned")

    assert raised.value.status_code == 409
```

- [ ] **Step 2: Run them and confirm they fail**

Run (from `backend/`): `pytest tests/test_event_lifecycle.py -v`
Expected: the new `return`/`resubmit` tests FAIL with `KeyError: 'return'` / `KeyError: 'resubmit'`. `test_a_returned_event_cannot_be_approved_or_rejected` already PASSES; it pins existing behaviour for AC7.

- [ ] **Step 3: Add the rows**

In `backend/app/modules/events/lifecycle.py`, update the docstring and the table:

```python
"""Which lifecycle actions each event status allows (REQUIREMENTS §5). Pure: no I/O.

One row per lifecycle action. SCRUM-12 (assign) adds its row here rather than
checking statuses inline.
"""

from app.core.exceptions import EventTransitionError
from app.modules.events.schemas import EventStatus

TRANSITIONS: dict[str, tuple[frozenset[EventStatus], EventStatus]] = {
    # The organiser's submission.
    "submit": (frozenset({EventStatus.draft}), EventStatus.under_review),
    # Initial feasibility decision, not confirmation (SCRUM-34, QA2-8).
    "approve": (frozenset({EventStatus.under_review}), EventStatus.planning),
    # Only before confirmation; a confirmed event is cancelled instead (QA2-6).
    "reject": (frozenset({EventStatus.under_review, EventStatus.planning}), EventStatus.rejected),
    # Back to the organiser with a message; planning waits for the answer (SCRUM-33, QA-22).
    "return": (frozenset({EventStatus.under_review}), EventStatus.returned),
    # Amended and sent back to the same coordinator (SCRUM-33, QA-77).
    "resubmit": (frozenset({EventStatus.returned}), EventStatus.under_review),
}
```

(Leave `allowed_from` and `target` unchanged.)

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `pytest tests/test_event_lifecycle.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/events/lifecycle.py backend/tests/test_event_lifecycle.py
git commit -m "feat(events): add return and resubmit to the lifecycle table

lifecycle.py is the single source of which status each action may start
from; the new endpoints and SQL functions read their allowed statuses from
here. Approve and reject already exclude returned, which a test now pins
(AC7).

SCRUM-33"
```

---

### Task 3: Repository wrappers for the new functions and table

**Files:**
- Modify: `backend/app/modules/events/repository.py` (append after `transition_event`)
- Test: `backend/tests/test_events_repository.py`

**Interfaces:**
- Consumes: the SQL functions and table from Task 1.
- Produces:
  - `repository.return_event(event_id: str, actor_id: str, from_statuses: list[str], to_status: str, expected_version: int, *, message: str, flagged_fields: list[str], notify_message: str) -> dict | None`
  - `repository.resubmit_event(event_id: str, actor_id: str, from_statuses: list[str], to_status: str, expected_version: int, *, note: str, notify_message: str) -> dict | None`
  - `repository.get_open_amendment(event_id: str) -> dict | None`: keys `id, message, flagged_fields, returned_at`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_events_repository.py`:

```python
class RpcClient:
    """Records the RPC name and parameters; answers with the rows given."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


def test_return_event_calls_the_return_function_with_every_parameter(monkeypatch):
    client = RpcClient([{"id": "event-1", "status": "returned"}])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    row = repository.return_event(
        "event-1", "coordinator-1", ["under_review"], "returned", 3,
        message="Confirm attendance", flagged_fields=["expected_attendance"], notify_message="msg",
    )

    assert row == {"id": "event-1", "status": "returned"}
    assert client.calls == [("return_event_for_amendment", {
        "p_event_id": "event-1", "p_actor_id": "coordinator-1", "p_from_statuses": ["under_review"],
        "p_to_status": "returned", "p_expected_version": 3, "p_message": "Confirm attendance",
        "p_flagged_fields": ["expected_attendance"], "p_notify_message": "msg",
    })]


def test_resubmit_event_calls_the_resubmit_function_with_every_parameter(monkeypatch):
    client = RpcClient([{"id": "event-1", "status": "under_review"}])
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: client)

    row = repository.resubmit_event(
        "event-1", "organiser-1", ["returned"], "under_review", 4, note="Now 40", notify_message="msg",
    )

    assert row == {"id": "event-1", "status": "under_review"}
    assert client.calls == [("resubmit_event", {
        "p_event_id": "event-1", "p_actor_id": "organiser-1", "p_from_statuses": ["returned"],
        "p_to_status": "under_review", "p_expected_version": 4, "p_note": "Now 40", "p_notify_message": "msg",
    })]


def test_a_stale_return_or_resubmit_comes_back_as_none(monkeypatch):
    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: RpcClient([]))

    assert repository.return_event("e", "c", ["under_review"], "returned", 1,
                                   message="m", flagged_fields=[], notify_message="n") is None
    assert repository.resubmit_event("e", "o", ["returned"], "under_review", 1, note="n", notify_message="n") is None


def test_get_open_amendment_reads_only_the_unresubmitted_row(monkeypatch):
    filters = []
    open_row = {"id": "a1", "message": "Confirm attendance", "flagged_fields": ["expected_attendance"],
                "returned_at": "2026-09-24T03:00:00+00:00"}

    class AmendmentQuery:
        def select(self, columns):
            filters.append(("select", columns))
            return self

        def eq(self, field, value):
            filters.append(("eq", field, value))
            return self

        def is_(self, field, value):
            filters.append(("is", field, value))
            return self

        def maybe_single(self):
            return self

        def execute(self):
            return SimpleNamespace(data=open_row)

    class AdminClient:
        def table(self, name):
            filters.append(("table", name))
            return AmendmentQuery()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    assert repository.get_open_amendment("event-1") == open_row
    assert filters == [
        ("table", "amendment_requests"),
        ("select", "id, message, flagged_fields, returned_at"),
        ("eq", "event_id", "event-1"),
        ("is", "resubmitted_at", "null"),
    ]


def test_get_open_amendment_is_none_when_nothing_is_open(monkeypatch):
    """supabase-py returns no response object at all for maybe_single() with no row."""

    class EmptyQuery:
        def select(self, columns): return self
        def eq(self, field, value): return self
        def is_(self, field, value): return self
        def maybe_single(self): return self
        def execute(self): return None

    class AdminClient:
        def table(self, name): return EmptyQuery()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    assert repository.get_open_amendment("event-1") is None
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `pytest tests/test_events_repository.py -v`
Expected: the five new tests FAIL with `AttributeError: module 'app.modules.events.repository' has no attribute 'return_event'` (and likewise `resubmit_event` and `get_open_amendment`).

- [ ] **Step 3: Implement the wrappers**

Append to `backend/app/modules/events/repository.py`:

```python
def _first_row(response) -> dict | None:
    rows = (response.data or []) if response else []
    return rows[0] if rows else None


def return_event(
    event_id: str,
    actor_id: str,
    from_statuses: list[str],
    to_status: str,
    expected_version: int,
    *,
    message: str,
    flagged_fields: list[str],
    notify_message: str,
) -> dict | None:
    """Run `public.return_event_for_amendment` (SCRUM-33): the transition, its history
    row, the organiser's notification and the amendment row in one transaction.
    None when the event had moved on, which the service reports as 409."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "return_event_for_amendment",
            {
                "p_event_id": event_id,
                "p_actor_id": actor_id,
                "p_from_statuses": from_statuses,
                "p_to_status": to_status,
                "p_expected_version": expected_version,
                "p_message": message,
                "p_flagged_fields": flagged_fields,
                "p_notify_message": notify_message,
            },
        )
        .execute()
    )
    return _first_row(response)


def resubmit_event(
    event_id: str,
    actor_id: str,
    from_statuses: list[str],
    to_status: str,
    expected_version: int,
    *,
    note: str,
    notify_message: str,
) -> dict | None:
    """Run `public.resubmit_event` (SCRUM-33): back to the same coordinator, the open
    amendment closed with the note, the coordinator notified. None when stale."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "resubmit_event",
            {
                "p_event_id": event_id,
                "p_actor_id": actor_id,
                "p_from_statuses": from_statuses,
                "p_to_status": to_status,
                "p_expected_version": expected_version,
                "p_note": note,
                "p_notify_message": notify_message,
            },
        )
        .execute()
    )
    return _first_row(response)


def get_open_amendment(event_id: str) -> dict | None:
    """The amendment the organiser still has to answer, if any. At most one is open
    per event (partial unique index in the migration)."""
    response = (
        get_supabase_admin_client()
        .table("amendment_requests")
        .select("id, message, flagged_fields, returned_at")
        .eq("event_id", event_id)
        .is_("resubmitted_at", "null")
        .maybe_single()
        .execute()
    )
    return response.data if response else None
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `pytest tests/test_events_repository.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/events/repository.py backend/tests/test_events_repository.py
git commit -m "feat(events): wrap the return/resubmit functions and read the open amendment

Keeps Supabase access in the repository so the service can stay pure
business logic, matching transition_event's wrapper.

SCRUM-33"
```

---

### Task 4: Endpoints — `POST /events/{id}/return`, `POST /events/{id}/resubmit`, `amendment` on responses

**Files:**
- Modify: `backend/app/modules/events/schemas.py` (after `EventRejectRequest`, and `EventResponse`)
- Modify: `backend/app/modules/events/service.py`
- Modify: `backend/app/modules/events/router.py`
- Test: `backend/tests/test_event_amendment_api.py` (new)

**Interfaces:**
- Consumes: Task 2 lifecycle rows; Task 3 `repository.return_event`, `repository.resubmit_event`, `repository.get_open_amendment`.
- Produces:
  - `schemas.EventField` (str enum, 15 values), `schemas.AMENDMENT_TEXT_MAX_LENGTH = 1000`, `schemas.EventReturnRequest`, `schemas.EventResubmitRequest`, `schemas.AmendmentRequest`, and `EventResponse.amendment: AmendmentRequest | None`.
  - `service.return_for_amendment(event_id: str, coordinator_id: str, body: EventReturnRequest) -> EventResponse` and `service.resubmit(event_id: str, organiser_id: str, body: EventResubmitRequest) -> EventResponse`.
  - HTTP: `POST /api/v1/events/{id}/return` with body `{"message": str, "flagged_fields": [str]}`; `POST /api/v1/events/{id}/resubmit` with body `{...EventUpdateRequest fields, "resubmission_note": str}`. Both answer `EventResponse`.
  - `GET /api/v1/events/{id}` and `PATCH /api/v1/events/{id}` include `amendment` while the event is `returned`.

- [ ] **Step 1: Write the failing API tests**

Create `backend/tests/test_event_amendment_api.py`:

```python
"""SCRUM-33 return for amendment and resubmission, through the HTTP API with the repository mocked."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.modules.events import repository
from tests.conftest import make_table_mock

ORGANISER_ID = "a0000000-0000-4000-8000-000000000001"
OTHER_ORGANISER_ID = "a0000000-0000-4000-8000-000000000008"
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_COORDINATOR_ID = "a0000000-0000-4000-8000-000000000009"
EVENT_ID = "e0000000-0000-4000-8000-000000000201"
ALL_STATUSES = ["draft", "submitted", "under_review", "returned", "planning",
                "confirmed", "rejected", "cancelled", "completed"]
OPEN_AMENDMENT = {"id": "a1", "message": "Please confirm the attendance",
                  "flagged_fields": ["expected_attendance"], "returned_at": "2026-09-24T03:00:00+00:00"}


def event_row(status="under_review"):
    now = datetime.now(timezone.utc).isoformat()
    starts = datetime.now(timezone.utc) + timedelta(days=30)
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": COORDINATOR_ID,
        "status": status, "event_timezone": "Asia/Singapore", "name": "Partner Summit",
        "purpose": "Quarterly partner meeting", "description": None,
        "starts_at": starts.isoformat(), "ends_at": (starts + timedelta(hours=2)).isoformat(),
        "expected_attendance": 12, "layout_preference": "boardroom", "facilities_required": [],
        "accessibility_needs": None, "preliminary_equipment_needs": None,
        "registration_enabled": False, "registration_capacity": None,
        "registration_opens_at": None, "registration_closes_at": None,
        "technical_readiness": "not_required", "submitted_at": now, "version": 3,
        "created_at": now, "updated_at": now,
    }


@pytest.fixture()
def events(monkeypatch):
    """An in-memory events table, an open-amendment slot, and fakes with the RPCs' guards."""
    state = {"store": {EVENT_ID: event_row()}, "amendment": None, "calls": [], "updates": []}

    def get_event(event_id):
        return deepcopy(state["store"].get(event_id))

    def _move(event_id, from_statuses, to_status, expected_version):
        row = state["store"].get(event_id)
        if row is None or row["version"] != expected_version or row["status"] not in from_statuses:
            return None
        row.update(status=to_status, version=row["version"] + 1)
        return deepcopy(row)

    def return_event(event_id, actor_id, from_statuses, to_status, expected_version, *,
                     message, flagged_fields, notify_message):
        state["calls"].append({"rpc": "return", "actor_id": actor_id, "from_statuses": from_statuses,
                               "to_status": to_status, "expected_version": expected_version,
                               "message": message, "flagged_fields": flagged_fields,
                               "notify_message": notify_message})
        moved = _move(event_id, from_statuses, to_status, expected_version)
        if moved:
            state["amendment"] = {"id": "a1", "message": message, "flagged_fields": flagged_fields,
                                  "returned_at": "2026-09-24T03:00:00+00:00"}
        return moved

    def resubmit_event(event_id, actor_id, from_statuses, to_status, expected_version, *, note, notify_message):
        state["calls"].append({"rpc": "resubmit", "actor_id": actor_id, "from_statuses": from_statuses,
                               "to_status": to_status, "expected_version": expected_version,
                               "note": note, "notify_message": notify_message})
        moved = _move(event_id, from_statuses, to_status, expected_version)
        if moved:
            state["amendment"] = None
        return moved

    def update_event(event_id, values, version):
        state["updates"].append(values)
        row = state["store"][event_id]
        if row["version"] != version:
            return None
        row.update(values, version=version + 1)
        return deepcopy(row)

    monkeypatch.setattr(repository, "get_event", get_event)
    monkeypatch.setattr(repository, "return_event", return_event)
    monkeypatch.setattr(repository, "resubmit_event", resubmit_event)
    monkeypatch.setattr(repository, "update_event", update_event)
    monkeypatch.setattr(repository, "get_open_amendment", lambda event_id: deepcopy(state["amendment"]))
    return state


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role, user_id):
        return authenticate_as(role, user_id=user_id)
    return _act_as


def returned(events):
    events["store"][EVENT_ID]["status"] = "returned"
    events["amendment"] = deepcopy(OPEN_AMENDMENT)


def return_request(client, auth_headers, message="Please confirm the attendance",
                   flagged_fields=("expected_attendance",), event_id=EVENT_ID):
    return client.post(f"/api/v1/events/{event_id}/return",
                       json={"message": message, "flagged_fields": list(flagged_fields)}, headers=auth_headers)


def resubmit_request(client, auth_headers, note="Attendance is now 40", **edits):
    return client.post(f"/api/v1/events/{EVENT_ID}/resubmit",
                       json={"resubmission_note": note, **edits}, headers=auth_headers)


def acting_as_another_role(monkeypatch, user_id, holds, acts_as):
    """SCRUM-76: an account that holds `holds` but whose session acts as `acts_as`."""
    profile = {"id": user_id, "email": "someone@connectsphere.dev", "full_name": "Someone",
               "role": holds, "organisation_name": None, "department": None, "phone_number": None}
    anon_client = MagicMock()
    anon_client.auth.get_claims.return_value = {"claims": {
        "sub": user_id, "aud": "authenticated", "email": profile["email"],
        "session_id": "33333333-3333-3333-3333-333333333333",
    }}
    monkeypatch.setattr("app.core.security.get_supabase_anon_client", lambda: anon_client)
    monkeypatch.setattr("app.core.security.get_supabase_admin_client",
                        lambda: make_table_mock(profile, session_active_role={"role": acts_as}))


class TestReturn:
    def test_the_assigned_coordinator_returns_an_under_review_request(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", COORDINATOR_ID)

        response = return_request(client, auth_headers, message="  Please confirm the attendance  ")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "returned"
        assert body["amendment"]["message"] == "Please confirm the attendance"
        assert body["amendment"]["flagged_fields"] == ["expected_attendance"]
        [call] = events["calls"]
        assert call["actor_id"] == COORDINATOR_ID
        assert call["from_statuses"] == ["under_review"]
        assert call["to_status"] == "returned"
        assert call["expected_version"] == 3
        assert call["message"] == "Please confirm the attendance"
        assert call["notify_message"] == 'Your event "Partner Summit" was returned for amendment: Please confirm the attendance'

    def test_no_fields_need_flagging(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", COORDINATOR_ID)

        response = return_request(client, auth_headers, flagged_fields=())

        assert response.status_code == 200
        assert events["calls"][0]["flagged_fields"] == []

    def test_a_field_flagged_twice_is_sent_once_in_order(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", COORDINATOR_ID)

        return_request(client, auth_headers, flagged_fields=("starts_at", "expected_attendance", "starts_at"))

        assert events["calls"][0]["flagged_fields"] == ["starts_at", "expected_attendance"]

    def test_an_unknown_field_is_refused(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", COORDINATOR_ID)

        assert return_request(client, auth_headers, flagged_fields=("venue_id",)).status_code == 422
        assert events["calls"] == []

    @pytest.mark.parametrize("message", ["", "   ", "\n\t "])
    def test_a_blank_message_is_refused(self, client, auth_headers, act_as, events, message):
        act_as("event_coordinator", COORDINATOR_ID)

        assert return_request(client, auth_headers, message=message).status_code == 422
        assert events["calls"] == []

    def test_a_missing_message_is_refused(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", COORDINATOR_ID)

        response = client.post(f"/api/v1/events/{EVENT_ID}/return", json={}, headers=auth_headers)

        assert response.status_code == 422
        assert events["calls"] == []

    def test_the_message_is_capped_at_1000_characters(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", COORDINATOR_ID)

        assert return_request(client, auth_headers, message="x" * 1001).status_code == 422
        assert return_request(client, auth_headers, message="x" * 1000).status_code == 200

    @pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s not in ("under_review", "draft")])
    def test_return_is_blocked_unless_under_review(self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as("event_coordinator", COORDINATOR_ID)

        response = return_request(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Cannot return an event that is {status.replace('_', ' ')}"
        assert events["calls"] == []

    def test_a_draft_is_not_found(self, client, auth_headers, act_as, events):
        events["store"][EVENT_ID]["status"] = "draft"
        act_as("event_coordinator", COORDINATOR_ID)

        assert return_request(client, auth_headers).status_code == 404

    def test_a_coordinator_who_is_not_assigned_is_forbidden(self, client, auth_headers, act_as, events):
        act_as("event_coordinator", OTHER_COORDINATOR_ID)

        assert return_request(client, auth_headers).status_code == 403
        assert events["calls"] == []

    @pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "tech_support", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, events, role):
        act_as(role, COORDINATOR_ID)

        assert return_request(client, auth_headers).status_code == 403
        assert events["calls"] == []

    def test_a_coordinator_acting_as_venue_staff_is_forbidden(self, client, auth_headers, monkeypatch, events):
        acting_as_another_role(monkeypatch, COORDINATOR_ID, holds="event_coordinator", acts_as="venue_staff")

        assert return_request(client, auth_headers).status_code == 403
        assert events["calls"] == []

    def test_a_lost_race_is_a_conflict(self, client, auth_headers, act_as, events, monkeypatch):
        monkeypatch.setattr(repository, "return_event", lambda *args, **kwargs: None)
        act_as("event_coordinator", COORDINATOR_ID)

        response = return_request(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "This event was updated by someone else. Reload."

    @pytest.mark.parametrize("action", ["approve", "reject"])
    def test_a_returned_request_cannot_be_decided(self, client, auth_headers, act_as, events, action):
        """AC7: the decision waits for the organiser's resubmission."""
        returned(events)
        act_as("event_coordinator", COORDINATOR_ID)

        response = client.post(f"/api/v1/events/{EVENT_ID}/{action}", json={"reason": "No venue"}, headers=auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Cannot {action} an event that is returned"


class TestResubmit:
    def test_the_owner_resubmits_with_edits_to_the_same_coordinator(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers, note="  Attendance is now 40  ", expected_attendance=40)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "under_review"
        assert body["coordinator_id"] == COORDINATOR_ID
        assert body["expected_attendance"] == 40
        assert body["amendment"] is None
        assert events["updates"] == [{"expected_attendance": 40}]
        [call] = events["calls"]
        assert call["actor_id"] == ORGANISER_ID
        assert call["from_statuses"] == ["returned"]
        assert call["to_status"] == "under_review"
        assert call["expected_version"] == 4  # the edit bumped it from 3
        assert call["note"] == "Attendance is now 40"
        assert call["notify_message"] == '"Partner Summit" was amended and resubmitted: Attendance is now 40'

    def test_resubmitting_without_edits_skips_the_update(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers)

        assert response.status_code == 200
        assert events["updates"] == []
        assert events["calls"][0]["expected_version"] == 3

    @pytest.mark.parametrize("note", ["", "   "])
    def test_a_blank_note_is_refused(self, client, auth_headers, act_as, events, note):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        assert resubmit_request(client, auth_headers, note=note).status_code == 422
        assert events["calls"] == []

    def test_a_missing_note_is_refused(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        response = client.post(f"/api/v1/events/{EVENT_ID}/resubmit", json={"expected_attendance": 40}, headers=auth_headers)

        assert response.status_code == 422
        assert events["updates"] == []

    def test_the_note_is_capped_at_1000_characters(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        assert resubmit_request(client, auth_headers, note="x" * 1001).status_code == 422

    def test_edits_that_break_submission_rules_are_refused_before_anything_changes(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers, purpose="")

        assert response.status_code == 422
        assert events["updates"] == []
        assert events["calls"] == []

    def test_an_event_date_that_has_passed_while_returned_is_refused(self, client, auth_headers, act_as, events):
        """Review focus: the organiser took too long; the request must not go back with a past date."""
        returned(events)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        events["store"][EVENT_ID].update(starts_at=yesterday.isoformat(),
                                         ends_at=(yesterday + timedelta(hours=2)).isoformat())
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers)

        assert response.status_code == 422
        assert any(error["msg"] == "Event date must be after today." for error in response.json()["detail"])
        assert events["store"][EVENT_ID]["status"] == "returned"

    def test_edits_saved_but_a_lost_race_is_a_conflict_and_stays_returned(self, client, auth_headers, act_as, events, monkeypatch):
        """Review focus: the PATCH lands, the RPC finds the version moved."""
        returned(events)
        monkeypatch.setattr(repository, "resubmit_event", lambda *args, **kwargs: None)
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers, expected_attendance=40)

        assert response.status_code == 409
        assert events["store"][EVENT_ID]["status"] == "returned"
        assert events["store"][EVENT_ID]["expected_attendance"] == 40

    @pytest.mark.parametrize("status", [s for s in ALL_STATUSES if s != "returned"])
    def test_resubmit_is_blocked_unless_returned(self, client, auth_headers, act_as, events, status):
        events["store"][EVENT_ID]["status"] = status
        act_as("event_organiser", ORGANISER_ID)

        response = resubmit_request(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Cannot resubmit an event that is {status.replace('_', ' ')}"
        assert events["calls"] == []

    def test_another_organiser_gets_not_found(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", OTHER_ORGANISER_ID)

        assert resubmit_request(client, auth_headers).status_code == 404
        assert events["calls"] == []

    @pytest.mark.parametrize("role", ["event_coordinator", "venue_staff", "tech_support", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, events, role):
        returned(events)
        act_as(role, ORGANISER_ID)

        assert resubmit_request(client, auth_headers).status_code == 403
        assert events["calls"] == []

    def test_an_organiser_acting_as_attendee_is_forbidden(self, client, auth_headers, monkeypatch, events):
        returned(events)
        acting_as_another_role(monkeypatch, ORGANISER_ID, holds="event_organiser", acts_as="attendee")

        assert resubmit_request(client, auth_headers).status_code == 403


class TestAmendmentOnResponses:
    def test_reading_a_returned_request_includes_its_open_amendment(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        body = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers).json()

        assert body["amendment"] == OPEN_AMENDMENT

    def test_the_assigned_coordinator_reads_the_same_amendment(self, client, auth_headers, act_as, events):
        returned(events)
        act_as("event_coordinator", COORDINATOR_ID)

        body = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers).json()

        assert body["amendment"]["message"] == OPEN_AMENDMENT["message"]

    def test_a_request_that_is_not_returned_has_no_amendment(self, client, auth_headers, act_as, events):
        events["amendment"] = deepcopy(OPEN_AMENDMENT)  # stale row must not leak onto another status
        act_as("event_organiser", ORGANISER_ID)

        body = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers).json()

        assert body["amendment"] is None

    def test_a_returned_request_with_no_amendment_row_reads_as_null(self, client, auth_headers, act_as, events):
        """Review focus: returned before this migration, or set by SQL."""
        events["store"][EVENT_ID]["status"] = "returned"
        act_as("event_organiser", ORGANISER_ID)

        response = client.get(f"/api/v1/events/{EVENT_ID}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["amendment"] is None

    def test_saving_changes_on_a_returned_request_keeps_the_amendment(self, client, auth_headers, act_as, events):
        """Review focus: the PATCH response feeds the form; losing `amendment` would drop the banner."""
        returned(events)
        act_as("event_organiser", ORGANISER_ID)

        response = client.patch(f"/api/v1/events/{EVENT_ID}", json={"expected_attendance": 40}, headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["amendment"] == OPEN_AMENDMENT
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `pytest tests/test_event_amendment_api.py -v`
Expected: every test that posts to `/return` or `/resubmit` FAILS with `405 Method Not Allowed` / `404` (no such route). The `TestAmendmentOnResponses` tests FAIL with `KeyError: 'amendment'`. `test_a_returned_request_cannot_be_decided` PASSES already (Task 2 pinned it).

- [ ] **Step 3: Add the schemas**

In `backend/app/modules/events/schemas.py`, add after `EventUpdateRequest` (before `EventResponse`):

```python
class EventField(str, Enum):
    """The request fields a coordinator can flag when returning it (SCRUM-33).
    Exactly the fields `EventUpdateRequest` lets the organiser edit."""

    name = "name"
    event_timezone = "event_timezone"
    purpose = "purpose"
    description = "description"
    starts_at = "starts_at"
    ends_at = "ends_at"
    expected_attendance = "expected_attendance"
    layout_preference = "layout_preference"
    facilities_required = "facilities_required"
    accessibility_needs = "accessibility_needs"
    preliminary_equipment_needs = "preliminary_equipment_needs"
    registration_enabled = "registration_enabled"
    registration_capacity = "registration_capacity"
    registration_opens_at = "registration_opens_at"
    registration_closes_at = "registration_closes_at"


class AmendmentRequest(BaseModel):
    id: str
    message: str
    flagged_fields: list[EventField]
    returned_at: datetime
```

Add `amendment` to `EventResponse`:

```python
class EventResponse(EventFields):
    id: str
    organiser_id: str
    coordinator_id: str | None = None
    status: EventStatus
    technical_readiness: TechnicalReadiness
    submitted_at: datetime | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    # The open amendment while the event is returned (SCRUM-33); null otherwise
    # and on list responses.
    amendment: AmendmentRequest | None = None
```

Append after `EventRejectRequest`:

```python
AMENDMENT_TEXT_MAX_LENGTH = 1000  # [Assumption] REQUIREMENTS §9; same cap as a rejection reason


def _required_text(value, message: str) -> str:
    if not isinstance(value, str):
        raise ValueError(message)
    stripped = value.strip()
    if not stripped:
        raise ValueError(message)
    return stripped


class EventReturnRequest(BaseModel):
    message: str = Field(max_length=AMENDMENT_TEXT_MAX_LENGTH)
    flagged_fields: list[EventField] = []

    @field_validator("message", mode="before")
    @classmethod
    def message_is_not_blank(cls, value):
        return _required_text(value, "A message for the organiser is required.")

    @field_validator("flagged_fields")
    @classmethod
    def flag_each_field_once(cls, value: list[EventField]) -> list[EventField]:
        return list(dict.fromkeys(value))


class EventResubmitRequest(EventUpdateRequest):
    resubmission_note: str = Field(max_length=AMENDMENT_TEXT_MAX_LENGTH)

    @field_validator("resubmission_note", mode="before")
    @classmethod
    def note_is_not_blank(cls, value):
        return _required_text(value, "A resubmission note is required.")
```

- [ ] **Step 4: Add the service functions**

In `backend/app/modules/events/service.py`, extend the schema import:

```python
from app.modules.events.schemas import (
    AmendmentRequest,
    EventCreateRequest,
    EventHistoryEntry,
    EventHistoryResponse,
    EventResponse,
    EventResubmitRequest,
    EventReturnRequest,
    EventStatus,
    EventUpdateRequest,
)
```

Add after `_to_response`:

```python
def _with_amendment(row: dict) -> EventResponse:
    """A single event, carrying its open amendment while it is returned (SCRUM-33)."""
    response = _to_response(row)
    if response.status == EventStatus.returned:
        amendment = repository.get_open_amendment(row["id"])
        if amendment:
            response.amendment = AmendmentRequest(**amendment)
    return response
```

Add after `reject`:

```python
def return_for_amendment(event_id: str, coordinator_id: str, body: EventReturnRequest) -> EventResponse:
    row = _assigned_event(event_id, coordinator_id)
    to_status = lifecycle.target("return", row["status"])
    updated = repository.return_event(
        row["id"], coordinator_id, lifecycle.allowed_from("return"), to_status.value, row["version"],
        message=body.message,
        flagged_fields=[field.value for field in body.flagged_fields],
        notify_message=f'Your event "{row["name"]}" was returned for amendment: {body.message}',
    )
    if not updated:
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return _with_amendment(updated)


def resubmit(event_id: str, organiser_id: str, body: EventResubmitRequest) -> EventResponse:
    """Like `submit`: apply the form's edits, check the request is still complete, then
    move it back to its coordinator. Edits that land before a lost race stay saved; the
    event stays returned and the organiser is told to reload."""
    row = _owned_event(event_id, organiser_id)
    to_status = lifecycle.target("resubmit", row["status"])
    values = body.model_dump(mode="json", exclude_unset=True, exclude={"resubmission_note"})
    _validate_submission({**row, **values})
    if values:
        updated = repository.update_event(event_id, values, row["version"])
        if not updated:
            raise EventConflictError(STALE_EVENT_MESSAGE)
        row = updated
    updated = repository.resubmit_event(
        event_id, organiser_id, lifecycle.allowed_from("resubmit"), to_status.value, row["version"],
        note=body.resubmission_note,
        notify_message=f'"{row["name"]}" was amended and resubmitted: {body.resubmission_note}',
    )
    if not updated:
        raise EventConflictError(STALE_EVENT_MESSAGE)
    return _to_response(updated)
```

Change `read` and `update` to carry the amendment:

```python
def read(event_id: str, user_id: str, role: str = "event_organiser") -> EventResponse:
    return _with_amendment(_visible_event(event_id, user_id, role))
```

and in `update`, replace the final `return _to_response(updated)` with `return _with_amendment(updated)`.

- [ ] **Step 5: Add the routes**

In `backend/app/modules/events/router.py`, extend the schema import with `EventResubmitRequest` and `EventReturnRequest`, and append:

```python
@router.post("/{event_id}/return", response_model=EventResponse)
def return_event(event_id: UUID, body: EventReturnRequest, current_user: EventCoordinator) -> EventResponse:
    return service.return_for_amendment(str(event_id), current_user.id, body)


@router.post("/{event_id}/resubmit", response_model=EventResponse)
def resubmit_event(event_id: UUID, body: EventResubmitRequest, current_user: EventOrganiser) -> EventResponse:
    return service.resubmit(str(event_id), current_user.id, body)
```

- [ ] **Step 6: Run the new tests and confirm they pass**

Run: `pytest tests/test_event_amendment_api.py -v`
Expected: all PASS.

- [ ] **Step 7: Run the full backend suite**

Run: `pytest`
Expected: all PASS, including `test_active_role_access.py`, which now also enumerates `/return` and `/resubmit` (allowed roles get 422 for its empty body, denied roles get 403), and the existing `test_events_api.py` / `test_event_review_api.py`. Those tests don't stub `get_open_amendment`, so if any reads a `returned` event it will try the real client. If one fails that way, stub `repository.get_open_amendment` to `lambda event_id: None` in that test's fixture rather than changing the service.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/events/schemas.py backend/app/modules/events/service.py backend/app/modules/events/router.py backend/tests/test_event_amendment_api.py
git commit -m "feat(events): return a request for amendment and resubmit it

The coordinator returns an under-review request with a message and the
fields to review; the organiser edits and resubmits with a note, back to
the same coordinator (QA-22, QA-77). Resubmission re-runs submission
validation, so a request can't go back incomplete or with a date that
passed while it was returned. Single-event responses, including the
PATCH that saves changes, carry the open amendment so the organiser's
banner survives a save.

SCRUM-33"
```

---

### Task 5: Frontend shared pieces — field labels, API client, review-store action

**Files:**
- Create: `frontend/src/features/events/amendment.js`
- Create: `frontend/src/features/events/__tests__/amendment.spec.js`
- Modify: `frontend/src/services/api.js` (inside `eventsApi`, after `reject`)
- Modify: `frontend/src/features/events/eventReviewStore.js`
- Test: `frontend/src/features/events/__tests__/eventReviewStore.spec.js`

**Interfaces:**
- Produces (`amendment.js`):
  - `EVENT_FIELD_LABELS: Array<{value: string, label: string}>`
  - `AMENDMENT_TEXT_MAX_LENGTH = 1000`
  - `FLAG_TEXT = "Flagged by coordinator"`
  - `fieldLabel(field: string): string`
  - `flaggedFormKeys(flaggedFields?: string[]): Set<string>`, the form-state keys to highlight.
- Produces (`api.js`): `eventsApi.returnForAmendment(eventId, {message, flagged_fields}, token)` and `eventsApi.resubmit(eventId, payload, token)`.
- Produces (`eventReviewStore.js`): `canReturn(status): boolean` and `useEventReviewStore().returnForAmendment(message: string, flaggedFields: string[])`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/features/events/__tests__/amendment.spec.js`:

```js
import { describe, expect, it } from "vitest";

import { AMENDMENT_TEXT_MAX_LENGTH, EVENT_FIELD_LABELS, FLAG_TEXT, fieldLabel, flaggedFormKeys } from "@/features/events/amendment";

describe("amendment field labels (SCRUM-33)", () => {
  it("offers exactly the fields the API accepts, each once", () => {
    const values = EVENT_FIELD_LABELS.map((option) => option.value);

    expect(values).toEqual([
      "name", "purpose", "description", "starts_at", "event_timezone", "ends_at",
      "expected_attendance", "layout_preference", "facilities_required", "accessibility_needs",
      "preliminary_equipment_needs", "registration_enabled", "registration_capacity",
      "registration_opens_at", "registration_closes_at",
    ]);
    expect(new Set(values).size).toBe(values.length);
  });

  it("labels a field with the request form's own wording", () => {
    expect(fieldLabel("expected_attendance")).toBe("Expected attendance");
    expect(fieldLabel("starts_at")).toBe("Proposed date and start time");
  });

  it("falls back to a readable label for a field this client doesn't know", () => {
    expect(fieldLabel("venue_notes")).toBe("venue notes");
  });

  it("maps a flagged date/time field onto every input that edits it", () => {
    expect([...flaggedFormKeys(["starts_at"])]).toEqual(["date", "startTime"]);
    expect([...flaggedFormKeys(["ends_at", "expected_attendance"])]).toEqual(["endTime", "expectedAttendance"]);
  });

  it("ignores unknown or missing flags rather than failing", () => {
    expect(flaggedFormKeys(["venue_notes"]).size).toBe(0);
    expect(flaggedFormKeys().size).toBe(0);
    expect(flaggedFormKeys(null).size).toBe(0);
  });

  it("mirrors the API's limits and wording", () => {
    expect(AMENDMENT_TEXT_MAX_LENGTH).toBe(1000);
    expect(FLAG_TEXT).toBe("Flagged by coordinator");
  });
});
```

In `frontend/src/features/events/__tests__/eventReviewStore.spec.js`:
- change the import to `import { canApprove, canReject, canReturn, REJECT_REASON_MAX_LENGTH, useEventReviewStore } from "@/features/events/eventReviewStore";`
- change the mock to `eventsApi: { get: vi.fn(), history: vi.fn(), approve: vi.fn(), reject: vi.fn(), returnForAmendment: vi.fn() },`
- add this test inside `describe("canApprove / canReject", ...)`:

```js
  it("allows return only from under_review (SCRUM-33)", () => {
    expect(canReturn("under_review")).toBe(true);
    for (const status of ["draft", "submitted", "returned", "planning", "confirmed", "rejected", "cancelled", "completed"]) {
      expect(canReturn(status)).toBe(false);
    }
  });
```

- add this test inside `describe("useEventReviewStore", ...)`:

```js
  it("returns the request with a trimmed message and the flagged fields, then refreshes history", async () => {
    const store = useEventReviewStore();
    store.event = { ...EVENT };
    store.historyEventId = EVENT.id;
    const returnedEvent = { ...EVENT, status: "returned", version: 4,
      amendment: { id: "a1", message: "Confirm attendance", flagged_fields: ["expected_attendance"], returned_at: "2026-09-24T03:00:00Z" } };
    eventsApi.returnForAmendment.mockResolvedValue(returnedEvent);
    eventsApi.history.mockResolvedValue({ entries: [ENTRY] });

    await store.returnForAmendment("  Confirm attendance  ", ["expected_attendance"]);

    expect(eventsApi.returnForAmendment).toHaveBeenCalledWith(
      "event-1", { message: "Confirm attendance", flagged_fields: ["expected_attendance"] }, "access-token",
    );
    expect(store.event.status).toBe("returned");
    expect(store.event.amendment.flagged_fields).toEqual(["expected_attendance"]);
    expect(eventsApi.history).toHaveBeenCalledWith("event-1", "access-token");
  });
```

- [ ] **Step 2: Run them and confirm they fail**

Run (from `frontend/`): `npx vitest run src/features/events/__tests__/amendment.spec.js src/features/events/__tests__/eventReviewStore.spec.js`
Expected: `amendment.spec.js` FAILS to resolve `@/features/events/amendment`. The review-store tests FAIL with `canReturn is not a function` and `store.returnForAmendment is not a function`.

- [ ] **Step 3: Write `amendment.js`**

Create `frontend/src/features/events/amendment.js`:

```js
// SCRUM-33: returning a request for amendment. The fields a coordinator can flag,
// in the request form's order and wording. `value` is the API's `EventField`
// name; the list plugs straight into BauhausCheckboxGroup's `options`.
export const EVENT_FIELD_LABELS = [
  { value: "name", label: "Event title" },
  { value: "purpose", label: "Purpose" },
  { value: "description", label: "Description" },
  { value: "starts_at", label: "Proposed date and start time" },
  { value: "event_timezone", label: "Event timezone" },
  { value: "ends_at", label: "Proposed end time" },
  { value: "expected_attendance", label: "Expected attendance" },
  { value: "layout_preference", label: "Preferred layout" },
  { value: "facilities_required", label: "Facilities required" },
  { value: "accessibility_needs", label: "Accessibility needs" },
  { value: "preliminary_equipment_needs", label: "Preliminary equipment needs" },
  { value: "registration_enabled", label: "Attendee registration" },
  { value: "registration_capacity", label: "Registration capacity" },
  { value: "registration_opens_at", label: "Registration opens" },
  { value: "registration_closes_at", label: "Registration closes" },
];

// Mirrors the API's AMENDMENT_TEXT_MAX_LENGTH ([Assumption], REQUIREMENTS §9).
export const AMENDMENT_TEXT_MAX_LENGTH = 1000;

export const FLAG_TEXT = "Flagged by coordinator";

// The form splits the event's start and end instants into date and time inputs,
// so one API field can highlight more than one input.
const FORM_KEYS_BY_FIELD = {
  name: ["name"],
  purpose: ["purpose"],
  description: ["description"],
  starts_at: ["date", "startTime"],
  event_timezone: ["eventTimezone"],
  ends_at: ["endTime"],
  expected_attendance: ["expectedAttendance"],
  layout_preference: ["layoutPreference"],
  facilities_required: ["facilitiesRequired"],
  accessibility_needs: ["accessibilityNeeds"],
  preliminary_equipment_needs: ["preliminaryEquipmentNeeds"],
  registration_enabled: ["registrationEnabled"],
  registration_capacity: ["registrationCapacity"],
  registration_opens_at: ["registrationOpensAt"],
  registration_closes_at: ["registrationClosesAt"],
};

export function fieldLabel(field) {
  return EVENT_FIELD_LABELS.find((option) => option.value === field)?.label ?? String(field).replaceAll("_", " ");
}

export function flaggedFormKeys(flaggedFields) {
  return new Set((flaggedFields ?? []).flatMap((field) => FORM_KEYS_BY_FIELD[field] ?? []));
}
```

- [ ] **Step 4: Add the API client methods**

In `frontend/src/services/api.js`, inside `eventsApi`, after `reject(...)`:

```js
  // SCRUM-33: the coordinator returns a request; the organiser resubmits it.
  returnForAmendment(eventId, payload, token) {
    return request(`/events/${encodeURIComponent(eventId)}/return`, { method: "POST", body: payload, token });
  },
  resubmit(eventId, payload, token) {
    return request(`/events/${encodeURIComponent(eventId)}/resubmit`, { method: "POST", body: payload, token });
  },
```

- [ ] **Step 5: Add `canReturn` and the store action**

In `frontend/src/features/events/eventReviewStore.js`, after `canReject`:

```js
export function canReturn(status) {
  return status === "under_review";
}
```

and in `actions`, after `reject(reason)`:

```js
    async returnForAmendment(message, flaggedFields) {
      return this.act((token) =>
        eventsApi.returnForAmendment(this.event.id, { message: message.trim(), flagged_fields: flaggedFields }, token),
      );
    },
```

Update the store's doc comment to read `(SCRUM-34 approve, SCRUM-52 reject, SCRUM-33 return)`.

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `npx vitest run src/features/events/__tests__/amendment.spec.js src/features/events/__tests__/eventReviewStore.spec.js`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/events/amendment.js frontend/src/features/events/__tests__/amendment.spec.js frontend/src/services/api.js frontend/src/features/events/eventReviewStore.js frontend/src/features/events/__tests__/eventReviewStore.spec.js
git commit -m "feat(events): add amendment field labels, API calls and the return action

Both roles need the same field names and labels: the coordinator ticks
them, the organiser sees them highlighted. Keeping one list means they
can't drift. Unknown field names fall back to a readable label so an API
ahead of the SPA degrades instead of breaking.

SCRUM-33"
```

---

### Task 6: A `flag` prop on the common form inputs

**Files:**
- Modify: `frontend/src/components/common/BauhausInput.vue`
- Modify: `frontend/src/components/common/BauhausSelect.vue`
- Modify: `frontend/src/components/common/BauhausCheckboxGroup.vue`
- Test: `frontend/src/components/common/__tests__/flaggableInputs.spec.js` (new)

**Interfaces:**
- Produces: an optional `flag: String` prop (default `""`) on all three. When it's set, the control gets `data-flagged="true"` and a highlighted look, the text is shown under it with id `<controlId>-flag`, and the control's `aria-describedby` includes that id. Independent of `error`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/common/__tests__/flaggableInputs.spec.js`:

```js
import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import BauhausCheckboxGroup from "@/components/common/BauhausCheckboxGroup.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";

const mounted = [];

async function mount(component, props) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(component, props) });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el;
}

const OPTIONS = [{ value: "a", label: "Option A" }];

describe("flag prop on common inputs (SCRUM-33)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it.each([
    ["BauhausInput", BauhausInput, { label: "Purpose", modelValue: "" }, "input"],
    ["BauhausSelect", BauhausSelect, { label: "Layout", options: OPTIONS }, "select"],
    ["BauhausCheckboxGroup", BauhausCheckboxGroup, { label: "Facilities", options: OPTIONS }, "fieldset"],
  ])("%s shows the flag and links it to the control", async (_name, component, props, selector) => {
    const el = await mount(component, { ...props, flag: "Flagged by coordinator" });

    const control = el.querySelector(selector);
    const flagId = control.getAttribute("aria-describedby");
    expect(control.dataset.flagged).toBe("true");
    expect(flagId).toBeTruthy();
    expect(el.querySelector(`#${flagId}`).textContent).toContain("Flagged by coordinator");
  });

  it.each([
    ["BauhausInput", BauhausInput, { label: "Purpose", modelValue: "" }, "input"],
    ["BauhausSelect", BauhausSelect, { label: "Layout", options: OPTIONS }, "select"],
    ["BauhausCheckboxGroup", BauhausCheckboxGroup, { label: "Facilities", options: OPTIONS }, "fieldset"],
  ])("%s is unchanged without a flag", async (_name, component, props, selector) => {
    const el = await mount(component, props);

    const control = el.querySelector(selector);
    expect(control.dataset.flagged).toBeUndefined();
    expect(control.getAttribute("aria-describedby")).toBeNull();
    expect(el.textContent).not.toContain("Flagged");
  });

  it("describes an input by both its error and its flag", async () => {
    const el = await mount(BauhausInput, { label: "Purpose", modelValue: "", error: "Enter the event purpose.", flag: "Flagged by coordinator" });

    const ids = el.querySelector("input").getAttribute("aria-describedby").split(" ");
    expect(ids).toHaveLength(2);
    expect(el.textContent).toContain("Enter the event purpose.");
    expect(el.textContent).toContain("Flagged by coordinator");
  });
});
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `npx vitest run src/components/common/__tests__/flaggableInputs.spec.js`
Expected: the "shows the flag" and "error and flag" cases FAIL (`dataset.flagged` is undefined, `aria-describedby` is null). The "unchanged" cases PASS.

- [ ] **Step 3: `BauhausInput.vue`**

Add the prop after `compact`:

```js
  flag: {
    type: String,
    default: "",
  },
```

Replace the `hasError` line with:

```js
const hasError = computed(() => Boolean(props.error));
const hasFlag = computed(() => Boolean(props.flag));
const describedBy = computed(
  () => [hasError.value && `${inputId}-error`, hasFlag.value && `${inputId}-flag`].filter(Boolean).join(" ") || undefined,
);
```

On the `<input>`, replace `:aria-describedby="hasError ? `${inputId}-error` : undefined"` with `:aria-describedby="describedBy"`, add `:data-flagged="hasFlag || undefined"`, and extend the class binding array with `hasFlag ? 'bg-bauhaus-yellow/30' : ''`:

```vue
      :aria-describedby="describedBy"
      :data-flagged="hasFlag || undefined"
      class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium text-ink outline-none transition-colors placeholder:text-ink/40 focus:bg-bauhaus-yellow/20"
      :class="[compact ? 'h-[50px] shadow-none' : 'shadow-hard sm:border-4', hasError ? 'border-bauhaus-red' : 'border-ink', hasFlag ? 'bg-bauhaus-yellow/30' : '']"
```

After the error `<p>`, add:

```vue
    <p v-if="hasFlag" :id="`${inputId}-flag`" class="border-l-4 border-bauhaus-yellow pl-2 text-xs font-bold uppercase tracking-wide text-ink">
      {{ flag }}
    </p>
```

- [ ] **Step 4: `BauhausSelect.vue`**

Add the same `flag` prop after `compact`. Add after `const usesMenu = ...`:

```js
const hasFlag = computed(() => Boolean(props.flag));
const flagId = `${selectId}-flag`;
```

On **both** the menu `<button :id="selectId" ...>` and the native `<select ...>` add:

```vue
        :aria-describedby="hasFlag ? flagId : undefined"
        :data-flagged="hasFlag || undefined"
```

and extend each one's `:class` to an array that includes `hasFlag ? 'bg-bauhaus-yellow/30' : ''`. For example, the native select becomes:

```vue
      :class="[compact ? 'h-[50px] shadow-none' : 'shadow-hard sm:border-4', hasFlag ? 'bg-bauhaus-yellow/30' : '']"
```

Just before the closing `</div>` of the root, after the `<select>`, add:

```vue
    <p v-if="hasFlag" :id="flagId" class="border-l-4 border-bauhaus-yellow pl-2 text-xs font-bold uppercase tracking-wide text-ink">
      {{ flag }}
    </p>
```

- [ ] **Step 5: `BauhausCheckboxGroup.vue`**

Add the `flag` prop after `options`, and after `const groupId = ...`:

```js
const flagId = `${groupId}-flag`;
```

Change the `<fieldset>` opening tag to:

```vue
  <fieldset
    class="flex flex-col gap-2"
    :class="props.flag ? 'bg-bauhaus-yellow/30 p-2' : ''"
    :aria-describedby="props.flag ? flagId : undefined"
    :data-flagged="props.flag ? 'true' : undefined"
  >
```

and after the options `<div>`, before `</fieldset>`:

```vue
    <p v-if="props.flag" :id="flagId" class="border-l-4 border-bauhaus-yellow pl-2 text-xs font-bold uppercase tracking-wide text-ink">
      {{ props.flag }}
    </p>
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `npx vitest run src/components/common/__tests__/flaggableInputs.spec.js`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/common/BauhausInput.vue frontend/src/components/common/BauhausSelect.vue frontend/src/components/common/BauhausCheckboxGroup.vue frontend/src/components/common/__tests__/flaggableInputs.spec.js
git commit -m "feat(ui): let common inputs show a coordinator's flag

A flagged field asks the organiser to review it, which is not a
validation failure, so it gets its own prop and styling rather than
reusing error, and both can show at once. The flag text is linked by
aria-describedby so screen readers announce it with the field.

SCRUM-33"
```

---

### Task 7: Coordinator returns a request — `ReturnEventModal`, `AmendmentBanner`, view wiring

**Files:**
- Create: `frontend/src/components/events/ReturnEventModal.vue`
- Create: `frontend/src/components/events/__tests__/ReturnEventModal.spec.js`
- Create: `frontend/src/components/events/AmendmentBanner.vue`
- Create: `frontend/src/components/events/__tests__/AmendmentBanner.spec.js`
- Modify: `frontend/src/views/events/CoordinatorEventView.vue`
- Test: `frontend/src/views/__tests__/CoordinatorEventView.spec.js`

**Interfaces:**
- Consumes: `EVENT_FIELD_LABELS`, `AMENDMENT_TEXT_MAX_LENGTH`, `fieldLabel` (Task 5); `canReturn` and `review.returnForAmendment` (Task 5).
- Produces:
  - `<ReturnEventModal :open :event-name :busy :error @confirm="({ message, flaggedFields }) => …" @cancel>`. The confirm button's `aria-label` is `"Return request"`.
  - `<AmendmentBanner :amendment audience="organiser|coordinator">` with a default slot for actions and a root `data-testid="amendment-banner"`.

- [ ] **Step 1: Write the failing component tests**

Create `frontend/src/components/events/__tests__/ReturnEventModal.spec.js`:

```js
import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import ReturnEventModal from "@/components/events/ReturnEventModal.vue";

const mounted = [];

async function mountModal(props = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(ReturnEventModal, { open: true, eventName: "Partner Summit", onConfirm, onCancel, ...props }),
  });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return { onConfirm, onCancel };
}

function typeMessage(text) {
  const textarea = document.querySelector("textarea");
  textarea.value = text;
  textarea.dispatchEvent(new Event("input"));
  return nextTick();
}

function tick(label) {
  const box = [...document.querySelectorAll('input[type="checkbox"]')]
    .find((input) => input.closest("label").textContent.includes(label));
  box.checked = true;
  box.dispatchEvent(new Event("change"));
  return nextTick();
}

const confirmButton = () => document.querySelector('button[aria-label="Return request"]');

describe("ReturnEventModal (SCRUM-33)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("names the event, asks for a message and offers every flaggable field", async () => {
    await mountModal();

    expect(document.body.textContent).toContain("Partner Summit");
    expect(document.querySelector("textarea").getAttribute("maxlength")).toBe("1000");
    expect(document.querySelectorAll('input[type="checkbox"]')).toHaveLength(15);
  });

  it("cannot be confirmed without a message, even with fields flagged", async () => {
    await mountModal();
    await tick("Expected attendance");

    expect(confirmButton().disabled).toBe(true);
  });

  it("cannot be confirmed with a whitespace-only message", async () => {
    await mountModal();
    await typeMessage("   \n ");

    expect(confirmButton().disabled).toBe(true);
  });

  it("emits the trimmed message and the flagged fields", async () => {
    const { onConfirm } = await mountModal();
    await typeMessage("  Please confirm the attendance  ");
    await tick("Expected attendance");

    confirmButton().click();

    expect(onConfirm).toHaveBeenCalledWith({ message: "Please confirm the attendance", flaggedFields: ["expected_attendance"] });
  });

  it("shows how many characters are used", async () => {
    await mountModal();
    await typeMessage("Confirm");

    expect(document.body.textContent).toContain("7 / 1000");
  });

  it("is disabled while the request is in flight", async () => {
    await mountModal({ busy: true });
    await typeMessage("Confirm");

    expect(confirmButton().disabled).toBe(true);
  });

  it("shows the API's error", async () => {
    await mountModal({ error: "Cannot return an event that is planning" });

    expect(document.querySelector('[role="alert"]').textContent).toContain("Cannot return an event that is planning");
  });

  it("emits cancel", async () => {
    const { onCancel } = await mountModal();

    document.querySelector('button[aria-label="Cancel"]').click();

    expect(onCancel).toHaveBeenCalled();
  });
});
```

Create `frontend/src/components/events/__tests__/AmendmentBanner.spec.js`:

```js
import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it } from "vitest";

import AmendmentBanner from "@/components/events/AmendmentBanner.vue";

const AMENDMENT = {
  id: "a1",
  message: "Please confirm the attendance",
  flagged_fields: ["expected_attendance", "starts_at"],
  returned_at: "2026-09-24T03:00:00Z",
};

const mounted = [];

async function mount(props, slot) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(AmendmentBanner, props, slot ? { default: slot } : undefined) });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el;
}

describe("AmendmentBanner (SCRUM-33)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("shows the organiser the coordinator's message and the fields to review", async () => {
    const el = await mount({ amendment: AMENDMENT });

    expect(el.textContent).toContain("Your coordinator asked for changes");
    expect(el.textContent).toContain("Please confirm the attendance");
    expect(el.textContent).toContain("Expected attendance");
    expect(el.textContent).toContain("Proposed date and start time");
  });

  it("tells the coordinator it is waiting on the organiser", async () => {
    const el = await mount({ amendment: AMENDMENT, audience: "coordinator" });

    expect(el.textContent).toContain("Waiting for the organiser to amend");
  });

  it("shows when it was returned, in Singapore time", async () => {
    const el = await mount({ amendment: AMENDMENT });

    expect(el.textContent).toContain("24 Sept 2026");
    expect(el.textContent).toContain("11:00");
  });

  it("omits the field list when nothing was flagged", async () => {
    const el = await mount({ amendment: { ...AMENDMENT, flagged_fields: [] } });

    expect(el.textContent).not.toContain("Fields to review");
  });

  it("renders an unknown field readably", async () => {
    const el = await mount({ amendment: { ...AMENDMENT, flagged_fields: ["venue_notes"] } });

    expect(el.textContent).toContain("venue notes");
  });

  it("renders actions passed in its slot", async () => {
    const el = await mount({ amendment: AMENDMENT }, () => h("button", "Amend and resubmit"));

    expect(el.querySelector("button").textContent).toBe("Amend and resubmit");
  });
});
```

- [ ] **Step 2: Write the failing view tests**

In `frontend/src/views/__tests__/CoordinatorEventView.spec.js`:
- change the mock to `eventsApi: { get: vi.fn(), history: vi.fn(), approve: vi.fn(), reject: vi.fn(), returnForAmendment: vi.fn() },`
- change the `it.each` "offers no decision" block so it also asserts `expect(button("Open return dialog")).toBeNull();`
- add these tests inside the `describe`:

```js
  it("offers return for a request under review, and not while planning", async () => {
    await mountView(eventResponse());
    expect(button("Open return dialog")).not.toBeNull();

    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
    await mountView(eventResponse({ status: "planning" }));
    expect(button("Open return dialog")).toBeNull();
  });

  it("returns the request with the message and flagged fields, then shows it waiting on the organiser", async () => {
    const el = await mountView(eventResponse());
    eventsApi.returnForAmendment.mockResolvedValue(eventResponse({
      status: "returned", version: 4,
      amendment: { id: "a1", message: "Confirm attendance", flagged_fields: ["expected_attendance"], returned_at: "2026-09-24T03:00:00Z" },
    }));

    button("Open return dialog").click();
    await nextTick();
    const textarea = document.querySelector("textarea");
    textarea.value = "Confirm attendance";
    textarea.dispatchEvent(new Event("input"));
    const box = [...document.querySelectorAll('input[type="checkbox"]')]
      .find((input) => input.closest("label").textContent.includes("Expected attendance"));
    box.checked = true;
    box.dispatchEvent(new Event("change"));
    await nextTick();
    button("Return request").click();

    await vi.waitFor(() => expect(eventsApi.returnForAmendment).toHaveBeenCalledWith(
      "event-1", { message: "Confirm attendance", flagged_fields: ["expected_attendance"] }, "access",
    ));
    await vi.waitFor(() => expect(el.textContent).toContain("Waiting for the organiser to amend"));
    expect(el.textContent).toContain("Returned for amendment");
    expect(button("Approve request")).toBeNull();
    expect(button("Open return dialog")).toBeNull();
  });
```

- [ ] **Step 3: Run them and confirm they fail**

Run: `npx vitest run src/components/events/__tests__/ReturnEventModal.spec.js src/components/events/__tests__/AmendmentBanner.spec.js src/views/__tests__/CoordinatorEventView.spec.js`
Expected: both component specs FAIL to resolve their `.vue` files. The two new view tests FAIL because `button("Open return dialog")` is null.

- [ ] **Step 4: Write `AmendmentBanner.vue`**

Create `frontend/src/components/events/AmendmentBanner.vue`:

```vue
<script setup>
import { computed } from "vue";

import { fieldLabel } from "@/features/events/amendment";

// SCRUM-33: the coordinator's open amendment request, shown to both sides.
const props = defineProps({
  amendment: { type: Object, required: true },
  // "organiser" (asked to amend) or "coordinator" (waiting on the organiser).
  audience: { type: String, default: "organiser" },
});

const heading = computed(() =>
  props.audience === "coordinator" ? "Waiting for the organiser to amend" : "Your coordinator asked for changes",
);

// Stored UTC, displayed in Asia/Singapore (REQUIREMENTS §4).
const returnedAt = computed(() =>
  new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore" })
    .format(new Date(props.amendment.returned_at)),
);
</script>

<template>
  <section data-testid="amendment-banner" class="border-4 border-ink bg-bauhaus-yellow p-6 text-ink shadow-hard sm:p-8">
    <h2 class="text-2xl font-black uppercase tracking-tight">{{ heading }}</h2>
    <p class="mt-1 text-xs font-bold uppercase tracking-widest text-ink/70">Returned {{ returnedAt }}</p>
    <p class="mt-4 whitespace-pre-wrap font-medium">{{ props.amendment.message }}</p>
    <div v-if="props.amendment.flagged_fields?.length" class="mt-4">
      <p class="text-xs font-bold uppercase tracking-widest">Fields to review</p>
      <ul class="mt-2 flex flex-wrap gap-2">
        <li
          v-for="field in props.amendment.flagged_fields"
          :key="field"
          class="border-2 border-ink bg-canvas px-3 py-1 text-xs font-bold uppercase tracking-wide"
        >
          {{ fieldLabel(field) }}
        </li>
      </ul>
    </div>
    <div v-if="$slots.default" class="mt-6"><slot /></div>
  </section>
</template>
```

- [ ] **Step 5: Write `ReturnEventModal.vue`**

Create `frontend/src/components/events/ReturnEventModal.vue`:

```vue
<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCheckboxGroup from "@/components/common/BauhausCheckboxGroup.vue";
import { AMENDMENT_TEXT_MAX_LENGTH, EVENT_FIELD_LABELS } from "@/features/events/amendment";

// SCRUM-33: the coordinator's message and the fields to review. A sibling of
// RejectEventModal; the API is the enforcement point for both rules shown here.
const props = defineProps({
  open: { type: Boolean, default: false },
  eventName: { type: String, required: true },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const emit = defineEmits(["confirm", "cancel"]);

const message = ref("");
const flaggedFields = ref([]);
const trimmed = computed(() => message.value.trim());
const canConfirm = computed(() => trimmed.value.length > 0 && !props.busy);

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      message.value = "";
      flaggedFields.value = [];
    }
  },
);

function confirm() {
  if (!canConfirm.value) return;
  // Keep the form's order, not the order the boxes were ticked in.
  const ordered = EVENT_FIELD_LABELS.map((option) => option.value).filter((value) => flaggedFields.value.includes(value));
  emit("confirm", { message: trimmed.value, flaggedFields: ordered });
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="props.open"
      class="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-ink/60 px-4 py-6"
      role="presentation"
      @click.self="emit('cancel')"
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="return-modal-title"
        class="w-full max-w-2xl border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <h2 id="return-modal-title" class="text-2xl font-black uppercase leading-tight tracking-tight">Return for amendment?</h2>
        <p class="mt-4 text-base font-medium">
          "{{ props.eventName }}" goes back to the organiser to edit and resubmit. Planning waits until they do.
        </p>
        <label for="return-message" class="mt-6 block text-xs font-bold uppercase tracking-widest text-ink/70">Message to the organiser (required)</label>
        <textarea
          id="return-message"
          v-model="message"
          rows="4"
          :maxlength="AMENDMENT_TEXT_MAX_LENGTH"
          class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
        ></textarea>
        <p class="mt-1 text-right text-xs font-bold text-ink/70">{{ message.length }} / {{ AMENDMENT_TEXT_MAX_LENGTH }}</p>
        <div class="mt-4">
          <BauhausCheckboxGroup v-model="flaggedFields" label="Fields to review (optional)" :options="EVENT_FIELD_LABELS" />
        </div>
        <p
          v-if="props.error"
          role="alert"
          class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas"
        >
          {{ props.error }}
        </p>
        <div class="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <BauhausButton type="button" variant="outline" aria-label="Cancel" @click="emit('cancel')">Cancel</BauhausButton>
          <BauhausButton type="button" variant="primary" aria-label="Return request" :disabled="!canConfirm" @click="confirm">
            Return request
          </BauhausButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
```

- [ ] **Step 6: Wire the coordinator view**

In `frontend/src/views/events/CoordinatorEventView.vue`:

Imports:

```js
import AmendmentBanner from "@/components/events/AmendmentBanner.vue";
import ReturnEventModal from "@/components/events/ReturnEventModal.vue";
import { canApprove, canReject, canReturn, useEventReviewStore } from "@/features/events/eventReviewStore";
```

State and computed, next to the existing ones:

```js
const isReturnOpen = ref(false);
const showReturn = computed(() => canReturn(event.value?.status));
```

Handler after `confirmReject`:

```js
async function confirmReturn({ message, flaggedFields }) {
  try {
    await review.returnForAmendment(message, flaggedFields);
    isReturnOpen.value = false;
    showToast("Returned to organiser");
  } catch {
    // Kept open so the coordinator sees the error beside their message.
  }
}
```

Change the page alert's condition to `v-if="review.error && !isRejectOpen && !isReturnOpen"`.

Change the actions row condition to `v-if="showApprove || showReject || showReturn"`, and add between Approve and Reject:

```vue
          <BauhausButton
            v-if="showReturn"
            variant="yellow"
            aria-label="Open return dialog"
            :disabled="review.isActing"
            @click="review.error = null; isReturnOpen = true"
          >
            Return for amendment
          </BauhausButton>
```

Right after the header `</BauhausCard>` (before the details grid), add:

```vue
      <AmendmentBanner
        v-if="event.status === 'returned' && event.amendment"
        :amendment="event.amendment"
        audience="coordinator"
        class="mb-8"
      />
```

Next to `<RejectEventModal …/>`, add:

```vue
    <ReturnEventModal
      v-if="event"
      :open="isReturnOpen"
      :event-name="event.name"
      :busy="review.isActing"
      :error="isReturnOpen ? review.error : null"
      @confirm="confirmReturn"
      @cancel="isReturnOpen = false"
    />
```

- [ ] **Step 7: Run the tests and confirm they pass**

Run: `npx vitest run src/components/events/__tests__/ReturnEventModal.spec.js src/components/events/__tests__/AmendmentBanner.spec.js src/views/__tests__/CoordinatorEventView.spec.js`
Expected: all PASS. If the date assertion in `AmendmentBanner.spec.js` fails only on the month abbreviation ("Sep" vs "Sept"), check what this Node's ICU prints for `en-SG` and match it in the test. The timezone assertion (`11:00`) must still hold.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/events/ReturnEventModal.vue frontend/src/components/events/AmendmentBanner.vue frontend/src/components/events/__tests__/ReturnEventModal.spec.js frontend/src/components/events/__tests__/AmendmentBanner.spec.js frontend/src/views/events/CoordinatorEventView.vue frontend/src/views/__tests__/CoordinatorEventView.spec.js
git commit -m "feat(events): let the coordinator return a request for amendment

Adds Return for amendment beside Approve and Reject on the review page,
with a required message and optional fields to review. Once returned,
the page shows the amendment and offers no decision until the organiser
resubmits (QA-22).

SCRUM-33"
```

---

### Task 8: Organiser store `resubmit` and `ResubmitEventModal`

**Files:**
- Modify: `frontend/src/stores/events.js` (actions, after `submit`)
- Test: `frontend/src/stores/__tests__/events.spec.js`
- Create: `frontend/src/components/events/ResubmitEventModal.vue`
- Create: `frontend/src/components/events/__tests__/ResubmitEventModal.spec.js`

**Interfaces:**
- Consumes: `eventsApi.resubmit` and `AMENDMENT_TEXT_MAX_LENGTH` (Task 5).
- Produces:
  - `useEventsStore().resubmit(eventId: string, event: FormState, note: string) => Promise<FormState>`
  - `<ResubmitEventModal :open :event-name :busy :error @confirm="(note) => …" @cancel>`. The confirm button's `aria-label` is `"Resubmit request"`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/stores/__tests__/events.spec.js`, add `resubmit: vi.fn()` to the mocked `eventsApi`, and add inside `describe("event store", ...)`:

```js
  it("resubmits a returned request with the form's fields and a trimmed note (SCRUM-33)", async () => {
    const store = signedInStore();
    eventsApi.resubmit.mockResolvedValue({ id: "e1", name: "Planning workshop", status: "under_review", amendment: null });
    const form = { ...emptyEvent(), name: "Planning workshop", expectedAttendance: "40" };

    const result = await store.resubmit("e1", form, "  Attendance is now 40  ");

    expect(eventsApi.resubmit).toHaveBeenCalledWith(
      "e1", { ...eventToPayload(form), resubmission_note: "Attendance is now 40" }, "access",
    );
    expect(result.status).toBe("under_review");
    expect(store.events.find((event) => event.id === "e1").status).toBe("under_review");
  });

  it("keeps the API's error when a resubmission is refused", async () => {
    const store = signedInStore();
    eventsApi.resubmit.mockRejectedValue(new ApiError("Cannot resubmit an event that is under review", 409));

    await expect(store.resubmit("e1", { ...emptyEvent(), name: "Planning workshop" }, "note")).rejects.toThrow();

    expect(store.error).toBe("Cannot resubmit an event that is under review");
    expect(store.isSaving).toBe(false);
  });
```

Create `frontend/src/components/events/__tests__/ResubmitEventModal.spec.js`:

```js
import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import ResubmitEventModal from "@/components/events/ResubmitEventModal.vue";

const mounted = [];

async function mountModal(props = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({
    render: () => h(ResubmitEventModal, { open: true, eventName: "Partner Summit", onConfirm, onCancel, ...props }),
  });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return { onConfirm, onCancel };
}

function typeNote(text) {
  const textarea = document.querySelector("textarea");
  textarea.value = text;
  textarea.dispatchEvent(new Event("input"));
  return nextTick();
}

const confirmButton = () => document.querySelector('button[aria-label="Resubmit request"]');

describe("ResubmitEventModal (SCRUM-33)", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("names the event and asks what changed", async () => {
    await mountModal();

    expect(document.body.textContent).toContain("Partner Summit");
    expect(document.querySelector("textarea").getAttribute("maxlength")).toBe("1000");
  });

  it("cannot be confirmed without a note", async () => {
    await mountModal();
    await typeNote("   ");

    expect(confirmButton().disabled).toBe(true);
  });

  it("emits the trimmed note", async () => {
    const { onConfirm } = await mountModal();
    await typeNote("  Attendance is now 40  ");

    confirmButton().click();

    expect(onConfirm).toHaveBeenCalledWith("Attendance is now 40");
  });

  it("can't be sent twice while the first is in flight", async () => {
    await mountModal({ busy: true });
    await typeNote("Attendance is now 40");

    expect(confirmButton().disabled).toBe(true);
  });

  it("shows the API's error", async () => {
    await mountModal({ error: "This event was updated by someone else. Reload." });

    expect(document.querySelector('[role="alert"]').textContent).toContain("updated by someone else");
  });

  it("emits cancel", async () => {
    const { onCancel } = await mountModal();

    document.querySelector('button[aria-label="Cancel"]').click();

    expect(onCancel).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `npx vitest run src/stores/__tests__/events.spec.js src/components/events/__tests__/ResubmitEventModal.spec.js`
Expected: the store tests FAIL with `store.resubmit is not a function`. The modal spec FAILS to resolve the `.vue` file.

- [ ] **Step 3: Add the store action**

In `frontend/src/stores/events.js`, after `submit(eventId, event)`:

```js
    // SCRUM-33: send a returned request back to its coordinator with the form's
    // edits and the organiser's note, in one request (like submit).
    async resubmit(eventId, event, note) {
      return this.save((token) =>
        eventsApi.resubmit(eventId, { ...eventToPayload(event), resubmission_note: note.trim() }, token),
      );
    },
```

- [ ] **Step 4: Write `ResubmitEventModal.vue`**

Create `frontend/src/components/events/ResubmitEventModal.vue`:

```vue
<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import { AMENDMENT_TEXT_MAX_LENGTH } from "@/features/events/amendment";

// SCRUM-33: the organiser's resubmission note, required by the API (§5 guard).
const props = defineProps({
  open: { type: Boolean, default: false },
  eventName: { type: String, required: true },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const emit = defineEmits(["confirm", "cancel"]);

const note = ref("");
const trimmed = computed(() => note.value.trim());
const canConfirm = computed(() => trimmed.value.length > 0 && !props.busy);

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) note.value = "";
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
        aria-labelledby="resubmit-modal-title"
        class="w-full max-w-lg border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <h2 id="resubmit-modal-title" class="text-2xl font-black uppercase leading-tight tracking-tight">Resubmit this request?</h2>
        <p class="mt-4 text-base font-medium">
          "{{ props.eventName }}" goes back to your coordinator for review. Tell them what you changed.
        </p>
        <label for="resubmit-note" class="mt-6 block text-xs font-bold uppercase tracking-widest text-ink/70">What changed (required)</label>
        <textarea
          id="resubmit-note"
          v-model="note"
          rows="4"
          :maxlength="AMENDMENT_TEXT_MAX_LENGTH"
          class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
        ></textarea>
        <p class="mt-1 text-right text-xs font-bold text-ink/70">{{ note.length }} / {{ AMENDMENT_TEXT_MAX_LENGTH }}</p>
        <p
          v-if="props.error"
          role="alert"
          class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas"
        >
          {{ props.error }}
        </p>
        <div class="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <BauhausButton type="button" variant="outline" aria-label="Cancel" @click="emit('cancel')">Cancel</BauhausButton>
          <BauhausButton type="button" variant="primary" aria-label="Resubmit request" :disabled="!canConfirm" @click="confirm">
            Resubmit request
          </BauhausButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `npx vitest run src/stores/__tests__/events.spec.js src/components/events/__tests__/ResubmitEventModal.spec.js`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/stores/events.js frontend/src/stores/__tests__/events.spec.js frontend/src/components/events/ResubmitEventModal.vue frontend/src/components/events/__tests__/ResubmitEventModal.spec.js
git commit -m "feat(events): add the organiser's resubmit action and note dialog

Resubmission sends the form's edits and the required note in one request,
the same shape as submit, so the organiser can't resubmit stale values.

SCRUM-33"
```

---

### Task 9: Organiser amends and resubmits on the request form; dashboard and detail page route there

**Files:**
- Modify: `frontend/src/views/events/EventRequestView.vue`
- Create: `frontend/src/views/__tests__/EventRequestView.spec.js`
- Modify: `frontend/src/views/dashboards/OrganiserDashboard.vue:166-173` (`eventAction`)
- Test: `frontend/src/views/__tests__/OrganiserDashboard.spec.js`
- Modify: `frontend/src/views/events/EventDetailView.vue`
- Test: `frontend/src/views/__tests__/EventDetailView.spec.js`

**Interfaces:**
- Consumes: `AmendmentBanner` (Task 7), `ResubmitEventModal` and `eventsStore.resubmit` (Task 8), `flaggedFormKeys` and `FLAG_TEXT` (Task 5), the `flag` prop (Task 6), and the existing `eventsStore.get(id)`, which keeps `amendment` on the normalised event because `fromResponse` spreads the response.
- Produces: `/events/new?id=<returned id>` opens the returned request in amend mode.

- [ ] **Step 1: Write the failing form tests**

Create `frontend/src/views/__tests__/EventRequestView.spec.js`:

```js
import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), submit: vi.fn(), resubmit: vi.fn() },
}));

const AMENDMENT = {
  id: "a1", message: "Please confirm the attendance",
  flagged_fields: ["expected_attendance", "starts_at"], returned_at: "2026-09-24T03:00:00Z",
};

function returnedEvent(overrides = {}) {
  return {
    id: "returned-1", name: "Product Briefing", status: "returned", event_timezone: "Asia/Singapore",
    purpose: "Brief partners", description: null,
    starts_at: "2026-12-01T02:00:00Z", ends_at: "2026-12-01T04:00:00Z",
    expected_attendance: 40, layout_preference: "theatre", facilities_required: [],
    accessibility_needs: null, preliminary_equipment_needs: null, registration_enabled: false,
    registration_capacity: null, registration_opens_at: null, registration_closes_at: null,
    coordinator_id: "coordinator-1", version: 4, amendment: AMENDMENT,
    ...overrides,
  };
}

const mountedApps = [];

async function mountForm(listed, detail) {
  eventsApi.list.mockResolvedValue(listed);
  eventsApi.get.mockResolvedValue(detail);
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "organiser-1", full_name: "Priya Nair", role: "event_organiser" };
  auth.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "event-new", query: { id: detail.id } });
  const { default: View } = await import("@/views/events/EventRequestView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await vi.waitFor(() => expect(el.querySelector("input").value).toBe(detail.name));
  await nextTick();
  return { el, router };
}

const labelled = (el, label) =>
  [...el.querySelectorAll("label")].find((node) => node.textContent.trim().startsWith(label));
const controlFor = (el, label) => document.getElementById(labelled(el, label).getAttribute("for"));
const buttonByText = (el, text) => [...el.querySelectorAll("button")].find((node) => node.textContent.trim() === text);

describe("EventRequestView amending a returned request (SCRUM-33)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("opens the returned request with the coordinator's message and fields to review", async () => {
    const { el } = await mountForm([returnedEvent({ amendment: null })], returnedEvent());

    expect(eventsApi.get).toHaveBeenCalledWith("returned-1", "access");
    expect(el.textContent).toContain("Amend your request");
    expect(el.querySelector('[data-testid="amendment-banner"]').textContent).toContain("Please confirm the attendance");
  });

  it("highlights every input behind a flagged field and nothing else", async () => {
    const { el } = await mountForm([returnedEvent({ amendment: null })], returnedEvent());

    expect(controlFor(el, "Expected attendance").dataset.flagged).toBe("true");
    expect(controlFor(el, "Proposed event date").dataset.flagged).toBe("true");
    expect(controlFor(el, "Proposed start time").dataset.flagged).toBe("true");
    expect(controlFor(el, "Purpose").dataset.flagged).toBeUndefined();
    expect(controlFor(el, "Proposed end time").dataset.flagged).toBeUndefined();
  });

  it("offers Resubmit and Save changes instead of Submit request and Save draft", async () => {
    const { el } = await mountForm([returnedEvent({ amendment: null })], returnedEvent());

    expect(buttonByText(el, "Resubmit")).toBeTruthy();
    expect(buttonByText(el, "Save changes")).toBeTruthy();
    expect(buttonByText(el, "Submit request")).toBeUndefined();
    expect(buttonByText(el, "Save draft")).toBeUndefined();
  });

  it("resubmits the edited request with a note and returns to the dashboard", async () => {
    const { el, router } = await mountForm([returnedEvent({ amendment: null })], returnedEvent());
    eventsApi.resubmit.mockResolvedValue(returnedEvent({ status: "under_review", expected_attendance: 60, amendment: null, version: 6 }));
    const attendance = controlFor(el, "Expected attendance");
    attendance.value = "60";
    attendance.dispatchEvent(new Event("input"));
    await nextTick();

    buttonByText(el, "Resubmit").click();
    await nextTick();
    const note = document.querySelector("#resubmit-note");
    note.value = "Attendance is now 60";
    note.dispatchEvent(new Event("input"));
    await nextTick();
    document.querySelector('button[aria-label="Resubmit request"]').click();

    await vi.waitFor(() => expect(eventsApi.resubmit).toHaveBeenCalled());
    const [id, payload, token] = eventsApi.resubmit.mock.calls[0];
    expect(id).toBe("returned-1");
    expect(payload.expected_attendance).toBe(60);
    expect(payload.resubmission_note).toBe("Attendance is now 60");
    expect(token).toBe("access");
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("dashboard-organiser"));
  });

  it("keeps the banner and highlights after Save changes", async () => {
    const { el } = await mountForm([returnedEvent({ amendment: null })], returnedEvent());
    eventsApi.update.mockResolvedValue(returnedEvent({ purpose: "Brief our partners", version: 5 }));
    const purpose = controlFor(el, "Purpose");
    purpose.value = "Brief our partners";
    purpose.dispatchEvent(new Event("input"));
    await nextTick();

    buttonByText(el, "Save changes").click();

    await vi.waitFor(() => expect(eventsApi.update).toHaveBeenCalled());
    await nextTick();
    expect(el.querySelector('[data-testid="amendment-banner"]')).not.toBeNull();
    expect(controlFor(el, "Expected attendance").dataset.flagged).toBe("true");
  });

  it("still opens and resubmits a returned request that has no amendment on record", async () => {
    const { el } = await mountForm([returnedEvent({ amendment: null })], returnedEvent({ amendment: null }));

    expect(el.textContent).toContain("Amend your request");
    expect(el.querySelector('[data-testid="amendment-banner"]')).toBeNull();
    expect(buttonByText(el, "Resubmit")).toBeTruthy();
  });

  it("leaves a draft in draft mode", async () => {
    const draft = returnedEvent({ id: "draft-1", status: "draft", amendment: null });
    const { el } = await mountForm([draft], draft);

    expect(el.textContent).toContain("Edit your draft");
    expect(buttonByText(el, "Submit request")).toBeTruthy();
    expect(el.querySelector('[data-testid="amendment-banner"]')).toBeNull();
  });
});
```

- [ ] **Step 2: Write the failing dashboard and detail-page tests**

In `frontend/src/views/__tests__/OrganiserDashboard.spec.js`, add after the "opens a draft through the existing request flow" test:

```js
  it("opens a returned request on the request form to amend and resubmit (SCRUM-33)", async () => {
    const { el, router } = await mountDashboard();
    await openEvents(el);

    buttonByText(el, "Amend and resubmit").click();

    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-new"));
    expect(router.currentRoute.value.query.id).toBe("returned-1");
  });
```

In `frontend/src/views/__tests__/EventDetailView.spec.js`, add inside the `describe`:

```js
  it("shows the coordinator's amendment request and a way to amend it (SCRUM-33)", async () => {
    const el = await mountDetail(eventResponse({
      status: "returned",
      amendment: { id: "a1", message: "Please confirm the attendance", flagged_fields: ["expected_attendance"], returned_at: "2026-09-24T03:00:00Z" },
    }));

    const banner = el.querySelector('[data-testid="amendment-banner"]');
    expect(banner.textContent).toContain("Please confirm the attendance");
    const { default: router } = await import("@/router");
    [...banner.querySelectorAll("button")].find((node) => node.textContent.trim() === "Amend and resubmit").click();
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-new"));
    expect(router.currentRoute.value.query.id).toBe("event-1");
  });

  it("shows no amendment banner for a request that isn't returned", async () => {
    const el = await mountDetail(eventResponse({ status: "under_review" }));

    expect(el.querySelector('[data-testid="amendment-banner"]')).toBeNull();
  });
```

- [ ] **Step 3: Run them and confirm they fail**

Run: `npx vitest run src/views/__tests__/EventRequestView.spec.js src/views/__tests__/OrganiserDashboard.spec.js src/views/__tests__/EventDetailView.spec.js`
Expected: the `EventRequestView` tests FAIL: the form stays empty because `onMounted` only loads drafts, so the initial `waitFor` times out (except "leaves a draft in draft mode", which may pass). The dashboard test FAILS with the route `event-detail` instead of `event-new`. The detail test FAILS because the banner is null.

- [ ] **Step 4: Put `EventRequestView` into amend mode for returned requests**

In `frontend/src/views/events/EventRequestView.vue`:

Imports:

```js
import AmendmentBanner from "@/components/events/AmendmentBanner.vue";
import ResubmitEventModal from "@/components/events/ResubmitEventModal.vue";
import { FLAG_TEXT, flaggedFormKeys } from "@/features/events/amendment";
```

State, after `const isNew = ...`:

```js
// SCRUM-33: a returned request is amended here and resubmitted to its coordinator.
const isReturned = computed(() => form.status === "returned");
const flaggedKeys = computed(() => flaggedFormKeys(form.amendment?.flagged_fields));
const isResubmitModalOpen = ref(false);

function flagFor(key) {
  return flaggedKeys.value.has(key) ? FLAG_TEXT : "";
}
```

Replace `requestSubmit`:

```js
function requestSubmit() {
  intent.value = "submit";
  if (!validateSubmission()) return;
  if (isReturned.value) isResubmitModalOpen.value = true;
  else isSubmitModalOpen.value = true;
}
```

Add after `confirmSubmit`:

```js
async function confirmResubmit(note) {
  try {
    await eventsStore.resubmit(form.id, form, note);
  } catch {
    return; // The modal stays open and shows the API's message.
  }
  isResubmitModalOpen.value = false;
  pristineSnapshot.value = serializeForm(form);
  showToast("Request resubmitted");
  await router.push({ name: "dashboard-organiser" });
}
```

In `save()`, change the draft-save toast so it matches the mode:

```js
      showToast(isReturned.value ? "Changes saved" : "Draft saved");
```

(`Object.assign(form, event)` right after it now keeps `amendment`, because the PATCH response carries it; see Task 4.)

Replace the draft lookup in `onMounted`:

```js
onMounted(async () => {
  try {
    if (!eventsStore.events.length) await eventsStore.load();
  } catch {
    return;
  }
  const stored = eventsStore.events.find(
    (event) => event.id === route.query.id && ["draft", "returned"].includes(event.status),
  );
  if (stored?.status === "returned") {
    // The list omits the amendment; the single-event read carries it.
    try {
      Object.assign(form, await eventsStore.get(stored.id));
    } catch {
      return;
    }
  } else if (stored) {
    Object.assign(form, stored);
  }
  pristineSnapshot.value = serializeForm(form);
});
```

Template changes:

1. Heading: `{{ isNew ? "Start an event" : isReturned ? "Amend your request" : "Edit your draft" }}`.
2. Directly after the header `</BauhausCard>`, add:

```vue
    <AmendmentBanner v-if="isReturned && form.amendment" :amendment="form.amendment" class="mb-10" />
```

3. Page alert: `v-if="eventsStore.error && !isResubmitModalOpen"`.
4. Add `:flag="flagFor('<key>')"` to each control:
   - `BauhausInput` name → `flagFor('name')`
   - purpose → `'purpose'`
   - date → `'date'`
   - startTime → `'startTime'`
   - endTime → `'endTime'`
   - expectedAttendance → `'expectedAttendance'`
   - accessibilityNeeds → `'accessibilityNeeds'`
   - preliminaryEquipmentNeeds → `'preliminaryEquipmentNeeds'`
   - registrationCapacity → `'registrationCapacity'`
   - registrationOpensAt → `'registrationOpensAt'`
   - registrationClosesAt → `'registrationClosesAt'`
   - `BauhausSelect` eventTimezone → `'eventTimezone'`
   - layoutPreference → `'layoutPreference'`
   - `BauhausCheckboxGroup` facilitiesRequired → `'facilitiesRequired'`
5. Description textarea (raw, not a common input): add `:aria-describedby="flagFor('description') ? 'event-description-flag' : undefined"`, `:data-flagged="flagFor('description') ? 'true' : undefined"` and `:class="flagFor('description') ? 'bg-bauhaus-yellow/30' : ''"`, and after it:

```vue
            <p v-if="flagFor('description')" id="event-description-flag" class="border-l-4 border-bauhaus-yellow pl-2 text-xs font-bold uppercase tracking-wide text-ink">{{ FLAG_TEXT }}</p>
```

6. Registration checkbox label: after the `<label …>Enable attendee registration</label>`, add:

```vue
          <p v-if="flagFor('registrationEnabled')" class="mt-2 border-l-4 border-bauhaus-yellow pl-2 text-xs font-bold uppercase tracking-wide">{{ FLAG_TEXT }}</p>
```

7. Workflow buttons:

```vue
            <BauhausButton type="button" variant="yellow" :disabled="eventsStore.isSaving" @click="chooseIntent('draft')">
              {{ eventsStore.isSaving ? "Saving..." : isReturned ? "Save changes" : "Save draft" }}
            </BauhausButton>
            <BauhausButton type="submit" variant="primary" :disabled="eventsStore.isSaving">{{ isReturned ? "Resubmit" : "Submit request" }}</BauhausButton>
```

8. After the submit `ConfirmModal`, add:

```vue
    <ResubmitEventModal
      :open="isResubmitModalOpen"
      :event-name="form.name"
      :busy="eventsStore.isSaving"
      :error="isResubmitModalOpen ? eventsStore.error : null"
      @confirm="confirmResubmit"
      @cancel="isResubmitModalOpen = false"
    />
```

- [ ] **Step 5: Route "Amend and resubmit" from the dashboard to the form**

In `frontend/src/views/dashboards/OrganiserDashboard.vue`, change `eventAction`:

```js
function eventAction(event) {
  const action = getOrganiserAction(event);
  // Drafts and returned requests are both edited on the request form (SCRUM-33).
  if (action.kind === "continue_draft" || action.kind === "amend") {
    router.push({ name: "event-new", query: { id: event.id } });
    return;
  }
  router.push({ name: "event-detail", params: { id: event.id } });
}
```

- [ ] **Step 6: Show the amendment on the organiser's detail page**

In `frontend/src/views/events/EventDetailView.vue`, import `AmendmentBanner`:

```js
import AmendmentBanner from "@/components/events/AmendmentBanner.vue";
```

Before the rejection `<section …>`, add:

```vue
      <AmendmentBanner v-if="event.status === 'returned' && event.amendment" :amendment="event.amendment" class="mb-8">
        <BauhausButton variant="primary" @click="router.push({ name: 'event-new', query: { id: event.id } })">Amend and resubmit</BauhausButton>
      </AmendmentBanner>
```

- [ ] **Step 7: Run the tests and confirm they pass**

Run: `npx vitest run src/views/__tests__/EventRequestView.spec.js src/views/__tests__/OrganiserDashboard.spec.js src/views/__tests__/EventDetailView.spec.js`
Expected: all PASS.

- [ ] **Step 8: Run the whole frontend suite and the build**

Run (from `frontend/`): `npm test`, then `npm run build`.
Expected: all specs PASS; the build succeeds with no unresolved imports.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/views/events/EventRequestView.vue frontend/src/views/__tests__/EventRequestView.spec.js frontend/src/views/dashboards/OrganiserDashboard.vue frontend/src/views/__tests__/OrganiserDashboard.spec.js frontend/src/views/events/EventDetailView.vue frontend/src/views/__tests__/EventDetailView.spec.js
git commit -m "feat(events): let the organiser amend and resubmit a returned request

The organiser edits the same request on the existing form (QA-77): the
coordinator's message sits at the top, flagged fields are highlighted,
and Resubmit asks what changed before sending it back to the same
coordinator. The dashboard's Amend and resubmit action and the detail
page now lead there.

SCRUM-33"
```

---

### Task 10: Verify against the real system

**Files:** none changed unless a defect is found (fix it test-first in the owning task's files, then re-run this task).

- [ ] **Step 1: Full automated suites**

Run from `backend/`: `pytest`, then from `frontend/`: `npm test`.
Expected: both all PASS. Record the pass counts for the SCENARIO entry.

- [ ] **Step 2: Reset the fixture event**

Run `supabase/verification/event_review_fixture_reset.sql` with the Supabase MCP `execute_sql`, so fixture event `e0000000-0000-4000-8000-000000000201` is `under_review` and assigned to `coordinator@connectsphere.dev`.

- [ ] **Step 3: Real HTTP requests**

Start the backend (`uvicorn app.main:app --reload --port 8000` from `backend/`). Log in as the coordinator and organiser (`POST /api/v1/auth/login`, password `Cs1234`) to get tokens, then check each of these:

| Request | Expected |
|---|---|
| organiser → `POST /events/…0201/return` `{"message":"x"}` | 403 |
| coordinator → `POST /events/…0201/return` `{"message":"Please confirm the attendance","flagged_fields":["expected_attendance"]}` | 200, `status: returned`, `amendment.flagged_fields == ["expected_attendance"]` |
| coordinator → `POST /events/…0201/approve` | 409 `Cannot approve an event that is returned` |
| coordinator → `POST /events/…0201/resubmit` `{"resubmission_note":"x"}` | 403 |
| organiser → `GET /events/…0201` | `amendment` present |
| organiser → `POST /events/…0201/resubmit` `{"resubmission_note":"Attendance confirmed","expected_attendance":40}` | 200, `status: under_review`, `coordinator_id` unchanged, `amendment: null` |
| coordinator → `GET /events/…0201/history` | newest first: `under_review` (reason "Attendance confirmed"), then `returned` (reason "Please confirm the attendance") |

Then query `public.notifications` for the event: one `event_returned` to the organiser and one `event_resubmitted` to the coordinator.

- [ ] **Step 4: The browser, with the console checked**

Start the frontend (`npm run dev` from `frontend/`) and reset the fixture again. In the in-app browser:
1. As the coordinator, open `/coordinator/events/e0000000-0000-4000-8000-000000000201` and click **Return for amendment**. Type a message, tick Expected attendance and Proposed date and start time, and confirm. The toast reads "Returned to organiser", the banner reads "Waiting for the organiser to amend", and there are no Approve or Return buttons.
2. As the organiser, on `/dashboard/organiser`, click **Amend and resubmit**. The form reads "Amend your request" with the banner, and the attendance, date and start-time inputs are highlighted.
3. Change the attendance and click **Save changes**. The toast reads "Changes saved", and the banner and highlights remain.
4. Click **Resubmit**, enter a note and confirm. The toast reads "Request resubmitted" and you land on the dashboard.
5. As the coordinator, reload the review page. It shows Under review, the history has both entries with the message and the note, and Approve is offered again.
6. Check the phone width (375 px): the return modal scrolls, and the banner and highlighted fields are readable.

Take screenshots of steps 1, 2 and 5. `read_console_messages` must show no errors.

- [ ] **Step 5: Advisors and fixture**

Run `get_advisors` (security, performance). Nothing new should be reported for this story's objects. Reset the fixture with `event_review_fixture_reset.sql` again. Its comment already says it clears stray history and notifications. Confirm it also leaves no open `amendment_requests` row for `…0201`. If it doesn't, add `delete from public.amendment_requests where event_id in ('e0000000-0000-4000-8000-000000000201', 'e0000000-0000-4000-8000-000000000202');` to it, run it, and commit that with the Task 11 docs.

---

### Task 11: Paper trail

**Files:**
- Modify: `docs/test-cases/events.md` (new section at the end)
- Modify: `docs/test-cases/dashboards.md` (TC-ORG-005)
- Modify: `docs/IMPLEMENTATION_MAP.md`
- Modify: `docs/SCENARIO.md` (§4, append)
- Modify: `docs/REQUIREMENTS.md` (§6.4 note, §9 assumption)
- Modify: `docs/PROJECT_REVIEW.md` (§B2a SCRUM-33 row)
- Modify (if Task 10 Step 5 needed it): `supabase/verification/event_review_fixture_reset.sql`

- [ ] **Step 1: Manual test cases**

Append to `docs/test-cases/events.md`:

```markdown
## Return for amendment (SCRUM-33)

**Preconditions for every case unless noted otherwise:** every migration applied (including `20260924140000_event_amendment_requests.sql`), fixture event `e0000000-…-0201` reset to `under_review` with `supabase/verification/event_review_fixture_reset.sql`, and assigned to `coordinator@connectsphere.dev` (Marcus Lim). The organiser is `organiser@connectsphere.dev` (Olivia Tan).

| ID | Title | Preconditions | Test Steps | Test Input | Expected Result | Priority |
|----|-------|----------------|------------|-------------|------------------|----------|
| TC-AMD-001 | AC1 — the assigned coordinator returns an under-review request with flagged fields | Coordinator on `/coordinator/events/…0201` | Click **Return for amendment**, type a message, tick **Expected attendance**, confirm | `"Please confirm the attendance"` | `POST /events/{id}/return` → 200, `status: returned`. Toast "Returned to organiser". The page shows "Waiting for the organiser to amend" with the message and "Expected attendance", and offers no Approve, Reject or Return. One `event_returned` notification to the organiser, none to the coordinator. | 🔴 |
| TC-AMD-002 | AC5 — the return message is required | Return dialog open | Leave the message empty, then type only spaces, then flag a field without a message | `""`, `"   "` | **Return request** stays disabled each time. `curl` with `{"message":"   "}` → 422. | 🔴 |
| TC-AMD-003 | AC2 — the organiser sees the message and the flagged fields highlighted | TC-AMD-001 done; organiser on `/dashboard/organiser` | Click **Amend and resubmit** | — | Opens `/events/new?id=…0201` headed "Amend your request", with the coordinator's message in a banner and "Expected attendance" listed. The Expected attendance input is highlighted and reads "Flagged by coordinator"; other inputs are not. `/events/…0201` shows the same banner with an **Amend and resubmit** button. | 🔴 |
| TC-AMD-004 | Saving changes keeps the request returned and the banner in place | TC-AMD-003 | Change attendance, click **Save changes** | `40` | Toast "Changes saved". Status still Returned; banner and highlights remain after the save and after a reload. | 🟠 |
| TC-AMD-005 | AC3 — the organiser resubmits with a note to the same coordinator | TC-AMD-004 | Click **Resubmit**, type a note, confirm | `"Attendance confirmed at 40"` | `POST /events/{id}/resubmit` → 200, `status: under_review`, same `coordinator_id`, `amendment: null`. Toast "Request resubmitted"; lands on the dashboard. One `event_resubmitted` notification to the coordinator, none to the organiser. | 🔴 |
| TC-AMD-006 | The resubmission note is required | Resubmit dialog open | Leave the note empty, then spaces only | `""`, `"   "` | **Resubmit request** stays disabled. `curl` without `resubmission_note` → 422. | 🟠 |
| TC-AMD-007 | A resubmitted request must still be complete | Event returned | Clear **Purpose**, click **Resubmit** | `purpose: ""` | The form blocks it with "Enter the event purpose."; a raw `curl` with `"purpose": ""` → 422. Status stays Returned. | 🟠 |
| TC-AMD-008 | AC4 — every return and resubmission is in the history, and a request can be returned again | TC-AMD-005 done | As the coordinator, return it again, then read the History panel as both users | `"Also confirm the timezone"` | History (newest first): Returned ("Also confirm the timezone", Marcus Lim) → Under review ("Attendance confirmed at 40", Olivia Tan) → Returned ("Please confirm the attendance", Marcus Lim) → …. Both users see the same entries. `amendment_requests` holds two rows for the event, one open. | 🔴 |
| TC-AMD-009 | AC7 — a returned request can't be approved or rejected | Event returned | `POST /events/{id}/approve`; `POST /events/{id}/reject` with a reason | — | 409 `Cannot approve an event that is returned` / `Cannot reject an event that is returned`. No decision buttons on the page. | 🔴 |
| TC-AMD-010 | AC6 — only the assigned coordinator can return | Event under review | `POST /events/{id}/return` as (a) the organiser, (b) venue staff, (c) `coordinator@connectsphere.dev` switched to Venue Staff | valid body | 403 for all three. | 🔴 |
| TC-AMD-011 | AC6 — only the owning organiser can resubmit | Event returned | `POST /events/{id}/resubmit` as (a) the coordinator, (b) an organiser who doesn't own it | valid body | (a) 403, (b) 404. | 🔴 |
| TC-AMD-012 | Return is offered only while under review | Event in each of Planning, Returned, Confirmed | Open the coordinator page; `curl` the return endpoint | — | No **Return for amendment** button; API → 409 `Cannot return an event that is <status>`. | 🟠 |

### Traceability — SCRUM-33

| Acceptance criterion | Covered by | Automated equivalent |
|---|---|---|
| AC1 return with message and flags; organiser notified | TC-AMD-001 | `test_event_amendment_api.py::TestReturn::test_the_assigned_coordinator_returns_an_under_review_request`; `event_amendment_checks.sql` (notification, amendment row); `CoordinatorEventView.spec.js` "returns the request with the message and flagged fields…" |
| AC2 organiser sees message, flagged fields highlighted | TC-AMD-003, TC-AMD-004 | `TestAmendmentOnResponses`; `EventRequestView.spec.js` "opens the returned request…", "highlights every input…", "keeps the banner…"; `AmendmentBanner.spec.js`; `flaggableInputs.spec.js`; `EventDetailView.spec.js` |
| AC3 resubmit with note to the same coordinator; coordinator notified | TC-AMD-005, TC-AMD-006, TC-AMD-007 | `TestResubmit`; `event_amendment_checks.sql`; `EventRequestView.spec.js` "resubmits the edited request…"; `ResubmitEventModal.spec.js`; `stores/events.spec.js` |
| AC4 history; returnable more than once | TC-AMD-008 | `event_amendment_checks.sql` (history rows, two rounds, one open) |
| AC5 message required | TC-AMD-002 | `TestReturn::test_a_blank_message_is_refused`, `test_a_missing_message_is_refused`; `ReturnEventModal.spec.js` |
| AC6 only the assigned coordinator / owning organiser | TC-AMD-010, TC-AMD-011 | `TestReturn::test_a_coordinator_who_is_not_assigned_is_forbidden`, `test_other_roles_are_forbidden`, `test_a_coordinator_acting_as_venue_staff_is_forbidden`; `TestResubmit::test_another_organiser_gets_not_found`, `test_other_roles_are_forbidden`, `test_an_organiser_acting_as_attendee_is_forbidden`; `test_active_role_access.py`; `event_amendment_checks.sql` (RLS) |
| AC7 no approve/reject while returned | TC-AMD-009 | `test_event_lifecycle.py::test_a_returned_event_cannot_be_approved_or_rejected`; `TestReturn::test_a_returned_request_cannot_be_decided` |

**Automated coverage today.** The API suite mocks the repository, so the functions' own atomicity, notifications and RLS are covered by `supabase/verification/event_amendment_checks.sql`, run against the live project, rather than by `pytest`. TC-AMD-004's "after a reload" and the phone-width checks remain manual.
```

In `docs/test-cases/dashboards.md`, change TC-ORG-005's expected result to: `Drafts and returned requests open /events/new with the event id (returned requests in amend mode, SCRUM-33); other requests open /events/:id; new requests open /events/new. No inline mutation occurs on the dashboard.`

Add `TC-AMD` to the events row of the index table in `docs/test-cases/README.md`.

- [ ] **Step 2: IMPLEMENTATION_MAP**

In `docs/IMPLEMENTATION_MAP.md`:
- In the status table, add a row for SCRUM-33 (endpoints `POST /events/{id}/return` and `/resubmit`; `ReturnEventModal`, `ResubmitEventModal`, `AmendmentBanner`, the `EventRequestView` amend mode; table `amendment_requests` with migration `20260924140000`).
- In the endpoints table, add the two endpoints with their guards and status codes, and note that `GET /events/{id}` and `PATCH /events/{id}` carry `amendment` while `returned`.
- In the reuse tables, add `features/events/amendment.js`, the `flag` prop on `BauhausInput`, `BauhausSelect` and `BauhausCheckboxGroup`, `AmendmentBanner`, and the SQL functions `return_event_for_amendment` / `resubmit_event` (both wrap `transition_event`).
- In "know before you build":
  - The booking-creation story must block creating a booking while the event is `returned`, with the message "Requirements are still being amended." (REQUIREMENTS §6.4).
  - `notifications` now also receives `event_returned` and `event_resubmitted`.
- Update the "Last updated" line.

- [ ] **Step 3: SCENARIO, REQUIREMENTS, PROJECT_REVIEW**

- `docs/SCENARIO.md` §4: append an entry for SCRUM-33 following the existing template. It should cover:
  - the Jira text as agreed (§2 of the spec), noting it replaced the clarification-thread criteria per QA-22 and QA-77;
  - what was built;
  - the verification evidence from Task 10 (pass counts, the HTTP table, the screenshots);
  - what wasn't verified.
- `docs/REQUIREMENTS.md`:
  - §9: add the **[Assumption]** that the return message and resubmission note are capped at 1000 characters (checked after trimming, as for the rejection reason).
  - §6.4: add a note that the "blocked while returned" booking rule is enforced by the booking-creation story, since no booking endpoint existed when SCRUM-33 shipped.
- `docs/PROJECT_REVIEW.md` §B2a: mark the SCRUM-33 row done in code (branch `feature/scrum-33-return-for-amendment`), and say the Jira description still needs the agreed criteria plus a QA-22/QA-77 comment.

- [ ] **Step 4: Commit**

```bash
git add docs/test-cases/events.md docs/test-cases/dashboards.md docs/test-cases/README.md docs/IMPLEMENTATION_MAP.md docs/SCENARIO.md docs/REQUIREMENTS.md docs/PROJECT_REVIEW.md
git commit -m "docs(events): record SCRUM-33 return for amendment

Manual cases and traceability for every acceptance criterion, the new
endpoints/table/components in the implementation map, the 1000-character
assumption, and the booking guard handed to the booking-creation story.

SCRUM-33"
```

(Add `supabase/verification/event_review_fixture_reset.sql` to that `git add` if Task 10 Step 5 changed it.)

- [ ] **Step 5: Hand over**

Report the following: what changed, how it was verified (with the Task 10 evidence), what wasn't verified, and the follow-ups:
- the Jira description update;
- the booking guard;
- PR #29 must merge first.

Then ask the developer, per CLAUDE.md, whether to open a PR and move SCRUM-33 to **In Review**. Opening the PR, review, merging and moving the ticket to Done are the developer's decisions.
