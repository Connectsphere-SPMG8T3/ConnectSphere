"""All Supabase reads for the venues module.

This is the module's only I/O seam (REQUIREMENTS §3.3 `repository.py`); the
service and the search rules never see a Supabase client. Tests patch the
functions here. Reads use the secret-key admin client, so callers must
already have passed the role check in the router.
"""

import re
from datetime import datetime

from app.db.supabase import get_supabase_admin_client
from app.modules.venues.schemas import (
    BlockSummary,
    BookingSummary,
    Occupant,
    Period,
    VenueSummary,
)
from app.modules.venues.search import OCCUPYING_STATUSES

_VENUE_COLUMNS = (
    "id, name, location, capacity, accessibility_features, opens_at, closes_at, is_active, description, "
    "venue_layouts(layout, capacity_for_layout), venue_facilities(facility)"
)

# PostgREST renders a tstzrange as e.g. ["2026-10-10 06:00:00+00","2026-10-10 09:00:00+00")
_RANGE_PATTERN = re.compile(r'^[\[(]"?([^",]+)"?,"?([^")\]]+)"?[)\]]$')


def _parse_range(value: str) -> Period:
    match = _RANGE_PATTERN.match(value)
    if match is None:
        raise ValueError(f"Unrecognised range literal from PostgREST: {value!r}")
    return Period(starts_at=datetime.fromisoformat(match.group(1)), ends_at=datetime.fromisoformat(match.group(2)))


def _range_literal(period: Period) -> str:
    return f"[{period.starts_at.isoformat()},{period.ends_at.isoformat()})"


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


def get_venue(venue_id: str) -> VenueSummary | None:
    response = (
        get_supabase_admin_client().table("venues").select(_VENUE_COLUMNS).eq("id", venue_id).maybe_single().execute()
    )
    row = response.data if response else None
    return _to_venue(row) if row else None


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
