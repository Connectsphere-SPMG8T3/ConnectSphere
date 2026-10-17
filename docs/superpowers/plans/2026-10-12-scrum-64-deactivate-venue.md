# SCRUM-64 Deactivate a venue — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Venue staff can deactivate a venue with a reason and reactivate it. Deactivation flags the venue's future held and approved bookings Affected, through a booking flag that CR-95 and CR-94 reuse and that the safety readiness and approval checks honour.

**Architecture:** One migration adds the reason and flag columns, a shared `flag_venue_bookings` function and two venue RPCs, and tightens `request_venue_booking` and `safety_approve_event`. The venues module gets deactivate/reactivate endpoints with the SCRUM-63 preview-then-confirm pattern. After commit, the service calls `events.service.return_to_planning` for flagged events. The venue page gets a modal, a banner and a reactivate confirm.

**Tech Stack:** Supabase Postgres (plpgsql), FastAPI 0.115 / Pydantic 2.11, pytest 8.3, Vue 3 + Pinia + Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-12-scrum-64-deactivate-venue-design.md`

## Global Constraints

- Branch `feature/scrum-64-deactivate-venue`. Never commit to `main`. Stage files by name. Never stage the untracked CR-98 migrations (`20261008100000_*`, `20261009100000_*`) or `docs/proposals/`.
- Commit messages: `feat(venues): …` / `test(…)` / `docs(…)`, with a *why* body and `SCRUM-64`. No attribution lines.
- Endpoints authorise by **active role** through `VenueStaffOnly` (`require_roles(["venue_staff"])`). The frontend gates on `authStore.role === "venue_staff"`.
- New database functions: `security definer`, `set search_path = ''`, execute revoked from `public, anon, authenticated`, granted to `service_role`.
- Reason enum values exactly: `permanently_closed`, `long_term_renovation`, `other`. Labels: "Permanently closed", "Long-term renovation", "Other".
- Flag enum values exactly: `affected`, `conflict`, `unsuitable`. Notification type exactly `venue_booking_affected`. `return_to_planning` reason code exactly `arrangement_flagged`.
- `inactive_note` max 500 characters. Required and non-blank when the reason is `other`.
- Endpoints that call Supabase are plain `def`. Errors are typed exceptions in `app/core/exceptions.py`.
- Coverage: 100% of new and changed lines in `backend/app/` and `frontend/src/` (`docs/CI.md` §4 item 2).
- Migration push to the live project is the **developer's** step (`supabase db push`). The agent runs `--dry-run` and asks for it.

## Review Focus

1. **Double submit on "Deactivate anyway"**: the second request finds the venue already inactive. Expect 409 "This venue is already inactive." and the modal shows it, with no crash and no second set of notifications. Pinned in Task 2 (API test) and Task 7 (button disabled while busy).
2. **A booking that ended before now, or one already flagged by another story**: it must not be flagged or notified again. Pinned in Task 1 (DB check).
3. **`return_to_planning` is unavailable after the venue was deactivated**: the user must not see a failed save for a change that committed. Expect `saved: true`, a logged warning, and the event left in place (approval still refuses the flagged booking). Pinned in Task 2.
4. **A whitespace-only note with reason Other** → 422, and the modal's confirm stays disabled. Pinned in Task 2 and Task 7.
5. **A reactivated venue appears in search again**, and the venue page reflects deactivation and reactivation without a manual reload. Pinned in Task 3 (search test) and Task 7 (refetch after save).

---

### Task 1: Migration and database verification

**Files:**
- Create: `supabase/migrations/20261012100000_venue_deactivation_and_booking_flag.sql`
- Create: `supabase/verification/venue_deactivation_checks.sql`

**Interfaces:**
- Produces (SQL, used by Tasks 2–5 and by CR-95/CR-94):
  - `public.venue_inactive_reason` enum; `venues.inactive_reason`, `venues.inactive_note varchar(500)`
  - `public.venue_booking_flag` enum; `venue_bookings.flag`, `flag_reason text`, `flagged_at timestamptz`
  - `public.flag_venue_bookings(p_venue_id uuid, p_period tstzrange, p_flag public.venue_booking_flag, p_reason text, p_message text) returns setof uuid` (distinct event ids flagged)
  - `public.deactivate_venue(p_venue_id uuid, p_actor_id uuid, p_expected_version integer, p_reason public.venue_inactive_reason, p_note text, p_before jsonb, p_after jsonb, p_flag_reason text, p_message text) returns table (outcome text, event_ids uuid[])`. `outcome` is one of `ok`, `venue_not_found`, `already_inactive`, `stale`.
  - `public.reactivate_venue(p_venue_id uuid, p_actor_id uuid, p_expected_version integer, p_before jsonb, p_after jsonb) returns text`. Returns `ok`, `venue_not_found`, `already_active` or `stale`.
  - `public.request_venue_booking` gains the outcome `venue_inactive`.
  - `public.safety_approve_event` returns no row when any active booking has `flag is not null`.

**Requirements:**
- Check constraint `venues_inactive_reason_consistent`:
  - `is_active` ⇒ `inactive_reason is null and inactive_note is null`
  - `not is_active` ⇒ `inactive_reason is not null`
  - `inactive_reason = 'other'` ⇒ `length(btrim(inactive_note)) > 0`
- Before adding the constraint, backfill existing inactive rows: `update venues set inactive_reason='other', inactive_note='Deactivated before reasons were recorded' where not is_active and inactive_reason is null`.
- Check constraint `venue_bookings_flag_consistent`: `flag`, `flag_reason` and `flagged_at` are all null or all non-null, and `length(btrim(flag_reason)) > 0` when set.
- `flag_venue_bookings` flags rows where:
  - `venue_id = p_venue_id`
  - `status in ('held','approved')`
  - `occupied_period && p_period`
  - `upper(occupied_period) > now()`
  - `flag is null`

  It sets `flag`, `flag_reason = btrim(p_reason)` and `flagged_at = now()`. Then it inserts one `notifications` row per distinct flagged event, with `recipient_id = events.coordinator_id` (skipped when null), `type = 'venue_booking_affected'` and `message = p_message`. It returns the distinct event ids.
- `deactivate_venue`:
  - `select … for update` the venue. Missing → `venue_not_found`. `not is_active` → `already_inactive`. `version <> p_expected_version` → `stale`.
  - Otherwise it sets `is_active=false`, the reason, `inactive_note = nullif(btrim(p_note),'')`, `updated_by = p_actor_id` and `version = version + 1`.
  - It inserts `venue_edit_history(venue_id, actor_id, before, after)`.
  - It calls `flag_venue_bookings(p_venue_id, tstzrange(now(), null), 'affected', p_flag_reason, p_message)` and returns `('ok', array_agg(ids))`. Use an empty array, not null, when nothing is flagged.
- `reactivate_venue`: the same lock and outcomes (`already_active` when `is_active`). It sets `is_active=true`, clears the reason and note, stamps `updated_by`, bumps `version` and writes the history row. **Flags untouched.**
- `request_venue_booking`: `create or replace` the function from `20261005120000_venue_booking_requests.sql` (copy its current live body; check it with `supabase db query --linked "select pg_get_functiondef('public.request_venue_booking'::regproc)"` first). Add `if not v_venue.is_active then return query select 'venue_inactive'::text, null::uuid; end if;` right after the `venue_not_found` check.
- `safety_approve_event`: `create or replace` the function from `20261009110000_safety_review_decision.sql`, unchanged apart from extending the refusal condition with `or exists (select 1 from public.venue_bookings where event_id=p_event_id and status in ('held','approved','re_review') and flag is not null)`. Re-issue its revoke/grant lines.
- Comments on the new columns and functions name SCRUM-64 and the CR-95/CR-94 contract.

- [ ] **Step 1: Check the live state the migration depends on**

Run from the repo root:
```bash
env PATH=/home/linuxbrew/.linuxbrew/bin:/usr/bin:/bin supabase db query --linked "select count(*) filter (where not is_active) as inactive, count(*) as total from public.venues"
```
Also fetch the live definitions of `request_venue_booking` and `safety_approve_event` with `pg_get_functiondef`, and diff them against the migration files. The migration must be built from the live body.

- [ ] **Step 2: Write the verification script first** (`supabase/verification/venue_deactivation_checks.sql`)

Follow `venue_edit_checks.sql`: `begin; … rollback;`, raise on the first failure, print `VENUE DEACTIVATION CHECKS PASSED`. Use the seeded coordinator (`a0000000-…0002`), venue staff (`…0003`) and Seminar Room 1 (`b0000000-…0003`). Insert throwaway events dated 2031 and their bookings inside the transaction. Cases:
1. Deactivate with one future `held` and one future `approved` booking on two events: both flagged `affected`, `flag_reason` set, two `venue_booking_affected` notifications to the coordinator, `outcome='ok'`, both event ids returned, venue inactive with its reason, one history row, version bumped.
2. Not flagged: a booking that ended in the past, a `re_review` booking, a `released` booking, and a booking already flagged `conflict` (its flag and reason unchanged, no notification).
3. A second deactivate → `already_inactive`. A stale version → `stale`. An unknown id → `venue_not_found`.
4. Reactivate → `ok`, reason and note null, flags on case 1's bookings unchanged. A second reactivate → `already_active`.
5. Constraints: an inactive venue with no reason fails; reason `other` with a note of `'  '` fails; an active venue with a reason fails; a booking with `flag` but no `flag_reason` fails.
6. `request_venue_booking` on the inactive venue → `venue_inactive`.
7. `safety_approve_event` on an event in `safety_review` whose only booking is `approved` but flagged returns no row and the event stays in `safety_review`.
8. As `anon` and `authenticated` (`set local role …`): executing `flag_venue_bookings`, `deactivate_venue` and `reactivate_venue` raises `insufficient_privilege`.

- [ ] **Step 3: Confirm the script fails before the migration**

```bash
env PATH=/home/linuxbrew/.linuxbrew/bin:/usr/bin:/bin supabase db query --linked -f supabase/verification/venue_deactivation_checks.sql
```
Expected: an error that `venue_inactive_reason` / `deactivate_venue` does not exist.

- [ ] **Step 4: Write the migration** per the requirements above.

- [ ] **Step 5: Dry run and hand off the push**

```bash
env PATH=/home/linuxbrew/.linuxbrew/bin:/usr/bin:/bin supabase db push --dry-run
```
Expected: only `20261012100000_venue_deactivation_and_booking_flag.sql` is listed. **Stop and ask the developer to run `supabase db push`.** Then confirm with `supabase migration list --linked`.

- [ ] **Step 6: Run the verification script live.** Expected: `VENUE DEACTIVATION CHECKS PASSED`. Then run the advisors (Supabase MCP `get_advisors`, security and performance) and check that no finding names the new objects. Re-run `send_for_safety_check.sql` and `safety_decision_checks.sql` (or their current names in `supabase/verification/`) to show that approval and booking requests still pass.

- [ ] **Step 7: Commit**

```bash
git add supabase/migrations/20261012100000_venue_deactivation_and_booking_flag.sql supabase/verification/venue_deactivation_checks.sql
git commit -m "feat(venues): venue deactivation reasons and the shared booking flag"
```

---

### Task 2: Deactivate endpoint

**Files:**
- Modify: `backend/app/modules/venues/schemas.py` (new enums and models; `VenueSummary` fields)
- Modify: `backend/app/modules/venues/repository.py` (`_VENUE_COLUMNS`, `_to_venue`, `list_flaggable_bookings`, `deactivate_venue`)
- Modify: `backend/app/modules/venues/service.py` (`_snapshot`, `deactivate_venue`)
- Modify: `backend/app/modules/venues/router.py` (route)
- Modify: `backend/app/core/exceptions.py` (`VenueAlreadyInactiveError`)
- Test: `backend/tests/test_venue_deactivation_api.py` (new)

**Interfaces:**
- Consumes: the `deactivate_venue` RPC (Task 1); `events_service.return_to_planning(event_id, *, reason_code="arrangement_flagged")` returning `EventResponse | None`, which raises `EventServiceUnavailableError`.
- Produces:
  - `class VenueInactiveReason(str, Enum)`: `permanently_closed`, `long_term_renovation`, `other`; `INACTIVE_REASON_LABELS: dict[VenueInactiveReason, str]`
  - `VenueSummary.inactive_reason: VenueInactiveReason | None = None`, `VenueSummary.inactive_note: str | None = None`
  - `class VenueDeactivateRequest(BaseModel)`: `reason: VenueInactiveReason`, `note: str | None = Field(None, max_length=500)`, `version: int`, `confirm: bool = False`. A model validator strips `note` and rejects `other` with an empty note (422).
  - `class FlaggableBooking(BaseModel)`: `booking_id: str, event_id: str, event_name: str | None, period: Period, status: Literal["held","approved"]`
  - `class VenueDeactivateResponse(BaseModel)`: `saved: bool, venue: VenueDetail | None = None, affected: list[FlaggableBooking] = []`
  - `repository.list_flaggable_bookings(venue_id: str, now: datetime) -> list[BookingSummary]`: held/approved, `occupied_period` overlapping `[now,)`, `flag is null`
  - `repository.deactivate_venue(venue_id, actor_id, expected_version, *, reason, note, before, after, flag_reason, message) -> dict` returns `{"outcome": str, "event_ids": list[str]}`
  - `service.deactivate_venue(venue_id: str, actor_id: str, body: VenueDeactivateRequest) -> VenueDeactivateResponse`
  - Route `POST /api/v1/venues/{venue_id}/deactivate` → `VenueDeactivateResponse`, 200
  - `_snapshot` adds `"is_active"`, `"inactive_reason"` (value or None) and `"inactive_note"`
  - `VenueAlreadyInactiveError` (409, detail "This venue is already inactive.")
- Wording:
  - flag reason: `f"Venue deactivated: {INACTIVE_REASON_LABELS[reason].lower()}"`, plus `f" — {note}"` when there is a note
  - notification: `f'Venue "{venue.name}" has been deactivated ({label}). Your booking is flagged Affected and needs a replacement venue.'`

**Behaviour:**
1. `get_venue` → None ⇒ `VenueNotFoundError`. `not current.is_active` ⇒ `VenueAlreadyInactiveError`.
2. `body.version != current.version` ⇒ `VenueConflictError` (409).
3. `affected = list_flaggable_bookings(venue_id, now)`, with event names from `events_service.names_by_id` (as `get_venue` does). If `affected` and not `body.confirm` ⇒ `VenueDeactivateResponse(saved=False, affected=…)`, with no RPC call.
4. Call the RPC. Outcome `stale` ⇒ `VenueConflictError`; `already_inactive` ⇒ `VenueAlreadyInactiveError`; `venue_not_found` ⇒ `VenueNotFoundError`.
5. For each returned event id, call `return_to_planning(event_id, reason_code="arrangement_flagged")`. Catch `EventServiceUnavailableError` per event, `logger.warning(...)` and continue (Review Focus 3).
6. Return `saved=True`, the `venue` re-read through `get_venue(venue_id)`, and `affected`.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_venue_deactivation_api.py`)

