from functools import lru_cache

from supabase import Client, create_client

from app.core.config import get_settings


@lru_cache
def get_supabase_anon_client() -> Client:
    """Client authenticated with the publishable key (replaces the legacy anon key).

    Used for operations that must respect the caller's own auth context,
    such as signing in with a password (GoTrue) on behalf of an end user.
    Named for the client's *role* (public/unprivileged caller context), not
    the literal key type, so it stays accurate across Supabase's key rename.
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_publishable_key)


@lru_cache
def get_supabase_admin_client() -> Client:
    """Client authenticated with the secret key (replaces the legacy service_role key).

    Bypasses Row Level Security. Reserved for trusted server-side reads,
    such as fetching a profile by id after the caller's JWT has already
    been verified.
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_secret_key)
