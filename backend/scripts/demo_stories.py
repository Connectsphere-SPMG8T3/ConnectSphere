"""Each story's demo starting state, registered with demo_data.story.

`build_event` walks an event through its lifecycle by API, signed in as the seeded
accounts, and stops at the stage a story's demo starts from. A story builder
combines it with the few extra calls its demo needs and returns what it made, for
the demo script.
"""

from datetime import datetime, timedelta

from scripts.demo_data import demo_email, demo_name, demo_start, story
from scripts.verify_live import SEEDED_PASSWORD, CheckFailed, Context, Session, db_query

ORGANISER = "a0000000-0000-4000-8000-000000000001"
COORDINATOR = "a0000000-0000-4000-8000-000000000002"
COORDINATOR_2 = "a0000000-0000-4000-8000-000000000008"
ATTENDEE = "a0000000-0000-4000-8000-000000000005"
EMAILS = {
    "event_organiser": "organiser@connectsphere.dev",
    COORDINATOR: "coordinator@connectsphere.dev",
    COORDINATOR_2: "coordinator2@connectsphere.dev",
    "venue_staff": "venue.staff@connectsphere.dev",
    "tech_support": "tech.support@connectsphere.dev",
    "attendee": "attendee@connectsphere.dev",
    "safety_officer": "safety.officer@connectsphere.dev",
    "event_coordinator_lead": "coordinator.lead@connectsphere.dev",
}

GRAND_BALLROOM = "b0000000-0000-4000-8000-000000000001"
AUDITORIUM_A = "b0000000-0000-4000-8000-000000000002"
SEMINAR_ROOM_1 = "b0000000-0000-4000-8000-000000000003"
BOARDROOM_ORCHID = "b0000000-0000-4000-8000-000000000004"
ROOFTOP_TERRACE = "b0000000-0000-4000-8000-000000000005"
INNOVATION_LAB = "b0000000-0000-4000-8000-000000000006"
HERITAGE_HALL = "b0000000-0000-4000-8000-000000000007"

PROJECTOR = "b0000000-0000-4000-8000-000000000001"
WIRELESS_MICS = "b0000000-0000-4000-8000-000000000002"
PA_SYSTEMS = "b0000000-0000-4000-8000-000000000003"
WHITEBOARDS = "b0000000-0000-4000-8000-000000000008"

STAGES = ["draft", "submitted", "under_review", "planning", "held", "venue_approved",
          "ready", "safety_review", "confirmed", "preparation"]
SAFETY_FACTORS = ["attendance_capacity", "layout", "emergency_access", "accessibility",
                  "equipment_placement", "venue_restrictions"]

DEMO_PASSWORD = "Demo1234"  # the stories' own attendee accounts

_sessions: dict[str, Session] = {}


def session(ctx: Context, who: str) -> Session:
    """One signed-in session per account: a role name, a coordinator's id, or a demo
    attendee's email (signed up by `demo_attendee`)."""
    if who not in _sessions:
        role = "event_coordinator" if who in (COORDINATOR, COORDINATOR_2) else who
        password = DEMO_PASSWORD if who.startswith("demo+") else SEEDED_PASSWORD
        _sessions[who] = ctx.login(role, email=EMAILS.get(who, who), password=password)
    return _sessions[who]


def demo_attendee(ctx: Context, story_id: str, extra: str, full_name: str) -> str:
    """Signs up an extra attendee for a story (demo+<id>-<extra>@…); returns its email."""
    email = demo_email(story_id, extra)
    response = ctx.client.post(f"{ctx.api}/auth/signup", json={
        "role": "attendee", "full_name": full_name, "email": email, "password": DEMO_PASSWORD})
    if response.status_code != 201:
        raise CheckFailed(f"sign-up of {email} answered {response.status_code}: {response.text[:200]}")
    return email


