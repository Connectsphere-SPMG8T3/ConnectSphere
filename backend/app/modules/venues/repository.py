"""All Supabase access for the venues module.

This is the module's only I/O seam (REQUIREMENTS §3.3 `repository.py`); the
service and the search rules never see a Supabase client. Tests patch the
functions here. Reads use the secret-key admin client, so callers must
already have passed the role check in the router.
"""

import re
from collections.abc import Iterable
from datetime import datetime, timezone

from postgrest.exceptions import APIError

from app.db.supabase import get_supabase_admin_client
from app.modules.venues.schemas import (
    BlockAffectedBooking,
    BlockSummary,
    BookingSummary,
    Editor,
    Occupant,
    Period,
    VenueProfile,
    VenueStaffBlock,
    VenueStaffBooking,
    VenueSummary,
    parse_occupied_datetime,
)
from app.modules.venues.search import OCCUPYING_STATUSES

_VENUE_COLUMNS = (
    "id, name, location, capacity, accessibility_features, opens_at, closes_at, is_active, description, "
    "inactive_reason, inactive_note, setup_minutes, turnaround_minutes, emergency_access, restrictions, "
    "venue_layouts(layout, capacity_for_layout), venue_facilities(facility)"
)

# The profile page additionally shows when the venue was last updated and by
# whom (SCRUM-67 AC2). The embed names its constraint even though `venues` has
# only one foreign key to `profiles` today: a second one (an owner, a creator)
# would otherwise break this query with PGRST201 rather than the new column.
_VENUE_PROFILE_COLUMNS = (
    _VENUE_COLUMNS + ", updated_at, updated_by, version, profiles!venues_updated_by_fkey(id, full_name)"
)

# PostgREST renders a tstzrange as e.g. ["2026-10-10 06:00:00+00","2026-10-10 09:00:00+00")
_RANGE_PATTERN = re.compile(r'^[\[(]"?([^",]+)"?,"?([^")\]]+)"?[)\]]$')


def _parse_range(value: str) -> Period:
    match = _RANGE_PATTERN.match(value)
    if match is None:
        raise ValueError(f"Unrecognised range literal from PostgREST: {value!r}")
    return Period(starts_at=parse_occupied_datetime(match.group(1)), ends_at=parse_occupied_datetime(match.group(2)))


def _range_literal(period: Period) -> str:
    return f"[{period.starts_at.isoformat()},{period.ends_at.isoformat()})"


def _open_ended_literal(since: datetime) -> str:
    """`[since,)` — everything from `since` onwards, with no upper bound.

    Overlapping this range is exactly "ends after `since`" for the bounded
    half-open ranges this schema stores, and it is answered by the same GiST
    index, so the filter runs in Postgres instead of in Python. Built by hand
    rather than through `_range_literal` because `Period` requires both ends
    and so cannot express an unbounded one.
    """
    return f"[{since.isoformat()},)"


def _to_one_embed(row: dict, key: str) -> dict | None:
    """Read a to-one PostgREST embed, whichever way it arrived.

    A to-one embed normally comes back as a dict, but PostgREST falls back to a
    one-element list when it cannot prove the relationship is to-one. Accept
    both rather than guessing.
    """
    embedded = row.get(key)
    if isinstance(embedded, list):
        embedded = embedded[0] if embedded else None
    return embedded or None


def _embedded_venue_name(row: dict) -> str:
    """The `venues(name)` embed. Degrades to "" rather than raising — a missing
    name should cost one label, not the whole dashboard."""
    return (_to_one_embed(row, "venues") or {}).get("name", "")


def _to_editor(row: dict) -> Editor | None:
    """Who last edited the venue (SCRUM-67 AC2), or None when nothing recorded it.

    Falls back to `venues.updated_by` when the `profiles` embed is empty, which
    happens if the editor's row is not readable: the id is still a truer answer
    than claiming nobody edited it.
    """
    profile = _to_one_embed(row, "profiles")
    if profile:
        return Editor(id=profile["id"], full_name=profile.get("full_name"))
    editor_id = row.get("updated_by")
    return Editor(id=editor_id) if editor_id else None


