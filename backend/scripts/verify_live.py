"""Run the scriptable manual test cases against the real system.

Two kinds of check, each named by the test case ID it runs (docs/test-cases/):

- API checks: real HTTP requests to a running backend, which talks to the live
  Supabase project. They only read shared data. The sessions they open are
  their own, and every one of them is logged out at the end.
- Database checks: the rolled-back scripts in supabase/verification/, run
  through `supabase db query` (needs `supabase login`), so they change nothing.

Sign-up checks create throwaway accounts named live-check+<run>-<case>@
connectsphere.dev. Every such account, and everything it owns, is deleted
through `supabase db query` before the checks start and after they finish, so
the seeded data is never touched. --skip-db skips these checks too.

Venue booking checks (SCRUM-19) likewise create throwaway events named
"live-check ..." (owned by the seeded organiser, assigned to the seeded
coordinator, dated 2031) and throwaway venue blocks noted "live-check". Those
events, their bookings and those blocks are deleted before and after the run.

Usage, from backend/ with the virtualenv active and the backend running:

    python scripts/verify_live.py                       # print results only
    python scripts/verify_live.py --record              # also write a run log
    python scripts/verify_live.py --api http://localhost:8010/api/v1
    python scripts/verify_live.py --skip-db             # API checks only
    python scripts/verify_live.py -k TC-ROLE            # checks whose ID or title contains this

--record writes docs/test-cases/runs/<date>-<time>-api-db-<commit>.md.
A check that couldn't run is recorded as Blocked, not as a pass or a fail:
after the first refused sign-in (Supabase's per-IP rate limit, or broken
sign-in), no further sign-ins are attempted. Exits 1 unless every check passed.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import hmac
import json
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "docs" / "test-cases" / "runs"
VERIFICATION_DIR = REPO_ROOT / "supabase" / "verification"
SGT = ZoneInfo("Asia/Singapore")
PROJECT_REF = "vuiryrzzyfecjqftwicj"

SEEDED_PASSWORD = "Cs1234"  # supabase/seed.sql
ACCOUNTS = {
    "event_organiser": "organiser@connectsphere.dev",
    "event_coordinator": "coordinator@connectsphere.dev",
    "venue_staff": "venue.staff@connectsphere.dev",
    "tech_support": "tech.support@connectsphere.dev",
    "attendee": "attendee@connectsphere.dev",
}
INVALID_CREDENTIALS = "Invalid email or password."
INVALID_TOKEN = "Invalid or expired authentication token."
PASSWORD_RULE = "Password must be at least 8 characters and include at least one letter and one digit."

# Throwaway accounts made by the sign-up checks. The LIKE pattern matches
# nothing else: seeded accounts have no "+".
THROWAWAY_PREFIX = "live-check+"
THROWAWAY_DOMAIN = "@connectsphere.dev"
THROWAWAY_PASSWORD = SEEDED_PASSWORD + "live"

# Rolled-back verification scripts, with the manual cases each one automates
# (as recorded in docs/test-cases/). event_review_fixture_reset.sql is left out
# on purpose: it writes to the shared fixtures.
DB_SCRIPTS = [
    ("auth_security_checks.sql", "TC-DATA-001–005, 007, 008, 010–012"),
    ("active_role_checks.sql", "TC-DATA-013"),
    ("venue_schema_checks.sql", "TC-VENUE-030–035"),
    ("event_schema_checks.sql", "SCRUM-8 schema"),
    ("event_review_checks.sql", "SCRUM-34/52 grants"),
    ("event_history_checks.sql", "TC-REV-015, TC-REV-016"),
    ("event_amendment_checks.sql", "TC-AMD-001, 005, 008 (database half)"),
    ("event_comment_checks.sql", "TC-CMT-008, 009, 010, 011, 013 (database half)"),
    ("venue_booking_request_checks.sql", "TC-BOOK-001–006 (database half)"),
    ("equipment_request_checks.sql", "TC-EQR-002, 003, 006, 007, 008, 009 (database half)"),
    ("venue_edit_checks.sql", "TC-VENUE-058, 059, 061 (database half)"),
]


class CheckFailed(Exception):
    pass


class CheckBlocked(Exception):
    """The check couldn't run, e.g. an earlier sign-in was refused. Not a verdict."""


# Supabase limits sign-ins per IP. The backend currently reports that refusal
# as a 401 "Invalid email or password." (DEFECTS D16), so a refused
# sign-in with known-good credentials can't be told apart from broken sign-in.
# After the first one, no more sign-ins are attempted: every further attempt
# would extend the limit, and every check needing one is marked Blocked.
SIGN_IN_REFUSED = (
    "correct credentials were refused (HTTP {status}). Either sign-in is broken, or Supabase "
    "rate-limited this IP, which the backend reports as a 401 (DEFECTS D16). "
    "No further sign-ins were attempted; wait about 5 minutes and re-run."
)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def expect_status(response: httpx.Response, status: int) -> None:
    expect(
        response.status_code == status,
        f"expected HTTP {status}, got {response.status_code}: {response.text[:200]}",
    )


def expect_detail(response: httpx.Response, detail: str) -> None:
    actual = response.json().get("detail")
    expect(actual == detail, f"expected detail {detail!r}, got {actual!r}")


@dataclass
class Session:
    role: str
    access_token: str
    refresh_token: str
    body: dict

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}


