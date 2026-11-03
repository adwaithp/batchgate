"""Audit log API."""

MANAGER = "meera@batchgate.dev"
ANALYST = "arjun@batchgate.dev"


def test_managers_see_the_audit_log_newest_first(client, login):
    h = login(MANAGER)
    page = client.get("/api/audit?limit=5", headers=h).json()
    entries = page["entries"]
    assert len(entries) == 5
    assert entries[0]["action"] == "login" and entries[0]["actor"] == "Meera Nair"
    ids = [e["id"] for e in entries]
    assert ids == sorted(ids, reverse=True)

    older = client.get(f"/api/audit?limit=5&before={page['next_before']}", headers=h).json()
    assert max(e["id"] for e in older["entries"]) < min(ids)


def test_entries_name_and_link_what_changed(client, login):
    h = login(MANAGER)
    batches = client.get("/api/audit?kind=batch&limit=200", headers=h).json()["entries"]
    assert {e["entity_type"] for e in batches} <= {"batch", "coa"}
    checked = next(e for e in batches if e["action"] == "check_run")
    assert checked["entity_label"] and checked["link"].startswith("/batches/")
    coa = next(e for e in batches if e["entity_type"] == "coa")
    assert "COA" in coa["entity_label"]


def test_analysts_cannot_read_the_audit_log(client, login):
    assert client.get("/api/audit", headers=login(ANALYST)).status_code == 403
