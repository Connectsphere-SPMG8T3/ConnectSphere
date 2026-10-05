# SCRUM-61 Event Comments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each submitted event an append-only discussion thread shared by its organiser and assigned coordinator, where every comment records author and time and notifies the other party.

**Architecture:** A new `event_comments` table, written only by a `security definer` function `public.add_event_comment` that saves the comment and its `comment_added` notification in one transaction. The `events` module gains `GET`/`POST /events/{id}/comments`, reusing `service._visible_event` for authorisation. The SPA gets a pure rules module, a Pinia store and an `EventDiscussion` component mounted on both event pages.

**Tech Stack:** PostgreSQL (Supabase) migrations and rolled-back SQL checks; FastAPI + Pydantic v2 + supabase-py; pytest; Vue 3 `<script setup>`, Pinia, Tailwind; Vitest.

**Spec:** `docs/superpowers/specs/2026-10-02-scrum-61-event-comments-design.md`

## Global Constraints

- Branch: `feature/scrum-61-event-comments` (already created; spec committed as `90d2554`). Never commit to `main`.
- Readers and posters: the owning organiser acting as `event_organiser`, and the assigned coordinator acting as `event_coordinator`. Authorise by the session's **active** role only (`require_roles`, `CurrentUser.role`, `private.current_user_role()`).
- Statuses that accept comments: `submitted`, `under_review`, `returned`, `planning`, `confirmed`. Closed (`rejected`, `cancelled`, `completed`): thread readable, posting 409. `draft`: organiser gets an empty list and 409 on post; every coordinator gets 404.
- Body: plain text, trimmed, 1–1000 characters (`COMMENT_MAX_LENGTH = 1000`, [Assumption]). Append-only: no edit or delete anywhere.
- Notification type is exactly `comment_added`; recipient is the other party; none when the recipient is null or is the author.
- Error copy: blank body → `"A comment can't be empty."`; closed → `"Comments are closed for a <status with spaces> event."`; draft → `"Comments open once the request is submitted."`.
- The secret key never reaches the frontend, logs or docs. All data access is through `repository.py` and the Supabase client (ADR-0002).
- Commit messages: imperative summary (`feat(events): …`), body explaining why, ending with `SCRUM-61`. Stage files by name.

## Review Focus

1. **A comment with only whitespace or newlines** — must be refused (422) by the API and the Post button disabled, never stored as an empty bubble. Pinned in Task 3 (`test_a_blank_comment_is_refused` parametrised over `"\n\t "`) and Task 6 (`disables Post for whitespace`).
2. **A coordinator whose session acts as venue staff** (the seeded dual-role account) — must get 403 on both routes even though they are the assigned coordinator. Pinned in Task 3 (`test_a_coordinator_acting_as_venue_staff_is_forbidden`).
3. **The event closes between page load and Post** (another tab rejects it) — the RPC returns no row; the API must answer 409, not 500, and the UI must show the message and keep the typed text. Pinned in Task 3 (`test_a_comment_racing_a_close_is_a_conflict`) and Task 6 (`keeps the draft text when posting fails`).
4. **Navigating from one event to another while comments load** — the first event's comments must never show on the second. Pinned in Task 5 (`drops a response for an event that is no longer current`).
5. **A long unbroken string (URL, 1000 × "x")** — must wrap, not widen the page on a phone. Pinned in Task 6 (`wraps long words`, asserts `break-words` class) and the manual phone-width pass.

---

### Task 1: Database — `event_comments` table, `add_event_comment` function, SQL checks

**Files:**
- Create: `supabase/verification/event_comment_checks.sql`
- Create: `supabase/migrations/20261002120000_event_comments.sql`
- Modify: `backend/scripts/verify_live.py:77-84` (add the script to the SQL list)

**Interfaces:**
- Produces: table `public.event_comments(id uuid, event_id uuid, author_id uuid null, body text, created_at timestamptz)`; FK name `event_comments_author_id_fkey` (Task 2 embeds through it); function `public.add_event_comment(p_event_id uuid, p_author_id uuid, p_body text, p_notify_message text) returns setof public.event_comments` — returns one row on success, **no rows** when the event is missing, a draft or closed.

- [ ] **Step 1: Write the failing SQL check**

Create `supabase/verification/event_comment_checks.sql`:

```sql
-- SCRUM-61 event comments: the real function, table constraints and RLS.
-- Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`. Raises on
-- the first failure and prints COMMENT CHECKS PASSED otherwise. Everything runs
-- inside `begin; ... rollback;`, so the throwaway events leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002) and venue staff (…0003).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name) values
    ('e0000000-0000-4000-8000-0000000006a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'under_review', 'Comment check (rolled back)'),
    ('e0000000-0000-4000-8000-0000000006a2', 'a0000000-0000-4000-8000-000000000001',
     null, 'under_review', 'Comment check, unassigned (rolled back)'),
    ('e0000000-0000-4000-8000-0000000006a3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'draft', 'Comment check, draft (rolled back)'),
    ('e0000000-0000-4000-8000-0000000006a4', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'rejected', 'Comment check, closed (rolled back)');

do $$
declare
    v_event uuid := 'e0000000-0000-4000-8000-0000000006a1';
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_comment public.event_comments;
    v_rows integer;
    v_before timestamptz := now();
begin
    -- Organiser posts: trimmed, timestamped by the database, coordinator notified.
    select * into v_comment from public.add_event_comment(
        v_event, v_organiser, '  Can we recce the hall on Friday?  ', 'The organiser commented on "Comment check (rolled back)".');
    if v_comment.body is distinct from 'Can we recce the hall on Friday?' or v_comment.author_id is distinct from v_organiser then
        raise exception 'COMMENT FAIL: the organiser''s comment was not stored trimmed with its author';
    end if;
    if v_comment.created_at is null or v_comment.created_at < v_before then
        raise exception 'COMMENT FAIL: created_at was not set by the database';
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'comment_added' and recipient_id = v_coordinator;
    if v_rows <> 1 then raise exception 'COMMENT FAIL: the coordinator was not notified exactly once'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'comment_added' and recipient_id = v_organiser;
    if v_rows <> 0 then raise exception 'COMMENT FAIL: the organiser was notified of their own comment'; end if;

    -- Coordinator replies: organiser notified.
    perform public.add_event_comment(v_event, v_coordinator, 'Booked for 3pm.', 'Your coordinator commented on "Comment check (rolled back)".');
    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'comment_added' and recipient_id = v_organiser;
    if v_rows <> 1 then raise exception 'COMMENT FAIL: the organiser was not notified of the reply'; end if;

    -- No coordinator assigned: the comment is saved, nobody is notified.
    select count(*) into v_rows from public.add_event_comment(
        'e0000000-0000-4000-8000-0000000006a2', v_organiser, 'Anyone there?', 'msg');
    if v_rows <> 1 then raise exception 'COMMENT FAIL: a comment on an unassigned event was refused'; end if;
    select count(*) into v_rows from public.notifications where event_id = 'e0000000-0000-4000-8000-0000000006a2';
    if v_rows <> 0 then raise exception 'COMMENT FAIL: an unassigned event produced a notification'; end if;

    -- Draft and closed events: no row, nothing written.
    select count(*) into v_rows from public.add_event_comment('e0000000-0000-4000-8000-0000000006a3', v_organiser, 'x', 'msg');
    if v_rows <> 0 then raise exception 'COMMENT FAIL: a draft accepted a comment'; end if;
    select count(*) into v_rows from public.add_event_comment('e0000000-0000-4000-8000-0000000006a4', v_organiser, 'x', 'msg');
    if v_rows <> 0 then raise exception 'COMMENT FAIL: a rejected event accepted a comment'; end if;
    select count(*) into v_rows from public.event_comments
     where event_id in ('e0000000-0000-4000-8000-0000000006a3', 'e0000000-0000-4000-8000-0000000006a4');
    if v_rows <> 0 then raise exception 'COMMENT FAIL: a refused comment was stored'; end if;

    -- The table refuses blank and overlong bodies by itself.
    begin
        insert into public.event_comments (event_id, author_id, body) values (v_event, v_organiser, '   ');
        raise exception 'COMMENT FAIL: a blank body was accepted';
    exception when check_violation then null;
    end;
    begin
        insert into public.event_comments (event_id, author_id, body) values (v_event, v_organiser, repeat('x', 1001));
        raise exception 'COMMENT FAIL: a 1001-character body was accepted';
    exception when check_violation then null;
    end;

    -- API-only: not callable by signed-in users.
    if has_function_privilege('authenticated', 'public.add_event_comment(uuid, uuid, text, text)', 'execute') then
        raise exception 'COMMENT FAIL: authenticated can execute add_event_comment';
    end if;
end $$;

-- RLS: the owning organiser, acting as organiser, reads both comments; cannot edit or delete.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
declare v_rows integer;
begin
    if (select count(*) from public.event_comments where event_id = 'e0000000-0000-4000-8000-0000000006a1') <> 2 then
        raise exception 'COMMENT FAIL: the owning organiser cannot read the thread';
    end if;
    update public.event_comments set body = 'edited' where event_id = 'e0000000-0000-4000-8000-0000000006a1';
    get diagnostics v_rows = row_count;
    if v_rows <> 0 then raise exception 'COMMENT FAIL: the organiser edited a comment'; end if;
    delete from public.event_comments where event_id = 'e0000000-0000-4000-8000-0000000006a1';
    get diagnostics v_rows = row_count;
    if v_rows <> 0 then raise exception 'COMMENT FAIL: the organiser deleted a comment'; end if;
end $$;
reset role;

-- RLS: the assigned coordinator, acting as coordinator, reads both comments.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_comments where event_id = 'e0000000-0000-4000-8000-0000000006a1') <> 2 then
        raise exception 'COMMENT FAIL: the assigned coordinator cannot read the thread';
    end if;
end $$;
reset role;

-- RLS: the same coordinator account acting as venue staff sees nothing (SCRUM-76).
insert into public.session_active_roles (session_id, profile_id, role)
values ('33333333-3333-4333-8333-333333333333', 'a0000000-0000-4000-8000-000000000002', 'venue_staff');
select set_config('request.jwt.claims',
    '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated","session_id":"33333333-3333-4333-8333-333333333333"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_comments where event_id = 'e0000000-0000-4000-8000-0000000006a1') <> 0 then
        raise exception 'COMMENT FAIL: the coordinator acting as venue staff can read the thread';
    end if;
end $$;
reset role;

-- RLS: an unrelated staff member sees nothing.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000003","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_comments where event_id = 'e0000000-0000-4000-8000-0000000006a1') <> 0 then
        raise exception 'COMMENT FAIL: venue staff can read the thread';
    end if;
end $$;
reset role;

select 'COMMENT CHECKS PASSED' as result;
rollback;
```

Before running, open `supabase/verification/active_role_checks.sql` and confirm the `session_active_roles` column names and the claim key it uses for the session (`session_id`); adjust the venue-staff block to match exactly.

- [ ] **Step 2: Run it to confirm it fails for the right reason**

Run with the Supabase MCP `execute_sql` (project `vuiryrzzyfecjqftwicj`), passing the file's contents.
Expected: FAIL with `function public.add_event_comment(...) does not exist` or `relation "public.event_comments" does not exist`. The transaction rolls back, so nothing changes.

- [ ] **Step 3: Write the migration**

Create `supabase/migrations/20261002120000_event_comments.sql`:

```sql
-- =============================================================================
-- ConnectSphere - SCRUM-61 comment and discuss on an event
--
-- event_comments: the organiser-coordinator discussion thread kept with the
-- event record (REQUIREMENTS 8; QA2-27). Append-only. add_event_comment writes
-- the comment and notifies the other party in one transaction (NT-R3).
-- API-only (ADR-0002): the API checks role and relationship before calling.
-- =============================================================================

create table public.event_comments (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null,
    author_id uuid null,
    body text not null,
    created_at timestamptz not null default now(),
    constraint event_comments_event_id_fkey
        foreign key (event_id) references public.events (id) on delete cascade,
    constraint event_comments_author_id_fkey
        foreign key (author_id) references public.profiles (id) on delete set null,
    constraint event_comments_body_length check (length(btrim(body)) between 1 and 1000)
);

comment on table public.event_comments is
    'Discussion thread on an event between its organiser and assigned coordinator (SCRUM-61). Append-only; written only by add_event_comment.';

create index event_comments_event_created_at_idx on public.event_comments (event_id, created_at);
create index event_comments_author_id_idx on public.event_comments (author_id);

alter table public.event_comments enable row level security;

-- Safety net only: the API uses the secret key. Same readers as event_status_history.
create policy "event_comments_select_owner_or_assigned_coordinator"
    on public.event_comments
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.events e
            where e.id = event_comments.event_id
              and (
                  (e.organiser_id = (select auth.uid())
                   and (select private.current_user_role()) = 'event_organiser')
                  or (e.coordinator_id = (select auth.uid())
                      and (select private.current_user_role()) = 'event_coordinator')
              )
        )
    );

