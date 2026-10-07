"""DEFECTS D18: the Supabase clients talk HTTP/1.1, never one shared HTTP/2 connection.

supabase-py builds its own httpx clients with `http2=True`. Shared by every
request thread, that one connection went stale after about two minutes idle;
the client reused it and every request of the next page load failed together
with "Server disconnected". Each factory now hands supabase-py an HTTP/1.1
client, so concurrent requests use separate pooled connections and a closed
idle one is replaced. The live regression check is TC-AUTH-049 in
scripts/verify_live.py.
"""

import httpx
import pytest

from app.db import supabase as factories


def _speaks_http1_only(client: httpx.Client) -> bool:
    pool = client._transport._pool
    return pool._http1 is True and pool._http2 is False


@pytest.fixture(autouse=True)
def fresh_cached_clients():
    factories.get_supabase_admin_client.cache_clear()
    factories.get_supabase_anon_client.cache_clear()
    yield
    factories.get_supabase_admin_client.cache_clear()
    factories.get_supabase_anon_client.cache_clear()


def test_the_http_client_speaks_http1_only_with_the_database_timeout():
    client = factories.create_http_client()

    assert _speaks_http1_only(client)
    assert client.follow_redirects is True
    # postgrest-py's own default, which its http2 client used before.
    assert client.timeout == httpx.Timeout(120)


@pytest.mark.parametrize("factory", ["get_supabase_admin_client", "get_supabase_anon_client"])
def test_the_shared_clients_send_database_and_auth_calls_over_http1(factory):
    client = getattr(factories, factory)()
    http = client.options.httpx_client

    assert isinstance(http, httpx.Client)
    assert _speaks_http1_only(http)
    assert client.postgrest.session is http
    assert client.auth._http_client is http


def test_a_sign_in_client_gets_its_own_http1_client_and_still_holds_no_session():
    first = factories.create_auth_client()
    second = factories.create_auth_client()

    assert _speaks_http1_only(first.options.httpx_client)
    assert first.auth._http_client is first.options.httpx_client
    assert first.options.httpx_client is not second.options.httpx_client
    assert first.options.persist_session is False
    assert first.options.auto_refresh_token is False
