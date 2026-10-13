"""Which events an Event Coordinator Lead sees (CR-101 AC5). Pure, no I/O.

Every Lead sees the unassigned queue. An assigned event is seen by the Lead who
assigned or last reassigned it, by every Lead when it was assigned before the
Lead role existed (`assigned_by` is null), and by every Lead when the assigner
no longer holds the role, so no event is ever orphaned. With a single Lead this
reduces to "sees everything".
"""


def in_lead_scope(row: dict, lead_id: str, lead_ids: set[str]) -> bool:
    if row.get("coordinator_id") is None:
        return True
    assigned_by = row.get("assigned_by")
    return assigned_by is None or assigned_by == lead_id or assigned_by not in lead_ids


def active_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        coordinator_id = row.get("coordinator_id")
        if coordinator_id is not None:
            counts[coordinator_id] = counts.get(coordinator_id, 0) + 1
    return counts
