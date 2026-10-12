# SCRUM-64 — Deactivate a venue from the catalogue: design

_Date: 2026-10-12 · Branch: `feature/scrum-64-deactivate-venue` · Epic: Venue catalogue · Sprint 3 · Priority 3 · 1 SP (proposed; see §8)_

## 1. Story and acceptance criteria (Product backlog sheet, row 64, read 12 Oct)

> As Venue staff, I want to deactivate a venue that's no longer available for use, so that I stop receiving requests for a venue I can no longer offer.

- **AC1** Can mark a venue as inactive with a reason (e.g. permanently closed, under long-term renovation).
- **AC2** Inactive venues no longer appear in venue search results or suitability checks.
- **AC3** [W7 CR-02] Existing future held or approved bookings at the venue are flagged Affected for Event Coordinator follow-up (as in CR-95) rather than silently removed.
- **AC4** An inactive venue can be reactivated, restoring its visibility in future searches.

Customer clarification (sheet): AC3 reuses the affected-booking flagging from CR-95; widened 08/10 to held and approved bookings, matching CR-95.

**Already built:** `venues.is_active` (migration `20260915090000`); search marks an inactive venue unsuitable with reason `inactive` (`venues/search.py`), so AC2's search half holds today; the venue staff dashboard splits active / inactive; `VenueDetailView` labels an inactive venue; `events.service.return_to_planning` (CR-104) with reason code `arrangement_flagged`; the readiness module already understands `BookingReadiness.flags` (82 AC10) but production always passes empty flags.

**Gaps found:**
- `request_venue_booking` only checks that the venue exists, so a direct API call can hold an inactive venue — contrary to the story's "so that".
- Nothing stores a booking flag. CR-95 (Xuan Wei) has not started and will build on what 64 adds.
- `_safety_readiness_for` reads booking statuses only, and `safety_approve_event` rechecks statuses only, so a flag would have no effect on the safety check.

## 2. Decisions

| Decision | Choice | Label |
|---|---|---|
| Who builds the booking flag | 64 adds it; CR-95 and CR-94 reuse it. Xuan Wei agreed to go with this design (12 Oct). | [Team decision] |
| Flag shape | One nullable flag per booking: `flag` (`affected`, `conflict`, `unsuitable`), `flag_reason`, `flagged_at`. `expired` stays derived from hold expiry, not stored. A booking with any flag is not ready. | [Team decision] |
| A booking that is already flagged | A new flag does not overwrite it. The first open issue stays until the coordinator resolves it. | [Team decision] |
| Who clears flags | CR-95 (replacement approved, CR-95 AC5) and CR-94. 64 never clears a flag. | [Team decision] |
| Deactivation reason | Controlled list `permanently_closed`, `long_term_renovation`, `other`, plus a note, required for `other`. | [Team decision] |
| Reactivation and existing flags | Flags stay; reactivation only restores the venue's visibility. Resolution is the coordinator's, as with VC-R2. | [Team decision] |
| Which bookings are flagged | Occupying `held` or `approved` bookings that have not ended (`upper(occupied_period) > now()`) and have no flag yet. `re_review` bookings are left alone: AC3 names held and approved only, and a re-review is already a follow-up in progress. | [Assumption] |
| Events in Safety review or Confirmed | Returned to Planning through `return_to_planning(event_id, reason_code="arrangement_flagged")` (CR-104 AC10, CR-95 AC7). | Contract from CR-104 |
| Preview before save | Same pattern as the SCRUM-63 edit: without `confirm`, return the bookings that would be flagged and write nothing. | [Team decision] |

## 3. Data (one migration)

**Venues**
- Enum `public.venue_inactive_reason`: `permanently_closed`, `long_term_renovation`, `other`.
- `venues.inactive_reason venue_inactive_reason null`, `venues.inactive_note varchar(500) null`.
- Check: `is_active` ⇒ reason and note are null; `not is_active` ⇒ reason is not null; reason `other` ⇒ note is not blank. Existing inactive rows (if any on the live project) must be checked before the constraint is added; backfill `other` with note "Deactivated before reasons were recorded" if any exist.