```python
"""SCRUM-64: deactivate a venue (AC1, AC3) — role gate, preview/confirm, outcomes."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import EventServiceUnavailableError
from app.modules.events import repository as events_repository
from app.modules.events import service as events_service
from app.modules.venues import repository
from app.modules.venues.schemas import BookingSummary, Period
from tests.test_venues_api import HALL_A_ID, make_venue_profile

URL = f"/api/v1/venues/{HALL_A_ID}/deactivate"
EVENT_ID = "e0000000-0000-4000-8000-000000000301"
BODY = {"reason": "permanently_closed", "note": None, "version": 3}


def _booking(status="approved"):
    start = datetime(2031, 5, 20, 6, tzinfo=timezone.utc)
    return BookingSummary(id="d0000000-0000-4000-8000-000000000301", event_id=EVENT_ID,
                          period=Period(starts_at=start, ends_at=start + timedelta(hours=3)), status=status)


@pytest.fixture()
def venue(monkeypatch):
    state = {"current": make_venue_profile(HALL_A_ID, "Hall A", version=3), "flaggable": [], "rpc": [],
             "outcome": {"outcome": "ok", "event_ids": []}, "returned": []}
    monkeypatch.setattr(repository, "get_venue", lambda vid: state["current"] if vid == HALL_A_ID else None)
    monkeypatch.setattr(repository, "list_upcoming_blocks", lambda vid, since: [])
    monkeypatch.setattr(repository, "list_upcoming_bookings", lambda vid, since: [])
    monkeypatch.setattr(repository, "list_flaggable_bookings", lambda vid, now: state["flaggable"])
    monkeypatch.setattr(events_repository, "list_event_names", lambda ids: {EVENT_ID: "Gala"})

    def _rpc(venue_id, actor_id, expected_version, **kwargs):
        state["rpc"].append({"venue_id": venue_id, "actor_id": actor_id, "version": expected_version, **kwargs})
        return state["outcome"]

    monkeypatch.setattr(repository, "deactivate_venue", _rpc)
    monkeypatch.setattr(events_service, "return_to_planning",
                        lambda event_id, **kw: state["returned"].append((event_id, kw)))
    return state


class TestDeactivate:
    def test_no_bookings_saves_straight_away(self, client, auth_headers, authenticate_as, venue):
        actor = authenticate_as("venue_staff")
        response = client.post(URL, json=BODY, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["saved"] is True
        [call] = venue["rpc"]
        assert call["actor_id"] == actor["id"] and call["version"] == 3
        assert call["reason"] == "permanently_closed"
        assert call["before"]["is_active"] is True and call["after"]["is_active"] is False
        assert call["after"]["inactive_reason"] == "permanently_closed"
        assert call["flag_reason"] == "Venue deactivated: permanently closed"

    def test_bookings_without_confirm_preview_and_write_nothing(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        venue["flaggable"] = [_booking("held")]
        response = client.post(URL, json=BODY, headers=auth_headers)
        body = response.json()
        assert response.status_code == 200 and body["saved"] is False
        assert body["affected"][0]["event_name"] == "Gala" and body["affected"][0]["status"] == "held"
        assert venue["rpc"] == []

    def test_confirm_flags_and_returns_flagged_events_to_planning(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        venue["flaggable"] = [_booking()]
        venue["outcome"] = {"outcome": "ok", "event_ids": [EVENT_ID]}
        response = client.post(URL, json={**BODY, "confirm": True}, headers=auth_headers)
        assert response.json()["saved"] is True
        assert venue["returned"] == [(EVENT_ID, {"reason_code": "arrangement_flagged"})]

    def test_event_service_outage_after_commit_still_reports_saved(
        self, client, auth_headers, authenticate_as, venue, monkeypatch
    ):
        authenticate_as("venue_staff")
        venue["outcome"] = {"outcome": "ok", "event_ids": [EVENT_ID]}

        def _down(event_id, **kw):
            raise EventServiceUnavailableError()

        monkeypatch.setattr(events_service, "return_to_planning", _down)
        response = client.post(URL, json={**BODY, "confirm": True}, headers=auth_headers)
        assert response.status_code == 200 and response.json()["saved"] is True

    def test_other_requires_a_note(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        for note in (None, "   "):
            response = client.post(URL, json={**BODY, "reason": "other", "note": note}, headers=auth_headers)
            assert response.status_code == 422
        assert venue["rpc"] == []

    def test_note_over_500_chars_is_422(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        response = client.post(URL, json={**BODY, "note": "x" * 501}, headers=auth_headers)
        assert response.status_code == 422

    def test_other_with_note_includes_it_in_the_flag_reason(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        client.post(URL, json={**BODY, "reason": "other", "note": " Lease ended "}, headers=auth_headers)
        assert venue["rpc"][0]["note"] == "Lease ended"
        assert venue["rpc"][0]["flag_reason"] == "Venue deactivated: other — Lease ended"

    def test_already_inactive_is_409(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        venue["current"] = make_venue_profile(HALL_A_ID, "Hall A", version=3, is_active=False,
                                              inactive_reason="permanently_closed")
        response = client.post(URL, json=BODY, headers=auth_headers)
        assert response.status_code == 409 and response.json()["detail"] == "This venue is already inactive."

    @pytest.mark.parametrize("outcome", ["already_inactive", "stale", "venue_not_found"])
    def test_rpc_refusals_map_to_errors(self, client, auth_headers, authenticate_as, venue, outcome):
        authenticate_as("venue_staff")
        venue["outcome"] = {"outcome": outcome, "event_ids": []}
        response = client.post(URL, json=BODY, headers=auth_headers)
        assert response.status_code == (404 if outcome == "venue_not_found" else 409)
        assert venue["returned"] == []

    def test_stale_version_from_client_is_409_without_rpc(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        response = client.post(URL, json={**BODY, "version": 2}, headers=auth_headers)
        assert response.status_code == 409 and venue["rpc"] == []

    def test_unknown_venue_is_404(self, client, auth_headers, authenticate_as, venue):
        authenticate_as("venue_staff")
        response = client.post("/api/v1/venues/b0000000-0000-4000-8000-0000000000ff/deactivate",
                               json=BODY, headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "tech_support",
                                      "safety_officer", "event_coordinator_lead", "attendee"])
    def test_other_roles_are_forbidden(self, client, auth_headers, authenticate_as, venue, role):
        authenticate_as(role)
        assert client.post(URL, json=BODY, headers=auth_headers).status_code == 403
        assert venue["rpc"] == []
```

