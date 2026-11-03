"""Run the scriptable manual test cases against the real system.

Two kinds of check, each named by the test case ID it runs (docs/test-cases/):

- API checks: real HTTP requests to a running backend, which talks to the live
  Supabase project. They only read shared data. The sessions they open are
  their own, and every one of them is logged out at the end.
- Database checks: the rolled-back scripts in supabase/verification/, run
  through `supabase db query` (needs `supabase login`), so they change nothing.

Sign-up checks create throwaway accounts named live-check+<run>-<case>@
connectsphere.dev. Each such account, and everything it owns, is deleted
through `supabase db query` after the checks finish, so the seeded data is
never touched. --skip-db skips these checks too.

Venue booking checks (SCRUM-19) likewise create throwaway events named
"live-check <run> ..." (owned by the seeded organiser, assigned to the seeded
coordinator, dated 2031) and throwaway venue blocks noted "live-check <run>".
Venue deactivation checks (SCRUM-64) create throwaway venues named
"live-check venue <run> ..."; seeded venues are never changed.

A run deletes only its own throwaway rows, before and after the checks, plus
any an earlier run left more than STALE_AFTER ago. So two runs at once (two
developers, or this and the browser suite) can't delete each other's rows.

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
    # A second Lead (CR-101 AC5: one or more Leads, each seeing what they assigned).
    "event_coordinator_lead_2": "coordinator.lead2@connectsphere.dev",
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
    ("safety_decision_checks.sql", "TC-SDEC-003, 009–011, 015–017, 024, 025 (database half)"),
    ("event_amendment_checks.sql", "TC-AMD-001, 005, 008 (database half)"),
    ("event_comment_checks.sql", "TC-CMT-008, 009, 010, 011, 013 (database half)"),
    ("venue_booking_request_checks.sql", "TC-BOOK-001–006 (database half)"),
    ("hold_expiry_checks.sql", "TC-HOLD-001–003 (database half: bounds, job, notices, approval race)"),
    ("event_space_checks.sql", "TC-SPACE-003, 005, 009; TC-HOLD-009 (overdue space holds); TC-BOOK-031–033 (CR-97 database half)"),
    ("equipment_request_checks.sql", "TC-EQR-002, 003, 006, 007, 008, 009 (database half)"),
    ("venue_edit_checks.sql", "TC-VENUE-058, 059, 061 (database half)"),
    ("venue_buffer_checks.sql", "TC-VENUE-092 (CR-100: defaults copied on new requests, existing bookings unchanged)"),
    ("venue_booking_reject_checks.sql", "TC-BOOK-023"),
    ("venue_booking_approve_checks.sql", "TC-BOOK-056"),
    ("lead_assignment_checks.sql", "CR-101 (database half: assignment columns, reassign_event)"),
    ("coordinator_assignment_checks.sql", "TC-ASSIGN-010 (SCRUM-12 database half: assign_event, exclusive Lead role)"),
    ("venue_deactivation_checks.sql", "TC-VENUE-070 (SCRUM-64 database half); D33"),
    ("booking_conflict_checks.sql", "TC-BOOK-040 (SCRUM-21 database half: occupied window, venue_conflicts)"),
    ("venue_block_flag_checks.sql", "TC-BOOK-043, 044 (CR-95: a block flags the bookings it overlaps; organiser notice)"),
    ("venue_replacement_checks.sql", "TC-BOOK-045 (CR-95: request a replacement for an affected booking)"),
    ("venue_release_checks.sql", "TC-BOOK-046 (CR-95: release the original when its replacement is approved)"),
    ("venue_restore_checks.sql", "TC-BOOK-047 (CR-95: restore an affected booking)"),
    ("venue_block_create_checks.sql", "TC-BLOCK-008–013 (SCRUM-51 database half: refusals, history, flags, links, notices, RLS)"),
    ("venue_block_change_checks.sql", "TC-BLOCK-025 (SCRUM-54 database half: changes, history, freed bookings, restore, RLS)"),
    ("equipment_availability_checks.sql", "TC-EQR-038 (23-R: condition, event window, reference location)"),
    ("equipment_reservation_checks.sql", "TC-EQR-016–020, 022–025 (SCRUM-24 database half)"),
    ("equipment_line_change_checks.sql", "TC-EQR-044–053 (SCRUM-44 database half: edits, removals, notices, history)"),
    ("event_cancellation_request_checks.sql", "TC-CANCEL-007, 008 (story 84 database half: superseding, index, RLS)"),
    ("event_cancellation_decision_checks.sql", "TC-CANCEL-018 (story 115 database half: releases, notices, refusals)"),
    ("event_change_request_checks.sql", "TC-CHANGE-007 (story 32 database half: one open per event, closing, RLS)"),
    ("registration_withdrawal_checks.sql", "TC-REG-018 (SCRUM-55 withdrawal, cutoff, re-registration and grants)"),
    ("change_request_decision_checks.sql", "TC-CHANGE-024 (story 37 database half: decisions, moves, marks, sends, re-review)"),
    ("technical_preparation_checks.sql", "TC-TPREP-001–006 (CR-110 database half: refusals, Preparation, history, notices, RLS)"),
    ("registration_waitlist_checks.sql", "TC-REG-020, 022–028 (SCRUM-86 database half)"),
    ("notification_registration_checks.sql", "TC-NOTIF-017, 018 (SCRUM-53: registration status confirmations, replacement venue)"),
    ("change_history_checks.sql", "TC-HIST-001–007 (story 62 database half: recorded edits, append-only history, RLS)"),
    ("reassignment_request_checks.sql", "TC-REASSIGN-012 (CR-106 database half: recipients, one open, closing, RLS)"),
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


def require_waitlist_migration() -> None:
    rows = db_query(
        "select to_regprocedure('public.accept_waitlist_invitation(uuid,uuid)') is not null "
        "and to_regprocedure('public.leave_waitlist(uuid,uuid)') is not null "
        "and exists (select 1 from information_schema.columns "
        "where table_schema = 'public' and table_name = 'event_registrations' "
        "and column_name = 'invitation_expires_at') "
        "and exists (select 1 from information_schema.columns "
        "where table_schema = 'public' and table_name = 'event_registrations' "
        "and column_name = 'waitlist_order') as migration_present"
    )
    expect(len(rows) == 1 and isinstance(rows[0].get("migration_present"), bool),
           "waitlist migration preflight returned an unexpected result")
    if not rows[0]["migration_present"]:
        raise CheckBlocked(
            "SCRUM-86 waitlist migration is not applied; waitlist verification was not run."
        )


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


def _matches_keyword(keyword: str | None, content: str) -> bool:
    if not keyword:
        return True
    terms = [term.strip().lower() for term in keyword.split(",") if term.strip()]
    content = content.lower()
    return not terms or any(term in content for term in terms)


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


@check("TC-SAFE-027", "Technical status from SCRUM-24 gates send: no lines pass, a pending line blocks, "
                      "reserved and ticked lets it through", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "SAFE027")
    event_id = throwaway_event(ctx, "SAFE027", "2031-08-20 10:00+08", "2031-08-20 12:00+08")
    db_query(
        "insert into public.venue_bookings (event_id, venue_id, booked_period, status) values "
        f"('{event_id}', '{venue_id}', tstzrange('2031-08-20 10:00+08', '2031-08-20 12:00+08', '[)'), 'approved')"
    )
    coordinator = ctx.shared("event_coordinator")
    event_url = f"{ctx.api}/events/{event_id}"

    readiness = ctx.client.get(event_url, headers=coordinator.headers).json()["safety_readiness"]
    expect(readiness["ready"] is True, f"an approved booking and no equipment lines is not ready: {readiness}")

    line_id = throwaway_line(event_id, throwaway_equipment(ctx, "SAFE027", 2), 1)
    readiness = ctx.client.get(event_url, headers=coordinator.headers).json()["safety_readiness"]
    expect(readiness["ready"] is False and "Technical status is not Ready." in readiness["missing"],
           f"a pending equipment line doesn't block: {readiness}")
    refused = ctx.client.post(f"{event_url}/send-for-safety-check", headers=coordinator.headers)
    expect_status(refused, 409)
    expect("Technical status is not Ready." in refused.json()["detail"], refused.text)
    [row] = db_query(f"select status::text as status from public.events where id = '{event_id}'")
    expect(row["status"] == "planning", f"the refused send moved the event to {row['status']}")

    tech = ctx.shared("tech_support")
    expect_status(reserve(ctx, tech, line_id), 200)
    expect_status(ctx.client.put(f"{ctx.api}/equipment/events/{event_id}/exit-confirmation",
                                 headers=tech.headers, json={"confirmed": True}), 204)
    sent = ctx.client.post(f"{event_url}/send-for-safety-check", headers=coordinator.headers)
    expect_status(sent, 200)
    expect(sent.json()["status"] == "safety_review", f"sent event is {sent.json()['status']}")


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


@check("TC-AUTH-053", "Profile update normalizes and clears its phone number", creates_accounts=True)
def _(ctx: Context) -> None:
    email = ctx.throwaway_email("053")
    expect_status(
        ctx.signup(
            role="attendee",
            full_name="Profile Check",
            email=email,
            organisation_name=None,
            phone_number=None,
        ),
        201,
    )
    session = ctx.login("attendee", email=email, password=THROWAWAY_PASSWORD)
    response = ctx.client.patch(
        f"{ctx.api}/auth/me",
        headers=session.headers,
        json={"full_name": "Updated Profile", "phone_number": "+65 9000 0001"},
    )
    expect_status(response, 200)
    expect(response.json()["full_name"] == "Updated Profile", "updated name is missing from the response")
    expect(response.json()["phone_number"] == "+6590000001", "updated phone was not normalized in the response")

    response = ctx.client.get(f"{ctx.api}/auth/me", headers=session.headers)
    expect_status(response, 200)
    expect(response.json()["phone_number"] == "+6590000001", "normalized phone was not persisted")

    response = ctx.client.patch(
        f"{ctx.api}/auth/me",
        headers=session.headers,
        json={"full_name": "Updated Profile", "phone_number": "   "},
    )
    expect_status(response, 200)
    expect(response.json()["phone_number"] is None, "blank phone was not normalized to NULL")

    response = ctx.client.get(f"{ctx.api}/auth/me", headers=session.headers)
    expect_status(response, 200)
    expect(response.json()["full_name"] == "Updated Profile", "updated name was not persisted")
    expect(response.json()["phone_number"] is None, "cleared phone was not persisted as NULL")


@check("TC-AUTH-054", "Profile update refuses protected fields, invalid phones and a blank name", creates_accounts=True)
def _(ctx: Context) -> None:
    email = ctx.throwaway_email("054")
    expect_status(
        ctx.signup(
            role="attendee",
            full_name="Profile Check",
            email=email,
            organisation_name=None,
            phone_number=None,
        ),
        201,
    )
    session = ctx.login("attendee", email=email, password=THROWAWAY_PASSWORD)
    original = ctx.client.get(f"{ctx.api}/auth/me", headers=session.headers)
    expect_status(original, 200)
    original_profile = original.json()

    response = ctx.client.patch(
        f"{ctx.api}/auth/me",
        headers=session.headers,
        json={
            "full_name": "Attempted Change",
            "phone_number": "+65 9000 0002",
            "email": "other@example.com",
            "role": "event_organiser",
            "organisation_name": "Other organisation",
            "department": "Other department",
            "id": "00000000-0000-4000-8000-000000000000",
        },
    )
    expect_status(response, 422)

    response = ctx.client.patch(
        f"{ctx.api}/auth/me",
        headers=session.headers,
        json={"full_name": "Profile Check", "phone_number": "9123 456"},
    )
    expect_field_error(response, "phone_number", "Enter 8 digits, with an optional +65 country code.")

    response = ctx.client.patch(
        f"{ctx.api}/auth/me",
        headers=session.headers,
        json={"full_name": "   ", "phone_number": None},
    )
    expect_status(response, 422)
    errors = response.json().get("detail", [])
    expect(
        any(error.get("loc") == ["body", "full_name"] for error in errors),
        "blank name error was not attached to full_name",
    )

    response = ctx.client.get(f"{ctx.api}/auth/me", headers=session.headers)
    expect_status(response, 200)
    current = response.json()
    for field in ("id", "email", "full_name", "role", "organisation_name", "department", "phone_number"):
        expect(current[field] == original_profile[field], f"rejected update changed {field}")


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


# --- Registered events (SCRUM-55/56) --------------------------------------
@check("TC-REG-008", "The active Attendee can read their registrations; another active role is refused")
def _(ctx: Context) -> None:
    attendee_response = ctx.client.get(
        f"{ctx.api}/registrations/me",
        headers=ctx.shared("attendee").headers,
    )
    expect_status(attendee_response, 200)
    registrations = attendee_response.json().get("registrations")
    expect(isinstance(registrations, list), "response does not contain a registrations list")
    for registration in registrations:
        expect(
            registration.get("status") in {"registered", "waitlisted", "invited"},
            f"unexpected registration status {registration.get('status')!r}",
        )
        event = registration.get("event")
        expect(isinstance(event, dict), "registration has no event details")
        for field in ("id", "name", "starts_at", "ends_at", "event_timezone", "venues"):
            expect(field in event, f"event details are missing {field}")
    denied = ctx.client.get(
        f"{ctx.api}/registrations/me",
        headers=ctx.shared("event_coordinator").headers,
    )
    expect_status(denied, 403)


def managed_registration_fixture(ctx: Context, case: str) -> tuple[str, dict]:
    event_id = throwaway_event(
        ctx,
        case,
        "2031-08-14 09:00+08",
        "2031-08-14 12:00+08",
        status="confirmed",
    )
    db_query(
        "update public.events set registration_enabled = true, registration_capacity = 5, "
        "registration_opens_at = '2031-08-13 09:00+08', "
        "registration_closes_at = '2031-08-14 08:00+08' "
        f"where id = '{event_id}'"
    )
    db_query(
        "insert into public.event_registrations "
        "(event_id, attendee_id, status, withdrawn_at, waitlist_order, invited_at, invitation_expires_at) values "
        f"('{event_id}', '{ATTENDEE_ID}', 'registered', null, null, null, null), "
        f"('{event_id}', 'a0000000-0000-4000-8000-000000000002', 'invited', null, null, now(), now() + interval '1 day'), "
        f"('{event_id}', 'a0000000-0000-4000-8000-000000000003', 'waitlisted', null, 1, null, null), "
        f"('{event_id}', 'a0000000-0000-4000-8000-000000000004', 'withdrawn', now(), null, null, null), "
        f"('{event_id}', 'a0000000-0000-4000-8000-000000000006', 'cancelled', null, null, null, null), "
        f"('{event_id}', 'a0000000-0000-4000-8000-000000000007', 'invitation_expired', null, null, now(), null), "
        f"('{event_id}', 'a0000000-0000-4000-8000-000000000008', 'left', null, null, null, null)"
    )
    [attendee] = db_query(
        "select id::text as id, full_name, email, phone_number "
        f"from public.profiles where id = '{ATTENDEE_ID}'"
    )
    return event_id, attendee


@check(
    "TC-REG-029",
    "Assigned managers see current counts and role-appropriate registration details",
    needs_db=True,
)
def _(ctx: Context) -> None:
    event_id, attendee = managed_registration_fixture(ctx, "35-029")
    url = f"{ctx.api}/events/{event_id}/registrations"
    coordinator = ctx.shared("event_coordinator")
    organiser = ctx.shared("event_organiser")
    coordinator_response = ctx.client.get(url, headers=coordinator.headers)
    expect_status(coordinator_response, 200)
    coordinator_report = coordinator_response.json()
    expect(
        (coordinator_report.get("effective_capacity"), coordinator_report.get("registered_count"),
         coordinator_report.get("remaining_places"), coordinator_report.get("waitlist_count"))
        == (5, 1, 3, 1),
        f"unexpected coordinator summary: {coordinator_report}",
    )
    expect(
        {row.get("status") for row in coordinator_report["registrations"]}
        == {"registered", "waitlisted", "invited", "withdrawn"},
        f"registration report returned unexpected manager-visible statuses: {coordinator_report['registrations']}",
    )
    coordinator_row = next(row for row in coordinator_report["registrations"] if row["status"] == "registered")
    expect(
        (coordinator_row.get("full_name"), coordinator_row.get("email"))
        == (attendee["full_name"], attendee["email"]),
        f"coordinator contact details differ from the attendee profile: {coordinator_row}",
    )
    if attendee.get("phone_number"):
        expect(coordinator_row.get("phone_number") == attendee["phone_number"],
               "coordinator response omitted the available phone number")

    organiser_response = ctx.client.get(url, headers=organiser.headers)
    expect_status(organiser_response, 200)
    organiser_report = organiser_response.json()
    expect(
        (organiser_report.get("registered_count"), organiser_report.get("remaining_places"))
        == (1, 3),
        f"unexpected organiser summary: {organiser_report}",
    )
    organiser_row = next(row for row in organiser_report["registrations"] if row["status"] == "registered")
    expect(organiser_row.get("full_name") == attendee["full_name"], "organiser did not receive the attendee name")
    expect(
        not {"email", "phone_number"} & organiser_row.keys(),
        f"organiser response included contact fields: {organiser_row}",
    )

    switch = ctx.client.post(
        f"{ctx.api}/auth/active-role",
        json={"role": "venue_staff"},
        headers=coordinator.headers,
    )
    expect_status(switch, 200)
    expect_status(ctx.client.get(url, headers=coordinator.headers), 403)
    switch_back = ctx.client.post(
        f"{ctx.api}/auth/active-role",
        json={"role": "event_coordinator"},
        headers=coordinator.headers,
    )
    expect_status(switch_back, 200)


@check("TC-REG-030", "Event registration reports require ownership or coordinator assignment", needs_db=True)
def _(ctx: Context) -> None:
    unassigned_event = throwaway_event(
        ctx,
        "35-030-unassigned",
        "2031-08-14 09:00+08",
        "2031-08-14 12:00+08",
        status="confirmed",
        assigned=False,
    )
    other_owner_event = throwaway_event(
        ctx,
        "35-030-other-owner",
        "2031-08-14 09:00+08",
        "2031-08-14 12:00+08",
        status="confirmed",
    )
    db_query(
        "update public.events set organiser_id = 'a0000000-0000-4000-8000-000000000008' "
        f"where id = '{other_owner_event}'"
    )

    coordinator = ctx.shared("event_coordinator")
    organiser = ctx.shared("event_organiser")
    expect_status(
        ctx.client.get(f"{ctx.api}/events/{unassigned_event}/registrations", headers=coordinator.headers),
        403,
    )
    expect_status(
        ctx.client.get(f"{ctx.api}/events/{other_owner_event}/registrations", headers=organiser.headers),
        403,
    )


@check(
    "TC-REG-017",
    "Withdrawal is caller-scoped, releases one place, and follows cutoff and re-registration settings",
    creates_accounts=True,
    needs_db=True,
)
def _(ctx: Context) -> None:
    attendee = ctx.shared("attendee")
    other_email = ctx.throwaway_email("55-other")
    signup = ctx.signup(
        role="attendee",
        email=other_email,
        full_name="Live Check Attendee",
        organisation_name=None,
    )
    expect_status(signup, 201)
    other_attendee = ctx.login("attendee", email=other_email, password=THROWAWAY_PASSWORD)
    event_id = throwaway_event(
        ctx,
        "55-017",
        "2031-08-12 09:00+08",
        "2031-08-12 17:00+08",
        status="confirmed",
        assigned=False,
    )
    attendee_id = attendee.body["profile"]["id"]
    db_query(
        "update public.events set registration_enabled = true, registration_capacity = 2, "
        "registration_opens_at = now() - interval '1 day', "
        "registration_closes_at = '2031-08-12 17:00+08', re_registration_allowed = true, "
        "withdrawal_closes_at = now() - interval '1 minute' "
        f"where id = '{event_id}'"
    )
    [registration] = db_query(
        "insert into public.event_registrations (event_id, attendee_id) "
        f"values ('{event_id}', '{attendee_id}') returning id"
    )
    withdrawal_url = f"{ctx.api}/registrations/{event_id}/withdraw"

    denied_role = ctx.client.post(
        withdrawal_url,
        headers=ctx.shared("event_organiser").headers,
    )
    expect_status(denied_role, 403)
    wrong_attendee = ctx.client.post(withdrawal_url, headers=other_attendee.headers)
    expect_status(wrong_attendee, 409)
    expect_detail(wrong_attendee, "No active registration found.")

    cutoff = ctx.client.post(withdrawal_url, headers=attendee.headers)
    expect_status(cutoff, 409)
    expect_detail(cutoff, "The withdrawal cutoff has passed.")
    [unchanged] = db_query(
        "select status, withdrawn_at from public.event_registrations "
        f"where id = '{registration['id']}'"
    )
    expect(unchanged == {"status": "registered", "withdrawn_at": None}, f"cutoff refusal changed registration: {unchanged}")

    db_query(
        "update public.events set withdrawal_closes_at = starts_at "
        f"where id = '{event_id}'"
    )
    withdrawn = ctx.client.post(withdrawal_url, headers=attendee.headers)
    expect_status(withdrawn, 200)
    expect(withdrawn.json() == {"registration_id": registration["id"], "status": "withdrawn"},
           f"unexpected withdrawal response: {withdrawn.json()}")
    [stored] = db_query(
        "select status, withdrawn_at from public.event_registrations "
        f"where id = '{registration['id']}'"
    )
    expect(stored["status"] == "withdrawn" and stored["withdrawn_at"], f"withdrawal was not persisted: {stored}")

    public_event = ctx.client.get(f"{ctx.api}/public/events/{event_id}")
    expect_status(public_event, 200)
    expect(public_event.json()["registered_count"] == 0, "the released place is still counted")
    my_events = ctx.client.get(f"{ctx.api}/registrations/me", headers=attendee.headers)
    expect_status(my_events, 200)
    expect(event_id not in {row["event"]["id"] for row in my_events.json()["registrations"]},
           "the withdrawn event remains in My events")

    repeated = ctx.client.post(withdrawal_url, headers=attendee.headers)
    expect_status(repeated, 409)
    expect_detail(repeated, "This registration has already been withdrawn.")
    expect(ctx.client.get(f"{ctx.api}/public/events/{event_id}").json()["registered_count"] == 0,
           "a repeated withdrawal changed the available-place count")

    reregistered = ctx.client.post(
        f"{ctx.api}/public/events/{event_id}/registrations",
        headers=attendee.headers,
    )
    expect_status(reregistered, 201)
    expect(reregistered.json()["status"] == "registered", f"unexpected re-registration: {reregistered.json()}")
    expect(ctx.client.get(f"{ctx.api}/public/events/{event_id}").json()["registered_count"] == 1,
           "re-registration did not consume a place")

    second_withdrawal = ctx.client.post(withdrawal_url, headers=attendee.headers)
    expect_status(second_withdrawal, 200)
    db_query(f"update public.events set re_registration_allowed = false where id = '{event_id}'")
    refused = ctx.client.post(
        f"{ctx.api}/public/events/{event_id}/registrations",
        headers=attendee.headers,
    )
    expect_status(refused, 409)
    expect_detail(refused, "Re-registration is not allowed for this event.")
    [final] = db_query(
        "select r.status, r.withdrawn_at, "
        "(select count(*) from public.event_registrations active "
        "where active.event_id = r.event_id and active.status = 'registered') as registered_count "
        "from public.event_registrations r "
        f"where r.id = '{registration['id']}'"
    )
    expect(final["status"] == "withdrawn" and final["withdrawn_at"] and int(final["registered_count"]) == 0,
           f"disabled re-registration changed the withdrawn registration: {final}")


@check(
    "TC-REG-021",
    "Two concurrent Attendees competing for the final place produce one registration and one waitlist entry",
    creates_accounts=True,
    needs_db=True,
)
def _(ctx: Context) -> None:
    require_waitlist_migration()
    event_id = throwaway_event(ctx, "021", "2031-06-21 09:00+08", "2031-06-21 12:00+08",
                               status="confirmed")
    db_query(
        "update public.events set registration_enabled = true, registration_capacity = 1, "
        "registration_opens_at = now() - interval '1 day', "
        "registration_closes_at = now() + interval '29 days', waitlist_enabled = true "
        f"where id = '{event_id}' returning id"
    )

    email = ctx.throwaway_email("REG021")
    expect_status(
        ctx.signup(
            role="attendee",
            full_name="Waitlist Concurrency Check",
            email=email,
            organisation_name=None,
            phone_number=None,
        ),
        201,
    )
    attendees = [
        ctx.shared("attendee"),
        ctx.login("attendee", email=email, password=THROWAWAY_PASSWORD),
    ]

    def register(session: Session) -> httpx.Response:
        return ctx.client.post(
            f"{ctx.api}/public/events/{event_id}/registrations",
            headers=session.headers,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(register, attendees))
    for response in responses:
        expect_status(response, 201)
    statuses = [response.json().get("status") for response in responses]
    expect(sorted(statuses) == ["registered", "waitlisted"],
           f"concurrent registrations returned {statuses!r}")

    rows = db_query(
        "select status, count(*)::integer as count from public.event_registrations "
        f"where event_id = '{event_id}' group by status"
    )
    counts = {row["status"]: int(row["count"]) for row in rows}
    expect(counts == {"registered": 1, "waitlisted": 1},
           f"stored outcomes were {counts!r}, expected one registered and one waitlisted")


@check(
    "TC-REG-023",
    "SCRUM-55 withdrawals invite the earliest waitlisted Attendees in FIFO order",
    creates_accounts=True,
    needs_db=True,
)
def _(ctx: Context) -> None:
    require_waitlist_migration()
    starts_at = "2031-06-22 09:00+08"
    event_id = throwaway_event(ctx, "023", starts_at, "2031-06-22 12:00+08",
                               status="confirmed", assigned=False)
    db_query(
        "update public.events set registration_enabled = true, registration_capacity = 2, "
        "registration_opens_at = now() - interval '1 day', "
        f"registration_closes_at = '{starts_at}', withdrawal_closes_at = '{starts_at}', "
        f"waitlist_enabled = true where id = '{event_id}'"
    )

    def attendee(case: str, full_name: str) -> Session:
        email = ctx.throwaway_email(f"REG023-{case}")
        expect_status(
            ctx.signup(
                role="attendee",
                full_name=full_name,
                email=email,
                organisation_name=None,
                phone_number=None,
            ),
            201,
        )
        return ctx.login("attendee", email=email, password=THROWAWAY_PASSWORD)

    occupants = [
        attendee("occupant-1", "Waitlist Withdrawal Occupant 1"),
        attendee("occupant-2", "Waitlist Withdrawal Occupant 2"),
    ]
    queued = [
        attendee("queued-1", "Waitlist Withdrawal Queue 1"),
        attendee("queued-2", "Waitlist Withdrawal Queue 2"),
        attendee("queued-3", "Waitlist Withdrawal Queue 3"),
    ]
    registration_url = f"{ctx.api}/public/events/{event_id}/registrations"
    for session, expected in [
        (occupants[0], "registered"),
        (occupants[1], "registered"),
        (queued[0], "waitlisted"),
        (queued[1], "waitlisted"),
        (queued[2], "waitlisted"),
    ]:
        response = ctx.client.post(registration_url, headers=session.headers)
        expect_status(response, 201)
        expect(response.json()["status"] == expected,
               f"{session.body['profile']['email']} was {response.json()['status']}, expected {expected}")

    withdrawal_url = f"{ctx.api}/registrations/{event_id}/withdraw"
    for session in occupants:
        response = ctx.client.post(withdrawal_url, headers=session.headers)
        expect_status(response, 200)
        expect(response.json()["status"] == "withdrawn", f"unexpected withdrawal: {response.json()}")

    registrations = db_query(
        "select attendee_id::text as attendee_id, status::text as status, "
        "(invited_at is not null and invitation_expires_at = invited_at + interval '24 hours') "
        "as has_24_hour_invitation "
        f"from public.event_registrations where event_id = '{event_id}'"
    )
    expected_statuses = {
        session.body["profile"]["id"]: status
        for session, status in [
            (occupants[0], "withdrawn"),
            (occupants[1], "withdrawn"),
            (queued[0], "invited"),
            (queued[1], "invited"),
            (queued[2], "waitlisted"),
        ]
    }
    actual_statuses = {row["attendee_id"]: row["status"] for row in registrations}
    expect(actual_statuses == expected_statuses, f"withdrawal did not preserve FIFO invitation order: {actual_statuses}")
    for session in queued[:2]:
        row = next(item for item in registrations if item["attendee_id"] == session.body["profile"]["id"])
        expect(row["has_24_hour_invitation"], f"invitation reservation is missing its 24-hour deadline: {row}")

    notices = db_query(
        "select recipient_id::text as recipient_id, recipient_role::text as recipient_role, type::text as type "
        f"from public.notifications where event_id = '{event_id}' and type = 'attendee_waitlist_invitation'"
    )
    expected_recipients = {session.body["profile"]["id"] for session in queued[:2]}
    expect(
        {(row["recipient_id"], row["recipient_role"], row["type"]) for row in notices}
        == {(recipient, "attendee", "attendee_waitlist_invitation") for recipient in expected_recipients},
        f"withdrawal invitations or their notifications were not delivered to the FIFO attendees: {notices}",
    )
    [occupied] = db_query(f"select public.registration_occupied_count('{event_id}')::integer as count")
    public_event = ctx.client.get(f"{ctx.api}/public/events/{event_id}")
    expect_status(public_event, 200)
    expect(int(occupied["count"]) == 2, f"registered attendees plus reservations exceed capacity: {occupied}")
    expect(public_event.json()["registered_count"] == 0,
           "invitation reservations were reported as registered attendees")


# --- Coordinator dashboard (SCRUM-72) --------------------------------------

COORDINATOR_DASHBOARD = "/events/dashboard/coordinator"
ACTIVE_COORDINATOR_STATUSES = {"under_review", "returned", "planning", "safety_review", "confirmed", "preparation"}
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


@check("TC-DASH-030", "Coordinator dashboard lists the caller's rejected events apart from active ones")
def _(ctx: Context) -> None:
    body = coordinator_dashboard(ctx)
    rejected = {event["event_id"] for event in body["rejected_events"]}
    overlap = rejected & {event["event_id"] for event in body["active_events"]}
    expect(not overlap, f"events listed as both active and rejected: {overlap}")
    headers = ctx.shared("event_coordinator").headers
    for event_id in sorted(rejected)[:5]:
        # Readable by the caller (so assigned to them) and really rejected.
        response = ctx.client.get(f"{ctx.api}/events/{event_id}", headers=headers)
        expect_status(response, 200)
        expect(response.json()["status"] == "rejected", f"{event_id} is listed as rejected but is {response.json()['status']}")


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
    expect(set(body) == {"action_items", "active_events", "rejected_events"}, f"unexpected fields: {sorted(body)}")


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
# Preparation follows Confirmed and is still the coordinator's work (D73).
LEAD_ACTIVE_STATUSES = {"under_review", "returned", "planning", "safety_review", "confirmed", "preparation"}
# The Lead's queue also holds events waiting for a coordinator (SCRUM-12).
LEAD_DASHBOARD_STATUSES = LEAD_ACTIVE_STATUSES | {"submitted"}
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
    stray = {event["status"] for event in listed} - LEAD_DASHBOARD_STATUSES
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


@check("TC-LEAD-015", "With two Leads, both see the whole queue and each sees only the events in their own scope", needs_db=True)
def _(ctx: Context) -> None:
    # Read-only. The expectation is computed from the database (events.assigned_by) and compared
    # with what each Lead's dashboard returns, so it does not depend on which events exist.
    leads = {
        row["email"]: row["id"]
        for row in db_query(
            "select p.email, p.id from public.profiles p join public.user_roles ur on ur.profile_id = p.id "
            "where ur.role = 'event_coordinator_lead'"
        )
    }
    first, second = W7_STAFF_ACCOUNTS["event_coordinator_lead"], W7_STAFF_ACCOUNTS["event_coordinator_lead_2"]
    expect(first in leads and second in leads, f"both Lead accounts must exist (found {sorted(leads)}): see supabase/seed.sql")
    statuses = ", ".join(f"'{status}'" for status in sorted(LEAD_DASHBOARD_STATUSES))
    events = db_query(f"select id, coordinator_id, assigned_by from public.events where status in ({statuses})")

    def expected(lead_id: str) -> tuple[set[str], set[str]]:
        queue = {e["id"] for e in events if e["coordinator_id"] is None}
        scope = {
            e["id"]
            for e in events
            if e["coordinator_id"] is not None
            and (e["assigned_by"] is None or e["assigned_by"] == lead_id or e["assigned_by"] not in leads.values())
        }
        return queue, scope

    seen = {}
    for role, email in (("event_coordinator_lead", first), ("event_coordinator_lead_2", second)):
        response = ctx.client.get(f"{ctx.api}{LEAD_DASHBOARD}", headers=ctx.shared(role).headers)
        expect_status(response, 200)
        body = response.json()
        queue, scope = expected(leads[email])
        got_queue = {e["event_id"] for e in body["unassigned"]}
        got_scope = {e["event_id"] for e in body["active_events"]}
        expect(got_queue == queue, f"{email}: queue differs. missing {queue - got_queue}, extra {got_queue - queue}")
        expect(got_scope == scope, f"{email}: scope differs. missing {scope - got_scope}, extra {got_scope - scope}")
        seen[email] = got_queue
    expect(seen[first] == seen[second], "the two Leads do not see the same unassigned queue")


@check("TC-LEAD-005", "The Lead dashboard and reassign without a token are 401")
def _(ctx: Context) -> None:
    expect_status(ctx.client.get(f"{ctx.api}{LEAD_DASHBOARD}"), 401)
    expect_status(
        ctx.client.post(f"{ctx.api}/events/{UNKNOWN_EVENT}/reassign", json={"coordinator_id": SOME_COORDINATOR, "expected_version": 1}), 401
    )


# --- Coordinator assignment (SCRUM-12) --------------------------------------
# Every check works on its own throwaway events (named "live-check ...", deleted when the run
# ends, with their history and notifications), never on seeded ones.

SECOND_COORDINATOR = "a0000000-0000-4000-8000-000000000008"
ASSIGN_OTHER_ROLES = ("event_organiser", "event_coordinator", "venue_staff", "tech_support", "attendee", "safety_officer")


def queued_event(ctx: Context, case: str) -> str:
    return throwaway_event(ctx, case, "2031-08-12 09:00+08", "2031-08-12 17:00+08", status="submitted", assigned=False)


def assign(ctx: Context, session: Session, event_id: str, coordinator_id: str = SOME_COORDINATOR) -> httpx.Response:
    return ctx.client.post(f"{ctx.api}/events/{event_id}/assign", headers=session.headers, json={"coordinator_id": coordinator_id})


def event_row(event_id: str) -> dict:
    return db_query(f"select status, coordinator_id, assigned_by, assigned_at from public.events where id = '{event_id}'")[0]


def lead_session(ctx: Context, role: str = "event_coordinator_lead") -> Session:
    return ctx.shared(role)


@check("TC-ASSIGN-001", "A submitted event joins the queue with no coordinator and no notice", needs_db=True)
def _(ctx: Context) -> None:
    organiser = ctx.shared("event_organiser")
    created = ctx.client.post(
        f"{ctx.api}/events",
        headers=organiser.headers,
        json={
            "name": f"{THROWAWAY_EVENT_PREFIX}{ctx.run_id} 12-001",
            "purpose": "Live check",
            "starts_at": "2031-08-12T09:00:00+08:00",
            "ends_at": "2031-08-12T17:00:00+08:00",
            "expected_attendance": 40,
            "layout_preference": "theatre",
            "facilities_required": ["projector"],
        },
    )
    expect_status(created, 201)
    event_id = created.json()["id"]
    submitted = ctx.client.post(f"{ctx.api}/events/{event_id}/submit", headers=organiser.headers)
    expect_status(submitted, 200)
    expect(submitted.json()["status"] == "submitted", f"status is {submitted.json()['status']}, expected submitted")
    row = event_row(event_id)
    expect(row["coordinator_id"] is None, "a coordinator was set on submission")
    notified = db_query(f"select count(*) as n from public.notifications where event_id = '{event_id}' and type = 'event_assigned'")
    expect(int(notified[0]["n"]) == 0, "a coordinator was notified on submission")
    queue = ctx.client.get(f"{ctx.api}{LEAD_DASHBOARD}", headers=lead_session(ctx).headers).json()["unassigned"]
    expect(event_id in {e["event_id"] for e in queue}, "the submitted event is not in the Lead's queue")


@check("TC-ASSIGN-002", "The queue is oldest submission first and carries the basic information", needs_db=True)
def _(ctx: Context) -> None:
    older, newer = queued_event(ctx, "12-002a"), queued_event(ctx, "12-002b")
    db_query(f"update public.events set submitted_at = now() - interval '2 days', expected_attendance = 55, layout_preference = 'theatre' where id = '{older}'")
    db_query(f"update public.events set submitted_at = now() - interval '1 day' where id = '{newer}'")
    queue = ctx.client.get(f"{ctx.api}{LEAD_DASHBOARD}", headers=lead_session(ctx).headers).json()["unassigned"]
    ids = [e["event_id"] for e in queue]
    expect(older in ids and newer in ids, "the throwaway events are not in the queue")
    expect(ids.index(older) < ids.index(newer), "the older submission is not listed first")
    stamps = [e["submitted_at"] for e in queue if e["submitted_at"]]
    expect(stamps == sorted(stamps), "the queue is not in submission order")
    entry = queue[ids.index(older)]
    expect(entry["event_name"] and entry["starts_at"] and entry["expected_attendance"] == 55 and entry["layout_preference"] == "theatre",
           f"basic information missing: {entry}")


@check("TC-ASSIGN-003", "The Lead assigns a coordinator: status, who and when, history, notices, off the queue", needs_db=True)
def _(ctx: Context) -> None:
    event_id = queued_event(ctx, "12-003")
    lead = lead_session(ctx)
    response = assign(ctx, lead, event_id)
    expect_status(response, 200)
    row = event_row(event_id)
    expect(row["status"] == "under_review" and row["coordinator_id"] == SOME_COORDINATOR, f"unexpected row: {row}")
    expect(row["assigned_by"] == lead.body["profile"]["id"] and row["assigned_at"], "assigner or time not recorded")
    history = db_query(
        f"select h.actor_id, h.reason from public.event_status_history h where h.event_id = '{event_id}' "
        "and h.from_status = 'submitted' and h.to_status = 'under_review'"
    )
    expect(len(history) == 1 and history[0]["actor_id"] == lead.body["profile"]["id"] and "Assigned to" in history[0]["reason"],
           f"history row wrong: {history}")
    notices = db_query(f"select recipient_id from public.notifications where event_id = '{event_id}'")
    recipients = sorted(n["recipient_id"] for n in notices)
    expect(recipients == sorted([SOME_COORDINATOR, "a0000000-0000-4000-8000-000000000001"]), f"notified {recipients}")
    queue = ctx.client.get(f"{ctx.api}{LEAD_DASHBOARD}", headers=lead.headers).json()["unassigned"]
    expect(event_id not in {e["event_id"] for e in queue}, "the assigned event is still in the queue")


@check("TC-ASSIGN-004", "Only an Event Coordinator can be assigned", needs_db=True)
def _(ctx: Context) -> None:
    event_id = queued_event(ctx, "12-004")
    lead = lead_session(ctx)
    for target in (lead.body["profile"]["id"], "a0000000-0000-4000-8000-000000000003", UNKNOWN_EVENT):
        response = assign(ctx, lead, event_id, target)
        expect_status(response, 422)
        expect_detail(response, "That person is not an Event Coordinator.")
    expect(event_row(event_id)["status"] == "submitted", "a refused assignment changed the event")


@check("TC-ASSIGN-005", "An assigned event cannot be assigned again; two Leads at once leave one winner", needs_db=True)
def _(ctx: Context) -> None:
    taken = queued_event(ctx, "12-005a")
    lead = lead_session(ctx)
    expect_status(assign(ctx, lead, taken), 200)
    for target in (SOME_COORDINATOR, SECOND_COORDINATOR):
        again = assign(ctx, lead, taken, target)
        expect_status(again, 409)
        expect_detail(again, "This event is already assigned.")
    expect(event_row(taken)["coordinator_id"] == SOME_COORDINATOR, "the coordinator changed")

    contested = queued_event(ctx, "12-005b")
    lead_two = lead_session(ctx, "event_coordinator_lead_2")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(assign, ctx, lead, contested, SOME_COORDINATOR)
        second = pool.submit(assign, ctx, lead_two, contested, SECOND_COORDINATOR)
        codes = sorted([first.result().status_code, second.result().status_code])
    expect(codes == [200, 409], f"expected one 200 and one 409, got {codes}")


@check("TC-ASSIGN-006", "A draft is not in the queue and cannot be assigned", needs_db=True)
def _(ctx: Context) -> None:
    draft = throwaway_event(ctx, "12-006", "2031-08-12 09:00+08", "2031-08-12 17:00+08", status="draft", assigned=False)
    lead = lead_session(ctx)
    expect_status(assign(ctx, lead, draft), 404)
    queue = ctx.client.get(f"{ctx.api}{LEAD_DASHBOARD}", headers=lead.headers).json()
    listed = {e["event_id"] for e in queue["unassigned"] + queue["active_events"]}
    expect(draft not in listed, "a draft is on the Lead's dashboard")


@check("TC-ASSIGN-007", "Every other active role is refused the assignment and the queue", needs_db=True)
def _(ctx: Context) -> None:
    event_id = queued_event(ctx, "12-007")
    for role in ASSIGN_OTHER_ROLES:
        session = ctx.shared(role)
        for response in (assign(ctx, session, event_id), ctx.client.get(f"{ctx.api}{LEAD_DASHBOARD}", headers=session.headers)):
            expect(response.status_code == 403, f"{role} got HTTP {response.status_code}, expected 403")
    expect(event_row(event_id)["status"] == "submitted", "a refused assignment changed the event")


@check("TC-ASSIGN-008", "Only the assigned coordinator can manage the event", needs_db=True)
def _(ctx: Context) -> None:
    event_id = queued_event(ctx, "12-008")
    expect_status(assign(ctx, lead_session(ctx), event_id), 200)
    other_email = db_query(f"select email from public.profiles where id = '{SECOND_COORDINATOR}'")[0]["email"]
    other = ctx.login("event_coordinator", email=other_email)
    denied = ctx.client.post(f"{ctx.api}/events/{event_id}/approve", headers=other.headers)
    expect(denied.status_code == 403, f"another coordinator got HTTP {denied.status_code}, expected 403")
    allowed = ctx.client.post(f"{ctx.api}/events/{event_id}/approve", headers=ctx.shared("event_coordinator").headers)
    expect_status(allowed, 200)


@check("TC-ASSIGN-009", "A Lead cannot act on an event as its coordinator", needs_db=True)
def _(ctx: Context) -> None:
    event_id = queued_event(ctx, "12-009")
    expect_status(assign(ctx, lead_session(ctx), event_id), 200)
    lead = lead_session(ctx)
    bodies = {
        "approve": None,
        "reject": {"reason": "Live check"},
        "return": {"message": "Live check", "flagged_fields": []},
        "send-for-safety-check": None,
    }
    for action, body in bodies.items():
        response = ctx.client.post(f"{ctx.api}/events/{event_id}/{action}", headers=lead.headers, json=body)
        expect(response.status_code == 403, f"Lead got HTTP {response.status_code} on {action}, expected 403")
    expect(event_row(event_id)["status"] == "under_review", "the event moved")


@check("TC-ASSIGN-016", "A reassignment shows in the event's history with who, from and to; an assignment from the queue shows once", needs_db=True)
def _(ctx: Context) -> None:
    event_id = queued_event(ctx, "12-016")
    lead = lead_session(ctx)
    expect_status(assign(ctx, lead, event_id), 200)
    version = db_query(f"select version from public.events where id = '{event_id}'")[0]["version"]
    moved = ctx.client.post(
        f"{ctx.api}/events/{event_id}/reassign", headers=lead.headers,
        json={"coordinator_id": SECOND_COORDINATOR, "expected_version": version},
    )
    expect_status(moved, 200)
    # The organiser reads the history; the new coordinator would too.
    history = ctx.client.get(f"{ctx.api}/events/{event_id}/history", headers=ctx.shared("event_organiser").headers)
    expect_status(history, 200)
    entries = history.json()["entries"]
    reassigned = [e for e in entries if e["kind"] == "reassignment"]
    expect(len(reassigned) == 1, f"expected one reassignment entry, got {len(reassigned)}")
    entry = reassigned[0]
    expect(entry["actor"]["id"] == lead.body["profile"]["id"], "the reassigning Lead is not recorded")
    expect(entry["from_coordinator"]["id"] == SOME_COORDINATOR and entry["to_coordinator"]["id"] == SECOND_COORDINATOR,
           f"from/to wrong: {entry}")
    assigned = [e for e in entries if e["kind"] == "status" and e["from_status"] == "submitted" and e["to_status"] == "under_review"]
    expect(len(assigned) == 1, "the assignment from the queue should appear exactly once, as a status change")
    expect(entries[0]["kind"] == "reassignment", "history is not newest first")


# --- Sign-up (SCRUM-80) ----------------------------------------------------


FIXTURE_EVENT = "e0000000-0000-4000-8000-000000000201"  # supabase/seed.sql: under_review, assigned


@check("TC-REV-017", "The assigned coordinator's event read names the organiser and their organisation "
       "(SCRUM-49 AC3, D82)", needs_db=True)
def _(ctx: Context) -> None:
    [expected] = db_query(
        "select p.full_name, p.organisation_name from public.events e "
        f"join public.profiles p on p.id = e.organiser_id where e.id = '{FIXTURE_EVENT}'"
    )
    response = ctx.client.get(f"{ctx.api}/events/{FIXTURE_EVENT}", headers=ctx.shared("event_coordinator").headers)
    expect_status(response, 200)
    organiser = response.json().get("organiser")
    expect(organiser == {"full_name": expected["full_name"], "organisation_name": expected["organisation_name"]},
           f"organiser {organiser}, expected {expected}")


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

# A run deletes only its own throwaway rows, plus any an earlier run left more than
# STALE_AFTER ago (it stopped before cleaning up). That is longer than any run, so a
# run going at the same time (another developer's, or the browser suite, which uses
# the same names) never loses its rows mid-run.
STALE_AFTER = "6 hours"


def mine_or_stale(column: str, mine: str, anyone: str) -> str:
    """A condition matching this run's rows (`mine`) or another run's rows (`anyone`)
    left over for longer than STALE_AFTER. Both are `like` patterns."""
    return (f"({column} like '{mine}' or ({column} like '{anyone}' "
            f"and created_at < now() - interval '{STALE_AFTER}'))")


def block_note(ctx: Context) -> str:
    """The note on this run's throwaway venue blocks, so its cleanup can tell them apart."""
    return f"{THROWAWAY_BLOCK_NOTE} {ctx.run_id}"


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