**Bookings (the CR-94 / CR-95 contract)**
- Enum `public.venue_booking_flag`: `affected`, `conflict`, `unsuitable`.
- `venue_bookings.flag venue_booking_flag null`, `flag_reason text null`, `flagged_at timestamptz null`.
- Check: the three are all null or all set; `flag_reason` not blank when set.

**Functions** (all `security definer`, `set search_path = ''`, execute revoked from `public`, `anon`, `authenticated`, granted to `service_role`)

- `public.flag_venue_bookings(p_venue_id uuid, p_period tstzrange, p_flag venue_booking_flag, p_reason text, p_message text) returns setof uuid`
  - Flags every `held`/`approved` booking at the venue whose `occupied_period` overlaps `p_period`, has not ended, and has `flag is null`.
  - Inserts one notification per affected event to its assigned coordinator, type `venue_booking_affected`, message `p_message`.
  - Returns the distinct event ids it flagged.
  - CR-95 calls it with the block's period; 64 calls it with `[now(), infinity)`.
- `public.deactivate_venue(p_venue_id uuid, p_actor_id uuid, p_version integer, p_reason venue_inactive_reason, p_note text, p_before jsonb, p_after jsonb, p_flag_reason text, p_message text) returns table (outcome text, event_ids uuid[])`
  - Locks the venue row. Outcomes: `venue_not_found`, `already_inactive`, `stale` (version mismatch), `ok`.
  - On `ok`: sets `is_active = false`, the reason and note, `updated_by`, bumps `version`; inserts the `venue_edit_history` row; calls `flag_venue_bookings`; returns the flagged event ids.
- `public.reactivate_venue(p_venue_id uuid, p_actor_id uuid, p_version integer, p_before jsonb, p_after jsonb) returns text`
  - Outcomes `venue_not_found`, `already_active`, `stale`, `ok`. On `ok`: `is_active = true`, reason and note cleared, `updated_by`, `version` bumped, history row. Flags untouched.
- `public.request_venue_booking`: new outcome `venue_inactive`, checked after `venue_not_found`.
- `public.safety_approve_event`: its locked recheck also refuses when any active booking has `flag is not null` (same refusal outcome as an unapproved booking).

RLS: the new columns sit on tables that are already deny-by-default; no new policies. Advisors are run after the migration.

## 4. API (venues module)

Both endpoints use `VenueStaffOnly` (active role `venue_staff`).

**`POST /api/v1/venues/{venue_id}/deactivate`**
- Request `VenueDeactivateRequest`: `reason: VenueInactiveReason`, `note: str | None` (max 500; required and non-blank for `other`, else 422), `version: int`, `confirm: bool = False`.
- Response `VenueDeactivateResponse`: `saved: bool`, `venue: VenueDetail | None`, `affected: list[AffectedBooking]` where `AffectedBooking` = `booking_id, event_id, event_name, period, status`.
- Without `confirm`, if any booking would be flagged: `saved=false`, `affected` filled, nothing written. Otherwise the RPC runs.
- After `ok`, the service calls `events_service.return_to_planning(event_id, reason_code="arrangement_flagged")` for each returned event id. It is a no-op for events not in Safety review or Confirmed.
- Errors: 404 unknown venue; 409 already inactive; 409 stale version ("reload and retry", as SCRUM-63); 422 invalid body.
- **Known gap:** if `return_to_planning` raises `EventServiceUnavailableError` (503), the venue is already deactivated and the booking flagged, so the event cannot be approved (the approval recheck refuses flags) and its coordinator has been notified. The service logs a warning and still returns `saved: true`, because the deactivation committed. No retry logic.

**`POST /api/v1/venues/{venue_id}/reactivate`**
- Request `VenueReactivateRequest`: `version: int`. Response `VenueDetail`.
- Errors: 404; 409 already active; 409 stale.