def call(ctx: Context, who: str, method: str, path: str, body: dict | None = None) -> dict:
    """An API call as `who` that must succeed; its JSON body ({} when empty)."""
    response = ctx.client.request(method, f"{ctx.api}{path}", json=body, headers=session(ctx, who).headers)
    if response.status_code >= 300:
        raise CheckFailed(f"{method} {path} answered {response.status_code}: {response.text[:300]}")
    return response.json() if response.content else {}


def build_event(ctx: Context, story_id: str, label: str, stage: str, *, day: int, hour: int = 10,
                hours: int = 3, relative: bool = False, attendance: int = 40, layout: str = "classroom",
                facilities: tuple = ("projector",), venue: str | None = INNOVATION_LAB,
                equipment: tuple = ((PROJECTOR, 2),), coordinator: str = COORDINATOR,
                **fields) -> dict:
    """An event owned by the seeded organiser, walked through the lifecycle up to `stage`
    (one of STAGES). Returns {"event_id", "booking_id", "line_ids", "starts_at"}."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage}")
    reached = STAGES.index(stage)
    starts_at, ends_at = demo_start(day, hour, hours, relative=relative)
    body = {"name": demo_name(story_id, label), "purpose": f"{label} (live demo)",
            "description": f"Demo event for story {story_id}.", "starts_at": starts_at, "ends_at": ends_at,
            "expected_attendance": attendance, "layout_preference": layout,
            "facilities_required": list(facilities), **fields}
    event_id = call(ctx, "event_organiser", "POST", "/events", body)["id"]
    made = {"event_id": event_id, "booking_id": None, "line_ids": [], "starts_at": starts_at}

    def at(name: str) -> bool:
        return reached >= STAGES.index(name)

    if at("submitted"):
        call(ctx, "event_organiser", "POST", f"/events/{event_id}/submit")
    if at("under_review"):
        call(ctx, "event_coordinator_lead", "POST", f"/events/{event_id}/assign", {"coordinator_id": coordinator})
    if at("planning"):
        call(ctx, coordinator, "POST", f"/events/{event_id}/approve")
    if at("held") and venue:
        made["booking_id"] = hold(ctx, coordinator, event_id, venue, starts_at, relative=relative)
    if at("venue_approved") and venue:
        call(ctx, "venue_staff", "POST", f"/venue-bookings/{made['booking_id']}/approve")
    if at("ready") and equipment:
        made["line_ids"] = request_equipment(ctx, coordinator, event_id, equipment)
        for line_id in made["line_ids"]:
            call(ctx, "tech_support", "POST", f"/equipment/requests/{line_id}/reserve")
        call(ctx, "tech_support", "PUT", f"/equipment/events/{event_id}/exit-confirmation", {"confirmed": True})
    if at("safety_review"):
        call(ctx, coordinator, "POST", f"/events/{event_id}/send-for-safety-check")
    if at("confirmed"):
        safety_approve(ctx, event_id, [made["booking_id"]] if made["booking_id"] else [])
    if at("preparation"):
        call(ctx, "venue_staff", "PUT", f"/venue-bookings/{made['booking_id']}/preparation",
             {"stage": "in_preparation"})
    return made


def hold(ctx: Context, coordinator: str, event_id: str, venue: str, starts_at: str, *,
         relative: bool = False, **fields) -> str:
    """A venue hold, its expiry moved to two hours before the event so it outlasts the
    presentation (holds otherwise expire 7 days after the request, CR-99)."""
    booking_id = call(ctx, coordinator, "POST", "/venue-bookings",
                      {"event_id": event_id, "venue_id": venue, **fields})["id"]
    if not relative:
        expires = datetime.fromisoformat(starts_at) - timedelta(hours=2)
        call(ctx, "venue_staff", "PATCH", f"/venue-bookings/{booking_id}/expiry",
             {"expires_at": expires.isoformat()})
    return booking_id


def request_equipment(ctx: Context, coordinator: str, event_id: str, items: tuple) -> list[str]:
    lines = call(ctx, coordinator, "POST", "/equipment/requests", {
        "event_id": event_id, "items": [{"equipment_id": e, "quantity": q} for e, q in items]})["lines"]
    return [line["id"] for line in lines]


def checklist(booking_ids: list[str], rating: str = "satisfactory") -> list[dict]:
    """Every factor marked; the venue factors once per booking (CR-108 AC2)."""
    answers = [{"factor": "equipment_placement", "rating": rating}]
    for factor in SAFETY_FACTORS:
        if factor != "equipment_placement":
            answers += [{"factor": factor, "rating": rating, "booking_id": b} for b in booking_ids]
    return answers


def safety_approve(ctx: Context, event_id: str, booking_ids: list[str]) -> None:
    call(ctx, "safety_officer", "POST", f"/events/{event_id}/safety-approve", {"checklist": checklist(booking_ids)})


def status_of(event_id: str) -> str:
    return db_query(f"select status from public.events where id = '{event_id}'")[0]["status"]


def expect_status(event_id: str, status: str) -> None:
    if (actual := status_of(event_id)) != status:
        raise CheckFailed(f"event {event_id} is {actual}, expected {status}")


def multi_space_event(ctx: Context, story_id: str, label: str, stage: str, *, day: int,
                      spaces: list[tuple[str, int, str, str | None]], attendance: int) -> dict:
    """An event with one space per (label, pax, layout, venue) tuple, each venue booked for
    its own space (CR-97/CR-98); the first space is the primary. Stages up to `preparation`;
    a space whose venue is None is left unbooked."""
    made = build_event(ctx, story_id, label, "draft", day=day, attendance=attendance, venue=None,
                       equipment=(), layout=None, facilities=())
    event_id = made["event_id"]
    made["space_ids"] = [
        call(ctx, "event_organiser", "POST", f"/events/{event_id}/spaces", {
            "label": space_label, "expected_pax": pax, "layout_preference": layout})["id"]
        for space_label, pax, layout, _ in spaces]
    reached = STAGES.index(stage)
    if reached >= STAGES.index("submitted"):
        call(ctx, "event_organiser", "POST", f"/events/{event_id}/submit")
    if reached >= STAGES.index("under_review"):
        call(ctx, "event_coordinator_lead", "POST", f"/events/{event_id}/assign", {"coordinator_id": COORDINATOR})
    if reached >= STAGES.index("planning"):
        call(ctx, COORDINATOR, "POST", f"/events/{event_id}/approve")
    made["booking_ids"] = []
    if reached >= STAGES.index("held"):
        for space_id, (_, _, _, venue) in zip(made["space_ids"], spaces):
            if venue:
                made["booking_ids"].append(hold(ctx, COORDINATOR, None, venue, made["starts_at"],
                                                event_space_request_id=space_id))
        call(ctx, COORDINATOR, "PUT", f"/events/{event_id}/spaces/{made['space_ids'][0]}/primary")
    if reached >= STAGES.index("venue_approved"):
        for booking_id in made["booking_ids"]:
            call(ctx, "venue_staff", "POST", f"/venue-bookings/{booking_id}/approve")
    if reached >= STAGES.index("safety_review"):
        call(ctx, COORDINATOR, "POST", f"/events/{event_id}/send-for-safety-check")
    if reached >= STAGES.index("confirmed"):
        safety_approve(ctx, event_id, made["booking_ids"])
    if reached >= STAGES.index("preparation"):
        call(ctx, "venue_staff", "PUT", f"/venue-bookings/{made['booking_ids'][0]}/preparation",
             {"stage": "in_progress", "note": "Chairs set out; AV check booked."})
    return made


# --- 4b: event request, review and assignment ------------------------------------------


@story("8", "Event Request Creation")
def _(ctx):
    made = build_event(ctx, "8", "Product launch", "draft", day=1, attendance=None,
                       accessibility_needs="Wheelchair access to the stage",
                       preliminary_equipment_needs="2 projectors, 4 wireless mics")
    return {"draft (attendance missing)": made["event_id"]}


@story("9", "Draft Event Requests")
def _(ctx):
    keep = build_event(ctx, "9", "Team offsite (draft)", "draft", day=2, attendance=None,
                       description=None, layout=None, facilities=())
    discard = build_event(ctx, "9", "Old idea to discard", "draft", day=2, hour=14, attendance=None)
    return {"draft to continue": keep["event_id"], "draft to discard": discard["event_id"]}


@story("66", "Reuse a previous or recurring event")
def _(ctx):
    made = build_event(ctx, "66", "Annual Tech Talk", "planning", day=3, attendance=120, layout="theatre",
                       venue=None, equipment=(), facilities=("projector", "microphone"),
                       accessibility_needs="Hearing loop", preliminary_equipment_needs="Lectern and 2 mics")
    return {"previous event": made["event_id"]}


@story("49", "Review Submitted Event Request Details")
def _(ctx):
    made = build_event(ctx, "49", "Industry networking night", "under_review", day=4, attendance=80,
                       layout="reception", facilities=("sound_system", "wifi"),
                       accessibility_needs="Step-free entry; two wheelchair users",
                       preliminary_equipment_needs="PA system and a lectern")
    return {"under review": made["event_id"]}


@story("33", "Request clarification or amendments")
def _(ctx):
    made = build_event(ctx, "33", "Startup pitch day", "under_review", day=5, attendance=150, layout="theatre")
    return {"under review": made["event_id"]}


@story("34", "Approve event request to start planning")
def _(ctx):
    made = build_event(ctx, "34", "Hackathon kickoff", "under_review", day=6, attendance=60)
    return {"under review": made["event_id"]}


@story("52", "Reject Event Request")
def _(ctx):
    made = build_event(ctx, "52", "Rooftop film night", "held", day=7, equipment=())
    return {"planning, holds Innovation Lab": made["event_id"], "hold": made["booking_id"]}


@story("12", "Coordinator Assignment")
def _(ctx):
    first = build_event(ctx, "12", "Alumni homecoming", "submitted", day=8, attendance=200, layout="banquet")
    second = build_event(ctx, "12", "Career fair", "submitted", day=9, attendance=300, layout="reception")
    return {"unassigned (older)": first["event_id"], "unassigned (newer)": second["event_id"]}


@story("81", "Change coordinator assignment")
def _(ctx):
    made = build_event(ctx, "81", "Research symposium", "held", day=10, equipment=())
    call(ctx, COORDINATOR, "POST", f"/events/{made['event_id']}/comments",
         {"body": "Venue hold placed; waiting on venue staff."})
    return {"planning, Marcus Lim": made["event_id"]}


@story("CR-101", "Event Coordinator Lead Dashboard")
def _(ctx):
    made = build_event(ctx, "CR-101", "Charity gala", "planning", day=11, coordinator=COORDINATOR_2,
                       attendance=250, layout="banquet")
    return {"planning, second coordinator": made["event_id"]}


@story("CR-106", "Request a reassignment from the Lead")
def _(ctx):
    made = build_event(ctx, "CR-106", "Leadership retreat", "planning", day=12)
    return {"planning": made["event_id"]}


@story("61", "Comment and discuss on my event")
def _(ctx):
    made = build_event(ctx, "61", "Design thinking workshop", "under_review", day=13)
    call(ctx, COORDINATOR, "POST", f"/events/{made['event_id']}/comments",
         {"body": "Will attendees need laptops, or should we arrange some?"})
    return {"under review, one comment": made["event_id"]}


@story("CR-111", "See my event's venues and coordinator")
def _(ctx):
    made = multi_space_event(ctx, "CR-111", "Tech conference", "preparation", day=14, attendance=140,
                             spaces=[("Main hall", 120, "theatre", AUDITORIUM_A),
                                     ("Breakout room", 20, "boardroom", SEMINAR_ROOM_1)])
    return {"preparation, two venues": made["event_id"]}


@story("62", "View an event's change history")
def _(ctx):
    made = build_event(ctx, "62", "Sustainability forum", "preparation", day=15)
    event = call(ctx, COORDINATOR, "GET", f"/events/{made['event_id']}")
    call(ctx, COORDINATOR, "PATCH", f"/events/{made['event_id']}/details",
         {"version": event["version"], "purpose": "Share campus sustainability results"})
    return {"preparation, with history": made["event_id"]}


@story("112", "Edit an assigned event's details")
def _(ctx):
    made = build_event(ctx, "112", "Data science meetup", "planning", day=16)
    return {"planning": made["event_id"]}


# --- 4c: venues ----------------------------------------------------------------------


def demo_venue(story_id: str, label: str, *, capacity: int, layouts: dict[str, int | None],
               facilities: tuple = (), setup: int = 0, turnaround: int = 0,
               accessibility: tuple = ("wheelchair_access",)) -> str:
    """A venue of the story's own (there is no endpoint to create one), active and
    open 08:00–22:00, last updated by venue staff like the seeded catalogue."""
    features = "{" + ",".join(accessibility) + "}"
    [row] = db_query(
        "insert into public.venues (name, location, capacity, opens_at, closes_at, is_active, "
        "accessibility_features, setup_minutes, turnaround_minutes, emergency_access, updated_by) values "
        f"('{demo_name(story_id, label)}', 'Demo Campus, Block D', {capacity}, '08:00', '22:00', true, "
        f"'{features}', {setup}, {turnaround}, 'Two exits to the courtyard', "
        "'a0000000-0000-4000-8000-000000000003') returning id")
    venue_id = row["id"]
    for layout, layout_capacity in layouts.items():
        db_query("insert into public.venue_layouts (venue_id, layout, capacity_for_layout) values "
                 f"('{venue_id}', '{layout}', {layout_capacity if layout_capacity else 'null'})")
    for facility in facilities:
        db_query(f"insert into public.venue_facilities (venue_id, facility) values ('{venue_id}', '{facility}')")
    return venue_id


def block(ctx: Context, story_id: str, venue_id: str, starts_at: str, ends_at: str,
          reason: str = "maintenance") -> str:
    """A venue block whose detail carries the story's demo name, so a reset deletes it."""
    return call(ctx, "venue_staff", "POST", f"/venues/{venue_id}/blocks", {
        "starts_at": starts_at, "ends_at": ends_at, "reason": reason,
        "detail": demo_name(story_id, f"{reason} block"), "confirm": True})["block"]["id"]