def delete_throwaway_bookings(run_id: str) -> int:
    """Deletes this run's booking-check events (their bookings first: that foreign key
    restricts) and blocks, and any an earlier run left (STALE_AFTER). Their history
    and notifications cascade."""
    events = mine_or_stale("name", f"{THROWAWAY_EVENT_PREFIX}{run_id} %", f"{THROWAWAY_EVENT_PREFIX}%")
    db_query(f"delete from public.venue_bookings where event_id in (select id from public.events where {events})")
    blocks = mine_or_stale("notes", f"{THROWAWAY_BLOCK_NOTE} {run_id}", f"{THROWAWAY_BLOCK_NOTE}%")
    db_query(f"delete from public.venue_blocks where {blocks}")
    deleted = len(db_query(f"delete from public.events where {events} returning id"))
    # SCRUM-24's throwaway equipment, after its events' lines (that foreign key
    # restricts); its reservations cascade.
    equipment = mine_or_stale("name", f"{THROWAWAY_EQUIPMENT_PREFIX}{run_id} %", f"{THROWAWAY_EVENT_PREFIX}%")
    db_query(f"delete from public.equipment where {equipment}")
    # CR-94's throwaway venues, named like its events: their layouts, facilities and
    # edit history cascade.
    venues = mine_or_stale("name", f"{THROWAWAY_EVENT_PREFIX}{run_id} %", f"{THROWAWAY_EVENT_PREFIX}%")
    db_query(f"delete from public.venues where {venues}")
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


def delete_throwaway_venues(run_id: str) -> int:
    """Deletes this run's deactivation-check venues, and any an earlier run left
    (STALE_AFTER), their bookings first (that foreign key restricts). Layouts,
    facilities and edit history cascade."""
    venues = mine_or_stale("name", f"{THROWAWAY_VENUE_PREFIX}{run_id} %", f"{THROWAWAY_VENUE_PREFIX}%")
    db_query(f"delete from public.venue_bookings where venue_id in (select id from public.venues where {venues})")
    return len(db_query(f"delete from public.venues where {venues} returning id"))


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

    # Booking requests already notified venue staff; inspect only new recipients
    # when checking the deactivation's audience.
    previous_notices = {row["id"] for row in db_query(
        f"select id from public.notifications where event_id = '{event_id}'")}
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
    organiser_id = "a0000000-0000-4000-8000-000000000001"  # throwaway_event's organiser
    organiser_notified = db_query(
        f"select recipient_id from public.notifications where event_id = '{event_id}' and type = 'venue_unavailable_organiser'")
    expect([row["recipient_id"] for row in organiser_notified] == [organiser_id],
           f"venue_unavailable_organiser went to {organiser_notified} (want the organiser once)")
    new_notices = [row for row in db_query(
        f"select id, recipient_id from public.notifications where event_id = '{event_id}'")
        if row["id"] not in previous_notices]
    expect(all(row["recipient_id"] in (organiser_id, COORDINATOR_ID) for row in new_notices),
           f"deactivation notified someone other than the organiser or coordinator: {new_notices}")


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


@check("TC-VENUE-097", "Deactivating again after reactivation previews the still-flagged booking", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "097")
    event_id = throwaway_event(ctx, "097", "2031-07-04 10:00+08", "2031-07-04 12:00+08")
    expect_status(request_venue(ctx, ctx.shared("event_coordinator"), event_id, venue_id), 201)
    staff = ctx.shared("venue_staff")
    expect_status(deactivate(ctx, staff, venue_id, confirm=True), 200)
    expect_status(ctx.client.post(f"{ctx.api}/venues/{venue_id}/reactivate", headers=staff.headers,
                                  json={"version": venue_version(venue_id)}), 200)
    notices_before = db_query(f"select count(*)::int as n from public.notifications where event_id = '{event_id}'")[0]["n"]

    preview = deactivate(ctx, staff, venue_id)
    expect_status(preview, 200)
    body = preview.json()
    expect(body["saved"] is False and [(b["event_id"], b["flag"]) for b in body["affected"]] == [(event_id, "affected")],
           f"second preview is {body}")
    expect_status(deactivate(ctx, staff, venue_id, confirm=True), 200)
    [booking] = db_query(f"select flag::text as flag from public.venue_bookings where event_id = '{event_id}'")
    expect(booking["flag"] == "affected", f"the flag became {booking['flag']}")
    notices_after = db_query(f"select count(*)::int as n from public.notifications where event_id = '{event_id}'")[0]["n"]
    expect(notices_after == notices_before, f"deactivating again sent {notices_after - notices_before} more notice(s)")


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
        f"'maintenance', '{block_note(ctx)}')"
    )
    event_id = throwaway_event(ctx, "003", "2031-05-22 11:00+08", "2031-05-22 13:00+08")

    response = request_venue(ctx, ctx.shared("event_coordinator"), event_id, HERITAGE_HALL)
    expect_status(response, 409)
    expect_detail(response, "Venue blocked for this time.")


@check("TC-BOOK-004", "An event that already holds a venue can't request another")
def _(ctx: Context) -> None:
    # Without its held booking the request would succeed and book Heritage Hall for
    # real (D78), so stop as blocked first. PLANNING_FIXTURE is SAFE_EVENT.
    safety_fixture(ctx)
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

