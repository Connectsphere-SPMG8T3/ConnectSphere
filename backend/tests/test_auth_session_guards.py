"""Feature 1: what the session guards hand to Supabase and refuse, checked at the service seam.

`test_auth.py` drives these through HTTP. These tests pin the identifiers each step passes
on, so a request can never be answered with another account's profile, role or session.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from postgrest.exceptions import APIError

from app.core import security
from app.core.exceptions import InvalidCredentialsError, InvalidOrExpiredTokenError, ProfileNotFoundError
from app.modules.auth import service
from app.modules.auth.schemas import ProfileUpdateRequest, SignupRequest, UserLoginRequest

USER_ID = "a0000000-0000-4000-8000-000000000001"
SESSION_ID = "b0000000-0000-4000-8000-000000000001"
TOKEN = "issued-access-token"
EMAIL = "someone@connectsphere.dev"
SIGN_IN_SECRET = "Cs" + "1234"
PROFILE = {
    "id": USER_ID, "email": EMAIL, "full_name": "Sam Lee", "role": "event_coordinator",
    "organisation_name": "NUS", "department": "Events", "phone_number": "+6591234567",
}


def _query(data=None) -> MagicMock:
    """A PostgREST builder whose every step returns itself; the calls stay inspectable."""
    query = MagicMock()
    for step in ("select", "eq", "order", "update", "upsert", "maybe_single"):
        getattr(query, step).return_value = query
    query.execute.return_value = SimpleNamespace(data=data)
    return query


def _current_user() -> security.CurrentUser:
    return security.CurrentUser(**PROFILE, session_id=SESSION_ID, access_token=TOKEN)


def _bearer() -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=TOKEN)


class TestDecodeAccessToken:
    def test_the_callers_token_is_what_gets_verified(self, monkeypatch):
        anon = MagicMock()
        anon.auth.get_claims.return_value = {"claims": {"aud": "authenticated", "sub": USER_ID}}
        monkeypatch.setattr(security, "get_supabase_anon_client", lambda: anon)

        assert security.decode_access_token(TOKEN)["sub"] == USER_ID
        anon.auth.get_claims.assert_called_once_with(TOKEN)

    def test_no_claims_is_an_invalid_token(self, monkeypatch):
        anon = MagicMock()
        anon.auth.get_claims.return_value = None
        monkeypatch.setattr(security, "get_supabase_anon_client", lambda: anon)

        with pytest.raises(InvalidOrExpiredTokenError):
            security.decode_access_token(TOKEN)


class TestGetCurrentUser:
    @pytest.mark.parametrize(
        "claims",
        [{"sub": USER_ID}, {"session_id": SESSION_ID}, {}],
        ids=["no session", "no user", "neither"],
    )
    def test_a_token_missing_either_identifier_is_refused(self, monkeypatch, claims):
        monkeypatch.setattr(security, "decode_access_token", lambda token: claims)
        monkeypatch.setattr(security, "get_supabase_admin_client", MagicMock())

        with pytest.raises(InvalidOrExpiredTokenError):
            security.get_current_user(_bearer())

    def test_no_credentials_are_refused(self):
        with pytest.raises(InvalidOrExpiredTokenError):
            security.get_current_user(None)

    def test_the_profile_is_loaded_for_the_tokens_user_and_session(self, monkeypatch):
        decoded, loaded = [], []
        monkeypatch.setattr(
            security, "decode_access_token",
            lambda token: decoded.append(token) or {"sub": USER_ID, "session_id": SESSION_ID},
        )
        monkeypatch.setattr(security, "get_supabase_admin_client", lambda: "admin")
        monkeypatch.setattr(
            security, "load_profile_with_active_role",
            lambda client, user_id, session_id: loaded.append((client, user_id, session_id)) or PROFILE,
        )

        user = security.get_current_user(_bearer())

        assert decoded == [TOKEN]
        assert loaded == [("admin", USER_ID, SESSION_ID)]
        assert (user.session_id, user.access_token) == (SESSION_ID, TOKEN)


class TestProfileLookups:
    def test_active_role_is_scoped_to_the_session_and_its_owner(self):
        query = _query({"role": "venue_staff"})
        admin = MagicMock()
        admin.table.return_value = query

        role = security.resolve_active_role(admin, USER_ID, SESSION_ID, "event_coordinator")

        assert role == "venue_staff"
        query.select.assert_called_once_with("role")
        assert [call.args for call in query.eq.call_args_list] == [("session_id", SESSION_ID), ("profile_id", USER_ID)]

    def test_no_response_falls_back_to_the_default_role(self):
        # supabase-py returns None, not an empty result, when maybe_single finds no row.
        query = _query()
        query.execute.return_value = None
        admin = MagicMock()
        admin.table.return_value = query

        assert security.resolve_active_role(admin, USER_ID, SESSION_ID, "attendee") == "attendee"

    def test_no_response_for_a_profile_is_not_found(self):
        query = _query()
        query.execute.return_value = None
        admin = MagicMock()
        admin.table.return_value = query

        with pytest.raises(ProfileNotFoundError):
            security.load_profile(admin, USER_ID)
        query.select.assert_called_once_with("id, email, full_name, role, organisation_name, department, phone_number")

    def test_the_active_role_is_resolved_for_the_same_user_and_session(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(security, "load_profile", lambda client, user_id: PROFILE)
        monkeypatch.setattr(
            security, "resolve_active_role",
            lambda client, *, user_id, session_id, default_role: seen.update(
                user_id=user_id, session_id=session_id, default_role=default_role
            ) or "venue_staff",
        )

        profile = security.load_profile_with_active_role("admin", USER_ID, SESSION_ID)

        assert seen == {"user_id": USER_ID, "session_id": SESSION_ID, "default_role": "event_coordinator"}
        assert profile["role"] == "venue_staff"

    def test_roles_are_read_for_that_profile_in_order(self, monkeypatch):
        query = _query([{"role": "attendee"}, {"role": "venue_staff"}])
        admin = MagicMock()
        admin.table.return_value = query
        monkeypatch.setattr(service, "get_supabase_admin_client", lambda: admin)

        assert service.get_roles(USER_ID) == ["attendee", "venue_staff"]
        admin.table.assert_called_once_with("user_roles")
        query.select.assert_called_once_with("role")
        query.eq.assert_called_once_with("profile_id", USER_ID)
        query.order.assert_called_once_with("role")


class TestTokenResponse:
    @pytest.fixture()
    def issued(self, monkeypatch):
        calls = {"decoded": [], "fetched": []}
        monkeypatch.setattr(
            service, "decode_access_token",
            lambda token: calls["decoded"].append(token) or {"session_id": SESSION_ID},
        )

        def fetch(user_id, session_id):
            calls["fetched"].append((user_id, session_id))
            return SimpleNamespace(email="profile@connectsphere.dev")

        monkeypatch.setattr(service, "_fetch_profile", fetch)
        monkeypatch.setattr(service, "TokenResponse", lambda **fields: SimpleNamespace(**fields))
        monkeypatch.setattr(service, "UserResponse", lambda **fields: SimpleNamespace(**fields))
        return calls

    @staticmethod
    def _session():
        return SimpleNamespace(access_token=TOKEN, refresh_token="r", expires_in=3600)

    def test_the_session_id_comes_from_the_issued_token_and_the_profile_from_its_user(self, issued):
        response = service._token_response(self._session(), SimpleNamespace(id=USER_ID, email=EMAIL))

        assert issued == {"decoded": [TOKEN], "fetched": [(USER_ID, SESSION_ID)]}
        assert response.user.email == EMAIL

    def test_a_user_without_an_email_takes_the_profiles(self, issued):
        response = service._token_response(self._session(), SimpleNamespace(id=USER_ID, email=None))

        assert response.user.email == "profile@connectsphere.dev"

    def test_fetch_profile_uses_one_user_for_the_profile_and_its_roles(self, monkeypatch):
        loaded, roles = [], []
        monkeypatch.setattr(service, "get_supabase_admin_client", lambda: "admin")
        monkeypatch.setattr(
            service, "load_profile_with_active_role",
            lambda client, user_id, session_id: loaded.append((user_id, session_id)) or PROFILE,
        )
        monkeypatch.setattr(service, "get_roles", lambda user_id: roles.append(user_id) or ["attendee"])

        service._fetch_profile(USER_ID, SESSION_ID)

        assert loaded == [(USER_ID, SESSION_ID)]
        assert roles == [USER_ID]


class TestSignIn:
    @pytest.mark.parametrize(
        "response",
        [SimpleNamespace(session=None, user=object()), SimpleNamespace(session=object(), user=None)],
        ids=["no session", "no user"],
    )
    def test_login_without_a_whole_session_is_refused(self, monkeypatch, response):
        client = MagicMock()
        client.auth.sign_in_with_password.return_value = response
        monkeypatch.setattr(service, "create_auth_client", lambda: client)

        with pytest.raises(InvalidCredentialsError):
            service.login(UserLoginRequest(email=EMAIL, password=SIGN_IN_SECRET))

    @pytest.mark.parametrize(
        "response",
        [SimpleNamespace(session=None, user=object()), SimpleNamespace(session=object(), user=None)],
        ids=["no session", "no user"],
    )
    def test_refresh_without_a_whole_session_is_refused(self, monkeypatch, response):
        client = MagicMock()
        client.auth.refresh_session.return_value = response
        monkeypatch.setattr(service, "create_auth_client", lambda: client)

        with pytest.raises(InvalidOrExpiredTokenError):
            service.refresh("refresh-token")

    def test_login_sends_the_submitted_email_and_password(self, monkeypatch):
        client = MagicMock()
        client.auth.sign_in_with_password.return_value = SimpleNamespace(session="s", user="u")
        monkeypatch.setattr(service, "create_auth_client", lambda: client)
        monkeypatch.setattr(service, "_token_response", lambda session, user: (session, user))

        assert service.login(UserLoginRequest(email=EMAIL, password=SIGN_IN_SECRET)) == ("s", "u")
        client.auth.sign_in_with_password.assert_called_once_with({"email": EMAIL, "password": SIGN_IN_SECRET})


class TestSetActiveRole:
    @pytest.fixture()
    def switch(self, monkeypatch):
        query = _query()
        admin = MagicMock()
        admin.table.return_value = query
        calls = SimpleNamespace(query=query, roles_for=[], resolved={})
        monkeypatch.setattr(service, "get_supabase_admin_client", lambda: admin)
        monkeypatch.setattr(
            service, "get_roles",
            lambda user_id: calls.roles_for.append(user_id) or ["event_coordinator", "venue_staff"],
        )

        def resolve(client, *, user_id, session_id, default_role):
            calls.resolved = {"user_id": user_id, "session_id": session_id, "default_role": default_role}
            return "venue_staff"

        monkeypatch.setattr(service, "resolve_active_role", resolve)
        return calls

    def test_the_switch_checks_and_writes_the_callers_own_session(self, switch):
        profile = service.set_active_role(_current_user(), "venue_staff")

        assert switch.roles_for == [USER_ID]
        switch.query.upsert.assert_called_once_with(
            {"session_id": SESSION_ID, "profile_id": USER_ID, "role": "venue_staff"}
        )
        assert switch.resolved == {"user_id": USER_ID, "session_id": SESSION_ID, "default_role": "venue_staff"}
        assert profile.role == "venue_staff"

    def test_the_rest_of_the_profile_comes_back_unchanged(self, switch):
        profile = service.set_active_role(_current_user(), "venue_staff")

        assert (profile.organisation_name, profile.department, profile.phone_number) == (
            "NUS", "Events", "+6591234567",
        )

    def test_any_other_database_error_is_not_read_as_a_revoked_role(self, switch):
        switch.query.execute.side_effect = APIError({"code": "42501", "message": "denied"})

        with pytest.raises(APIError):
            service.set_active_role(_current_user(), "venue_staff")


class TestSignupAndProfileEdit:
    def test_signup_reads_back_the_account_it_created(self, monkeypatch):
        admin = MagicMock()
        admin.auth.admin.create_user.return_value = SimpleNamespace(user=SimpleNamespace(id=USER_ID))
        loaded, roles = [], []
        monkeypatch.setattr(service, "get_supabase_admin_client", lambda: admin)
        monkeypatch.setattr(service, "load_profile", lambda client, user_id: loaded.append(user_id) or PROFILE)
        monkeypatch.setattr(service, "get_roles", lambda user_id: roles.append(user_id) or ["attendee"])

        service.signup(SignupRequest(
            email=EMAIL, password=SIGN_IN_SECRET + "Aa!", full_name="Sam Lee", role="attendee",
            phone_number="+6591234567",
        ))

        assert loaded == roles == [USER_ID]

    def _edit(self, monkeypatch, execute_returns):
        query = _query()
        query.execute.return_value = execute_returns
        admin = MagicMock()
        admin.table.return_value = query
        roles = []
        monkeypatch.setattr(service, "get_supabase_admin_client", lambda: admin)
        monkeypatch.setattr(service, "get_roles", lambda user_id: roles.append(user_id) or ["attendee"])
        body = ProfileUpdateRequest(full_name="Sam Tan", phone_number="+6591234567")
        return service.update_profile(_current_user(), body), roles

    def test_an_edit_reports_the_sessions_active_role_not_the_stored_one(self, monkeypatch):
        stored = {**PROFILE, "role": "attendee"}
        profile, roles = self._edit(monkeypatch, SimpleNamespace(data=[stored]))

        assert profile.role == "event_coordinator"
        assert roles == [USER_ID]

    def test_an_edit_with_no_response_is_not_found(self, monkeypatch):
        with pytest.raises(ProfileNotFoundError):
            self._edit(monkeypatch, None)
