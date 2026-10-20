# CR-104 Safety Rejection Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a Safety Officer rejects a venue, the coordinator can either explain/revise (with a required note the Safety Officer sees) or replace the venue, and every safety decision names the venues and equipment it concerns.

**Architecture:** One migration changes `mark_safety_revision` (note, `replacement_pending`), widens CR-95's replacement rule and the one-live-booking index to `safety_rejected`. The API passes the note through, accepts the new flag in `_prepare_replacement`, and enriches `SafetyDecision` with names and the coordinator's response. The SPA adds a revise dialog and a Replace venue button to `SafetyRejectedNotice`, and names things in `SafetyDecisionDetails`.

**Tech Stack:** Supabase Postgres (plpgsql, security-definer RPCs), FastAPI + Pydantic v2, pytest; Vue 3 `<script setup>`, Pinia, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-20-cr-104-safety-rejection-followup-design.md`

## Global Constraints

- Branch `fix/cr-104-safety-rejection-followup`; never commit to `main`. Defects D51 (no replacement for Safety rejected), D52 (history shows counts), D53 (Mark as revised records nothing).
- **Spec correction (decided while planning):** the response note is stored in the existing `venue_booking_history.reason` column (already `null` or 1–1,000 chars trimmed, already returned as `BookingHistoryEntry.reason` and shown on the booking page). No new `note` column. Update the spec's §1 in Task 7.
- Note rules: trimmed, 1–1,000 characters. Blank → 422 in the API, `note_required` in the database.
- Every RPC stays `security definer`, `set search_path = ''`, executable by `service_role` only.
- Authorise by the active role: only the assigned coordinator acting as `event_coordinator` may mark revised or request a replacement (existing `CoordinatorOnly` dependency and RPC assignment checks).
- Never null-unsafe flag comparisons in plpgsql: `v.flag not in (...)` is NULL for an unflagged row. Use `v.flag is null or v.flag not in ('affected','safety_rejected')`.
- Copy (exact): dialog title "Mark as revised"; label "What changed, or what should the Safety Officer know?"; 409 "A replacement venue has been requested for this booking."; notice line "Replacement requested: {venue}"; history lines "Rejected venue: …", "Concerns: …", "Coordinator's response:", fallback name "a booking that no longer exists" / "an equipment request that no longer exists".
- The live database is shared: apply the migration only through the developer (`supabase db push`), after a rolled-back validation.

## Review Focus

- A coordinator double-clicks **Mark as revised** in the dialog → exactly one request; the store's `isActing` guard must block the second (Task 5 test).
- A note of exactly 1,000 characters is accepted and 1,001 refused in both API and SQL (Tasks 1, 2 tests).
- A replacement was requested, then venue staff rejected it (status `rejected`) → Mark as revised is allowed again and the notice returns to the two-button state (Tasks 1, 5 tests).
- A decision whose booking or equipment line was later deleted or released → history renders the fallback text, never crashes (Tasks 4, 6 tests).
- An unflagged approved booking named as `replaces_booking_id` → still refused `replaced_booking_invalid` (the null-flag trap; Task 1 test).

---

### Task 1: Migration and SQL verification

**Files:**
- Create: `supabase/migrations/20261020150000_safety_rejection_followup.sql`
- Modify: `supabase/verification/safety_decision_checks.sql` (preflight signature line 14, revision block lines ~225–245, privilege list line ~297, new block before the final `select 'SAFETY DECISION CHECKS PASSED'`)

**Interfaces:**
- Produces: `public.mark_safety_revision(p_booking_id uuid, p_actor_id uuid, p_note text) returns text` — outcomes `ok | booking_not_found | not_safety_rejected | not_assigned | not_planning | note_required | replacement_pending`. Two-argument version dropped.
- Produces: `request_venue_booking(...)` / `request_venue_booking_for_space(...)` signatures unchanged; a replaced booking may be flagged `affected` or `safety_rejected`.
- Produces: index `venue_bookings_one_active_per_space` with predicate `status in ('held','approved','re_review') and (flag is null or flag not in ('affected','safety_rejected'))`.

- [ ] **Step 1: Write the failing SQL checks.** In `safety_decision_checks.sql`:
  - preflight: `to_regprocedure('public.mark_safety_revision(uuid,uuid,text)')`;
  - privilege loop: `'public.mark_safety_revision(uuid,uuid,text)'`;
  - every existing `public.mark_safety_revision(x,y)` call becomes `public.mark_safety_revision(x,y,'Moved the barriers')`;
  - after `'revision succeeds'`, assert the note is stored:

```sql
    perform pg_temp.assert((select reason from public.venue_booking_history where booking_id=b and action='safety_revised')='Moved the barriers','revision note stored');
```

  - new block (fixtures: add keys `'replace_event','booking_replace_old','booking_replace_new','replace_venue_new','booking_plain'` to the `safety_fixture` array; create the event as `planning` alongside the others by adding `'replace_event'` to the events insert and overriding its status to `planning` after the loop):

```sql
do $$
declare coordinator uuid := (select id from safety_fixture where key='coordinator');
        e uuid := (select id from safety_fixture where key='replace_event');
        old_b uuid := (select id from safety_fixture where key='booking_replace_old');
        plain uuid := (select id from safety_fixture where key='booking_plain');
        new_venue uuid := (select id from safety_fixture where key='replace_venue_new');
        space uuid := gen_random_uuid(); old_venue uuid := gen_random_uuid();
        outcome text; new_id uuid;