@dataclass
class Context:
    api: str
    client: httpx.Client
    run_id: str = ""
    sign_in_refused: bool = False
    _shared: dict = field(default_factory=dict)
    _opened: list = field(default_factory=list)

    def login(self, role: str, email: str | None = None, password: str = SEEDED_PASSWORD) -> Session:
        """A fresh session of its own, logged out when the run ends.

        Only for credentials that should work; wrong-password checks post
        to /auth/login directly.
        """
        if self.sign_in_refused:
            raise CheckBlocked("not run: an earlier sign-in was refused (see the first failure)")
        response = self.client.post(
            f"{self.api}/auth/login",
            json={"email": email or ACCOUNTS[role], "password": password},
        )
        if response.status_code in (401, 429):
            self.sign_in_refused = True
            raise CheckFailed(SIGN_IN_REFUSED.format(status=response.status_code))
        expect_status(response, 200)
        body = response.json()
        session = Session(role, body["access_token"], body["refresh_token"], body)
        self._opened.append(session)
        return session

    def attempt_login(self, email: str, password: str) -> httpx.Response:
        """A sign-in expected to be refused. Blocked once sign-ins are being
        refused, since a rate-limited 401 would otherwise pass as a correct one."""
        if self.sign_in_refused:
            raise CheckBlocked("not run: an earlier sign-in was refused (see the first failure)")
        return self.client.post(f"{self.api}/auth/login", json={"email": email, "password": password})

    def shared(self, role: str) -> Session:
        """One session per role for checks that only read, to spare sign-ins."""
        if role not in self._shared:
            self._shared[role] = self.login(role)
        return self._shared[role]

    def throwaway_email(self, case: str) -> str:
        return f"{THROWAWAY_PREFIX}{self.run_id}-{case}{THROWAWAY_DOMAIN}"

    def signup(self, **overrides) -> httpx.Response:
        body = {
            "role": "event_organiser",
            "full_name": "Live Check",
            "email": None,
            "password": THROWAWAY_PASSWORD,
            "organisation_name": "Live Check Org",
            "phone_number": "+65 9123 4567",
            **overrides,
        }
        return self.client.post(f"{self.api}/auth/signup", json=body)

    def logout_all(self) -> None:
        for session in self._opened:
            try:
                self.client.post(f"{self.api}/auth/logout", headers=session.headers)
            except httpx.HTTPError:
                pass


@dataclass
class Check:
    case_id: str
    title: str
    run: Callable[[Context], None]
    creates_accounts: bool = False
    # Reads the database to compare against, so --skip-db skips it too.
    needs_db: bool = False


API_CHECKS: list[Check] = []


def check(case_id: str, title: str, creates_accounts: bool = False, needs_db: bool = False):
    def register(fn: Callable[[Context], None]):
        API_CHECKS.append(Check(case_id, title, fn, creates_accounts, needs_db))
        return fn

    return register


# --- Login -----------------------------------------------------------------


@check("TC-AUTH-001", "Coordinator login returns tokens and the coordinator profile")
def _(ctx: Context) -> None:
    body = ctx.shared("event_coordinator").body
    expect(body.get("access_token") and body.get("refresh_token"), "tokens missing from the response")
    expect(body["profile"]["role"] == "event_coordinator", f"role is {body['profile']['role']!r}")


@check("TC-AUTH-002", "Every other seeded role logs in with its own role")
def _(ctx: Context) -> None:
    for role in ("event_organiser", "venue_staff", "tech_support", "attendee"):
        actual = ctx.shared(role).body["profile"]["role"]
        expect(actual == role, f"{ACCOUNTS[role]} logged in as {actual!r}")


@check("TC-AUTH-003", "Login response carries the full profile")
def _(ctx: Context) -> None:
    profile = ctx.shared("attendee").body["profile"]
    for key in ("id", "email", "full_name", "role", "organisation_name", "department", "phone_number"):
        expect(key in profile, f"profile has no {key!r}")


@check("TC-AUTH-006", "Wrong password is rejected with the generic message")
def _(ctx: Context) -> None:
    response = ctx.attempt_login(ACCOUNTS["event_coordinator"], SEEDED_PASSWORD + "x")
    expect_status(response, 401)
    expect_detail(response, INVALID_CREDENTIALS)


@check("TC-AUTH-007", "Unregistered email gets the same message as a wrong password")
def _(ctx: Context) -> None:
    response = ctx.attempt_login("nobody@connectsphere.dev", SEEDED_PASSWORD)
    expect_status(response, 401)
    expect_detail(response, INVALID_CREDENTIALS)


@check("TC-AUTH-010", "Malformed email is rejected by schema validation")
def _(ctx: Context) -> None:
    response = ctx.client.post(f"{ctx.api}/auth/login", json={"email": "not-an-email", "password": "irrelevant"})
    expect_status(response, 422)


@check("TC-AUTH-011", "Reserved-TLD email is rejected by schema validation")
def _(ctx: Context) -> None:
    response = ctx.client.post(
        f"{ctx.api}/auth/login", json={"email": "someone@example.test", "password": SEEDED_PASSWORD}
    )
    expect_status(response, 422)


@check("TC-AUTH-012", "Email padded with spaces still logs in")
def _(ctx: Context) -> None:
    session = ctx.login("event_coordinator", email=f"  {ACCOUNTS['event_coordinator']}  ")
    expect(session.body["profile"]["role"] == "event_coordinator", "logged in as the wrong account")


@check("TC-AUTH-013", "Email in a different case still logs in")
def _(ctx: Context) -> None:
    session = ctx.login("event_coordinator", email=ACCOUNTS["event_coordinator"].upper())
    expect(session.body["profile"]["role"] == "event_coordinator", "logged in as the wrong account")


@check("TC-AUTH-014", "SQL-injection password is an ordinary wrong password")
def _(ctx: Context) -> None:
    injection = "' OR " + "'1'='1"
    response = ctx.attempt_login(ACCOUNTS["event_coordinator"], injection)
    expect_status(response, 401)
    expect_detail(response, INVALID_CREDENTIALS)


# --- Session ---------------------------------------------------------------


@check("TC-AUTH-020", "/auth/me without a token is 401 with WWW-Authenticate")
def _(ctx: Context) -> None:
    response = ctx.client.get(f"{ctx.api}/auth/me")
    expect_status(response, 401)
    expect(response.headers.get("www-authenticate") == "Bearer", "WWW-Authenticate: Bearer missing")


