# ruff: noqa: E402  (settings come from the environment, so it is set before importing the app)
"""Test setup: a fresh batchgate_test schema and a rolled-back transaction per test.

The schema is built by the migrations and dropped afterwards, so real data is never touched.
"""

import os

TEST_SCHEMA = os.environ.get("BATCHGATE_TEST_SCHEMA", "batchgate_test")
os.environ.setdefault("BATCHGATE_BCRYPT_ROUNDS", "4")  # fast hashing in tests
os.environ["ANTHROPIC_API_KEY"] = ""  # never call Claude or queue jobs; tests opt in with fakes
os.environ["BATCHGATE_DB_SCHEMA"] = TEST_SCHEMA
os.environ["BATCHGATE_CHECK_SCHEMA_ON_START"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core import migrations
from app.core.config import get_settings
from app.core.database import get_db, scratch_schema
from app.main import app
from app.seed import seed


@pytest.fixture(scope="session")
def test_engine():
    with scratch_schema(TEST_SCHEMA) as engine:
        migrations.upgrade(engine)
        yield engine


@pytest.fixture
def db_session(test_engine):
    """Yield a seeded session inside a transaction that is rolled back."""
    conn = test_engine.connect()
    outer = conn.begin()
    session = Session(
        bind=conn,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        seed(session)
        yield session
    finally:
        session.close()
        outer.rollback()
        conn.close()


@pytest.fixture
def client(db_session):
    """Yield an API test client bound to the test session."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def login(client):
    """Return a helper that signs in a demo user and returns auth headers."""

    def _login(email: str) -> dict:
        """Sign in as `email` and return the Authorization header."""
        res = client.post(
            "/api/auth/token",
            data={"username": email, "password": get_settings().demo_password},
        )
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    return _login
