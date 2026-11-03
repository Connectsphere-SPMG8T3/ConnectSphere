"""CR-111: the organiser's own view of each venue on an event (AC2 to AC4, AC6)."""
from datetime import datetime, timezone

from app.modules.events.organiser_venues import ORGANISER_VENUE_STATUSES, organiser_venues
from app.modules.events.schemas import EventSpaceRequestResponse

EVENT_START = datetime(2026, 11, 12, 2, 0, tzinfo=timezone.utc)
EVENT_END = datetime(2026, 11, 12, 4, 0, tzinfo=timezone.utc)
SPACE_START = datetime(2026, 11, 12, 3, 0, tzinfo=timezone.utc)
SPACE_END = datetime(2026, 11, 12, 3, 30, tzinfo=timezone.utc)


def space(space_id="sp-1", label="Main hall", primary=False, starts_at=None, ends_at=None):
    return EventSpaceRequestResponse(
        id=space_id, event_id="ev-1", label=label, is_primary=primary,
        starts_at=starts_at, ends_at=ends_at,
    )


def booking(booking_id="b-1", status="approved", space_id="sp-1", **extra):
    return {
        "id": booking_id, "event_space_request_id": space_id, "venue_id": "v-1",
        "venue_name": "Marina Hall", "venue_location": "1 Bayfront Ave", "status": status,
        "flag": None, "flag_reason": None, "replaces_booking_id": None, **extra,
    }


def build(bookings, spaces=None, status="confirmed"):
    return organiser_venues(status, EVENT_START, EVENT_END, spaces if spaces is not None else [space()], bookings)


def test_each_booking_is_listed_separately_with_venue_location_window_and_status():
    spaces = [space("sp-1", "Main hall", starts_at=SPACE_START, ends_at=SPACE_END), space("sp-2", "Foyer")]
    bookings = [
        booking("b-1", "approved", "sp-1"),
        booking("b-2", "held", "sp-2", venue_name="Harbour Foyer", venue_location="2 Quay Rd"),
    ]

    venues = build(bookings, spaces)

    assert [(v.booking_id, v.space_label, v.venue_name, v.location) for v in venues] == [
        ("b-1", "Main hall", "Marina Hall", "1 Bayfront Ave"),
        ("b-2", "Foyer", "Harbour Foyer", "2 Quay Rd"),
    ]
    assert (venues[0].starts_at, venues[0].ends_at) == (SPACE_START, SPACE_END)
    # A space with no window of its own inherits the event's.
    assert (venues[1].starts_at, venues[1].ends_at) == (EVENT_START, EVENT_END)
    assert [v.status for v in venues] == ["approved", "awaiting_approval"]


def test_the_primary_venue_is_marked():
    venues = build([booking("b-1", space_id="sp-1"), booking("b-2", space_id="sp-2")],
                   [space("sp-1", primary=True), space("sp-2", "Foyer")])

    assert [v.is_primary for v in venues] == [True, False]


def test_a_booking_with_no_space_uses_the_event_window_and_has_no_label():
    venues = build([booking(space_id=None)], [])

    assert venues[0].space_label is None
    assert (venues[0].starts_at, venues[0].ends_at) == (EVENT_START, EVENT_END)
    assert venues[0].is_primary is False


def test_an_affected_venue_says_so_and_what_happens_next():
    venues = build([booking(flag="affected", flag_reason="Venue unavailable: roof repairs (internal)")])

    assert venues[0].status == "affected"
    assert "no longer available" in venues[0].next_action
    assert "coordinator" in venues[0].next_action


def test_other_internal_flags_do_not_change_what_the_organiser_sees():
    venues = build([booking(status="approved", flag="unsuitable", flag_reason="Too small")])

    assert venues[0].status == "approved"


def test_a_hold_awaiting_venue_staff_is_labelled_as_not_yet_confirmed():
    venues = build([booking(status="held")], status="planning")

    assert venues[0].status == "awaiting_approval"
    assert venues[0].status_label == "Awaiting venue approval"


def test_an_approved_venue_asks_nothing_of_the_organiser_once_the_event_is_confirmed():
    confirmed = build([booking(status="approved")], status="confirmed")
    planning = build([booking(status="approved")], status="planning")

    assert "Nothing is needed from you" in confirmed[0].next_action
    assert "remaining checks" in planning[0].next_action


def test_a_booking_under_re_review_is_shown_as_being_rechecked():
    venues = build([booking(status="re_review")])

    assert venues[0].status == "re_review"
    assert venues[0].status_label == "Being re-checked"


def test_expired_bookings_are_not_listed():
    assert build([booking(status="expired")]) == []


def test_every_listed_status_has_wording():
    assert set(ORGANISER_VENUE_STATUSES) == {"awaiting_approval", "approved", "re_review", "affected"}
    assert all(entry["label"] and entry["next_action"] for entry in ORGANISER_VENUE_STATUSES.values())


def test_internal_details_are_never_part_of_the_shape():
    venue = build([booking(flag="affected", flag_reason="secret staff note", replaces_booking_id="b-0",
                           needs_re_review_reason="internal reason", notes="staff only")])[0]

    dumped = str(venue.model_dump())
    for secret in ("secret staff note", "internal reason", "staff only", "b-0"):
        assert secret not in dumped
    assert not {"flag", "flag_reason", "replaces_booking_id", "needs_re_review_reason"} & set(venue.model_dump())


def test_a_confirmed_event_shows_each_venues_preparation_stage_without_the_note():
    # SCRUM-109 AC4: the organiser sees each venue's progress stage, never the internal note.
    venues = build([
        booking("b-1", preparation={"stage": "in_progress", "note": "staff only note", "updated_at": None}),
        booking("b-2"),
    ], status="preparation")

    assert [v.preparation_stage for v in venues] == ["in_progress", "not_started"]
    assert "staff only note" not in str([v.model_dump() for v in venues])


def test_preparation_stage_is_not_shown_before_the_event_is_confirmed():
    # SCRUM-109 AC1, AC7: progress is kept in Planning but is not part of what the organiser sees.
    venues = build([booking(preparation={"stage": "completed", "note": None})], status="planning")

    assert venues[0].preparation_stage is None
