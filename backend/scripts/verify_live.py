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


API_CHECKS: list[Check] = []


def check(case_id: str, title: str, creates_accounts: bool = False):
    def register(fn: Callable[[Context], None]):
        API_CHECKS.append(Check(case_id, title, fn, creates_accounts))
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


# --- Sign-up (SCRUM-80) ----------------------------------------------------


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
                results += run_api_checks(ctx, args.keyword, skip_accounts=args.skip_db)
            finally:
                ctx.logout_all()
                if not args.skip_db:
                    delete_throwaway_accounts()

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
