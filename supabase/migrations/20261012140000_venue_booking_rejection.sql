-- =============================================================================
-- ConnectSphere - SCRUM-38 venue staff reject a booking request
--
-- Venue staff reject a `held` booking with a required reason and an optional
-- suggested alternative (REQUIREMENTS 6.13). The booking keeps the current
-- decision; CR-99's venue_booking_history keeps the trail (AC12), which this
-- migration extends with the reason and the suggestion.
--
-- Depends on CR-99 (20261012120000, 20261012120001: the `expired` status,
-- venue_booking_history and lock_hold_for_approval), which is applied to the
-- live project but not yet in the repository.
--
-- reject_venue_booking is API-only (ADR-0002): the API checks the active role,
-- and the function decides under CR-99's lock on the booking row, so a
-- rejection racing an approval or the expiry job is refused rather than
-- overwritten (AC10).
-- =============================================================================

alter table public.venue_bookings
    add column suggestion_note text null,
    add column decided_by uuid null,
    add column decided_at timestamptz null,
    add constraint venue_bookings_decided_by_fkey
        foreign key (decided_by) references public.profiles (id) on delete set null,
    -- AC2, AC3: 1-1000 characters after trimming, like the other free-text fields.
    add constraint venue_bookings_decision_reason_length
        check (decision_reason is null or length(btrim(decision_reason)) between 1 and 1000),
    add constraint venue_bookings_suggestion_note_length
        check (suggestion_note is null or length(btrim(suggestion_note)) between 1 and 1000);

create index venue_bookings_decided_by_idx on public.venue_bookings (decided_by);

comment on column public.venue_bookings.decision_reason is
    'Why venue staff rejected the booking (SCRUM-38). Shown to the assigned coordinator, never to organisers or attendees.';
comment on column public.venue_bookings.suggestion_note is
    'Optional alternative venue or arrangement suggested on rejection (SCRUM-38). A note only: it holds nothing.';
comment on column public.venue_bookings.decided_by is
    'Who made the latest venue-staff decision on the booking (SCRUM-38; SCRUM-36 for approval).';
comment on column public.venue_bookings.decided_at is
    'When the latest venue-staff decision was made.';

-- AC12: the history records why, not only what changed.
alter table public.venue_booking_history
    add column reason text null,
    add column suggestion_note text null,
    add constraint venue_booking_history_reason_length
        check (reason is null or length(btrim(reason)) between 1 and 1000),
    add constraint venue_booking_history_suggestion_note_length
        check (suggestion_note is null or length(btrim(suggestion_note)) between 1 and 1000);

comment on column public.venue_booking_history.reason is
    'Why the change was made, where the action takes one (a rejection, SCRUM-38).';
comment on column public.venue_booking_history.suggestion_note is
    'The alternative suggested with a rejection (SCRUM-38).';

create or replace function public.reject_venue_booking(
    p_booking_id uuid,
    p_actor_id uuid,
    p_reason text,
    p_suggestion text,
    p_notify_message text
)
returns table (outcome text, event_id uuid, from_status public.venue_booking_status)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_reason text := nullif(btrim(p_reason), '');
    v_suggestion text := nullif(btrim(p_suggestion), '');
    v_lock text;
    v_booking public.venue_bookings;
    v_coordinator uuid;
begin
    -- AC2, AC3: the API validates these too; the function never trusts it.
    if v_reason is null or length(v_reason) > 1000 then
        return query select 'invalid_reason'::text, null::uuid, null::public.venue_booking_status;
        return;
    end if;
    if v_suggestion is not null and length(v_suggestion) > 1000 then
        return query select 'invalid_suggestion'::text, null::uuid, null::public.venue_booking_status;
        return;
    end if;

    -- AC9, AC10: CR-99's guard locks the booking row for the rest of this
    -- transaction, and expires a hold already past its expiry. Approval
    -- (SCRUM-36) and the expiry job take the same lock, so whichever decides
    -- first wins and the others see its outcome. It is named for approval but
    -- answers the same question a rejection needs: is this still a live hold?
    v_lock := public.lock_hold_for_approval(p_booking_id);
    if v_lock = 'booking_not_found' then
        return query select 'booking_not_found'::text, null::uuid, null::public.venue_booking_status;
        return;
    end if;

    select * into v_booking from public.venue_bookings vb where vb.id = p_booking_id;
    if v_lock = 'hold_expired' then
        return query select 'hold_expired'::text, v_booking.event_id, 'expired'::public.venue_booking_status;
        return;
    end if;
    if v_lock <> 'ok' then
        return query select 'not_held'::text, v_booking.event_id, v_booking.status;
        return;
    end if;

    -- AC4, AC5: rejected no longer occupies the slot (DB-1 counts held,
    -- approved and re_review only), so the hold leaves the calendar at once.
    update public.venue_bookings vb
    set status = 'rejected',
        decision_reason = v_reason,
        suggestion_note = v_suggestion,
        decided_by = p_actor_id,
        decided_at = now(),
        updated_at = now()
    where vb.id = p_booking_id;

    -- AC12.
    insert into public.venue_booking_history
        (booking_id, actor_id, action, from_status, to_status, old_expires_at, new_expires_at, reason, suggestion_note)
    values (p_booking_id, p_actor_id, 'rejected', 'held', 'rejected', v_booking.expires_at, v_booking.expires_at,
            v_reason, v_suggestion);

    -- AC4: the event's assigned coordinator is told, in this transaction
    -- (NT-R3), never the actor (NT-R1). The message carries no reason: it is
    -- read on the event or booking page.
    select e.coordinator_id into v_coordinator from public.events e where e.id = v_booking.event_id;
    if v_coordinator is not null and v_coordinator <> p_actor_id then
        insert into public.notifications (recipient_id, event_id, type, message)
        values (v_coordinator, v_booking.event_id, 'venue_booking_rejected', p_notify_message);
    end if;

    return query select 'ok'::text, v_booking.event_id, 'held'::public.venue_booking_status;
end;
$$;

comment on function public.reject_venue_booking is
    'Venue staff reject a held booking with a reason and optional suggestion (SCRUM-38); records history and notifies the assigned coordinator. Returns an outcome code instead of raising. API-only.';

revoke execute on function public.reject_venue_booking(uuid, uuid, text, text, text) from public, anon, authenticated;
grant execute on function public.reject_venue_booking(uuid, uuid, text, text, text) to service_role;