# --- CR-100: venue defaults, safety facts, history and active-role denial ----

def require_venue_buffer_migration() -> None:
    rows = db_query("select count(*) = 4 as present from information_schema.columns "
                    "where table_schema = 'public' and table_name = 'venues' "
                    "and column_name in ('setup_minutes', 'turnaround_minutes', 'emergency_access', 'restrictions')")
    if not rows[0]["present"]:
        raise CheckBlocked("CR-100 venue-buffer migration is not deployed; verify after the merged migration reaches this project.")


@check("TC-VENUE-089", "CR-100 edit, read, clear and history on a throwaway venue", needs_db=True)
def _(ctx: Context) -> None:
    require_venue_buffer_migration()
    venue_id = throwaway_venue(ctx, "089")
    headers = ctx.shared("venue_staff").headers
    url = f"{ctx.api}/venues/{venue_id}"
    response = ctx.client.get(url, headers=headers)
    expect_status(response, 200)
    venue = response.json()
    expect(venue["setup_minutes"] == venue["turnaround_minutes"] == 0, "defaults are not zero")
    payload = {key: venue[key] for key in (
        "name", "location", "capacity", "opens_at", "closes_at", "description", "layouts", "facilities", "accessibility_features")}
    payload.update(setup_minutes=30, turnaround_minutes=1000000,
                   emergency_access="East exit\nCourtyard", restrictions="No flames")
    response = ctx.client.patch(url, headers=headers, json=payload)
    expect_status(response, 200)
    expect(response.json()["saved"], "edit was not saved")
    response = ctx.client.get(url, headers=ctx.shared("event_coordinator").headers)
    expect_status(response, 200)
    for key in ("setup_minutes", "turnaround_minutes", "emergency_access", "restrictions"):
        expect(response.json()[key] == payload[key], f"{key} did not round-trip")
    response = ctx.client.get(url + "/history", headers=headers)
    expect_status(response, 200)
    entry = response.json()["entries"][0]
    expect(entry["actor"]["id"] == VENUE_STAFF_ID and entry["at"], "history lacks actor/time")
    expect(entry["before"]["setup_minutes"] == 0 and entry["after"]["setup_minutes"] == 30,
           "history lacks buffer change")
    payload.update(emergency_access="   ", restrictions=None)
    response = ctx.client.patch(url, headers=headers, json=payload)
    expect_status(response, 200)
    expect(response.json()["venue"]["emergency_access"] is None
           and response.json()["venue"]["restrictions"] is None, "safety facts did not clear")


@check("TC-VENUE-091", "CR-100 recorded venue safety facts reach the Safety Officer review", needs_db=True)
def _(ctx: Context) -> None:
    require_venue_buffer_migration()
    venue_id = throwaway_venue(ctx, "091")
    db_query(f"update public.venues set emergency_access = 'East exit', restrictions = 'No flames' where id = '{venue_id}'")
    event_id = throwaway_event(ctx, "091", "2035-02-10T10:00:00Z", "2035-02-10T12:00:00Z", status="safety_review")
    db_query("insert into public.venue_bookings (event_id, venue_id, booked_period, status) values "
             f"('{event_id}', '{venue_id}', tstzrange('2035-02-10T10:00:00Z', '2035-02-10T12:00:00Z', '[)'), 'approved')")
    response = ctx.client.get(f"{ctx.api}/events/{event_id}/safety-review", headers=ctx.shared("safety_officer").headers)
    expect_status(response, 200)
    [venue] = response.json()["venues"]
    expect(venue["emergency_access"] == "East exit" and venue["restrictions"] == "No flames", "safety facts missing from review")


@check("TC-VENUE-090", "CR-100 invalid default minutes are rejected", needs_db=True)
def _(ctx: Context) -> None:
    require_venue_buffer_migration()
    venue_id = throwaway_venue(ctx, "090")
    headers = ctx.shared("venue_staff").headers
    payload = {"name": "live-check venue validation", "location": "Test", "capacity": 50,
               "opens_at": "08:00:00", "closes_at": "22:00:00", "setup_minutes": 0, "turnaround_minutes": 0}
    for field in ("setup_minutes", "turnaround_minutes"):
        for value in (-1, 2147483648, "abc", "", None, True, 1.5):
            expect_status(ctx.client.patch(f"{ctx.api}/venues/{venue_id}", headers=headers,
                                          json={**payload, field: value}), 422)


@check("TC-VENUE-093", "CR-100 only the active Venue Staff role can edit", needs_db=True)
def _(ctx: Context) -> None:
    require_venue_buffer_migration()
    # The seeded coordinator also holds Venue Staff. Its active coordinator
    # session must still get 403, including on a raw request bypassing the UI.
    payload = {"name": "Denied", "location": "Test", "capacity": 50, "opens_at": "08:00:00",
               "closes_at": "22:00:00", "setup_minutes": 30, "turnaround_minutes": 45,
               "emergency_access": "East exit", "restrictions": "No flames"}
    for role in ("event_organiser", "event_coordinator", "event_coordinator_lead", "safety_officer", "tech_support", "attendee"):
        expect_status(ctx.client.patch(f"{ctx.api}/venues/{INNOVATION_LAB}",
                                      headers=ctx.shared(role).headers, json=payload), 403)


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


# --- Venue staff approve a booking request (SCRUM-36) ---------------------------

def approve_booking(ctx: Context, session: Session, booking_id: str) -> httpx.Response:
    return ctx.client.post(f"{ctx.api}{BOOKINGS}/{booking_id}/approve", headers=session.headers)


def booking_status(booking_id: str) -> str:
    [row] = db_query(f"select status::text as status from public.venue_bookings where id = '{booking_id}'")
    return row["status"]


@check("TC-BOOK-051", "Approving a hold makes it Approved, records it, tells only the coordinator and keeps "
                      "the slot occupied", needs_db=True)
def _(ctx: Context) -> None:
    event_id, booking_id = hold_for(ctx, "051-a", "2031-08-04 14:00+08", "2031-08-04 17:00+08")
    other_event = throwaway_event(ctx, "051-b", "2031-08-04 16:00+08", "2031-08-04 18:00+08")

    response = approve_booking(ctx, ctx.shared("venue_staff"), booking_id)
    expect_status(response, 200)
    body = response.json()
    expect(body["status"] == "approved" and body["decision"] is None, f"booking reads {body}")
    expect([(e["action"], e["from_status"], e["to_status"]) for e in body["history"]] == [("approved", "held", "approved")],
           f"history is {body['history']}")
    [stored] = db_query(f"select decided_by, decided_at is not null as stamped from public.venue_bookings "
                        f"where id = '{booking_id}'")
    expect(stored == {"decided_by": VENUE_STAFF_ID, "stamped": True}, f"stored decision is {stored}")
    notified = db_query(f"select recipient_id from public.notifications "
                        f"where event_id = '{event_id}' and type = 'venue_booking_approved'")
    expect([row["recipient_id"] for row in notified] == [COORDINATOR_ID],
           f"venue_booking_approved went to {notified} (want the assigned coordinator only)")

    # AC5: the approved booking still occupies Innovation Lab.
    refused = request_venue(ctx, ctx.shared("event_coordinator"), other_event, INNOVATION_LAB)
    expect_status(refused, 409)
    expect_detail(refused, "Venue already held for this time by another event.")


@check("TC-BOOK-052", "Approval is refused when a block now overlaps the hold or the venue is inactive", needs_db=True)
def _(ctx: Context) -> None:
    staff = ctx.shared("venue_staff")
    # AC3: the block is saved after the hold, as CAL-R1 allows.
    _, blocked_id = hold_for(ctx, "052-a", "2031-08-05 14:00+08", "2031-08-05 17:00+08")
    db_query(
        "insert into public.venue_blocks (venue_id, blocked_period, reason, notes) values "
        f"('{INNOVATION_LAB}', tstzrange('2031-08-05 16:00+08', '2031-08-05 18:00+08', '[)'), "
        f"'maintenance', '{block_note(ctx)}')"
    )
    blocked = approve_booking(ctx, staff, blocked_id)
    expect_status(blocked, 409)
    expect_detail(blocked, "Venue blocked for this time.")
    expect(booking_status(blocked_id) == "held", "a refused approval changed the booking under the block")

    # AC4: a throwaway venue, deactivated after the hold was made.
    venue_id = throwaway_venue(ctx, "052")
    event_id = throwaway_event(ctx, "052-b", "2031-08-05 10:00+08", "2031-08-05 12:00+08")
    held = request_venue(ctx, ctx.shared("event_coordinator"), event_id, venue_id)
    expect_status(held, 201)
    expect_status(deactivate(ctx, staff, venue_id, confirm=True), 200)
    inactive = approve_booking(ctx, staff, held.json()["id"])
    expect_status(inactive, 409)
    expect_detail(inactive, "This venue is inactive, so the booking can't be approved.")
    expect(booking_status(held.json()["id"]) == "held", "a refused approval changed the booking at the inactive venue")


@check("TC-BOOK-053", "An expired hold, or a booking no longer held, can't be approved", needs_db=True)
def _(ctx: Context) -> None:
    staff = ctx.shared("venue_staff")
    # AC6: past its expiry, before the minute job has run.
    _, overdue_id = hold_for(ctx, "053-a", "2031-08-06 14:00+08", "2031-08-06 17:00+08")
    db_query(f"update public.venue_bookings set expires_at = now() - interval '1 minute' where id = '{overdue_id}'")
    expired = approve_booking(ctx, staff, overdue_id)
    expect_status(expired, 409)
    expect_detail(expired, "This hold has expired, so it can't be approved.")
    expect(booking_status(overdue_id) == "expired", "the overdue hold was not expired")

    _, rejected_id = hold_for(ctx, "053-b", "2031-08-06 18:00+08", "2031-08-06 19:00+08")
    expect_status(reject_booking(ctx, staff, rejected_id), 200)
    refused = approve_booking(ctx, staff, rejected_id)
    expect_status(refused, 409)
    expect_detail(refused, "Only a held booking can be approved. This one is already rejected.")

    _, approved_id = hold_for(ctx, "053-c", "2031-08-06 20:00+08", "2031-08-06 21:00+08")
    expect_status(approve_booking(ctx, staff, approved_id), 200)
    twice = approve_booking(ctx, staff, approved_id)
    expect_status(twice, 409)
    expect_detail(twice, "Only a held booking can be approved. This one is approved.")
    # 38 AC9 against a real approval, which TC-BOOK-017 had to fake.
    late = reject_booking(ctx, staff, approved_id)
    expect_status(late, 409)
    expect_detail(late, "Only a held booking can be rejected. This one is approved.")


@check("TC-BOOK-054", "Approve and reject sent at the same instant: exactly one outcome is saved", needs_db=True)
def _(ctx: Context) -> None:
    from concurrent.futures import ThreadPoolExecutor

    _, booking_id = hold_for(ctx, "054", "2031-08-07 14:00+08", "2031-08-07 17:00+08")
    staff = ctx.shared("venue_staff")

    def fire(action: str) -> tuple[str, int]:
        with httpx.Client(timeout=30) as client:
            body = {"reason": "Raced"} if action == "reject" else None
            return action, client.post(f"{ctx.api}{BOOKINGS}/{booking_id}/{action}", headers=staff.headers,
                                       json=body).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = dict(pool.map(fire, ["approve", "reject"]))
    expect(sorted(results.values()) == [200, 409], f"expected one 200 and one 409, got {results}")
    winner = "approved" if results["approve"] == 200 else "rejected"
    decisions = db_query("select action from public.venue_booking_history "
                         f"where booking_id = '{booking_id}' and action in ('approved', 'rejected')")
    expect([row["action"] for row in decisions] == [winner], f"history recorded {decisions}, want only {winner}")
    expect(booking_status(booking_id) == winner, f"the booking is {booking_status(booking_id)}, want {winner}")


@check("TC-BOOK-055", "Only a session acting as venue staff can approve", needs_db=True)
def _(ctx: Context) -> None:
    _, booking_id = hold_for(ctx, "055", "2031-08-08 14:00+08", "2031-08-08 17:00+08")
    for role in ("event_organiser", "event_coordinator", "tech_support", "attendee"):
        expect_status(approve_booking(ctx, ctx.shared(role), booking_id), 403)
    # SCRUM-76: the seeded coordinator also holds venue_staff, but acting as coordinator is refused.
    expect_status(approve_booking(ctx, ctx.login("event_coordinator"), booking_id), 403)
    expect(booking_status(booking_id) == "held", "a refused caller changed the booking")


@check("TC-BOOK-061", "Approving a replacement and restoring its original at the same instant: exactly one wins",
       needs_db=True)
def _(ctx: Context) -> None:
    from concurrent.futures import ThreadPoolExecutor

    # CR-95: an approved original flagged Affected at Heritage Hall, and its
    # held replacement at Innovation Lab. Both are this check's own rows.
    event_id = throwaway_event(ctx, "061", "2031-08-13 09:00+08", "2031-08-13 10:00+08")
    [original] = db_query(
        "insert into public.venue_bookings (event_id, venue_id, occupied_period, status, flag, flag_reason, flagged_at) "
        f"values ('{event_id}', '{HERITAGE_HALL}', tstzrange('2031-08-13 09:00+08', '2031-08-13 10:00+08', '[)'), "
        "'approved', 'affected', 'live check', now()) returning id"
    )
    [replacement] = db_query(
        "insert into public.venue_bookings (event_id, venue_id, occupied_period, status, replaces_booking_id) "
        f"values ('{event_id}', '{INNOVATION_LAB}', tstzrange('2031-08-13 09:00+08', '2031-08-13 10:00+08', '[)'), "
        f"'held', '{original['id']}') returning id"
    )
    staff = ctx.shared("venue_staff")

    def fire(call: tuple[str, str]) -> tuple[str, int]:
        action, booking_id = call
        with httpx.Client(timeout=30) as client:
            return action, client.post(f"{ctx.api}{BOOKINGS}/{booking_id}/{action}", headers=staff.headers).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = dict(pool.map(fire, [("approve", replacement["id"]), ("restore", original["id"])]))
    # A deadlock would surface as a 500 here, not a 409.
    expect(sorted(results.values()) == [200, 409], f"expected one 200 and one 409, got {results}")
    states = (booking_status(original["id"]), booking_status(replacement["id"]))
    want = ("released", "approved") if results["approve"] == 200 else ("approved", "cancelled")
    expect(states == want, f"original and replacement are {states}, want {want}")


# --- Venue staff block a venue (SCRUM-51) -----------------------------------
# Every block goes on a throwaway venue, so search and booking of seeded venues
# never change; the venues (and their blocks, links and history) are deleted
# with the booking checks' events.

def create_block(ctx: Context, session: Session | None, venue_id: str, starts: str, ends: str, **body):
    headers = session.headers if session else {}
    return ctx.client.post(f"{ctx.api}/venues/{venue_id}/blocks", headers=headers,
                           json={"starts_at": starts, "ends_at": ends, "reason": "maintenance", **body})


def search_lists(ctx: Context, venue_id: str, starts: str | None = None, ends: str | None = None) -> bool:
    params = {"starts_at": starts, "ends_at": ends} if starts else {}
    found = ctx.client.get(f"{ctx.api}/venues", params=params, headers=ctx.shared("event_coordinator").headers)
    expect_status(found, 200)
    return any(r["venue"]["id"] == venue_id and not r["excluded"] for r in found.json()["results"])


def blocks_on(venue_id: str) -> list[dict]:
    return db_query(f"select id, reason::text as reason, notes, created_by from public.venue_blocks "
                    f"where venue_id = '{venue_id}'")


@check("TC-BLOCK-001", "Venue staff block a venue with a reason; the block and its history row record who and what",
       needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "B001")
    response = create_block(ctx, ctx.shared("venue_staff"), venue_id, "2031-09-01T09:00:00+08:00",
                            "2031-09-01T17:00:00+08:00", reason="equipment_failure", detail="  Projector rig down  ")
    expect_status(response, 200)
    body = response.json()
    expect(body["saved"] is True and body["affected"] == [] and body["block"]["reason"] == "equipment_failure",
           f"response is {body}")
    [stored] = blocks_on(venue_id)
    expect(stored["notes"] == "Projector rig down" and stored["created_by"] == VENUE_STAFF_ID, f"stored block is {stored}")

    history = ctx.client.get(f"{ctx.api}/venues/{venue_id}/history", headers=ctx.shared("venue_staff").headers)
    expect_status(history, 200)
    [entry] = history.json()["entries"]
    expect(entry["actor"]["id"] == VENUE_STAFF_ID and entry["after"]["block"]["reason"] == "equipment_failure"
           and entry["after"]["block"]["notes"] == "Projector rig down", f"history entry is {entry}")


@check("TC-BLOCK-002", "Invalid or incomplete block input is refused with a message naming the problem", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "B002")
    staff = ctx.shared("venue_staff")
    cases = [
        ({"starts_at": "2031-09-02T17:00:00+08:00", "ends_at": "2031-09-02T09:00:00+08:00"}, "End must be after start."),
        ({"starts_at": "2020-09-02T09:00:00+08:00", "ends_at": "2020-09-02T17:00:00+08:00"}, "End must be in the future."),
        ({"reason": "other", "detail": "  "}, "A detail is required when the reason is Other."),
        ({"detail": "x" * 1001}, "The detail can be at most 1000 characters."),
        ({"reason": ""}, "reason"),
    ]
    for overrides, named in cases:
        body = {"starts_at": "2031-09-02T09:00:00+08:00", "ends_at": "2031-09-02T17:00:00+08:00", **overrides}
        response = create_block(ctx, staff, venue_id, body.pop("starts_at"), body.pop("ends_at"), **body)
        expect_status(response, 422)
        expect(named in response.text, f"{overrides} answered {response.text} (want it to name {named!r})")
    expect(blocks_on(venue_id) == [], "a refused block was saved")


@check("TC-BLOCK-003", "A blocked venue drops out of overlapping searches only, and returns when the block ends",
       needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "B003")
    expect_status(create_block(ctx, ctx.shared("venue_staff"), venue_id, "2031-09-03T09:00:00+08:00",
                               "2031-09-03T12:00:00+08:00"), 200)
    expect(not search_lists(ctx, venue_id, "2031-09-03T11:00:00+08:00", "2031-09-03T13:00:00+08:00"),
           "the venue appears in a search overlapping its block")
    # AC4: the block's end is exclusive and nothing has to be reset.
    expect(search_lists(ctx, venue_id, "2031-09-03T12:00:00+08:00", "2031-09-03T15:00:00+08:00"),
           "the venue is missing from a search starting when its block ends")
    expect(search_lists(ctx, venue_id), "the venue is missing from a search with no date/time")


@check("TC-BLOCK-004", "A booking request during a block is refused; one after it ends is accepted; approval of an "
                       "earlier hold is refused", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "B004")
    coordinator = ctx.shared("event_coordinator")
    staff = ctx.shared("venue_staff")
    early = throwaway_event(ctx, "B004-a", "2031-09-04 10:00+08", "2031-09-04 11:00+08")
    held = request_venue(ctx, coordinator, early, venue_id)
    expect_status(held, 201)
    expect_status(create_block(ctx, staff, venue_id, "2031-09-04T09:00:00+08:00", "2031-09-04T12:00:00+08:00",
                               confirm=True), 200)

    during = throwaway_event(ctx, "B004-b", "2031-09-04 11:00+08", "2031-09-04 13:00+08")
    refused = request_venue(ctx, coordinator, during, venue_id)
    expect_status(refused, 409)
    expect_detail(refused, "Venue blocked for this time.")
    after = throwaway_event(ctx, "B004-c", "2031-09-04 12:00+08", "2031-09-04 14:00+08")
    expect_status(request_venue(ctx, coordinator, after, venue_id), 201)

    approval = approve_booking(ctx, staff, held.json()["id"])
    expect_status(approval, 409)
    expect_detail(approval, "Venue blocked for this time.")


@check("TC-BLOCK-005", "Blocking over bookings previews them, then flags them Affected, notifies the coordinator "
                       "and lists them with event, status and reason", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "B005")
    staff = ctx.shared("venue_staff")
    held_event = throwaway_event(ctx, "B005-a", "2031-09-05 10:00+08", "2031-09-05 11:00+08")
    held = request_venue(ctx, ctx.shared("event_coordinator"), held_event, venue_id)
    expect_status(held, 201)
    approved_event = throwaway_event(ctx, "B005-b", "2031-09-05 13:00+08", "2031-09-05 14:00+08", status="confirmed")
    [approved] = db_query(
        "insert into public.venue_bookings (event_id, venue_id, booked_period, status) "
        f"values ('{approved_event}', '{venue_id}', tstzrange('2031-09-05 13:00+08', '2031-09-05 14:00+08', '[)'), "
        "'approved') returning id"
    )
    period = ("2031-09-05T09:00:00+08:00", "2031-09-05T15:00:00+08:00")

    preview = create_block(ctx, staff, venue_id, *period, reason="safety")
    expect_status(preview, 200)
    body = preview.json()
    expect(body["saved"] is False and sorted(b["booking_id"] for b in body["affected"])
           == sorted([held.json()["id"], approved["id"]]), f"preview is {body}")
    expect(blocks_on(venue_id) == [], "the preview saved the block")

    saved = create_block(ctx, staff, venue_id, *period, reason="safety", confirm=True)
    expect_status(saved, 200)
    rows = {b["booking_id"]: b for b in saved.json()["affected"]}
    expect(set(rows) == {held.json()["id"], approved["id"]}, f"saved affected is {saved.json()}")
    expect(rows[approved["id"]]["status"] == "approved" and rows[approved["id"]]["block_reason"] == "Safety"
           and rows[approved["id"]]["event_name"].endswith("B005-b"), f"affected row is {rows[approved['id']]}")

    flags = db_query(f"select status::text as status, flag::text as flag, flag_reason from public.venue_bookings "
                     f"where venue_id = '{venue_id}' order by status")
    expect(flags == [{"status": "approved", "flag": "affected", "flag_reason": "Venue unavailable: Safety"},
                     {"status": "held", "flag": "affected", "flag_reason": "Venue unavailable: Safety"}],
           f"bookings are {flags}")
    [event] = db_query(f"select status::text as status from public.events where id = '{approved_event}'")
    expect(event["status"] == "confirmed", f"the confirmed event moved to {event['status']}")
    notified = db_query(f"select recipient_id from public.notifications where event_id = '{approved_event}' "
                        "and type = 'venue_booking_affected'")
    expect([row["recipient_id"] for row in notified] == [COORDINATOR_ID],
           f"venue_booking_affected went to {notified} (want the coordinator once)")
    [organiser] = db_query(f"select message from public.notifications where event_id = '{approved_event}' "
                           "and type = 'venue_unavailable_organiser'")
    expect("Safety" not in organiser["message"] and "safety" not in organiser["message"],
           f"the organiser was told the reason: {organiser['message']}")


@check("TC-BLOCK-006", "Only a session acting as venue staff can block; a coordinator, a venue-staff holder acting "
                       "as coordinator, and no token are refused", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "B006")
    period = ("2031-09-06T09:00:00+08:00", "2031-09-06T12:00:00+08:00")
    # The seeded coordinator also holds Venue Staff; its shared session acts as coordinator.
    expect_status(create_block(ctx, ctx.shared("event_coordinator"), venue_id, *period), 403)
    for role in ("tech_support", "event_organiser"):
        expect_status(create_block(ctx, ctx.shared(role), venue_id, *period), 403)
    expect_status(create_block(ctx, None, venue_id, *period), 401)
    expect(blocks_on(venue_id) == [], "a refused caller saved a block")


@check("TC-BLOCK-007", "A block and a booking request for the same slot at the same instant never leave an "
                       "unflagged overlapping hold", needs_db=True)
def _(ctx: Context) -> None:
    from concurrent.futures import ThreadPoolExecutor

    coordinator = ctx.shared("event_coordinator")
    staff = ctx.shared("venue_staff")
    for attempt in range(3):
        venue_id = throwaway_venue(ctx, f"B007-{attempt}")
        event_id = throwaway_event(ctx, f"B007-{attempt}", "2031-09-07 10:00+08", "2031-09-07 12:00+08")

        def fire(kind: str) -> tuple[str, int]:
            with httpx.Client(timeout=30) as client:
                if kind == "block":
                    response = client.post(f"{ctx.api}/venues/{venue_id}/blocks", headers=staff.headers,
                                           json={"starts_at": "2031-09-07T09:00:00+08:00",
                                                 "ends_at": "2031-09-07T13:00:00+08:00",
                                                 "reason": "maintenance", "confirm": True})
                else:
                    response = client.post(f"{ctx.api}{BOOKINGS}", headers=coordinator.headers,
                                           json={"event_id": event_id, "venue_id": venue_id})
                return kind, response.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = dict(pool.map(fire, ["block", "request"]))
        expect(codes["block"] == 200 and codes["request"] in (201, 409), f"attempt {attempt}: {codes}")
        holds = db_query(
            "select vb.flag::text as flag, exists (select 1 from public.venue_block_bookings l "
            "where l.booking_id = vb.id) as linked from public.venue_bookings vb "
            f"where vb.venue_id = '{venue_id}' and vb.status = 'held'"
        )
        if codes["request"] == 201:
            expect(holds == [{"flag": "affected", "linked": True}], f"attempt {attempt}: the hold is {holds}")
        else:
            expect(holds == [], f"attempt {attempt}: a refused request left {holds}")


# --- Venue staff end, shorten or remove a block early (SCRUM-54) -----------
# Same throwaway venues as SCRUM-51, so seeded venues are never blocked; the
# blocks, their history and any bookings go with the venues at the end.

def change_block(ctx: Context, session: Session | None, venue_id: str, block_id: str, action: str, **body):
    headers = session.headers if session else {}
    return ctx.client.post(f"{ctx.api}/venues/{venue_id}/blocks/{block_id}/change", headers=headers,
                           json={"action": action, **body})


def _iso(moment: dt.datetime) -> str:
    return moment.isoformat(timespec="seconds")