@story("39", "View Venue Catalogue")
def _(ctx):
    made = build_event(ctx, "39", "Booked into Auditorium A", "held", day=17, hour=14, venue=AUDITORIUM_A,
                       layout="theatre", equipment=())
    starts_at, ends_at = demo_start(17, 13, 5)
    block(ctx, "39", SEMINAR_ROOM_1, starts_at, ends_at)
    return {"holds Auditorium A 14:00-17:00": made["event_id"], "Seminar Room 1 blocked 13:00-18:00": SEMINAR_ROOM_1}


@story("18", "Venue Suitability Checking")
def _(ctx):
    made = build_event(ctx, "18", "Guest lecture", "planning", day=18, attendance=120, layout="theatre",
                       facilities=("projector", "microphone"), venue=None, equipment=())
    return {"planning, 120 theatre, projector + mic": made["event_id"]}


@story("19", "Venue Booking Request")
def _(ctx):
    made = build_event(ctx, "19", "Robotics showcase", "planning", day=19, hour=14, attendance=100,
                       layout="theatre", facilities=(), venue=None, equipment=())
    other = build_event(ctx, "19", "Already in Heritage Hall", "held", day=19, hour=13, attendance=100,
                        layout="theatre", facilities=(), venue=HERITAGE_HALL, equipment=())
    return {"planning, no venue": made["event_id"], "holds Heritage Hall 13:00-16:00": other["event_id"]}