begin
    update public.events set status='planning' where id=e;
    insert into public.venues(id,name,location,capacity,opens_at,closes_at) values
        (old_venue,'Safety fixture old '||old_venue,'Verification',100,'08:00','23:00'),
        (new_venue,'Safety fixture new '||new_venue,'Verification',100,'08:00','23:00');
    insert into public.event_space_requests(id,event_id,label,starts_at,ends_at)
        values(space,e,'Safety fixture replace','2099-01-01 10:00+00','2099-01-01 12:00+00');
    insert into public.venue_bookings(id,event_id,venue_id,event_space_request_id,occupied_period,status,flag,flag_reason,flagged_at)
        values(old_b,e,old_venue,space,tstzrange('2099-01-01 10:00+00','2099-01-01 12:00+00','[)'),'approved','safety_rejected','Exits blocked',now());

    -- F1: blank and over-long notes refused, nothing changed.
    perform pg_temp.assert(public.mark_safety_revision(old_b,coordinator,null)='note_required','note null');
    perform pg_temp.assert(public.mark_safety_revision(old_b,coordinator,'   ')='note_required','note blank');
    begin
        perform public.mark_safety_revision(old_b,coordinator,repeat('x',1001));
        raise exception 'SAFETY FAIL: 1001-char note accepted';
    exception when check_violation then null; end;
    perform pg_temp.assert((select flag from public.venue_bookings where id=old_b)='safety_rejected','refused note leaves flag');

    -- F3: a Safety-rejected booking can be replaced; the index lets the replacement sit beside it.
    select o.outcome, o.booking_id into outcome, new_id
      from public.request_venue_booking_for_space(space,new_venue,coordinator,null,'msg',old_b) o;
    perform pg_temp.assert(outcome='ok','replacement of safety_rejected accepted: '||coalesce(outcome,'null'));
    perform pg_temp.assert((select replaces_booking_id from public.venue_bookings where id=new_id)=old_b,'replacement links');

    -- F4: revision refused while the replacement is live; allowed once it is rejected.
    perform pg_temp.assert(public.mark_safety_revision(old_b,coordinator,'Kept it')='replacement_pending','pending blocks revision');
    update public.venue_bookings set status='rejected' where id=new_id;
    perform pg_temp.assert(public.mark_safety_revision(old_b,coordinator,repeat('y',1000))='ok','1000-char note after replacement rejected');

    -- Null-flag trap: an unflagged approved booking is still not replaceable.
    -- It gets its own space: old_b is now an unflagged live booking on `space`,
    -- so a second live booking there would break the unique index.
    -- Its own venue too: DB-1 refuses two live bookings on one venue at once.
    space := gen_random_uuid(); old_venue := gen_random_uuid();
    insert into public.venues(id,name,location,capacity,opens_at,closes_at)
        values(old_venue,'Safety fixture plain '||old_venue,'Verification',100,'08:00','23:00');
    insert into public.event_space_requests(id,event_id,label,starts_at,ends_at)
        values(space,e,'Safety fixture plain','2099-01-01 10:00+00','2099-01-01 12:00+00');
    insert into public.venue_bookings(id,event_id,venue_id,event_space_request_id,occupied_period,status)
        values(plain,e,old_venue,space,tstzrange('2099-01-01 10:00+00','2099-01-01 12:00+00','[)'),'approved');
    select o.outcome into outcome from public.request_venue_booking_for_space(space,new_venue,coordinator,null,'msg',plain) o;
    perform pg_temp.assert(outcome='replaced_booking_invalid','unflagged booking not replaceable: '||coalesce(outcome,'null'));
end $$;
```

- [ ] **Step 2: Run it against the live project (rolled back) and confirm it fails on the preflight.**

Run (from repo root): `supabase db query --linked -f supabase/verification/safety_decision_checks.sql` (if `-f` is unsupported in CLI 2.120.0, pass the file's contents as the query argument).
Expected: `SAFETY FAIL: Task 1 table/RPC interfaces are missing`.

- [ ] **Step 3: Write the migration.** Start each function from its **live** body (`select pg_get_functiondef('public.request_venue_booking'::regproc)`, same for `_for_space`), change only the replaced-booking condition, and keep comments and grants.

```sql
-- ConnectSphere - CR-104 follow-up (D51, D53): revise with a note, replace a
-- Safety-rejected venue through CR-95's replacement request.

-- D51: a Safety-rejected booking also stops holding the space's single slot,
-- so its replacement can sit beside it until approval releases it.
drop index public.venue_bookings_one_active_per_space;
create unique index venue_bookings_one_active_per_space
    on public.venue_bookings (event_space_request_id)
    where status in ('held', 'approved', 're_review')
      and (flag is null or flag not in ('affected', 'safety_rejected'));

