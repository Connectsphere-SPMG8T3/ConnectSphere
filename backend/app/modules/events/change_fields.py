"""Which event details a change request can propose, and which of them are significant
(REQUIREMENTS §6.7, §6.19 CR-R16/CR-R17). Pure: no I/O. Story 37 (deciding) and story
112 (the coordinator's direct edits) read the same classification."""

# Significant (§6.7, QA-66, QA2-10): date and time, attendance, venue and equipment
# requirements. The timezone moves the real time, so it counts as date and time.
SIGNIFICANT_EVENT_FIELDS = frozenset({
    "starts_at", "ends_at", "event_timezone", "expected_attendance", "layout_preference",
    "facilities_required", "preliminary_equipment_needs",
})
SIGNIFICANT_SPACE_FIELDS = frozenset({
    "expected_pax", "layout_preference", "facilities_required", "starts_at", "ends_at",
})


def diff(current: dict, proposed: dict) -> list[dict]:
    """The proposed fields whose value differs from the current one, as
    `{field, before, after}`, in the order proposed."""
    return [
        {"field": field, "before": current.get(field), "after": after}
        for field, after in proposed.items()
        if current.get(field) != after
    ]


def is_significant(changes: dict) -> bool:
    return (any(change["field"] in SIGNIFICANT_EVENT_FIELDS for change in changes["event"])
            or any(change["field"] in SIGNIFICANT_SPACE_FIELDS
                   for space in changes["spaces"] for change in space["fields"]))


def field_names(changes: dict) -> list[str]:
    names = [change["field"] for change in changes["event"]]
    names += [change["field"] for space in changes["spaces"] for change in space["fields"]]
    return list(dict.fromkeys(names))
