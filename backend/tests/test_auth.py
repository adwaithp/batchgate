"""Sign-in, demo accounts, permissions and the startup schema check."""

from sqlalchemy import select

from app.models import AuditLog


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_login_success_returns_token_and_audits(client, db_session):
    res = client.post(
        "/api/auth/token", data={"username": "Arjun@BatchGate.dev ", "password": "demo1234"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert db_session.scalar(select(AuditLog).where(AuditLog.action == "login")) is not None


def test_login_wrong_password(client):
    res = client.post(
        "/api/auth/token", data={"username": "arjun@batchgate.dev", "password": "nope"}
    )
    assert res.status_code == 401


def test_login_unknown_user(client):
    res = client.post(
        "/api/auth/token", data={"username": "ghost@batchgate.dev", "password": "demo1234"}
    )
    assert res.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    bad = {"Authorization": "Bearer not-a-jwt"}
    assert client.get("/api/auth/me", headers=bad).status_code == 401


def test_me_returns_role_and_permissions(client, login):
    me = client.get("/api/auth/me", headers=login("meera@batchgate.dev")).json()
    assert me["role"] == "qc_manager"
    assert me["role_label"] == "QC Manager"
    assert "batch:approve_release" in me["permissions"]


def test_analyst_cannot_approve_release(client, login):
    me = client.get("/api/auth/me", headers=login("arjun@batchgate.dev")).json()
    assert "batch:propose_release" in me["permissions"]
    assert "batch:approve_release" not in me["permissions"]


def test_demo_accounts_listed(client):
    body = client.get("/api/auth/demo-accounts").json()
    assert body["enabled"] is True
    roles = {a["role"] for a in body["accounts"]}
    assert roles == {"admin", "qc_manager", "qc_analyst", "sales"}


def test_a_database_not_built_by_migrations_is_reported_clearly(monkeypatch):
    import pytest
    from sqlalchemy import text

    from app.core import database
    from app.core.config import get_settings

    with database.scratch_schema("batchgate_old_test") as old:
        with old.begin() as conn:
            conn.execute(text("CREATE TABLE batches (id integer primary key)"))
        monkeypatch.setattr(database, "engine", old)
        monkeypatch.setattr(get_settings(), "check_schema_on_start", True)
        with pytest.raises(database.SchemaOutOfDateError, match="seed --reset"):
            database.check_schema()