def _to_venue(row: dict) -> VenueSummary:
    return VenueSummary(
        id=row["id"],
        name=row["name"],
        location=row["location"],
        capacity=row["capacity"],
        layouts=row.get("venue_layouts") or [],
        facilities=[f["facility"] for f in row.get("venue_facilities") or []],
        accessibility_features=row.get("accessibility_features") or [],
        opens_at=row["opens_at"],
        closes_at=row["closes_at"],
        is_active=row["is_active"],
        description=row.get("description"),
        setup_minutes=row.get("setup_minutes", 0),
        turnaround_minutes=row.get("turnaround_minutes", 0),
        emergency_access=row.get("emergency_access"),
        restrictions=row.get("restrictions"),
        inactive_reason=row.get("inactive_reason"),
        inactive_note=row.get("inactive_note"),
    )


def list_venues() -> list[VenueSummary]:
    """Every venue, active or not, with its layouts and facilities embedded.
    The search rules decide what an inactive venue means (VC-R1)."""
    response = get_supabase_admin_client().table("venues").select(_VENUE_COLUMNS).order("name").execute()
    return [_to_venue(row) for row in response.data or []]


def get_venue(venue_id: str) -> VenueProfile | None:
    """One venue with the audit stamp its profile page shows (SCRUM-67)."""
    response = (
        get_supabase_admin_client()
        .table("venues")
        .select(_VENUE_PROFILE_COLUMNS)
        .eq("id", venue_id)
        .maybe_single()
        .execute()
    )
    row = response.data if response else None
    if not row:
        return None
    return VenueProfile(
        **_to_venue(row).model_dump(),
        updated_at=row["updated_at"],
        updated_by=_to_editor(row),
        version=row.get("version", 0),
    )


def update_venue(
    venue_id: str,
    actor_id: str,
    expected_version: int,
    *,
    name: str,
    location: str,
    capacity: int,
    opens_at,
    closes_at,
    description: str | None,
    accessibility_features: list[str],
    layouts: list[dict],
    facilities: list[str],
    before: dict,
    after: dict,
    notifications: list[dict],
    flags: list[dict],
) -> tuple[VenueProfile, list[str]] | None:
    """Run `public.update_venue`: the version-checked update, the layouts/
    facilities replace, the history row, any affected-booking notifications,
    and the Unsuitable flags (CR-94, through `flag_venue_bookings`), all in
    one transaction (SCRUM-63). Returns the saved profile with the ids of the
    events it newly flagged, or None when the venue had moved on (lost the
    race), which the service reports as 409.
    """
    response = (
        get_supabase_admin_client()
        .rpc(
            "update_venue",
            {
                "p_venue_id": venue_id,
                "p_actor_id": actor_id,
                "p_expected_version": expected_version,
                "p_name": name,
                "p_location": location,
                "p_capacity": capacity,
                "p_opens_at": opens_at.isoformat() if hasattr(opens_at, "isoformat") else opens_at,
                "p_closes_at": closes_at.isoformat() if hasattr(closes_at, "isoformat") else closes_at,
                "p_description": description,
                "p_accessibility_features": accessibility_features,
                "p_layouts": layouts,
                "p_facilities": facilities,
                "p_before": before,
                "p_after": after,
                "p_notifications": notifications,
                "p_flags": flags,
            },
        )
        .execute()
    )
    result = response.data if response else None
    if not result:
        return None
    return get_venue(venue_id), result["flagged_event_ids"]


def list_flaggable_bookings(venue_id: str, since: datetime) -> list[BookingSummary]:
    """Held or approved bookings on the venue that end after `since` and carry
    no flag yet: exactly what `flag_venue_bookings` would flag (SCRUM-64 AC3),
    soonest first."""
    response = (
        get_supabase_admin_client()
        .table("venue_bookings")
        .select("id, event_id, booked_period, status")
        .eq("venue_id", venue_id)
        .in_("status", ["approved", "held"])
        .is_("flag", "null")
        .overlaps("occupied_period", _open_ended_literal(since))
        .execute()
    )
    bookings = [
        BookingSummary(
            id=row["id"], event_id=row["event_id"], period=_parse_range(row["booked_period"]), status=row["status"]
        )
        for row in response.data or []
    ]
    return sorted(bookings, key=lambda b: b.period.starts_at)


