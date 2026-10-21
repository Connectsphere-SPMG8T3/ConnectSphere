# Sprint 4 In-App Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Plan style (the owner's rule for plans Codex may implement):** this plan states requirements, exact interfaces, tests and acceptance criteria. It does not contain implementation bodies. The implementer writes the code; tests below are given as code and are the definition of done.

**Goal:** Give every role a working notification bell (113), deliver attendee notifications and the day-before reminder (53), and send staff reminders about incomplete arrangements (90), all in-app only.

**Architecture:** Notification rows keep being written inside the Postgres function that performs each action (NT-R3). A `BEFORE INSERT` trigger stamps each row with the role it is addressed to, using a type registry, so the API can filter on the caller's active role without touching the 31 existing functions. A new `notifications` backend module serves the unread-count poll, the list and mark-read. The SPA polls every 10 seconds while the tab is visible (ADR-0004). Reminders are SQL functions run by `pg_cron`, made idempotent with a dedupe key.

**Tech Stack:** PostgreSQL (Supabase migrations, `pg_cron`), FastAPI + supabase-py (`backend/`), Vue 3 + Pinia + Vitest (`frontend/`).

**Spec:** `docs/superpowers/specs/2026-10-20-sprint4-in-app-notifications-design.md`. Also read `docs/adr/0004-notification-delivery.md` and `docs/REQUIREMENTS.md` §6.20.

**Backlog:** 113 In-app notifications, 53 Receive notifications about my events, 90 Reminders. 114 (email) is out of Sprint 4. Branch `feature/scrum-113-in-app-notifications` (one branch for the three; split if the team prefers one PBI per branch, tasks 1 to 3 are 113, task 4 is 53, task 5 is 53 AC4 and 90).

## Global Constraints