Also add a repository test in the same file. Patch `repository.get_supabase_admin_client` with `tests.conftest.make_table_mock` (or the RPC mock pattern used for `update_venue` elsewhere) and assert that `repository.deactivate_venue` sends `p_expected_version`, `p_reason`, `p_note`, `p_before`, `p_after`, `p_flag_reason`, `p_message` and maps the RPC row to `{"outcome", "event_ids"}`. Assert too that `list_flaggable_bookings` filters `status in (held, approved)`, `flag is null` and overlap with `[now,)`.

The active-role matrix (`tests/test_active_role_access.py`) picks up the new route automatically. No edit is needed, but it must pass.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_venue_deactivation_api.py -q`
Expected: FAIL. The route returns 404/405, and `list_flaggable_bookings` doesn't exist.

- [ ] **Step 3: Implement** the schemas, exception, repository functions, `_snapshot` fields, service and route, as specified under Interfaces and Behaviour. Sketch of the route:

```python
@router.post("/{venue_id}/deactivate", response_model=VenueDeactivateResponse, status_code=status.HTTP_200_OK)
def deactivate_venue(venue_id: UUID, body: VenueDeactivateRequest, current_user: VenueStaffOnly) -> VenueDeactivateResponse:
    """Mark a venue inactive with a reason (SCRUM-64 AC1, AC3). `saved: false` previews
    the bookings that would be flagged Affected; nothing is written until `confirm: true`."""
    return service.deactivate_venue(str(venue_id), current_user.id, body)