**Read models**
- `VenueSummary` / `VenueDetail` gain `inactive_reason` and `inactive_note`.
- History snapshots (`_snapshot`) gain `is_active`, `inactive_reason`, `inactive_note`.
- `venues.service.booking_statuses_by_event` (or a sibling returning `{status, flag}`) feeds `BookingReadiness(status, flags=[flag] if flag else [])` in `events.service._safety_readiness_for`.
- Booking request refusal `venue_inactive` → 409 "This venue is inactive."

## 5. UI

**`VenueDetailView`** (buttons only when the active role is `venue_staff`, as `canEdit`):
- "Deactivate venue" next to "Edit venue"; "Reactivate venue" instead on an inactive venue.
- Inactive banner: "Inactive: <reason label>" plus the note.
- History tab: `summariseEditHistoryEntry` shows the change as field rows: Status (Active → Inactive), Inactive reason and Inactive note.

**`components/venues/DeactivateVenueModal.vue`** (modelled on `ReturnEventModal`):
- Reason select and note (required for Other).
- First submit sends without `confirm`. If `affected` comes back, the modal lists each booking (event, period, held/approved) with "These bookings will be flagged Affected and their coordinators notified", and offers "Deactivate anyway".
- 409 stale: show the message and reload the venue.

Reactivate uses `ConfirmModal`. API calls and state live in `venueEditStore`. The venue staff dashboard needs no change. The coordinator sees the existing readiness message "A venue booking is flagged Affected." and the notification; the "Needs alternative venue" alert is CR-95's.

## 6. Tests

**Backend (`pytest`)**
- Deactivate: preview writes nothing; confirm calls the RPC; no bookings saves straight away; `other` without a note → 422; already inactive → 409; stale → 409; unknown → 404; `return_to_planning` called for exactly the returned event ids.
- Reactivate: happy path; already active → 409; stale → 409.
- Access: 403 for every non-venue-staff role, and for an account holding `venue_staff` while acting as coordinator (SCRUM-76).
- Booking request on an inactive venue → 409.
- Readiness: a flagged booking blocks send for safety check (82 AC10).
- Full suite passes; 100% of new and changed code covered.

**Database (`supabase/verification/venue_deactivation_checks.sql`, rolled back, run live)**
- Deactivation flags only not-yet-ended held/approved unflagged bookings; skips ended, `re_review` and already-flagged ones; one notification per event; history row written.
- Reactivation leaves flags; constraints reject invalid reason/note and partial flags.
- `safety_approve_event` refuses a flagged booking; `request_venue_booking` refuses an inactive venue.
- `anon` / `authenticated` cannot execute the new functions.

**Frontend (Vitest):** the modal's preview → confirm steps; Other requires a note; buttons gated on active role; banner; history summary.

**Live checks:** `verify_live.py` deactivates and reactivates a throwaway venue it creates and deletes (seeded venues untouched); e2e drives the same as venue staff and proves a coordinator gets 403 on the raw endpoint.

**Manual (developer):** new `TC-VEN-0xx` cases — modal at phone width, banner wording, the coordinator's notification text.

## 7. AC trace

| AC | Satisfied by |
|---|---|
| AC1 | `deactivate_venue`, reason enum + note, modal; deactivate tests and live check |
| AC2 | existing search rule + `venue_inactive` refusal; booking-request test, DB check |
| AC3 | `flag_venue_bookings`, notifications, `return_to_planning`, readiness and approval rechecks; DB checks, service tests |
| AC4 | `reactivate_venue`, button; reactivate tests, live check, search test on a reactivated venue |

## 8. Notes and follow-ups

- **Estimate:** 1 SP was proposed before 64 took on the flag contract. Suggest re-estimating at stand-up.
- **Heads-up for Xuan Wei (CR-95) and CR-94:** the flag columns, `flag_venue_bookings`, notification type `venue_booking_affected`, the "first flag stays" rule, clearing is theirs, and `arrangement_flagged` for `return_to_planning`. CR-95 rebases onto 64's migration and does not add its own flag migration. A paste-ready note goes in the final report, and the contract goes in `docs/IMPLEMENTATION_MAP.md`.
- Docs: REQUIREMENTS §6.8 (VC-R1 reason rule and the decisions in §2), IMPLEMENTATION_MAP, BUILD_LOG, `docs/test-cases/`.
