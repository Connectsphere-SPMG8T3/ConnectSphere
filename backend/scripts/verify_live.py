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
Venue deactivation checks (SCRUM-64) create throwaway venues named
"live-check venue ...", deleted the same way; seeded venues are never changed.

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
# Seeded staff for the W7 roles (CR-103 AC5, 12 AC12). Kept out of ACCOUNTS,
# whose loops assert a denial for every role in it.
W7_STAFF_ACCOUNTS = {
    "safety_officer": "safety.officer@connectsphere.dev",
    "event_coordinator_lead": "coordinator.lead@connectsphere.dev",
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
    ("send_for_safety_check.sql", "TC-SAFE-010–015"),
    ("safety_decision_checks.sql", "TC-SDEC-003, 009–011, 015–017 (database half); CR-104 helper paths"),
    ("event_amendment_checks.sql", "TC-AMD-001, 005, 008 (database half)"),
    ("event_comment_checks.sql", "TC-CMT-008, 009, 010, 011, 013 (database half)"),
    ("venue_booking_request_checks.sql", "TC-BOOK-001–006 (database half)"),
    ("hold_expiry_checks.sql", "TC-HOLD-001–003 (database half: bounds, job, notices, approval race)"),
    ("event_space_checks.sql", "TC-SPACE-003, 005, 009; TC-HOLD-009 (overdue space holds); TC-BOOK-031–033 (CR-97 database half)"),
    ("equipment_request_checks.sql", "TC-EQR-002, 003, 006, 007, 008, 009 (database half)"),
    ("venue_edit_checks.sql", "TC-VENUE-058, 059, 061 (database half)"),
    ("venue_booking_reject_checks.sql", "TC-BOOK-023"),
    ("lead_assignment_checks.sql", "CR-101 (database half: assignment columns, reassign_event)"),
    ("venue_deactivation_checks.sql", "TC-VENUE-070 (SCRUM-64 database half); D33"),
    ("booking_conflict_checks.sql", "TC-BOOK-040 (SCRUM-21 database half: occupied window, venue_conflicts)"),
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
            json={"email": email or ACCOUNTS.get(role) or W7_STAFF_ACCOUNTS[role], "password": password},
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


# --- SCRUM-82: read-only safety checks ----------------------------------------
SAFE_EVENT = "e0000000-0000-4000-8000-000000000202"


@check("TC-SAFE-001", "Only an active coordinator can send for safety check")
def _(ctx: Context) -> None:
    for role in ("event_organiser", "venue_staff", "tech_support"):
        response = ctx.client.post(f"{ctx.api}/events/{SAFE_EVENT}/send-for-safety-check", headers=ctx.shared(role).headers)
        expect_status(response, 403)


def safety_fixture(ctx: Context) -> tuple[Session, dict]:
    session = ctx.shared("event_coordinator")
    response = ctx.client.get(f"{ctx.api}/events/{SAFE_EVENT}", headers=session.headers)
    expect_status(response, 200)
    event = response.json()
    if event["status"] != "planning" or (event.get("venue_booking") or {}).get("status") != "held":
        raise CheckBlocked("Fixture drift: needs Planning with its held booking; ask before event_review_fixture_reset.sql")
    return session, event


@check("TC-SAFE-002", "An unapproved booking blocks send without changing data")
def _(ctx: Context) -> None:
    session, _ = safety_fixture(ctx)
    response = ctx.client.post(f"{ctx.api}/events/{SAFE_EVENT}/send-for-safety-check", headers=session.headers)
    expect_status(response, 409)
    # CR-97: the seeded event's booking is on its backfilled "Main space", so the reason names it.
    expect("Main space: awaiting venue staff approval." in response.json()["detail"], "Missing booking reason")


@check("TC-SAFE-003", "The coordinator read carries the same missing booking reason")
def _(ctx: Context) -> None:
    _, event = safety_fixture(ctx)
    expect(event["safety_readiness"]["ready"] is False, "Fixture must not be ready")
    expect("Main space: awaiting venue staff approval." in event["safety_readiness"]["missing"], "Missing booking reason")


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
ACTIVE_COORDINATOR_STATUSES = {"under_review", "returned", "planning", "safety_review", "confirmed"}
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


# --- Event Coordinator Lead dashboard (CR-101) ------------------------------
# Read-only: no live check reassigns a seeded event. The reassign success path
# changes shared data and stays manual (TC-LEAD-011).

LEAD_DASHBOARD = "/events/dashboard/lead"
LEAD_ACTIVE_STATUSES = {"under_review", "returned", "planning", "safety_review", "confirmed"}
UNKNOWN_EVENT = "e0000000-0000-4000-8000-0000000009ff"
SOME_COORDINATOR = "a0000000-0000-4000-8000-000000000002"
LEAD_FIXTURE_EVENT = "e0000000-0000-4000-8000-000000000201"  # supabase/seed.sql: under_review, assigned


@check("TC-LEAD-001", "The Lead's dashboard has the queue, active events and coordinator counts, active statuses only")
def _(ctx: Context) -> None:
    response = ctx.client.get(f"{ctx.api}{LEAD_DASHBOARD}", headers=ctx.shared("event_coordinator_lead").headers)
    expect_status(response, 200)
    body = response.json()
    expect(set(body) == {"unassigned", "active_events", "coordinators"}, f"unexpected fields: {sorted(body)}")
    listed = body["unassigned"] + body["active_events"]
    stray = {event["status"] for event in listed} - LEAD_ACTIVE_STATUSES
    expect(not stray, f"inactive statuses listed: {stray}")
    expect(all(event["coordinator"] is None for event in body["unassigned"]), "the queue holds an assigned event")
    expect(all(event["coordinator"] for event in body["active_events"]), "an active event has no coordinator")
    expect(
        all(isinstance(person["active_count"], int) and person["active_count"] >= 0 for person in body["coordinators"]),
        "a coordinator count is not a non-negative integer",
    )


@check("TC-LEAD-002", "Only the Lead can read the Lead dashboard; every other role is 403")
def _(ctx: Context) -> None:
    for role in ACCOUNTS:
        response = ctx.client.get(f"{ctx.api}{LEAD_DASHBOARD}", headers=ctx.shared(role).headers)
        expect(response.status_code == 403, f"{role} got HTTP {response.status_code}, expected 403")


@check("TC-LEAD-003", "Only the Lead can reassign; every other role is 403 and nothing is written")
def _(ctx: Context) -> None:
    for role in ACCOUNTS:
        response = ctx.client.post(
            f"{ctx.api}/events/{LEAD_FIXTURE_EVENT}/reassign",
            headers=ctx.shared(role).headers,
            json={"coordinator_id": SOME_COORDINATOR, "expected_version": 1},
        )
        expect(response.status_code == 403, f"{role} got HTTP {response.status_code}, expected 403")


@check("TC-LEAD-004", "The Lead reassigning an unknown event is 404")
def _(ctx: Context) -> None:
    response = ctx.client.post(
        f"{ctx.api}/events/{UNKNOWN_EVENT}/reassign",
        headers=ctx.shared("event_coordinator_lead").headers,
        json={"coordinator_id": SOME_COORDINATOR, "expected_version": 1},
    )
    expect_status(response, 404)


@check("TC-LEAD-005", "The Lead dashboard and reassign without a token are 401")
def _(ctx: Context) -> None:
    expect_status(ctx.client.get(f"{ctx.api}{LEAD_DASHBOARD}"), 401)
    expect_status(
        ctx.client.post(f"{ctx.api}/events/{UNKNOWN_EVENT}/reassign", json={"coordinator_id": SOME_COORDINATOR, "expected_version": 1}), 401
    )


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
COORDINATOR_ID = "a0000000-0000-4000-8000-000000000002"
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
    deleted = len(db_query(f"delete from public.events where name like {like} returning id"))
    # CR-94's throwaway venues: their layouts, facilities and edit history cascade.
    db_query(f"delete from public.venues where name like {like}")
    return deleted


THROWAWAY_VENUE_PREFIX = "live-check venue "


def throwaway_venue(ctx: Context, case: str) -> str:
    """A throwaway active venue (SCRUM-64), deleted with its bookings when the run ends."""
    rows = db_query(
        "insert into public.venues (name, location, capacity, opens_at, closes_at, is_active) values "
        f"('{THROWAWAY_VENUE_PREFIX}{ctx.run_id} {case}', 'Live check', 50, '08:00', '22:00', true) returning id"
    )
    venue_id = rows[0]["id"]
    db_query(f"insert into public.venue_layouts (venue_id, layout) values ('{venue_id}', 'theatre')")
    return venue_id


def delete_throwaway_venues() -> int:
    """Deletes the deactivation checks' venues, their bookings first (that foreign
    key restricts). Layouts, facilities and edit history cascade."""
    like = f"'{THROWAWAY_VENUE_PREFIX}%'"
    db_query(f"delete from public.venue_bookings where venue_id in (select id from public.venues where name like {like})")
    return len(db_query(f"delete from public.venues where name like {like} returning id"))


def venue_version(venue_id: str) -> int:
    return db_query(f"select version from public.venues where id = '{venue_id}'")[0]["version"]


def deactivate(ctx: Context, session: Session, venue_id: str, **body):
    return ctx.client.post(f"{ctx.api}/venues/{venue_id}/deactivate", headers=session.headers,
                           json={"reason": "long_term_renovation", "note": "live check",
                                 "version": venue_version(venue_id), **body})


def search_includes(ctx: Context, venue_id: str) -> bool:
    found = ctx.client.get(f"{ctx.api}/venues", headers=ctx.shared("event_coordinator").headers)
    expect_status(found, 200)
    return any(r["venue"]["id"] == venue_id and not r["excluded"] for r in found.json()["results"])


def request_venue(ctx: Context, session: Session, event_id: str, venue_id: str, note: str | None = None):
    return ctx.client.post(f"{ctx.api}{BOOKINGS}", headers=session.headers,
                           json={"event_id": event_id, "venue_id": venue_id, "note": note})


@check("TC-VENUE-065", "Venue staff deactivate a venue with a reason; search stops showing it", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "065")
    expect(search_includes(ctx, venue_id), "the new venue is not in search before deactivation")

    response = deactivate(ctx, ctx.shared("venue_staff"), venue_id)
    expect_status(response, 200)
    body = response.json()
    expect(body["saved"] is True and body["venue"]["is_active"] is False, f"unexpected response {body}")
    [stored] = db_query(f"select is_active, inactive_reason::text as reason, inactive_note from public.venues where id = '{venue_id}'")
    expect(stored == {"is_active": False, "reason": "long_term_renovation", "inactive_note": "live check"},
           f"stored venue is {stored}")
    expect(not search_includes(ctx, venue_id), "the deactivated venue still appears in search")


@check("TC-VENUE-066", "Deactivating a booked venue previews, then flags the booking Affected and notifies", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "066")
    event_id = throwaway_event(ctx, "066", "2031-07-01 10:00+08", "2031-07-01 12:00+08")
    expect_status(request_venue(ctx, ctx.shared("event_coordinator"), event_id, venue_id), 201)
    staff = ctx.shared("venue_staff")

    preview = deactivate(ctx, staff, venue_id)
    expect_status(preview, 200)
    body = preview.json()
    expect(body["saved"] is False and [b["event_id"] for b in body["affected"]] == [event_id],
           f"preview is {body}")
    [still] = db_query(f"select is_active from public.venues where id = '{venue_id}'")
    expect(still["is_active"] is True, "the preview deactivated the venue")

    expect_status(deactivate(ctx, staff, venue_id, confirm=True), 200)
    [booking] = db_query(f"select status::text as status, flag::text as flag, flag_reason from public.venue_bookings where event_id = '{event_id}'")
    expect(booking["status"] == "held" and booking["flag"] == "affected"
           and booking["flag_reason"] == "Venue deactivated: long-term renovation — live check",
           f"booking is {booking}")
    notified = db_query(
        f"select recipient_id from public.notifications where event_id = '{event_id}' and type = 'venue_booking_affected'")
    expect([row["recipient_id"] for row in notified] == ["a0000000-0000-4000-8000-000000000002"],
           f"venue_booking_affected went to {notified} (want the coordinator once)")


@check("TC-VENUE-067", "A booking request for an inactive venue is refused", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "067")
    expect_status(deactivate(ctx, ctx.shared("venue_staff"), venue_id), 200)
    event_id = throwaway_event(ctx, "067", "2031-07-02 10:00+08", "2031-07-02 12:00+08")
    refused = request_venue(ctx, ctx.shared("event_coordinator"), event_id, venue_id)
    expect_status(refused, 409)
    expect_detail(refused, "This venue is inactive.")


@check("TC-VENUE-068", "Reactivating restores search and leaves the Affected flag", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "068")
    event_id = throwaway_event(ctx, "068", "2031-07-03 10:00+08", "2031-07-03 12:00+08")
    expect_status(request_venue(ctx, ctx.shared("event_coordinator"), event_id, venue_id), 201)
    staff = ctx.shared("venue_staff")
    expect_status(deactivate(ctx, staff, venue_id, confirm=True), 200)

    response = ctx.client.post(f"{ctx.api}/venues/{venue_id}/reactivate", headers=staff.headers,
                               json={"version": venue_version(venue_id)})
    expect_status(response, 200)
    expect(response.json()["is_active"] is True, f"unexpected response {response.json()}")
    [booking] = db_query(f"select flag::text as flag from public.venue_bookings where event_id = '{event_id}'")
    expect(booking["flag"] == "affected", f"reactivation changed the flag to {booking['flag']}")
    expect(search_includes(ctx, venue_id), "the reactivated venue is not back in search")


@check("TC-VENUE-069", "Only venue staff can deactivate or reactivate; a coordinator gets 403", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "069")
    # coordinator@ also holds venue_staff (SCRUM-74/75) but acts as coordinator here.
    coordinator = ctx.shared("event_coordinator")
    expect_status(deactivate(ctx, coordinator, venue_id), 403)
    response = ctx.client.post(f"{ctx.api}/venues/{venue_id}/reactivate", headers=coordinator.headers,
                               json={"version": venue_version(venue_id)})
    expect_status(response, 403)
    [stored] = db_query(f"select is_active from public.venues where id = '{venue_id}'")
    expect(stored["is_active"] is True, "a refused call changed the venue")


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

# --- Venue edit re-checks bookings (CR-94) ----------------------------------
# Each check builds its own "live-check" venue holding throwaway events, so an
# edit that saves never touches a seeded venue. All of it is deleted with the
# booking checks' events.

CR94_PERIOD = ("2031-06-10 14:00+08", "2031-06-10 17:00+08")
CR94_VENUE = {
    "location": "Live check campus", "capacity": 150,
    "layouts": [{"layout": "theatre", "capacity_for_layout": None}],
    "facilities": ["projector"], "accessibility_features": ["wheelchair_access"],
    "opens_at": "08:00:00", "closes_at": "22:00:00", "description": None,
}


def cr94_venue(ctx: Context, case: str) -> tuple[str, dict]:
    """A throwaway venue shaped like CR94_VENUE: (its id, its full edit payload)."""
    name = f"{THROWAWAY_EVENT_PREFIX}{ctx.run_id} {case}"
    [row] = db_query(
        "with v as (insert into public.venues (name, location, capacity, accessibility_features, opens_at, closes_at) "
        f"values ('{name}', 'Live check campus', 150, '{{wheelchair_access}}', '08:00', '22:00') returning id), "
        "l as (insert into public.venue_layouts (venue_id, layout) select id, 'theatre' from v), "
        "f as (insert into public.venue_facilities (venue_id, facility) select id, 'projector' from v) "
        "select id from v"
    )
    return row["id"], {**CR94_VENUE, "name": name}


def cr94_booking(ctx: Context, case: str, venue_id: str, *, attendance: int = 120, needs: str | None = None) -> tuple[str, str]:
    """A throwaway planning event expecting `attendance` in theatre layout with a
    projector, holding `venue_id`: (event id, booking id)."""
    event_id = throwaway_event(ctx, case, *CR94_PERIOD)
    accessibility = f"'{needs}'" if needs else "null"
    db_query(
        f"update public.events set expected_attendance = {attendance}, layout_preference = 'theatre', "
        f"facilities_required = '{{projector}}', accessibility_needs = {accessibility} where id = '{event_id}'"
    )
    response = request_venue(ctx, ctx.shared("event_coordinator"), event_id, venue_id)
    expect_status(response, 201)
    return event_id, response.json()["id"]


def edit_venue(ctx: Context, venue_id: str, payload: dict) -> dict:
    response = ctx.client.patch(f"{ctx.api}/venues/{venue_id}", headers=ctx.shared("venue_staff").headers, json=payload)
    expect_status(response, 200)
    return response.json()


def warning_for(body: dict, booking_id: str) -> dict | None:
    return next((w for w in body["warnings"] if w["booking_id"] == booking_id), None)


@check("TC-VENUE-076", "Cutting capacity below attendance marks the booking Unsuitable, saving nothing", needs_db=True)
def _(ctx: Context) -> None:
    venue_id, payload = cr94_venue(ctx, "076")
    _, booking_id = cr94_booking(ctx, "076", venue_id)

    body = edit_venue(ctx, venue_id, {**payload, "capacity": 100})

    expect(body["saved"] is False, f"saved={body['saved']} before confirming")
    warning = warning_for(body, booking_id)
    expect(warning is not None, f"no warning for the booking: {body['warnings']}")
    expect(warning["outcome"] == "unsuitable", f"outcome {warning['outcome']}")
    expect([d["code"] for d in warning["details"]] == ["capacity"], f"details {warning['details']}")
    expect(warning["reasons"] == ["Capacity 100 is below the expected attendance of 120."], f"reasons {warning['reasons']}")
    [stored] = db_query(f"select capacity, version from public.venues where id = '{venue_id}'")
    expect(stored == {"capacity": 150, "version": 0}, f"the venue changed before confirming: {stored}")


@check("TC-VENUE-077", "Removing a required facility marks the booking Unsuitable", needs_db=True)
def _(ctx: Context) -> None:
    venue_id, payload = cr94_venue(ctx, "077")
    _, booking_id = cr94_booking(ctx, "077", venue_id)

    warning = warning_for(edit_venue(ctx, venue_id, {**payload, "facilities": []}), booking_id)

    expect(warning is not None and warning["outcome"] == "unsuitable", f"warning {warning}")
    expect(warning["reasons"] == ["Missing facilities this event needs: projector."], f"reasons {warning['reasons']}")


@check("TC-VENUE-078", "Layout and operating-hours changes only warn", needs_db=True)
def _(ctx: Context) -> None:
    venue_id, payload = cr94_venue(ctx, "078")
    _, booking_id = cr94_booking(ctx, "078", venue_id)

    layout = warning_for(
        edit_venue(ctx, venue_id, {**payload, "layouts": [{"layout": "boardroom", "capacity_for_layout": None}]}),
        booking_id,
    )
    hours = warning_for(edit_venue(ctx, venue_id, {**payload, "closes_at": "16:00:00"}), booking_id)

    expect(layout is not None and layout["outcome"] == "warning", f"layout warning {layout}")
    expect([d["code"] for d in layout["details"]] == ["layout_not_supported"], f"layout details {layout['details']}")
    expect(hours is not None and hours["outcome"] == "warning", f"hours warning {hours}")
    expect([d["code"] for d in hours["details"]] == ["outside_operating_hours"], f"hours details {hours['details']}")


@check("TC-VENUE-079", "An accessibility change warns only events that list accessibility needs", needs_db=True)
def _(ctx: Context) -> None:
    venue_id, payload = cr94_venue(ctx, "079")
    _, with_needs = cr94_booking(ctx, "079-a", venue_id, needs="Two wheelchair users")
    # Same period on the same venue would be refused, so the second event is a day later.
    other = throwaway_event(ctx, "079-b", "2031-06-11 14:00+08", "2031-06-11 17:00+08")
    response = request_venue(ctx, ctx.shared("event_coordinator"), other, venue_id)
    expect_status(response, 201)
    without_needs = response.json()["id"]

    body = edit_venue(ctx, venue_id, {**payload, "accessibility_features": []})

    warning = warning_for(body, with_needs)
    expect(warning is not None and warning["outcome"] == "warning", f"warning {warning}")
    expect([d["code"] for d in warning["details"]] == ["accessibility_changed"], f"details {warning['details']}")
    expect(warning_for(body, without_needs) is None, "an event with no accessibility needs was warned")


@check("TC-VENUE-080", "Saving past the warning notifies the coordinator and the other venue staff, not the editor; "
       "the booking is unchanged (TC-VENUE-081)", needs_db=True)
def _(ctx: Context) -> None:
    venue_id, payload = cr94_venue(ctx, "080")
    event_id, booking_id = cr94_booking(ctx, "080", venue_id)

    body = edit_venue(ctx, venue_id, {**payload, "capacity": 100, "confirm": True})

    expect(body["saved"] is True, f"saved={body['saved']}")
    rows = db_query(
        "select recipient_id::text as recipient_id, type, message from public.notifications "
        f"where event_id = '{event_id}' and type in ('venue_booking_affected', 'venue_updated_affects_booking') "
        "order by type"
    )
    recipients = sorted((row["type"], row["recipient_id"]) for row in rows)
    # The seeded coordinator also holds venue_staff, so is notified once as the
    # event's coordinator (through the Unsuitable flag, part 2) and once as a
    # member of the venue staff pool.
    expect(recipients == [("venue_booking_affected", COORDINATOR_ID), ("venue_updated_affects_booking", COORDINATOR_ID)],
           f"notified {rows}")
    expect(all(row["recipient_id"] != VENUE_STAFF_ID for row in rows), "the editor was notified")
    staff_message = f'Venue "{payload["name"]}" was edited and "{THROWAWAY_EVENT_PREFIX}{ctx.run_id} 080" is now Unsuitable: '
    expect(any(row["message"].startswith(staff_message) for row in rows), f"no venue staff message in {rows}")
    [booking] = db_query(f"select status::text as status, venue_id::text as venue_id from public.venue_bookings where id = '{booking_id}'")
    expect(booking == {"status": "held", "venue_id": venue_id}, f"the booking changed: {booking}")


@check("TC-VENUE-082", "Bookings of cancelled events aren't re-checked", needs_db=True)
def _(ctx: Context) -> None:
    venue_id, payload = cr94_venue(ctx, "082")
    _, live = cr94_booking(ctx, "082-a", venue_id)
    cancelled = throwaway_event(ctx, "082-b", "2031-06-11 14:00+08", "2031-06-11 17:00+08")
    db_query(f"update public.events set expected_attendance = 120 where id = '{cancelled}'")
    response = request_venue(ctx, ctx.shared("event_coordinator"), cancelled, venue_id)
    expect_status(response, 201)
    cancelled_booking = response.json()["id"]
    db_query(f"update public.events set status = 'cancelled' where id = '{cancelled}'")

    body = edit_venue(ctx, venue_id, {**payload, "capacity": 100})

    expect(warning_for(body, live) is not None, "the planning event's booking was not warned")
    expect(warning_for(body, cancelled_booking) is None, "the cancelled event's booking was re-checked")


def booking_flag(booking_id: str) -> dict:
    [row] = db_query(
        "select status::text as status, flag::text as flag, flag_reason from public.venue_bookings "
        f"where id = '{booking_id}'"
    )
    return row


@check("TC-VENUE-085", "Saving past an Unsuitable warning flags the booking with its reason; it stays held", needs_db=True)
def _(ctx: Context) -> None:
    venue_id, payload = cr94_venue(ctx, "085")
    event_id, booking_id = cr94_booking(ctx, "085", venue_id)

    edit_venue(ctx, venue_id, {**payload, "capacity": 100, "confirm": True})

    reason = f'Venue "{payload["name"]}" was edited: Capacity 100 is below the expected attendance of 120.'
    flag = booking_flag(booking_id)
    expect(flag == {"status": "held", "flag": "unsuitable", "flag_reason": reason}, f"booking {flag}")
    [notice] = db_query(
        "select recipient_id::text as recipient_id, message from public.notifications "
        f"where event_id = '{event_id}' and type = 'venue_booking_affected'"
    )
    expect(notice["recipient_id"] == COORDINATOR_ID, f"notified {notice}")
    expect("is flagged Unsuitable: Capacity 100 is below the expected attendance of 120." in notice["message"],
           f"message {notice['message']}")


@check("TC-VENUE-086", "A warning-only change saves without flagging", needs_db=True)
def _(ctx: Context) -> None:
    venue_id, payload = cr94_venue(ctx, "086")
    _, booking_id = cr94_booking(ctx, "086", venue_id)

    body = edit_venue(ctx, venue_id, {**payload, "layouts": [{"layout": "boardroom", "capacity_for_layout": None}],
                                      "confirm": True})

    expect(body["saved"] is True, f"saved={body['saved']}")
    expect(booking_flag(booking_id)["flag"] is None, "a warning-only change flagged the booking")


@check("TC-VENUE-087", "An already-flagged booking keeps its first flag; its coordinator is still told", needs_db=True)
def _(ctx: Context) -> None:
    venue_id, payload = cr94_venue(ctx, "087")
    event_id, booking_id = cr94_booking(ctx, "087", venue_id)
    db_query(
        "update public.venue_bookings set flag = 'affected', flag_reason = 'Live check: flagged first', "
        f"flagged_at = now() where id = '{booking_id}'"
    )

    edit_venue(ctx, venue_id, {**payload, "capacity": 100, "confirm": True})

    flag = booking_flag(booking_id)
    expect((flag["flag"], flag["flag_reason"]) == ("affected", "Live check: flagged first"), f"booking {flag}")
    rows = db_query(
        "select type, message from public.notifications "
        f"where event_id = '{event_id}' and recipient_id = '{COORDINATOR_ID}' order by type"
    )
    # One as the coordinator (the unflagged message), one as venue staff.
    expect([row["type"] for row in rows] == ["venue_updated_affects_booking"] * 2, f"notified {rows}")
    expect(any(row["message"].startswith(f'Venue "{payload["name"]}" changed in a way that may affect') for row in rows),
           f"no coordinator message in {rows}")


@check("TC-VENUE-088", "A flagged event in Safety review goes back to Planning", needs_db=True)
def _(ctx: Context) -> None:
    venue_id, payload = cr94_venue(ctx, "088")
    event_id, booking_id = cr94_booking(ctx, "088", venue_id)
    db_query(f"update public.events set status = 'safety_review' where id = '{event_id}'")

    edit_venue(ctx, venue_id, {**payload, "capacity": 100, "confirm": True})

    expect(booking_flag(booking_id)["flag"] == "unsuitable", "the booking was not flagged")
    [event] = db_query(f"select status::text as status from public.events where id = '{event_id}'")
    expect(event["status"] == "planning", f"event status {event['status']}")


# --- Tentative hold expiry (CR-99) -----------------------------------------


def hold_for(ctx: Context, case: str, starts: str, ends: str) -> tuple[str, str]:
    """A throwaway planning event holding Innovation Lab: (event id, booking id)."""
    event_id = throwaway_event(ctx, case, starts, ends)
    response = request_venue(ctx, ctx.shared("event_coordinator"), event_id, INNOVATION_LAB)
    expect_status(response, 201)
    return event_id, response.json()["id"]


@check("TC-HOLD-001", "A new hold expires 7 days after the request", needs_db=True)
def _(ctx: Context) -> None:
    _event_id, booking_id = hold_for(ctx, "H001", "2031-06-20 14:00+08", "2031-06-20 17:00+08")

    [row] = db_query(
        "select abs(extract(epoch from expires_at - (created_at + interval '7 days'))) < 1 as seven_days "
        f"from public.venue_bookings where id = '{booking_id}'"
    )
    expect(row["seven_days"] is True, f"expiry is not 7 days after the request: {row}")
    queue = ctx.client.get(f"{ctx.api}/venues/dashboard/venue-staff", headers=ctx.shared("venue_staff").headers).json()
    [listed] = [b for b in queue["pending_holds"] if b["id"] == booking_id]
    expect(listed.get("expires_at"), f"the queue shows no expiry: {listed}")


@check("TC-HOLD-002", "Venue staff change a hold's expiry within its bounds; others can't", needs_db=True)
def _(ctx: Context) -> None:
    _event_id, booking_id = hold_for(ctx, "H002", "2031-06-21 14:00+08", "2031-06-21 17:00+08")
    url = f"{ctx.api}{BOOKINGS}/{booking_id}/expiry"
    staff = ctx.shared("venue_staff")

    changed = ctx.client.patch(url, headers=staff.headers, json={"expires_at": "2031-06-21T14:00:00+08:00"})
    expect_status(changed, 200)
    [history] = db_query(
        "select actor_id, new_expires_at = '2031-06-21 14:00+08' as new_ok from public.venue_booking_history "
        f"where booking_id = '{booking_id}' and action = 'expiry_changed'"
    )
    expect(history["actor_id"] == VENUE_STAFF_ID and history["new_ok"] is True, f"history row is {history}")

    late = ctx.client.patch(url, headers=staff.headers, json={"expires_at": "2031-06-21T14:01:00+08:00"})
    expect_status(late, 422)
    expect_detail(late, "The new expiry can't be after the event starts.")
    past = ctx.client.patch(url, headers=staff.headers, json={"expires_at": "2020-01-01T09:00:00+08:00"})
    expect_status(past, 422)
    expect_detail(past, "The new expiry must be in the future.")
    for role in ("event_coordinator", "event_organiser", "tech_support", "attendee"):
        denied = ctx.client.patch(url, headers=ctx.shared(role).headers, json={"expires_at": "2031-06-20T09:00:00+08:00"})
        expect_status(denied, 403)


@check("TC-HOLD-003", "An overdue hold expires, the coordinator is told, and the venue can be requested again",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id, booking_id = hold_for(ctx, "H003", "2031-06-22 14:00+08", "2031-06-22 17:00+08")
    # Only this check's own hold is moved into the past; the job then runs as
    # pg_cron runs it every minute.
    db_query(f"update public.venue_bookings set expires_at = now() - interval '1 minute' where id = '{booking_id}'")
    db_query("select public.expire_venue_holds()")

    [row] = db_query(f"select status::text as status from public.venue_bookings where id = '{booking_id}'")
    expect(row["status"] == "expired", f"the overdue hold is {row['status']}")
    notices = db_query(
        f"select recipient_id, type from public.notifications where event_id = '{event_id}' "
        "and type in ('venue_hold_expiring', 'venue_hold_expired') order by type"
    )
    # Only the expired notice: a hold already past its expiry isn't warned first.
    expect([(n["recipient_id"], n["type"]) for n in notices] == [(COORDINATOR_ID, "venue_hold_expired")],
           f"notices were {notices}")

    coordinator = ctx.shared("event_coordinator")
    shown = ctx.client.get(f"{ctx.api}/events/{event_id}", headers=coordinator.headers).json()["venue_booking"]
    expect(shown and shown["status"] == "expired", f"the event page shows {shown}")
    queue = ctx.client.get(f"{ctx.api}/venues/dashboard/venue-staff", headers=ctx.shared("venue_staff").headers).json()
    expect(all(b["id"] != booking_id for b in queue["pending_holds"]), "the expired hold is still in the queue")
    again = request_venue(ctx, coordinator, event_id, INNOVATION_LAB)
    expect_status(again, 201)
    refused = ctx.client.patch(f"{ctx.api}{BOOKINGS}/{booking_id}/expiry", headers=ctx.shared("venue_staff").headers,
                               json={"expires_at": "2031-06-21T09:00:00+08:00"})
    expect_status(refused, 409)
    expect_detail(refused, "This hold has already expired.")


# --- Venue staff reject a booking request (SCRUM-38) ----------------------------

def reject_booking(ctx: Context, session: Session, booking_id: str, reason: str | None = "Capacity exceeded",
                   suggestion: str | None = None) -> httpx.Response:
    return ctx.client.post(f"{ctx.api}{BOOKINGS}/{booking_id}/reject", headers=session.headers,
                           json={"reason": reason, "suggestion": suggestion})


@check("TC-BOOK-014", "Venue staff open a held request and see the event's requirements", needs_db=True)
def _(ctx: Context) -> None:
    event_id, booking_id = hold_for(ctx, "014", "2031-06-02 14:00+08", "2031-06-02 17:00+08")
    db_query(f"update public.events set expected_attendance = 40, layout_preference = 'classroom', "
             f"accessibility_needs = 'Step-free access' where id = '{event_id}'")

    response = ctx.client.get(f"{ctx.api}{BOOKINGS}/{booking_id}", headers=ctx.shared("venue_staff").headers)
    expect_status(response, 200)
    body = response.json()
    expect(body["status"] == "held" and body["venue_name"], f"booking reads {body}")
    event = body["event"]
    expect(event["id"] == event_id and event["expected_attendance"] == 40 and event["layout_preference"] == "classroom"
           and event["accessibility_needs"] == "Step-free access", f"event requirements read {event}")
    expect(body["period"]["starts_at"].startswith("2031-06-02T06:00"), f"period is {body['period']}")


@check("TC-BOOK-015", "Rejecting a hold with a reason frees the slot, keeps the event in planning and tells "
                      "only the coordinator", needs_db=True)
def _(ctx: Context) -> None:
    event_id, booking_id = hold_for(ctx, "015-a", "2031-06-03 14:00+08", "2031-06-03 17:00+08")
    other_event = throwaway_event(ctx, "015-b", "2031-06-03 15:00+08", "2031-06-03 16:00+08")

    response = reject_booking(ctx, ctx.shared("venue_staff"), booking_id, "  Capacity exceeded  ", " Try Heritage Hall ")
    expect_status(response, 200)
    body = response.json()
    expect(body["status"] == "rejected" and body["decision"]["reason"] == "Capacity exceeded"
           and body["decision"]["suggestion"] == "Try Heritage Hall", f"decision reads {body.get('decision')}")
    expect([entry["action"] for entry in body["history"]] == ["rejected"], f"history is {body['history']}")

    notified = db_query(f"select recipient_id, message from public.notifications "
                        f"where event_id = '{event_id}' and type = 'venue_booking_rejected'")
    expect([row["recipient_id"] for row in notified] == [COORDINATOR_ID],
           f"venue_booking_rejected went to {notified} (want the assigned coordinator only)")
    expect("Capacity" not in notified[0]["message"], "the notification carries the reason")

    # AC5: another event can now hold the same venue for an overlapping time.
    expect_status(request_venue(ctx, ctx.shared("event_coordinator"), other_event, INNOVATION_LAB), 201)
    # AC7: the event stays in planning and can request another venue.
    [event] = db_query(f"select status::text as status from public.events where id = '{event_id}'")
    expect(event["status"] == "planning", f"the event became {event['status']}")
    expect_status(request_venue(ctx, ctx.shared("event_coordinator"), event_id, HERITAGE_HALL), 201)


@check("TC-BOOK-016", "A blank or over-long reason, or an over-long suggestion, is refused", needs_db=True)
def _(ctx: Context) -> None:
    _, booking_id = hold_for(ctx, "016", "2031-06-04 14:00+08", "2031-06-04 17:00+08")
    staff = ctx.shared("venue_staff")

    for reason, suggestion in (("   ", None), (None, None), ("x" * 1001, None), ("Closed", "y" * 1001)):
        expect_status(reject_booking(ctx, staff, booking_id, reason, suggestion), 422)
    [stored] = db_query(f"select status::text as status from public.venue_bookings where id = '{booking_id}'")
    expect(stored["status"] == "held", f"a refused rejection left the booking {stored['status']}")


@check("TC-BOOK-017", "A booking that is no longer held can't be rejected", needs_db=True)
def _(ctx: Context) -> None:
    _, booking_id = hold_for(ctx, "017", "2031-06-05 14:00+08", "2031-06-05 17:00+08")
    staff = ctx.shared("venue_staff")

    expect_status(reject_booking(ctx, staff, booking_id), 200)
    again = reject_booking(ctx, staff, booking_id, "Again")
    expect_status(again, 409)
    expect_detail(again, "Only a held booking can be rejected. This one is already rejected.")
    # Approval is SCRUM-36's, so the throwaway booking is set approved directly.
    _, approved_id = hold_for(ctx, "017-b", "2031-06-05 18:00+08", "2031-06-05 19:00+08")
    db_query(f"update public.venue_bookings set status = 'approved' where id = '{approved_id}'")
    refused = reject_booking(ctx, staff, approved_id)
    expect_status(refused, 409)
    expect_detail(refused, "Only a held booking can be rejected. This one is approved.")


@check("TC-BOOK-018", "Two simultaneous rejections of one hold: exactly one is saved", needs_db=True)
def _(ctx: Context) -> None:
    from concurrent.futures import ThreadPoolExecutor

    _, booking_id = hold_for(ctx, "018", "2031-06-06 14:00+08", "2031-06-06 17:00+08")
    staff = ctx.shared("venue_staff")

    def fire(reason: str) -> int:
        with httpx.Client(timeout=30) as client:
            return client.post(f"{ctx.api}{BOOKINGS}/{booking_id}/reject", headers=staff.headers,
                               json={"reason": reason}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(fire, ["First reason", "Second reason"]))
    expect(codes == [200, 409], f"expected one 200 and one 409, got {codes}")
    [count] = db_query("select count(*)::int as n from public.venue_booking_history "
                       f"where booking_id = '{booking_id}' and action = 'rejected'")
    expect(count["n"] == 1, f"{count['n']} rejections were recorded")


@check("TC-BOOK-019", "Only a session acting as venue staff can reject", needs_db=True)
def _(ctx: Context) -> None:
    _, booking_id = hold_for(ctx, "019", "2031-06-07 14:00+08", "2031-06-07 17:00+08")
    for role in ("event_organiser", "event_coordinator", "tech_support", "attendee"):
        expect_status(reject_booking(ctx, ctx.shared(role), booking_id), 403)
    # SCRUM-76: the seeded coordinator also holds venue_staff, but acting as coordinator is refused.
    expect_status(reject_booking(ctx, ctx.login("event_coordinator"), booking_id), 403)
    [stored] = db_query(f"select status::text as status from public.venue_bookings where id = '{booking_id}'")
    expect(stored["status"] == "held", f"a refused caller left the booking {stored['status']}")


@check("TC-BOOK-020", "The coordinator sees the reason on the event and the booking; the organiser sees neither",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id, booking_id = hold_for(ctx, "020", "2031-06-08 14:00+08", "2031-06-08 17:00+08")
    expect_status(reject_booking(ctx, ctx.shared("venue_staff"), booking_id, "Under repair", "Heritage Hall"), 200)
    coordinator, organiser = ctx.shared("event_coordinator"), ctx.shared("event_organiser")

    event = ctx.client.get(f"{ctx.api}/events/{event_id}", headers=coordinator.headers).json()
    expect([(b["id"], b["reason"], b["suggestion"]) for b in event.get("rejected_bookings", [])]
           == [(booking_id, "Under repair", "Heritage Hall")], f"coordinator reads {event.get('rejected_bookings')}")
    booking = ctx.client.get(f"{ctx.api}{BOOKINGS}/{booking_id}", headers=coordinator.headers)
    expect_status(booking, 200)
    expect(booking.json()["decision"]["reason"] == "Under repair", "the coordinator can't see the reason on the booking")

    seen = ctx.client.get(f"{ctx.api}/events/{event_id}", headers=organiser.headers)
    expect_status(seen, 200)
    expect(seen.json().get("rejected_bookings") == [] and "Under repair" not in seen.text,
           "the organiser's event read shows the rejection")
    expect_status(ctx.client.get(f"{ctx.api}{BOOKINGS}/{booking_id}", headers=organiser.headers), 403)


# --- Several venues per event (CR-97) --------------------------------------

def throwaway_space(event_id: str, label: str, *, pax: int | None = None, layout: str | None = None,
                    starts: str | None = None, ends: str | None = None) -> str:
    """A space on a throwaway event; it goes when the event is deleted (cascade)."""
    def literal(value):
        return "null" if value is None else f"'{value}'"
    rows = db_query(
        "insert into public.event_space_requests (event_id, label, expected_pax, layout_preference, starts_at, ends_at) "
        f"values ('{event_id}', '{label}', {'null' if pax is None else pax}, {literal(layout)}, "
        f"{literal(starts)}, {literal(ends)}) returning id"
    )
    return rows[0]["id"]


def request_space(ctx: Context, session: Session, space_id: str, venue_id: str):
    return ctx.client.post(f"{ctx.api}{BOOKINGS}", headers=session.headers,
                           json={"event_space_request_id": space_id, "venue_id": venue_id})


@check("TC-BOOK-027", "A venue too small for the space's layout is refused with its capacity", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "027", "2031-06-10 09:00+08", "2031-06-10 12:00+08")
    space_id = throwaway_space(event_id, "Workshop", pax=61, layout="classroom")

    response = request_space(ctx, ctx.shared("event_coordinator"), space_id, INNOVATION_LAB)
    expect_status(response, 409)
    expect_detail(response, "Innovation Lab seats 60; this space needs 61.")
    expect(not db_query(f"select 1 from public.venue_bookings where event_id = '{event_id}'"),
           "a refused request left a booking behind")


@check("TC-BOOK-028", "Two spaces hold two venues; the event lists both and readiness names each space",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "028", "2031-06-11 09:00+08", "2031-06-11 13:00+08")
    main = throwaway_space(event_id, "Main hall", pax=50)
    breakout = throwaway_space(event_id, "Breakout room", pax=20,
                               starts="2031-06-11 10:00+08", ends="2031-06-11 11:00+08")
    coordinator = ctx.shared("event_coordinator")

    expect_status(request_space(ctx, coordinator, main, INNOVATION_LAB), 201)
    refused = request_space(ctx, coordinator, breakout, INNOVATION_LAB)  # AC3: same venue, overlapping
    expect_status(refused, 409)
    expect_detail(refused, "Venue already held for this time by another event.")
    expect_status(request_space(ctx, coordinator, breakout, HERITAGE_HALL), 201)

    event = ctx.client.get(f"{ctx.api}/events/{event_id}", headers=coordinator.headers).json()
    booked = sorted((b["event_space_request_id"], b["venue_id"], b["status"]) for b in event.get("venue_bookings", []))
    expect(booked == sorted([(main, INNOVATION_LAB, "held"), (breakout, HERITAGE_HALL, "held")]),
           f"event lists {event.get('venue_bookings')}")
    expect(event["safety_readiness"]["missing"] == [
        "Main hall: awaiting venue staff approval.", "Breakout room: awaiting venue staff approval.",
    ], f"readiness reads {event['safety_readiness']}")


@check("TC-BOOK-029", "The assigned coordinator sets, swaps and clears the primary venue; others can't",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "029", "2031-06-12 09:00+08", "2031-06-12 12:00+08")
    main = throwaway_space(event_id, "Main hall")
    breakout = throwaway_space(event_id, "Breakout room")
    coordinator = ctx.shared("event_coordinator")
    url = f"{ctx.api}/events/{event_id}/spaces"

    def primaries(response):
        expect_status(response, 200)
        return [s["id"] for s in response.json()["spaces"] if s["is_primary"]]

    expect(primaries(ctx.client.get(f"{ctx.api}/events/{event_id}", headers=coordinator.headers)) == [],
           "a two-space event starts with a primary")
    expect(primaries(ctx.client.put(f"{url}/{main}/primary", headers=coordinator.headers)) == [main], "set failed")
    expect(primaries(ctx.client.put(f"{url}/{breakout}/primary", headers=coordinator.headers)) == [breakout],
           "swap failed")
    expect(primaries(ctx.client.delete(f"{url}/primary", headers=coordinator.headers)) == [], "clear failed")

    for role in ("event_organiser", "venue_staff", "tech_support", "attendee"):
        expect_status(ctx.client.put(f"{url}/{main}/primary", headers=ctx.shared(role).headers), 403)
    session = ctx.login("event_coordinator")  # SCRUM-76: holds venue_staff too
    expect_status(ctx.client.post(f"{ctx.api}/auth/active-role", json={"role": "venue_staff"},
                                  headers=session.headers), 200)
    expect_status(ctx.client.put(f"{url}/{main}/primary", headers=session.headers), 403)
    expect(not db_query(f"select 1 from public.event_space_requests where event_id = '{event_id}' and is_primary"),
           "a refused call set a primary")

    db_query(f"update public.events set status = 'safety_review' where id = '{event_id}'")
    refused = ctx.client.put(f"{url}/{main}/primary", headers=coordinator.headers)
    expect_status(refused, 409)
    expect_detail(refused, "The primary venue can only be changed while the event is in planning.")


@check("TC-BOOK-030", "An event-only request books the event's first space", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "030", "2031-06-13 09:00+08", "2031-06-13 12:00+08")
    first = throwaway_space(event_id, "Main hall", pax=40)
    throwaway_space(event_id, "Breakout room", pax=10)

    response = request_venue(ctx, ctx.shared("event_coordinator"), event_id, HERITAGE_HALL)
    expect_status(response, 201)
    expect(response.json()["event_space_request_id"] == first, f"booked {response.json()}")


# --- Booking conflict detection (SCRUM-21) ---------------------------------

def hold_with_buffers(ctx: Context, case: str, starts: str, ends: str, venue_id: str) -> str:
    """A throwaway event holding `venue_id`, its hold given 30 min setup and
    45 min turnaround the way CR-100 will copy them in. Returns the event id."""
    event_id = throwaway_event(ctx, case, starts, ends)
    expect_status(request_venue(ctx, ctx.shared("event_coordinator"), event_id, venue_id), 201)
    db_query("update public.venue_bookings set setup_minutes = 30, turnaround_minutes = 45 "
             f"where event_id = '{event_id}'")
    return event_id


@check("TC-BOOK-037", "A request in another booking's turnaround is refused, naming that event and its window",
       needs_db=True)
def _(ctx: Context) -> None:
    hold_with_buffers(ctx, "037-a", "2031-06-16 10:00+08", "2031-06-16 12:00+08", INNOVATION_LAB)
    later = throwaway_event(ctx, "037-b", "2031-06-16 12:30+08", "2031-06-16 14:00+08")
    after_turnaround = throwaway_event(ctx, "037-c", "2031-06-16 12:45+08", "2031-06-16 14:00+08")
    coordinator = ctx.shared("event_coordinator")

    refused = request_venue(ctx, coordinator, later, INNOVATION_LAB)
    expect_status(refused, 409)
    expect(refused.json() == {
        "detail": "Venue already held for this time by another event.",
        "conflict": {"kind": "booking", "event_name": f"{THROWAWAY_EVENT_PREFIX}{ctx.run_id} 037-a",
                     "block_reason": None,
                     "starts_at": "2031-06-16T01:30:00Z", "ends_at": "2031-06-16T04:45:00Z"},
    }, f"refusal was {refused.json()}")
    # AC3: starting exactly as the turnaround ends is allowed.
    expect_status(request_venue(ctx, coordinator, after_turnaround, INNOVATION_LAB), 201)


@check("TC-BOOK-038", "A space request during a block is refused with the block's reason and period", needs_db=True)
def _(ctx: Context) -> None:
    db_query(
        "insert into public.venue_blocks (venue_id, blocked_period, reason, notes) values "
        f"('{HERITAGE_HALL}', tstzrange('2031-06-17 10:00+08', '2031-06-17 12:00+08', '[)'), "
        f"'maintenance', '{THROWAWAY_BLOCK_NOTE}')"
    )
    event_id = throwaway_event(ctx, "038", "2031-06-17 09:00+08", "2031-06-17 18:00+08")
    space_id = throwaway_space(event_id, "Morning room", starts="2031-06-17 11:00+08", ends="2031-06-17 13:00+08")

    refused = request_space(ctx, ctx.shared("event_coordinator"), space_id, HERITAGE_HALL)
    expect_status(refused, 409)
    expect(refused.json() == {
        "detail": "Venue blocked for this time.",
        "conflict": {"kind": "block", "event_name": None, "block_reason": "maintenance",
                     "starts_at": "2031-06-17T02:00:00Z", "ends_at": "2031-06-17T04:00:00Z"},
    }, f"refusal was {refused.json()}")


@check("TC-BOOK-039", "Search rules a venue out during another booking's turnaround, without naming the event",
       needs_db=True)
def _(ctx: Context) -> None:
    hold_with_buffers(ctx, "039", "2031-06-18 10:00+08", "2031-06-18 12:00+08", INNOVATION_LAB)

    found = ctx.client.get(f"{ctx.api}/venues", headers=ctx.shared("event_coordinator").headers, params={
        "starts_at": "2031-06-18T12:30:00+08:00", "ends_at": "2031-06-18T14:00:00+08:00", "include_excluded": "true",
    })
    expect_status(found, 200)
    [lab] = [r for r in found.json()["results"] if r["venue"]["id"] == INNOVATION_LAB]
    messages = [reason["message"] for reason in lab["reasons"]]
    expect(lab["excluded"] and "Held by another event 18 Jun 09:30–12:45" in messages,
           f"Innovation Lab was {lab['excluded'] and 'excluded' or 'listed'} with {messages}")
    expect(not any(ctx.run_id in message for message in messages), f"search named the event: {messages}")


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


# CR-103/104: denial probes never target a seeded/shared event. Even if a
# role guard regresses, the missing UUID cannot produce a decision or transition.
@check("TC-SDEC-001", "Non-officer active roles cannot read the safety queue or review, or decide")
def _(ctx: Context) -> None:
    missing_event = "00000000-0000-4000-8000-000000000000"
    for role in ACCOUNTS:
        headers = ctx.shared(role).headers
        for path in ("/events/safety-queue", f"/events/{missing_event}/safety-review"):
            expect_status(ctx.client.get(f"{ctx.api}{path}", headers=headers), 403)
        for action, body in (
            ("safety-approve", {}),
            ("safety-request-changes", {"comment": "Denial check"}),
            ("safety-reject", {"reason": "Denial check"}),
        ):
            expect_status(ctx.client.post(
                f"{ctx.api}/events/{missing_event}/{action}", headers=headers, json=body,
            ), 403)


@check("TC-SDEC-002", "External and unrelated staff roles cannot read safety decision comments")
def _(ctx: Context) -> None:
    # Assigned coordinators are allowed; their relationship denial needs a
    # known unassigned event and is left to TC-SDEC-003's manual setup.
    for role in ("event_organiser", "venue_staff", "tech_support", "attendee"):
        expect_status(ctx.client.get(
            f"{ctx.api}/events/00000000-0000-4000-8000-000000000000/safety-decisions",
            headers=ctx.shared(role).headers,
        ), 403)


# Officer checks below only read, or are refused before any write: the missing
# UUID, schema validation (422) and the status check (409) all answer before an
# RPC is called, so the shared planning fixture is never changed.
MISSING_EVENT = "00000000-0000-4000-8000-000000000000"
SAFETY_DECISIONS = (
    ("safety-approve", {}),
    ("safety-request-changes", {"comment": "Live check"}),
    ("safety-reject", {"reason": "Live check"}),
)


@check("TC-SDEC-003", "The Event Coordinator Lead is denied every Safety Officer endpoint")
def _(ctx: Context) -> None:
    headers = ctx.shared("event_coordinator_lead").headers
    for path in ("/events/safety-queue", "/events/safety-history", f"/events/{MISSING_EVENT}/safety-review",
                 f"/events/{MISSING_EVENT}/safety-decisions"):
        expect_status(ctx.client.get(f"{ctx.api}{path}", headers=headers), 403)
    for action, body in SAFETY_DECISIONS:
        expect_status(ctx.client.post(f"{ctx.api}/events/{MISSING_EVENT}/{action}", headers=headers, json=body), 403)


@check("TC-SDEC-005", "An active Safety Officer reads the queue, oldest entry into review first")
def _(ctx: Context) -> None:
    response = ctx.client.get(f"{ctx.api}/events/safety-queue", headers=ctx.shared("safety_officer").headers)
    expect_status(response, 200)
    items = response.json()["items"]
    keys = [(item["entered_review_at"], item["event_id"]) for item in items]
    expect(keys == sorted(keys), f"Queue not oldest first: {keys}")


@check("TC-SDEC-021", "An active Safety Officer reads the last 30 days of decisions, newest first")
def _(ctx: Context) -> None:
    response = ctx.client.get(f"{ctx.api}/events/safety-history", headers=ctx.shared("safety_officer").headers)
    expect_status(response, 200)
    times = [item["decided_at"] for item in response.json()["items"]]
    expect(times == sorted(times, reverse=True), f"History not newest first: {times}")


@check("TC-SDEC-014", "A missing event answers 404 to the Safety Officer's review and decisions")
def _(ctx: Context) -> None:
    headers = ctx.shared("safety_officer").headers
    expect_status(ctx.client.get(f"{ctx.api}/events/{MISSING_EVENT}/safety-review", headers=headers), 404)
    for action, body in SAFETY_DECISIONS:
        expect_status(ctx.client.post(f"{ctx.api}/events/{MISSING_EVENT}/{action}", headers=headers, json=body), 404)


@check("TC-SDEC-015", "A decision on an event outside Safety review is refused with 409")
def _(ctx: Context) -> None:
    headers = ctx.shared("safety_officer").headers
    expect_status(ctx.client.get(f"{ctx.api}/events/{SAFE_EVENT}/safety-review", headers=headers), 404)
    for action, body in SAFETY_DECISIONS:
        response = ctx.client.post(f"{ctx.api}/events/{SAFE_EVENT}/{action}", headers=headers, json=body)
        expect_status(response, 409)
        expect("planning" in response.json()["detail"], f"{action}: {response.json()['detail']}")


@check("TC-SDEC-016", "A blank, whitespace-only or 1001-character comment or reason is refused with 422")
def _(ctx: Context) -> None:
    headers = ctx.shared("safety_officer").headers
    for text in ("", "   ", "x" * 1001):
        for action, field_name in (("safety-request-changes", "comment"), ("safety-reject", "reason")):
            expect_status(ctx.client.post(
                f"{ctx.api}/events/{MISSING_EVENT}/{action}", headers=headers, json={field_name: text},
            ), 422)


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
    return _rows(completed.stdout)


def _rows(stdout: str) -> list[dict]:
    """The rows in the CLI's JSON. It prints `{"rows": [...]}` under an agent but a bare
    list in a plain terminal (`[]` when nothing matched), with notices around either."""
    starts = [i for i in (stdout.find("{"), stdout.find("[")) if i != -1]
    if not starts:
        raise CheckFailed(f"database query printed no JSON: {stdout.strip()[:200]!r}")
    payload, _ = json.JSONDecoder().raw_decode(stdout[min(starts):])
    return payload.get("rows", []) if isinstance(payload, dict) else payload


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
        title = f"{cases}: supabase/verification/{script}"
        if script == "safety_decision_checks.sql":
            # Read-only and scoped to this migration's exact table/RPC contract.
            # Connectivity/CLI errors remain failures, not migration blockers.
            try:
                rows = db_query(
                    "select to_regclass('public.event_safety_decisions') is not null "
                    "and to_regprocedure('public.safety_approve_event(uuid,uuid,integer,text,text,text)') is not null "
                    "and to_regprocedure('public.safety_return_event(uuid,uuid,integer,text,text,uuid[],uuid[],text)') is not null "
                    "and to_regprocedure('public.return_event_to_planning(uuid,integer,text,text,text,text)') is not null "
                    "as migration_present"
                )
                expect(len(rows) == 1 and isinstance(rows[0].get("migration_present"), bool),
                       "safety migration preflight returned an unexpected result")
            except Exception as error:
                results.append(Result(script, title, "fail", str(error)))
                print_result(results[-1])
                continue
            if not rows[0]["migration_present"]:
                results.append(Result(
                    script, title, "blocked",
                    "Safety-decision migration table/RPC interfaces are missing; "
                    "SQL verification not run. Apply the migration through the authorised workflow first.",
                ))
                print_result(results[-1])
                continue
        completed = _supabase_query("-f", str(VERIFICATION_DIR / script))
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
    rows = _rows(stdout)
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
                    left_over = delete_throwaway_venues()
                    if left_over:
                        print(f"  (deleted {left_over} deactivation check venue(s) left by an earlier run)")
                results += run_api_checks(ctx, args.keyword, skip_accounts=args.skip_db)
            finally:
                ctx.logout_all()
                if not args.skip_db:
                    delete_throwaway_accounts()
                    delete_throwaway_bookings()
                    delete_throwaway_venues()

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