@story("21", "Booking Conflict Detection")
def _(ctx):
    venue = demo_venue("21", "Buffer Studio", capacity=80, layouts={"classroom": None},
                       facilities=("projector",), setup=30, turnaround=45)
    booked = build_event(ctx, "21", "Booked 10:00-12:00", "venue_approved", day=20, hours=2, venue=venue,
                         equipment=())
    overlaps = build_event(ctx, "21", "Wants 13:00 (overlaps)", "planning", day=20, hour=13, hours=2,
                           venue=None, equipment=())
    touches = build_event(ctx, "21", "Wants 13:15 (touches)", "planning", day=20, hour=13, hours=2,
                          venue=None, equipment=())
    starts_at, ends_at = demo_start(20, 13, 2)
    db_query(f"update public.events set starts_at = '{starts_at}'::timestamptz + interval '15 minutes', "
             f"ends_at = '{ends_at}'::timestamptz + interval '15 minutes' where id = '{touches['event_id']}'")
    return {"Buffer Studio (setup 30, turnaround 45)": venue, "approved 10:00-12:00": booked["event_id"],
            "13:00 request (refused)": overlaps["event_id"], "13:15 request (allowed)": touches["event_id"]}


@story("36", "Approve a venue booking request")
def _(ctx):
    made = build_event(ctx, "36", "Wellness week opener", "held", day=21, venue=SEMINAR_ROOM_1, equipment=(),
                       accessibility_needs="Lift access")
    return {"held at Seminar Room 1": made["booking_id"], "event": made["event_id"]}