def deactivate_venue(venue_id: str, actor_id: str, expected_version: int, *, reason: str, note: str | None,
                     before: dict, after: dict, flag_reason: str, message: str) -> dict:
    """Run `public.deactivate_venue` (SCRUM-64): the version-checked update,
    the history row and the booking flags in one transaction. Returns
    `{outcome, event_ids}`; refusals are outcome codes, never raised."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "deactivate_venue",
            {
                "p_venue_id": venue_id,
                "p_actor_id": actor_id,
                "p_expected_version": expected_version,
                "p_reason": reason,
                "p_note": note,
                "p_before": before,
                "p_after": after,
                "p_flag_reason": flag_reason,
                "p_message": message,
            },
        )
        .execute()
    )
    row = (response.data or [])[0]
    return {"outcome": row["outcome"], "event_ids": [str(e) for e in row.get("event_ids") or []]}


def list_block_conflicts(venue_id: str, period: Period) -> list[BlockAffectedBooking]:
    """The held and approved bookings a block on `period` would affect
    (SCRUM-51 AC5, AC7, AC11), from `public.venue_conflicts`: the same check,
    on each booking's occupied window, that the trigger links by. Re-review
    bookings are not flagged by a block, and finished ones are left alone."""
    response = (
        get_supabase_admin_client()
        .rpc("venue_conflicts", {"p_period": _range_literal(period), "p_venue_id": venue_id})
        .execute()
    )
    now = datetime.now(timezone.utc)
    rows = [
        BlockAffectedBooking(booking_id=row["booking_id"], event_id=row["event_id"], status=row["booking_status"],
                             period=_parse_range(row["occupied_period"]))
        for row in response.data or []
        if row["kind"] == "booking" and row["booking_status"] in ("held", "approved")
    ]
    return [row for row in rows if row.period.ends_at > now]


def create_venue_block(venue_id: str, actor_id: str, *, period: Period, reason: str, notes: str | None,
                       history_after: dict) -> dict:
    """Run `public.create_venue_block` (SCRUM-51): the venue lock, the block,
    its history row, and (by trigger) the booking flags, links and notices in
    one transaction. Returns `{outcome, block_id}`; refusals are outcome codes."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "create_venue_block",
            {
                "p_venue_id": venue_id,
                "p_actor_id": actor_id,
                "p_starts_at": period.starts_at.isoformat(),
                "p_ends_at": period.ends_at.isoformat(),
                "p_reason": reason,
                "p_notes": notes,
                "p_history_after": history_after,
            },
        )
        .execute()
    )
    row = (response.data or [])[0]
    return {"outcome": row["outcome"], "block_id": str(row["block_id"]) if row.get("block_id") else None}


def list_block_bookings(block_id: str) -> list[BlockAffectedBooking]:
    """The bookings recorded against a block (SCRUM-51 AC6, AC10), soonest first."""
    response = (
        get_supabase_admin_client()
        .table("venue_block_bookings")
        .select("booking:venue_bookings!venue_block_bookings_booking_id_fkey(id, event_id, status, occupied_period)")
        .eq("block_id", block_id)
        .execute()
    )
    bookings = [
        BlockAffectedBooking(booking_id=b["id"], event_id=b["event_id"], status=b["status"],
                             period=_parse_range(b["occupied_period"]))
        for b in (row["booking"] for row in response.data or [])
        if b and b["status"] in ("held", "approved")
    ]
    return sorted(bookings, key=lambda b: (b.period.starts_at, b.booking_id))


