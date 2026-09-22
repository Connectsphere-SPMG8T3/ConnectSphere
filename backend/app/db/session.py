"""Database session helpers.

ConnectSphere accesses PostgreSQL exclusively through the Supabase client
(see `app.db.supabase`), which already manages pooled HTTP connections to
PostgREST/GoTrue. This module exists as the designated seam for a future
direct-SQL session (e.g. SQLAlchemy engine) should a module require
transactional queries that PostgREST cannot express, without disturbing
existing module imports.
"""

from collections.abc import Generator
from functools import lru_cache

from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.supabase import get_supabase_admin_client, get_supabase_anon_client


@lru_cache
def get_sqlalchemy_engine():
	database_url = get_settings().database_url
	if not database_url:
		return None
	return create_engine(database_url, pool_pre_ping=True)


def get_db() -> Generator[Session, None, None]:
	engine = get_sqlalchemy_engine()
	if engine is None:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="Database connection is not configured.",
		)
	with Session(engine) as session:
		yield session

__all__ = ["get_db", "get_supabase_admin_client", "get_supabase_anon_client"]