@story("38", "Reject a venue booking request")
def _(ctx):
    made = build_event(ctx, "38", "Chess tournament", "held", day=22, equipment=())
    return {"held at Innovation Lab": made["booking_id"], "event": made["event_id"]}


@story("85", "Cancel a held or approved venue booking")
def _(ctx):
    made = build_event(ctx, "85", "Photography exhibition", "confirmed", day=23, equipment=())
    return {"confirmed, approved booking": made["event_id"]}


@story("CR-97", "Book more than one venue for an event")
def _(ctx):
    made = multi_space_event(ctx, "CR-97", "Education summit", "venue_approved", day=24, attendance=170,
                             spaces=[("Plenary", 150, "theatre", AUDITORIUM_A),
                                     ("Workshop room", 20, "classroom", None)])
    return {"planning, Plenary booked, Workshop room not": made["event_id"]}


@story("CR-98", "Propose multiple event spaces")
def _(ctx):
    made = build_event(ctx, "CR-98", "Music festival", "draft", day=25, attendance=200, layout=None,
                       facilities=(), venue=None, equipment=())
    call(ctx, "event_organiser", "POST", f"/events/{made['event_id']}/spaces",
         {"label": "Main stage", "expected_pax": 120, "layout_preference": "theatre"})
    return {"draft, 200 expected, one 120-pax space": made["event_id"]}