def reactivate_venue(venue_id: str, actor_id: str, expected_version: int, *, before: dict, after: dict) -> str:
    """Run `public.reactivate_venue` (SCRUM-64 AC4). Returns its outcome code."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "reactivate_venue",
            {
                "p_venue_id": venue_id,
                "p_actor_id": actor_id,
                "p_expected_version": expected_version,
                "p_before": before,
                "p_after": after,
            },
        )
        .execute()
    )
    return response.data


def list_edit_history(venue_id: str) -> list[dict]:
    """Newest first. The actor is embedded through the FK named in the
    migration, like `event_status_history`'s pattern (SCRUM-63, VC-R3)."""
    response = (
        get_supabase_admin_client()
        .table("venue_edit_history")
        .select("id, before, after, created_at, actor:profiles!venue_edit_history_actor_id_fkey(id, full_name)")
        .eq("venue_id", venue_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def list_occupants(period: Period) -> dict[str, list[Occupant]]:
    """Occupying bookings and blocks that overlap `period`, keyed by venue id.

    Asks `public.venue_conflicts`, the single conflict check the request
    functions use (SCRUM-21 AC4), for every venue at once. It compares
    occupied windows (setup to turnaround) and leaves out overdue holds and
    finished bookings. A booking's `detail` is its status, a block's its
    reason; search never names the other event (REQUIREMENTS §6.14).
    """
    response = get_supabase_admin_client().rpc("venue_conflicts", {"p_period": _range_literal(period)}).execute()
    occupants: dict[str, list[Occupant]] = {}
    for row in response.data or []:
        detail = row["booking_status"] if row["kind"] == "booking" else row["block_reason"]
        occupants.setdefault(row["venue_id"], []).append(
            Occupant(kind=row["kind"], period=_parse_range(row["occupied_period"]), detail=detail)
        )
    return occupants


def list_upcoming_blocks(venue_id: str, since: datetime) -> list[BlockSummary]:
    """Blocks on one venue that end after `since`, soonest first."""
    response = (
        get_supabase_admin_client()
        .table("venue_blocks")
        .select("id, blocked_period, reason, notes")
        .eq("venue_id", venue_id)
        .execute()
    )
    # One venue carries a handful of blocks, so "still relevant" (ends after
    # `since`, which keeps in-progress ones) is decided on the parsed range.
    blocks = [
        BlockSummary(id=row["id"], period=_parse_range(row["blocked_period"]), reason=row["reason"], notes=row.get("notes"))
        for row in response.data or []
    ]
    return sorted((b for b in blocks if b.period.ends_at > since), key=lambda b: b.period.starts_at)


def list_upcoming_bookings(venue_id: str, since: datetime) -> list[BookingSummary]:
    """Occupying bookings on one venue that end after `since`, soonest first."""
    response = (
        get_supabase_admin_client()
        .table("venue_bookings")
        .select("id, event_id, event_space_request_id, booked_period, occupied_period, status")
        .eq("venue_id", venue_id)
        .in_("status", sorted(OCCUPYING_STATUSES))
        .execute()
    )
    # Shown by its booked window, but kept while its turnaround still occupies the venue.
    bookings = [
        BookingSummary(
            id=row["id"],
            event_id=row["event_id"],
            event_space_request_id=row.get("event_space_request_id"),
            period=_parse_range(row["booked_period"]),
            status=row["status"],
        )
        for row in response.data or []
        if _parse_range(row["occupied_period"]).ends_at > since
    ]
    return sorted(bookings, key=lambda b: b.period.starts_at)


# The two functions above scope to one venue and drop past rows in Python,
# which is fine for the handful of rows one venue carries. The venue-staff
# dashboard spans every venue (AUTH-R5), where that would become a full-table
# scan on every page load, so the pair below pushes the time filter into
# Postgres. Ordering by `lower(range)` cannot be expressed through PostgREST,
# so the sort stays in Python — but now on an already-filtered handful.


def list_all_upcoming_blocks(since: datetime) -> list[VenueStaffBlock]:
    """Blocks on every venue that are still relevant at `since`, soonest first.

    "Still relevant" means the block ends after `since`, which keeps one that
    is currently in progress. There is no owner filter: venue staff work as a
    pool and staff-to-venue allocation is not tracked (AUTH-R5, QA-44).
    """
    response = (
        get_supabase_admin_client()
        .table("venue_blocks")
        .select("id, venue_id, blocked_period, reason, notes, venues(name)")
        .overlaps("blocked_period", _open_ended_literal(since))
        .execute()
    )
    blocks = [
        VenueStaffBlock(
            id=row["id"],
            venue_id=row["venue_id"],
            venue_name=_embedded_venue_name(row),
            period=_parse_range(row["blocked_period"]),
            reason=row["reason"],
            notes=row.get("notes"),
        )
        for row in response.data or []
    ]
    # Tie-break on id so two blocks starting at the same instant keep a stable
    # order between requests, rather than shuffling on each load.
    return sorted(blocks, key=lambda b: (b.period.starts_at, b.id))


def list_all_upcoming_bookings(since: datetime, statuses: Iterable[str]) -> list[VenueStaffBooking]:
    """Read active requests and resolved history for every venue."""
    requested_statuses = set(statuses)
    query = (
        get_supabase_admin_client()
        .table("venue_bookings")
        # Every relationship is named because bookings have multiple venue,
        # event and profile foreign keys.
        .select(
            "id, event_id, venue_id, booked_period, status, created_at, expires_at, flag, "
            "decision_reason, suggestion_note, decided_at, "
            "venues!venue_bookings_venue_id_fkey(name), "
            "events!venue_bookings_event_id_fkey(name, coordinator:profiles!events_coordinator_id_fkey(full_name)), "
            "requester:profiles!venue_bookings_requested_by_fkey(full_name)"
        )
        .in_("status", sorted(requested_statuses))
    )
    if requested_statuses.issubset({"held", "re_review"}):
        query = query.overlaps("occupied_period", _open_ended_literal(since))
    response = query.execute()
    bookings = [
        VenueStaffBooking(
            id=row["id"],
            event_id=row["event_id"],
            venue_id=row["venue_id"],
            venue_name=_embedded_venue_name(row),
            period=_parse_range(row["booked_period"]),
            status=row["status"],
            requested_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row.get("expires_at") else None,
            flag=row.get("flag"),
            event_name=_embedded_name(row, "events", "name"),
            coordinator_name=_embedded_name(
                {"coordinator": (_embedded_relation(row, "events") or {}).get("coordinator")},
                "coordinator",
                "full_name",
            ),
            requested_by_name=_embedded_name(row, "requester", "full_name"),
            decision_reason=row.get("decision_reason"),
            suggestion=row.get("suggestion_note"),
            decided_at=datetime.fromisoformat(row["decided_at"]) if row.get("decided_at") else None,
        )
        for row in response.data or []
    ]
    return sorted(bookings, key=lambda b: (b.period.starts_at, b.id))


def list_booking_statuses(event_ids: Iterable[str]) -> list[dict]:
    """`{event_id, event_space_request_id, status, flag}` for every booking of these events, whatever its status."""
    ids = list(event_ids)
    if not ids:
        return []
    response = (
        get_supabase_admin_client()
        .table("venue_bookings")
        .select("event_id, event_space_request_id, status, flag")
        .in_("event_id", ids)
        .execute()
    )
    return response.data or []


def get_replaceable_booking(booking_id: str) -> dict | None:
    """`{id, event_id, event_space_request_id, status, flag}` for the booking a
    replacement names (CR-95 AC4), or None. The database function decides again
    under its lock; this read lets the caller refuse before it changes anything."""
    response = (
        get_supabase_admin_client()
        .table("venue_bookings")
        .select("id, event_id, event_space_request_id, status, flag")
        .eq("id", booking_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def request_booking(event_id: str, venue_id: str, actor_id: str, note: str | None, *,
                    notify_message: str, replaces_booking_id: str | None = None) -> dict:
    """Run `public.request_venue_booking` (SCRUM-19): the hold and venue staff's
    notifications in one transaction. Returns `{outcome, booking_id}`; every
    refusal is an outcome code, never a raised database error. With
    `replaces_booking_id` it replaces that affected booking (CR-95 AC4)."""
    params = {
        "p_event_id": event_id,
        "p_venue_id": venue_id,
        "p_actor_id": actor_id,
        "p_note": note,
        "p_notify_message": notify_message,
    }
    if replaces_booking_id:
        params["p_replaces_booking_id"] = replaces_booking_id
    response = get_supabase_admin_client().rpc("request_venue_booking", params).execute()
    rows = response.data or []
    return rows[0]


def request_booking_for_space(space_id: str, venue_id: str, actor_id: str, note: str | None, *,
                              notify_message: str, replaces_booking_id: str | None = None) -> dict:
    """Create a hold for one event-space request using its own period. With
    `replaces_booking_id` it replaces that space's affected booking (CR-95 AC4)."""
    params = {
        "p_event_space_request_id": space_id,
        "p_venue_id": venue_id,
        "p_actor_id": actor_id,
        "p_note": note,
        "p_notify_message": notify_message,
    }
    if replaces_booking_id:
        params["p_replaces_booking_id"] = replaces_booking_id
    response = get_supabase_admin_client().rpc("request_venue_booking_for_space", params).execute()
    rows = response.data or []
    return rows[0]


def get_active_booking(event_id: str) -> dict | None:
    """The event's occupying booking, with its venue's name; or, when it has
    none, its most recent expired hold, so the event page can say the hold ran
    out and offer the venue again (CR-99 AC7); or None."""
    response = (
        get_supabase_admin_client()
        .table("venue_bookings")
        .select("id, event_space_request_id, venue_id, status, expires_at, flag, flag_reason, replaces_booking_id, venues!venue_bookings_venue_id_fkey(name)")
        .eq("event_id", event_id)
        .in_("status", [*OCCUPYING_STATUSES, "expired"])
        .order("created_at", desc=True)
        .execute()
    )
    rows = response.data or []
    active = [row for row in rows if row["status"] in OCCUPYING_STATUSES]
    return (active or rows or [None])[0]


def list_event_booking_ids(event_id: str) -> list[dict]:
    response = (get_supabase_admin_client().table("venue_bookings").select("id")
                .eq("event_id", event_id).execute())
    return response.data or []


def list_event_bookings_with_venues(event_id: str) -> list[dict]:
    response = (get_supabase_admin_client().table("venue_bookings")
                .select("id, venue_id, status, venues!venue_bookings_venue_id_fkey(name, capacity, venue_layouts(layout), accessibility_features, emergency_access, restrictions)")
                .eq("event_id", event_id).in_("status", ["held", "approved", "re_review"]).execute())
    return response.data or []


def set_hold_expiry(booking_id: str, actor_id: str, expires_at: datetime) -> dict:
    """Run `public.set_venue_hold_expiry` (CR-99 AC2): the change and its history
    row in one transaction. Returns `{outcome, expires_at}`; every refusal is an
    outcome code, never a raised database error."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "set_venue_hold_expiry",
            {"p_booking_id": booking_id, "p_actor_id": actor_id, "p_expires_at": expires_at.isoformat()},
        )
        .execute()
    )
    return (response.data or [])[0]


# SCRUM-38. `venue_bookings` has two foreign keys to `venues` and two to
# `profiles` (requester and decider), so every embed names its constraint.
_BOOKING_DETAIL_COLUMNS = (
    "id, event_id, venue_id, booked_period, status, request_note, created_at, "
    "decision_reason, suggestion_note, decided_at, flag, flag_reason, "
    "venue:venues!venue_bookings_venue_id_fkey(name), "
    "requester:profiles!venue_bookings_requested_by_fkey(full_name), "
    "decider:profiles!venue_bookings_decided_by_fkey(full_name)"
)


def _embedded_name(row: dict, key: str, field: str) -> str | None:
    embedded = row.get(key)
    if isinstance(embedded, list):
        embedded = embedded[0] if embedded else None
    return (embedded or {}).get(field)


def _embedded_relation(row: dict, key: str) -> dict | None:
    embedded = row.get(key)
    if isinstance(embedded, list):
        embedded = embedded[0] if embedded else None
    return embedded if isinstance(embedded, dict) else None


def get_booking(booking_id: str) -> dict | None:
    """One booking with its venue's name, who requested it and who decided it,
    shaped for `service.booking_detail`; None if it doesn't exist."""
    response = (
        get_supabase_admin_client()
        .table("venue_bookings")
        .select(_BOOKING_DETAIL_COLUMNS)
        .eq("id", booking_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return None
    row = rows[0]
    decided_at = row.get("decided_at")
    return {
        "id": row["id"],
        "event_id": row["event_id"],
        "venue_id": row["venue_id"],
        "venue_name": _embedded_name(row, "venue", "name"),
        "period": _parse_range(row["booked_period"]),
        "status": row["status"],
        "request_note": row.get("request_note"),
        "requested_at": datetime.fromisoformat(row["created_at"]),
        "requested_by_name": _embedded_name(row, "requester", "full_name"),
        "flag": row.get("flag"),
        "flag_reason": row.get("flag_reason"),
        "decision_reason": row.get("decision_reason"),
        "suggestion_note": row.get("suggestion_note"),
        "decided_by_name": _embedded_name(row, "decider", "full_name"),
        "decided_at": datetime.fromisoformat(decided_at) if decided_at else None,
    }


def list_booking_history(booking_id: str) -> list[dict]:
    """CR-99's history of one booking, oldest first, with each actor's name.
    A null actor is the system (the expiry job)."""
    response = (
        get_supabase_admin_client()
        .table("venue_booking_history")
        .select("action, from_status, to_status, reason, suggestion_note, created_at, "
                "actor:profiles!venue_booking_history_actor_id_fkey(full_name)")
        .eq("booking_id", booking_id)
        .order("created_at")
        .execute()
    )
    return [
        {
            "action": row["action"],
            "from_status": row.get("from_status"),
            "to_status": row.get("to_status"),
            "actor_name": _embedded_name(row, "actor", "full_name"),
            "reason": row.get("reason"),
            "suggestion": row.get("suggestion_note"),
            "at": datetime.fromisoformat(row["created_at"]),
        }
        for row in response.data or []
    ]


def reject_booking(booking_id: str, actor_id: str, reason: str, suggestion: str | None, *,
                   notify_message: str) -> dict:
    """Run `public.reject_venue_booking` (SCRUM-38): the decision, its history
    row and the coordinator's notification in one transaction. Returns
    `{outcome, event_id, from_status}`; every refusal is an outcome code."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "reject_venue_booking",
            {
                "p_booking_id": booking_id,
                "p_actor_id": actor_id,
                "p_reason": reason,
                "p_suggestion": suggestion,
                "p_notify_message": notify_message,
            },
        )
        .execute()
    )
    return (response.data or [])[0]


def approve_booking(booking_id: str, actor_id: str, *, notify_message: str) -> dict:
    """Run `public.approve_venue_booking` (SCRUM-36): the decision, its history
    row and the coordinator's notification in one transaction. Returns
    `{outcome, event_id, from_status}`; every refusal is an outcome code."""
    response = (
        get_supabase_admin_client()
        .rpc(
            "approve_venue_booking",
            {"p_booking_id": booking_id, "p_actor_id": actor_id, "p_notify_message": notify_message},
        )
        .execute()
    )
    return (response.data or [])[0]


def restore_affected_booking(booking_id: str, actor_id: str) -> dict:
    """Run `public.restore_affected_booking` (CR-95 AC9): the flag cleared, a
    pending replacement cancelled, history and notices in one transaction.
    Returns `{outcome, cancelled_booking_ids}`; every refusal is an outcome code."""
    response = (
        get_supabase_admin_client()
        .rpc("restore_affected_booking", {"p_booking_id": booking_id, "p_actor_id": actor_id})
        .execute()
    )
    return (response.data or [])[0]


def list_rejected_bookings(event_id: str) -> list[dict]:
    """The event's rejected bookings, newest decision first, with what venue
    staff said (SCRUM-38 AC6). For the assigned coordinator only."""
    response = (
        get_supabase_admin_client()
        .table("venue_bookings")
        .select("id, venue_id, decision_reason, suggestion_note, decided_at, "
                "venue:venues!venue_bookings_venue_id_fkey(name)")
        .eq("event_id", event_id)
        .eq("status", "rejected")
        .order("decided_at", desc=True)
        .execute()
    )
    return [
        {
            "id": row["id"],
            "venue_id": row["venue_id"],
            "venue_name": _embedded_name(row, "venue", "name"),
            "reason": row.get("decision_reason"),
            "suggestion": row.get("suggestion_note"),
            "decided_at": datetime.fromisoformat(row["decided_at"]) if row.get("decided_at") else None,
        }
        for row in response.data or []
    ]


def list_active_bookings(event_id: str) -> list[dict]:
    try:
        response = (
            get_supabase_admin_client()
            .table("venue_bookings")
            .select("id, event_id, event_space_request_id, venue_id, status, expires_at, flag, flag_reason, replaces_booking_id, venues!venue_bookings_venue_id_fkey(name)")
            .eq("event_id", event_id)
            # Expired too: a space whose hold ran out still shows it (CR-99 AC7, CR-97).
            .in_("status", [*OCCUPYING_STATUSES, "expired"])
            .order("created_at")
            .execute()
        )
    except APIError as exc:
        # Keep coordinator reads usable while the forward-only schema migration
        # is rolling out; only a missing schema-cache column permits fallback.
        if exc.code == "PGRST204":
            return []
        raise
    return response.data or []


def list_venue_staff_ids() -> set[str]:
    """Profiles holding the venue staff role. Used only to address the
    notifications a venue edit sends (CR-94), never to authorise a caller."""
    response = (
        get_supabase_admin_client()
        .table("user_roles")
        .select("profile_id")
        .eq("role", "venue_staff")
        .execute()
    )
    return {row["profile_id"] for row in response.data or []}


def mark_safety_revision(booking_id: str, actor_id: str) -> str:
    """CR-104: the RPC clears the safety flag atomically and returns an outcome."""
    return get_supabase_admin_client().rpc(
        "mark_safety_revision", {"p_booking_id": booking_id, "p_actor_id": actor_id}
    ).execute().data