```

- [ ] **Step 4: Run the tests and confirm they pass**, along with `tests/test_venues_api.py` and `tests/test_active_role_access.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/venues/schemas.py backend/app/modules/venues/repository.py backend/app/modules/venues/service.py backend/app/modules/venues/router.py backend/app/core/exceptions.py backend/tests/test_venue_deactivation_api.py
git commit -m "feat(venues): deactivate a venue and flag its future bookings Affected"
```

---

### Task 3: Reactivate endpoint

**Files:**
- Modify: `backend/app/modules/venues/schemas.py`, `repository.py`, `service.py`, `router.py`, `backend/app/core/exceptions.py`
- Test: `backend/tests/test_venue_deactivation_api.py` (new class `TestReactivate`), `backend/tests/test_venue_search.py`

**Interfaces:**
- Consumes: the `reactivate_venue` RPC (Task 1); `_snapshot`, `VenueAlreadyInactiveError` pattern (Task 2).
- Produces:
  - `class VenueReactivateRequest(BaseModel)`: `version: int`
  - `repository.reactivate_venue(venue_id, actor_id, expected_version, *, before, after) -> str` (the outcome)
  - `service.reactivate_venue(venue_id: str, actor_id: str, body: VenueReactivateRequest) -> VenueDetail`
  - Route `POST /api/v1/venues/{venue_id}/reactivate` → `VenueDetail`, 200
  - `VenueAlreadyActiveError` (409, "This venue is already active.")

**Behaviour:** 404 unknown venue; 409 if already active, or if the client version ≠ current; outcomes from the RPC map as in Task 2. On `ok`, return the re-read `get_venue` detail (with upcoming blocks and bookings, as `get_venue` does). No call to the events module.

- [ ] **Step 1: Write the failing tests**

```python
class TestReactivate:
    URL = f"/api/v1/venues/{HALL_A_ID}/reactivate"

    @pytest.fixture()
    def inactive(self, monkeypatch, venue):
        venue["current"] = make_venue_profile(HALL_A_ID, "Hall A", version=4, is_active=False,
                                              inactive_reason="long_term_renovation", inactive_note="Roof works")
        venue["re_rpc"] = []

        def _rpc(venue_id, actor_id, expected_version, **kwargs):
            venue["re_rpc"].append({"version": expected_version, **kwargs})
            return venue.get("re_outcome", "ok")

        monkeypatch.setattr(repository, "reactivate_venue", _rpc)
        return venue

    def test_venue_staff_reactivates(self, client, auth_headers, authenticate_as, inactive):
        authenticate_as("venue_staff")
        response = client.post(self.URL, json={"version": 4}, headers=auth_headers)
        assert response.status_code == 200
        [call] = inactive["re_rpc"]
        assert call["before"]["inactive_reason"] == "long_term_renovation"
        assert call["after"] == {**call["before"], "is_active": True, "inactive_reason": None, "inactive_note": None}
        assert inactive["returned"] == []

    def test_already_active_is_409(self, client, auth_headers, authenticate_as, venue, monkeypatch):
        authenticate_as("venue_staff")
        monkeypatch.setattr(repository, "reactivate_venue", lambda *a, **k: pytest.fail("must not write"))
        response = client.post(self.URL, json={"version": 3}, headers=auth_headers)
        assert response.status_code == 409 and response.json()["detail"] == "This venue is already active."

    @pytest.mark.parametrize(("outcome", "code"), [("stale", 409), ("already_active", 409), ("venue_not_found", 404)])
    def test_rpc_refusals(self, client, auth_headers, authenticate_as, inactive, outcome, code):
        authenticate_as("venue_staff")
        inactive["re_outcome"] = outcome
        assert client.post(self.URL, json={"version": 4}, headers=auth_headers).status_code == code

    def test_stale_client_version_is_409(self, client, auth_headers, authenticate_as, inactive):
        authenticate_as("venue_staff")
        assert client.post(self.URL, json={"version": 3}, headers=auth_headers).status_code == 409
        assert inactive["re_rpc"] == []

    def test_coordinator_is_forbidden(self, client, auth_headers, authenticate_as, inactive):
        authenticate_as("event_coordinator")
        assert client.post(self.URL, json={"version": 4}, headers=auth_headers).status_code == 403