@story("CR-99", "Expire tentative venue holds")
def _(ctx):
    live = build_event(ctx, "CR-99", "Hold to extend", "held", day=26, equipment=())
    lapsed = build_event(ctx, "CR-99", "Hold that expired", "held", day=26, hour=15, venue=SEMINAR_ROOM_1,
                         equipment=())
    db_query(f"update public.venue_bookings set expires_at = now() + interval '1 second' "
             f"where id = '{lapsed['booking_id']}'")
    return {"held, extendable": live["booking_id"], "expired hold": lapsed["booking_id"]}


@story("51", "Block venue for maintenance or operational reasons")
def _(ctx):
    made = build_event(ctx, "51", "Board game night", "venue_approved", day=27, venue=HERITAGE_HALL,
                       layout="theatre", facilities=(), equipment=())
    return {"approved at Heritage Hall": made["event_id"]}


@story("54", "Remove or shorten a venue block early")
def _(ctx):
    made = build_event(ctx, "54", "Debate finals", "venue_approved", day=28, venue=ROOFTOP_TERRACE,
                       layout="reception", facilities=(), equipment=())
    starts_at, _ = demo_start(28, 8, 1)
    _, ends_at = demo_start(28, 18, 1)
    block(ctx, "54", ROOFTOP_TERRACE, starts_at, ends_at, reason="safety")
    return {"affected by a safety block 08:00-19:00": made["event_id"]}