@check("TC-BLOCK-020", "Venue staff end a started block now: it shows as Ended early, the history records it, and "
                       "the rest of its period is searchable again", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "B020")
    staff = ctx.shared("venue_staff")
    now = dt.datetime.now(dt.timezone.utc)
    created = create_block(ctx, staff, venue_id, _iso(now - dt.timedelta(hours=1)), _iso(now + dt.timedelta(hours=6)))
    expect_status(created, 200)
    block_id = created.json()["block"]["id"]
    later = (_iso(now + dt.timedelta(hours=3)), _iso(now + dt.timedelta(hours=4)))
    expect(not search_lists(ctx, venue_id, *later), "the venue was searchable during its block")

    ended = change_block(ctx, staff, venue_id, block_id, "end_now", note="  Repaired early  ")
    expect_status(ended, 200)
    block = ended.json()["block"]
    expect(block["status"] == "ended_early" and block["change_note"] == "Repaired early"
           and block["changed_by"]["id"] == VENUE_STAFF_ID and block["original_period"] is not None
           and block["created_by"]["id"] == VENUE_STAFF_ID, f"the ended block is {block}")
    expect(search_lists(ctx, venue_id, *later), "the freed time is not searchable after ending the block")

    history = ctx.client.get(f"{ctx.api}/venues/{venue_id}/history", headers=staff.headers)
    expect_status(history, 200)
    newest = history.json()["entries"][0]
    expect(newest["actor"]["id"] == VENUE_STAFF_ID and newest["after"]["block"]["status"] == "ended_early"
           and newest["after"]["block"]["note"] == "Repaired early" and newest["before"]["block"]["ends_at"],
           f"the newest history entry is {newest}")


@check("TC-BLOCK-021", "A block is shortened to an earlier end; lengthening, an end at its start, ending one that "
                       "hasn't started and changing one that ended are refused", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "B021")
    staff = ctx.shared("venue_staff")
    created = create_block(ctx, staff, venue_id, "2031-09-21T09:00:00+08:00", "2031-09-21T17:00:00+08:00")
    expect_status(created, 200)
    block_id = created.json()["block"]["id"]

    cases = [
        ("shorten", {"ends_at": "2031-09-21T18:00:00+08:00"}, 422,
         "The new end must be earlier than the current end. To block for longer, add a new block."),
        ("shorten", {"ends_at": "2031-09-21T09:00:00+08:00"}, 422, "The new end must be after the block's start."),
        ("end_now", {}, 409, "This block hasn't started yet. Remove it instead."),
        ("end_now", {"note": "x" * 1001}, 422, "The note can be at most 1000 characters."),
    ]
    for action, body, status, detail in cases:
        response = change_block(ctx, staff, venue_id, block_id, action, **body)
        expect_status(response, status)
        expect(detail in response.text, f"{action} {body} answered {response.text} (want {detail!r})")

    shortened = change_block(ctx, staff, venue_id, block_id, "shorten", ends_at="2031-09-21T12:00:00+08:00")
    expect_status(shortened, 200)
    period = shortened.json()["block"]["period"]
    expect(period["ends_at"].startswith("2031-09-21T04:00:00"), f"the shortened period is {period}")
    expect(search_lists(ctx, venue_id, "2031-09-21T12:00:00+08:00", "2031-09-21T15:00:00+08:00"),
           "the freed afternoon is not searchable")
    expect(not search_lists(ctx, venue_id, "2031-09-21T10:00:00+08:00", "2031-09-21T11:00:00+08:00"),
           "the morning the block still covers is searchable")

    # One that has ended can't be changed (a block whose end has passed).
    [past] = db_query(
        "insert into public.venue_blocks (venue_id, blocked_period, reason, notes) values "
        f"('{venue_id}', tstzrange(now() - interval '3 hours', now() - interval '1 hour', '[)'), 'maintenance', "
        f"'{block_note(ctx)}') returning id"
    )
    refused = change_block(ctx, staff, venue_id, past["id"], "end_now")
    expect_status(refused, 409)
    expect_detail(refused, "This block has already ended, so it can't be changed.")


@check("TC-BLOCK-022", "A block that hasn't started is removed: kept for history, gone from the venue's blocks and "
                       "from search; it can't be removed twice", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "B022")
    staff = ctx.shared("venue_staff")
    created = create_block(ctx, staff, venue_id, "2031-09-22T09:00:00+08:00", "2031-09-22T17:00:00+08:00")
    expect_status(created, 200)
    block_id = created.json()["block"]["id"]

    removed = change_block(ctx, staff, venue_id, block_id, "remove", note="Contractor cancelled")
    expect_status(removed, 200)
    expect(removed.json()["block"]["status"] == "removed", f"the removed block is {removed.json()['block']}")
    expect(len(blocks_on(venue_id)) == 1, "the removed block was deleted")
    venue = ctx.client.get(f"{ctx.api}/venues/{venue_id}", headers=staff.headers)
    expect_status(venue, 200)
    expect(venue.json()["upcoming_blocks"] == [], f"the venue still lists {venue.json()['upcoming_blocks']}")
    expect(search_lists(ctx, venue_id, "2031-09-22T10:00:00+08:00", "2031-09-22T11:00:00+08:00"),
           "the removed block's period is not searchable")

    again = change_block(ctx, staff, venue_id, block_id, "remove")
    expect_status(again, 409)
    expect_detail(again, "This block was removed, so it can't be changed.")


@check("TC-BLOCK-023", "Only a session acting as venue staff can change a block; a coordinator, a venue-staff "
                       "holder acting as coordinator, other roles and no token are refused", needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "B023")
    created = create_block(ctx, ctx.shared("venue_staff"), venue_id, "2031-09-23T09:00:00+08:00",
                           "2031-09-23T17:00:00+08:00")
    expect_status(created, 200)
    block_id = created.json()["block"]["id"]
    # The seeded coordinator also holds Venue Staff; its shared session acts as coordinator.
    for role in ("event_coordinator", "tech_support", "event_organiser"):
        expect_status(change_block(ctx, ctx.shared(role), venue_id, block_id, "remove"), 403)
    expect_status(change_block(ctx, None, venue_id, block_id, "remove"), 401)
    [stored] = db_query(f"select removed_at, changed_at from public.venue_blocks where id = '{block_id}'")
    expect(stored == {"removed_at": None, "changed_at": None}, f"a refused caller changed the block: {stored}")


@check("TC-BLOCK-024", "A booking the block flagged is listed once the block no longer covers it, stays Affected "
                       "until restored, and restoring tells the coordinator and organiser and leaves the event",
       needs_db=True)
def _(ctx: Context) -> None:
    venue_id = throwaway_venue(ctx, "B024")
    staff = ctx.shared("venue_staff")
    event_id = throwaway_event(ctx, "B024", "2031-09-24 13:00+08", "2031-09-24 14:00+08", status="confirmed")
    [booking] = db_query(
        "insert into public.venue_bookings (event_id, venue_id, booked_period, status) "
        f"values ('{event_id}', '{venue_id}', tstzrange('2031-09-24 13:00+08', '2031-09-24 14:00+08', '[)'), "
        "'approved') returning id"
    )
    created = create_block(ctx, staff, venue_id, "2031-09-24T09:00:00+08:00", "2031-09-24T17:00:00+08:00",
                           confirm=True)
    expect_status(created, 200)
    block_id = created.json()["block"]["id"]

    # Shortened to end before the booking's start: the booking is free and listed.
    shortened = change_block(ctx, staff, venue_id, block_id, "shorten", ends_at="2031-09-24T12:00:00+08:00")
    expect_status(shortened, 200)
    listed = shortened.json()["restorable"]
    expect([b["booking_id"] for b in listed] == [booking["id"]] and listed[0]["has_pending_replacement"] is False
           and listed[0]["block_reason"] == "Maintenance", f"restorable is {listed}")
    [flag] = db_query(f"select flag::text as flag from public.venue_bookings where id = '{booking['id']}'")
    expect(flag["flag"] == "affected", "shortening the block cleared the flag (QA3-9)")
    dashboard = ctx.client.get(f"{ctx.api}/venues/dashboard/venue-staff", headers=staff.headers)
    expect_status(dashboard, 200)
    mine = [b for b in dashboard.json()["affected_bookings"] if b["id"] == booking["id"]]
    expect(len(mine) == 1 and mine[0]["restorable"] is True, f"the dashboard shows {mine}")

    restored = ctx.client.post(f"{ctx.api}{BOOKINGS}/{booking['id']}/restore", headers=staff.headers)
    expect_status(restored, 200)
    expect(restored.json()["flag"] is None and restored.json()["status"] == "approved", f"restored is {restored.json()}")
    [event] = db_query(f"select status::text as status from public.events where id = '{event_id}'")
    expect(event["status"] == "confirmed", f"restoring moved the event to {event['status']}")
    roles = db_query(f"select recipient_role::text as role from public.notifications where event_id = '{event_id}' "
                     "and type = 'venue_booking_restored' order by 1")
    expect([r["role"] for r in roles] == ["event_coordinator", "event_organiser"],
           f"restore notices are addressed to {roles} (D83: the organiser's must have a role)")


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
        f"'maintenance', '{block_note(ctx)}')"
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

PROJECTOR_ID = "b0000000-0000-4000-8000-000000000001"  # supabase/seed.sql: 4K Projector, 14 in total
EQUIPMENT_REQUESTS = "/equipment/requests"
LIVE_CHECK_NOTE = "live-check SCRUM-45"  # marks the lines TC-EQR-002 writes, so only those are deleted


def delete_live_check_lines(run_id: str) -> None:
    lines = mine_or_stale("technical_requirements", f"{LIVE_CHECK_NOTE} {run_id}%", f"{LIVE_CHECK_NOTE}%")
    db_query(f"delete from public.equipment_requests where event_id = '{PLANNING_FIXTURE}' and {lines}")


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
        # 15 is above the 14 that exist: EQ-R1 allows it.
        response = submit_equipment(ctx, coordinator, PLANNING_FIXTURE, [
            {"equipment_id": PROJECTOR_ID, "quantity": 15, "technical_requirements": note},
        ])
        expect_status(response, 201)
        [line] = response.json()["lines"]
        expect(line["status"] == "pending", f"status is {line['status']!r}")
        expect(line["quantity"] == 15, f"quantity is {line['quantity']}")

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
        expect(stored == [{"status": "pending", "quantity": 15}], f"stored row is {stored}")
    finally:
        delete_live_check_lines(ctx.run_id)


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


# --- SCRUM-24 equipment reservation -------------------------------------------
# Each check uses its own "live-check equipment" item on throwaway 2031 events,
# so seeded stock is never reserved. The items (and, by cascade, their
# reservations) are deleted with the throwaway events.

THROWAWAY_EQUIPMENT_PREFIX = "live-check equipment "


def throwaway_equipment(ctx: Context, case: str, quantity: int) -> str:
    rows = db_query(
        "insert into public.equipment (name, equipment_type, total_quantity, status) values "
        f"('{THROWAWAY_EQUIPMENT_PREFIX}{ctx.run_id} {case}', 'live-check', {quantity}, 'active') returning id"
    )
    return rows[0]["id"]


def throwaway_line(event_id: str, equipment_id: str, quantity: int) -> str:
    rows = db_query(
        "insert into public.equipment_requests (event_id, equipment_id, submission_id, quantity, requested_by) values "
        f"('{event_id}', '{equipment_id}', gen_random_uuid(), {quantity}, '{COORDINATOR_ID}') returning id"
    )
    return rows[0]["id"]


def reserve(ctx: Context, session: Session, line_id: str) -> httpx.Response:
    return ctx.client.post(f"{ctx.api}{EQUIPMENT_REQUESTS}/{line_id}/reserve", headers=session.headers)


@check("TC-EQR-042", "23-R/D58: duplicate availability demand is rejected, including UUID case variants")
def check_duplicate_availability_demand(ctx: Context) -> None:
    session = ctx.shared("tech_support")
    for same_id in (PROJECTOR_ID, PROJECTOR_ID.upper()):
        response = ctx.client.post(f"{ctx.api}/equipment/availability/check", headers=session.headers, json={
            "start_at": "2034-01-01T09:00:00+08:00", "end_at": "2034-01-01T12:00:00+08:00",
            "items": [{"equipment_id": PROJECTOR_ID, "quantity_needed": 5},
                      {"equipment_id": same_id, "quantity_needed": 5}],
        })
        expect_status(response, 422)
        expect("combine" in response.text.lower(), "duplicate demand has no combine-quantities guidance")


def require_equipment_location_migration() -> None:
    [row] = db_query(
        "select exists (select 1 from information_schema.columns where table_schema = 'public' "
        "and table_name = 'equipment' and column_name = 'storage_location') as present"
    )
    if not row["present"]:
        raise CheckBlocked("23-R migration is pending: equipment.storage_location is missing.")


@check("TC-EQR-039", "23-R: usable quantity, shortage, event times and reference-only location", needs_db=True)
def check_reopened_equipment_availability(ctx: Context) -> None:
    require_equipment_location_migration()
    item = throwaway_equipment(ctx, "039", 7)
    try:
        db_query(
            "insert into public.equipment_unavailability (equipment_id, quantity, start_at, end_at, reason) values "
            f"('{item}', 2, '2034-01-01 09:00+08', '2034-01-01 12:00+08', 'Faulty units'), "
            f"('{item}', 5, '2034-01-01 07:00+08', '2034-01-01 09:00+08', 'Maintenance before event'), "
            f"('{item}', 5, '2034-01-01 12:00+08', '2034-01-01 14:00+08', 'Maintenance after event')"
        )
        session = ctx.shared("tech_support")
        for location in ("Store A", "Different venue store", None):
            value = "null" if location is None else f"'{location}'"
            db_query(f"update public.equipment set storage_location = {value} where id = '{item}'")
            for needed, missing in ((6, 1), (5, 0), (3, 0)):
                response = ctx.client.post(f"{ctx.api}/equipment/availability/check", headers=session.headers, json={
                    "start_at": "2034-01-01T09:00:00+08:00", "end_at": "2034-01-01T12:00:00+08:00",
                    "items": [{"equipment_id": item, "quantity_needed": needed}],
                })
                expect_status(response, 200)
                [result] = response.json()["items"]
                expect(result["storage_location"] == location, "storage location did not round-trip")
                expect((result["quantity_needed"], result["quantity_available"], result["quantity_missing"]) ==
                       (needed, 5, missing), f"incorrect quantities: {result}")
                expect(result["sufficient"] is (missing == 0), "sufficient status disagrees with shortage")
                expect(response.json()["sufficient"] is (missing == 0), "overall status disagrees")
        db_query(f"update public.equipment set status = 'retired' where id = '{item}'")
        response = ctx.client.post(f"{ctx.api}/equipment/availability/check", headers=session.headers, json={
            "start_at": "2034-01-01T09:00:00+08:00", "end_at": "2034-01-01T12:00:00+08:00",
            "items": [{"equipment_id": item, "quantity_needed": 6}],
        })
        expect_status(response, 200)
        [result] = response.json()["items"]
        expect((result["quantity_available"], result["quantity_missing"], result["sufficient"]) ==
               (0, 6, False), f"retired stock still usable: {result}")
        for params in ({"start_at": "2034-01-01T09:00:00+08:00", "end_at": "2034-01-01T12:00:00+08:00"}, {}):
            inventory = ctx.client.get(f"{ctx.api}/equipment/inventory", headers=session.headers, params=params)
            expect_status(inventory, 200)
            retired = next(row for row in inventory.json()["items"] if row["equipment_id"] == item)
            expect((retired["total_quantity"], retired["net_available"]) == (7, 0),
                   f"inventory still offers retired stock: {retired}")
        for role in ("event_organiser", "event_coordinator", "venue_staff", "attendee"):
            response = ctx.client.post(f"{ctx.api}/equipment/availability/check", headers=ctx.shared(role).headers, json={
                "start_at": "2034-01-01T09:00:00+08:00", "end_at": "2034-01-01T12:00:00+08:00",
                "items": [{"equipment_id": item, "quantity_needed": 1}],
            })
            expect_status(response, 403)
    finally:
        db_query(f"delete from public.equipment where id = '{item}'")


@check("TC-EQR-017", "Tech support reserve a pending line; it is linked, Reserved, and the coordinator is told", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "EQR017", "2031-08-01 09:00+08", "2031-08-01 12:00+08")
    item = throwaway_equipment(ctx, "017", 5)
    line_id = throwaway_line(event_id, item, 3)

    response = reserve(ctx, ctx.shared("tech_support"), line_id)
    expect_status(response, 200)
    expect(response.json() == {"line_id": line_id, "status": "reserved", "free_quantity": 2}, response.text)
    [row] = db_query(
        "select count(*)::int as n from public.equipment_reservations "
        f"where request_line_id = '{line_id}' and event_id = '{event_id}' and status = 'confirmed' "
        "and start_at = '2031-08-01 09:00+08' and end_at = '2031-08-01 12:00+08'"
    )
    expect(row["n"] == 1, "the reservation is not linked to its line, event and window")
    [notice] = db_query(
        "select count(*)::int as n from public.notifications "
        f"where event_id = '{event_id}' and recipient_id = '{COORDINATOR_ID}' and type = 'equipment_reserved'"
    )
    expect(notice["n"] == 1, f"the coordinator got {notice['n']} reserve notices")
    lines = ctx.client.get(f"{ctx.api}{EQUIPMENT_REQUESTS}/event/{event_id}", headers=ctx.shared("event_coordinator").headers)
    expect_status(lines, 200)
    expect(lines.json()["lines"][0]["status"] == "reserved", "the coordinator does not see Reserved")
    expect(lines.json()["technical_status"] == "pending", "reserved but unticked is not Pending")


@check("TC-EQR-018", "An overlapping event is refused with how many are free; another time is unaffected", needs_db=True)
def _(ctx: Context) -> None:
    first = throwaway_event(ctx, "EQR018-a", "2031-08-02 09:00+08", "2031-08-02 12:00+08")
    overlapping = throwaway_event(ctx, "EQR018-b", "2031-08-02 11:00+08", "2031-08-02 13:00+08")
    back_to_back = throwaway_event(ctx, "EQR018-c", "2031-08-02 12:00+08", "2031-08-02 14:00+08")
    item = throwaway_equipment(ctx, "018", 4)
    tech = ctx.shared("tech_support")

    expect_status(reserve(ctx, tech, throwaway_line(first, item, 3)), 200)
    refused_line = throwaway_line(overlapping, item, 2)
    refused = reserve(ctx, tech, refused_line)
    expect_status(refused, 409)
    expect(refused.json() == {
        "detail": "Not enough available: 1 free for this event's time. The line stays Pending.", "free_quantity": 1,
    }, refused.text)
    [line] = db_query(f"select status::text as status from public.equipment_requests where id = '{refused_line}'")
    expect(line["status"] == "pending", f"the refused line is {line['status']}")
    expect_status(reserve(ctx, tech, throwaway_line(back_to_back, item, 4)), 200)


@check("TC-EQR-019", "Not available needs a reason; the coordinator sees it and the notes, the organiser can't", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "EQR019", "2031-08-03 09:00+08", "2031-08-03 12:00+08")
    line_id = throwaway_line(event_id, throwaway_equipment(ctx, "019", 2), 1)
    tech = ctx.shared("tech_support")
    url = f"{ctx.api}{EQUIPMENT_REQUESTS}/{line_id}"

    expect_status(ctx.client.post(f"{url}/not-available", headers=tech.headers, json={"reason": "  "}), 422)
    expect_status(ctx.client.put(f"{url}/notes", headers=tech.headers, json={"note": "live check note"}), 200)
    expect_status(ctx.client.post(f"{url}/not-available", headers=tech.headers, json={"reason": "Only 0 in stock"}), 200)
    body = ctx.client.get(f"{ctx.api}{EQUIPMENT_REQUESTS}/event/{event_id}", headers=ctx.shared("event_coordinator").headers).json()
    [line] = body["lines"]
    expect((line["status"], line["not_available_reason"], line["technical_notes"])
           == ("rejected", "Only 0 in stock", "live check note"), f"coordinator sees {line}")
    expect(body["technical_status"] == "issue", f"technical status is {body['technical_status']}")
    organiser = ctx.shared("event_organiser")
    expect_status(ctx.client.get(f"{ctx.api}{EQUIPMENT_REQUESTS}/event/{event_id}", headers=organiser.headers), 403)
    expect_status(ctx.client.get(f"{ctx.api}/equipment/events/{event_id}/technical", headers=organiser.headers), 403)


@check("TC-EQR-021", "Two tech staff reserving the last units at once: exactly one succeeds", needs_db=True)
def _(ctx: Context) -> None:
    from concurrent.futures import ThreadPoolExecutor

    left = throwaway_event(ctx, "EQR021-a", "2031-08-04 09:00+08", "2031-08-04 12:00+08")
    right = throwaway_event(ctx, "EQR021-b", "2031-08-04 10:00+08", "2031-08-04 13:00+08")
    item = throwaway_equipment(ctx, "021", 2)
    lines = [throwaway_line(left, item, 2), throwaway_line(right, item, 2)]
    sessions = [ctx.login("tech_support"), ctx.login("tech_support")]

    # Separate clients and sessions, so the two reserves really are in flight together.
    def fire(pair) -> int:
        line_id, session = pair
        with httpx.Client(timeout=30) as client:
            return client.post(f"{ctx.api}{EQUIPMENT_REQUESTS}/{line_id}/reserve", headers=session.headers).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(fire, zip(lines, sessions)))
    expect(codes == [200, 409], f"expected one 200 and one 409, got {codes}")
    [row] = db_query(
        "select coalesce(sum(quantity), 0)::int as held from public.equipment_reservations "
        f"where equipment_id = '{item}' and status = 'confirmed'"
    )
    expect(row["held"] == 2, f"{row['held']} units are reserved of 2")


@check("TC-EQR-022", "Every line Reserved plus the exit tick is Ready, with who ticked it; a new line clears it", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "EQR022", "2031-08-05 09:00+08", "2031-08-05 12:00+08")
    item = throwaway_equipment(ctx, "022", 3)
    tech = ctx.shared("tech_support")
    technical = f"{ctx.api}/equipment/events/{event_id}/technical"
    expect_status(reserve(ctx, tech, throwaway_line(event_id, item, 1)), 200)

    expect_status(ctx.client.put(f"{ctx.api}/equipment/events/{event_id}/exit-confirmation",
                                 headers=tech.headers, json={"confirmed": True}), 204)
    body = ctx.client.get(technical, headers=tech.headers).json()
    expect(body["technical_status"] == "ready", f"technical status is {body['technical_status']}")
    expect(body["exit_confirmation"] and body["exit_confirmation"]["confirmed_by_name"],
           f"no confirmer: {body['exit_confirmation']}")
    expect(any(e["action"] == "technical_status" and e["to_status"] == "ready" and e["actor_name"]
               for e in body["history"]), "the change to Ready is not in history with who made it")

    throwaway_line(event_id, item, 1)
    body = ctx.client.get(technical, headers=tech.headers).json()
    expect(body["exit_confirmation"] is None, "adding a line did not clear the exit tick")
    expect(body["technical_status"] == "pending", f"technical status is {body['technical_status']}")


@check("TC-EQR-026", "Only Technical Support reserve, mark, annotate and tick; every other role gets 403", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "EQR026", "2031-08-06 09:00+08", "2031-08-06 12:00+08")
    line_id = throwaway_line(event_id, throwaway_equipment(ctx, "026", 2), 1)
    calls = [
        ("POST", f"{EQUIPMENT_REQUESTS}/{line_id}/reserve", None),
        ("POST", f"{EQUIPMENT_REQUESTS}/{line_id}/not-available", {"reason": "x"}),
        ("PUT", f"{EQUIPMENT_REQUESTS}/{line_id}/notes", {"note": "x"}),
        ("PUT", f"/equipment/events/{event_id}/exit-confirmation", {"confirmed": True}),
        ("GET", f"/equipment/events/{event_id}/technical", None),
    ]
    roles = [r for r in ACCOUNTS if r != "tech_support"] + list(W7_STAFF_ACCOUNTS)
    for role in roles:
        session = ctx.shared(role)
        for method, path, body in calls:
            response = ctx.client.request(method, f"{ctx.api}{path}", headers=session.headers, json=body)
            expect(response.status_code == 403, f"{role} {method} {path} answered {response.status_code}")
    [line] = db_query(f"select status::text as status from public.equipment_requests where id = '{line_id}'")
    expect(line["status"] == "pending", f"a refused role changed the line to {line['status']}")


# --- SCRUM-44 modify or remove equipment requirements ---------------------------

def change_line(ctx: Context, line_id: str, body: dict, session: Session | None = None) -> httpx.Response:
    session = session or ctx.shared("event_coordinator")
    return ctx.client.patch(f"{ctx.api}{EQUIPMENT_REQUESTS}/{line_id}", headers=session.headers, json=body)


def remove_line(ctx: Context, line_id: str, expected_status: str, session: Session | None = None) -> httpx.Response:
    session = session or ctx.shared("event_coordinator")
    return ctx.client.delete(f"{ctx.api}{EQUIPMENT_REQUESTS}/{line_id}", headers=session.headers,
                             params={"expected_status": expected_status})


def tech_support_notices(event_id: str, notice_type: str) -> int:
    [row] = db_query(
        "select count(*)::int as n from public.notifications n "
        "join public.user_roles ur on ur.profile_id = n.recipient_id and ur.role = 'tech_support' "
        f"where n.event_id = '{event_id}' and n.type = '{notice_type}'"
    )
    return row["n"]