```

In `tests/test_venue_search.py`, add a pure-rule test (AC2/AC4): a venue with `is_active=False` is excluded with reason code `inactive`, and the same venue with `is_active=True` and the `inactive_*` fields cleared is included. Use that file's existing helper and `search(...)` call style.

- [ ] **Step 2: Run the tests and confirm they fail.** `pytest tests/test_venue_deactivation_api.py::TestReactivate -q` → 404/405.
- [ ] **Step 3: Implement** the schema, exception, repository, service and route.
- [ ] **Step 4: Run the tests and confirm they pass**, along with `tests/test_active_role_access.py`.
- [ ] **Step 5: Commit**: `feat(venues): reactivate an inactive venue`.

---

### Task 4: Booking requests refuse an inactive venue (AC2)

**Files:**
- Modify: `backend/app/modules/venues/service.py` (`BOOKING_REFUSALS`)
- Test: `backend/tests/test_venue_booking_request_api.py`

**Interfaces:** consumes the `venue_inactive` outcome (Task 1). Produces the refusal text `"This venue is inactive."` with a 409.

- [ ] **Step 1: Write the failing test.** Add one row to the existing refusal parametrisation in `tests/test_venue_booking_request_api.py` (around line 90, next to `("blocked", 409, "Venue blocked for this time.")`):

```python
            # SCRUM-64 AC2: an inactive venue takes no new requests.
            ("venue_inactive", 409, "This venue is inactive."),