@story("CR-94", "Flag bookings affected by venue changes")
def _(ctx):
    venue = demo_venue("CR-94", "Garden Room", capacity=80, layouts={"classroom": None},
                       facilities=("projector", "wifi"))
    made = build_event(ctx, "CR-94", "Poetry reading", "venue_approved", day=29, attendance=60, venue=venue,
                       equipment=())
    return {"Garden Room (80, projector)": venue, "approved, 60 pax, needs projector": made["event_id"]}


@story("CR-95", "Rearrange bookings affected by venue unavailability")
def _(ctx):
    made = build_event(ctx, "CR-95", "Science fair", "confirmed", day=30, equipment=())
    starts_at, ends_at = demo_start(30, 8, 12)
    block(ctx, "CR-95", INNOVATION_LAB, starts_at, ends_at, reason="equipment_failure")
    return {"confirmed, booking affected": made["event_id"]}


@story("CR-100", "Set venue buffer times and safety details")
def _(ctx):
    return {"venue": demo_venue("CR-100", "Studio Theatre", capacity=90, layouts={"theatre": None},
                                facilities=("sound_system",))}


@story("63", "Update venue capacity and facilities information")
def _(ctx):
    venue = demo_venue("63", "Riverside Room", capacity=100, layouts={"classroom": None},
                       facilities=("projector", "whiteboard"))
    made = build_event(ctx, "63", "Coding bootcamp", "held", day=31, attendance=80, venue=venue, equipment=())
    return {"Riverside Room (100)": venue, "held, 80 pax": made["event_id"]}


@story("64", "Deactivate a venue from the catalogue")
def _(ctx):
    venue = demo_venue("64", "Annex Hall", capacity=120, layouts={"classroom": None}, facilities=("projector",))
    made = build_event(ctx, "64", "Language exchange", "venue_approved", day=32, venue=venue, equipment=())
    return {"Annex Hall": venue, "approved booking": made["event_id"]}


@story("CR-109", "Record venue preparation progress")
def _(ctx):
    made = build_event(ctx, "CR-109", "Art auction", "confirmed", day=33, equipment=())
    return {"confirmed": made["event_id"], "booking": made["booking_id"]}


@story("57", "View venue availability calendar")
def _(ctx):
    approved = build_event(ctx, "57", "Confirmed booking", "venue_approved", day=60, venue=GRAND_BALLROOM,
                           equipment=())
    held = build_event(ctx, "57", "Tentative hold", "held", day=61, venue=GRAND_BALLROOM, equipment=())
    starts_at, ends_at = demo_start(62, 9, 8)
    block(ctx, "57", GRAND_BALLROOM, starts_at, ends_at, reason="renovation")
    affected = build_event(ctx, "57", "Affected booking", "venue_approved", day=63, venue=GRAND_BALLROOM,
                           equipment=())
    starts_at, ends_at = demo_start(63, 9, 4)
    block(ctx, "57", GRAND_BALLROOM, starts_at, ends_at, reason="safety")
    return {"Grand Ballroom, week of 30 Jan 2027": GRAND_BALLROOM, "approved": approved["event_id"],
            "held": held["event_id"], "affected": affected["event_id"]}