@check("TC-EQR-044", "The coordinator changes a pending line; it stays Pending and the history shows before and after",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "EQR044", "2031-09-01 09:00+08", "2031-09-01 12:00+08")
    item = throwaway_equipment(ctx, "044", 5)
    line_id = throwaway_line(event_id, item, 1)

    response = change_line(ctx, line_id, {"equipment_id": item, "quantity": 3,
                                          "technical_requirements": " HDMI ", "expected_status": "pending"})
    expect_status(response, 200)
    expect(response.json()["status"] == "pending", response.text)
    [line] = db_query(f"select quantity, technical_requirements from public.equipment_requests where id = '{line_id}'")
    expect((line["quantity"], line["technical_requirements"]) == (3, "HDMI"), f"the line is {line}")
    expect(tech_support_notices(event_id, "equipment_line_changed") == 0, "tech support were told of a pending edit")
    history = ctx.client.get(f"{ctx.api}{EQUIPMENT_REQUESTS}/event/{event_id}/history",
                             headers=ctx.shared("event_coordinator").headers)
    expect_status(history, 200)
    [entry] = [e for e in history.json()["history"] if e["action"] == "edited"]
    expect("Quantity: 1 → 3" in entry["detail"] and entry["actor_name"], f"the history entry is {entry}")
    expect_status(change_line(ctx, line_id, {"equipment_id": item, "quantity": 0, "expected_status": "pending"}), 422)


@check("TC-EQR-045", "Changing a reserved line sends it for re-review, keeps its reservation and tells tech support",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "EQR045", "2031-09-02 09:00+08", "2031-09-02 12:00+08")
    item = throwaway_equipment(ctx, "045", 5)
    line_id = throwaway_line(event_id, item, 2)
    expect_status(reserve(ctx, ctx.shared("tech_support"), line_id), 200)

    response = change_line(ctx, line_id, {"equipment_id": item, "quantity": 4, "expected_status": "reserved"})
    expect_status(response, 200)
    expect(response.json()["status"] == "re_review", response.text)
    [held] = db_query("select quantity from public.equipment_reservations "
                      f"where request_line_id = '{line_id}' and status = 'confirmed'")
    expect(held["quantity"] == 2, f"the reservation now holds {held['quantity']}, not the old 2")
    expect(tech_support_notices(event_id, "equipment_line_changed") >= 1, "tech support were not told")
    expect_status(reserve(ctx, ctx.shared("tech_support"), line_id), 200)
    [held] = db_query("select quantity from public.equipment_reservations "
                      f"where request_line_id = '{line_id}' and status = 'confirmed'")
    expect(held["quantity"] == 4, f"re-reserving holds {held['quantity']}, not 4")


@check("TC-EQR-048", "Removing a reserved line frees its units, tells tech support and stays in the history",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "EQR048-a", "2031-09-03 09:00+08", "2031-09-03 12:00+08")
    other = throwaway_event(ctx, "EQR048-b", "2031-09-03 10:00+08", "2031-09-03 13:00+08")
    item = throwaway_equipment(ctx, "048", 3)
    tech = ctx.shared("tech_support")
    line_id = throwaway_line(event_id, item, 3)
    expect_status(reserve(ctx, tech, line_id), 200)
    expect_status(reserve(ctx, tech, throwaway_line(other, item, 3)), 409)

    response = remove_line(ctx, line_id, "reserved")
    expect_status(response, 200)
    expect(response.json()["status"] == "released", response.text)
    expect_status(reserve(ctx, tech, throwaway_line(other, item, 3)), 200)
    expect(tech_support_notices(event_id, "equipment_line_removed") >= 1, "tech support were not told")
    expect_status(reserve(ctx, tech, line_id), 409)
    body = ctx.client.get(f"{ctx.api}{EQUIPMENT_REQUESTS}/event/{event_id}/history",
                          headers=ctx.shared("event_coordinator").headers).json()
    expect(any(e["action"] == "removed" and e["line_label"] for e in body["history"]),
           "the removed line is not named in the history")
    lines = ctx.client.get(f"{ctx.api}{EQUIPMENT_REQUESTS}/event/{event_id}",
                           headers=ctx.shared("event_coordinator").headers).json()
    expect(lines["technical_status"] == "not_required", f"technical status is {lines['technical_status']}")


@check("TC-EQR-049", "Outside Planning a line can't be changed or removed", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "EQR049", "2031-09-04 09:00+08", "2031-09-04 12:00+08", status="safety_review")
    item = throwaway_equipment(ctx, "049", 2)
    line_id = throwaway_line(event_id, item, 1)
    message = "Equipment can only be changed while the event is in Planning."

    for response in (change_line(ctx, line_id, {"equipment_id": item, "quantity": 2, "expected_status": "pending"}),
                     remove_line(ctx, line_id, "pending")):
        expect_status(response, 409)
        expect(response.json()["detail"] == message, response.text)


@check("TC-EQR-050", "A removal and a reservation of the same line at once: exactly one is saved", needs_db=True)
def _(ctx: Context) -> None:
    from concurrent.futures import ThreadPoolExecutor

    event_id = throwaway_event(ctx, "EQR050", "2031-09-05 09:00+08", "2031-09-05 12:00+08")
    line_id = throwaway_line(event_id, throwaway_equipment(ctx, "050", 2), 1)
    coordinator, tech = ctx.login("event_coordinator"), ctx.login("tech_support")

    def fire(kind: str) -> int:
        with httpx.Client(timeout=30) as client:
            if kind == "remove":
                return client.delete(f"{ctx.api}{EQUIPMENT_REQUESTS}/{line_id}", headers=coordinator.headers,
                                     params={"expected_status": "pending"}).status_code
            return client.post(f"{ctx.api}{EQUIPMENT_REQUESTS}/{line_id}/reserve", headers=tech.headers).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(fire, ["remove", "reserve"]))
    expect(codes == [200, 409], f"expected one 200 and one 409, got {codes}")
    [line] = db_query(f"select status::text as status from public.equipment_requests where id = '{line_id}'")
    [held] = db_query("select count(*)::int as n from public.equipment_reservations "
                      f"where request_line_id = '{line_id}' and status = 'confirmed'")
    expect((line["status"], held["n"]) in {("released", 0), ("reserved", 1)},
           f"the line is {line['status']} holding {held['n']} reservations")


@check("TC-EQR-051", "Only the assigned coordinator, acting as coordinator, changes or removes a line", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "EQR051", "2031-09-06 09:00+08", "2031-09-06 12:00+08")
    unassigned = throwaway_event(ctx, "EQR051-u", "2031-09-06 09:00+08", "2031-09-06 12:00+08", assigned=False)
    item = throwaway_equipment(ctx, "051", 2)
    line_id = throwaway_line(event_id, item, 1)
    body = {"equipment_id": item, "quantity": 2, "expected_status": "pending"}

    roles = [r for r in ACCOUNTS if r != "event_coordinator"] + list(W7_STAFF_ACCOUNTS)
    for role in roles:
        session = ctx.shared(role)
        for response in (change_line(ctx, line_id, body, session), remove_line(ctx, line_id, "pending", session)):
            expect(response.status_code == 403, f"{role} answered {response.status_code}")
    other_line = throwaway_line(unassigned, item, 1)
    expect_status(change_line(ctx, other_line, body), 403)
    expect_status(remove_line(ctx, other_line, "pending"), 403)
    [line] = db_query(f"select status::text as status, quantity from public.equipment_requests where id = '{line_id}'")
    expect((line["status"], line["quantity"]) == ("pending", 1), f"a refused role changed the line: {line}")


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
    expect(stored["phone_number"] == "+6591234567", "phone number not stored in normalized form")
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


@check("TC-AUTH-043", "Sign-up refuses internal roles")
def _(ctx: Context) -> None:
    for role in ("event_coordinator", "event_coordinator_lead", "venue_staff", "tech_support", "safety_officer"):
        expect_field_error(ctx.signup(email=ctx.throwaway_email("043"), role=role), "role")


@check("TC-AUTH-050", "Attendee signup stores only the attendee role and allows immediate login", creates_accounts=True)
def _(ctx: Context) -> None:
    email = ctx.throwaway_email("050")
    response = ctx.signup(
        role="attendee",
        full_name="Avery Attendee",
        email=email,
        organisation_name=None,
        phone_number=None,
    )
    expect_status(response, 201)
    body = response.json()
    expect(body["role"] == "attendee", f"response role is {body['role']!r}")
    expect(body["roles"] == ["attendee"], f"response roles are {body['roles']}")

    stored = stored_account(email)
    expect(stored["role"] == "attendee", f"profiles.role is {stored['role']!r}")
    expect(stored["roles"] == "attendee", f"user_roles holds {stored['roles']!r}")
    expect(stored["organisation_name"] is None, "attendee organisation_name is not NULL")
    expect(stored["phone_number"] is None, "attendee phone_number is not NULL")
    expect(stored["confirmed"] is True, "email_confirmed_at is not set (ADR-0003)")

    session = ctx.login("attendee", email=email, password=THROWAWAY_PASSWORD)
    expect(session.body["profile"]["role"] == "attendee", "logged in with the wrong role")


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
    ("safety-reject", {"reason": "Live check", "booking_id": MISSING_EVENT}),
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
                f"{ctx.api}/events/{MISSING_EVENT}/{action}", headers=headers, json={field_name: text, **({"booking_id": MISSING_EVENT} if action == "safety-reject" else {})},
            ), 422)


    expect_status(ctx.client.post(
        f"{ctx.api}/events/{MISSING_EVENT}/safety-reject", headers=headers,
        json={"reason": "Legacy arrays", "booking_ids": [MISSING_EVENT]},
    ), 422)


@check("TC-SDEC-022", "Mark as revised is refused for every non-coordinator active role")
def _(ctx: Context) -> None:
    for role in (*ACCOUNTS, *W7_STAFF_ACCOUNTS):
        if role != "event_coordinator":
            expect_status(ctx.client.post(
                f"{ctx.api}/venue-bookings/{MISSING_EVENT}/mark-revised",
                headers=ctx.shared(role).headers, json={"note": "live check"},
            ), 403)


@check("TC-SDEC-023", "Mark as revised on a missing booking answers 404")
def _(ctx: Context) -> None:
    expect_status(ctx.client.post(
        f"{ctx.api}/venue-bookings/{MISSING_EVENT}/mark-revised",
        headers=ctx.shared("event_coordinator").headers, json={"note": "live check"},
    ), 404)


# D52-D54: disposable success flows, only after the follow-up migration is deployed.
def safety_rejection_followup_fixture(ctx: Context, case: str) -> tuple[str, str, str]:
    event_id = throwaway_event(ctx, case, "2031-08-20 10:00+08", "2031-08-20 12:00+08")
    venue_id = throwaway_venue(ctx, case)
    [booking] = db_query(
        "insert into public.venue_bookings (event_id, venue_id, occupied_period, status) values "
        f"('{event_id}', '{venue_id}', tstzrange('2031-08-20 10:00+08', '2031-08-20 12:00+08', '[)'), 'approved') returning id"
    )
    db_query(f"update public.events set status='safety_review' where id='{event_id}'")
    return event_id, booking["id"], venue_id


@check("TC-SDEC-031", "Reject then revise with a note; named history shows the response", needs_db=True)
def _(ctx: Context) -> None:
    event_id, booking_id, venue_id = safety_rejection_followup_fixture(ctx, "SDEC-031")
    officer = ctx.shared("safety_officer")
    coordinator = ctx.shared("event_coordinator")
    expect_status(ctx.client.post(
        f"{ctx.api}/events/{event_id}/safety-reject", headers=officer.headers,
        json={"booking_id": booking_id, "reason": "live check exits"},
    ), 200)
    for note, code in (("   ", 422), ("live check revised", 200)):
        expect_status(ctx.client.post(
            f"{ctx.api}/venue-bookings/{booking_id}/mark-revised", headers=coordinator.headers,
            json={"note": note},
        ), code)
    response = ctx.client.get(f"{ctx.api}/events/{event_id}/safety-decisions", headers=officer.headers)
    expect_status(response, 200)
    rejection = next(row for row in response.json() if row["decision"] == "arrangement_rejected")
    [venue] = db_query(f"select name from public.venues where id='{venue_id}'")
    expect(rejection["rejected_venues"][0]["venue_name"] == venue["name"], "history names the rejected venue")
    expect(rejection["revision"]["note"] == "live check revised", "history carries the coordinator response")


@check("TC-SDEC-032", "Replace a Safety-rejected venue; approval releases it", needs_db=True)
def _(ctx: Context) -> None:
    event_id, booking_id, _ = safety_rejection_followup_fixture(ctx, "SDEC-032")
    venue_id = throwaway_venue(ctx, "SDEC-032 replacement")
    officer = ctx.shared("safety_officer")
    coordinator = ctx.shared("event_coordinator")
    staff = ctx.shared("venue_staff")
    expect_status(ctx.client.post(
        f"{ctx.api}/events/{event_id}/safety-reject", headers=officer.headers,
        json={"booking_id": booking_id, "reason": "live check exits"},
    ), 200)
    requested = ctx.client.post(f"{ctx.api}/venue-bookings", headers=coordinator.headers,
        json={"event_id": event_id, "venue_id": venue_id, "replaces_booking_id": booking_id})
    expect_status(requested, 201)
    replacement_id = requested.json()["id"]
    refused = ctx.client.post(f"{ctx.api}/venue-bookings/{booking_id}/mark-revised", headers=coordinator.headers,
                             json={"note": "live check revised"})
    expect_status(refused, 409)
    expect(refused.json()["detail"] == "A replacement venue has been requested for this booking.", "pending replacement refusal")
    expect_status(approve_booking(ctx, staff, replacement_id), 200)
    rows = db_query(f"select id, status, flag from public.venue_bookings where id in ('{booking_id}', '{replacement_id}')")
    stored = {row["id"]: row for row in rows}
    expect(stored[booking_id]["status"] == "released", "the rejected booking is released")
    expect(stored[replacement_id]["status"] == "approved" and stored[replacement_id]["flag"] is None,
           "the replacement is approved and unflagged")


# --- Venue suitability checking (SCRUM-18) ---------------------------------------

def suitability_search(ctx: Context, session: Session, **params):
    return ctx.client.get(f"{ctx.api}/venues", headers=session.headers,
                          params={"include_excluded": "true", **params})


def suitability_of(response: httpx.Response, venue_id: str) -> dict:
    expect_status(response, 200)
    found = [r for r in response.json()["results"] if r["venue"]["id"] == venue_id]
    expect(len(found) == 1, f"venue {venue_id} appears {len(found)} times")
    return found[0]["suitability"]


@check("TC-SUIT-001", "A space is judged on its own attendance, not the event's (AC1, AC2, AC11)", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "SUIT-001", "2031-07-10 09:00+08", "2031-07-10 12:00+08")
    db_query(f"update public.events set expected_attendance = 500 where id = '{event_id}'")
    fits = throwaway_space(event_id, "Breakout", pax=60, layout="classroom")
    too_big = throwaway_space(event_id, "Workshop", pax=61, layout="classroom")
    coordinator = ctx.shared("event_coordinator")

    passing = suitability_of(suitability_search(ctx, coordinator, space_id=fits), INNOVATION_LAB)
    expect("capacity" not in {r["code"] for r in passing["reasons"]},
           f"60 people in a 60-seat classroom failed: {passing['reasons']}")
    failing = suitability_of(suitability_search(ctx, coordinator, space_id=too_big), INNOVATION_LAB)
    expect(failing["verdict"] == "unsuitable", f"verdict {failing['verdict']}")
    expect("Capacity 60 is below the expected attendance of 61." in [r["message"] for r in failing["reasons"]],
           f"reasons {failing['reasons']}")


@check("TC-SUIT-002", "A missing facility and an inactive venue are Unsuitable and named (AC3, AC4, AC7)", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "SUIT-002", "2031-07-11 09:00+08", "2031-07-11 12:00+08")
    db_query(f"update public.events set expected_attendance = 10, facilities_required = '{{projector}}' "
             f"where id = '{event_id}'")
    bare = throwaway_venue(ctx, "SUIT-002 bare")
    closed = throwaway_venue(ctx, "SUIT-002 closed")
    db_query(f"update public.venues set is_active = false, inactive_reason = 'permanently_closed' where id = '{closed}'")
    coordinator = ctx.shared("event_coordinator")

    response = suitability_search(ctx, coordinator, event_id=event_id)
    missing = suitability_of(response, bare)
    expect(missing["verdict"] == "unsuitable", f"verdict {missing['verdict']}")
    expect("Missing facilities this event needs: projector." in [r["message"] for r in missing["reasons"]],
           f"reasons {missing['reasons']}")
    inactive = suitability_of(response, closed)
    expect(inactive["verdict"] == "unsuitable" and inactive["reasons"][0]["code"] == "inactive",
           f"inactive venue reads {inactive}")


@check("TC-SUIT-003", "Only the assigned coordinator, acting as coordinator, can run the check (AC10)", needs_db=True)
def _(ctx: Context) -> None:
    mine = throwaway_event(ctx, "SUIT-003 mine", "2031-07-12 09:00+08", "2031-07-12 12:00+08")
    unassigned = throwaway_event(ctx, "SUIT-003 unassigned", "2031-07-12 09:00+08", "2031-07-12 12:00+08",
                                 assigned=False)
    space = throwaway_space(mine, "Room", pax=10)

    for role in ("venue_staff", "event_organiser", "tech_support", "attendee"):
        for params in ({"event_id": mine}, {"space_id": space}):
            expect_status(suitability_search(ctx, ctx.shared(role), **params), 403)
    coordinator = ctx.shared("event_coordinator")
    expect_status(suitability_search(ctx, coordinator, event_id=unassigned), 403)
    expect_status(suitability_search(ctx, coordinator, event_id=mine), 200)
    expect_status(ctx.client.get(f"{ctx.api}/venues", headers=ctx.shared("venue_staff").headers), 200)


@check("TC-SUIT-004", "Availability is reported separately from suitability (AC8)", needs_db=True)
def _(ctx: Context) -> None:
    holder = throwaway_event(ctx, "SUIT-004 holder", "2031-07-13 09:00+08", "2031-07-13 12:00+08")
    expect_status(ctx.client.post(f"{ctx.api}{BOOKINGS}", headers=ctx.shared("event_coordinator").headers,
                                  json={"event_id": holder, "venue_id": HERITAGE_HALL}), 201)
    wanting = throwaway_event(ctx, "SUIT-004 wanting", "2031-07-13 09:00+08", "2031-07-13 12:00+08")
    db_query(f"update public.events set expected_attendance = 10 where id = '{wanting}'")

    response = suitability_search(ctx, ctx.shared("event_coordinator"), event_id=wanting,
                                  starts_at="2031-07-13T09:00:00+08:00", ends_at="2031-07-13T12:00:00+08:00")
    expect_status(response, 200)
    hall = next(r for r in response.json()["results"] if r["venue"]["id"] == HERITAGE_HALL)
    expect(hall["availability"] == "unavailable", f"availability {hall['availability']}")
    expect(hall["suitability"]["verdict"] in ("suitable", "suitable_with_warnings"),
           f"a held venue read {hall['suitability']['verdict']}")


@check("TC-SUIT-010", "A request for an Unsuitable venue is refused and leaves no hold (BR-R3)", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "SUIT-007", "2031-07-14 09:00+08", "2031-07-14 12:00+08")
    db_query(f"update public.events set expected_attendance = 10, facilities_required = '{{projector}}' "
             f"where id = '{event_id}'")
    bare = throwaway_venue(ctx, "SUIT-007 bare")

    for body in ({}, {"acknowledge_warnings": True}):  # acknowledging never excuses a hard failure
        response = ctx.client.post(f"{ctx.api}{BOOKINGS}", headers=ctx.shared("event_coordinator").headers,
                                   json={"event_id": event_id, "venue_id": bare, **body})
        expect_status(response, 409)
        expect_detail(response, "This venue is unsuitable for this event: Missing facilities this event needs: projector.")
    expect(not db_query(f"select 1 from public.venue_bookings where event_id = '{event_id}'"),
           "a refused request left a booking behind")


@check("TC-SUIT-011", "A venue with warnings is held only once the coordinator acknowledges them (BR-R3)",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "SUIT-008", "2031-07-15 10:00+08", "2031-07-15 12:00+08")
    db_query(f"update public.events set expected_attendance = 10, layout_preference = 'banquet' where id = '{event_id}'")
    venue = throwaway_venue(ctx, "SUIT-008 theatre only")  # no banquet layout: a warning, not a failure
    coordinator = ctx.shared("event_coordinator")

    refused = ctx.client.post(f"{ctx.api}{BOOKINGS}", headers=coordinator.headers,
                              json={"event_id": event_id, "venue_id": venue})
    expect_status(refused, 409)
    expect_detail(refused, "This venue is suitable with warnings: The banquet layout this event needs is not supported. "
                           "Acknowledge the warnings to request it.")
    expect(not db_query(f"select 1 from public.venue_bookings where event_id = '{event_id}'"),
           "an unacknowledged request left a booking behind")

    held = ctx.client.post(f"{ctx.api}{BOOKINGS}", headers=coordinator.headers,
                           json={"event_id": event_id, "venue_id": venue, "acknowledge_warnings": True})
    expect_status(held, 201)
    expect(len(db_query(f"select 1 from public.venue_bookings where event_id = '{event_id}' and status = 'held'")) == 1,
           "the acknowledged request did not hold the venue")


@check("TC-SUIT-012", "A suitable venue needs no acknowledgement (BR-R3)", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "SUIT-010", "2031-07-16 10:00+08", "2031-07-16 12:00+08")
    db_query(f"update public.events set expected_attendance = 10, layout_preference = 'theatre' where id = '{event_id}'")
    venue = throwaway_venue(ctx, "SUIT-010 suits")

    response = ctx.client.post(f"{ctx.api}{BOOKINGS}", headers=ctx.shared("event_coordinator").headers,
                               json={"event_id": event_id, "venue_id": venue})
    expect_status(response, 201)


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
        if not _matches_keyword(keyword, f"{item.case_id} {item.title}"):
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
        encoding="utf-8",
    )


# --- SCRUM-113: the notification bell --------------------------------------------
# Needs migration 20261021100000 applied. The notices are made for throwaway
# events ("live-check ..."), so deleting those events at the end of the run
# deletes them (notifications cascade); no seeded notification is changed.
NOTIFICATIONS = "/notifications"


def add_notice(event_id: str, recipient_id: str, notice_type: str, message: str) -> str:
    [row] = db_query(
        f"select public.add_notification('{recipient_id}', '{event_id}', '{notice_type}', '{message}') as id"
    )
    expect(row["id"], f"no {notice_type} notice was made for {recipient_id}")
    return row["id"]


def bell_count(ctx: Context, session: Session) -> int:
    response = ctx.client.get(f"{ctx.api}{NOTIFICATIONS}/unread-count", headers=session.headers)
    expect_status(response, 200)
    return response.json()["count"]


def bell_page(ctx: Context, session: Session, query: str = "limit=100") -> dict:
    response = ctx.client.get(f"{ctx.api}{NOTIFICATIONS}?{query}", headers=session.headers)
    expect_status(response, 200)
    return response.json()


@check("TC-NOTIF-001", "The bell endpoints need a signed-in user")
def _(ctx: Context) -> None:
    for method, path in (("GET", "/unread-count"), ("GET", ""), ("POST", "/read-all"),
                         ("POST", "/e0000000-0000-4000-8000-000000000201/read")):
        response = ctx.client.request(method, f"{ctx.api}{NOTIFICATIONS}{path}")
        expect_status(response, 401)


@check("TC-NOTIF-002", "The bell counts and lists only what is addressed to the role the session is acting as", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "NOTIF002", "2031-09-01 09:00+08", "2031-09-01 12:00+08")
    session = ctx.login("event_coordinator")
    before = bell_count(ctx, session)
    for_coordinator = add_notice(event_id, COORDINATOR_ID, "event_assigned", "live-check notice for the coordinator")
    add_notice(event_id, COORDINATOR_ID, "venue_booking_requested", "live-check notice for venue staff")

    expect(bell_count(ctx, session) == before + 1, "the coordinator's count did not rise by exactly the one coordinator notice")
    newest = bell_page(ctx, session)["items"][0]
    expect(newest["message"] == "live-check notice for the coordinator", f"newest coordinator notice is {newest['message']!r}")
    expect(newest["link"] == f"/coordinator/events/{event_id}", f"the notice links to {newest['link']!r}")
    expect(newest["read"] is False, "a new notice reads as read")

    # The same account, now acting as venue staff: the other role's notice shows, this one does not (SCRUM-76).
    expect_status(ctx.client.post(f"{ctx.api}/auth/active-role", json={"role": "venue_staff"}, headers=session.headers), 200)
    messages = [item["message"] for item in bell_page(ctx, session)["items"]]
    expect("live-check notice for venue staff" in messages, "the venue staff notice is missing while acting as venue staff")
    expect("live-check notice for the coordinator" not in messages, "a coordinator notice leaked into the venue staff bell")
    response = ctx.client.post(f"{ctx.api}{NOTIFICATIONS}/{for_coordinator}/read", headers=session.headers)
    expect_status(response, 404)
    [row] = db_query(f"select read_at from public.notifications where id = '{for_coordinator}'")
    expect(row["read_at"] is None, "marking the other role's notice changed it")


@check("TC-NOTIF-003", "Paging, mark read and mark all read touch only the caller's own notices",
       creates_accounts=True, needs_db=True)