```

- [ ] **Step 2: Run the test and confirm it fails.** Expected: 500 or an unmapped outcome.
- [ ] **Step 3: Implement.** Add `"venue_inactive": "This venue is inactive."` to `BOOKING_REFUSALS`.
- [ ] **Step 4: Run the test and confirm it passes.**
- [ ] **Step 5: Commit**: `feat(venues): refuse booking requests for an inactive venue`.

---

### Task 5: Booking flags reach the safety readiness check (82 AC10)

**Files:**
- Modify: `backend/app/modules/venues/repository.py` (`list_booking_statuses` also selects `flag`)
- Modify: `backend/app/modules/venues/service.py` (new `booking_readiness_by_event`)
- Modify: `backend/app/modules/events/service.py:193-195` (`_safety_readiness_for`)
- Test: `backend/tests/test_send_for_safety_check.py`, `backend/tests/test_coordinator_dashboard.py`; update the monkeypatches in `tests/test_safety_queue_and_review.py:27` and `tests/test_safety_decisions_api.py:22`

**Interfaces:**
- Produces: `venues.service.booking_readiness_by_event(event_ids: Iterable[str]) -> dict[str, list[BookingReadiness]]`, where each item is `BookingReadiness(status=row["status"], flags=[row["flag"]] if row.get("flag") else [])`.
- `booking_statuses_by_event` keeps its signature and output (the coordinator dashboard uses it).
- `_safety_readiness_for(row)` → `safety_readiness(venues_service.booking_readiness_by_event([row["id"]]).get(row["id"], []), technical_status(row))`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_send_for_safety_check.py`, whose `state` fixture patches `venues_repository.list_booking_statuses`. It goes through the real `booking_readiness_by_event`, so this also proves that the `flag` column flows end to end:
```python
def test_a_flagged_booking_blocks_sending(client, auth_headers, authenticate_as, state, monkeypatch):
    authenticate_as("event_coordinator", COORDINATOR_ID)
    monkeypatch.setattr(venues_repository, "list_booking_statuses",
                        lambda ids: [{"event_id": EVENT_ID, "status": "approved", "flag": "affected"}])
    response = client.post(URL, headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "Not ready for safety check: A venue booking is flagged Affected."
    assert not state["calls"]
```

In `tests/test_coordinator_dashboard.py`, next to the existing `booking_statuses_by_event` test at line ~252, add one test of `booking_readiness_by_event` that patches `repository.list_booking_statuses` to return `[{"event_id": "e-1", "status": "approved", "flag": "affected"}, {"event_id": "e-1", "status": "held", "flag": None}]` and asserts the two `BookingReadiness` objects. Also assert `booking_statuses_by_event` still returns plain status lists for rows that carry `flag`.

- [ ] **Step 2: Run the tests and confirm they fail.** The send succeeds (flags are ignored) and `booking_readiness_by_event` doesn't exist.
- [ ] **Step 3: Implement**, and switch the two safety test files' monkeypatches to `booking_readiness_by_event` with `BookingReadiness(status=...)` values.
- [ ] **Step 4: Run the full backend suite with coverage**

Run: `cd backend && .venv/bin/python -m pytest --cov -q`
Expected: all pass, at or above the coverage floor, and every new line in `app/` covered.

- [ ] **Step 5: Commit**: `feat(events): booking flags make an event not ready for safety check`.

---

### Task 6: Frontend API, store and labels

**Files:**
- Modify: `frontend/src/services/api.js` (`venuesApi.deactivate`, `venuesApi.reactivate`)
- Modify: `frontend/src/features/venues/venueEditStore.js` (actions `deactivate`, `reactivate`; state `affected`)
- Modify: `frontend/src/features/venues/venueProfile.js` (`INACTIVE_REASONS`, `inactiveReasonLabel`, history labels)
- Test: `frontend/src/features/venues/__tests__/venueEditStore.spec.js`, `venueProfile.spec.js`

**Interfaces:**
- Produces:
  - `venuesApi.deactivate(venueId, payload, token)` → `POST /venues/{id}/deactivate`; `venuesApi.reactivate(venueId, payload, token)` → `POST /venues/{id}/reactivate`
  - `INACTIVE_REASONS = [{ value: "permanently_closed", label: "Permanently closed" }, { value: "long_term_renovation", label: "Long-term renovation" }, { value: "other", label: "Other" }]`; `inactiveReasonLabel(value) -> string` (returns the value itself when unknown)
  - `store.deactivate(venueId, { reason, note, version }, { confirm = false } = {}) -> Promise<boolean>`: true once saved; false after a preview, with `store.affected` set. On error it sets `store.error` and rethrows. It toggles `isSaving` and trims `note`, sending `null` when blank.
  - `store.reactivate(venueId, version) -> Promise<void>`: the same error handling.
  - `EDIT_HISTORY_FIELD_LABELS` gains `is_active: "Status"`, `inactive_reason: "Inactive reason"`, `inactive_note: "Inactive note"`. `formatHistoryValue` renders `is_active` as "Active"/"Inactive" and `inactive_reason` through `inactiveReasonLabel`.

- [ ] **Step 1: Write the failing tests**