-- request_venue_booking / request_venue_booking_for_space: recreated from the
-- live bodies; the only change is the replaced booking's flag test:
--     or v_replaced.flag is distinct from 'affected'
-- becomes
--     or v_replaced.flag is null
--     or v_replaced.flag not in ('affected', 'safety_rejected')
-- Update each function's comment to say "affected or Safety-rejected booking".

drop function public.mark_safety_revision(uuid, uuid);
create function public.mark_safety_revision(p_booking_id uuid, p_actor_id uuid, p_note text)
returns text language plpgsql security definer set search_path = '' as $$
declare
    v_booking public.venue_bookings;
    v_event public.events;
begin
    select * into v_event from public.events
    where id=(select event_id from public.venue_bookings where id=p_booking_id) for update;
    select * into v_booking from public.venue_bookings where id=p_booking_id for update;
    if not found then return 'booking_not_found'; end if;
    if v_booking.flag is distinct from 'safety_rejected' then return 'not_safety_rejected'; end if;
    if v_event.coordinator_id is distinct from p_actor_id then return 'not_assigned'; end if;
    if v_event.status <> 'planning' then return 'not_planning'; end if;
    if p_note is null or length(btrim(p_note)) = 0 then return 'note_required'; end if;
    if exists (select 1 from public.venue_bookings r
               where r.replaces_booking_id = p_booking_id
                 and r.status in ('held', 'approved', 're_review')) then
        return 'replacement_pending';
    end if;
    update public.venue_bookings set flag=null, flag_reason=null, flagged_at=null where id=p_booking_id;
    insert into public.venue_booking_history(booking_id,actor_id,action,from_status,to_status,reason)
    values(p_booking_id,p_actor_id,'safety_revised',v_booking.status,v_booking.status,btrim(p_note));
    return 'ok';
end $$;
comment on function public.mark_safety_revision(uuid,uuid,text) is
    'CR-104 AC3/AC4, D53: the assigned coordinator marks a Safety-rejected booking revised in Planning with a required note (stored as the history row''s reason). Refused while a replacement is pending (D51). API-only.';