def _(ctx: Context) -> None:
    email = ctx.throwaway_email("NOTIF003")
    expect_status(ctx.signup(email=email), 201)
    session = ctx.login("event_organiser", email=email, password=THROWAWAY_PASSWORD)
    me = session.body["profile"]["id"]
    event_id = throwaway_event(ctx, "NOTIF003", "2031-09-02 09:00+08", "2031-09-02 12:00+08")
    # One statement, so the three share a created_at: the page boundary must not skip or repeat one.
    made = db_query(
        f"select public.add_notification('{me}', '{event_id}', 'event_coordinator_changed', "
        "'live-check notice ' || n) as id from generate_series(1, 3) as n"
    )
    ids = {row["id"] for row in made}
    expect(len(ids) == 3, f"expected 3 notices, made {len(ids)}")
    someone_elses = add_notice(event_id, VENUE_STAFF_ID, "venue_booking_requested", "live-check notice for someone else")

    first = bell_page(ctx, session, "limit=2")
    expect(len(first["items"]) == 2 and first["next_before"], f"first page was {first}")
    second = bell_page(ctx, session, f"limit=2&before={first['next_before']}")
    expect(len(second["items"]) == 1 and second["next_before"] is None, f"second page was {second}")
    seen = [item["id"] for item in first["items"] + second["items"]]
    expect(set(seen) == ids and len(seen) == 3, f"paging skipped or repeated a notice: {seen}")

    expect(bell_count(ctx, session) == 3, "the count is not 3")
    url = f"{ctx.api}{NOTIFICATIONS}/{seen[0]}/read"
    expect_status(ctx.client.post(url, headers=session.headers), 200)
    [row] = db_query(f"select read_at::text as at from public.notifications where id = '{seen[0]}'")
    expect(row["at"], "the notice was not marked read")
    expect_status(ctx.client.post(url, headers=session.headers), 200)
    [again] = db_query(f"select read_at::text as at from public.notifications where id = '{seen[0]}'")
    expect(again["at"] == row["at"], "marking a read notice again rewrote its time")
    expect(bell_count(ctx, session) == 2, "the count did not drop to 2")
    expect_status(ctx.client.post(url, headers=ctx.shared("event_coordinator").headers), 404)

    response = ctx.client.post(f"{ctx.api}{NOTIFICATIONS}/read-all", headers=session.headers)
    expect_status(response, 200)
    expect(response.json() == {"updated": 2}, f"read-all said {response.json()}")
    expect(bell_count(ctx, session) == 0, "the count is not 0 after read-all")
    [other] = db_query(f"select read_at from public.notifications where id = '{someone_elses}'")
    expect(other["read_at"] is None, "read-all marked someone else's notice")


# --- Story 84: the organiser requests cancellation ---------------------------------
# Every check works on its own throwaway events (deleted when the run ends, with their
# requests and notifications), never on seeded ones.

CANCEL_REASON = "live-check: keynote speaker withdrew"


def request_cancellation(ctx: Context, event_id: str, reason: str = CANCEL_REASON,
                         session: Session | None = None) -> httpx.Response:
    session = session or ctx.shared("event_organiser")
    return ctx.client.post(f"{ctx.api}/events/{event_id}/cancellation-request",
                           headers=session.headers, json={"reason": reason})


@check("TC-CANCEL-001", "The owner requests cancellation: one open request, the coordinator told, nothing released",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "84-001", "2031-10-02 09:00+08", "2031-10-02 12:00+08", status="confirmed")
    response = request_cancellation(ctx, event_id, f"  {CANCEL_REASON}  ")
    expect_status(response, 201)
    body = response.json()
    expect(body["status"] == "open" and body["kind"] == "cancellation" and body["reason"] == CANCEL_REASON,
           f"unexpected request: {body}")
    rows = db_query(f"select status, requested_by from public.event_change_requests where event_id = '{event_id}'")
    expect(rows == [{"status": "open", "requested_by": "a0000000-0000-4000-8000-000000000001"}], f"rows: {rows}")
    notices = db_query(
        "select recipient_id, recipient_role::text as role, message from public.notifications "
        f"where event_id = '{event_id}' and type = 'event_cancellation_requested'"
    )
    expect(len(notices) == 1 and notices[0]["recipient_id"] == COORDINATOR_ID and notices[0]["role"] == "event_coordinator"
           and CANCEL_REASON in notices[0]["message"], f"notices: {notices}")
    [event] = db_query(f"select status from public.events where id = '{event_id}'")
    expect(event["status"] == "confirmed", f"requesting moved the event to {event['status']}")


@check("TC-CANCEL-002", "A second request while one is open is refused (CR-R1)", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "84-002", "2031-10-03 09:00+08", "2031-10-03 12:00+08")
    expect_status(request_cancellation(ctx, event_id), 201)
    again = request_cancellation(ctx, event_id, "live-check: again")
    expect_status(again, 409)
    expect_detail(again, "A cancellation request is already open for this event.")
    [count] = db_query(f"select count(*) as n from public.event_change_requests where event_id = '{event_id}'")
    expect(int(count["n"]) == 1, f"{count['n']} requests stored")


@check("TC-CANCEL-003", "Draft, rejected, cancelled and completed events refuse a request and store nothing",
       needs_db=True)
def _(ctx: Context) -> None:
    for status in ("draft", "rejected", "cancelled", "completed"):
        event_id = throwaway_event(ctx, f"84-003-{status}", "2031-10-04 09:00+08", "2031-10-04 12:00+08", status=status)
        response = request_cancellation(ctx, event_id)
        expect_status(response, 409)
        expected = ("A draft can't be cancelled. Discard the draft instead." if status == "draft"
                    else f"Cancellation can't be requested for an event that is {status}.")
        expect_detail(response, expected)
        [count] = db_query(f"select count(*) as n from public.event_change_requests where event_id = '{event_id}'")
        expect(int(count["n"]) == 0, f"a request was stored on a {status} event")


@check("TC-EVENT-037", "Only the owning organiser can discard a draft; it is then gone (story 9 AC6, D81)",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "9-037", "2031-10-07 09:00+08", "2031-10-07 12:00+08", status="draft",
                               assigned=False)
    for role in ("event_coordinator", "venue_staff", "tech_support", "attendee"):
        session = ctx.shared(role)
        expect_status(ctx.client.delete(f"{ctx.api}/events/{event_id}", headers=session.headers), 403)
    owner = ctx.shared("event_organiser")
    expect_status(ctx.client.delete(f"{ctx.api}/events/{event_id}", headers=owner.headers), 204)
    expect_status(ctx.client.get(f"{ctx.api}/events/{event_id}", headers=owner.headers), 404)
    [count] = db_query(f"select count(*) as n from public.events where id = '{event_id}'")
    expect(int(count["n"]) == 0, "the discarded draft is still stored")


@check("TC-CANCEL-004", "Only the organiser role can request; a blank reason is refused", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "84-004", "2031-10-05 09:00+08", "2031-10-05 12:00+08")
    for role in ("event_coordinator", "venue_staff", "tech_support", "attendee"):
        expect_status(request_cancellation(ctx, event_id, session=ctx.shared(role)), 403)
    for role in ("safety_officer", "event_coordinator_lead"):
        expect_status(request_cancellation(ctx, event_id, session=ctx.shared(role)), 403)
    expect_status(request_cancellation(ctx, event_id, "   "), 422)
    expect_status(request_cancellation(ctx, UNKNOWN_EVENT), 404)
    [count] = db_query(f"select count(*) as n from public.event_change_requests where event_id = '{event_id}'")
    expect(int(count["n"]) == 0, "a refused request was stored")


@check("TC-CANCEL-005", "On an unassigned submitted event every Lead is told, in the Lead role", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "84-005", "2031-10-06 09:00+08", "2031-10-06 12:00+08",
                               status="submitted", assigned=False)
    expect_status(request_cancellation(ctx, event_id), 201)
    notices = db_query(
        "select recipient_id, recipient_role::text as role from public.notifications "
        f"where event_id = '{event_id}' and type = 'event_cancellation_requested'"
    )
    leads = db_query("select profile_id from public.user_roles where role = 'event_coordinator_lead'")
    expect(sorted(n["recipient_id"] for n in notices) == sorted(l["profile_id"] for l in leads)
           and all(n["role"] == "event_coordinator_lead" for n in notices) and notices,
           f"notices: {notices}, leads: {leads}")


@check("TC-CANCEL-006", "The event page, history and coordinator dashboard show the open request", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "84-006", "2031-10-07 09:00+08", "2031-10-07 12:00+08")
    expect_status(request_cancellation(ctx, event_id), 201)
    for role in ("event_organiser", "event_coordinator"):
        session = ctx.shared(role)
        detail = ctx.client.get(f"{ctx.api}/events/{event_id}", headers=session.headers)
        expect_status(detail, 200)
        request = detail.json()["open_cancellation_request"]
        expect(request and request["reason"] == CANCEL_REASON, f"{role} sees {request}")
        history = ctx.client.get(f"{ctx.api}/events/{event_id}/history", headers=session.headers).json()["entries"]
        entry = next((e for e in history if e["kind"] == "cancellation_requested"), None)
        expect(entry and entry["reason"] == CANCEL_REASON and entry["actor"], f"{role} history: {history}")
    items = coordinator_dashboard(ctx)["action_items"]
    expect(any(i["event_id"] == event_id and i["kind"] == "cancellation_request" for i in items),
           "no cancellation_request item on the coordinator dashboard")


@check("TC-CANCEL-013", "A preparation event accepts a request and stays in preparation", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "84-013", "2031-10-09 09:00+08", "2031-10-09 12:00+08", status="preparation")
    expect_status(request_cancellation(ctx, event_id), 201)
    rows = db_query(f"select status from public.event_change_requests where event_id = '{event_id}'")
    expect(rows == [{"status": "open"}], f"rows: {rows}")
    [event] = db_query(f"select status from public.events where id = '{event_id}'")
    expect(event["status"] == "preparation", f"requesting moved the event to {event['status']}")


# --- Story 32: the organiser requests changes -------------------------------------
# Throwaway events again, with a throwaway space where a check needs one.

CHANGE_REASON = "live-check: sponsor wants more seats"


def change_fixture(ctx: Context, case: str, day: str, status: str = "planning", assigned: bool = True) -> tuple[str, str]:
    """A throwaway event for 80 with one 80-pax theatre space. Returns (event, space)."""
    event_id = throwaway_event(ctx, case, f"{day} 10:00+08", f"{day} 12:00+08", status=status, assigned=assigned)
    db_query(f"update public.events set purpose = 'live-check', expected_attendance = 80 where id = '{event_id}'")
    [space] = db_query(
        "insert into public.event_space_requests (event_id, label, expected_pax, layout_preference) "
        f"values ('{event_id}', 'Main hall', 80, 'theatre') returning id"
    )
    return event_id, space["id"]


def event_version(event_id: str) -> int:
    [row] = db_query(f"select version from public.events where id = '{event_id}'")
    return int(row["version"])


def request_change(ctx: Context, event_id: str, *, event: dict | None = None, spaces: list | None = None,
                   reason: str = CHANGE_REASON, version: int | None = None,
                   session: Session | None = None) -> httpx.Response:
    session = session or ctx.shared("event_organiser")
    body = {"reason": reason, "version": event_version(event_id) if version is None else version,
            "event": event or {}, "spaces": spaces or []}
    return ctx.client.post(f"{ctx.api}/events/{event_id}/change-request", headers=session.headers, json=body)


def stored_requests(event_id: str, kind: str = "change") -> list[dict]:
    return db_query(f"select status, significant, changes, decision_reason from public.event_change_requests "
                    f"where event_id = '{event_id}' and kind = '{kind}'")