```js
// venueEditStore.spec.js — extend the vi.mock venuesApi with deactivate: vi.fn(), reactivate: vi.fn()
it("previews affected bookings without saving", async () => {
  venuesApi.deactivate.mockResolvedValue({ saved: false, affected: [{ booking_id: "b1", event_name: "Gala" }] });
  const store = useVenueEditStore();
  const saved = await store.deactivate("venue-1", { reason: "permanently_closed", note: "  ", version: 3 });
  expect(saved).toBe(false);
  expect(store.affected).toHaveLength(1);
  expect(venuesApi.deactivate).toHaveBeenCalledWith(
    "venue-1", { reason: "permanently_closed", note: null, version: 3, confirm: false }, "access-token");
});

it("saves on confirm and clears the preview", async () => {
  venuesApi.deactivate.mockResolvedValue({ saved: true, venue: { id: "venue-1", is_active: false }, affected: [] });
  const store = useVenueEditStore();
  expect(await store.deactivate("venue-1", { reason: "other", note: " Lease ended ", version: 3 }, { confirm: true })).toBe(true);
  expect(venuesApi.deactivate.mock.calls[0][1]).toMatchObject({ note: "Lease ended", confirm: true });
  expect(store.affected).toEqual([]);
  expect(store.isSaving).toBe(false);
});

it("keeps a deactivate error for the modal and rethrows", async () => {
  venuesApi.deactivate.mockRejectedValue(new Error("This venue is already inactive."));
  const store = useVenueEditStore();
  await expect(store.deactivate("venue-1", { reason: "permanently_closed", note: null, version: 3 }, { confirm: true }))
    .rejects.toThrow("This venue is already inactive.");
  expect(store.error).toBe("This venue is already inactive.");
  expect(store.isSaving).toBe(false);
});

it("reactivates with the loaded version", async () => {
  venuesApi.reactivate.mockResolvedValue({ id: "venue-1", is_active: true });
  const store = useVenueEditStore();
  await store.reactivate("venue-1", 4);
  expect(venuesApi.reactivate).toHaveBeenCalledWith("venue-1", { version: 4 }, "access-token");
});
```

```js
// venueProfile.spec.js
it("summarises a deactivation entry", () => {
  const diff = summariseEditHistoryEntry({
    before: { is_active: true, inactive_reason: null, inactive_note: null },
    after: { is_active: false, inactive_reason: "long_term_renovation", inactive_note: "Roof works" },
  });
  expect(diff).toEqual([
    { field: "is_active", label: "Status", before: "Active", after: "Inactive" },
    { field: "inactive_reason", label: "Inactive reason", before: "None recorded", after: "Long-term renovation" },
    { field: "inactive_note", label: "Inactive note", before: "None recorded", after: "Roof works" },
  ]);
});
```

- [ ] **Step 2: Run the tests and confirm they fail.** `cd frontend && npx vitest run src/features/venues` shows the new tests failing (`deactivate is not a function`, missing labels).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests and confirm they pass.**
- [ ] **Step 5: Commit**: `feat(venues): store actions and labels for deactivating a venue`.

---

### Task 7: Deactivate modal and venue page

**Files:**
- Create: `frontend/src/components/venues/DeactivateVenueModal.vue`
- Create: `frontend/src/components/venues/__tests__/DeactivateVenueModal.spec.js`
- Modify: `frontend/src/views/venues/VenueDetailView.vue` (buttons, banner, modal wiring, `ConfirmModal` for reactivate, refetch)
- Test: `frontend/src/views/venues/__tests__/VenueDetailView.spec.js` (create it if absent, following the closest existing view spec)

**Interfaces:**
- `DeactivateVenueModal` props: `open: Boolean`, `venueName: String (required)`, `affected: Array (default [])`, `busy: Boolean`, `error: String|null`. Emits `confirm` with `{ reason, note, confirm: boolean }` and `cancel`.
  - Step 1 (no `affected`): a reason select (`INACTIVE_REASONS`), a note (max 500, required for Other), and a "Deactivate venue" button that emits `confirm` with `confirm: false`.
  - Step 2 (`affected.length > 0`): lists each booking as event name (or short id), Singapore-time period and status label, with the text "These bookings will be flagged Affected and their coordinators notified." The "Deactivate anyway" button emits `confirm` with `confirm: true`. The reason and note stay as chosen.
  - Buttons are disabled while `busy`. `error` is shown with `role="alert"`. The form resets when `open` turns true.
- `VenueDetailView`:
  - `canEdit` gates "Deactivate venue" (when `venue.is_active`) and "Reactivate venue" (when not).
  - When inactive, a banner (`data-testid="venue-inactive-banner"`) shows "Inactive: {label}", plus the note on its own line when there is one.
  - After a successful deactivate or reactivate it calls `venuesStore.fetchVenue(id)`, refreshes history if that tab is open, and closes the modal.
  - Reactivate opens the existing `ConfirmModal` with "Reactivate {name}? It will appear in venue search again. Bookings flagged Affected stay flagged."

- [ ] **Step 1: Write the failing component tests** (`DeactivateVenueModal.spec.js`, with `@vue/test-utils` `mount` as other component specs in `src/components/**/__tests__`):
  - The confirm button is disabled for Other with an empty or whitespace note, and enabled once the note has text.
  - Submitting with Permanently closed emits `[{ reason: "permanently_closed", note: "", confirm: false }]`.
  - Given `affected` with one booking, it renders the event name and the "flagged Affected" sentence, and "Deactivate anyway" emits `confirm: true`.
  - With `busy: true`, both action buttons are disabled.
  - The `error` prop renders in a `role="alert"` element.

  View spec (`VenueDetailView.spec.js`):
  - As `venue_staff` on an active venue the Deactivate button shows. As `event_coordinator` neither button shows.
  - An inactive venue with `inactive_reason: "long_term_renovation"` and note "Roof works" shows the banner text "Inactive: Long-term renovation" and "Roof works", plus the Reactivate button.
  - A successful `deactivate` (mocked store resolving `true`) calls `venuesStore.fetchVenue` again.

