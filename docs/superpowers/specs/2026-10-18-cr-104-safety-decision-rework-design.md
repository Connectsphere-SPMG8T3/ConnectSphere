# CR-104 safety decision rework (after Session 3) — design

**PBI:** CR-104, Product backlog row 71 (ACs rewritten 17/10 after CR-104-R was merged back in). **Branch:** `feature/cr-104-safety-decision-rework`. **Kind:** story rework, not a defect fix: PR #50 met the 9 Oct ACs; Session 3 (QA3-2, QA3-3, QA3-16, QA3-46, QA3-47) changed AC1–AC4 and AC6. AC5 and AC7–AC10 are unchanged and must stay green.

Rules: `docs/REQUIREMENTS.md` §6.6.1 SF-R3, SF-R4, SF-R6; LC-R7; §9 item 33. Out of scope: the checklist and organiser-visible comments (CR-108), pick-up and officer access (CR-107), the `preparation` status (68 AC8), cancelling a booking (85).

## Decisions taken in brainstorming (18/10)

1. **Revise path = "Mark as revised".** A Safety-rejected booking blocks readiness, so the coordinator needs a way out. The assigned coordinator, acting as Event Coordinator, marks the booking revised while the event is in Planning; that clears the flag. Replacing the venue waits for 85 (cancel) plus a normal new request. **[Team decision]**, recorded in REQUIREMENTS §6.6.1 and §9 item 33.
2. **`preparation` stays with 68 AC8.** CR-104 adds a tested TODO so `approved_change` accepts `preparation` once it exists. AC6 is reported as partly blocked on 68.
3. **Reject names exactly one venue booking** and no equipment lines. Request changes keeps its optional booking/equipment ids, recorded only as "the arrangements this concerns".
4. `docs/DEVELOPMENT_WORKFLOW.md:34` is left as it is.

## AC → behaviour

| AC | Behaviour after the rework |
|----|----------------------------|
| AC1 | Unchanged approve → `confirmed`, same notifications. No UI or doc copy calls Confirmed "the Preparation stage" (none found on 18/10; re-grep at the end). |
| AC2 | `changes_requested`: event → `planning`, coordinator notified, decision row recorded with the concerned ids. **No `venue_bookings` or `equipment_requests` row changes.** |
| AC3 | `arrangement_rejected`: exactly one booking id, which must be one of the event's own `approved`, unflagged bookings. That booking gets `flag='safety_rejected'`, `flag_reason` = the officer's reason, `flagged_at=now()`, and a `venue_booking_history` row. Status unchanged (not released). Event → `planning`; coordinator notified; decision row stores the booking id and its venue in `rejected_venue_ids`. The coordinator sees "Safety rejected" and the reason on that booking. |
| AC4 | Readiness (82) reports "flagged Safety rejected" for that booking only. Other spaces' bookings are untouched, so they stay ready. After Mark as revised the event can be sent again. |
| AC5 | Unchanged (only `safety_approve` reaches `confirmed`). |
| AC6 | `approved_change` sources stay `{confirmed}`; a test pins this with a TODO naming 68 AC8. |
| AC7–AC10 | Unchanged; existing tests stay green. |

## Components

**Database — new migration `supabase/migrations/20261018150000_cr104_safety_decision_rework.sql`**
- `alter type public.venue_booking_flag add value 'safety_rejected'`. Additive: CR-95 replacement and restore still accept only `affected`; `flag_venue_bookings` skips any flagged booking (first flag wins). Update the column comment on `venue_bookings.flag`.
- `create or replace function public.safety_return_event(...)`, same signature and grants. Version and lock behaviour as today. Returns no row (→ API 409) when the reject booking rule fails.
- New `public.mark_safety_revision(p_booking_id uuid, p_actor_id uuid) returns text`, security definer, API-only (service_role execute). Outcomes: `ok`, `booking_not_found`, `not_safety_rejected`, `not_planning`, `not_assigned`. Clears flag, flag_reason and flagged_at, writes a `venue_booking_history` row (`action='safety_revised'`, actor). No notification **[Assumption]**.
- Note: `alter type ... add value` cannot be used in the same transaction as the new value. The functions are plpgsql (resolved at run time), so defining them in the same migration is fine; no statement in the migration may *use* `'safety_rejected'` as a literal outside a function body.

**Backend**
- `events/schemas.py`: `SafetyRejectRequest` becomes `{reason: str (1–1000, stripped), booking_id: UUID}`; it no longer inherits `SafetyArrangementIds`.
- `events/service.py`: reject passes `[booking_id]` and `[]`; it raises `UnknownEventArrangementError` (422) when the booking is not the event's. A RPC no-row result → 409 with a message saying the booking can't be rejected (not approved, already flagged) or the event changed. `_SAFETY_LABELS["arrangement_rejected"]` no longer says "must be replaced".
- `events/readiness.py`: `FLAG_LABELS["safety_rejected"] = "Safety rejected"`.
- `events/lifecycle.py`: comments for AC2/AC3; `approved_change` unchanged with a TODO(68 AC8).
- `venues`: `POST /venue-bookings/{booking_id}/mark-revised`, active role `event_coordinator` only, returns `VenueBookingDetail`. 404 / 403 (not assigned) / 409 (not safety rejected, not planning).

**Frontend**
- `SafetyReviewView.vue`: Reject needs one venue chosen with a radio group; Request changes keeps optional checkboxes headed "Arrangements this concerns (optional)". New dialog copy (see plan).
- `features/venues/bookingRequest.js`: `venuePanelState` returns `{kind: "safety-rejected", booking, reason, canMarkRevised}` for a live booking flagged `safety_rejected` (checked before `affected`).
- New `components/venues/SafetyRejectedNotice.vue` (badge "Safety rejected", reason, "Mark as revised" button), rendered on the per-space panels and the single-venue panel of `CoordinatorEventView.vue`.
- `services/api.js`: `markSafetyRevision(bookingId, token)`.

## Error handling
- Reject with zero/two ids is impossible at the schema level (single `booking_id`). A foreign id → 422. A held, re_review, released or already-flagged booking → 409, no change.
- Mark revised races (event leaves planning, flag cleared twice) resolve inside the RPC under a row lock; the second caller gets 409.

## Known edges (recorded, not fixed)
- A Safety-rejected booking whose venue is later deactivated or blocked is not also flagged Affected (first flag wins). Record in IMPLEMENTATION_MAP.
- Replacing a Safety-rejected venue is not possible until 85 lands, because the booking still holds the space's active slot.

## Testing
pytest (service, schemas, readiness, lifecycle, the new endpoint's role/assignment denials), `supabase/verification/safety_decision_checks.sql` rewritten for the new AC2/AC3 behaviour plus mark-revised, Vitest (view, notice, panel state), `verify_live.py` checks for the new automatable cases, and manual cases for copy and layout. Test cases TC-SDEC-010 and TC-SDEC-011 are rewritten for the new behaviour; new cases from TC-SDEC-022.
