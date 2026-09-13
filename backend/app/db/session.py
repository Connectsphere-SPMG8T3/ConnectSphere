"""Database session helpers.

ConnectSphere accesses PostgreSQL exclusively through the Supabase client
(see `app.db.supabase`), which already manages pooled HTTP connections to
PostgREST/GoTrue. This module exists as the designated seam for a future
direct-SQL session (e.g. SQLAlchemy engine) should a module require
transactional queries that PostgREST cannot express, without disturbing
existing module imports.
"""

from app.db.supabase import get_supabase_admin_client, get_supabase_anon_client

__all__ = ["get_supabase_admin_client", "get_supabase_anon_client"]