@check("TC-AUTH-021", "/auth/me with a malformed token is 401")
def _(ctx: Context) -> None:
    response = ctx.client.get(f"{ctx.api}/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    expect_status(response, 401)
    expect_detail(response, INVALID_TOKEN)


@check("TC-AUTH-022", "/auth/me with a token signed by the wrong key is 401")
def _(ctx: Context) -> None:
    real = ctx.shared("attendee")
    claims = _jwt_claims(real.access_token)
    forged = _sign_hs256({**claims, "role": "authenticated"}, key=b"not-this-projects-key")
    response = ctx.client.get(f"{ctx.api}/auth/me", headers={"Authorization": f"Bearer {forged}"})
    expect_status(response, 401)


@check("TC-AUTH-019", "/auth/me returns the caller's own profile")
def _(ctx: Context) -> None:
    session = ctx.shared("event_organiser")
    response = ctx.client.get(f"{ctx.api}/auth/me", headers=session.headers)
    expect_status(response, 200)
    expect(response.json()["email"] == ACCOUNTS["event_organiser"], "a different profile came back")


# DEFECTS D18: the backend once sent every database call over one shared HTTP/2
# connection to Supabase. After about two minutes with no requests, Supabase
# closed that connection, the client reused it anyway, and every request of the
# next page load failed together ("Server disconnected"). Reproduced on 6 Oct
# 2026: bursts after up to 60 s idle passed; after 120 s, 5 of 6 requests
# answered 500. This check idles for longer than that between two bursts, so it
# adds IDLE_SECONDS to the run.
IDLE_SECONDS = 150
PAGE_LOAD_PATHS = ("/auth/me", "/events/dashboard/coordinator", "/equipment/catalogue") * 2


@check("TC-AUTH-049", "Parallel requests after the backend sits idle all succeed (D18)")
def _(ctx: Context) -> None:
    headers = ctx.shared("event_coordinator").headers
    urls = [f"{ctx.api}{path}" for path in PAGE_LOAD_PATHS]
    failures: list[str] = []

    def get(client: httpx.Client, url: str) -> str:
        try:
            return str(client.get(url, headers=headers).status_code)
        except httpx.HTTPError as exc:
            return type(exc).__name__

    # Its own client: these calls run in parallel threads.
    with httpx.Client(timeout=60) as client, ThreadPoolExecutor(max_workers=len(urls)) as pool:
        for label in ("first burst", f"after {IDLE_SECONDS}s idle"):
            if label != "first burst":
                time.sleep(IDLE_SECONDS)
            for url, status in zip(urls, pool.map(lambda u: get(client, u), urls)):
                if status != "200":
                    failures.append(f"{label}: {url.removeprefix(ctx.api)} -> {status}")
    expect(not failures, f"{len(failures)} of {2 * len(urls)} parallel requests failed: {failures}")


# --- Logout and refresh ----------------------------------------------------


@check("TC-AUTH-028", "Logout without a token is 401")
def _(ctx: Context) -> None:
    expect_status(ctx.client.post(f"{ctx.api}/auth/logout"), 401)


@check("TC-AUTH-029", "Logging out one user leaves another user's session working")
def _(ctx: Context) -> None:
    organiser = ctx.login("event_organiser")
    coordinator = ctx.login("event_coordinator")
    expect_status(ctx.client.post(f"{ctx.api}/auth/logout", headers=organiser.headers), 204)

    kept = ctx.client.post(f"{ctx.api}/auth/refresh", json={"refresh_token": coordinator.refresh_token})
    expect_status(kept, 200)
    coordinator.access_token = kept.json()["access_token"]  # so logout_all revokes it

    revoked = ctx.client.post(f"{ctx.api}/auth/refresh", json={"refresh_token": organiser.refresh_token})
    expect_status(revoked, 401)


@check("TC-AUTH-032", "Refresh rejects an unknown token (401) and an empty one (422)")
def _(ctx: Context) -> None:
    unknown = ctx.client.post(f"{ctx.api}/auth/refresh", json={"refresh_token": "not-a-real-refresh-token"})
    expect_status(unknown, 401)
    expect_detail(unknown, INVALID_TOKEN)
    expect_status(ctx.client.post(f"{ctx.api}/auth/refresh", json={"refresh_token": ""}), 422)


# --- Roles -----------------------------------------------------------------

VENUE_STAFF_DASHBOARD = "/venues/dashboard/venue-staff"


@check("TC-RBAC-006", "A venue-staff-only endpoint refuses an attendee")
def _(ctx: Context) -> None:
    response = ctx.client.get(f"{ctx.api}{VENUE_STAFF_DASHBOARD}", headers=ctx.shared("attendee").headers)
    expect_status(response, 403)
    expect("venue_staff" in response.json().get("detail", ""), "403 detail does not name venue_staff")


@check("TC-RBAC-007", "The same endpoint opens for venue staff")
def _(ctx: Context) -> None:
    response = ctx.client.get(f"{ctx.api}{VENUE_STAFF_DASHBOARD}", headers=ctx.shared("venue_staff").headers)
    expect_status(response, 200)


@check("TC-ROLE-006", "Switching to a role the account doesn't hold is 403")
def _(ctx: Context) -> None:
    response = ctx.client.post(
        f"{ctx.api}/auth/active-role",
        json={"role": "attendee"},
        headers=ctx.shared("event_coordinator").headers,
    )
    expect_status(response, 403)
    expect_detail(response, "You do not hold the 'attendee' role.")


@check("TC-ROLE-007", "Switching roles without a token is 401")
def _(ctx: Context) -> None:
    expect_status(ctx.client.post(f"{ctx.api}/auth/active-role", json={"role": "venue_staff"}), 401)


@check("TC-ROLE-008", "Login and /auth/me both list every role the account holds")
def _(ctx: Context) -> None:
    session = ctx.shared("event_coordinator")
    expected = {"event_coordinator", "venue_staff"}
    expect(set(session.body["profile"]["roles"]) == expected, f"login roles: {session.body['profile']['roles']}")
    me = ctx.client.get(f"{ctx.api}/auth/me", headers=session.headers)
    expect_status(me, 200)
    expect(set(me.json()["roles"]) == expected, f"/auth/me roles: {me.json()['roles']}")


@check("TC-ROLE-017", "A held but inactive role doesn't open its endpoint")
def _(ctx: Context) -> None:
    response = ctx.client.get(
        f"{ctx.api}{VENUE_STAFF_DASHBOARD}", headers=ctx.shared("event_coordinator").headers
    )
    expect_status(response, 403)


@check("TC-ROLE-018", "The endpoint opens after switching role and closes after switching back")
def _(ctx: Context) -> None:
    session = ctx.login("event_coordinator")  # its own session: switching must not touch shared ones

    def switch(role: str) -> None:
        response = ctx.client.post(f"{ctx.api}/auth/active-role", json={"role": role}, headers=session.headers)
        expect_status(response, 200)

    switch("venue_staff")
    expect_status(ctx.client.get(f"{ctx.api}{VENUE_STAFF_DASHBOARD}", headers=session.headers), 200)
    switch("event_coordinator")
    expect_status(ctx.client.get(f"{ctx.api}{VENUE_STAFF_DASHBOARD}", headers=session.headers), 403)


# --- Coordinator dashboard (SCRUM-72) --------------------------------------

COORDINATOR_DASHBOARD = "/events/dashboard/coordinator"
ACTIVE_COORDINATOR_STATUSES = {"under_review", "returned", "planning", "confirmed"}
# supabase/seed.sql: review fixtures assigned to coordinator@connectsphere.dev.
REVIEW_FIXTURES = {"e0000000-0000-4000-8000-000000000201", "e0000000-0000-4000-8000-000000000202"}


def coordinator_dashboard(ctx: Context) -> dict:
    response = ctx.client.get(f"{ctx.api}{COORDINATOR_DASHBOARD}", headers=ctx.shared("event_coordinator").headers)
    expect_status(response, 200)
    return response.json()


@check("TC-DASH-013", "Coordinator dashboard returns only the caller's active events")
def _(ctx: Context) -> None:
    body = coordinator_dashboard(ctx)
    listed = {event["event_id"]: event for event in body["active_events"]}
    statuses = {event["status"] for event in listed.values()}
    expect(statuses <= ACTIVE_COORDINATOR_STATUSES, f"inactive statuses listed: {statuses - ACTIVE_COORDINATOR_STATUSES}")
    # A fixture moved to a terminal status by an un-reset manual run is correctly absent.
    missing = REVIEW_FIXTURES - set(listed)
    expect(not missing, f"fixture events missing (reset them with event_review_fixture_reset.sql?): {missing}")
    stray = {item["event_id"] for item in body["action_items"]} - set(listed)
    expect(not stray, f"action items for events not listed: {stray}")


@check("TC-DASH-014", "Every event under review is one action item; a returned one is none")
def _(ctx: Context) -> None:
    body = coordinator_dashboard(ctx)
    kinds_by_event: dict[str, list[str]] = {}
    for item in body["action_items"]:
        kinds_by_event.setdefault(item["event_id"], []).append(item["kind"])
    for event in body["active_events"]:
        kinds = kinds_by_event.get(event["event_id"], [])
        if event["status"] == "under_review":
            expect(
                len(kinds) == 1 and kinds[0] in {"awaiting_review", "resubmitted"},
                f"{event['event_id']} under review has action items {kinds}",
            )
        if event["status"] == "returned":
            expect(not kinds, f"{event['event_id']} is returned but has action items {kinds}")


@check("TC-DASH-015", "A coordinator's dashboard says nothing about unassigned events")
def _(ctx: Context) -> None:
    # Unassigned events are the Event Coordinator Lead's queue (REQUIREMENTS §6.5).
    body = coordinator_dashboard(ctx)
    expect(set(body) == {"action_items", "active_events"}, f"unexpected fields: {sorted(body)}")


@check("TC-DASH-016", "An organiser can't read the coordinator dashboard")
def _(ctx: Context) -> None:
    response = ctx.client.get(f"{ctx.api}{COORDINATOR_DASHBOARD}", headers=ctx.shared("event_organiser").headers)
    expect_status(response, 403)


@check("TC-DASH-017", "The coordinator dashboard closes while acting as venue staff and reopens after")
def _(ctx: Context) -> None:
    session = ctx.login("event_coordinator")  # its own session: switching must not touch shared ones

    def switch(role: str) -> None:
        response = ctx.client.post(f"{ctx.api}/auth/active-role", json={"role": role}, headers=session.headers)
        expect_status(response, 200)

    switch("venue_staff")
    expect_status(ctx.client.get(f"{ctx.api}{COORDINATOR_DASHBOARD}", headers=session.headers), 403)
    switch("event_coordinator")
    expect_status(ctx.client.get(f"{ctx.api}{COORDINATOR_DASHBOARD}", headers=session.headers), 200)


@check("TC-DASH-018", "The coordinator dashboard without a token is 401")
def _(ctx: Context) -> None:
    expect_status(ctx.client.get(f"{ctx.api}{COORDINATOR_DASHBOARD}"), 401)


# --- Sign-up (SCRUM-80) ----------------------------------------------------


FIXTURE_EVENT = "e0000000-0000-4000-8000-000000000201"  # supabase/seed.sql: under_review, assigned


@check("TC-CMT-009", "The organiser and the assigned coordinator both read the event's comment thread")
def _(ctx: Context) -> None:
    for role in ("event_organiser", "event_coordinator"):
        response = ctx.client.get(f"{ctx.api}/events/{FIXTURE_EVENT}/comments", headers=ctx.shared(role).headers)
        expect_status(response, 200)
        comments = response.json().get("comments")
        expect(isinstance(comments, list), f"{role}: response has no comments list")
        for comment in comments:
            expect({"id", "body", "created_at", "author"} <= comment.keys(), f"{role}: comment is missing fields")


@check("TC-CMT-008", "Venue staff, tech support and attendees can neither read nor post comments")
def _(ctx: Context) -> None:
    url = f"{ctx.api}/events/{FIXTURE_EVENT}/comments"
    for role in ("venue_staff", "tech_support", "attendee"):
        headers = ctx.shared(role).headers
        expect_status(ctx.client.get(url, headers=headers), 403)
        expect_status(ctx.client.post(url, headers=headers, json={"body": "live check"}), 403)


# --- Venue booking request (SCRUM-19) ------------------------------------------

BOOKINGS = "/venue-bookings"
PLANNING_FIXTURE = "e0000000-0000-4000-8000-000000000202"  # supabase/seed.sql: planning, already holds a venue
INNOVATION_LAB = "b0000000-0000-4000-8000-000000000006"
HERITAGE_HALL = "b0000000-0000-4000-8000-000000000007"
VENUE_STAFF_ID = "a0000000-0000-4000-8000-000000000003"
THROWAWAY_EVENT_PREFIX = "live-check "
THROWAWAY_BLOCK_NOTE = "live-check"


def throwaway_event(ctx: Context, case: str, starts: str, ends: str, *, status: str = "planning",
                    assigned: bool = True) -> str:
    """A throwaway event in 2031, deleted with its bookings when the run ends."""
    coordinator = "'a0000000-0000-4000-8000-000000000002'" if assigned else "null"
    rows = db_query(
        "insert into public.events (organiser_id, coordinator_id, status, name, starts_at, ends_at) values "
        f"('a0000000-0000-4000-8000-000000000001', {coordinator}, '{status}', "
        f"'{THROWAWAY_EVENT_PREFIX}{ctx.run_id} {case}', '{starts}', '{ends}') returning id"
    )
    return rows[0]["id"]


def delete_throwaway_bookings() -> int:
    """Deletes the booking checks' events (their bookings first: that foreign key
    restricts) and blocks. Their history and notifications cascade."""
    like = f"'{THROWAWAY_EVENT_PREFIX}%'"
    db_query(f"delete from public.venue_bookings where event_id in (select id from public.events where name like {like})")
    db_query(f"delete from public.venue_blocks where notes = '{THROWAWAY_BLOCK_NOTE}'")
    return len(db_query(f"delete from public.events where name like {like} returning id"))


def request_venue(ctx: Context, session: Session, event_id: str, venue_id: str, note: str | None = None):
    return ctx.client.post(f"{ctx.api}{BOOKINGS}", headers=session.headers,
                           json={"event_id": event_id, "venue_id": venue_id, "note": note})


@check("TC-BOOK-001", "Requesting a free venue holds it for the event's period and notifies venue staff", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "001", "2031-05-20 14:00+08", "2031-05-20 17:00+08")
    coordinator = ctx.shared("event_coordinator")

    response = request_venue(ctx, coordinator, event_id, INNOVATION_LAB, "  Early access at 13:00  ")
    expect_status(response, 201)
    body = response.json()
    expect(body["status"] == "held" and body["note"] == "Early access at 13:00", f"unexpected booking {body}")

    [stored] = db_query(
        "select status::text as status, lower(occupied_period) = '2031-05-20 14:00+08' "
        "and upper(occupied_period) = '2031-05-20 17:00+08' as event_period, request_note "
        f"from public.venue_bookings where id = '{body['id']}'"
    )
    expect(stored["status"] == "held" and stored["event_period"] is True, f"stored booking is {stored}")
    notified = db_query(
        "select recipient_id from public.notifications "
        f"where event_id = '{event_id}' and type = 'venue_booking_requested'"
    )
    expect([row["recipient_id"] for row in notified] == [VENUE_STAFF_ID],
           f"venue_booking_requested went to {notified} (want venue staff only, not the coordinator)")

    event = ctx.client.get(f"{ctx.api}/events/{event_id}", headers=coordinator.headers).json()
    expect((event.get("venue_booking") or {}).get("status") == "held", f"event shows {event.get('venue_booking')}")
    queue = ctx.client.get(f"{ctx.api}/venues/dashboard/venue-staff", headers=ctx.shared("venue_staff").headers).json()
    expect(any(b["id"] == body["id"] for b in queue["pending_holds"]), "the hold is not in the venue-staff queue")


@check("TC-BOOK-002", "An overlapping request is refused; a back-to-back one is accepted", needs_db=True)
def _(ctx: Context) -> None:
    first = throwaway_event(ctx, "002-x", "2031-05-21 14:00+08", "2031-05-21 17:00+08")
    overlapping = throwaway_event(ctx, "002-y", "2031-05-21 16:00+08", "2031-05-21 18:00+08")
    back_to_back = throwaway_event(ctx, "002-z", "2031-05-21 17:00+08", "2031-05-21 19:00+08")
    coordinator = ctx.shared("event_coordinator")

    expect_status(request_venue(ctx, coordinator, first, INNOVATION_LAB), 201)
    refused = request_venue(ctx, coordinator, overlapping, INNOVATION_LAB)
    expect_status(refused, 409)
    expect_detail(refused, "Venue already held for this time by another event.")
    expect_status(request_venue(ctx, coordinator, back_to_back, INNOVATION_LAB), 201)


@check("TC-BOOK-003", "A request overlapping a venue block is refused", needs_db=True)
def _(ctx: Context) -> None:
    db_query(
        "insert into public.venue_blocks (venue_id, blocked_period, reason, notes) values "
        f"('{HERITAGE_HALL}', tstzrange('2031-05-22 10:00+08', '2031-05-22 12:00+08', '[)'), "
        f"'maintenance', '{THROWAWAY_BLOCK_NOTE}')"
    )
    event_id = throwaway_event(ctx, "003", "2031-05-22 11:00+08", "2031-05-22 13:00+08")

    response = request_venue(ctx, ctx.shared("event_coordinator"), event_id, HERITAGE_HALL)
    expect_status(response, 409)
    expect_detail(response, "Venue blocked for this time.")


@check("TC-BOOK-004", "An event that already holds a venue can't request another")
def _(ctx: Context) -> None:
    response = request_venue(ctx, ctx.shared("event_coordinator"), PLANNING_FIXTURE, HERITAGE_HALL)
    expect_status(response, 409)
    expect_detail(response, "This event already has a venue booking.")


@check("TC-BOOK-005", "A returned or under-review event can't request a venue", needs_db=True)
def _(ctx: Context) -> None:
    returned = throwaway_event(ctx, "005", "2031-05-23 09:00+08", "2031-05-23 10:00+08", status="returned")
    coordinator = ctx.shared("event_coordinator")

    response = request_venue(ctx, coordinator, returned, HERITAGE_HALL)
    expect_status(response, 409)
    expect_detail(response, "Requirements are still being amended.")
    response = request_venue(ctx, coordinator, FIXTURE_EVENT, HERITAGE_HALL)
    expect_status(response, 409)
    expect_detail(response, "Cannot request a venue for an event that is under review.")


@check("TC-BOOK-006", "Only the event's assigned coordinator, acting as coordinator, can request", needs_db=True)
def _(ctx: Context) -> None:
    unassigned = throwaway_event(ctx, "006-other", "2031-05-24 09:00+08", "2031-05-24 10:00+08", assigned=False)
    mine = throwaway_event(ctx, "006-mine", "2031-05-24 11:00+08", "2031-05-24 12:00+08")
    expect_status(request_venue(ctx, ctx.shared("event_coordinator"), unassigned, HERITAGE_HALL), 403)
    for role in ("event_organiser", "venue_staff", "tech_support", "attendee"):
        expect_status(request_venue(ctx, ctx.shared(role), mine, HERITAGE_HALL), 403)

    # SCRUM-76: the seeded coordinator also holds venue_staff; acting as it, their own event is refused.
    session = ctx.login("event_coordinator")
    switched = ctx.client.post(f"{ctx.api}/auth/active-role", json={"role": "venue_staff"}, headers=session.headers)
    expect_status(switched, 200)
    expect_status(request_venue(ctx, session, mine, HERITAGE_HALL), 403)
    expect(not db_query(f"select 1 from public.venue_bookings where event_id in ('{unassigned}', '{mine}')"),
           "a refused request left a booking behind")


@check("TC-BOOK-007", "Two simultaneous overlapping requests leave exactly one hold", needs_db=True)
def _(ctx: Context) -> None:
    from concurrent.futures import ThreadPoolExecutor

    left = throwaway_event(ctx, "007-a", "2031-05-25 14:00+08", "2031-05-25 17:00+08")
    right = throwaway_event(ctx, "007-b", "2031-05-25 15:00+08", "2031-05-25 18:00+08")
    coordinator = ctx.shared("event_coordinator")

    # Separate clients so the two requests really are in flight together.
    def fire(event_id: str) -> int:
        with httpx.Client(timeout=30) as client:
            return client.post(f"{ctx.api}{BOOKINGS}", headers=coordinator.headers,
                               json={"event_id": event_id, "venue_id": INNOVATION_LAB}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(fire, [left, right]))
    expect(codes == [201, 409], f"expected one 201 and one 409, got {codes}")
    [count] = db_query(
        "select count(*)::int as n from public.venue_bookings "
        f"where event_id in ('{left}', '{right}') and status = 'held'"
    )
    expect(count["n"] == 1, f"{count['n']} holds exist")

# --- Equipment requests (SCRUM-45) ----------------------------------------

PROJECTOR_ID = "b0000000-0000-4000-8000-000000000001"  # supabase/seed.sql: 4K Projector, 4 in total
EQUIPMENT_REQUESTS = "/equipment/requests"
LIVE_CHECK_NOTE = "live-check SCRUM-45"  # marks the lines TC-EQR-002 writes, so only those are deleted


def delete_live_check_lines() -> None:
    db_query(
        "delete from public.equipment_requests "
        f"where event_id = '{PLANNING_FIXTURE}' and technical_requirements like '{LIVE_CHECK_NOTE}%'"
    )


def submit_equipment(ctx: Context, session: Session, event_id: str, items: list) -> httpx.Response:
    return ctx.client.post(
        f"{ctx.api}{EQUIPMENT_REQUESTS}", json={"event_id": event_id, "items": items}, headers=session.headers,
    )


@check("TC-EQR-001", "Coordinators and tech support read the equipment catalogue; organisers can't")
def _(ctx: Context) -> None:
    for role in ("event_coordinator", "tech_support"):
        response = ctx.client.get(f"{ctx.api}/equipment/catalogue", headers=ctx.shared(role).headers)
        expect_status(response, 200)
        items = response.json()["items"]
        expect(any(item["equipment_id"] == PROJECTOR_ID for item in items), f"{role}: seeded projector missing")
        expect(all({"name", "total_quantity"} <= item.keys() for item in items), f"{role}: item fields missing")
    expect_status(ctx.client.get(f"{ctx.api}/equipment/catalogue", headers=ctx.shared("event_organiser").headers), 403)


@check(
    "TC-EQR-002",
    "A submission on a planning event is saved pending, above inventory, and visible to both sides",
    needs_db=True,
)
def _(ctx: Context) -> None:
    coordinator = ctx.shared("event_coordinator")
    note = f"{LIVE_CHECK_NOTE} {ctx.run_id}: HDMI to the lectern"
    try:
        # 5 is above the 4 that exist: EQ-R1 allows it.
        response = submit_equipment(ctx, coordinator, PLANNING_FIXTURE, [
            {"equipment_id": PROJECTOR_ID, "quantity": 5, "technical_requirements": note},
        ])
        expect_status(response, 201)
        [line] = response.json()["lines"]
        expect(line["status"] == "pending", f"status is {line['status']!r}")
        expect(line["quantity"] == 5, f"quantity is {line['quantity']}")

        mine = ctx.client.get(f"{ctx.api}{EQUIPMENT_REQUESTS}/event/{PLANNING_FIXTURE}", headers=coordinator.headers)
        expect_status(mine, 200)
        expect(any(l["id"] == line["id"] for l in mine.json()["lines"]), "the coordinator doesn't see the line")

        queue = ctx.client.get(f"{ctx.api}{EQUIPMENT_REQUESTS}/pending", headers=ctx.shared("tech_support").headers)
        expect_status(queue, 200)
        seen = [l for l in queue.json()["lines"] if l["id"] == line["id"]]
        expect(seen, "tech support don't see the line")
        expect(seen[0]["technical_requirements"] == note, "tech support don't see the technical requirements")
        expect(seen[0]["event_name"], "tech support line has no event name")

        stored = db_query(f"select status::text as status, quantity from public.equipment_requests where id = '{line['id']}'")
        expect(stored == [{"status": "pending", "quantity": 5}], f"stored row is {stored}")
    finally:
        delete_live_check_lines()


@check("TC-EQR-004", "Quantities that aren't whole numbers of at least 1, and empty submissions, are refused")
def _(ctx: Context) -> None:
    coordinator = ctx.shared("event_coordinator")
    for quantity in (0, -1, 2.5, "2"):
        response = submit_equipment(ctx, coordinator, PLANNING_FIXTURE, [{"equipment_id": PROJECTOR_ID, "quantity": quantity}])
        expect(response.status_code == 422, f"quantity {quantity!r} answered {response.status_code}")
    expect_status(submit_equipment(ctx, coordinator, PLANNING_FIXTURE, []), 422)
    too_long = [{"equipment_id": PROJECTOR_ID, "quantity": 1, "technical_requirements": "x" * 1001}]
    expect_status(submit_equipment(ctx, coordinator, PLANNING_FIXTURE, too_long), 422)


@check("TC-EQR-008", "An event that isn't in planning refuses an equipment request")
def _(ctx: Context) -> None:
    response = submit_equipment(ctx, ctx.shared("event_coordinator"), FIXTURE_EVENT, [{"equipment_id": PROJECTOR_ID, "quantity": 1}])
    expect_status(response, 409)
    expect("planning" in response.json().get("detail", ""), f"detail is {response.json().get('detail')!r}")


@check("TC-EQR-009", "Only a coordinator submits and only tech support see the queue, by active role")
def _(ctx: Context) -> None:
    item = [{"equipment_id": PROJECTOR_ID, "quantity": 1}]
    for role in ("event_organiser", "venue_staff", "tech_support", "attendee"):
        expect_status(submit_equipment(ctx, ctx.shared(role), PLANNING_FIXTURE, item), 403)
    expect_status(
        ctx.client.get(f"{ctx.api}{EQUIPMENT_REQUESTS}/pending", headers=ctx.shared("event_coordinator").headers), 403,
    )
    # The seeded coordinator also holds venue_staff: acting as it closes submission.
    session = ctx.login("event_coordinator")
    response = ctx.client.post(f"{ctx.api}/auth/active-role", json={"role": "venue_staff"}, headers=session.headers)
    expect_status(response, 200)
    expect_status(submit_equipment(ctx, session, PLANNING_FIXTURE, item), 403)


def expect_field_error(response: httpx.Response, field_name: str, msg: str | None = None) -> None:
    expect_status(response, 422)
    errors = [e for e in response.json().get("detail", []) if e.get("loc") == ["body", field_name]]
    expect(errors, f"no 422 error on body.{field_name}: {response.text[:200]}")
    if msg is not None:
        expect(errors[0].get("msg") == msg, f"body.{field_name} msg is {errors[0].get('msg')!r}")


def stored_account(email: str) -> dict:
    """The auth.users, profiles and user_roles rows behind an email."""
    rows = db_query(
        "select u.email, u.email_confirmed_at is not null as confirmed, p.role::text as role, "
        "p.organisation_name, p.phone_number, "
        "(select string_agg(r.role::text, ',' order by r.role) from public.user_roles r "
        " where r.profile_id = p.id) as roles "
        f"from auth.users u join public.profiles p on p.id = u.id where u.email = '{email}'"
    )
    expect(len(rows) == 1, f"expected one stored account for {email}, found {len(rows)}")
    return rows[0]


@check("TC-AUTH-037", "Sign-up creates a confirmed organiser with its profile and role rows", creates_accounts=True)
def _(ctx: Context) -> None:
    email = ctx.throwaway_email("037")
    response = ctx.signup(email=email, organisation_name="SMU Events Club")
    expect_status(response, 201)
    body = response.json()
    expect(body["role"] == "event_organiser", f"response role is {body['role']!r}")
    expect(body["roles"] == ["event_organiser"], f"response roles are {body['roles']}")

    stored = stored_account(email)
    expect(stored["role"] == "event_organiser", f"profiles.role is {stored['role']!r}")
    expect(stored["roles"] == "event_organiser", f"user_roles holds {stored['roles']!r}")
    expect(stored["organisation_name"] == "SMU Events Club", "organisation not stored")
    expect(stored["phone_number"] == "+65 9123 4567", "phone number not stored")
    expect(stored["confirmed"] is True, "email_confirmed_at is not set (ADR-0003)")


@check("TC-AUTH-038", "A new organiser can log in straight away", creates_accounts=True)
def _(ctx: Context) -> None:
    email = ctx.throwaway_email("038")
    expect_status(ctx.signup(email=email), 201)
    session = ctx.login("event_organiser", email=email, password=THROWAWAY_PASSWORD)
    expect(session.body["profile"]["role"] == "event_organiser", "logged in with the wrong role")


@check("TC-AUTH-040", "A malformed email is refused by the API with no account made")
def _(ctx: Context) -> None:
    for bad in ("not-an-email", "olivia@", "@connectsphere.dev"):
        expect_field_error(ctx.signup(email=bad), "email")


@check("TC-AUTH-041", "A password that breaks the rule is refused; exactly 8 characters is accepted", creates_accounts=True)
def _(ctx: Context) -> None:
    too_short, no_digit, no_letter = "Abc" + "1234", "Pass" + "word", "1234" + "5678"
    for bad in (too_short, no_digit, no_letter):
        expect_field_error(ctx.signup(email=ctx.throwaway_email("041-refused"), password=bad), "password", PASSWORD_RULE)
    expect_status(ctx.signup(email=ctx.throwaway_email("041"), password="a" * 7 + "1"), 201)


@check("TC-AUTH-042", "An email that already has an account is refused with 409")
def _(ctx: Context) -> None:
    response = ctx.signup(email=ACCOUNTS["event_organiser"])
    expect_status(response, 409)
    expect_detail(response, "An account with this email already exists.")


@check("TC-AUTH-043", "Sign-up refuses every role but event_organiser")
def _(ctx: Context) -> None:
    for role in ("event_coordinator", "venue_staff", "tech_support", "attendee"):
        expect_field_error(ctx.signup(email=ctx.throwaway_email("043"), role=role), "role")


@check("TC-AUTH-044", "A blank phone number is stored as NULL", creates_accounts=True)
def _(ctx: Context) -> None:
    email = ctx.throwaway_email("044")
    response = ctx.signup(email=email, phone_number="   ")
    expect_status(response, 201)
    expect(response.json()["phone_number"] is None, "response phone_number is not null")
    expect(stored_account(email)["phone_number"] is None, "profiles.phone_number is not NULL")


@check("TC-AUTH-047", "An email padded with spaces is stored trimmed and logs in", creates_accounts=True)
def _(ctx: Context) -> None:
    email = ctx.throwaway_email("047")
    response = ctx.signup(email=f"  {email}  ")
    expect_status(response, 201)
    expect(response.json()["email"] == email, f"response email is {response.json()['email']!r}")
    stored_account(email)
    ctx.login("event_organiser", email=email, password=THROWAWAY_PASSWORD)


# --- Helpers ---------------------------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _jwt_claims(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def _sign_hs256(claims: dict, key: bytes) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64url(json.dumps(claims).encode())
    signature = hmac.new(key, f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(signature)}"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


# --- Running ---------------------------------------------------------------


@dataclass
class Result:
    case_id: str
    title: str
    status: str  # "pass", "fail" or "blocked"
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "pass"


def run_api_checks(ctx: Context, keyword: str | None, skip_accounts: bool) -> list[Result]:
    results = []
    for item in API_CHECKS:
        if keyword and keyword.lower() not in f"{item.case_id} {item.title}".lower():
            continue
        if item.creates_accounts and skip_accounts:
            print(f"  SKIP  {item.case_id:<28} {item.title} (creates an account; needs the database)")
            continue
        if item.needs_db and skip_accounts:
            print(f"  SKIP  {item.case_id:<28} {item.title} (compares against the database)")
            continue
        try:
            item.run(ctx)
            results.append(Result(item.case_id, item.title, "pass"))
        except CheckBlocked as blocked:
            results.append(Result(item.case_id, item.title, "blocked", str(blocked)))
        except CheckFailed as failure:
            results.append(Result(item.case_id, item.title, "fail", str(failure)))
        except Exception:  # a crash in a check is a failure, not a reason to stop the run
            results.append(Result(item.case_id, item.title, "fail", traceback.format_exc(limit=1).strip()))
        print_result(results[-1])
    return results


def _supabase_query(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["supabase", "db", "query", "--linked", "--project-ref", PROJECT_REF, "-o", "json", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def db_query(sql: str) -> list[dict]:
    completed = _supabase_query(sql)
    if completed.returncode != 0:
        raise CheckFailed(f"database query failed: {_cli_error(completed.stderr)}")
    return json.loads(completed.stdout[completed.stdout.index("{"):]).get("rows", [])


def delete_throwaway_accounts() -> int:
    """Deletes every sign-up check account; auth.users cascades to what it owns."""
    rows = db_query(
        f"delete from auth.users where email like '{THROWAWAY_PREFIX}%{THROWAWAY_DOMAIN}' returning email"
    )
    return len(rows)


def run_db_checks(keyword: str | None) -> list[Result]:
    results = []
    for script, cases in DB_SCRIPTS:
        if keyword and keyword.lower() not in f"{script} {cases}".lower():
            continue
        completed = _supabase_query("-f", str(VERIFICATION_DIR / script))
        title = f"{cases}: supabase/verification/{script}"
        if completed.returncode != 0:
            results.append(Result(script, title, "fail", _cli_error(completed.stderr)))
        else:
            failed = _failed_rows(completed.stdout)
            results.append(Result(script, title, "fail" if failed else "pass", "; ".join(failed)))
        print_result(results[-1])
    return results


def _cli_error(stderr: str) -> str:
    lines = [line for line in stderr.splitlines() if line.strip() and "new version" not in line
             and "recommend updating" not in line and "Try rerunning" not in line and "Initialising" not in line]
    return next((line for line in lines if "ERROR" in line), " ".join(lines))[:300]


def _failed_rows(stdout: str) -> list[str]:
    """Scripts either raise on failure or return rows with a boolean `ok` column."""
    rows = json.loads(stdout[stdout.index("{"):]).get("rows", [])
    failed = []
    for row in rows:
        values = list(row.values())
        if False in values:
            failed.append(str(values[0]))
    return failed


def print_result(result: Result) -> None:
    mark = {"pass": "PASS", "fail": "FAIL", "blocked": "BLOCK"}[result.status]
    print(f"  {mark:<5} {result.case_id:<28} {result.title}")
    if result.detail:
        print(f"        {result.detail}")


def summary(results: list[Result]) -> str:
    passed = sum(r.status == "pass" for r in results)
    blocked = sum(r.status == "blocked" for r in results)
    text = f"{passed}/{len(results)} passed"
    return text + (f", {blocked} blocked" if blocked else "")


def write_run_log(results: list[Result], api: str, started: dt.datetime, duration: float) -> Path:
    commit = git("rev-parse", "--short", "HEAD")
    dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{started:%Y-%m-%d-%H%M}-api-db-{commit}.md"

    lines = [
        f"# Automated live checks — {started:%Y-%m-%d %H:%M} SGT",
        "",
        "| | |",
        "|---|---|",
        "| Method | `backend/scripts/verify_live.py` (API + rolled-back SQL) |",
        f"| Result | **{summary(results)}** |",
        f"| Commit | `{commit}`{' + uncommitted changes' if dirty else ''} on `{git('branch', '--show-current')}` |",
        f"| Backend | `{api}` |",
        f"| Database | live Supabase project `{PROJECT_REF}`, via `supabase db query` |",
        f"| Run by | {git('config', 'user.name') or 'unknown'} |",
        f"| Duration | {duration:.0f}s |",
        "",
        "| Case | Check | Result | Detail |",
        "|---|---|---|---|",
    ]
    for r in results:
        detail = r.detail.replace("|", "\\|").replace("\n", " ")
        label = {"pass": "Pass", "fail": "**Fail**", "blocked": "Blocked"}[r.status]
        lines.append(f"| {r.case_id} | {r.title} | {label} | {detail} |")
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://localhost:8000/api/v1", help="backend API base URL")
    parser.add_argument("--record", action="store_true", help="write a run log to docs/test-cases/runs/")
    parser.add_argument(
        "--skip-db", action="store_true", help="skip the supabase/verification scripts and the sign-up checks"
    )
    parser.add_argument("--skip-api", action="store_true", help="skip the API checks")
    parser.add_argument("-k", dest="keyword", help="only checks whose ID, title or script contains this")
    args = parser.parse_args()

    started = dt.datetime.now(SGT)
    clock = time.monotonic()
    results: list[Result] = []

    if not args.skip_api:
        with httpx.Client(timeout=30) as client:
            try:
                client.get(args.api.rsplit("/api/", 1)[0] + "/health").raise_for_status()
            except httpx.HTTPError as error:
                print(f"Backend not reachable at {args.api} ({error}). Start it, or pass --api.")
                return 2
            ctx = Context(args.api, client, run_id=f"{started:%Y%m%d%H%M%S}")
            print(f"API checks against {args.api}")
            try:
                if not args.skip_db:
                    left_over = delete_throwaway_accounts()
                    if left_over:
                        print(f"  (deleted {left_over} sign-up check account(s) left by an earlier run)")
                    left_over = delete_throwaway_bookings()
                    if left_over:
                        print(f"  (deleted {left_over} booking check event(s) left by an earlier run)")
                results += run_api_checks(ctx, args.keyword, skip_accounts=args.skip_db)
            finally:
                ctx.logout_all()
                if not args.skip_db:
                    delete_throwaway_accounts()
                    delete_throwaway_bookings()

    if not args.skip_db:
        print(f"Database checks (rolled back) on Supabase project {PROJECT_REF}")
        results += run_db_checks(args.keyword)

    failed = [r for r in results if r.status != "pass"]
    print(f"\n{summary(results)}")
    if args.record and results:
        path = write_run_log(results, args.api, started, time.monotonic() - clock)
        print(f"Run log: {path.relative_to(REPO_ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