- [ ] **Step 2: Run the tests and confirm they fail.** `npx vitest run src/components/venues src/views/venues`
- [ ] **Step 3: Implement**, following `ReturnEventModal.vue` for structure and styling (Teleport, `role="dialog"`, Bauhaus classes) and the frontend AGENTS.md design rules. Buttons stack at phone width.
- [ ] **Step 4: Run the tests and confirm they pass**, then run the full frontend suite with coverage: `npm run test:coverage`.
- [ ] **Step 5: Commit**: `feat(venues): deactivate and reactivate from the venue page`.

---

### Task 8: Live checks and e2e

**Files:**
- Modify: `backend/scripts/verify_live.py` (new checks, throwaway venue cleanup)
- Create: `frontend/e2e/venue-deactivation.e2e.js`
- Modify: `frontend/e2e/support/throwaway.js` (`createThrowawayVenue`, `deleteThrowawayVenues`)
- Modify: `docs/test-cases/venues.md` (cases `TC-VENUE-065` onwards)

**Requirements:**
- A throwaway venue is named `live-check venue <run>`. It's created with `db_query` insert (capacity 50, theatre layout) and deleted before and after the run, together with its bookings, its `venue_edit_history` rows, and the throwaway events' notifications of type `venue_booking_affected`. Seeded venues are never changed.
- verify_live checks (case ID first):
  - `TC-VENUE-065`: venue staff deactivate the throwaway venue with no bookings → 200 `saved: true`; the DB shows it inactive with its reason; a search as coordinator excludes it.
  - `TC-VENUE-066`: a throwaway event holds the throwaway venue. Deactivate without confirm → `saved: false` with one `affected` booking and nothing written. With confirm, the booking is `flag='affected'` and a `venue_booking_affected` notification exists for the seeded coordinator.
  - `TC-VENUE-067`: requesting the inactive venue → 409 "This venue is inactive."
  - `TC-VENUE-068`: reactivate → 200; the booking's flag is still set; search includes the venue again.
  - `TC-VENUE-069`: the seeded coordinator posting to `/deactivate` → 403. `coordinator@connectsphere.dev` (which also holds `venue_staff`) acting as coordinator → 403.
  - `TC-VENUE-070` (`needs_db`): `supabase/verification/venue_deactivation_checks.sql` passes.
- e2e `venue-deactivation.e2e.js`: as venue staff, open the throwaway venue, deactivate with Long-term renovation and a note, see the banner, reactivate, and see the banner gone.
- Manual cases (developer) added to `docs/test-cases/venues.md` with Type, Created and Last run:
  - `TC-VENUE-071`: the modal and its preview list at 375 px wide
  - `TC-VENUE-072`: banner and button wording
  - `TC-VENUE-073`: the coordinator's notification text after a deactivation

- [ ] **Step 1: Write the checks and e2e spec first.** Run them against a backend and frontend on this branch (spare ports if the developer's own servers are up) **before** the migration is live, and confirm they fail.
- [ ] **Step 2: After Task 1's push and Tasks 2–7, run both suites with recording on:**

```bash
cd backend && env PATH=/home/linuxbrew/.linuxbrew/bin:/usr/bin:/bin .venv/bin/python scripts/verify_live.py --record
```
```bash
cd frontend && npm run test:e2e:record
```
Expected: the new cases pass and no existing case regresses. A failure is a finding: fix it or report it, never re-run until green. Ask before resetting the review fixtures (memory: fixture drift).

- [ ] **Step 3: Ask the developer for the manual pass** (TC-VENUE-071–073), with page, steps and what to look at. Record their results as a manual run file.
- [ ] **Step 4: Commit** the checks, e2e spec, test cases and run logs.

---

### Task 9: Paper trail and heads-up

**Files:**
- Modify: `docs/REQUIREMENTS.md` §6.8 (VC-R1: reason rule; VC-R9 [Team decision]: reactivation leaves flags; booking-flag rules; §9 the `re_review` [Assumption])
- Modify: `docs/IMPLEMENTATION_MAP.md` (status row for 64; the booking-flag contract under "know before you build" for CR-94/CR-95; new endpoints, RPCs and the migration; `booking_readiness_by_event`; `DeactivateVenueModal`; "Last updated" line; also fix the stale CR-103/104 "In progress" rows and the 2026-10-09 migration-drift paragraph, both now merged/resolved)
- Modify: `docs/BUILD_LOG.md` §4 (append a SCRUM-64 entry)
- Modify: `docs/DEFECTS.md` only if live checks found a defect

- [ ] **Step 1: Update the docs** as listed.
- [ ] **Step 2: Draft the Xuan Wei heads-up** for the final report: flag columns and values, `flag_venue_bookings` signature and when to call it, the "first flag stays" rule, CR-95 owns clearing, `venue_booking_affected`, `return_to_planning(..., reason_code="arrangement_flagged")`, and rebasing onto `20261012100000`.
- [ ] **Step 3: Verification before completion.** Run the full `pytest --cov` and `npm run test:coverage` and check against `docs/DEFINITION_OF_DONE.md`.
- [ ] **Step 4: Commit**: `docs: record SCRUM-64 venue deactivation and the booking flag contract`.
- [ ] **Step 5: Ask about the backlog status.** Suggest 64 → IN REVIEW once a PR is open and CI passes (developer's call), and note the re-estimate.