create or replace function public.add_event_comment(
    p_event_id uuid,
    p_author_id uuid,
    p_body text,
    p_notify_message text
)
returns setof public.event_comments
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_event public.events;
    v_comment public.event_comments;
    v_recipient uuid;
begin
    -- Lock the event so a concurrent close can't slip between the check and the insert.
    select * into v_event from public.events where id = p_event_id for update;
    if not found
       or v_event.status not in ('submitted', 'under_review', 'returned', 'planning', 'confirmed') then
        return;
    end if;

    insert into public.event_comments (event_id, author_id, body)
    values (p_event_id, p_author_id, btrim(p_body))
    returning * into v_comment;

    v_recipient := case
        when p_author_id = v_event.organiser_id then v_event.coordinator_id
        else v_event.organiser_id
    end;
    if v_recipient is not null and v_recipient is distinct from p_author_id then
        insert into public.notifications (recipient_id, event_id, type, message)
        values (v_recipient, p_event_id, 'comment_added', p_notify_message);
    end if;

    return next v_comment;
end;
$$;

comment on function public.add_event_comment is
    'Adds a comment to an open (submitted to confirmed) event and notifies the other party, atomically. No row for a missing, draft or closed event. API-only.';

revoke execute on function public.add_event_comment(uuid, uuid, text, text) from public, anon, authenticated;
grant execute on function public.add_event_comment(uuid, uuid, text, text) to service_role;
```

- [ ] **Step 4: Ask the developer, then apply the migration to the live project**

Applying changes the shared Supabase project, so stop and ask first. On a yes: Supabase MCP `apply_migration` with name `event_comments` and the file's SQL; then `list_migrations` and, if the ledger row got a generated version, rename it to `20261002120000` (the same fix-up recorded for `20260924140000` in `docs/IMPLEMENTATION_MAP.md` §4).

- [ ] **Step 5: Run the SQL check to confirm it passes**

Run `event_comment_checks.sql` again with `execute_sql`.
Expected: `COMMENT CHECKS PASSED`.

- [ ] **Step 6: Check advisors**

Supabase MCP `get_advisors` for `security` and `performance`. Expected: nothing new naming `event_comments` or `add_event_comment`. Fix any new finding in a follow-up migration before moving on.

- [ ] **Step 7: Register the script with the live checks**

In `backend/scripts/verify_live.py`, add to the SQL script list after the `event_amendment_checks.sql` line:

```python
    ("event_comment_checks.sql", "TC-CMT-008, 009, 010, 011, 013 (database half)"),
```

- [ ] **Step 8: Commit**

```bash
git add supabase/migrations/20261002120000_event_comments.sql supabase/verification/event_comment_checks.sql backend/scripts/verify_live.py
git commit -m "feat(events): store event comments and notify the other party

Adds event_comments and add_event_comment so a comment and its
notification commit together, with RLS limited to the organiser and the
assigned coordinator in their active roles. SCRUM-61"
```

---

### Task 2: Backend schemas and repository

**Files:**
- Modify: `backend/app/modules/events/schemas.py` (append after `EventHistoryResponse`)
- Modify: `backend/app/modules/events/repository.py` (append)
- Test: `backend/tests/test_events_repository.py` (append)

**Interfaces:**
- Consumes: `public.add_event_comment(p_event_id, p_author_id, p_body, p_notify_message)` and FK `event_comments_author_id_fkey` from Task 1.
- Produces:
  - `COMMENT_MAX_LENGTH = 1000`, `COMMENTABLE_STATUSES: frozenset[EventStatus]`
  - `EventCommentCreate(body: str)` — stripped, required, max 1000
  - `EventCommentAuthor(id: str, full_name: str, role: str | None = None)`
  - `EventComment(id: str, body: str, created_at: datetime, author: EventCommentAuthor | None = None)`
  - `EventCommentsResponse(comments: list[EventComment])`
  - `repository.list_comments(event_id: str) -> list[dict]` — oldest first, each `{"id", "body", "created_at", "author": {"id", "full_name"} | None}`
  - `repository.add_comment(event_id: str, author_id: str, body: str, *, notify_message: str) -> dict | None` — the created row with `author_id`, or `None` when the function returned no row

- [ ] **Step 1: Write the failing repository tests**

Append to `backend/tests/test_events_repository.py`:

```python
def test_list_comments_reads_oldest_first_with_the_author_embedded(monkeypatch):
    calls = {}

    class CommentQuery:
        def select(self, columns):
            calls["columns"] = columns
            return self

        def eq(self, field, value):
            calls["eq"] = (field, value)
            return self

        def order(self, column, *, desc=False):
            calls["order"] = (column, desc)
            return self

        def execute(self):
            return SimpleNamespace(data=[{"id": "c1"}])

    class AdminClient:
        def table(self, name):
            calls["table"] = name
            return CommentQuery()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    assert repository.list_comments("event-1") == [{"id": "c1"}]
    assert calls["table"] == "event_comments"
    assert "author:profiles!event_comments_author_id_fkey(id, full_name)" in calls["columns"]
    assert calls["eq"] == ("event_id", "event-1")
    assert calls["order"] == ("created_at", False)