revoke execute on function public.mark_safety_revision(uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.mark_safety_revision(uuid,uuid,text) to service_role;
```

  Also update the `venue_bookings.flag` column comment: `safety_rejected` is cleared by Mark as revised **or** released when an approved replacement stands in for it.

- [ ] **Step 4: Validate the migration in a rolled-back transaction.** Build a scratch file `begin; <migration>; <safety_decision_checks.sql body without its own begin/rollback>; rollback;` in the scratchpad and run it with `supabase db query --linked -f <file>`.
Expected: `SAFETY DECISION CHECKS PASSED`, and `venue_deactivation_checks.sql` still passes the same way (it touches the index).

- [ ] **Step 5: Hand the push to the developer.** Run `supabase db push --dry-run` and show it; ask the developer to run `supabase db push`; confirm with `supabase migration list --linked`, then re-run the checks file on its own: `SAFETY DECISION CHECKS PASSED`. Run `get_advisors` (security and performance) or the CLI equivalent and confirm nothing new.

- [ ] **Step 6: Commit**

```bash
git add supabase/migrations/20261020150000_safety_rejection_followup.sql supabase/verification/safety_decision_checks.sql
git commit -m "feat(db): revise with a note and replace a Safety-rejected booking (D51, D53)"
```

---

### Task 2: API — Mark as revised takes a note

**Files:**
- Modify: `backend/app/modules/venues/schemas.py` (add `SafetyRevisionRequest`)
- Modify: `backend/app/modules/venues/router.py:186-189`
- Modify: `backend/app/modules/venues/service.py:1043-1061`
- Modify: `backend/app/modules/venues/repository.py:815-819`
- Test: `backend/tests/test_venue_booking_mark_revised_api.py`

**Interfaces:**
- Consumes: Task 1's RPC `mark_safety_revision(p_booking_id, p_actor_id, p_note)`.
- Produces: `SafetyRevisionRequest(BaseModel)` with `note: str` (stripped, 1–1000); `service.mark_safety_revision(booking_id: str, actor_id: str, note: str) -> VenueBookingDetail`; `repository.mark_safety_revision(booking_id: str, actor_id: str, note: str) -> str`; endpoint `POST /api/v1/venue-bookings/{id}/mark-revised` body `{"note": str}`.

- [ ] **Step 1: Update the tests first.** In the `revising` fixture, `mark(booking_id, actor_id, note)` appends `(booking_id, actor_id, note)`. Every `client.post(REVISE_URL, ...)` sends `json={'note': 'Moved the barriers'}`. Change the existing assertion to `[(BOOKING_ID, COORDINATOR_ID, 'Moved the barriers')]`, the repository test to call `mark_safety_revision(BOOKING_ID, COORDINATOR_ID, 'Moved the barriers')` and expect params `{'p_booking_id':…, 'p_actor_id':…, 'p_note':'Moved the barriers'}`. Add:

```python
@pytest.mark.parametrize('body', [{}, {'note': ''}, {'note': '   '}, {'note': 'x' * 1001}])
def test_note_is_required_and_bounded(client, auth_headers, authenticate_as, revising, body):
    authenticate_as('event_coordinator', user_id=COORDINATOR_ID)
    assert client.post(REVISE_URL, json=body, headers=auth_headers).status_code == 422
    assert not revising['revisions']

def test_note_is_trimmed_and_1000_chars_accepted(client, auth_headers, authenticate_as, revising):
    authenticate_as('event_coordinator', user_id=COORDINATOR_ID)
    assert client.post(REVISE_URL, json={'note': '  ' + 'x' * 1000 + ' '}, headers=auth_headers).status_code == 200
    assert revising['revisions'][0][2] == 'x' * 1000

def test_pending_replacement_is_409(client, auth_headers, authenticate_as, revising):
    authenticate_as('event_coordinator', user_id=COORDINATOR_ID)
    revising['outcome'] = 'replacement_pending'
    response = client.post(REVISE_URL, json={'note': 'Kept it'}, headers=auth_headers)
    assert response.status_code == 409
    assert response.json()['detail'] == 'A replacement venue has been requested for this booking.'

def test_note_required_outcome_from_the_database_is_422(client, auth_headers, authenticate_as, revising):
    authenticate_as('event_coordinator', user_id=COORDINATOR_ID)
    revising['outcome'] = 'note_required'
    assert client.post(REVISE_URL, json={'note': 'x'}, headers=auth_headers).status_code == 422
```

  The role-denial and acting-as tests also send the valid body and still expect 403 (auth runs before body validation; keep it that way).

- [ ] **Step 2: Run and confirm the failures.** `cd backend && .venv/bin/python -m pytest tests/test_venue_booking_mark_revised_api.py -q` → fails (mark called with 2 args; 422 tests get 200).

- [ ] **Step 3: Implement.** Schema, matching `SafetyRejectRequest`'s strip validator:

```python
class SafetyRevisionRequest(BaseModel):
    """D53: what the coordinator changed, or wants the Safety Officer to know."""
    note: str = Field(min_length=1, max_length=1000)

    @field_validator("note", mode="before")
    @classmethod
    def strip_note(cls, value):
        return value.strip() if isinstance(value, str) else value
```

  Router: `def mark_venue_booking_revised(booking_id: UUID, body: SafetyRevisionRequest, current_user: CoordinatorOnly)` → `service.mark_safety_revision(str(booking_id), current_user.id, body.note)`. Repository passes `"p_note": note`. Service adds to `MARK_REVISED_REFUSALS` the entry `"replacement_pending": "A replacement venue has been requested for this booking."` and maps `note_required` to `HTTPException(422, "A note is required.")` (raised before the refusal lookup).

- [ ] **Step 4: Run.** Same command → all pass. Then the full backend suite: `.venv/bin/python -m pytest -q` → all pass.

- [ ] **Step 5: Commit** `git commit -m "feat(venues): Mark as revised requires a note (D53)"` with the four source files and the test.

---

### Task 3: API — replacement accepts a Safety-rejected booking

**Files:**
- Modify: `backend/app/modules/venues/service.py:710-729` (`_prepare_replacement`)
- Test: `backend/tests/test_venue_booking_request_api.py` (next to the existing CR-95 replacement tests; find them with `grep -n replaces_booking_id`)

**Interfaces:**
- Consumes: Task 1's widened database rule.
- Produces: `POST /venue-bookings` with `replaces_booking_id` naming a `safety_rejected` held/approved booking of the same event/space → handled like an `affected` one.

- [ ] **Step 1: Write the failing tests**, reusing the existing replacement fixture (`get_replaceable_booking` stub):

```python
@pytest.mark.parametrize("flag", ["affected", "safety_rejected"])
def test_a_flagged_booking_can_be_replaced(client, auth_headers, authenticate_as, replaceable, flag):
    replaceable["row"]["flag"] = flag
    authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
    response = client.post(URL, json=replacement_body(), headers=auth_headers)
    assert response.status_code == 201

@pytest.mark.parametrize("flag", [None, "conflict", "unsuitable"])
def test_other_flags_are_not_replaceable(client, auth_headers, authenticate_as, replaceable, flag):
    replaceable["row"]["flag"] = flag
    authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
    response = client.post(URL, json=replacement_body(), headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "That booking is not waiting for a replacement."

def test_replacing_a_safety_rejected_booking_does_not_return_to_planning(
    client, auth_headers, authenticate_as, replaceable, monkeypatch
):
    replaceable["row"]["flag"] = "safety_rejected"
    returned = []
    monkeypatch.setattr(events_service, "return_to_planning", lambda *a, **k: returned.append(a))
    authenticate_as("event_coordinator", user_id=COORDINATOR_ID)
    client.post(URL, json=replacement_body(), headers=auth_headers)
    assert returned == []  # the event is already in Planning after a rejection
```

  If the existing fixture/helper names differ (`replaceable`, `replacement_body`), use the existing ones and keep the assertions.

- [ ] **Step 2: Run** `-k replace` → the `safety_rejected` case fails with 409.

- [ ] **Step 3: Implement.** In `_prepare_replacement` replace `row.get("flag") != "affected"` with `row.get("flag") not in REPLACEABLE_FLAGS`, where module-level `REPLACEABLE_FLAGS = ("affected", "safety_rejected")` with a one-line comment (CR-95 AC4; D51). Update the docstring ("this event's own affected or Safety-rejected booking").

- [ ] **Step 4: Run** the file, then the full suite → pass.

- [ ] **Step 5: Commit** `git commit -m "feat(venues): replace a Safety-rejected booking through CR-95's request (D51)"`.

---

### Task 4: API — named decision history with the coordinator's response

**Files:**
- Modify: `backend/app/modules/events/schemas.py:339-348` (`SafetyDecision`, new small models)
- Modify: `backend/app/modules/events/service.py:952-982` (`safety_decisions`, `safety_review`)
- Modify: `backend/app/modules/venues/repository.py`, `backend/app/modules/venues/service.py` (name and revision lookups)
- Modify: `backend/app/modules/equipment/repository.py`, `backend/app/modules/equipment/service.py` (line names)
- Test: `backend/tests/test_safety_decision_names.py` (new)

**Interfaces:**
- Produces (venues service): `booking_venue_names(booking_ids: list[str]) -> dict[str, str | None]`; `venue_names(venue_ids: list[str]) -> dict[str, str | None]`; `safety_revisions(booking_ids: list[str]) -> list[dict]` with keys `booking_id, note, by_name, at` (from `venue_booking_history` rows `action='safety_revised'`, `reason is not null`, oldest first, actor name via `venue_booking_history_actor_id_fkey`).
- Produces (equipment service): `line_names(line_ids: list[str]) -> dict[str, str | None]` (equipment name for each `equipment_requests` id).
- Produces (events schemas):

```python
class NamedBooking(BaseModel):
    booking_id: UUID
    venue_name: str | None = None

class NamedEquipmentLine(BaseModel):
    id: UUID
    equipment_name: str | None = None

class NamedVenue(BaseModel):
    venue_id: UUID
    venue_name: str | None = None

class SafetyRevision(BaseModel):
    note: str
    by_name: str | None = None
    at: datetime

class SafetyDecision(BaseModel):  # existing fields unchanged, plus:
    affected_bookings: list[NamedBooking] = []
    affected_equipment: list[NamedEquipmentLine] = []
    rejected_venues: list[NamedVenue] = []
    revision: SafetyRevision | None = None
```

- Produces (events service): `_named_decisions(rows: list[dict]) -> list[SafetyDecision]`, used by both `safety_decisions` and `safety_review`.

- [ ] **Step 1: Write the failing tests** (`test_safety_decision_names.py`), stubbing the lookups and `repository.list_safety_decisions`, and calling the existing `GET /api/v1/events/{id}/safety-decisions` as the assigned coordinator and as the Safety Officer (reuse the fixtures in `test_safety_history.py` / the safety review tests for `_assigned_event` and `_officer_event` stubs):

```python
def test_decisions_name_their_venues_equipment_and_rejected_venue(client, auth_headers, authenticate_as, decisions):
    decisions["rows"] = [dict(ROW, decision="arrangement_rejected", affected_booking_ids=[B1], rejected_venue_ids=[V1],
                              affected_equipment_request_ids=[L1])]
    decisions["booking_names"] = {B1: "Heritage Hall"}
    decisions["venue_names"] = {V1: "Heritage Hall"}
    decisions["line_names"] = {L1: "Projector"}
    authenticate_as("safety_officer")
    [body] = client.get(URL, headers=auth_headers).json()
    assert body["affected_bookings"] == [{"booking_id": B1, "venue_name": "Heritage Hall"}]
    assert body["rejected_venues"] == [{"venue_id": V1, "venue_name": "Heritage Hall"}]
    assert body["affected_equipment"] == [{"id": L1, "equipment_name": "Projector"}]
    assert body["affected_booking_ids"] == [B1]  # unchanged contract

def test_a_rejection_carries_the_first_response_after_it(client, auth_headers, authenticate_as, decisions):
    decisions["rows"] = [dict(ROW, decision="arrangement_rejected", affected_booking_ids=[B1], decided_at="2031-01-01T10:00:00Z")]
    decisions["revisions"] = [
        dict(booking_id=B1, note="Before", by_name="Marcus", at="2030-12-31T10:00:00Z"),
        dict(booking_id=B1, note="Moved the barriers", by_name="Marcus", at="2031-01-02T10:00:00Z"),
        dict(booking_id=B1, note="Later", by_name="Marcus", at="2031-01-03T10:00:00Z"),
    ]
    authenticate_as("safety_officer")
    [body] = client.get(URL, headers=auth_headers).json()
    assert body["revision"]["note"] == "Moved the barriers" and body["revision"]["by_name"] == "Marcus"

def test_missing_names_are_null_and_other_decisions_have_no_revision(client, auth_headers, authenticate_as, decisions):
    decisions["rows"] = [dict(ROW, decision="changes_requested", affected_booking_ids=[B1], affected_equipment_request_ids=[L1])]
    authenticate_as("safety_officer")
    [body] = client.get(URL, headers=auth_headers).json()
    assert body["affected_bookings"] == [{"booking_id": B1, "venue_name": None}]
    assert body["affected_equipment"] == [{"id": L1, "equipment_name": None}]
    assert body["revision"] is None

def test_lookups_run_once_for_all_decisions(client, auth_headers, authenticate_as, decisions):
    decisions["rows"] = [dict(ROW, id=str(uuid4()), affected_booking_ids=[B1]) for _ in range(5)]
    authenticate_as("safety_officer")
    client.get(URL, headers=auth_headers)
    assert decisions["calls"]["booking_venue_names"] == 1 and decisions["calls"]["safety_revisions"] == 1

def test_the_safety_review_uses_the_same_named_decisions(client, auth_headers, authenticate_as, decisions, review_stubs):
    decisions["rows"] = [dict(ROW, affected_booking_ids=[B1])]
    decisions["booking_names"] = {B1: "Heritage Hall"}
    authenticate_as("safety_officer")
    body = client.get(REVIEW_URL, headers=auth_headers).json()
    assert body["decisions"][0]["affected_bookings"][0]["venue_name"] == "Heritage Hall"
```

  The `decisions` fixture monkeypatches `venues_service.booking_venue_names`, `venues_service.venue_names`, `venues_service.safety_revisions`, `equipment_service.line_names` to read from its dict and count calls. Add repository tests (MagicMock admin client, as in `test_venue_buffers_and_safety.py`) asserting each lookup issues one `.in_(...)` query and returns `{}` / `[]` without querying when given no ids. Existing denial tests for this endpoint stay and must still pass.

- [ ] **Step 2: Run** `pytest tests/test_safety_decision_names.py -q` → fail (fields missing).

- [ ] **Step 3: Implement.** Repository functions query once each with `.in_("id", ids)` (bookings with `venue:venues(name)` embed named by its FK; venues; `equipment_requests` with `equipment(name)`; `venue_booking_history` filtered `.eq("action","safety_revised").in_("booking_id", ids).not_.is_("reason","null").order("created_at")`). Short-circuit on empty ids. `_named_decisions` collects all ids across rows, calls each lookup once, and builds each `SafetyDecision`; for `arrangement_rejected` it picks the earliest revision with `booking_id in affected_booking_ids` and `at > decided_at`.

- [ ] **Step 4: Run** the new file and the full suite → pass.

- [ ] **Step 5: Commit** `git commit -m "feat(safety): name venues and equipment in decisions and show the coordinator's response (D52, D53)"`.

---

### Task 5: SPA — revise dialog, Replace venue, pending replacement

**Files:**
- Modify: `frontend/src/services/api.js:106-108` (`markRevised(bookingId, note, token)` sends `{ note }`)
- Modify: `frontend/src/features/events/eventReviewStore.js:~110-125` (`markBookingRevised(bookingId, note)`)
- Modify: `frontend/src/features/venues/bookingRequest.js:96-102` (`safetyRejectedPanelState`)
- Modify: `frontend/src/components/venues/SafetyRejectedNotice.vue`
- Modify: `frontend/src/views/events/CoordinatorEventView.vue:59-67, 316-322, 370-375`
- Test: `frontend/src/services/__tests__/api.spec.js`, `frontend/src/features/venues/__tests__/bookingRequest.spec.js`, `frontend/src/components/venues/__tests__/SafetyRejectedNotice.spec.js`, the event review store spec (find with `grep -rln markBookingRevised frontend/src`)

**Interfaces:**
- Consumes: Task 2's body `{note}`; Task 3's replacement acceptance.
- Produces: `safetyRejectedPanelState` → `{kind:'safety-rejected', booking, reason, canMarkRevised, canReplace}` or, with a live replacement, `{kind:'safety-rejected', booking, reason, replacement, canMarkRevised:false, canReplace:false}`.
- Produces: `SafetyRejectedNotice` props `reason, canMarkRevised, canReplace, replacement (Object|null), busy`; emits `mark-revised(note: string)` and `replace`.

- [ ] **Step 1: Write the failing tests.**

```js
// bookingRequest.spec.js
it("offers revise and replace in Planning", () => {
  expect(venuePanelState({ status: "planning", venue_bookings: [rejected] })).toEqual({
    kind: "safety-rejected", booking: rejected, reason: "Exits blocked", canMarkRevised: true, canReplace: true,
  });
});
it.each(["held", "approved", "re_review"])("a %s replacement hides both actions and names it", (status) => {
  const replacement = { ...booking(status), id: "r1", replaces_booking_id: rejected.id, venue_name: "Town Hall" };
  const state = venuePanelState({ status: "planning", venue_bookings: [rejected, replacement] });
  expect(state).toMatchObject({ kind: "safety-rejected", replacement, canMarkRevised: false, canReplace: false });
});
it("a rejected replacement brings both actions back", () => {
  const replacement = { ...booking("rejected"), id: "r1", replaces_booking_id: rejected.id };
  expect(venuePanelState({ status: "planning", venue_bookings: [rejected, replacement] }))
    .toMatchObject({ canMarkRevised: true, canReplace: true });
});

// SafetyRejectedNotice.spec.js
it("asks for a note and emits it trimmed", async () => {
  const { emitted } = await mountNotice({ canMarkRevised: true });
  button("Mark as revised").click(); await nextTick();
  const dialog = document.querySelector('[role="dialog"]');
  expect(dialog.textContent).toContain("What changed, or what should the Safety Officer know?");
  expect(dialogButton("Mark as revised").disabled).toBe(true);
  await type(dialog.querySelector("textarea"), "  Moved the barriers ");
  dialogButton("Mark as revised").click();
  expect(emitted["mark-revised"]).toEqual([["Moved the barriers"]]);
});
it("emits replace", async () => {
  const { emitted } = await mountNotice({ canReplace: true });
  button("Replace venue").click();
  expect(emitted.replace).toHaveLength(1);
});
it("names a requested replacement and offers no actions", async () => {
  await mountNotice({ replacement: { venue_name: "Town Hall" } });
  expect(document.body.textContent).toContain("Replacement requested: Town Hall");
  expect(button("Mark as revised")).toBeNull(); expect(button("Replace venue")).toBeNull();
});

// api.spec.js
it("markRevised posts the note", async () => {
  await venueBookingsApi.markRevised("b1", "Moved the barriers", "tok");
  expect(lastRequest()).toMatchObject({ url: expect.stringContaining("/venue-bookings/b1/mark-revised"), method: "POST", body: { note: "Moved the barriers" } });
});

// event review store spec
it("markBookingRevised sends the note once even if called twice", async () => {
  const store = useEventReviewStore(); store.event = { id: "e1" };
  await Promise.all([store.markBookingRevised("b1", "Note"), store.markBookingRevised("b1", "Note")]);
  expect(venueBookingsApi.markRevised).toHaveBeenCalledTimes(1);
  expect(venueBookingsApi.markRevised).toHaveBeenCalledWith("b1", "Note", "access");
});
```

  Use each spec file's existing mount and request helpers; the helper names above are placeholders for them only where the file already has an equivalent.

- [ ] **Step 2: Run** `npx vitest run <those files>` → fail.

- [ ] **Step 3: Implement.**
  - `safetyRejectedPanelState` finds `replacement = bookings.find(b => b.replaces_booking_id === booking.id && ["held","approved","re_review"].includes(b.status))`; `canMarkRevised = !replacement && event.status === "planning"`; `canReplace` the same.
  - `SafetyRejectedNotice`: keep the badge, reason and guidance line; buttons **Mark as revised** (opens an inline dialog: `role="dialog"`, label above, textarea `maxlength=1000` with "n / 1000" counter, **Mark as revised** disabled until trimmed text is non-empty or while `busy`, **Cancel**) and **Replace venue** (`variant="outline"`); with `replacement`, show "Replacement requested: {{ replacement.venue_name ?? 'another venue' }}" instead of the buttons. Guidance line becomes "Revise the arrangement with venue staff and mark it revised, or replace the venue. Then send the event for safety check again."
  - `markBookingRevised(bookingId, note)` returns early when `isActing`, sets `isActing = true` before the await, passes `note`.
  - `CoordinatorEventView`: `@mark-revised="(note) => markRevised(panel.booking.id, note)"`, `:can-replace`, `:replacement`, `@replace="findReplacement(panel, space)"` for both the space and event-level notices.

- [ ] **Step 4: Run** the files, then `npx vitest run` → all pass.

- [ ] **Step 5: Commit** `git commit -m "feat(safety): revise with a note or replace a Safety-rejected venue in the SPA (D51, D53)"`.

---

### Task 6: SPA — named decision history

**Files:**
- Modify: `frontend/src/components/events/SafetyDecisionDetails.vue`
- Create: `frontend/src/components/events/__tests__/SafetyDecisionDetails.spec.js`

**Interfaces:**
- Consumes: Task 4's `affected_bookings`, `affected_equipment`, `rejected_venues`, `revision`.

- [ ] **Step 1: Write the failing tests.**

```js
it("names the rejected venue and the coordinator's response", async () => {
  mount({ ...BASE, decision: "arrangement_rejected", comment: "Exits blocked",
    rejected_venues: [{ venue_id: "v1", venue_name: "Heritage Hall" }],
    affected_bookings: [{ booking_id: "b1", venue_name: "Heritage Hall" }],
    revision: { note: "Moved the barriers", by_name: "Marcus", at: "2031-01-02T02:00:00Z" } });
  const text = document.body.textContent;
  expect(text).toContain("Rejected venue: Heritage Hall");
  expect(text).toContain("Coordinator's response:");
  expect(text).toContain("Moved the barriers");
  expect(text).toContain("Marcus");
  expect(text).not.toContain("Affected bookings: 1");
});
it("lists what a change request concerns, with fallbacks", async () => {
  mount({ ...BASE, decision: "changes_requested",
    affected_bookings: [{ booking_id: "b1", venue_name: "Heritage Hall" }, { booking_id: "b2", venue_name: null }],
    affected_equipment: [{ id: "q1", equipment_name: "Projector" }] });
  expect(document.body.textContent).toContain("Concerns: Heritage Hall · a booking that no longer exists · Projector");
});
it("shows nothing extra for a decision with no arrangements", async () => {
  mount({ ...BASE, decision: "approved" });
  expect(document.body.textContent).not.toContain("Concerns:");
  expect(document.body.textContent).not.toContain("Coordinator's response:");
});
```

- [ ] **Step 2: Run** → fail.

- [ ] **Step 3: Implement.** Replace the two count paragraphs with: "Rejected venue: {names}" when `rejected_venues` is non-empty; "Concerns: {booking names · equipment names}" for non-rejection decisions with arrangements; under a rejection with `revision`, a bordered block "Coordinator's response:" + note (`whitespace-pre-wrap`) + "{by_name ?? 'Coordinator'} · {displaySafetyTime(at)}". Fallback strings per Global Constraints.

- [ ] **Step 4: Run** the file and `npx vitest run` → pass. Run `npm run build` → succeeds.

- [ ] **Step 5: Commit** `git commit -m "feat(safety): decision history names venues, equipment and the response (D52)"`.

---

### Task 7: Live checks, browser check, manual cases and paper trail

**Files:**
- Modify: `backend/scripts/verify_live.py` (TC-SDEC-022/023 send a body; new TC-SDEC-031, TC-SDEC-032)
- Modify: `backend/tests/test_verify_live_safety_rework.py` (the mark-revised probe asserts a JSON body with `note`)
- Create: `frontend/e2e/safety-rejection-followup.e2e.js` (TC-SDEC-033)
- Modify: `docs/test-cases/safety-decisions.md` (TC-SDEC-031–035), `docs/DEFECTS.md` (D51–D53), `docs/BUILD_LOG.md`, `docs/IMPLEMENTATION_MAP.md`, `docs/REQUIREMENTS.md` (two [Team decision]s), the spec (§1 note storage correction)

- [ ] **Step 1: Update the probes first.** TC-SDEC-022 and 023 post `json={"note": "live check"}`; the probe test asserts `json.loads(request.content) == {"note": "live check"}`. Run `pytest tests/test_verify_live_safety_rework.py` → fails, then fix the checks → passes.

- [ ] **Step 2: Add live checks** (throwaway records only; deleted by the run's existing cleanup):
  - **TC-SDEC-031** "Reject, then mark revised with a note; the decision history shows the response": throwaway venue + event + approved booking (SQL, as TC-VENUE checks do), set the event to `safety_review` via SQL; as `safety_officer` POST `/events/{id}/safety-reject` `{booking_id, reason:"live check exits"}` → 200; as coordinator POST mark-revised with `{"note":"   "}` → 422, then `{"note":"live check revised"}` → 200; as `safety_officer` GET `/events/{id}/safety-decisions` → the rejection has `rejected_venues[0].venue_name` = the throwaway venue's name and `revision.note == "live check revised"`.
  - **TC-SDEC-032** "Replace a Safety-rejected venue; approval releases it": same setup through the reject; as coordinator POST `/venue-bookings` `{event_id, venue_id: second throwaway venue, replaces_booking_id}` → 201; mark-revised now → 409 with the replacement message; as venue staff POST `/venue-bookings/{new}/approve` → 200; SQL: original `status='released'`, new `approved`, unflagged.

  Run each with `-k TC-SDEC-03` against this branch's backend on a spare port → pass.

- [ ] **Step 3: Browser check TC-SDEC-033.** Throwaway planning event with an approved booking flagged `safety_rejected` (SQL helper `createThrowawayBooking` + an update), coordinator session: open `/coordinator/events/{id}`, see "Safety rejected", click **Replace venue** → URL has `replaces=`; request the second throwaway venue from search → back on the event page the notice shows "Replacement requested: …" and no Mark as revised. Run with `E2E_BASE_URL`/`E2E_API_URL` on spare ports → pass.

- [ ] **Step 4: Manual cases.** TC-SDEC-034 (revise dialog wording, counter, 375 px), TC-SDEC-035 (named history and response as Safety Officer and coordinator, 375 px). Add rows for 031–033 too, with Created 2026-10-20.

- [ ] **Step 5: Paper trail.** D51–D53 in `DEFECTS.md` (fixed on this branch); `BUILD_LOG.md` entry (symptoms, causes, fix, verification, not verified); `IMPLEMENTATION_MAP.md` (mark-revised body, replacement flags, `SafetyDecision` fields, migration row, booking flag contract note, Last updated); `REQUIREMENTS.md` [Team decision]s (replacement via CR-95; note required); spec §1 correction (note stored in `reason`).

- [ ] **Step 6: Recorded runs.** `python scripts/verify_live.py --record --api <port>` and `npm run test:e2e:record` (at least the safety, venue and booking specs) against this branch; commit the run logs with the docs.

- [ ] **Step 7: Ask the developer for the manual pass** (TC-SDEC-034, 035) and record it.

- [ ] **Step 8: Commit** `git commit -m "test(safety): live, browser and manual cases for the rejection follow-up (D51-D53)"` and `git commit -m "docs(safety): D51-D53 paper trail"`.
