import os

os.environ.setdefault("SUPABASE_URL", "https://vuiryrzzyfecjqftwicj.supabase.co")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test-key")
os.environ.setdefault("SUPABASE_SECRET_KEY", "sb_secret_test-key")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)
