from functools import lru_cache

from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from app.core.config import get_settings


@lru_cache
def get_supabase_anon_client() -> Client:
    """Shared client authenticated with the publishable key (replaces the legacy anon key).

    Cached and shared by every request, so it must only be used for stateless
    calls that take the caller's token explicitly (e.g. `auth.get_claims(token)`,
    `auth.admin.sign_out(token, ...)`). Never create or refresh a session on it —
    use `create_auth_client()` for that.
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_publishable_key)


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
        options=SyncClientOptions(persist_session=False, auto_refresh_token=False),
    )


@lru_cache
def get_supabase_admin_client() -> Client:
    """Client authenticated with the secret key (replaces the legacy service_role key).

    Bypasses Row Level Security. Reserved for trusted server-side data access
    after the caller's JWT has been verified; never used for session-creating
    auth calls.
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_secret_key)
