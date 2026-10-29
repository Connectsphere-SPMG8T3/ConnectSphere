"""Which event details a change request can propose, and which of them are significant
(REQUIREMENTS §6.7, §6.19 CR-R16/CR-R17). Pure: no I/O. Story 37 (deciding) and story
112 (the coordinator's direct edits) read the same classification."""

from datetime import datetime

# Significant (§6.7, QA-66, QA2-10): date and time, attendance, venue and equipment
# requirements. The timezone moves the real time, so it counts as date and time.
SIGNIFICANT_EVENT_FIELDS = frozenset({
    "starts_at", "ends_at", "event_timezone", "expected_attendance", "layout_preference",
    "facilities_required", "preliminary_equipment_needs",
})
SIGNIFICANT_SPACE_FIELDS = frozenset({
    "expected_pax", "layout_preference", "facilities_required", "starts_at", "ends_at",
})

FIELD_LABELS = {
    "name": "name", "purpose": "purpose", "description": "description",
    "event_timezone": "timezone", "starts_at": "start time", "ends_at": "end time",
    "expected_attendance": "expected attendance", "expected_pax": "attendance",
    "layout_preference": "layout", "facilities_required": "facilities",
    "accessibility_needs": "accessibility needs", "preliminary_equipment_needs": "equipment needs",
    "registration_enabled": "registration", "registration_capacity": "registration capacity",
    "registration_opens_at": "registration opening", "registration_closes_at": "registration closing",
    "re_registration_allowed": "re-registration", "waitlist_enabled": "waiting list",
    "label": "name",
}

_TIME_FIELDS = frozenset({
    "starts_at", "ends_at", "registration_opens_at", "registration_closes_at",
})


def _comparable(field: str, value):
    """Q10: blank text is no text, facilities are a set, times are instants."""
    if isinstance(value, str):
        value = value.strip() or None
    if value is None:
        return None
    if field == "facilities_required":
        return frozenset(value)
    if field in _TIME_FIELDS:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def diff(current: dict, proposed: dict) -> list[dict]:
    """The proposed fields whose value really differs from the current one, as
    `{field, before, after}`, in the order `proposed` lists them (the schema's
    field order)."""
    return [
        {"field": field, "before": current.get(field), "after": trimmed(after)}
        for field, after in proposed.items()
        if _comparable(field, current.get(field)) != _comparable(field, after)
    ]


def trimmed(value):
    return (value.strip() or None) if isinstance(value, str) else value


def is_significant(changes: dict) -> bool:
    return (any(change["field"] in SIGNIFICANT_EVENT_FIELDS for change in changes["event"])
            or any(change["field"] in SIGNIFICANT_SPACE_FIELDS
                   for space in changes["spaces"] for change in space["fields"]))


def describe(changes: dict) -> str:
    """The changed fields in words, such as "expected attendance, Main hall layout"."""
    names = [FIELD_LABELS[change["field"]] for change in changes["event"]]
    names += [f'{space["label"]} {FIELD_LABELS[change["field"]]}'
              for space in changes["spaces"] for change in space["fields"]]
    return ", ".join(names)
