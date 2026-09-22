"""Database session helpers.

ConnectSphere accesses PostgreSQL exclusively through the Supabase client
(see `app.db.supabase`), which already manages pooled HTTP connections to
PostgREST/GoTrue. This module re-exports those client factories so modules
have one import site for data access.
"""

from app.db.supabase import get_supabase_admin_client, get_supabase_anon_client

__all__ = ["get_supabase_admin_client", "get_supabase_anon_client"]