- In-app only. No email, SMS, push, outbox table or worker (spec "Out of scope").
- Poll interval is 10 seconds while the tab is visible; one constant (ADR-0004).
- The API authorises by the session's **active** role (`CurrentUser.role`), never by every role in `user_roles` (`AGENTS.md` security baseline). A user acting as role Y gets no role-X rows even if they hold X; prove it with a raw request.
- NT-R1: the actor is never notified of their own action. NT-R2: text never exposes information the recipient's role can't see (no staff notes, private safety notes, venue block reasons, other events' details). NT-R3: a notification commits with its action. NT-R4: in-app notifications cannot be switched off.
- Database functions are `security definer`, `set search_path = ''`, `execute` revoked from `public, anon, authenticated`, granted to `service_role` only (same as `20261020100000_coordinator_assignment.sql`).
- Backend: `def` (sync) endpoints; all data access through `app.db.supabase.get_supabase_admin_client()` inside `repository.py`; module layout `router.py`, `schemas.py`, `service.py`, `repository.py`; tests patch `repository` functions (see `backend/tests/test_event_comments_api.py`).
- Frontend: Composition API `<script setup>`, Pinia, calls through `authStore.withSession`, API clients in `frontend/src/services/api.js`, feature code under `frontend/src/features/notifications/`, tests with `vi.mock("@/services/api")`.
- Coverage: 100% of new and changed code in `backend/app/` and `frontend/src/`, or each uncovered line listed with the reason (`docs/CI.md` §4 item 2).
- TDD: for every step that adds behaviour, write the failing test, run it and see it fail for the stated reason, then write the minimum code.
- Migration filenames: the latest is `20261020110000`; use `20261021100000`, `…110000`, `…120000` in order. Never edit an applied migration. The developer pushes migrations (`supabase db push --dry-run`, then ask; see the live-check memory notes).
- Roles in `public.user_role`: `event_organiser`, `event_coordinator`, `event_coordinator_lead`, `venue_staff`, `tech_support`, `safety_officer`, `attendee`.
- Messages are role-safe text written by the function that raises the notification.
- Nothing is pushed, no PR opened and no sheet edited without the developer asking.

## Review Focus

Failure modes the spec implies that are easy to miss; each is pinned by a test in the task named.

1. **Role switch leaves a stale bell.** A user who switches active role must see the new role's count and list at once, not the old role's. (Task 3: store resets on role change.)
2. **A type missing from the registry** produces a row with a null role. It must be hidden from every role (fail closed), and the database check must fail when any type used by a function is unregistered. (Task 1.)
3. **Same-timestamp rows.** Several notifications are created in one transaction and share `created_at`. Paging by `created_at` alone would skip or repeat rows. (Task 2: keyset on `(created_at, id)`.)
4. **Someone else's notification id**, or a row for another of the caller's roles, on mark-read: 404, never 200 and never a change. (Task 2.)
5. **Reminders run twice** (cron overlap, a manual re-run, a restart) must not duplicate; and a cancelled event, a waitlisted or withdrawn attendee, or an event whose arrangements are complete gets none. (Task 5.)
6. **A holder of two roles listed for one type** (for example an organiser who is also the event's coordinator receiving `comment_added`): the trigger picks the first role in the registry order that the recipient holds. This is a known limitation; the test documents it rather than hiding it. (Task 1.)
7. **Hidden tab / overlapping polls.** A tick is skipped while one is in flight; nothing polls while the tab is hidden; becoming visible polls at once. (Task 3.)

---

## File Structure

| File | Responsibility |
|---|---|
| `supabase/migrations/20261021100000_notification_roles_and_helper.sql` (create) | `recipient_role`, `dedupe_key`, `notification_types`, trigger, backfill, `add_notification`, new index |
| `supabase/migrations/20261021110000_notify_registered_attendees.sql` (create) | `notify_registered_attendees` (after Dev 1's registrations table exists) |
| `supabase/migrations/20261021120000_notification_reminders.sql` (create) | the two reminder functions and their `cron.schedule` jobs |
| `supabase/verification/notification_role_checks.sql`, `notification_reminder_checks.sql` (create) | rolled-back SQL checks, same style as `event_comment_checks.sql` |
| `backend/app/modules/notifications/{__init__,router,schemas,service,repository}.py` (create) | read API |
| `backend/app/main.py` (modify) | register the router |
| `backend/tests/test_notifications_api.py`, `test_notifications_repository.py` (create) | API and repository tests |
| `frontend/src/services/api.js` (modify) | `notificationsApi` |
| `frontend/src/features/notifications/{notificationsStore.js,polling.js,format.js}` (create) | store, visibility-aware poller, time label |
| `frontend/src/components/common/NotificationBell.vue` (create), `TopBar.vue` (modify) | the bell and panel; TopBar uses it |
| `frontend/src/features/notifications/__tests__/*.spec.js`, `components/common/__tests__/NotificationBell.spec.js` (create) | frontend tests |
| `docs/IMPLEMENTATION_MAP.md`, `docs/BUILD_LOG.md`, `docs/test-cases/notifications.md`, `docs/REQUIREMENTS.md` §6.20, `docs/adr/0004-…md` (modify/create) | paper trail |

---

### Task 1: Database foundation (113 AC4, NT-R1, NT-R3)

**Files:**
- Create: `supabase/migrations/20261021100000_notification_roles_and_helper.sql`
- Create: `supabase/verification/notification_role_checks.sql`

**Interfaces:**
- Produces (SQL):
  - `public.notification_types(type text primary key, recipient_roles public.user_role[] not null)` with a check that the array is non-empty. Order matters: the first role the recipient holds wins.
  - `public.notifications.recipient_role public.user_role null`, `public.notifications.dedupe_key text null`.
  - Unique partial index `notifications_dedupe_key_uidx` on `(recipient_id, dedupe_key) where dedupe_key is not null`.
  - Index `notifications_recipient_role_unread_idx` on `(recipient_id, recipient_role, read_at, created_at desc, id)`.
  - Trigger `private.set_notification_role()` `BEFORE INSERT` on `notifications`: when `new.recipient_role is null`, set it to the first element of `notification_types.recipient_roles` (for `new.type`) that the recipient holds in `public.user_roles`. If the type is unregistered, or the recipient holds none of its roles, leave it null.
  - `public.add_notification(p_recipient uuid, p_event uuid, p_type text, p_message text, p_actor uuid default null, p_dedupe_key text default null) returns uuid`: returns null (inserts nothing) when `p_recipient = p_actor` (NT-R1) or when the dedupe key already exists for that recipient; otherwise inserts and returns the new id.
- Registry content: every type used today. The implementer builds the list from three sources and records it in the migration: (a) `grep` the string literals inside `insert into public.notifications` across `supabase/migrations/`; (b) the `notify_type`/`p_notify_type` values passed from `backend/app/modules/*/` (`event_approved`, `event_rejected` and others found by `grep -rn "notify_type\|\"type\":" backend/app`); (c) `select distinct type from public.notifications` on the live project via the Supabase MCP. Roles per type follow `docs/REQUIREMENTS.md` §6.20 recipients table; for example `event_assigned` → `{event_coordinator}`, `event_coordinator_changed` → `{event_organiser}`, `venue_booking_requested` → `{venue_staff}`, `comment_added` → `{event_organiser, event_coordinator}`, `event_safety_approved` → `{event_organiser, event_coordinator, venue_staff, tech_support}` (one row per recipient, so list every role that can receive it).
- Backfill: set `recipient_role` on existing rows by the same rule (one `update … from` statement).
- Does not change any existing function.

- [ ] **Step 1: Write the failing verification script** `supabase/verification/notification_role_checks.sql`, in the style of `event_comment_checks.sql` (`begin; … rollback;`, raises on first failure, prints `NOTIFICATION ROLE CHECKS PASSED`). It must check, using the seeded accounts (organiser `…0001`, coordinator `…0002`, venue staff `…0003`) and a throwaway event:

```sql
-- 1. the trigger stamps the role from the registry
insert into public.notifications (recipient_id, event_id, type, message)
values (v_coordinator, v_event, 'event_assigned', 'x');
if (select recipient_role from public.notifications where type = 'event_assigned' and event_id = v_event) is distinct from 'event_coordinator' then
    raise exception 'ROLE FAIL: event_assigned was not stamped event_coordinator';
end if;
-- 2. an unregistered type stays null
insert into public.notifications (recipient_id, event_id, type, message)
values (v_coordinator, v_event, 'zz_unregistered_type', 'x');
if (select recipient_role from public.notifications where type = 'zz_unregistered_type') is not null then
    raise exception 'ROLE FAIL: an unregistered type must stay null';
end if;
-- 3. add_notification: NT-R1, dedupe, return values
if public.add_notification(v_organiser, v_event, 'event_coordinator_changed', 'm', v_organiser) is not null then
    raise exception 'ROLE FAIL: the actor was notified of their own action';
end if;
perform public.add_notification(v_organiser, v_event, 'event_coordinator_changed', 'm', v_coordinator, 'k1');
if public.add_notification(v_organiser, v_event, 'event_coordinator_changed', 'm', v_coordinator, 'k1') is not null then
    raise exception 'ROLE FAIL: the same dedupe key inserted twice';
end if;
-- 4. every type that existing functions can raise is registered
--    (a list of the types gathered in the Interfaces note, asserted against notification_types)
-- 5. grants: add_notification is not executable by anon/authenticated
```
Also assert the first-listed-role rule (limitation 6): give a throwaway profile both `event_organiser` and `event_coordinator` rows in `user_roles`, insert a `comment_added`, and expect `event_organiser`.

- [ ] **Step 2: Run it and confirm it fails** because the column and function do not exist.
Run (read-only against the live project, via the Supabase MCP `execute_sql`, or `psql "$DATABASE_URL" -f supabase/verification/notification_role_checks.sql`).
Expected: error `column "recipient_role" of relation "notifications" does not exist` (or the first check raising), not a typo in the script.

- [ ] **Step 3: Write the migration** to satisfy the Interfaces block. Add `comment on` lines for each new object, in the style of the other migrations, and note the known limitation 6 in the trigger's comment.

- [ ] **Step 4: Apply and re-run.** Ask the developer to push: `supabase db push --dry-run`, show it, then they run `supabase db push`. Re-run the script. Expected: `NOTIFICATION ROLE CHECKS PASSED`.

- [ ] **Step 5: Check advisories.** Supabase MCP `get_advisors` (security and performance). Expected: no new warnings from the new table, function or index.

- [ ] **Step 6: Commit** (migration + verification file; subject `feat(notifications): stamp each notification with its recipient role (SCRUM-113)`; body explains why: active-role filtering without touching existing functions).

**Acceptance:** script passes live; backfill leaves no row with a registered type and a null role; advisories clean.

---

### Task 2: Read API (113 AC1 to AC4)

**Files:**
- Create: `backend/app/modules/notifications/__init__.py`, `router.py`, `schemas.py`, `service.py`, `repository.py`
- Modify: `backend/app/main.py` (import `router as notifications_router`, include with `prefix=settings.api_v1_prefix`)
- Test: `backend/tests/test_notifications_api.py`, `backend/tests/test_notifications_repository.py`

**Interfaces:**
- Consumes: `get_current_user` / `CurrentUser` (`app.modules.auth.dependencies`), `get_supabase_admin_client`, Task 1's `recipient_role`.
- Produces (HTTP, prefix `/api/v1`, any signed-in role, 401 without a token):
  - `GET /notifications/unread-count` → `{"count": int, "latest_at": str | null}` for `recipient_id = caller AND recipient_role = caller's active role AND read_at is null`; `latest_at` is the newest `created_at` among that role's rows (read or unread), null when none.
  - `GET /notifications?limit=20&before=<cursor>` → `{"items": [NotificationItem], "next_before": str | null}`, newest first; `limit` 1 to 100 (422 outside); `before` is the `next_before` of the previous page, format `"<created_at ISO>|<id>"` (422 when malformed). Keyset on `(created_at desc, id desc)`.
  - `POST /notifications/{id}/read` → 200 `{"id": str, "read": true}`; 404 when the id is not the caller's in their active role; already-read is 200 and keeps the original `read_at`.
  - `POST /notifications/read-all` → 200 `{"updated": int}`; touches only the caller's unread rows in the active role.
  - `NotificationItem = {id: str, event_id: str | null, type: str, message: str, link: str | null, read: bool, created_at: str}`.
- Produces (Python):
  - `repository.count_unread(recipient_id: str, role: str) -> dict` returning `{"count": int, "latest_at": str | None}`
  - `repository.list_page(recipient_id: str, role: str, limit: int, before: tuple[str, str] | None) -> list[dict]` (rows as stored, newest first, up to `limit + 1` so the service can tell whether another page exists)
  - `repository.mark_read(notification_id: str, recipient_id: str, role: str) -> bool` (False when no such row for that recipient and role)
  - `repository.mark_all_read(recipient_id: str, role: str) -> int`
  - `service.link_for(role: str, event_id: str | None) -> str | None`: organiser → `/events/{id}`, coordinator → `/coordinator/events/{id}`, lead → `/lead/events/{id}`, tech_support → `/tech-support/events/{id}`, safety_officer → `/safety/events/{id}`, venue_staff → `/dashboard/venue-staff/requests`, attendee → `/dashboard/attendee`; `None` when `event_id` is null for the event-based roles.
  - `service.encode_cursor(created_at: str, id: str) -> str`, `service.decode_cursor(value: str) -> tuple[str, str]` (raises `ValueError` on malformed input; the router maps it to 422).

- [ ] **Step 1: Write the failing API tests** `backend/tests/test_notifications_api.py` (fixtures follow `test_event_comments_api.py`; `authenticate_as` is in `conftest.py`):

```python
"""113 in-app notifications, through the HTTP API with the repository mocked."""
import pytest
from app.modules.notifications import repository
from tests.test_event_comments_api import acting_as_another_role

USER_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_ID = "a0000000-0000-4000-8000-000000000009"
EVENT_ID = "e0000000-0000-4000-8000-000000000201"
BASE = "/api/v1/notifications"


def row(i, role="event_coordinator", read_at=None, created="2026-10-20T03:00:00+00:00"):
    return {"id": f"00000000-0000-4000-8000-{i:012d}", "recipient_id": USER_ID, "recipient_role": role,
            "event_id": EVENT_ID, "type": "event_assigned", "message": f"m{i}", "read_at": read_at,
            "created_at": created}


@pytest.fixture()
def inbox(monkeypatch):
    """In-memory rows keyed by (recipient, role); the fake repository enforces the same filters."""
    state = {"rows": [], "calls": []}

    def visible(recipient_id, role):
        return [r for r in state["rows"] if r["recipient_id"] == recipient_id and r["recipient_role"] == role]

    def count_unread(recipient_id, role):
        state["calls"].append(("count", recipient_id, role))
        rows = visible(recipient_id, role)
        return {"count": sum(1 for r in rows if r["read_at"] is None),
                "latest_at": max((r["created_at"] for r in rows), default=None)}

    def list_page(recipient_id, role, limit, before):
        state["calls"].append(("list", recipient_id, role, limit, before))
        rows = sorted(visible(recipient_id, role), key=lambda r: (r["created_at"], r["id"]), reverse=True)
        if before:
            rows = [r for r in rows if (r["created_at"], r["id"]) < before]
        return rows[: limit + 1]

    def mark_read(notification_id, recipient_id, role):
        for r in visible(recipient_id, role):
            if r["id"] == notification_id:
                r["read_at"] = r["read_at"] or "2026-10-20T04:00:00+00:00"
                return True
        return False

    def mark_all_read(recipient_id, role):
        n = 0
        for r in visible(recipient_id, role):
            if r["read_at"] is None:
                r["read_at"], n = "2026-10-20T04:00:00+00:00", n + 1
        return n

    for name, fn in [("count_unread", count_unread), ("list_page", list_page),
                     ("mark_read", mark_read), ("mark_all_read", mark_all_read)]:
        monkeypatch.setattr(repository, name, fn)
    return state


class TestUnreadCount:
    def test_counts_only_unread_rows_for_the_active_role(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=USER_ID)
        inbox["rows"] = [row(1), row(2, read_at="x"), row(3, role="event_organiser")]
        body = client.get(f"{BASE}/unread-count", headers=auth_headers).json()
        assert body["count"] == 1 and body["latest_at"]

    def test_requires_a_session(self, client):
        assert client.get(f"{BASE}/unread-count").status_code == 401

    @pytest.mark.parametrize("role", ["event_organiser", "event_coordinator", "event_coordinator_lead",
                                      "venue_staff", "tech_support", "safety_officer", "attendee"])
    def test_every_role_may_read_its_own(self, client, auth_headers, authenticate_as, inbox, role):
        authenticate_as(role, user_id=USER_ID)
        assert client.get(f"{BASE}/unread-count", headers=auth_headers).status_code == 200


class TestActiveRoleDenial:  # SCRUM-76, AGENTS.md security baseline
    def test_a_user_acting_as_another_role_sees_none_of_the_other_roles_rows(
        self, client, auth_headers, monkeypatch, inbox
    ):
        inbox["rows"] = [row(1, role="event_coordinator"), row(2, role="event_organiser")]
        acting_as_another_role(monkeypatch, USER_ID, holds="event_coordinator", acts_as="event_organiser")
        items = client.get(BASE, headers=auth_headers).json()["items"]
        assert [i["message"] for i in items] == ["m2"]
        assert client.get(f"{BASE}/unread-count", headers=auth_headers).json()["count"] == 1

    def test_marking_a_row_of_another_role_is_404_and_changes_nothing(
        self, client, auth_headers, monkeypatch, inbox
    ):
        inbox["rows"] = [row(1, role="event_coordinator")]
        acting_as_another_role(monkeypatch, USER_ID, holds="event_coordinator", acts_as="event_organiser")
        r = client.post(f"{BASE}/{inbox['rows'][0]['id']}/read", headers=auth_headers)
        assert r.status_code == 404 and inbox["rows"][0]["read_at"] is None


class TestList:
    def test_newest_first_with_link_read_flag_and_no_internal_fields(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=USER_ID)
        inbox["rows"] = [row(1, created="2026-10-20T01:00:00+00:00"), row(2, read_at="x", created="2026-10-20T02:00:00+00:00")]
        items = client.get(BASE, headers=auth_headers).json()["items"]
        assert [i["message"] for i in items] == ["m2", "m1"]
        assert items[0]["read"] is True and items[1]["read"] is False
        assert items[0]["link"] == f"/coordinator/events/{EVENT_ID}"
        assert set(items[0]) == {"id", "event_id", "type", "message", "link", "read", "created_at"}

    def test_rows_sharing_a_timestamp_page_without_skips_or_repeats(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=USER_ID)
        inbox["rows"] = [row(i) for i in range(1, 6)]            # same created_at
        seen, cursor = [], None
        while True:
            url = f"{BASE}?limit=2" + (f"&before={cursor}" if cursor else "")
            page = client.get(url, headers=auth_headers).json()
            seen += [i["message"] for i in page["items"]]
            cursor = page["next_before"]
            if not cursor:
                break
        assert sorted(seen) == ["m1", "m2", "m3", "m4", "m5"] and len(seen) == 5

    @pytest.mark.parametrize("query", ["limit=0", "limit=101", "before=garbage"])
    def test_bad_query_is_422(self, client, auth_headers, authenticate_as, inbox, query):
        authenticate_as("event_coordinator", user_id=USER_ID)
        assert client.get(f"{BASE}?{query}", headers=auth_headers).status_code == 422

    def test_no_event_id_means_no_link(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=USER_ID)
        inbox["rows"] = [{**row(1), "event_id": None}]
        assert client.get(BASE, headers=auth_headers).json()["items"][0]["link"] is None


class TestMarkRead:
    def test_marks_one_and_is_idempotent(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=USER_ID)
        inbox["rows"] = [row(1)]
        url = f"{BASE}/{inbox['rows'][0]['id']}/read"
        assert client.post(url, headers=auth_headers).json() == {"id": inbox["rows"][0]["id"], "read": True}
        first = inbox["rows"][0]["read_at"]
        assert client.post(url, headers=auth_headers).status_code == 200
        assert inbox["rows"][0]["read_at"] == first

    def test_someone_elses_id_is_404(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=OTHER_ID)
        inbox["rows"] = [row(1)]                                  # belongs to USER_ID
        assert client.post(f"{BASE}/{inbox['rows'][0]['id']}/read", headers=auth_headers).status_code == 404

    def test_read_all_touches_only_the_callers_rows_in_the_active_role(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=USER_ID)
        inbox["rows"] = [row(1), row(2), row(3, role="event_organiser")]
        assert client.post(f"{BASE}/read-all", headers=auth_headers).json() == {"updated": 2}
        assert inbox["rows"][2]["read_at"] is None
```

- [ ] **Step 2: Run and confirm failure.** `cd backend && pytest tests/test_notifications_api.py -v`. Expected: `ModuleNotFoundError: No module named 'app.modules.notifications'` (the right reason; not a typo in the tests).

- [ ] **Step 3: Write the repository tests** `backend/tests/test_notifications_repository.py`, following `test_events_repository.py`: patch `get_supabase_admin_client` with a recording query mock and assert that every call filters by `recipient_id` **and** `recipient_role`, that `count_unread` filters `read_at is null`, that `list_page` orders `created_at desc, id desc` and applies the keyset with `or_`/`lt` on `(created_at, id)`, that `mark_read` updates only unread rows (keeps the original `read_at`) and returns False when nothing matched, and that `mark_all_read` returns the number updated. Run; expected fail: functions not defined.

- [ ] **Step 4: Implement the module** to the Interfaces block (router uses `get_current_user`; no `require_roles`, since every role has a bell; the role passed to the repository is `current_user.role`, the active role). Keep `service.py` free of Supabase calls. Register the router in `main.py`.

- [ ] **Step 5: Run the new tests, then the full suite.** `cd backend && pytest tests/test_notifications_api.py tests/test_notifications_repository.py -v` then `pytest`. Expected: all pass; coverage of `app/modules/notifications/` is 100% (`pytest --cov=app/modules/notifications`).

- [ ] **Step 6: Real-system check.** Start the backend on a spare port (`uvicorn app.main:app --port 8010`), sign in as the seeded coordinator, create rows with `add_notification` through `execute_sql`, and call the four endpoints with real HTTP. Then switch the session's active role (`POST /auth/active-role`) and confirm the list changes. Record the commands and results for the run log.

- [ ] **Step 7: Commit** (`feat(notifications): read API for the bell, filtered by active role (SCRUM-113)`).

**Acceptance:** 113 AC1 (count), AC2 (list, order, links), AC3 (mark read, mark all), AC4 (own rows only, active role, including a raw request) are covered by named tests.

---

### Task 3: Bell, store and polling (113 AC1 to AC3, 53 AC7)

**Files:**
- Create: `frontend/src/features/notifications/notificationsStore.js`, `polling.js`, `format.js`
- Create: `frontend/src/components/common/NotificationBell.vue`
- Modify: `frontend/src/services/api.js` (add `notificationsApi`), `frontend/src/components/common/TopBar.vue` (replace the empty panel block with `<NotificationBell />`)
- Test: `frontend/src/features/notifications/__tests__/notificationsStore.spec.js`, `polling.spec.js`, `format.spec.js`, `frontend/src/components/common/__tests__/NotificationBell.spec.js`

**Interfaces:**
- Consumes: Task 2's endpoints; `useAuthStore().withSession(call)`, `useAuthStore().role`.
- Produces:
  - `notificationsApi.unreadCount(token)`, `.list({ limit, before }, token)`, `.markRead(id, token)`, `.markAllRead(token)`.
  - `POLL_INTERVAL_MS = 10_000` exported from `polling.js`; `createPoller({ tick, intervalMs = POLL_INTERVAL_MS, isVisible = () => document.visibilityState === "visible" }) -> { start(), stop() }`. Behaviour: runs `tick` every interval only while visible; skips a tick while the previous `tick` promise is pending; runs `tick` immediately when the document becomes visible; `stop()` clears the timer and the listener.
  - `useNotificationsStore` (Pinia `notifications`): state `{ count, latestAt, items, nextBefore, isOpen, isLoading, error }`; actions `poll()` (fetch the count; reload the list only when `latestAt` or `count` changed, or the panel is open), `open()`, `close()`, `loadMore()`, `markRead(id)`, `markAllRead()`, `reset()`, `start()`, `stop()`.
  - `formatNotificationTime(iso: string, now = new Date()) -> string` (for example `just now`, `5 min ago`, `3 h ago`, `20 Oct`).
  - `NotificationBell.vue`: no props; button `aria-label="Notifications"`, unread badge (`99+` above 99), panel listing items with the message, time label and a link (`RouterLink`) when `link` is set; unread items visually distinct and `aria-label` says "unread"; **Mark all as read**; empty state "No notifications"; closes on route change and on click-away; works at phone width.

- [ ] **Step 1: Write failing tests.** Sketches that define done:

```js
// polling.spec.js
it("skips a tick while the previous one is still running", async () => {
  vi.useFakeTimers();
  let release; const tick = vi.fn(() => new Promise((r) => { release = r; }));
  const p = createPoller({ tick, isVisible: () => true }); p.start();
  await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
  expect(tick).toHaveBeenCalledTimes(1);
  release(); await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
  expect(tick).toHaveBeenCalledTimes(2);
});
it("does not tick while hidden and ticks at once when visible again", ...);
it("stop() clears the timer and the visibility listener", ...);

// notificationsStore.spec.js  (vi.mock("@/services/api") as in eventCommentsStore.spec.js)
it("poll() reloads the list only when the count or latestAt changed", ...);
it("opening the panel loads the list and marks nothing read", ...);
it("markRead updates the item and decrements the count without waiting for a poll", ...);
it("markAllRead zeroes the count and marks every loaded item read", ...);
it("RESET ON ROLE SWITCH: changing authStore.role clears items and count and polls the new role at once", ...); // Review Focus 1
it("a poll that fails (503) skips the tick silently and keeps the last good count", ...);
it("a 401 from a poll ends the session via withSession like every other call", ...);
it("stale response guard: a slow list for the previous role never lands after a role switch", ...);

// NotificationBell.spec.js
it("shows the unread count and caps it at 99+", ...);
it("lists newest first with a link and marks unread rows", ...);
it("clicking an item marks it read and navigates to its link", ...);
it("shows the empty state", ...);
it("closes on route change and on click-away", ...);
```
Each `...` is written out by the implementer in full before any implementation; each asserts the behaviour in its title.

- [ ] **Step 2: Run and confirm failure.** `cd frontend && npx vitest run src/features/notifications src/components/common/__tests__/NotificationBell.spec.js`. Expected: failing on missing modules, not on syntax errors.
- [ ] **Step 3: Implement** the API client, poller, formatter, store and component to the Interfaces block; swap the placeholder panel in `TopBar.vue`; start polling when a session exists (watch `authStore.token`), stop on logout, and `reset()` on `authStore.role` change.
- [ ] **Step 4: Run** `npx vitest run` (full), `npm run test:coverage` (new files 100%), `npm run lint` if configured. Expected: pass.
- [ ] **Step 5: Real-browser check** (dev server on a spare port with the backend from Task 2): sign in as the coordinator, create a row with `add_notification`, and confirm the badge changes within 10 seconds with the page open; hide the tab and confirm no requests in the network panel; switch role and confirm the bell changes; check the console is clean.
- [ ] **Step 6: Commit** (`feat(notifications): notification bell with 10-second polling (SCRUM-113)`).

**Acceptance:** 113 AC1 to AC3 and ADR-0004's polling rules by test; the browser pass is the developer's (layout at phone width, wording, no flash when the count changes).

---

### Task 4: Attendee notifications (53 AC1 to AC3, AC5 to AC7)

**Depends on:** Dev 1's registrations table. Agree its name and status values with Dev 1 on day 1. This plan assumes `public.registrations(event_id uuid, attendee_id uuid, status text)` with `status = 'registered'` for registered attendees; if Dev 1 names it differently, change only the `from` clause.

**Files:**
- Create: `supabase/migrations/20261021110000_notify_registered_attendees.sql`
- Modify: `supabase/verification/notification_role_checks.sql` (append checks)
- Register attendee types in `notification_types` (same migration): `attendee_event_changed` → `{attendee}`, `attendee_event_cancelled` → `{attendee}`, `attendee_registration_changed` → `{attendee}`, `attendee_event_reminder` → `{attendee}`.

**Interfaces:**
- Produces: `public.notify_registered_attendees(p_event uuid, p_type text, p_message text, p_actor uuid default null, p_dedupe_key text default null) returns integer` (the number of rows inserted): one `add_notification` per attendee whose registration for `p_event` is `registered`; never the actor (NT-R1); waitlisted and withdrawn attendees get none. `service_role` only.
- Produces (contract for other developers): Dev 2 calls it from the approve-change (37) and cancel (115) functions with `attendee_event_changed` / `attendee_event_cancelled`; Dev 3 calls it for a confirmed replacement venue (53 AC6); Dev 1 raises `attendee_registration_changed` (53 AC5) with `add_notification` from the registration functions.
- Message rule (53 AC2, AC3): names the event, says what changed, and for a multi-venue event names only the primary venue (QA3-26). Written by the caller; the helper does not build text.

- [ ] **Step 1: Write failing checks** appended to `notification_role_checks.sql`:

```sql
-- three attendees on a throwaway event: registered, waitlisted, withdrawn
-- expect exactly one row, addressed to the registered attendee, role 'attendee'
if public.notify_registered_attendees(v_event, 'attendee_event_changed', 'Date moved', v_coordinator) <> 1 then
    raise exception 'ATTENDEE FAIL: only the registered attendee should be notified';
end if;
-- the actor who is also registered gets nothing (NT-R1)
-- an unknown event id returns 0 and inserts nothing
```
- [ ] **Step 2: Run** and confirm failure (`function public.notify_registered_attendees … does not exist`).
- [ ] **Step 3: Write the migration** to the Interfaces block.
- [ ] **Step 4: Apply (developer pushes), re-run, expect pass**; run `get_advisors`.
- [ ] **Step 5: Hand-off note** in the PR body listing the three callers above, so Dev 1 to 3 add their calls in their own branches. This task does not edit their functions.
- [ ] **Step 6: Commit** (`feat(notifications): notify an event's registered attendees (SCRUM-53)`).

**Acceptance:** 53 AC1, AC3, AC5, AC6 hold at the database level for any caller that uses the helper; the callers' own tests prove the wiring.

---

### Task 5: Reminders (53 AC4, 90 AC1 to AC3)

**Files:**
- Create: `supabase/migrations/20261021120000_notification_reminders.sql`, `supabase/verification/notification_reminder_checks.sql`

**Interfaces:**
- Register types: `staff_arrangement_reminder` → `{event_coordinator, venue_staff, tech_support, safety_officer}` (the recipient's role is stamped from what they hold; a person who holds two of these gets the first listed, limitation 6).
- Produces: `public.send_attendee_event_reminders() returns integer` and `public.send_staff_arrangement_reminders() returns integer`, both `security definer`, `service_role` only, both returning the number of rows inserted.
- `send_attendee_event_reminders`: for every event that starts within the next 24 hours and is not cancelled, one `attendee_event_reminder` per `registered` attendee, message with the event's name, date, start time and venue (primary venue only for multi-venue events), `dedupe_key = 'reminder-24h:' || event_id`. No row for waitlisted or withdrawn attendees or for cancelled events.
- `send_staff_arrangement_reminders` **[Assumption, confirm in planning poker]**: for every event starting within 3 days (status `planning`, `safety_review`, `confirmed`) that still has an incomplete arrangement (a venue booking not `approved`, an equipment line not `reserved`, or the safety check not done), notify the assigned coordinator (90 AC1) and the venue staff or technical support who have a pending request on it (90 AC2). At most one per recipient, event and day: `dedupe_key = 'staff-reminder:' || event_id || ':' || current_date`. Reuse the readiness logic that already exists for "send for safety check" rather than re-deriving it (find it with `grep -n "not ready\|Not ready for safety check" supabase/migrations backend/app/modules/events/readiness.py`).
- Cron: `select cron.schedule('attendee-event-reminders', '*/15 * * * *', 'select public.send_attendee_event_reminders()')` and `select cron.schedule('staff-arrangement-reminders', '0 1 * * *', 'select public.send_staff_arrangement_reminders()')` (01:00 UTC is 09:00 Singapore time). `cron.schedule` replaces a job of the same name, so the migration can be re-run.

- [ ] **Step 1: Write failing checks** `notification_reminder_checks.sql` (rolled back, throwaway events, seeded accounts):
  - Attendee reminder: an event starting in 23 hours with one registered, one waitlisted, one withdrawn attendee → function returns 1; run it again → returns 0 (idempotent); an event starting in 25 hours → 0; a cancelled event starting in 20 hours → 0.
  - Staff reminder: a planning event starting in 2 days with a `held` booking → the coordinator and the venue staff are notified once; run again the same day → 0; make the booking `approved` and the equipment `reserved` and the safety check done → 0; an event 5 days away → 0.
  - Messages contain no staff notes, block reasons or private safety notes (NT-R2): assert the text of each reminder equals the template.
- [ ] **Step 2: Run and confirm failure** (functions do not exist).
- [ ] **Step 3: Write the migration** to the Interfaces block.
- [ ] **Step 4: Apply (developer pushes), re-run, expect `NOTIFICATION REMINDER CHECKS PASSED`**; confirm the jobs exist (`select jobname, schedule from cron.job`); run `get_advisors`.
- [ ] **Step 5: Commit** (`feat(notifications): scheduled reminders for attendees and staff (SCRUM-53, SCRUM-90)`).

**Acceptance:** 53 AC4 and 90 AC1, AC2 hold; AC3's timing is the stated assumption, recorded in `docs/REQUIREMENTS.md` §9.

---

### Task 6: Verification and paper trail

**Files:** `backend/scripts/verify_live.py`, `frontend/e2e/notifications.e2e.js`, `docs/test-cases/notifications.md`, `docs/test-cases/runs/…`, `docs/IMPLEMENTATION_MAP.md`, `docs/BUILD_LOG.md`, `docs/REQUIREMENTS.md`, `docs/DEFECTS.md` (only if a defect is found), `docs/adr/0004-notification-delivery.md`.

- [ ] **Step 1: Automate what can be automated** (case ID first in each check name): in `verify_live.py`, the four endpoints as the seeded coordinator and organiser, including the active-role denial after `POST /auth/active-role`, and mark-read of another user's id → 404; in `frontend/e2e/`, the badge updating within 10 seconds after a row is created, and no polling while the tab is hidden. Never change seeded data; checks that create rows delete them.
- [ ] **Step 2: Run the full suites:** `cd backend && pytest --cov`; `cd frontend && npm run test:coverage`; then `python scripts/verify_live.py --record` from `backend/` and `npm run test:e2e:record` from `frontend/` against servers running this branch (spare ports, `--api` / `E2E_BASE_URL` / `E2E_API_URL` if yours are busy). A failure is a finding to fix or report, never something to re-run until it passes.
- [ ] **Step 3: Ask the developer to do the manual pass** (do not mark these passed yourself): the bell at phone width and desktop; the badge change not flashing or jumping the layout; wording of each seeded notification; the panel closing on navigation; keyboard and screen-reader label; an attendee seeing the bell on their dashboard. Record their result as a manual run file (template in `docs/test-cases/runs/README.md`).
- [ ] **Step 4: Paper trail.** `docs/IMPLEMENTATION_MAP.md`: new module, endpoints, tables/columns/functions, the registry and the rule "register your type in `notification_types`"; replace the TopBar line that says there is no notifications backend. `docs/BUILD_LOG.md` §4: one entry per story. `docs/test-cases/notifications.md`: cases traced to 113, 53 and 90 ACs with Type, Created and Last run. `docs/REQUIREMENTS.md`: §6.20 now in-app only for release 1, the 90 AC3 assumption in §9. ADR-0004: set Status to Accepted once the team agrees (ask first).
- [ ] **Step 5: Check against `docs/DEFINITION_OF_DONE.md`.** In the final report name the items only the developer can do: the manual browser pass, the PR and teammate review, the PO's acceptance, the merge, ticking the AC rows in the **AC ticks** tab, and the status changes (ask before changing any; see the project CLAUDE.md).
- [ ] **Step 6: Commit** the docs and run logs with the story.

---

## Self-review

- **Spec coverage:** §1 active role → Task 1 and Task 2 denial tests; §2 helper → Tasks 1 and 4; §3 read API → Task 2; §4 bell → Task 3; §5 reminders → Task 5; §6 who writes which triggers → Task 4 hand-off note; testing → each task plus Task 6; out of scope respected (no email, outbox, Realtime).
- **Gaps carried, not hidden:** the registry's full type list is built by the implementer from the three sources in Task 1 (the live data plus the Python `notify_type` values cannot be listed statically); Task 4's table name depends on Dev 1; Task 5's staff-reminder timing is an assumption for planning poker.
- **Type consistency:** `recipient_role`, `notification_types.recipient_roles`, `add_notification`, `notify_registered_attendees`, `count_unread`, `list_page`, `mark_read`, `mark_all_read`, `link_for`, `encode_cursor`/`decode_cursor`, `POLL_INTERVAL_MS`, `createPoller`, `useNotificationsStore` are spelled the same in every task that uses them.
