"""CR-108 AC1-AC3: the safety checklist's completeness and outcome rules (pure, no I/O)."""
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.events import safety_checklist as checklist
from app.modules.events.schemas import SafetyChecklistAnswer

B1 = UUID("b0000000-0000-4000-8000-000000000001")
B2 = UUID("b0000000-0000-4000-8000-000000000002")


def answers(bookings, rating="satisfactory", equipment=True):
    rows = [
        SafetyChecklistAnswer(factor=factor, booking_id=booking, rating=rating)
        for booking in bookings
        for factor in checklist.VENUE_FACTORS
    ]
    if equipment:
        rows.append(SafetyChecklistAnswer(factor=checklist.EQUIPMENT_FACTOR, rating=rating))
    return rows


def test_six_factors_five_of_them_per_venue():
    assert checklist.VENUE_FACTORS == (
        "attendance_capacity", "layout", "emergency_access", "accessibility", "venue_restrictions",
    )
    assert checklist.EQUIPMENT_FACTOR == "equipment_placement"


def test_complete_checklist_has_no_problems():
    assert checklist.checklist_problems(answers([B1, B2]), [B1, B2], "changes_requested") == []


def test_every_venue_factor_is_needed_for_every_booking():
    rows = [a for a in answers([B1, B2]) if not (a.booking_id == B2 and a.factor == "layout")]
    problems = checklist.checklist_problems(rows, [B1, B2], "changes_requested")
    assert problems == [f"Mark layout for venue booking {B2}"]


def test_equipment_placement_is_needed_once():
    rows = answers([B1], equipment=False)
    assert checklist.checklist_problems(rows, [B1], "changes_requested") == ["Mark equipment placement"]


def test_an_empty_checklist_names_everything_missing():
    problems = checklist.checklist_problems([], [B1], "changes_requested")
    assert len(problems) == len(checklist.VENUE_FACTORS) + 1


def test_a_factor_answered_twice_is_refused():
    rows = answers([B1]) + [SafetyChecklistAnswer(factor="layout", booking_id=B1, rating="concern")]
    assert checklist.checklist_problems(rows, [B1], "changes_requested") == [
        f"Layout for venue booking {B1} is marked more than once"
    ]


def test_a_booking_that_is_not_the_events_is_refused():
    rows = answers([B1, B2])
    assert checklist.checklist_problems(rows, [B1], "changes_requested") == [
        f"Venue booking {B2} is not part of this event"
    ]


def test_a_venue_factor_needs_a_booking_and_equipment_placement_must_not_have_one():
    no_booking = SafetyChecklistAnswer(factor="layout", rating="satisfactory")
    with_booking = SafetyChecklistAnswer(factor="equipment_placement", booking_id=B1, rating="satisfactory")
    base = [a for a in answers([B1]) if a.factor not in ("layout", "equipment_placement")]
    equipment = SafetyChecklistAnswer(factor="equipment_placement", rating="satisfactory")
    assert checklist.checklist_problems(base + [equipment, no_booking], [B1], "changes_requested") == [
        "Layout needs a venue booking", "Mark layout for venue booking " + str(B1),
    ]
    assert checklist.checklist_problems(base + [with_booking], [B1], "changes_requested") == [
        "Equipment placement applies to the whole event, not a venue booking", "Mark layout for venue booking " + str(B1),
    ]


@pytest.mark.parametrize("rating", ["satisfactory", "not_applicable"])
def test_approval_is_allowed_without_concerns(rating):
    assert checklist.checklist_problems(answers([B1], rating), [B1], "approved") == []


def test_a_concern_blocks_approval_but_not_the_other_outcomes():
    rows = answers([B1])
    rows[0] = SafetyChecklistAnswer(factor=rows[0].factor, booking_id=B1, rating="concern")
    assert checklist.checklist_problems(rows, [B1], "approved") == [
        "A factor marked Concern blocks approval: request changes or reject instead"
    ]
    assert checklist.checklist_problems(rows, [B1], "changes_requested") == []
    assert checklist.checklist_problems(rows, [B1], "arrangement_rejected") == []


def test_ratings_and_factors_are_a_closed_set():
    with pytest.raises(ValidationError):
        SafetyChecklistAnswer(factor="lighting", rating="satisfactory")
    with pytest.raises(ValidationError):
        SafetyChecklistAnswer(factor="layout", booking_id=B1, rating="fine")


@pytest.mark.parametrize("note,ok", [(None, True), ("  trimmed  ", True), ("x" * 1000, True), ("x" * 1001, False)])
def test_note_is_optional_trimmed_and_bounded(note, ok):
    if ok:
        row = SafetyChecklistAnswer(factor="layout", booking_id=B1, rating="concern", note=note)
        assert row.note == (note.strip() if note else None)
    else:
        with pytest.raises(ValidationError):
            SafetyChecklistAnswer(factor="layout", booking_id=B1, rating="concern", note=note)


def test_a_blank_note_is_stored_as_no_note():
    row = SafetyChecklistAnswer(factor="layout", booking_id=B1, rating="concern", note="   ")
    assert row.note is None