def test_add_comment_calls_the_function_and_returns_its_row(monkeypatch):
    sent = {}

    class Rpc:
        def execute(self):
            return SimpleNamespace(data=[{"id": "c1", "body": "Hi"}])

    class AdminClient:
        def rpc(self, name, params):
            sent["name"], sent["params"] = name, params
            return Rpc()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    row = repository.add_comment("event-1", "user-1", "Hi", notify_message="msg")

    assert row == {"id": "c1", "body": "Hi"}
    assert sent == {"name": "add_event_comment", "params": {
        "p_event_id": "event-1", "p_author_id": "user-1", "p_body": "Hi", "p_notify_message": "msg"}}


def test_add_comment_is_none_when_the_function_refuses(monkeypatch):
    class Rpc:
        def execute(self):
            return SimpleNamespace(data=[])

    class AdminClient:
        def rpc(self, name, params):
            return Rpc()

    monkeypatch.setattr(repository, "get_supabase_admin_client", lambda: AdminClient())

    assert repository.add_comment("event-1", "user-1", "Hi", notify_message="msg") is None
```

- [ ] **Step 2: Run them to confirm they fail**

Run (from `backend/`): `pytest tests/test_events_repository.py -v -k comment`
Expected: FAIL with `AttributeError: module 'app.modules.events.repository' has no attribute 'list_comments'`.

- [ ] **Step 3: Implement the repository functions**

Append to `backend/app/modules/events/repository.py`:

```python
def list_comments(event_id: str) -> list[dict]:
    """The event's discussion thread, oldest first (SCRUM-61). The author is embedded
    through the FK named in the migration; it is null if their profile was deleted."""
    response = (
        get_supabase_admin_client()
        .table("event_comments")
        .select("id, body, created_at, author_id, author:profiles!event_comments_author_id_fkey(id, full_name)")
        .eq("event_id", event_id)
        .order("created_at", desc=False)
        .execute()
    )
    return response.data or []


def add_comment(event_id: str, author_id: str, body: str, *, notify_message: str) -> dict | None:
    """Run `public.add_event_comment`: the comment and the other party's notification in
    one transaction. None when the event is missing, a draft or closed."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "add_event_comment",
            {
                "p_event_id": event_id,
                "p_author_id": author_id,
                "p_body": body,
                "p_notify_message": notify_message,
            },
        )
        .execute()
    )
    return _first_row(response)
```

- [ ] **Step 4: Add the schemas**

Append to `backend/app/modules/events/schemas.py`:

```python
COMMENT_MAX_LENGTH = 1000  # [Assumption] REQUIREMENTS §9; same cap as a rejection reason

# Statuses whose thread accepts new comments (SCRUM-61). Drafts have no thread yet;
# rejected, cancelled and completed events keep theirs read-only. Mirrored in
# public.add_event_comment and in the SPA's features/events/comments.js.
COMMENTABLE_STATUSES = frozenset({
    EventStatus.submitted, EventStatus.under_review, EventStatus.returned,
    EventStatus.planning, EventStatus.confirmed,
})


class EventCommentCreate(BaseModel):
    body: str = Field(max_length=COMMENT_MAX_LENGTH)

    @field_validator("body", mode="before")
    @classmethod
    def body_is_not_blank(cls, value):
        return _required_text(value, "A comment can't be empty.")


class EventCommentAuthor(BaseModel):
    id: str
    full_name: str
    role: str | None = None  # the role they hold on this event, not their profile role


class EventComment(BaseModel):
    id: str
    body: str
    created_at: datetime
    author: EventCommentAuthor | None = None


class EventCommentsResponse(BaseModel):
    comments: list[EventComment]
```

- [ ] **Step 5: Run the repository tests to confirm they pass**

Run: `pytest tests/test_events_repository.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/events/schemas.py backend/app/modules/events/repository.py backend/tests/test_events_repository.py
git commit -m "feat(events): read and add event comments in the repository

Wraps add_event_comment and the thread read so the service never touches
the table directly, and defines the comment request and response shapes.
SCRUM-61"
```

---

### Task 3: Backend service and endpoints

**Files:**
- Modify: `backend/app/modules/events/service.py` (append; extend imports)
- Modify: `backend/app/modules/events/router.py` (two routes; extend imports)
- Create: `backend/tests/test_event_comments_api.py`

**Interfaces:**
- Consumes: Task 2's schemas and `repository.list_comments` / `repository.add_comment`; existing `service._visible_event(event_id, user_id, role) -> dict` and `EventConflictError`.
- Produces: `service.comments(event_id: str, user_id: str, role: str) -> EventCommentsResponse`; `service.add_comment(event_id: str, user_id: str, role: str, body: str) -> EventComment`; routes `GET /api/v1/events/{event_id}/comments` (200 `EventCommentsResponse`) and `POST /api/v1/events/{event_id}/comments` (201 `EventComment`).

- [ ] **Step 1: Write the failing API tests**

Create `backend/tests/test_event_comments_api.py`:

```python
"""SCRUM-61 event comments, through the HTTP API with the repository mocked."""

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
OPEN_STATUSES = ["submitted", "under_review", "returned", "planning", "confirmed"]
CLOSED_STATUSES = ["rejected", "cancelled", "completed"]
URL = f"/api/v1/events/{EVENT_ID}/comments"


def event_row(status="under_review", coordinator_id=COORDINATOR_ID):
    now = datetime.now(timezone.utc).isoformat()
    starts = datetime.now(timezone.utc) + timedelta(days=30)
    return {
        "id": EVENT_ID, "organiser_id": ORGANISER_ID, "coordinator_id": coordinator_id,
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
def thread(monkeypatch):
    """An in-memory event and comment list; `add_comment` mimics the function's guard."""
    state = {"event": event_row(), "comments": [], "calls": [], "refuse": False}

    def add_comment(event_id, author_id, body, *, notify_message):
        state["calls"].append({"event_id": event_id, "author_id": author_id, "body": body,
                               "notify_message": notify_message})
        if state["refuse"] or state["event"]["status"] not in OPEN_STATUSES:
            return None
        row = {"id": f"c{len(state['comments']) + 1}", "event_id": event_id, "author_id": author_id,
               "body": body, "created_at": "2026-10-02T03:00:00+00:00"}
        state["comments"].append(row)
        return deepcopy(row)

    def list_comments(event_id):
        names = {ORGANISER_ID: "Olivia Tan", COORDINATOR_ID: "Marcus Lim"}
        return [{**row, "author": {"id": row["author_id"], "full_name": names[row["author_id"]]}}
                for row in deepcopy(state["comments"])]

    monkeypatch.setattr(repository, "get_event", lambda event_id: deepcopy(state["event"]) if event_id == EVENT_ID else None)
    monkeypatch.setattr(repository, "add_comment", add_comment)
    monkeypatch.setattr(repository, "list_comments", list_comments)
    return state


@pytest.fixture()
def act_as(authenticate_as):
    def _act_as(role, user_id):
        return authenticate_as(role, user_id=user_id)
    return _act_as


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


def post(client, auth_headers, body="Can we recce the hall on Friday?"):
    return client.post(URL, json={"body": body}, headers=auth_headers)


