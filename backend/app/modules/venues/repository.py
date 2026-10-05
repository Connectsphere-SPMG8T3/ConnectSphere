"""All Supabase reads for the venues module.

This is the module's only I/O seam (REQUIREMENTS §3.3 `repository.py`); the
service and the search rules never see a Supabase client. Tests patch the
functions here. Reads use the secret-key admin client, so callers must
already have passed the role check in the router.
"""

import re
from collections.abc import Iterable
from datetime import datetime

from app.db.supabase import get_supabase_admin_client
from app.modules.venues.schemas import (
    BlockSummary,
    BookingSummary,
    Editor,
    Occupant,
    Period,
    VenueProfile,
    VenueStaffBlock,
    VenueStaffBooking,
    VenueSummary,
)
from app.modules.venues.search import OCCUPYING_STATUSES

_VENUE_COLUMNS = (
    "id, name, location, capacity, accessibility_features, opens_at, closes_at, is_active, description, "
    "venue_layouts(layout, capacity_for_layout), venue_facilities(facility)"
)

# The profile page additionally shows when the venue was last updated and by
# whom (SCRUM-67 AC2). The embed names its constraint even though `venues` has
# only one foreign key to `profiles` today: a second one (an owner, a creator)
# would otherwise break this query with PGRST201 rather than the new column.
_VENUE_PROFILE_COLUMNS = _VENUE_COLUMNS + ", updated_at, updated_by, profiles!venues_updated_by_fkey(id, full_name)"

# PostgREST renders a tstzrange as e.g. ["2026-10-10 06:00:00+00","2026-10-10 09:00:00+00")
_RANGE_PATTERN = re.compile(r'^[\[(]"?([^",]+)"?,"?([^")\]]+)"?[)\]]$')


def _parse_range(value: str) -> Period:
    match = _RANGE_PATTERN.match(value)
    if match is None:
        raise ValueError(f"Unrecognised range literal from PostgREST: {value!r}")
    return Period(starts_at=datetime.fromisoformat(match.group(1)), ends_at=datetime.fromisoformat(match.group(2)))


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
    )


def list_occupants(period: Period) -> dict[str, list[Occupant]]:
    """Occupying bookings and blocks that overlap `period`, keyed by venue id.

    The overlap is evaluated in Postgres (`&&` on the GiST-indexed ranges),
    so at most a handful of rows come back however large the tables grow.
    """
    client = get_supabase_admin_client()
    literal = _range_literal(period)
    occupants: dict[str, list[Occupant]] = {}

    bookings = (
        client.table("venue_bookings")
        .select("venue_id, occupied_period, status")
        .in_("status", sorted(OCCUPYING_STATUSES))
        .overlaps("occupied_period", literal)
        .execute()
    )
    for row in bookings.data or []:
        occupants.setdefault(row["venue_id"], []).append(
            Occupant(kind="booking", period=_parse_range(row["occupied_period"]), detail=row["status"])
        )

    blocks = (
        client.table("venue_blocks")
        .select("venue_id, blocked_period, reason")
        .overlaps("blocked_period", literal)
        .execute()
    )
    for row in blocks.data or []:
        occupants.setdefault(row["venue_id"], []).append(
            Occupant(kind="block", period=_parse_range(row["blocked_period"]), detail=row["reason"])
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
        .select("id, event_id, occupied_period, status")
        .eq("venue_id", venue_id)
        .in_("status", sorted(OCCUPYING_STATUSES))
        .execute()
    )
    bookings = [
        BookingSummary(
            id=row["id"], event_id=row["event_id"], period=_parse_range(row["occupied_period"]), status=row["status"]
        )
        for row in response.data or []
    ]
    return sorted((b for b in bookings if b.period.ends_at > since), key=lambda b: b.period.starts_at)


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
    """Bookings on every venue in `statuses` whose period ends after `since`."""
    response = (
        get_supabase_admin_client()
        .table("venue_bookings")
        # The embed must name the constraint. `venue_bookings` has two foreign
        # keys to `venues` — `venue_id` and the `suggested_venue_id` a rejection
        # may carry (§6.13) — so a bare `venues(name)` is ambiguous and
        # PostgREST refuses the whole request with PGRST201 rather than
        # guessing. `venue_blocks` has only one, which is why it can stay bare.
        .select("id, event_id, venue_id, occupied_period, status, created_at, venues!venue_bookings_venue_id_fkey(name)")
        .in_("status", sorted(statuses))
        .overlaps("occupied_period", _open_ended_literal(since))
        .execute()
    )
    bookings = [
        VenueStaffBooking(
            id=row["id"],
            event_id=row["event_id"],
            venue_id=row["venue_id"],
            venue_name=_embedded_venue_name(row),
            period=_parse_range(row["occupied_period"]),
            status=row["status"],
            requested_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in response.data or []
    ]
    return sorted(bookings, key=lambda b: (b.period.starts_at, b.id))


def list_booking_statuses(event_ids: Iterable[str]) -> list[dict]:
    """`{event_id, status}` for every booking of these events, whatever its status."""
    ids = list(event_ids)
    if not ids:
        return []
    response = (
        get_supabase_admin_client()
        .table("venue_bookings")
        .select("event_id, status")
        .in_("event_id", ids)
        .execute()
    )
    return response.data or []
