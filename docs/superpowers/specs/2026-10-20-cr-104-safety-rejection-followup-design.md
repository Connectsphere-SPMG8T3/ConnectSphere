# CR-104 follow-up: after a safety rejection — design

_2026-10-20 · branch `fix/cr-104-safety-rejection-followup` · defects D51, D52, D53 · owner Jie Ching_

## Why

Sprint review comment on CR-104 (Done): "May need to revise after safety officer rejects, how can coordinator readjust arrangements and resend, decision history should show the affected venues."

A rejection (CR-104 AC3) flags one approved booking `safety_rejected` and returns the event to Planning. Today the coordinator then has only **Mark as revised**, which clears the flag and records nothing. Two real cases follow a rejection, and neither is served:

1. **The venue really doesn't suit.** The coordinator needs another venue. CR-95's replacement request accepts only an `affected` booking, and cancelling a booking (85) isn't built, so there is no path at all. → **D51**
2. **The Safety Officer misunderstood, or the coordinator fixed it with venue staff.** The coordinator keeps the venue, but Mark as revised carries no explanation, so on re-review the Safety Officer can't see what changed. → **D53**

And the decision history shows "Affected bookings: 1", not which venue or equipment a decision was about. → **D52**

This is a fix branch, not a reopened story (developer's decision, 20/10).

## Acceptance criteria

- **F1 (D53).** Marking a Safety-rejected booking revised requires a response note (1–1,000 characters after trimming). The note is stored on the `safety_revised` booking-history row with who and when.
- **F2 (D52, D53).** Each safety decision in the history names the venues and equipment it concerns, and the venue it rejected; a rejection also shows the coordinator's response note, who wrote it and when, once the booking was marked revised. Shown wherever `SafetyDecisionDetails` is used (Safety Officer review, Safety dashboard, coordinator event page).
- **F3 (D51).** The assigned coordinator, acting as coordinator, with the event in Planning, can request a replacement for a Safety-rejected booking from the rejected-venue notice, through CR-95's existing replacement request. When venue staff approve the replacement, the rejected booking is released, as for an Affected booking.
- **F4.** While a replacement for a Safety-rejected booking is pending, Mark as revised is refused (409) and hidden; the notice says a replacement was requested and names its venue.
- **F5.** Readiness is unchanged: a `safety_rejected` booking is not ready, so the event can't be sent for safety check again until it is marked revised or its replacement is approved and releases it.
- **F6.** Every new or changed endpoint keeps the active-role and assignment rules: anyone other than the assigned coordinator acting as coordinator gets 403 (or 404 where the existing endpoint already answers 404 for an unrelated caller), proved by a raw request.

## Design

### 1. Mark as revised with a response note (F1, F4)

**Database (new migration).**
- `venue_booking_history.note text null`, with a check `note is null or length(btrim(note)) between 1 and 1000`.
- Replace `public.mark_safety_revision(p_booking_id uuid, p_actor_id uuid)` with `public.mark_safety_revision(p_booking_id uuid, p_actor_id uuid, p_note text) returns text` (drop the two-argument version). Same locks and order (event, then booking), same outcomes (`ok`, `booking_not_found`, `not_safety_rejected`, `not_assigned`, `not_planning`), plus:
  - `note_required` when `p_note` is null or blank after trimming;
  - `replacement_pending` when a booking with `replaces_booking_id = p_booking_id` is `held`, `approved` or `re_review`.
- On `ok` the history row stores `btrim(p_note)`. Security definer, empty search path, `service_role` only, as now.

**API.** `POST /api/v1/venue-bookings/{booking_id}/mark-revised` takes a body `SafetyRevisionRequest {note: str}` (trimmed, 1–1,000; blank or longer → 422 before the RPC). `replacement_pending` → 409 "A replacement venue has been requested for this booking." Other outcomes map as today. Response unchanged (`VenueBookingDetail`).

**SPA.** `SafetyRejectedNotice`'s **Mark as revised** opens a dialog asking "What changed, or what should the Safety Officer know?" with a required textarea (1,000 max, counter), **Mark as revised** and **Cancel**. The store action sends `{note}`. Booking history (`BookingRequestView`) shows the note under a "Marked revised" row.

### 2. Replace a Safety-rejected venue (F3, F4, F5)

**Database (same migration).**
- Both booking-request functions (`request_venue_booking`, `request_venue_booking_for_space`, latest bodies) accept a replaced booking whose flag is `affected` **or** `safety_rejected`; every other replacement rule is unchanged. Recreate them from their live bodies, changing only that condition.
- `venue_bookings_one_active_per_space` (and the event-level equivalent, if one exists live) excludes both flags: `flag is null or flag not in ('affected', 'safety_rejected')`. Verify the live index definitions first.
- `release_replaced_booking` is unchanged (it doesn't check the flag; confirm). `restore_affected_booking` stays Affected-only: restoring is about the venue becoming free, which doesn't apply to a safety rejection.

**API.** `venues.service._prepare_replacement` accepts either flag. The event is already in Planning after a rejection, so no return to planning happens.

**SPA.**
- `SafetyRejectedNotice` gains **Replace venue** (shown when the event is in Planning), opening `replacementSearchRoute(event, space, booking)`, as the Affected notice does.
- `safetyRejectedPanelState` finds a pending replacement (`replaces_booking_id` = this booking, status held/approved/re_review) and returns a state that shows "Replacement requested: <venue>" and no Mark as revised, reusing the `replacing` presentation where possible.

### 3. Named decision history (F2)

**API.** `SafetyDecision` keeps its id lists and adds:
- `affected_bookings: list[{booking_id, venue_name}]`
- `affected_equipment: list[{id, equipment_name}]`
- `rejected_venues: list[{venue_id, venue_name}]`
- `revision: {note, by_name, at} | None` — for an `arrangement_rejected` decision, the first `safety_revised` history row with a note on its rejected booking after `decided_at`.

Built in `events.service` for both `safety_decisions` and `safety_review`, with one lookup per kind (no per-row queries). A name that can't be found is `null`, not an error.

**SPA.** `SafetyDecisionDetails` replaces the counts with "Rejected venue: …", "Concerns: Heritage Hall · Projector" (falling back to "a booking that no longer exists" for a null name) and, under a rejection, "Coordinator's response: <note>" with name and time.

## Edge cases

- Mark revised with a blank or whitespace note → 422 (API) / `note_required` (database), nothing changed.
- Mark revised after a replacement was requested → 409; a replacement that was later rejected or expired no longer blocks it.
- A replacement request naming a Safety-rejected booking of another event or space → existing "That booking is not waiting for a replacement." (409).
- Two replacement requests for one rejected booking → the second refused by the one-live-booking index, as for Affected.
- Decisions recorded before this change have no response note and show none.
- An `affected` booking that is later Safety-rejected can't happen (the rejection requires an unflagged booking); a `safety_rejected` booking can't be flagged Affected later (first flag wins).

## Testing

- **pytest:** request body validation; every new outcome mapping; replacement accepted for `safety_rejected`; decision enrichment (names, null names, revision lookup, no N+1); active-role and assignment denials on both endpoints.
- **SQL (rolled back), `supabase/verification/safety_decision_checks.sql`:** note required and stored; `replacement_pending`; replacement allowed for `safety_rejected` and still refused for other flags; index allows the replacement beside the rejected booking but not two replacements; release on approval.
- **Vitest:** notice buttons by state; revise dialog; panel state with a pending replacement; named history and fallbacks.
- **Live (`verify_live.py`):** reject → mark revised with note → history shows it; reject → replace → approve → original released → event can be sent again. On throwaway events only.
- **Browser (`e2e`):** reject → Replace venue from the notice → replacement shows as requested.
- **Manual:** dialog and notice wording, history readability, 375 px.

## Decisions for the PO

- **[Team decision]** A rejected venue is replaced through CR-95's replacement request rather than waiting for 85's cancel, which AC3 names. Reason: 85 isn't built and the coordinator otherwise has no path.
- **[Team decision]** The response note is required, so the Safety Officer always sees why the event came back.

## Out of scope

- Editing a booking's arrangement details (layout, attendance, setup) from the notice: 37 and CR-100 own those.
- Cancelling a booking (85).
- Notifying the Safety Officer when a booking is marked revised: they see it on re-review (existing [Assumption] in `mark_safety_revision`).