@check("TC-CHANGE-001", "The owner proposes event and space changes: recorded with before and after, coordinator told, event unchanged",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id, space_id = change_fixture(ctx, "32-001", "2031-11-03")
    before = event_version(event_id)
    response = request_change(ctx, event_id, event={"expected_attendance": 120, "description": "live-check"},
                              spaces=[{"id": space_id, "layout_preference": "banquet"}])
    expect_status(response, 201)
    body = response.json()
    expect(body["kind"] == "change" and body["status"] == "open" and body["significant"] is True, f"request: {body}")
    [row] = stored_requests(event_id)
    changes = row["changes"] if isinstance(row["changes"], dict) else json.loads(row["changes"])
    expect({"field": "expected_attendance", "before": 80, "after": 120} in changes["event"], f"changes: {changes}")
    expect(changes["spaces"] == [{"space_id": space_id, "label": "Main hall",
                                  "fields": [{"field": "layout_preference", "before": "theatre", "after": "banquet"}]}],
           f"space changes: {changes['spaces']}")
    notices = db_query("select recipient_id, recipient_role::text as role, message from public.notifications "
                       f"where event_id = '{event_id}' and type = 'event_change_requested'")
    expect(len(notices) == 1 and notices[0]["recipient_id"] == COORDINATOR_ID and notices[0]["role"] == "event_coordinator"
           and "expected attendance" in notices[0]["message"] and CHANGE_REASON in notices[0]["message"], f"notices: {notices}")
    [event] = db_query(f"select status, expected_attendance, version from public.events where id = '{event_id}'")
    expect(event["status"] == "planning" and event["expected_attendance"] == 80 and int(event["version"]) == before,
           f"requesting changed the event: {event}")


@check("TC-CHANGE-002", "An open cancellation blocks a change request; a cancellation request supersedes an open one (84 AC4)",
       needs_db=True)
def _(ctx: Context) -> None:
    blocked, _ = change_fixture(ctx, "32-002a", "2031-11-04")
    expect_status(request_cancellation(ctx, blocked), 201)
    response = request_change(ctx, blocked, event={"expected_attendance": 120})
    expect_status(response, 409)
    expect_detail(response, "A cancellation request is open for this event; ask your coordinator to reject it "
                            "before requesting changes.")
    expect(stored_requests(blocked) == [], "a blocked change request was stored")

    superseded, _ = change_fixture(ctx, "32-002b", "2031-11-05")
    expect_status(request_change(ctx, superseded, event={"expected_attendance": 120}), 201)
    expect_status(request_cancellation(ctx, superseded), 201)
    [row] = stored_requests(superseded)
    expect(row["status"] == "superseded", f"the change request is {row['status']}")
    history = ctx.client.get(f"{ctx.api}/events/{superseded}/history",
                             headers=ctx.shared("event_organiser").headers).json()["entries"]
    expect(any(e["kind"] == "change_request_closed" for e in history), f"history: {history}")


@check("TC-CHANGE-003", "Closed events refuse a change request and store nothing (AC4); draft and returned are pointed elsewhere",
       needs_db=True)
def _(ctx: Context) -> None:
    expected = {
        "rejected": "Changes can't be requested for an event that is rejected.",
        "cancelled": "Changes can't be requested for an event that is cancelled.",
        "completed": "Changes can't be requested for an event that is completed.",
        "draft": "A draft can be edited directly.",
        "returned": "Edit and resubmit the returned request instead.",
    }
    for status, detail in expected.items():
        event_id, _ = change_fixture(ctx, f"32-003-{status}", "2031-11-06", status=status)
        response = request_change(ctx, event_id, event={"expected_attendance": 120})
        expect_status(response, 409)
        expect_detail(response, detail)
        expect(stored_requests(event_id) == [], f"a request was stored on a {status} event")
        [event] = db_query(f"select expected_attendance from public.events where id = '{event_id}'")
        expect(event["expected_attendance"] == 80, f"the {status} event changed")


@check("TC-CHANGE-004", "Only the owner acting as organiser can ask; stale, empty and duplicate requests are refused",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id, space_id = change_fixture(ctx, "32-004", "2031-11-07")
    for role in ("event_coordinator", "event_coordinator_lead", "venue_staff", "tech_support", "safety_officer",
                 "attendee"):
        expect_status(request_change(ctx, event_id, event={"expected_attendance": 120}, session=ctx.shared(role)), 403)
    stale = request_change(ctx, event_id, event={"expected_attendance": 120}, version=event_version(event_id) + 5)
    expect_status(stale, 409)
    expect_detail(stale, "This event was updated by someone else. Reload.")
    empty = request_change(ctx, event_id, event={"expected_attendance": 80}, spaces=[{"id": space_id, "expected_pax": 80}])
    expect_status(empty, 422)
    expect_detail(empty, "Change at least one detail.")
    expect_status(request_change(ctx, event_id, event={"expected_attendance": 120}, reason="   "), 422)
    expect(stored_requests(event_id) == [], "a refused request was stored")
    expect_status(request_change(ctx, event_id, event={"expected_attendance": 120}), 201)
    again = request_change(ctx, event_id, event={"expected_attendance": 150})
    expect_status(again, 409)
    expect_detail(again, "A change request is already open for this event.")


@check("TC-CHANGE-005", "The event page, history and coordinator dashboard show the open change request", needs_db=True)
def _(ctx: Context) -> None:
    event_id, _ = change_fixture(ctx, "32-005", "2031-11-08")
    expect_status(request_change(ctx, event_id, event={"expected_attendance": 120}), 201)
    for role in ("event_organiser", "event_coordinator"):
        session = ctx.shared(role)
        detail = ctx.client.get(f"{ctx.api}/events/{event_id}", headers=session.headers)
        expect_status(detail, 200)
        request = detail.json()["open_change_request"]
        expect(request and request["reason"] == CHANGE_REASON and request["changes"]["event"], f"{role} sees {request}")
        history = ctx.client.get(f"{ctx.api}/events/{event_id}/history", headers=session.headers).json()["entries"]
        entry = next((e for e in history if e["kind"] == "change_requested"), None)
        expect(entry and entry["actor"] and entry["changes"], f"{role} history: {history}")
    items = coordinator_dashboard(ctx)["action_items"]
    expect(any(i["event_id"] == event_id and i["kind"] == "change_request" for i in items),
           "no change_request item on the coordinator dashboard")


@check("TC-CHANGE-006", "On an unassigned event every Lead is told; cancelling the event closes its open change request",
       needs_db=True)
def _(ctx: Context) -> None:
    unassigned, _ = change_fixture(ctx, "32-006a", "2031-11-09", status="submitted", assigned=False)
    expect_status(request_change(ctx, unassigned, event={"expected_attendance": 120}), 201)
    notices = db_query("select recipient_id, recipient_role::text as role from public.notifications "
                       f"where event_id = '{unassigned}' and type = 'event_change_requested'")
    leads = db_query("select profile_id from public.user_roles where role = 'event_coordinator_lead'")
    expect(notices and sorted(n["recipient_id"] for n in notices) == sorted(l["profile_id"] for l in leads)
           and all(n["role"] == "event_coordinator_lead" for n in notices), f"notices: {notices}, leads: {leads}")

    closing, _ = change_fixture(ctx, "32-006b", "2031-11-10")
    expect_status(request_change(ctx, closing, event={"expected_attendance": 120}), 201)
    expect_status(decide(ctx, closing, "cancel", "live-check: venue withdrawn"), 200)
    [row] = stored_requests(closing)
    expect(row["status"] == "superseded" and row["decision_reason"] == "Closed because the event was cancelled.",
           f"after the cancel the change request is {row}")


# --- Story 115: the coordinator decides, or cancels directly -----------------------
# Throwaway events again; their bookings, lines and registrations go with them.

ATTENDEE_ID = "a0000000-0000-4000-8000-000000000005"
DECISION_REASON = "live-check: no replacement venue"


def cancellation_fixture(ctx: Context, case: str, day: str, status: str = "confirmed") -> tuple[str, str, str]:
    """An event holding an approved venue booking, a pending equipment line and one
    registration. Returns (event, booking, line)."""
    event_id = throwaway_event(ctx, case, f"{day} 10:00+08", f"{day} 12:00+08", status=status)
    venue_id = throwaway_venue(ctx, case)
    [booking] = db_query(
        "insert into public.venue_bookings (event_id, venue_id, occupied_period, status) values "
        f"('{event_id}', '{venue_id}', tstzrange('{day} 10:00+08', '{day} 12:00+08', '[)'), 'approved') returning id"
    )
    line_id = throwaway_line(event_id, throwaway_equipment(ctx, case, 5), 2)
    db_query(f"insert into public.event_registrations (event_id, attendee_id) values ('{event_id}', '{ATTENDEE_ID}')")
    return event_id, booking["id"], line_id


def decide(ctx: Context, event_id: str, path: str, reason: str | None = None,
           session: Session | None = None) -> httpx.Response:
    session = session or ctx.shared("event_coordinator")
    body = {"reason": reason} if reason is not None else None
    return ctx.client.post(f"{ctx.api}/events/{event_id}/{path}", headers=session.headers, json=body)


@check("TC-CANCEL-014", "Approving cancels the event and releases its venue, equipment and registrations",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id, booking_id, line_id = cancellation_fixture(ctx, "115-014", "2031-11-03")
    expect_status(request_cancellation(ctx, event_id), 201)
    response = decide(ctx, event_id, "cancellation-request/approve")
    expect_status(response, 200)
    expect(response.json()["status"] == "cancelled", f"the event is {response.json()['status']}")
    [booking] = db_query(f"select status::text from public.venue_bookings where id = '{booking_id}'")
    expect(booking["status"] == "released", f"the venue booking is {booking['status']}")
    [line] = db_query(f"select status::text from public.equipment_requests where id = '{line_id}'")
    expect(line["status"] == "released", f"the equipment line is {line['status']}")
    [registration] = db_query(f"select status from public.event_registrations where event_id = '{event_id}'")
    expect(registration["status"] == "cancelled", f"the registration is {registration['status']}")
    [request] = db_query(f"select status, decided_by from public.event_change_requests where event_id = '{event_id}'")
    expect(request == {"status": "approved", "decided_by": COORDINATOR_ID}, f"request: {request}")
    notices = db_query(
        "select type, recipient_role::text as role from public.notifications "
        f"where event_id = '{event_id}' and type in ('event_cancelled', 'attendee_event_cancelled')"
    )
    roles = {n["role"] for n in notices}
    expect({"event_organiser", "attendee", "venue_staff", "tech_support"} <= roles, f"notified roles: {roles}")
    history = ctx.client.get(f"{ctx.api}/events/{event_id}/history",
                             headers=ctx.shared("event_organiser").headers).json()["entries"]
    entry = next((e for e in history if e.get("to_status") == "cancelled"), None)
    expect(entry and CANCEL_REASON in (entry["reason"] or "") and entry["actor"], f"history: {history}")


@check("TC-CANCEL-015", "Rejecting keeps the event and its arrangements; the organiser sees why", needs_db=True)
def _(ctx: Context) -> None:
    event_id, booking_id, _line = cancellation_fixture(ctx, "115-015", "2031-11-04", status="planning")
    expect_status(request_cancellation(ctx, event_id), 201)
    expect_status(decide(ctx, event_id, "cancellation-request/reject", "   "), 422)
    response = decide(ctx, event_id, "cancellation-request/reject", DECISION_REASON)
    expect_status(response, 200)
    expect(response.json()["status"] == "planning", f"the event is {response.json()['status']}")
    [booking] = db_query(f"select status::text from public.venue_bookings where id = '{booking_id}'")
    expect(booking["status"] == "approved", f"rejecting changed the booking to {booking['status']}")
    notices = db_query(
        "select recipient_role::text as role, message from public.notifications "
        f"where event_id = '{event_id}' and type = 'event_cancellation_rejected'"
    )
    expect(len(notices) == 1 and notices[0]["role"] == "event_organiser" and DECISION_REASON in notices[0]["message"],
           f"notices: {notices}")
    history = ctx.client.get(f"{ctx.api}/events/{event_id}/history",
                             headers=ctx.shared("event_organiser").headers).json()["entries"]
    entry = next((e for e in history if e["kind"] == "cancellation_rejected"), None)
    expect(entry and entry["reason"] == DECISION_REASON and entry["actor"], f"history: {history}")
    again = decide(ctx, event_id, "cancellation-request/approve")
    expect_status(again, 409)
    expect_detail(again, "There is no open cancellation request for this event.")


@check("TC-CANCEL-016", "The coordinator cancels directly only from planning, confirmed or preparation, before the start",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id, booking_id, _line = cancellation_fixture(ctx, "115-016", "2031-11-05", status="planning")
    expect_status(request_cancellation(ctx, event_id), 201)
    response = decide(ctx, event_id, "cancel", DECISION_REASON)
    expect_status(response, 200)
    [request] = db_query(f"select status, decision_reason from public.event_change_requests where event_id = '{event_id}'")
    expect(request == {"status": "approved", "decision_reason": DECISION_REASON}, f"request: {request}")
    [booking] = db_query(f"select status::text from public.venue_bookings where id = '{booking_id}'")
    expect(booking["status"] == "released", f"the venue booking is {booking['status']}")

    for status in ("under_review", "safety_review", "rejected", "completed"):
        other = throwaway_event(ctx, f"115-016-{status}", "2031-11-06 10:00+08", "2031-11-06 12:00+08", status=status)
        expect_status(decide(ctx, other, "cancel", DECISION_REASON), 409)
        [event] = db_query(f"select status::text from public.events where id = '{other}'")
        expect(event["status"] == status, f"a refused cancel moved a {status} event to {event['status']}")
    started = throwaway_event(ctx, "115-016-started", "2020-01-01 10:00+08", "2099-01-01 12:00+08", status="confirmed")
    refused = decide(ctx, started, "cancel", DECISION_REASON)
    expect_status(refused, 409)
    expect_detail(refused, "This event has already started, so it can't be cancelled.")


@check("TC-CANCEL-017", "Only the assigned coordinator, acting as coordinator, decides a cancellation", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "115-017", "2031-11-07 10:00+08", "2031-11-07 12:00+08", status="confirmed")
    expect_status(request_cancellation(ctx, event_id), 201)
    for role in ("event_organiser", "event_coordinator_lead", "venue_staff", "tech_support", "safety_officer", "attendee"):
        session = ctx.shared(role)
        expect_status(decide(ctx, event_id, "cancellation-request/approve", session=session), 403)
        expect_status(decide(ctx, event_id, "cancellation-request/reject", DECISION_REASON, session=session), 403)
        expect_status(decide(ctx, event_id, "cancel", DECISION_REASON, session=session), 403)
    unassigned = throwaway_event(ctx, "115-017-unassigned", "2031-11-08 10:00+08", "2031-11-08 12:00+08",
                                 status="confirmed", assigned=False)
    expect_status(decide(ctx, unassigned, "cancel", DECISION_REASON), 403)
    [request] = db_query(f"select status from public.event_change_requests where event_id = '{event_id}'")
    [event] = db_query(f"select status::text from public.events where id = '{event_id}'")
    expect(request["status"] == "open" and event["status"] == "confirmed",
           f"a refused decision changed something: request {request}, event {event}")


@check("TC-CANCEL-024", "Rejecting the event closes its open cancellation request (CR-R22)", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "115-024", "2031-11-09 10:00+08", "2031-11-09 12:00+08", status="planning")
    expect_status(request_cancellation(ctx, event_id), 201)
    expect_status(decide(ctx, event_id, "reject", DECISION_REASON), 200)
    [request] = db_query(f"select status, decision_reason from public.event_change_requests where event_id = '{event_id}'")
    expect(request == {"status": "superseded", "decision_reason": "Closed because the event was rejected."},
           f"request: {request}")
    event = ctx.client.get(f"{ctx.api}/events/{event_id}", headers=ctx.shared("event_coordinator").headers).json()
    expect(event["status"] == "rejected" and event.get("open_cancellation_request") is None,
           f"the coordinator still sees an open request: {event.get('open_cancellation_request')}")
    refused = decide(ctx, event_id, "cancellation-request/reject", DECISION_REASON)
    expect_status(refused, 409)
    expect_detail(refused, "There is no open cancellation request for this event.")
    notices = db_query(f"select count(*) as n from public.notifications "
                       f"where event_id = '{event_id}' and type = 'event_cancellation_rejected'")
    expect(int(notices[0]["n"]) == 0, "the organiser was told their request was rejected")


# --- Story 37: the coordinator decides a change request ---------------------------
# Throwaway events, venues and equipment again; everything goes with them.

TECH_SUPPORT_ID = "a0000000-0000-4000-8000-000000000004"
SAFETY_OFFICER_ID = "a0000000-0000-4000-8000-000000000006"
CHANGE_DECISION_REASON = "live-check: the venue can't take more people"


def decision_fixture(ctx: Context, case: str, day: str, status: str = "planning",
                     spaces: tuple[str, ...] = ("Main hall",)) -> tuple[str, list[str]]:
    """A complete throwaway event for 40 on `day` 10:00-12:00, with 40-pax theatre spaces
    that inherit its times. Returns (event, spaces)."""
    event_id = throwaway_event(ctx, case, f"{day} 10:00+08", f"{day} 12:00+08", status=status)
    db_query("update public.events set purpose = 'live-check', expected_attendance = 40, "
             f"layout_preference = 'theatre' where id = '{event_id}'")
    return event_id, [throwaway_space(event_id, label, pax=40, layout="theatre") for label in spaces]


def booking_on(event_id: str, space_id: str | None, venue_id: str, day: str, status: str = "approved", *,
               start: str = "10:00", end: str = "12:00", setup: int = 0) -> str:
    space = f"'{space_id}'" if space_id else "null"
    [row] = db_query(
        "insert into public.venue_bookings (event_id, event_space_request_id, venue_id, booked_period, setup_minutes, "
        f"status) values ('{event_id}', {space}, '{venue_id}', tstzrange('{day} {start}+08', '{day} {end}+08', '[)'), "
        f"{setup}, '{status}') returning id"
    )
    return row["id"]


def decide_change(ctx: Context, event_id: str, decision: str, *, reason: str | None = None,
                  session: Session | None = None) -> httpx.Response:
    session = session or ctx.shared("event_coordinator")
    body = {"version": event_version(event_id)} if decision == "approve" else {"reason": reason}
    return ctx.client.post(f"{ctx.api}/events/{event_id}/change-request/{decision}", headers=session.headers, json=body)


def later(day: str, start: str = "14:00", end: str = "16:00") -> dict:
    return {"starts_at": f"{day}T{start}:00+08:00", "ends_at": f"{day}T{end}:00+08:00"}


def booking_row(booking_id: str) -> dict:
    [row] = db_query("select status::text as status, flag::text as flag, flag_reason, needs_re_review_reason, "
                     "lower(booked_period) as starts, upper(booked_period) as ends "
                     f"from public.venue_bookings where id = '{booking_id}'")
    return row


def at_hour(value: str) -> str:
    """'2031-12-01 06:00:00+00' as the SGT hour, for comparing a booking's window."""
    return dt.datetime.fromisoformat(value.replace(" ", "T").replace("+00", "+00:00")).astimezone(SGT).strftime("%H:%M")


def notices_of(event_id: str, kind: str) -> list[dict]:
    return db_query("select recipient_id, recipient_role::text as role, message from public.notifications "
                    f"where event_id = '{event_id}' and type = '{kind}'")


@check("TC-CHANGE-013", "The coordinator rejects a change with a reason; the event keeps everything (AC2, AC4)",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id, [space] = decision_fixture(ctx, "37-013", "2031-12-01", status="confirmed")
    booking_id = booking_on(event_id, space, throwaway_venue(ctx, "37-013"), "2031-12-01")
    expect_status(request_change(ctx, event_id, event={"expected_attendance": 45}), 201)
    for reason in ("   ", "x" * 1001):
        expect_status(decide_change(ctx, event_id, "reject", reason=reason), 422)
    response = decide_change(ctx, event_id, "reject", reason=f"  {CHANGE_DECISION_REASON}  ")
    expect_status(response, 200)
    [event] = db_query(f"select status::text, expected_attendance from public.events where id = '{event_id}'")
    expect(event == {"status": "confirmed", "expected_attendance": 40}, f"rejecting changed the event: {event}")
    expect(booking_row(booking_id)["status"] == "approved", "rejecting touched the booking")
    [request] = stored_requests(event_id)
    expect(request["status"] == "rejected" and request["decision_reason"] == CHANGE_DECISION_REASON, f"request: {request}")
    notices = notices_of(event_id, "event_change_rejected")
    expect(len(notices) == 1 and notices[0]["role"] == "event_organiser"
           and CHANGE_DECISION_REASON in notices[0]["message"], f"notices: {notices}")
    history = ctx.client.get(f"{ctx.api}/events/{event_id}/history",
                             headers=ctx.shared("event_organiser").headers).json()["entries"]
    expect(any(e["kind"] == "change_rejected" and e["reason"] == CHANGE_DECISION_REASON for e in history),
           f"history: {history}")


@check("TC-CHANGE-014", "An ordinary change is applied with no status change; a stale one is refused (Q7, Q8)",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id, [space] = decision_fixture(ctx, "37-014", "2031-12-02", status="confirmed")
    booking_id = booking_on(event_id, space, throwaway_venue(ctx, "37-014"), "2031-12-02")
    expect_status(request_change(ctx, event_id, event={"description": "live-check: new description"},
                                 spaces=[{"id": space, "label": "Great hall"}]), 201)
    before = event_version(event_id)
    expect_status(decide_change(ctx, event_id, "approve"), 200)
    [event] = db_query(f"select status::text, description, version from public.events where id = '{event_id}'")
    expect(event["status"] == "confirmed" and event["description"] == "live-check: new description"
           and int(event["version"]) == before + 1, f"event: {event}")
    [label] = db_query(f"select label from public.event_space_requests where id = '{space}'")
    expect(label["label"] == "Great hall", f"space: {label}")
    expect(booking_row(booking_id)["status"] == "approved", "an ordinary change touched the booking")
    expect(stored_requests(event_id)[0]["status"] == "approved", "the request isn't approved")
    expect(len(notices_of(event_id, "event_change_approved")) == 1, "the organiser wasn't told once")

    stale_event, _spaces = decision_fixture(ctx, "37-014b", "2031-12-03", status="confirmed")
    expect_status(request_change(ctx, stale_event, event={"description": "live-check: requested"}), 201)
    db_query(f"update public.events set description = 'live-check: edited since' where id = '{stale_event}'")
    stale = decide_change(ctx, stale_event, "approve")
    expect_status(stale, 409)
    expect_detail(stale, "This event has changed since the request was made; reject it and ask for a new one.")
    expect(stored_requests(stale_event)[0]["status"] == "open", "a refused approval closed the request")


@check("TC-CHANGE-015", "A significant change sends Confirmed, Preparation and Safety review back to Planning (AC7, Q6)",
       needs_db=True)
def _(ctx: Context) -> None:
    outcomes = {}
    for status in ("confirmed", "preparation", "safety_review", "planning"):
        event_id, _spaces = decision_fixture(ctx, f"37-015-{status}", "2031-12-04", status=status)
        if status == "confirmed":
            db_query(f"insert into public.event_registrations (event_id, attendee_id) values ('{event_id}', '{ATTENDEE_ID}')")
        expect_status(request_change(ctx, event_id, event={"expected_attendance": 45}), 201)
        expect_status(decide_change(ctx, event_id, "approve"), 200)
        [event] = db_query(f"select status::text from public.events where id = '{event_id}'")
        outcomes[status] = (event_id, event["status"])
    expect(all(after == "planning" for _id, after in outcomes.values()), f"statuses: {outcomes}")
    confirmed = outcomes["confirmed"][0]
    rows = db_query(f"select actor_id, reason from public.event_status_history where event_id = '{confirmed}' "
                    "and from_status = 'confirmed' and to_status = 'planning'")
    expect(len(rows) == 1 and rows[0]["actor_id"] == COORDINATOR_ID and "expected attendance" in rows[0]["reason"],
           f"history: {rows}")
    expect(notices_of(confirmed, "attendee_event_changed") == [], "an attendee was told of an attendance change")
    safety = outcomes["safety_review"][0]
    withdrawn = db_query(f"select reason_code from public.event_safety_decisions where event_id = '{safety}' "
                         "and decision = 'withdrawn'")
    expect(withdrawn == [{"reason_code": "approved_details_changed"}], f"safety decisions: {withdrawn}")
    officers = notices_of(safety, "event_returned_to_planning")
    expect(any(n["recipient_id"] == SAFETY_OFFICER_ID and n["role"] == "safety_officer" for n in officers),
           f"officer notices: {officers}")
    planning = outcomes["planning"][0]
    moved = db_query(f"select count(*) as n from public.event_status_history where event_id = '{planning}' "
                     "and from_status is not null")
    expect(int(moved[0]["n"]) == 0, "a Planning event got a status row")


def moved_event(ctx: Context, case: str, day: str) -> dict:
    """A planning event on `day` with four spaces and their bookings, and two reserved
    equipment lines, ready for a change that moves it to 14:00-16:00 and raises the
    Crowded space to 60: Clear (approved, free at the new time), Clash (approved, an
    hour's setup runs into another event's 13:00-14:00 hold), Held and Crowded (a venue
    for 50). One line of 8 is left short by another event's 5 of the same 10 at the new
    time; one of 2 still fits. Exits are ticked, so it is technically Ready."""
    event_id, (clear, clash, held, crowded) = decision_fixture(
        ctx, case, day, spaces=("Clear", "Clash", "Held", "Crowded"))
    venues = {name: throwaway_venue(ctx, f"{case} {name}") for name in ("clear", "clash", "held", "crowded")}
    blocker = throwaway_event(ctx, f"{case} blocker", f"{day} 13:00+08", f"{day} 14:00+08")
    booking_on(blocker, None, venues["clash"], day, status="held", start="13:00", end="14:00")
    bookings = {
        "clear": booking_on(event_id, clear, venues["clear"], day),
        "clash": booking_on(event_id, clash, venues["clash"], day, setup=60),
        "held": booking_on(event_id, held, venues["held"], day, status="held"),
        "crowded": booking_on(event_id, crowded, venues["crowded"], day),
    }
    stock = throwaway_equipment(ctx, f"{case} short", 10)
    roomy = throwaway_equipment(ctx, f"{case} roomy", 10)
    lines = {"short": throwaway_line(event_id, stock, 8), "fits": throwaway_line(event_id, roomy, 2)}
    for line_id, item, quantity in ((lines["short"], stock, 8), (lines["fits"], roomy, 2)):
        db_query(f"update public.equipment_requests set status = 'reserved' where id = '{line_id}'")
        db_query("insert into public.equipment_reservations (equipment_id, event_id, quantity, start_at, end_at, "
                 f"request_line_id) values ('{item}', '{event_id}', {quantity}, '{day} 10:00+08', '{day} 12:00+08', "
                 f"'{line_id}')")
    db_query("insert into public.equipment_reservations (equipment_id, event_id, quantity, start_at, end_at) values "
             f"('{stock}', '{blocker}', 5, '{day} 14:00+08', '{day} 16:00+08')")
    db_query(f"update public.events set exit_confirmed_at = now(), exit_confirmed_by = '{TECH_SUPPORT_ID}' "
             f"where id = '{event_id}'")
    db_query(f"select private.refresh_technical_status('{event_id}')")
    expect_status(request_change(ctx, event_id, event=later(day), spaces=[{"id": crowded, "expected_pax": 60}]), 201)
    return {"event": event_id, "bookings": bookings, "lines": lines, "venues": venues,
            "spaces": {"clear": clear, "clash": clash, "held": held, "crowded": crowded}}


@check("TC-CHANGE-016", "A new time moves, marks or flags each booking (AC3, AC5, Q11, Q15, Q17)", needs_db=True)
def _(ctx: Context) -> None:
    fixture = moved_event(ctx, "37-016", "2031-12-05")
    expect_status(decide_change(ctx, fixture["event"], "approve"), 200)
    clear, clash, held, crowded = (booking_row(fixture["bookings"][k]) for k in ("clear", "clash", "held", "crowded"))
    expect(clear["status"] == "approved" and at_hour(clear["starts"]) == "14:00"
           and clear["needs_re_review_reason"] == "Date or time changed.", f"clear booking: {clear}")
    moves = db_query("select at_hour from (select to_char(lower(old_period) at time zone 'Asia/Singapore', 'HH24:MI') "
                     "as at_hour from public.venue_booking_history where booking_id = "
                     f"'{fixture['bookings']['clear']}' and action = 'moved_by_change') m")
    expect(moves == [{"at_hour": "10:00"}], f"move history: {moves}")
    expect(clash["flag"] == "conflict" and at_hour(clash["starts"]) == "10:00" and clash["needs_re_review_reason"] is None
           and "blocker" in (clash["flag_reason"] or ""), f"clashing booking: {clash}")
    expect(held["status"] == "held" and at_hour(held["starts"]) == "14:00" and held["needs_re_review_reason"] is None,
           f"held booking: {held}")
    expect(crowded["flag"] == "unsuitable" and "needs 60 people" in (crowded["flag_reason"] or ""),
           f"crowded booking: {crowded}")
    readiness = ctx.client.get(f"{ctx.api}/events/{fixture['event']}",
                               headers=ctx.shared("event_coordinator").headers).json()["safety_readiness"]
    expect("Clear: needs re-review." in readiness["missing"] and "Clash: flagged Conflict." in readiness["missing"],
           f"readiness: {readiness}")


@check("TC-CHANGE-017", "A new time moves every reservation; only a short line is marked, keeping its units (Q14)",
       needs_db=True)
def _(ctx: Context) -> None:
    fixture = moved_event(ctx, "37-017", "2031-12-06")
    expect_status(decide_change(ctx, fixture["event"], "approve"), 200)
    windows = db_query("select to_char(start_at at time zone 'Asia/Singapore', 'HH24:MI') as at from "
                       f"public.equipment_reservations where event_id = '{fixture['event']}'")
    expect(windows and all(w["at"] == "14:00" for w in windows), f"reservations: {windows}")
    lines = {key: db_query("select status::text, needs_re_review_reason from public.equipment_requests "
                           f"where id = '{line_id}'")[0] for key, line_id in fixture["lines"].items()}
    expect(lines["short"] == {"status": "reserved", "needs_re_review_reason": "Event time changed; 5 free for 8."},
           f"short line: {lines['short']}")
    expect(lines["fits"]["needs_re_review_reason"] is None, f"the line that fits was marked: {lines['fits']}")
    [event] = db_query(f"select technical_readiness::text from public.events where id = '{fixture['event']}'")
    expect(event["technical_readiness"] == "pending", f"technical status: {event}")
    # The organiser's request told them (story 32); nothing since should have.
    own = db_query(f"select type, message from public.notifications where event_id = '{fixture['event']}' "
                   f"and recipient_id = '{COORDINATOR_ID}' and type <> 'event_change_requested'")
    expect(own == [], f"the coordinator was told of their own approval: {own}")


@check("TC-CHANGE-018", "The coordinator sends a marked booking and line for re-review; staff are told (AC6, Q20)",
       needs_db=True)
def _(ctx: Context) -> None:
    fixture = moved_event(ctx, "37-018", "2031-12-07")
    expect_status(decide_change(ctx, fixture["event"], "approve"), 200)
    coordinator = ctx.shared("event_coordinator")
    booking, line = fixture["bookings"]["clear"], fixture["lines"]["short"]
    for role in ("event_organiser", "venue_staff", "tech_support"):
        expect_status(ctx.client.post(f"{ctx.api}{BOOKINGS}/{booking}/send-for-re-review",
                                      headers=ctx.shared(role).headers, json={}), 403)
    sent = ctx.client.post(f"{ctx.api}{BOOKINGS}/{booking}/send-for-re-review", headers=coordinator.headers,
                           json={"note": "  live-check: please check the afternoon  "})
    expect_status(sent, 204)
    row = booking_row(booking)
    expect(row["status"] == "re_review" and row["needs_re_review_reason"] is None, f"sent booking: {row}")
    notes = db_query("select reason from public.venue_booking_history where booking_id = "
                     f"'{booking}' and action = 'sent_for_re_review'")
    expect(notes == [{"reason": "live-check: please check the afternoon"}], f"send history: {notes}")
    staff = notices_of(fixture["event"], "venue_booking_re_review")
    expect(any(n["recipient_id"] == VENUE_STAFF_ID and n["role"] == "venue_staff" for n in staff), f"notices: {staff}")
    again = ctx.client.post(f"{ctx.api}{BOOKINGS}/{booking}/send-for-re-review", headers=coordinator.headers, json={})
    expect_status(again, 409)
    expect_detail(again, "This booking doesn't need re-review.")

    expect_status(ctx.client.post(f"{ctx.api}{EQUIPMENT_REQUESTS}/{line}/send-for-re-review",
                                  headers=coordinator.headers, json={}), 204)
    [state] = db_query(f"select status::text, needs_re_review_reason from public.equipment_requests where id = '{line}'")
    expect(state == {"status": "re_review", "needs_re_review_reason": None}, f"sent line: {state}")
    kept = db_query(f"select status from public.equipment_reservations where request_line_id = '{line}'")
    expect(kept == [{"status": "confirmed"}], f"the line's reservation: {kept}")
    tech = notices_of(fixture["event"], "equipment_line_re_review")
    expect(any(n["recipient_id"] == TECH_SUPPORT_ID and n["role"] == "tech_support" for n in tech), f"notices: {tech}")


@check("TC-CHANGE-019", "Venue staff see what changed, then re-approve or reject a booking under re-review (Q12, Q21)",
       needs_db=True)
def _(ctx: Context) -> None:
    fixture = moved_event(ctx, "37-019", "2031-12-08")
    second = booking_on(fixture["event"], throwaway_space(fixture["event"], "Second", pax=40, layout="theatre"),
                        throwaway_venue(ctx, "37-019 second"), "2031-12-08")
    expect_status(decide_change(ctx, fixture["event"], "approve"), 200)
    coordinator, staff = ctx.shared("event_coordinator"), ctx.shared("venue_staff")
    first = fixture["bookings"]["clear"]
    for booking_id in (first, second):
        expect_status(ctx.client.post(f"{ctx.api}{BOOKINGS}/{booking_id}/send-for-re-review",
                                      headers=coordinator.headers, json={"note": "live-check note"}), 204)
    detail = ctx.client.get(f"{ctx.api}{BOOKINGS}/{first}", headers=staff.headers).json()
    context = detail["re_review"]
    expect(context and context["note"] == "live-check note" and context["changes"]["event"]
           and context["moved_from"] and context["moved_to"], f"re-review context: {context}")
    expect_status(ctx.client.post(f"{ctx.api}{BOOKINGS}/{first}/approve", headers=staff.headers), 200)
    expect(booking_row(first)["status"] == "approved", "re-approval didn't approve")
    told = notices_of(fixture["event"], "venue_booking_approved")
    expect(any("re-approved" in n["message"] for n in told), f"coordinator notices: {told}")
    expect_status(ctx.client.post(f"{ctx.api}{BOOKINGS}/{second}/reject", headers=staff.headers,
                                  json={"reason": "live-check: too small now"}), 200)
    expect(booking_row(second)["status"] == "rejected", "the re-review rejection didn't reject")
    actions = db_query(f"select action from public.venue_booking_history where booking_id in ('{first}', '{second}') "
                       "and action like 're_review_%' order by action")
    expect(actions == [{"action": "re_review_approved"}, {"action": "re_review_rejected"}], f"history: {actions}")


@check("TC-CHANGE-020", "A booking an approved change flagged Conflict or Unsuitable can be replaced (Q16, Q17)",
       needs_db=True)
def _(ctx: Context) -> None:
    fixture = moved_event(ctx, "37-020", "2031-12-09")
    expect_status(decide_change(ctx, fixture["event"], "approve"), 200)
    coordinator = ctx.shared("event_coordinator")
    for key in ("clash", "crowded"):
        venue = throwaway_venue(ctx, f"37-020 replacement {key}")
        db_query(f"update public.venues set capacity = 100 where id = '{venue}'")
        response = ctx.client.post(f"{ctx.api}{BOOKINGS}", headers=coordinator.headers, json={
            "event_space_request_id": fixture["spaces"][key], "venue_id": venue,
            "replaces_booking_id": fixture["bookings"][key]})
        expect_status(response, 201)


@check("TC-CHANGE-021", "The impact preview says what approving would do; only the coordinator sees it (Q1)",
       needs_db=True)
def _(ctx: Context) -> None:
    fixture = moved_event(ctx, "37-021", "2031-12-10")
    db_query(f"insert into public.event_registrations (event_id, attendee_id) values ('{fixture['event']}', '{ATTENDEE_ID}')")
    url = f"{ctx.api}/events/{fixture['event']}/change-request/impact"
    for role in ("event_organiser", "venue_staff", "tech_support", "event_coordinator_lead", "attendee"):
        expect_status(ctx.client.get(url, headers=ctx.shared(role).headers), 403)
    response = ctx.client.get(url, headers=ctx.shared("event_coordinator").headers)
    expect_status(response, 200)
    impact = response.json()
    messages = {b["space_label"]: " ".join(b["messages"]) for b in impact["bookings"]}
    expect("Needs re-review by venue staff" in messages.get("Clear", ""), f"Clear: {messages}")
    expect("Clashes with" in messages.get("Clash", "") and "flagged Conflict" in messages["Clash"], f"Clash: {messages}")
    expect("A replacement venue is needed." in messages.get("Crowded", ""), f"Crowded: {messages}")
    expect([(e["needed"], e["free"]) for e in impact["equipment"]] == [(8, 5)], f"equipment: {impact['equipment']}")
    expect(impact["attendees_notified"] == 1, f"attendees: {impact['attendees_notified']}")
    expect(stored_requests(fixture["event"])[0]["status"] == "open", "previewing decided the request")


@check("TC-CHANGE-022", "A closed or started event takes no decision; nothing changes (AC8, Q5)", needs_db=True)
def _(ctx: Context) -> None:
    for status in ("completed", "cancelled", "rejected", "started"):
        if status == "started":
            event_id = throwaway_event(ctx, "37-022-started", "2020-01-01 10:00+08", "2099-01-01 12:00+08",
                                       status="confirmed")
        else:
            event_id, _spaces = decision_fixture(ctx, f"37-022-{status}", "2031-12-11", status=status)
        db_query("insert into public.event_change_requests (event_id, kind, reason, requested_by, changes, significant) "
                 f"values ('{event_id}', 'change', 'live-check', 'a0000000-0000-4000-8000-000000000001', "
                 """'{"event": [{"field": "description", "before": null, "after": "x"}], "spaces": []}', false)""")
        expect_status(decide_change(ctx, event_id, "approve"), 409)
        expect_status(decide_change(ctx, event_id, "reject", reason=CHANGE_DECISION_REASON), 409)
        [request] = stored_requests(event_id)
        [event] = db_query(f"select status::text, description from public.events where id = '{event_id}'")
        expect(request["status"] == "open" and event["description"] is None, f"{status}: {request}, {event}")


@check("TC-CHANGE-023", "A second change keeps a booking under re-review with venue staff (Q22)", needs_db=True)
def _(ctx: Context) -> None:
    event_id, [space] = decision_fixture(ctx, "37-023", "2031-12-12")
    booking_id = booking_on(event_id, space, throwaway_venue(ctx, "37-023"), "2031-12-12", status="re_review")
    expect_status(request_change(ctx, event_id, event=later("2031-12-12")), 201)
    expect_status(decide_change(ctx, event_id, "approve"), 200)
    row = booking_row(booking_id)
    expect(row["status"] == "re_review" and at_hour(row["starts"]) == "14:00" and row["needs_re_review_reason"] is None,
           f"booking: {row}")
    told = notices_of(event_id, "venue_booking_re_review")
    expect(any(n["role"] == "venue_staff" and "changed again" in n["message"] for n in told), f"notices: {told}")


# --- CR-110 technical preparation ----------------------------------------------

def preparation(ctx: Context, event_id: str, stage: str, note: str | None = None,
                session: Session | None = None) -> httpx.Response:
    session = session or ctx.shared("tech_support")
    return ctx.client.put(f"{ctx.api}/equipment/events/{event_id}/preparation", headers=session.headers,
                          json={"stage": stage, "note": note})


@check("TC-TPREP-007", "Tech support's first update on a Confirmed event moves it to Preparation and tells "
       "the organiser and coordinator", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "TPREP007", "2031-12-01 09:00+08", "2031-12-01 12:00+08", status="confirmed")
    response = preparation(ctx, event_id, "in_preparation", "  Cables ordered  ")
    expect_status(response, 200)
    expect(response.json() == {"stage": "in_preparation", "note": "Cables ordered", "event_status": "preparation"},
           f"response: {response.json()}")
    [event] = db_query(f"select status::text from public.events where id = '{event_id}'")
    expect(event["status"] == "preparation", f"the event is {event['status']}")
    notices = db_query("select recipient_role::text as role from public.notifications "
                       f"where event_id = '{event_id}' and type = 'preparation_started'")
    roles = sorted(n["role"] for n in notices)
    expect(roles == ["event_coordinator", "event_organiser"], f"notified roles: {roles}")
    expect_status(preparation(ctx, event_id, "completed"), 200)
    [moves] = db_query("select count(*) as n from public.event_status_history "
                       f"where event_id = '{event_id}' and to_status = 'preparation'")
    expect(int(moves["n"]) == 1, f"{moves['n']} moves to Preparation, expected 1")
    # D73: the coordinator still has the event once it is in Preparation.
    dashboard = ctx.client.get(f"{ctx.api}/events/dashboard/coordinator",
                               headers=ctx.shared("event_coordinator").headers).json()
    active = {e["event_id"]: e["status"] for e in dashboard["active_events"]}
    expect(active.get(event_id) == "preparation", f"the coordinator's dashboard has {active.get(event_id)}")


@check("TC-TPREP-008", "Technical preparation is refused before the Safety Officer confirms the event",
       needs_db=True)
def _(ctx: Context) -> None:
    for status in ("planning", "safety_review"):
        event_id = throwaway_event(ctx, f"TPREP008-{status}", "2031-12-02 09:00+08", "2031-12-02 12:00+08",
                                   status=status)
        response = preparation(ctx, event_id, "in_progress")
        expect_status(response, 409)
        expect_detail(response, "Technical preparation opens once the Safety Officer has confirmed the event.")
        [event] = db_query(f"select status::text from public.events where id = '{event_id}'")
        expect(event["status"] == status, f"a refused update moved the event to {event['status']}")


@check("TC-TPREP-009", "Two tech staff updating a Confirmed event at once move it to Preparation once",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "TPREP009", "2031-12-03 09:00+08", "2031-12-03 12:00+08", status="confirmed")
    sessions = [ctx.login("tech_support"), ctx.login("tech_support")]

    # Separate clients and sessions, so the two updates really are in flight together.
    def fire(pair) -> int:
        stage, session = pair
        with httpx.Client(timeout=30) as client:
            return client.put(f"{ctx.api}/equipment/events/{event_id}/preparation", headers=session.headers,
                              json={"stage": stage}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(fire, zip(["in_preparation", "in_progress"], sessions)))
    expect(codes == [200, 200], f"expected two 200s, got {codes}")
    [moves] = db_query("select count(*) as n from public.event_status_history "
                       f"where event_id = '{event_id}' and to_status = 'preparation'")
    expect(int(moves["n"]) == 1, f"{moves['n']} moves to Preparation, expected 1")
    [notices] = db_query("select count(*) as n from public.notifications "
                         f"where event_id = '{event_id}' and type = 'preparation_started'")
    expect(int(notices["n"]) == 2, f"{notices['n']} preparation_started notices, expected 2")


@check("TC-TPREP-010", "The coordinator sees the stage and note; the organiser sees the stage only", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "TPREP010", "2031-12-04 09:00+08", "2031-12-04 12:00+08", status="confirmed")
    expect_status(preparation(ctx, event_id, "in_progress", "Internal cabling note"), 200)
    coordinator = ctx.client.get(f"{ctx.api}/events/{event_id}",
                                 headers=ctx.shared("event_coordinator").headers).json()["technical_preparation"]
    expect(coordinator and coordinator["stage"] == "in_progress" and coordinator["note"] == "Internal cabling note",
           f"coordinator sees {coordinator}")
    organiser = ctx.client.get(f"{ctx.api}/events/{event_id}", headers=ctx.shared("event_organiser").headers)
    expect_status(organiser, 200)
    seen = organiser.json()["technical_preparation"]
    expect(seen and seen["stage"] == "in_progress" and "note" not in seen, f"organiser sees {seen}")
    expect("Internal cabling note" not in organiser.text, "the note reached the organiser's response")


@check("TC-TPREP-011", "Only Technical Support can record technical preparation", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "TPREP011", "2031-12-05 09:00+08", "2031-12-05 12:00+08", status="confirmed")
    for role in ("event_organiser", "event_coordinator", "venue_staff", "safety_officer"):
        expect_status(preparation(ctx, event_id, "completed", session=ctx.shared(role)), 403)
    [event] = db_query(f"select status::text from public.events where id = '{event_id}'")
    expect(event["status"] == "confirmed", f"a refused update moved the event to {event['status']}")


# --- Story 62: an event's change history -------------------------------------------
# Needs migration 20261030120000 applied. Each check makes its own throwaway event;
# its history cascades when the run deletes it.
def event_history(ctx: Context, event_id: str, role: str) -> httpx.Response:
    return ctx.client.get(f"{ctx.api}/events/{event_id}/history", headers=ctx.shared(role).headers)


@check("TC-HIST-008", "An edit to a returned request shows in its history with the old and new value", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "HIST008", "2031-12-10 09:00+08", "2031-12-10 12:00+08", status="returned")
    edited = ctx.client.patch(f"{ctx.api}/events/{event_id}", json={"description": "Now with a keynote"},
                              headers=ctx.shared("event_organiser").headers)
    expect_status(edited, 200)
    for role in ("event_organiser", "event_coordinator"):
        response = event_history(ctx, event_id, role)
        expect_status(response, 200)
        edits = [entry for entry in response.json()["entries"] if entry["kind"] == "edit"]
        expect(len(edits) == 1, f"{role} sees {len(edits)} edits, expected 1")
        [edit] = edits
        expect(edit["field"] == "description" and edit["old_value"] is None
               and edit["new_value"] == "Now with a keynote", f"{role} sees {edit}")
        expect((edit["actor"] or {}).get("id") == "a0000000-0000-4000-8000-000000000001",
               f"{role} sees the edit made by {edit['actor']}")


@check("TC-HIST-009", "The organiser's history has no staff-only entries or safety comments; "
                      "the coordinator's has them", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "HIST009", "2031-12-11 09:00+08", "2031-12-11 12:00+08", status="planning")
    db_query(
        "insert into public.event_safety_decisions (event_id, decision, comment, decided_by) values "
        f"('{event_id}', 'changes_requested', 'HIST009 officer note', 'a0000000-0000-4000-8000-000000000006');"
        "insert into public.event_technical_history (event_id, action, actor_id) values "
        f"('{event_id}', 'preparation', 'a0000000-0000-4000-8000-000000000004')"
    )
    organiser = event_history(ctx, event_id, "event_organiser")
    expect_status(organiser, 200)
    kinds = [entry["kind"] for entry in organiser.json()["entries"]]
    expect("safety_decision" in kinds, f"the organiser doesn't see the safety outcome: {kinds}")
    expect("technical" not in kinds and "booking" not in kinds, f"the organiser sees staff-only entries: {kinds}")
    expect("HIST009 officer note" not in organiser.text, "the safety comment reached the organiser's response")
    coordinator = event_history(ctx, event_id, "event_coordinator")
    expect_status(coordinator, 200)
    kinds = [entry["kind"] for entry in coordinator.json()["entries"]]
    expect({"safety_decision", "technical"} <= set(kinds), f"the coordinator misses entries: {kinds}")
    expect("HIST009 officer note" in coordinator.text, "the coordinator doesn't see the safety comment")


@check("TC-HIST-015", "A venue edit made while the event holds the venue shows in the coordinator's history only",
       needs_db=True)
def _(ctx: Context) -> None:
    venue_id, payload = cr94_venue(ctx, "HIST015")
    event_id, _ = cr94_booking(ctx, "HIST015", venue_id)
    body = edit_venue(ctx, venue_id, {**payload, "description": "HIST015 new description"})
    expect(body["saved"] is True, f"the harmless edit wasn't saved: {body}")
    coordinator = event_history(ctx, event_id, "event_coordinator")
    expect_status(coordinator, 200)
    edits = [entry for entry in coordinator.json()["entries"] if entry["kind"] == "venue_edit"]
    expect(len(edits) == 1, f"the coordinator sees {len(edits)} venue edits, expected 1")
    expect(edits[0]["new_value"].get("description") == "HIST015 new description", f"venue edit {edits[0]}")
    organiser = event_history(ctx, event_id, "event_organiser")
    expect_status(organiser, 200)
    expect("venue_edit" not in [entry["kind"] for entry in organiser.json()["entries"]],
           "the organiser sees a venue edit")


@check("TC-HIST-010", "Venue staff, tech support and attendees can't read an event's history", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "HIST010", "2031-12-12 09:00+08", "2031-12-12 12:00+08", status="planning")
    for role in ("venue_staff", "tech_support", "attendee"):
        expect_status(event_history(ctx, event_id, role), 403)


# --- CR-106: the coordinator asks the Lead to reassign their event ----------------------
# Every check works on its own throwaway events (deleted when the run ends, with their
# requests, history and notifications), never on seeded ones.

REASSIGN_REASON = "live-check: on leave this month"
DECLINE_REASON = "live-check: nobody else is free"


def seeded_lead_id() -> str:
    email = ACCOUNTS.get("event_coordinator_lead") or W7_STAFF_ACCOUNTS["event_coordinator_lead"]
    return db_query(f"select id from public.profiles where email = '{email}'")[0]["id"]


def scoped_event(ctx: Context, case: str, day: str, *, status: str = "planning") -> str:
    """A throwaway event assigned to the coordinator by the seeded Lead, so that Lead holds its scope."""
    event_id = throwaway_event(ctx, case, f"2031-{day} 09:00+08", f"2031-{day} 12:00+08", status=status)
    db_query(f"update public.events set assigned_by = '{seeded_lead_id()}' where id = '{event_id}'")
    return event_id


def ask_reassignment(ctx: Context, event_id: str, reason: str = REASSIGN_REASON,
                     session: Session | None = None) -> httpx.Response:
    session = session or ctx.shared("event_coordinator")
    return ctx.client.post(f"{ctx.api}/events/{event_id}/reassignment-request",
                           headers=session.headers, json={"reason": reason})


def decline_request(ctx: Context, event_id: str, reason: str = DECLINE_REASON,
                    session: Session | None = None) -> httpx.Response:
    session = session or lead_session(ctx)
    return ctx.client.post(f"{ctx.api}/events/{event_id}/reassignment-request/decline",
                           headers=session.headers, json={"reason": reason})


def open_requests(event_id: str) -> int:
    return int(db_query("select count(*) as n from public.event_reassignment_requests "
                        f"where event_id = '{event_id}'")[0]["n"])


@check("TC-REASSIGN-001", "The assigned coordinator asks: one open request, only the Lead holding the scope told, the event unchanged",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = scoped_event(ctx, "106-001", "11-02")
    before = event_row(event_id)
    response = ask_reassignment(ctx, event_id, f"  {REASSIGN_REASON}  ")
    expect_status(response, 201)
    body = response.json()
    expect(body["kind"] == "reassignment" and body["status"] == "open" and body["reason"] == REASSIGN_REASON,
           f"unexpected request: {body}")
    [row] = db_query("select status, requested_by from public.event_reassignment_requests "
                     f"where event_id = '{event_id}'")
    expect(row == {"status": "open", "requested_by": COORDINATOR_ID}, f"row: {row}")
    notices = db_query("select recipient_id, recipient_role::text as role, message from public.notifications "
                       f"where event_id = '{event_id}' and type = 'reassignment_requested'")
    expect(len(notices) == 1 and notices[0]["recipient_id"] == seeded_lead_id()
           and notices[0]["role"] == "event_coordinator_lead" and REASSIGN_REASON in notices[0]["message"],
           f"notices: {notices}")
    expect(event_row(event_id) == before, "requesting changed the event (AC3)")


@check("TC-REASSIGN-002", "A second request while one is open is refused", needs_db=True)
def _(ctx: Context) -> None:
    event_id = scoped_event(ctx, "106-002", "11-03")
    expect_status(ask_reassignment(ctx, event_id), 201)
    again = ask_reassignment(ctx, event_id, "live-check: again")
    expect_status(again, 409)
    expect_detail(again, "A reassignment request is already open for this event.")
    expect(open_requests(event_id) == 1, "a second request was stored")


@check("TC-REASSIGN-003", "A draft, a submitted and a closed event refuse a request and store nothing",
       needs_db=True)
def _(ctx: Context) -> None:
    for status in ("submitted", "completed", "cancelled", "rejected"):
        event_id = scoped_event(ctx, f"106-003-{status}", "11-04", status=status)
        response = ask_reassignment(ctx, event_id)
        expect_status(response, 409)
        expect_detail(response, f"Reassignment can't be requested for an event that is {status}.")
        expect(open_requests(event_id) == 0, f"a request was stored on a {status} event")
    draft = scoped_event(ctx, "106-003-draft", "11-04", status="draft")
    expect_status(ask_reassignment(ctx, draft), 404)
    expect_status(ask_reassignment(ctx, UNKNOWN_EVENT), 404)


@check("TC-REASSIGN-004", "Only the assigned coordinator, acting as coordinator, can ask; a reason is required", needs_db=True)
def _(ctx: Context) -> None:
    event_id = scoped_event(ctx, "106-004", "11-05")
    for role in ("event_organiser", "event_coordinator_lead", "venue_staff", "tech_support", "attendee", "safety_officer"):
        response = ask_reassignment(ctx, event_id, session=ctx.shared(role))
        expect(response.status_code == 403, f"{role} got HTTP {response.status_code}, expected 403")
    other_email = db_query(f"select email from public.profiles where id = '{SECOND_COORDINATOR}'")[0]["email"]
    other = ctx.login("event_coordinator", email=other_email)
    expect_status(ask_reassignment(ctx, event_id, session=other), 403)
    for reason in ("", "   "):
        expect_status(ask_reassignment(ctx, event_id, reason), 422)
    expect(open_requests(event_id) == 0, "a refused request was stored")


@check("TC-REASSIGN-005", "A coordinator cannot reassign or hand over directly; the event and its history are untouched",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = scoped_event(ctx, "106-005", "11-06")
    before = event_row(event_id)
    coordinator = ctx.shared("event_coordinator")
    expect_status(ctx.client.post(f"{ctx.api}/events/{event_id}/reassign", headers=coordinator.headers,
                                  json={"coordinator_id": SECOND_COORDINATOR, "expected_version": 1}), 403)
    expect_status(ctx.client.post(f"{ctx.api}/events/{event_id}/assign", headers=coordinator.headers,
                                  json={"coordinator_id": SECOND_COORDINATOR}), 403)
    expect(event_row(event_id) == before, "a refused reassignment changed the event")
    [history] = db_query(f"select count(*) as n from public.event_assignment_history where event_id = '{event_id}'")
    expect(int(history["n"]) == 0, "a refused reassignment wrote history")


@check("TC-REASSIGN-006", "The Lead's dashboard and the coordinator's page show the open request; the organiser does not",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = scoped_event(ctx, "106-006", "11-07")
    expect_status(ask_reassignment(ctx, event_id), 201)
    dashboard = ctx.client.get(f"{ctx.api}{LEAD_DASHBOARD}", headers=lead_session(ctx).headers).json()
    flagged = next((e for e in dashboard["active_events"] if e["event_id"] == event_id), None)
    expect(flagged and flagged["open_reassignment_request"]["reason"] == REASSIGN_REASON
           and flagged["open_reassignment_request"]["requested_by"]["id"] == COORDINATOR_ID,
           f"the Lead's dashboard has {flagged}")
    detail = ctx.client.get(f"{ctx.api}/events/{event_id}", headers=ctx.shared("event_coordinator").headers).json()
    expect(detail["open_reassignment_request"]["reason"] == REASSIGN_REASON, "the coordinator does not see it")
    organiser = ctx.shared("event_organiser")
    detail = ctx.client.get(f"{ctx.api}/events/{event_id}", headers=organiser.headers).json()
    expect(detail["open_reassignment_request"] is None, "the organiser sees the request")
    history = ctx.client.get(f"{ctx.api}/events/{event_id}/history", headers=ctx.shared("event_coordinator").headers).json()["entries"]
    entry = next((e for e in history if e["kind"] == "reassignment_requested"), None)
    expect(entry and entry["reason"] == REASSIGN_REASON and entry["actor"]["id"] == COORDINATOR_ID,
           f"coordinator history: {history}")
    history = ctx.client.get(f"{ctx.api}/events/{event_id}/history", headers=organiser.headers).json()["entries"]
    expect(not any(e["kind"].startswith("reassignment_request") for e in history), f"organiser history: {history}")


@check("TC-REASSIGN-007", "The Lead declines with a reason: the coordinator is told and stays assigned; blank reasons and other roles are refused",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = scoped_event(ctx, "106-007", "11-08")
    expect_status(ask_reassignment(ctx, event_id), 201)
    before = event_row(event_id)
    for role in ("event_coordinator", "event_organiser", "safety_officer"):
        response = decline_request(ctx, event_id, session=ctx.shared(role))
        expect(response.status_code == 403, f"{role} got HTTP {response.status_code}, expected 403")
    expect_status(decline_request(ctx, event_id, "   "), 422)
    response = decline_request(ctx, event_id, f"  {DECLINE_REASON}  ")
    expect_status(response, 200)
    expect(response.json()["status"] == "declined", f"unexpected response: {response.json()}")
    [row] = db_query("select status, decided_by, decision_reason from public.event_reassignment_requests "
                     f"where event_id = '{event_id}'")
    expect(row == {"status": "declined", "decided_by": seeded_lead_id(), "decision_reason": DECLINE_REASON}, f"row: {row}")
    notices = db_query("select recipient_id, recipient_role::text as role, message from public.notifications "
                       f"where event_id = '{event_id}' and type = 'reassignment_declined'")
    expect(len(notices) == 1 and notices[0]["recipient_id"] == COORDINATOR_ID
           and notices[0]["role"] == "event_coordinator" and DECLINE_REASON in notices[0]["message"], f"notices: {notices}")
    expect(event_row(event_id) == before, "declining changed the assignment")
    again = decline_request(ctx, event_id)
    expect_status(again, 409)
    expect_detail(again, "There is no open reassignment request for this event.")
    history = ctx.client.get(f"{ctx.api}/events/{event_id}/history", headers=ctx.shared("event_coordinator").headers).json()["entries"]
    declined = next((e for e in history if e["kind"] == "reassignment_declined"), None)
    expect(declined and declined["reason"] == DECLINE_REASON and declined["actor"]["id"] == seeded_lead_id(),
           f"history: {history}")
    expect_status(ask_reassignment(ctx, event_id, "live-check: asking again"), 201)


@check("TC-REASSIGN-008", "Another Lead's event cannot be declined", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "106-008", "2031-11-09 09:00+08", "2031-11-09 12:00+08")
    # Held by the other seeded Lead, so the shared one is out of scope when two Leads exist.
    others = db_query("select profile_id from public.user_roles where role = 'event_coordinator_lead' "
                      f"and profile_id <> '{seeded_lead_id()}'")
    if not others:
        raise CheckBlocked("not run: only one Lead is seeded, so there is no other Lead's scope to cross")
    db_query(f"update public.events set assigned_by = '{others[0]['profile_id']}' where id = '{event_id}'")
    expect_status(ask_reassignment(ctx, event_id), 201)
    expect_status(decline_request(ctx, event_id), 403)
    [row] = db_query(f"select status from public.event_reassignment_requests where event_id = '{event_id}'")
    expect(row["status"] == "open", "an out-of-scope Lead closed the request")


@check("TC-REASSIGN-009", "The Lead reassigning answers the request; the coordinator who asked is told; the flag clears",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = scoped_event(ctx, "106-009", "11-10")
    expect_status(ask_reassignment(ctx, event_id), 201)
    [event] = db_query(f"select version from public.events where id = '{event_id}'")
    response = ctx.client.post(f"{ctx.api}/events/{event_id}/reassign", headers=lead_session(ctx).headers,
                               json={"coordinator_id": SECOND_COORDINATOR, "expected_version": event["version"]})
    expect_status(response, 200)
    [row] = db_query("select status, decided_by from public.event_reassignment_requests "
                     f"where event_id = '{event_id}'")
    expect(row == {"status": "reassigned", "decided_by": seeded_lead_id()}, f"row: {row}")
    told = db_query(f"select recipient_id from public.notifications where event_id = '{event_id}' and type = 'event_reassigned'")
    expect([t["recipient_id"] for t in told] == [COORDINATOR_ID], f"the coordinator who asked was told: {told}")
    dashboard = ctx.client.get(f"{ctx.api}{LEAD_DASHBOARD}", headers=lead_session(ctx).headers).json()
    entry = next((e for e in dashboard["active_events"] if e["event_id"] == event_id), None)
    expect(entry and entry["open_reassignment_request"] is None, f"the Lead's dashboard still flags it: {entry}")


@check("TC-REASSIGN-010", "An event with no Lead holding its scope tells every Lead", needs_db=True)
def _(ctx: Context) -> None:
    event_id = throwaway_event(ctx, "106-010", "2031-11-11 09:00+08", "2031-11-11 12:00+08")
    expect_status(ask_reassignment(ctx, event_id), 201)
    notices = db_query("select recipient_id, recipient_role::text as role from public.notifications "
                       f"where event_id = '{event_id}' and type = 'reassignment_requested'")
    leads = db_query("select profile_id from public.user_roles where role = 'event_coordinator_lead'")
    expect(leads and sorted(n["recipient_id"] for n in notices) == sorted(l["profile_id"] for l in leads)
           and all(n["role"] == "event_coordinator_lead" for n in notices), f"notices: {notices}, leads: {leads}")


@check("TC-REASSIGN-011", "Cancelling the event closes its open request", needs_db=True)
def _(ctx: Context) -> None:
    event_id = scoped_event(ctx, "106-011", "11-12", status="confirmed")
    expect_status(ask_reassignment(ctx, event_id), 201)
    cancelled = ctx.client.post(f"{ctx.api}/events/{event_id}/cancel", headers=ctx.shared("event_coordinator").headers,
                                json={"reason": "live-check: cancelled"})
    expect_status(cancelled, 200)
    [row] = db_query("select status, decision_reason from public.event_reassignment_requests "
                     f"where event_id = '{event_id}'")
    expect(row == {"status": "superseded", "decision_reason": "Closed because the event was cancelled."}, f"row: {row}")
    history = ctx.client.get(f"{ctx.api}/events/{event_id}/history", headers=ctx.shared("event_coordinator").headers).json()["entries"]
    expect(any(e["kind"] == "reassignment_request_closed" for e in history), f"history: {history}")


@check("TC-REASSIGN-019", "A Preparation event takes a request and keeps it open, and a Lead can still reassign it (QA3-3, D73)",
       needs_db=True)
def _(ctx: Context) -> None:
    event_id = scoped_event(ctx, "106-019", "11-14", status="preparation")
    expect_status(ask_reassignment(ctx, event_id), 201)
    [row] = db_query(f"select status from public.event_reassignment_requests where event_id = '{event_id}'")
    expect(row["status"] == "open", f"the request is {row['status']}")
    dashboard = ctx.client.get(f"{ctx.api}{LEAD_DASHBOARD}", headers=lead_session(ctx).headers).json()
    entry = next((e for e in dashboard["active_events"] if e["event_id"] == event_id), None)
    expect(entry and entry["open_reassignment_request"]["reason"] == REASSIGN_REASON,
           f"the Lead's dashboard has {entry}")
    # Moving a confirmed event into Preparation does not answer its request either.
    moving = scoped_event(ctx, "106-019-move", "11-14", status="confirmed")
    expect_status(ask_reassignment(ctx, moving), 201)
    db_query(f"update public.events set status = 'preparation' where id = '{moving}'")
    [row] = db_query(f"select status from public.event_reassignment_requests where event_id = '{moving}'")
    expect(row["status"] == "open", f"entering Preparation left the request {row['status']}")


@check("TC-REASSIGN-013", "Asking and declining without a token are 401", needs_db=True)
def _(ctx: Context) -> None:
    event_id = scoped_event(ctx, "106-013", "11-13")
    for path in ("reassignment-request", "reassignment-request/decline"):
        response = ctx.client.post(f"{ctx.api}/events/{event_id}/{path}", json={"reason": REASSIGN_REASON})
        expect_status(response, 401)
    expect(open_requests(event_id) == 0, "an unauthenticated request was stored")


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


def delete_throwaway_accounts(run_id: str) -> int:
    """Deletes this run's sign-up check accounts, and any an earlier run left
    (STALE_AFTER); auth.users cascades to what they own."""
    accounts = mine_or_stale("email", f"{THROWAWAY_PREFIX}{run_id}-%{THROWAWAY_DOMAIN}",
                             f"{THROWAWAY_PREFIX}%{THROWAWAY_DOMAIN}")
    return len(db_query(f"delete from auth.users where {accounts} returning email"))


def cleanup_throwaway_data(run_id: str) -> dict[str, int]:
    """Delete owned events before accounts whose registrations reference them."""
    bookings = delete_throwaway_bookings(run_id)
    venues = delete_throwaway_venues(run_id)
    accounts = delete_throwaway_accounts(run_id)
    return {"accounts": accounts, "bookings": bookings, "venues": venues}


def run_db_checks(keyword: str | None) -> list[Result]:
    results = []
    for script, cases in DB_SCRIPTS:
        if not _matches_keyword(keyword, f"{script} {cases}"):
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
        if script == "registration_waitlist_checks.sql":
            try:
                require_waitlist_migration()
            except CheckBlocked as error:
                results.append(Result(script, title, "blocked", str(error)))
                print_result(results[-1])
                continue
            except Exception as error:
                results.append(Result(script, title, "fail", str(error)))
                print_result(results[-1])
                continue
        if script == "equipment_availability_checks.sql":
            try:
                require_equipment_location_migration()
            except CheckBlocked as error:
                results.append(Result(script, title, "blocked", str(error)))
                print_result(results[-1])
                continue
            except Exception as error:
                results.append(Result(script, title, "fail", str(error)))
                print_result(results[-1])
                continue
        if script == "venue_buffer_checks.sql":
            try:
                require_venue_buffer_migration()
            except CheckBlocked as error:
                results.append(Result(script, title, "blocked", str(error)))
                print_result(results[-1])
                continue
            except Exception as error:
                results.append(Result(script, title, "fail", str(error)))
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
    parser.add_argument(
        "-k", dest="keyword", help="only checks containing this keyword; comma-separated keywords are ORed"
    )
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
                    left_over = cleanup_throwaway_data(ctx.run_id)
                    for kind, label in (
                        ("accounts", "sign-up check account"),
                        ("bookings", "booking check event"),
                        ("venues", "deactivation check venue"),
                    ):
                        if left_over[kind]:
                            print(f"  (deleted {left_over[kind]} {label}(s) left by an earlier run)")
                results += run_api_checks(ctx, args.keyword, skip_accounts=args.skip_db)
            finally:
                ctx.logout_all()
                if not args.skip_db:
                    cleanup_throwaway_data(ctx.run_id)

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