class TestPost:
    def test_the_owning_organiser_posts_and_the_coordinator_is_told(self, client, auth_headers, act_as, thread):
        act_as("event_organiser", ORGANISER_ID)

        response = post(client, auth_headers, body="  Can we recce the hall on Friday?  ")

        assert response.status_code == 201
        body = response.json()
        assert body["body"] == "Can we recce the hall on Friday?"
        assert body["author"] == {"id": ORGANISER_ID, "full_name": "Olivia Tan", "role": "event_organiser"}
        assert body["created_at"]
        [call] = thread["calls"]
        assert call["author_id"] == ORGANISER_ID
        assert call["notify_message"] == 'The organiser commented on "Partner Summit".'

    def test_the_assigned_coordinator_posts_and_the_organiser_is_told(self, client, auth_headers, act_as, thread):
        act_as("event_coordinator", COORDINATOR_ID)

        response = post(client, auth_headers, body="Booked for 3pm.")

        assert response.status_code == 201
        assert response.json()["author"]["role"] == "event_coordinator"
        assert thread["calls"][0]["notify_message"] == 'Your coordinator commented on "Partner Summit".'

    @pytest.mark.parametrize("status", OPEN_STATUSES)
    def test_every_open_status_accepts_a_comment(self, client, auth_headers, act_as, thread, status):
        thread["event"]["status"] = status
        act_as("event_organiser", ORGANISER_ID)

        assert post(client, auth_headers).status_code == 201

    @pytest.mark.parametrize("body", ["", "   ", "\n\t "])
    def test_a_blank_comment_is_refused(self, client, auth_headers, act_as, thread, body):
        act_as("event_organiser", ORGANISER_ID)

        assert post(client, auth_headers, body=body).status_code == 422
        assert thread["calls"] == []

    def test_a_missing_body_is_refused(self, client, auth_headers, act_as, thread):
        act_as("event_organiser", ORGANISER_ID)

        assert client.post(URL, json={}, headers=auth_headers).status_code == 422
        assert thread["calls"] == []

    def test_a_comment_is_capped_at_1000_characters(self, client, auth_headers, act_as, thread):
        act_as("event_organiser", ORGANISER_ID)

        assert post(client, auth_headers, body="x" * 1001).status_code == 422
        assert post(client, auth_headers, body="x" * 1000).status_code == 201

    @pytest.mark.parametrize("status", CLOSED_STATUSES)
    def test_a_closed_event_refuses_new_comments(self, client, auth_headers, act_as, thread, status):
        thread["event"]["status"] = status
        act_as("event_coordinator", COORDINATOR_ID)

        response = post(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == f"Comments are closed for a {status} event."
        assert thread["calls"] == []

    def test_a_draft_refuses_comments_for_its_organiser(self, client, auth_headers, act_as, thread):
        thread["event"]["status"] = "draft"
        act_as("event_organiser", ORGANISER_ID)

        response = post(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "Comments open once the request is submitted."

    def test_a_comment_racing_a_close_is_a_conflict(self, client, auth_headers, act_as, thread):
        thread["refuse"] = True  # the event closed after the service read it
        act_as("event_organiser", ORGANISER_ID)

        response = post(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "Comments are closed for this event. Reload."

    def test_an_unassigned_event_still_takes_the_organisers_comment(self, client, auth_headers, act_as, thread):
        thread["event"]["coordinator_id"] = None
        act_as("event_organiser", ORGANISER_ID)

        assert post(client, auth_headers).status_code == 201


class TestRead:
    def test_both_parties_read_the_thread_oldest_first(self, client, auth_headers, act_as, thread):
        act_as("event_organiser", ORGANISER_ID)
        post(client, auth_headers, body="First")
        act_as("event_coordinator", COORDINATOR_ID)
        post(client, auth_headers, body="Second")

        for role, user_id in (("event_organiser", ORGANISER_ID), ("event_coordinator", COORDINATOR_ID)):
            act_as(role, user_id)
            response = client.get(URL, headers=auth_headers)
            assert response.status_code == 200
            comments = response.json()["comments"]
            assert [c["body"] for c in comments] == ["First", "Second"]
            assert [c["author"]["role"] for c in comments] == ["event_organiser", "event_coordinator"]

    @pytest.mark.parametrize("status", CLOSED_STATUSES)
    def test_a_closed_events_thread_stays_readable(self, client, auth_headers, act_as, thread, status):
        thread["event"]["status"] = status
        act_as("event_coordinator", COORDINATOR_ID)

        assert client.get(URL, headers=auth_headers).status_code == 200

    def test_a_draft_has_an_empty_thread_for_its_organiser(self, client, auth_headers, act_as, thread):
        thread["event"]["status"] = "draft"
        act_as("event_organiser", ORGANISER_ID)

        response = client.get(URL, headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {"comments": []}

    def test_a_deleted_authors_comment_keeps_its_place(self, client, auth_headers, act_as, thread, monkeypatch):
        monkeypatch.setattr(repository, "list_comments", lambda event_id: [
            {"id": "c1", "body": "Old note", "created_at": "2026-10-02T03:00:00+00:00", "author_id": None, "author": None}])
        act_as("event_organiser", ORGANISER_ID)

        [comment] = client.get(URL, headers=auth_headers).json()["comments"]

        assert comment["author"] is None
        assert comment["body"] == "Old note"

    def test_a_former_coordinators_comment_has_no_role(self, client, auth_headers, act_as, thread):
        act_as("event_coordinator", COORDINATOR_ID)
        post(client, auth_headers, body="Handing over")
        thread["event"]["coordinator_id"] = OTHER_COORDINATOR_ID
        act_as("event_organiser", ORGANISER_ID)

        [comment] = client.get(URL, headers=auth_headers).json()["comments"]

        assert comment["author"]["role"] is None


class TestAccess:
    @pytest.mark.parametrize("method", ["get", "post"])
    def test_another_organiser_gets_not_found(self, client, auth_headers, act_as, thread, method):
        act_as("event_organiser", OTHER_ORGANISER_ID)

        response = getattr(client, method)(URL, headers=auth_headers, **({"json": {"body": "hi"}} if method == "post" else {}))

        assert response.status_code == 404
        assert thread["calls"] == []

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_a_coordinator_who_is_not_assigned_is_forbidden(self, client, auth_headers, act_as, thread, method):
        act_as("event_coordinator", OTHER_COORDINATOR_ID)

        response = getattr(client, method)(URL, headers=auth_headers, **({"json": {"body": "hi"}} if method == "post" else {}))

        assert response.status_code == 403
        assert thread["calls"] == []

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_every_coordinator_gets_not_found_on_a_draft(self, client, auth_headers, act_as, thread, method):
        thread["event"]["status"] = "draft"
        act_as("event_coordinator", COORDINATOR_ID)

        response = getattr(client, method)(URL, headers=auth_headers, **({"json": {"body": "hi"}} if method == "post" else {}))

        assert response.status_code == 404

    @pytest.mark.parametrize("role", ["venue_staff", "tech_support", "attendee"])
    @pytest.mark.parametrize("method", ["get", "post"])
    def test_other_roles_are_forbidden(self, client, auth_headers, act_as, thread, role, method):
        act_as(role, "a0000000-0000-4000-8000-000000000003")

        response = getattr(client, method)(URL, headers=auth_headers, **({"json": {"body": "hi"}} if method == "post" else {}))

        assert response.status_code == 403
        assert thread["calls"] == []

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_a_coordinator_acting_as_venue_staff_is_forbidden(self, client, auth_headers, monkeypatch, thread, method):
        acting_as_another_role(monkeypatch, COORDINATOR_ID, holds="event_coordinator", acts_as="venue_staff")

        response = getattr(client, method)(URL, headers=auth_headers, **({"json": {"body": "hi"}} if method == "post" else {}))

        assert response.status_code == 403
        assert thread["calls"] == []

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_an_organiser_acting_as_attendee_is_forbidden(self, client, auth_headers, monkeypatch, thread, method):
        acting_as_another_role(monkeypatch, ORGANISER_ID, holds="event_organiser", acts_as="attendee")

        response = getattr(client, method)(URL, headers=auth_headers, **({"json": {"body": "hi"}} if method == "post" else {}))

        assert response.status_code == 403
        assert thread["calls"] == []
```

If `acting_as_another_role` needs `user_roles=` to pass `resolve_active_role` here, copy whatever `tests/test_event_amendment_api.py` does at the call sites on lines ~227 and ~384 exactly.

- [ ] **Step 2: Run them to confirm they fail**

Run: `pytest tests/test_event_comments_api.py -v`
Expected: FAIL — the access tests for other roles may pass by accident (404 from the missing route is not 403, so most fail); the happy paths fail with `404 Not Found` because the routes don't exist yet. Confirm the failures are 404/405 from routing, not import errors.

- [ ] **Step 3: Implement the service**

In `backend/app/modules/events/service.py`, extend the schemas import with `COMMENTABLE_STATUSES, EventComment, EventCommentsResponse`, then append:

```python
def _comment_role(event: dict, author_id: str | None) -> str | None:
    """The role an author holds on this event. None for someone no longer on it,
    such as a coordinator since reassigned."""
    if author_id and author_id == event.get("organiser_id"):
        return "event_organiser"
    if author_id and author_id == event.get("coordinator_id"):
        return "event_coordinator"
    return None


def _to_comment(event: dict, row: dict) -> EventComment:
    author = row.get("author")
    if author:
        author = {**author, "role": _comment_role(event, author.get("id"))}
    return EventComment(id=row["id"], body=row["body"], created_at=row["created_at"], author=author)


def comments(event_id: str, user_id: str, role: str) -> EventCommentsResponse:
    """The discussion thread (SCRUM-61), visible to the same people as the event."""
    event = _visible_event(event_id, user_id, role)
    if event["status"] == EventStatus.draft.value:
        return EventCommentsResponse(comments=[])
    return EventCommentsResponse(comments=[_to_comment(event, row) for row in repository.list_comments(event_id)])


def add_comment(event_id: str, user_id: str, role: str, body: str) -> EventComment:
    event = _visible_event(event_id, user_id, role)
    status = EventStatus(event["status"])
    if status == EventStatus.draft:
        raise EventConflictError("Comments open once the request is submitted.")
    if status not in COMMENTABLE_STATUSES:
        raise EventConflictError(f"Comments are closed for a {status.value.replace('_', ' ')} event.")
    who = "The organiser" if role == "event_organiser" else "Your coordinator"
    row = repository.add_comment(
        event_id, user_id, body, notify_message=f'{who} commented on "{event["name"]}".',
    )
    if not row:
        raise EventConflictError("Comments are closed for this event. Reload.")
    full_name = next(
        (c["author"]["full_name"] for c in repository.list_comments(event_id) if c["id"] == row["id"] and c.get("author")),
        None,
    )
    author = {"id": user_id, "full_name": full_name} if full_name else None
    return _to_comment(event, {**row, "author": author})
```

Note: re-reading the thread to get the author's name costs one query per post; that is acceptable here (posting is rare and the thread is short) and keeps the name coming from `profiles`, not from the request.

- [ ] **Step 4: Add the routes**

In `backend/app/modules/events/router.py`, extend the schemas import with `EventComment, EventCommentCreate, EventCommentsResponse`, and add after `read_event_history`:

```python
@router.get("/{event_id}/comments", response_model=EventCommentsResponse)
def read_event_comments(event_id: UUID, current_user: EventParticipant) -> EventCommentsResponse:
    return service.comments(str(event_id), current_user.id, current_user.role)


@router.post("/{event_id}/comments", response_model=EventComment, status_code=status.HTTP_201_CREATED)
def add_event_comment(event_id: UUID, body: EventCommentCreate, current_user: EventParticipant) -> EventComment:
    return service.add_comment(str(event_id), current_user.id, current_user.role, body.body)
```

- [ ] **Step 5: Run the new tests to confirm they pass**

Run: `pytest tests/test_event_comments_api.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `pytest`
Expected: all PASS, including `tests/test_active_role_access.py`, which now also parametrises over the two comment routes.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/events/service.py backend/app/modules/events/router.py backend/tests/test_event_comments_api.py
git commit -m "feat(events): let organiser and coordinator discuss an event

GET and POST /events/{id}/comments reuse the event's visibility rules, so
only the owning organiser and the assigned coordinator in their active
roles can read or post, and closed events keep a read-only thread.
SCRUM-61"
```

---

### Task 4: Live API checks

**Files:**
- Modify: `backend/scripts/verify_live.py` (add checks after the TC-ROLE checks, before `expect_field_error`)

**Interfaces:**
- Consumes: seeded fixture event `e0000000-0000-4000-8000-000000000201` (`under_review`, organiser …0001, coordinator …0002); `ctx.shared(role)`, `expect_status`.
- Produces: checks `TC-CMT-007`, `TC-CMT-008`, `TC-CMT-009 (read)`. They only read, so they never change shared data.

- [ ] **Step 1: Add the checks**

```python
FIXTURE_EVENT = "e0000000-0000-4000-8000-000000000201"  # supabase/seed.sql: under_review, assigned


@check("TC-CMT-009", "The organiser and the assigned coordinator both read the event's comment thread")
def _(ctx: Context) -> None:
    for role in ("event_organiser", "event_coordinator"):
        response = ctx.client.get(f"{ctx.api}/events/{FIXTURE_EVENT}/comments", headers=ctx.shared(role).headers)
        expect_status(response, 200)
        comments = response.json().get("comments")
        expect(isinstance(comments, list), f"{role}: response has no comments list")
        for comment in comments:
            expect({"id", "body", "created_at", "author"} <= comment.keys(), f"{role}: comment is missing fields")


@check("TC-CMT-008", "Venue staff, tech support and attendees can neither read nor post comments")
def _(ctx: Context) -> None:
    url = f"{ctx.api}/events/{FIXTURE_EVENT}/comments"
    for role in ("venue_staff", "tech_support", "attendee"):
        headers = ctx.shared(role).headers
        expect_status(ctx.client.get(url, headers=headers), 403)
        expect_status(ctx.client.post(url, headers=headers, json={"body": "live check"}), 403)
```

Only one organiser and one coordinator are seeded, so TC-CMT-006/007 (another organiser, another coordinator) stay covered by pytest, not by a live check. Check `ACCOUNTS` in `verify_live.py` has keys for `tech_support` and `attendee`; use whatever keys it defines.

- [ ] **Step 2: Run them against a backend on this branch**

Start a backend from `backend/` on a spare port if 8000 is taken (`uvicorn app.main:app --port 8010`), then run:
`python scripts/verify_live.py --api http://localhost:8010/api/v1 -k TC-CMT`
Expected: both checks PASS. (Check `--api`'s expected format in the script's `--help` first.)

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/verify_live.py
git commit -m "test(events): live-check comment access on the real API

Reads the seeded fixture's thread as both parties and confirms the other
roles get 403, without posting anything to shared data. SCRUM-61"
```

---

### Task 5: Frontend rules, API client and store

**Files:**
- Create: `frontend/src/features/events/comments.js`
- Create: `frontend/src/features/events/eventCommentsStore.js`
- Modify: `frontend/src/services/api.js` (inside `eventsApi`, after `history`)
- Test: `frontend/src/features/events/__tests__/comments.spec.js`
- Test: `frontend/src/features/events/__tests__/eventCommentsStore.spec.js`

**Interfaces:**
- Produces:
  - `COMMENT_MAX_LENGTH = 1000`, `COMMENTABLE_STATUSES` (array), `canPost(status) -> boolean`, `hasThread(status) -> boolean` (false only for `draft`), `validateComment(text) -> string | null` (error message or null)
  - `eventsApi.listComments(eventId, token)`, `eventsApi.addComment(eventId, body, token)`
  - `useEventCommentsStore` with state `{ eventId, comments, isLoading, isPosting, error }` and actions `load(eventId)`, `post(body) -> Promise<boolean>`

- [ ] **Step 1: Write the failing rules test**

`frontend/src/features/events/__tests__/comments.spec.js`:

```js
import { describe, expect, it } from "vitest";

import { canPost, COMMENT_MAX_LENGTH, hasThread, validateComment } from "@/features/events/comments";

describe("comment rules (SCRUM-61)", () => {
  it("accepts comments from submission until the event closes", () => {
    for (const status of ["submitted", "under_review", "returned", "planning", "confirmed"]) {
      expect(canPost(status)).toBe(true);
    }
    for (const status of ["draft", "rejected", "cancelled", "completed", undefined]) {
      expect(canPost(status)).toBe(false);
    }
  });

  it("has a thread for every status except draft", () => {
    expect(hasThread("draft")).toBe(false);
    expect(hasThread("rejected")).toBe(true);
    expect(hasThread("under_review")).toBe(true);
  });

  it("caps a comment at the API's 1000 characters", () => {
    expect(COMMENT_MAX_LENGTH).toBe(1000);
    expect(validateComment("x".repeat(1000))).toBeNull();
    expect(validateComment("x".repeat(1001))).toBe("Keep it to 1000 characters.");
  });

  it("refuses an empty or whitespace-only comment", () => {
    for (const text of ["", "   ", "\n\t "]) {
      expect(validateComment(text)).toBe("A comment can't be empty.");
    }
  });

  it("measures the trimmed text", () => {
    expect(validateComment(`  ${"x".repeat(1000)}  `)).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to confirm it fails**

Run (from `frontend/`): `npx vitest run src/features/events/__tests__/comments.spec.js`
Expected: FAIL — `Failed to resolve import "@/features/events/comments"`.

- [ ] **Step 3: Implement the rules**

`frontend/src/features/events/comments.js`:

```js
// SCRUM-61 comment rules. The API is the enforcement point (events/service.py,
// public.add_event_comment); these only avoid offering a post that would fail.

// Mirrors the API's COMMENT_MAX_LENGTH ([Assumption], REQUIREMENTS §9).
export const COMMENT_MAX_LENGTH = 1000;

export const COMMENTABLE_STATUSES = ["submitted", "under_review", "returned", "planning", "confirmed"];

export function canPost(status) {
  return COMMENTABLE_STATUSES.includes(status);
}

export function hasThread(status) {
  return Boolean(status) && status !== "draft";
}

export function validateComment(text) {
  const trimmed = (text ?? "").trim();
  if (!trimmed) return "A comment can't be empty.";
  if (trimmed.length > COMMENT_MAX_LENGTH) return `Keep it to ${COMMENT_MAX_LENGTH} characters.`;
  return null;
}
```

- [ ] **Step 4: Run it to confirm it passes**

Run: `npx vitest run src/features/events/__tests__/comments.spec.js`
Expected: PASS.

- [ ] **Step 5: Add the API client methods**

In `frontend/src/services/api.js`, inside `eventsApi` after `history(...)`:

```js
  // SCRUM-61: the organiser–coordinator discussion thread.
  listComments(eventId, token) {
    return request(`/events/${encodeURIComponent(eventId)}/comments`, { token });
  },
  addComment(eventId, body, token) {
    return request(`/events/${encodeURIComponent(eventId)}/comments`, { method: "POST", body: { body }, token });
  },
```

- [ ] **Step 6: Write the failing store test**

`frontend/src/features/events/__tests__/eventCommentsStore.spec.js`:

```js
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useEventCommentsStore } from "@/features/events/eventCommentsStore";
import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  eventsApi: { listComments: vi.fn(), addComment: vi.fn() },
}));

const FIRST = { id: "c1", body: "First", created_at: "2026-10-02T03:00:00Z", author: { id: "o1", full_name: "Olivia Tan", role: "event_organiser" } };
const SECOND = { id: "c2", body: "Second", created_at: "2026-10-02T04:00:00Z", author: { id: "m1", full_name: "Marcus Lim", role: "event_coordinator" } };

function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}

describe("useEventCommentsStore (SCRUM-61)", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    const auth = useAuthStore();
    auth.token = "access";
    auth.profile = { id: "o1", role: "event_organiser", full_name: "Olivia Tan" };
  });

  it("loads the thread for an event", async () => {
    eventsApi.listComments.mockResolvedValue({ comments: [FIRST] });
    const store = useEventCommentsStore();

    await store.load("event-1");

    expect(eventsApi.listComments).toHaveBeenCalledWith("event-1", "access");
    expect(store.comments).toEqual([FIRST]);
    expect(store.error).toBeNull();
    expect(store.isLoading).toBe(false);
  });

  it("clears the previous event's thread before loading another", async () => {
    eventsApi.listComments.mockResolvedValueOnce({ comments: [FIRST] });
    const store = useEventCommentsStore();
    await store.load("event-1");
    const pending = deferred();
    eventsApi.listComments.mockReturnValueOnce(pending.promise);

    const loading = store.load("event-2");

    expect(store.comments).toEqual([]);
    pending.resolve({ comments: [SECOND] });
    await loading;
    expect(store.comments).toEqual([SECOND]);
  });

  it("drops a response for an event that is no longer current", async () => {
    const slow = deferred();
    eventsApi.listComments.mockReturnValueOnce(slow.promise).mockResolvedValueOnce({ comments: [SECOND] });
    const store = useEventCommentsStore();

    const first = store.load("event-1");
    await store.load("event-2");
    slow.resolve({ comments: [FIRST] });
    await first;

    expect(store.eventId).toBe("event-2");
    expect(store.comments).toEqual([SECOND]);
  });

  it("reports a load failure", async () => {
    eventsApi.listComments.mockRejectedValue(new Error("Network down"));
    const store = useEventCommentsStore();

    await store.load("event-1");

    expect(store.comments).toEqual([]);
    expect(store.error).toBe("Network down");
  });

  it("posts the trimmed text and appends the saved comment", async () => {
    eventsApi.listComments.mockResolvedValue({ comments: [FIRST] });
    eventsApi.addComment.mockResolvedValue(SECOND);
    const store = useEventCommentsStore();
    await store.load("event-1");

    const ok = await store.post("  Second  ");

    expect(ok).toBe(true);
    expect(eventsApi.addComment).toHaveBeenCalledWith("event-1", "Second", "access");
    expect(store.comments).toEqual([FIRST, SECOND]);
    expect(store.isPosting).toBe(false);
  });

  it("keeps the thread and reports the error when posting fails", async () => {
    eventsApi.listComments.mockResolvedValue({ comments: [FIRST] });
    eventsApi.addComment.mockRejectedValue(new Error("Comments are closed for a rejected event."));
    const store = useEventCommentsStore();
    await store.load("event-1");

    const ok = await store.post("Late question");

    expect(ok).toBe(false);
    expect(store.comments).toEqual([FIRST]);
    expect(store.error).toBe("Comments are closed for a rejected event.");
    expect(store.isPosting).toBe(false);
  });

  it("does not post an invalid comment", async () => {
    const store = useEventCommentsStore();
    store.eventId = "event-1";

    expect(await store.post("   ")).toBe(false);
    expect(eventsApi.addComment).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 7: Run it to confirm it fails**

Run: `npx vitest run src/features/events/__tests__/eventCommentsStore.spec.js`
Expected: FAIL — `Failed to resolve import "@/features/events/eventCommentsStore"`.

- [ ] **Step 8: Implement the store**

`frontend/src/features/events/eventCommentsStore.js`:

```js
import { defineStore } from "pinia";

import { validateComment } from "@/features/events/comments";
import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

/**
 * The discussion thread on one event (SCRUM-61), shared by the organiser's and the
 * coordinator's event pages. `eventId` marks which event the state belongs to; every
 * request re-checks it after its await, so a slow response for a previous event can
 * never land on the current one (the same guard as useEventReviewStore).
 */
export const useEventCommentsStore = defineStore("eventComments", {
  state: () => ({ eventId: null, comments: [], isLoading: false, isPosting: false, error: null }),

  actions: {
    async load(eventId) {
      const auth = useAuthStore();
      if (this.eventId !== eventId) this.comments = [];
      this.eventId = eventId;
      this.isLoading = true;
      this.error = null;
      try {
        const response = await auth.withSession((token) => eventsApi.listComments(eventId, token));
        if (this.eventId !== eventId) return;
        this.comments = response?.comments ?? [];
      } catch (error) {
        if (this.eventId !== eventId) return;
        this.comments = [];
        this.error = error.message;
      } finally {
        if (this.eventId === eventId) this.isLoading = false;
      }
    },

    async post(text) {
      const eventId = this.eventId;
      if (!eventId || validateComment(text)) return false;
      const auth = useAuthStore();
      this.isPosting = true;
      this.error = null;
      try {
        const saved = await auth.withSession((token) => eventsApi.addComment(eventId, text.trim(), token));
        if (this.eventId !== eventId) return false;
        this.comments = [...this.comments, saved];
        return true;
      } catch (error) {
        if (this.eventId === eventId) this.error = error.message;
        return false;
      } finally {
        if (this.eventId === eventId) this.isPosting = false;
      }
    },
  },
});
```

- [ ] **Step 9: Run both specs to confirm they pass**

Run: `npx vitest run src/features/events/__tests__/comments.spec.js src/features/events/__tests__/eventCommentsStore.spec.js`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/features/events/comments.js frontend/src/features/events/eventCommentsStore.js frontend/src/services/api.js frontend/src/features/events/__tests__/comments.spec.js frontend/src/features/events/__tests__/eventCommentsStore.spec.js
git commit -m "feat(events): load and post event comments from the SPA

Adds the comment rules, API calls and a store that ignores responses for
an event the user has already left. SCRUM-61"
```

---

### Task 6: `EventDiscussion` component

**Files:**
- Create: `frontend/src/components/events/EventDiscussion.vue`
- Test: `frontend/src/components/events/__tests__/EventDiscussion.spec.js`

**Interfaces:**
- Consumes: `useEventCommentsStore`, `canPost`, `COMMENT_MAX_LENGTH`, `validateComment` (Task 5); `ROLE_LABELS` from `@/stores/auth`; `BauhausButton`, `BauhausEmptyState`.
- Produces: `<EventDiscussion :event-id="…" :status="…" />` — loads the thread on mount and whenever `eventId` changes.

- [ ] **Step 1: Write the failing component test**

`frontend/src/components/events/__tests__/EventDiscussion.spec.js`:

```js
import { createPinia, setActivePinia } from "pinia";
import { createApp, h, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import EventDiscussion from "@/components/events/EventDiscussion.vue";
import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  eventsApi: { listComments: vi.fn(), addComment: vi.fn() },
}));

const COMMENT = {
  id: "c1", body: "Can we recce the hall on Friday?", created_at: "2026-10-02T03:00:00Z",
  author: { id: "o1", full_name: "Olivia Tan", role: "event_organiser" },
};
const mounted = [];

async function mountDiscussion(props = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.profile = { id: "o1", role: "event_organiser", full_name: "Olivia Tan" };
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(EventDiscussion, { eventId: "event-1", status: "under_review", ...props }) });
  app.use(pinia);
  app.mount(el);
  mounted.push(app);
  await vi.waitFor(() => expect(eventsApi.listComments).toHaveBeenCalled());
  await nextTick();
  await nextTick();
}

async function type(text) {
  const textarea = document.querySelector("textarea");
  textarea.value = text;
  textarea.dispatchEvent(new Event("input"));
  await nextTick();
}

const postButton = () => document.querySelector('button[aria-label="Post comment"]');

describe("EventDiscussion (SCRUM-61)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    eventsApi.listComments.mockResolvedValue({ comments: [COMMENT] });
  });

  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("shows each comment with its author, role and Singapore time", async () => {
    await mountDiscussion();

    const text = document.body.textContent;
    expect(text).toContain("Can we recce the hall on Friday?");
    expect(text).toContain("Olivia Tan");
    expect(text).toContain("Event Organiser");
    expect(text).toContain("11:00"); // 03:00Z is 11:00 in Singapore
  });

  it("shows an empty state when nobody has commented", async () => {
    eventsApi.listComments.mockResolvedValue({ comments: [] });
    await mountDiscussion();

    expect(document.body.textContent).toContain("No comments yet");
  });

  it("names a comment whose author was removed", async () => {
    eventsApi.listComments.mockResolvedValue({ comments: [{ ...COMMENT, author: null }] });
    await mountDiscussion();

    expect(document.body.textContent).toContain("Unknown user");
  });

  it("wraps long words so the thread never widens the page", async () => {
    eventsApi.listComments.mockResolvedValue({ comments: [{ ...COMMENT, body: "x".repeat(1000) }] });
    await mountDiscussion();

    expect(document.querySelector("[data-comment-body]").className).toContain("break-words");
  });

  it("counts characters against the 1000 limit", async () => {
    await mountDiscussion();
    await type("Hello");

    expect(document.body.textContent).toContain("5 / 1000");
  });

  it("disables Post for whitespace", async () => {
    await mountDiscussion();
    await type("   \n ");

    expect(postButton().disabled).toBe(true);
  });

  it("posts the comment, appends it and clears the box", async () => {
    eventsApi.addComment.mockResolvedValue({ ...COMMENT, id: "c2", body: "Booked for 3pm." });
    await mountDiscussion();
    await type("  Booked for 3pm.  ");

    postButton().click();
    await vi.waitFor(() => expect(eventsApi.addComment).toHaveBeenCalledWith("event-1", "Booked for 3pm.", "access"));
    await nextTick();

    expect(document.body.textContent).toContain("Booked for 3pm.");
    expect(document.querySelector("textarea").value).toBe("");
  });

  it("keeps the draft text when posting fails", async () => {
    eventsApi.addComment.mockRejectedValue(new Error("Comments are closed for this event. Reload."));
    await mountDiscussion();
    await type("Late question");

    postButton().click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());

    expect(document.querySelector('[role="alert"]').textContent).toContain("Comments are closed for this event. Reload.");
    expect(document.querySelector("textarea").value).toBe("Late question");
  });

  it("is read-only once the event is closed", async () => {
    await mountDiscussion({ status: "rejected" });

    expect(document.querySelector("textarea")).toBeNull();
    expect(document.body.textContent).toContain("This discussion is closed");
    expect(document.body.textContent).toContain("Can we recce the hall on Friday?");
  });
});
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `npx vitest run src/components/events/__tests__/EventDiscussion.spec.js`
Expected: FAIL — `Failed to resolve import "@/components/events/EventDiscussion.vue"`.

- [ ] **Step 3: Implement the component**

`frontend/src/components/events/EventDiscussion.vue`:

```vue
<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import { canPost, COMMENT_MAX_LENGTH, validateComment } from "@/features/events/comments";
import { useEventCommentsStore } from "@/features/events/eventCommentsStore";
import { ROLE_LABELS } from "@/stores/auth";

const props = defineProps({
  eventId: { type: String, required: true },
  status: { type: String, required: true },
});

const store = useEventCommentsStore();
const draft = ref("");
const isOpen = computed(() => canPost(props.status));
const canSubmit = computed(() => !validateComment(draft.value) && !store.isPosting);

const formatter = new Intl.DateTimeFormat("en-SG", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Singapore",
});

watch(
  () => props.eventId,
  (eventId) => {
    draft.value = "";
    store.load(eventId);
  },
  { immediate: true },
);

async function submit() {
  if (!canSubmit.value) return;
  if (await store.post(draft.value)) draft.value = "";
}
</script>

<template>
  <section aria-labelledby="discussion-title">
    <h2 id="discussion-title" class="mb-6 text-2xl font-black uppercase tracking-tight">Discussion</h2>

    <p v-if="store.isLoading && !store.comments.length" class="text-sm font-bold uppercase tracking-widest text-ink/70">
      Loading comments…
    </p>
    <BauhausEmptyState
      v-else-if="!store.comments.length"
      title="No comments yet"
      :detail="isOpen ? 'Questions and planning notes for this event appear here.' : ''"
    />
    <ol v-else class="space-y-4">
      <li v-for="comment in store.comments" :key="comment.id" class="border-l-4 border-ink pl-4">
        <p class="text-xs font-bold text-ink/70">
          <span class="font-black uppercase tracking-wide text-ink">{{ comment.author?.full_name ?? "Unknown user" }}</span>
          <template v-if="comment.author?.role"> · {{ ROLE_LABELS[comment.author.role] ?? comment.author.role }}</template>
          · {{ formatter.format(new Date(comment.created_at)) }}
        </p>
        <p data-comment-body class="mt-1 whitespace-pre-wrap break-words text-sm font-medium">{{ comment.body }}</p>
      </li>
    </ol>

    <p
      v-if="store.error"
      role="alert"
      class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas"
    >
      {{ store.error }}
    </p>

    <form v-if="isOpen" class="mt-6" @submit.prevent="submit">
      <label for="comment-body" class="block text-xs font-bold uppercase tracking-widest text-ink/70">Add a comment</label>
      <textarea
        id="comment-body"
        v-model="draft"
        rows="3"
        :maxlength="COMMENT_MAX_LENGTH"
        class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
      ></textarea>
      <div class="mt-2 flex items-center justify-between gap-4">
        <p class="text-xs font-bold text-ink/70">{{ draft.length }} / {{ COMMENT_MAX_LENGTH }}</p>
        <BauhausButton type="submit" variant="secondary" aria-label="Post comment" :disabled="!canSubmit">
          {{ store.isPosting ? "Posting…" : "Post" }}
        </BauhausButton>
      </div>
    </form>
    <p v-else class="mt-6 text-sm font-medium text-ink/70">This discussion is closed. Earlier comments stay on the record.</p>
  </section>
</template>
```

- [ ] **Step 4: Run it to confirm it passes**

Run: `npx vitest run src/components/events/__tests__/EventDiscussion.spec.js`
Expected: PASS. If the SGT time assertion fails because of locale formatting (e.g. `11:00 am`), keep `toContain("11:00")` and check the actual string rather than changing the formatter.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/events/EventDiscussion.vue frontend/src/components/events/__tests__/EventDiscussion.spec.js
git commit -m "feat(events): add the event discussion panel

Shows each comment's author, role and Singapore time, posts new ones,
and turns read-only once the event closes. SCRUM-61"
```

---

### Task 7: Mount the discussion on both event pages

**Files:**
- Modify: `frontend/src/views/events/EventDetailView.vue` (import; new card after the History card, ~line 131)
- Modify: `frontend/src/views/events/CoordinatorEventView.vue` (import; new card after the History card, ~line 159)
- Modify: `frontend/src/views/__tests__/EventDetailView.spec.js` (mock + one test)
- Modify: `frontend/src/views/__tests__/CoordinatorEventView.spec.js` (mock + one test)

**Interfaces:**
- Consumes: `EventDiscussion` (Task 6), `hasThread` (Task 5).

- [ ] **Step 1: Write the failing view tests**

In both view specs, add `listComments: vi.fn(), addComment: vi.fn()` to the mocked `eventsApi` object. In `CoordinatorEventView.spec.js`'s `mountView` and `EventDetailView.spec.js`'s `mountDetail`, next to the existing `eventsApi.history.mockResolvedValue(...)` line, add:

```js
  eventsApi.listComments.mockResolvedValue({ comments: [] });
```

Then add inside the existing `describe` block of `CoordinatorEventView.spec.js`:

```js
  it("shows the event's discussion thread (SCRUM-61)", async () => {
    const el = await mountView(eventResponse());

    await vi.waitFor(() => expect(eventsApi.listComments).toHaveBeenCalledWith("event-1", "access"));
    expect(el.textContent).toContain("Discussion");
  });
```

And inside the existing `describe("EventDetailView status", …)` block of `EventDetailView.spec.js`:

```js
  it("shows the discussion once the request is submitted (SCRUM-61)", async () => {
    const el = await mountDetail(eventResponse({ status: "under_review" }));

    await vi.waitFor(() => expect(eventsApi.listComments).toHaveBeenCalledWith("event-1", "access"));
    expect(el.textContent).toContain("Discussion");
  });

  it("has no discussion on a draft (SCRUM-61)", async () => {
    const el = await mountDetail(eventResponse({ status: "draft" }));

    expect(el.textContent).not.toContain("Discussion");
    expect(eventsApi.listComments).not.toHaveBeenCalled();
  });
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `npx vitest run src/views/__tests__/EventDetailView.spec.js src/views/__tests__/CoordinatorEventView.spec.js`
Expected: the new "shows the discussion" tests FAIL (no "Discussion" text); the draft test passes trivially; existing tests still PASS.

- [ ] **Step 3: Mount the component**

`EventDetailView.vue` — add imports:

```js
import EventDiscussion from "@/components/events/EventDiscussion.vue";
import { hasThread } from "@/features/events/comments";
```

and after the History `BauhausCard` inside the `<aside>`:

```vue
          <BauhausCard v-if="hasThread(event.status)" background="white" accent="none">
            <EventDiscussion :event-id="event.id" :status="event.status" />
          </BauhausCard>
```

`CoordinatorEventView.vue` — add `import EventDiscussion from "@/components/events/EventDiscussion.vue";` and after the History `BauhausCard`:

```vue
        <BauhausCard background="white" accent="none">
          <EventDiscussion :event-id="event.id" :status="event.status" />
        </BauhausCard>
```

(A coordinator never sees a draft — the API answers 404 — so no `hasThread` guard is needed there.)

- [ ] **Step 4: Run the full frontend suite and build**

Run (from `frontend/`): `npm test`, then `npm run build`
Expected: all specs PASS; build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/events/EventDetailView.vue frontend/src/views/events/CoordinatorEventView.vue frontend/src/views/__tests__/EventDetailView.spec.js frontend/src/views/__tests__/CoordinatorEventView.spec.js
git commit -m "feat(events): show the discussion on both event pages

The organiser sees it once a request is submitted and the assigned
coordinator on the review page, beside the status history. SCRUM-61"
```

---

### Task 8: Paper trail

**Files:**
- Modify: `docs/test-cases/events.md` (new section at the end), `docs/test-cases/README.md` (table row)
- Modify: `docs/REQUIREMENTS.md` (§8 comments row ~line 1240; §9 Q12 ~line 1286; new §9 assumption)
- Modify: `docs/IMPLEMENTATION_MAP.md` (Last updated line; §1 status rows; §2 endpoints and reuse; §3 reuse and specs; §4 migration row and count; §5 notifications note)
- Modify: `docs/BUILD_LOG.md` (append §4.23)

- [ ] **Step 1: Add the manual cases**

Append to `docs/test-cases/events.md` a `## Event comments (SCRUM-61)` section following README "Adding cases for a new story": preconditions (seeded organiser and coordinator; fixture `e0000000-…-0201` under review and assigned; reset with `event_review_fixture_reset.sql` afterwards and delete test comments only via that script if it is extended to clear `event_comments` for the fixtures — extend it in this step), then a case table with TC-CMT-001 to TC-CMT-013 exactly as titled in the spec §8, each with steps, input, expected result and priority (🔴 for 001, 002, 006–010; 🟠 for 003, 004, 011, 012; 🟢 for 005, 013). Then `### Traceability — SCRUM-61`: the spec §8 table, with the automated column filled with the real test names from Tasks 1–7. Then a short "Automated coverage today" note: TC-CMT-001/002/012 and phone-width layout are manual because they post to shared data or need a person's eye.

Also extend `supabase/verification/event_review_fixture_reset.sql` to `delete from public.event_comments where event_id in (<the two fixture ids>);` and the matching `notifications` rows of type `comment_added`, so a manual pass leaves the fixtures clean. Add `TC-CMT` to the `events.md` row in `docs/test-cases/README.md`.

- [ ] **Step 2: Update REQUIREMENTS.md**

- §8 comments row: replace with the built behaviour — organiser and assigned coordinator only, open statuses, read-only when closed, append-only, `comment_added` notification, [Team decision] labels, `event_comments`, "Built (SCRUM-61)".
- §9 Q12: mark answered — "Yes, built in release 1 as the organiser–coordinator thread (SCRUM-61, QA2-27)."
- §9: add "**Comment length (SCRUM-61):** **[Assumption]** 1000 characters after trimming, the same cap as the rejection reason and return message. Is a different limit expected?"

- [ ] **Step 3: Update IMPLEMENTATION_MAP.md**

- Replace the "Last updated" line with one entry for `feature/scrum-61-event-comments`.
- §1: add a SCRUM-61 row; change SCRUM-34, SCRUM-52 and SCRUM-33 from "not yet merged" to merged (check `git log --oneline main | grep -i "scrum-3[34]"` for the PR numbers).
- §2 endpoints: the two comment routes with their guard and every status code from Task 3.
- §2 reuse: `service.comments` / `service.add_comment`, `repository.list_comments` / `add_comment`, `COMMENTABLE_STATUSES`, `COMMENT_MAX_LENGTH`.
- §3 reuse: `features/events/comments.js`, `useEventCommentsStore`, `EventDiscussion`; `eventsApi.listComments` / `addComment`; bump the spec-file count.
- §4: the `20261002120000_event_comments.sql` row (table, RLS, function, grants, applied-to-live note) and the migration count (eighteen); add `event_comment_checks.sql` to the verification script list.
- §5: extend the notifications note with `comment_added` (to the other party, SCRUM-61).

- [ ] **Step 4: Append the BUILD_LOG entry**

Add `### 4.23. SCRUM-61 — Comment and discuss on my event` following the template of §4.18: the Jira story and four criteria verbatim, decisions and their labels, what was built per layer, tests, real-system verification, and what was not verified.

- [ ] **Step 5: Commit**

```bash
git add docs/test-cases/events.md docs/test-cases/README.md docs/REQUIREMENTS.md docs/IMPLEMENTATION_MAP.md docs/BUILD_LOG.md supabase/verification/event_review_fixture_reset.sql
git commit -m "docs(events): record SCRUM-61 comments in the paper trail

Adds TC-CMT cases traced to each acceptance criterion, answers the open
question on comments, and brings the implementation map up to date,
including the review stories that had already merged. SCRUM-61"
```

---

### Task 9: Real-system verification and the manual pass

**Files:**
- Create: run logs under `docs/test-cases/runs/` (written by the recorders and by hand)

- [ ] **Step 1: Full automated suites**

Run `pytest` from `backend/` and `npm test` from `frontend/`. Expected: all PASS. Record the counts.

- [ ] **Step 2: Real browser smoke test of the new flow**

Start this branch's backend and frontend on spare ports if 8000/5173 are taken. In the in-app browser, sign in as `coordinator@connectsphere.dev`, open `/coordinator/events/e0000000-0000-4000-8000-000000000201`, post a comment, reload, and check the console for errors. Then sign in as `organiser@connectsphere.dev`, open `/events/e0000000-0000-4000-8000-000000000201`, confirm the coordinator's comment shows with name, role and SGT time, and reply. Query `notifications` with `execute_sql` to confirm one `comment_added` row each way. Then run `event_review_fixture_reset.sql` to clean up.

Ask the developer before this step: it posts to the shared fixture event (cleaned up afterwards).

- [ ] **Step 3: Live checks with recording on**

From `backend/`: `python scripts/verify_live.py --record` (with `--api` if on a spare port). From `frontend/`: `npm run test:e2e:record` (with `E2E_BASE_URL` / `E2E_API_URL` if needed). Any failure is a finding to fix or report, not something to re-run until it passes.

- [ ] **Step 4: Ask the developer for the manual pass**

Give this checklist, grouped by page, and do not mark any as passed yourself:

- **Coordinator review page** (`/coordinator/events/e0000000-…-0201`, as the coordinator): TC-CMT-002 post a comment; TC-CMT-009 name, role and SGT time read correctly; TC-CMT-003 the counter and disabled Post on whitespace; layout at 375 px wide (no sideways scroll with a long URL in a comment).
- **Organiser event page** (`/events/e0000000-…-0201`, as the organiser): TC-CMT-001 reply; TC-CMT-012 reload keeps both comments oldest first; wording of the empty state and the closed note; layout at 375 px.
- **A closed event** (set the fixture to `rejected` via SQL, then reset): TC-CMT-004 the thread is visible and the composer is replaced by the closed note.

- [ ] **Step 5: Record and commit the results**

Write the developer's results as a manual run file using the template in `docs/test-cases/runs/README.md`. Any failure also becomes the next defect number in `docs/DEFECTS.md`.

```bash
git add docs/test-cases/runs/
git commit -m "test(events): record SCRUM-61 live and manual runs

Evidence that comments were exercised against the real API, database
and browser. SCRUM-61"
```

- [ ] **Step 6: Final report and Jira**

Report what changed, how it was verified, what wasn't verified and why, and follow-ups (the bell is SCRUM-27; venue staff and tech support comments wait for their event links). Phase 4 (PR, review, merge, Jira to Done) is the developer's; when a PR is opened, suggest moving SCRUM-61 to In Review and ask first.
