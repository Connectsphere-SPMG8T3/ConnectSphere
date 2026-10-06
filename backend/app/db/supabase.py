from functools import lru_cache

import httpx
from postgrest.constants import DEFAULT_POSTGREST_CLIENT_TIMEOUT
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from app.core.config import get_settings


def create_http_client() -> httpx.Client:
    """The HTTP client every Supabase client here sends its requests through.

    HTTP/1.1, not the HTTP/2 supabase-py would build itself (DEFECTS D18). The
    shared clients below serve every request thread, and on HTTP/2 they shared
    one connection: once Supabase closed it after about two minutes idle, the
    client reused it and every request of the next page load failed together
    ("Server disconnected"). On HTTP/1.1 each request in flight has its own
    pooled connection, and an idle one that was closed is replaced.

    The timeout is postgrest-py's own default, which its client used before; auth
    calls share it (they had httpx's 5 s default).
    """
    return httpx.Client(
        http2=False,
        follow_redirects=True,
        timeout=httpx.Timeout(DEFAULT_POSTGREST_CLIENT_TIMEOUT),
    )


@lru_cache
def get_supabase_anon_client() -> Client:
    """Shared client authenticated with the publishable key (replaces the legacy anon key).

    Cached and shared by every request, so it must only be used for stateless
    calls that take the caller's token explicitly (e.g. `auth.get_claims(token)`,
    `auth.admin.sign_out(token, ...)`). Never create or refresh a session on it —
    use `create_auth_client()` for that.
    """
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_publishable_key,
        options=SyncClientOptions(httpx_client=create_http_client()),
    )


def create_auth_client() -> Client:
    """A fresh publishable-key client for one session-creating call (sign-in, refresh).

    supabase-py stores the resulting session on the client instance and, by
    default, starts a background timer that refreshes it. On a shared client
    that leaks one user's session into other requests and silently rotates
    their refresh token, so each call gets its own client with both disabled.
    """
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_publishable_key,
        options=SyncClientOptions(
            persist_session=False,
            auto_refresh_token=False,
            httpx_client=create_http_client(),
        ),
    )


@lru_cache
def get_supabase_admin_client() -> Client:
    """Client authenticated with the secret key (replaces the legacy service_role key).

    Bypasses Row Level Security. Reserved for trusted server-side data access
    after the caller's JWT has been verified; never used for session-creating
    auth calls.
    """
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_secret_key,
        options=SyncClientOptions(httpx_client=create_http_client()),
    )
