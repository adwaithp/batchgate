import json

import pytest

from app.core.config import get_settings

ANALYST = "arjun@batchgate.dev"
MANAGER = "meera@batchgate.dev"
SALES = "sara@batchgate.dev"

PDF = b"%PDF-1.4\n% demo coa\n"


@pytest.fixture(autouse=True)
def tmp_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))


def find(client, headers, batch_number):
    batches = client.get("/api/batches", headers=headers).json()
    return next(b for b in batches if b["batch_number"] == batch_number)


def detail(client, headers, batch_number):
    b = find(client, headers, batch_number)
    return client.get(f"/api/batches/{b['id']}", headers=headers).json()


def sse(res) -> list[dict]:
    """The events of a server-sent event stream, in order."""
    return [json.loads(line[6:]) for line in res.text.splitlines() if line.startswith("data: ")]


def act(client, headers, batch_id, action, **body):
    return client.post(
        f"/api/batches/{batch_id}/actions", headers=headers, json={"action": action, **body}
    )


def test_seeded_batches_cover_every_stage(client, login):
    h = login(ANALYST)
    statuses = {
        b["batch_number"]: b["status"] for b in client.get("/api/batches", headers=h).json()
    }
    assert statuses == {
        "FC-2611-07": "on_hold",
        "FC-2611-12": "awaiting_coa",
        "MT-2610-31": "pending_approval",
        "MT-2611-04": "pending_review",
        "PO-2611-A": "pending_review",
    }


def test_filter_by_status(client, login):
    h = login(ANALYST)
    res = client.get("/api/batches?status=pending_review", headers=h).json()
    assert {b["batch_number"] for b in res} == {"MT-2611-04", "PO-2611-A"}


def test_sales_cannot_see_batches(client, login):
    assert client.get("/api/batches", headers=login(SALES)).status_code == 403


def test_held_batch_explains_itself(client, login):
    d = detail(client, login(ANALYST), "FC-2611-07")
    assert d["verdict"]["decision"] == "hold"
    assert "Insoluble matter: 0.14 % is above max 0.1 %" in d["verdict"]["summary"]
    assert d["line"]["po_number"] == "PO-1042"
    assert set(d["allowed_actions"]) == {"propose_release", "assign_line", "rerun_check"}


def test_engine_release_is_approved_by_manager_and_rolls_up_to_order(client, login):
    h = login(MANAGER)
    d = detail(client, h, "MT-2610-31")
    assert "approve_release" in d["allowed_actions"]
    res = act(client, h, d["id"], "approve_release")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "released"

    dash = client.get("/api/dashboard", headers=h).json()
    po = next(o for o in dash["recent_orders"] if o["po_number"] == "PO-1042")
    assert po["status"] == "partially_ready"
    line2 = next(ln for ln in po["lines"] if ln["line_no"] == 2)
    assert line2["ready"] is True
    assert line2["released_quantity"] == 10


def test_analyst_override_needs_a_note_and_a_manager(client, login):
    analyst, manager = login(ANALYST), login(MANAGER)
    d = detail(client, analyst, "PO-2611-A")

    assert act(client, analyst, d["id"], "propose_release").status_code == 422
    res = act(
        client,
        analyst,
        d["id"],
        "propose_release",
        note="Lab retest of assay on retained sample: 99.4 %. Within tolerance.",
    )
    assert res.json()["status"] == "pending_approval"

    assert act(client, analyst, d["id"], "approve_release").status_code == 403
    res = act(client, manager, d["id"], "approve_release")
    assert res.json()["status"] == "released"
    assert [a["action"] for a in res.json()["actions"]] == ["propose_release", "approve_release"]

    dash = client.get("/api/dashboard", headers=manager).json()
    po = next(o for o in dash["recent_orders"] if o["po_number"] == "PO-2001")
    assert po["status"] == "ready"


def test_manager_cannot_approve_own_proposal(client, login):
    h = login(MANAGER)
    d = detail(client, h, "FC-2611-07")
    act(client, h, d["id"], "propose_release", note="Concession agreed with customer.")
    res = act(client, h, d["id"], "approve_release")
    assert res.status_code == 409
    assert "another QC manager" in res.json()["detail"]


def test_unassigned_batch_gets_line_suggestions_then_assignment(client, login):
    h = login(ANALYST)
    d = detail(client, h, "MT-2611-04")
    assert d["line"] is None
    assert d["verdict"] is None
    top, other = d["suggestions"]
    assert (top["line"]["line_no"], top["decision"]) == (3, "release")
    assert (other["line"]["line_no"], other["decision"]) == (2, "hold")

    res = act(client, h, d["id"], "assign_line", line_id=top["line"]["id"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["line"]["line_no"] == 3
    assert body["status"] == "pending_approval"


def test_assigning_a_line_for_another_product_fails(client, login):
    h = login(ANALYST)
    d = detail(client, h, "MT-2611-04")
    ferric_line = detail(client, h, "FC-2611-07")["line"]["id"]
    assert act(client, h, d["id"], "assign_line", line_id=ferric_line).status_code == 422


def _options(client, h):
    return client.get("/api/catalog/options", headers=h).json()


def test_create_batch_upload_coa_and_enter_values(client, login):
    h = login(ANALYST)
    opts = _options(client, h)
    ferric = next(p for p in opts["products"] if p["name"] == "Ferric Chloride")
    factory = opts["factories"][0]
    line = next(ln for ln in opts["open_lines"] if ln["product_id"] == ferric["id"])

    res = client.post(
        "/api/batches",
        headers=h,
        json={
            "batch_number": "FC-2611-30",
            "product_id": ferric["id"],
            "factory_id": factory["id"],
            "line_id": line["id"],
            "quantity": 5,
        },
    )
    assert res.status_code == 201, res.text
    batch = res.json()
    assert batch["status"] == "awaiting_coa"

    dup = client.post(
        "/api/batches",
        headers=h,
        json={
            "batch_number": "FC-2611-30",
            "product_id": ferric["id"],
            "factory_id": factory["id"],
        },
    )
    assert dup.status_code == 409

    up = client.post(
        f"/api/batches/{batch['id']}/coas",
        headers=h,
        data={"source": "factory"},
        files={"file": ("coa.pdf", PDF, "application/pdf")},
    )
    assert up.status_code == 201, up.text
    received, last = sse(up)
    assert received["stage"] == "received"
    coa = received["batch"]["coas"][0]
    assert coa["has_file"] and coa["extraction_status"] == "pending"
    assert received["batch"]["status"] == "awaiting_coa"  # values not in yet
    assert last["stage"] == "manual"  # no API key in tests: a person types the values

    again = client.post(
        f"/api/batches/{batch['id']}/coas",
        headers=h,
        data={"source": "factory"},
        files={"file": ("coa.pdf", PDF, "application/pdf")},
    )
    assert again.status_code == 409

    params = received["batch"]["line_detail"]["spec"]["parameters"]
    values = {
        "Ferric chloride (FeCl3)": "40.4",
        "Iron (as Fe)": "13.9",
        "Free acid (as HCl)": "0.2",
        "Ferrous iron (Fe2+)": "0.1",
        "Insoluble matter": "0.04",
        "Specific gravity @ 25 °C": "1.43",
        "Appearance": "Dark brown liquid",
    }
    saved = client.put(
        f"/api/coas/{coa['id']}/data",
        headers=h,
        json={
            "product_name": "Ferric Chloride",
            "cas_number": "7705-08-0",
            "batch_number": "FC-2611-30",
            "results": [
                {
                    "name_as_written": p["name"],
                    "raw_value": values[p["name"]],
                    "unit": p["unit"],
                    "parameter_id": p["id"],
                }
                for p in params
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["status"] == "pending_review"
    assert body["verdict"]["summary"] == "Needs review: Independent lab COA not received yet."

    file_res = client.get(f"/api/coas/{coa['id']}/file", headers=h)
    assert file_res.status_code == 200
    assert file_res.content == PDF


def test_rejects_unsupported_file_type(client, login):
    h = login(ANALYST)
    b = find(client, h, "FC-2611-12")
    res = client.post(
        f"/api/batches/{b['id']}/coas",
        headers=h,
        data={"source": "factory"},
        files={"file": ("coa.docx", b"PK\x03\x04", "application/msword")},
    )
    assert res.status_code == 415


def test_new_factory_coa_resets_a_pending_approval(client, login):
    h = login(ANALYST)
    b = find(client, h, "MT-2610-31")
    res = client.post(
        f"/api/batches/{b['id']}/coas",
        headers=h,
        data={"source": "factory"},
        files={"file": ("revised.pdf", PDF + b"rev2", "application/pdf")},
    )
    body = sse(res)[0]["batch"]
    assert body["status"] == "pending_review"
    assert body["verdict"]["summary"] == "Needs review: Factory COA not received yet."
    assert sum(not c["superseded"] for c in body["coas"]) == 2


def test_closed_batches_accept_no_more_coas(client, login):
    manager = login(MANAGER)
    b = find(client, manager, "MT-2610-31")
    act(client, manager, b["id"], "approve_release")
    res = client.post(
        f"/api/batches/{b['id']}/coas",
        headers=login(ANALYST),
        data={"source": "lab"},
        files={"file": ("late.pdf", PDF + b"late", "application/pdf")},
    )
    assert res.status_code == 409


def test_lab_coa_must_come_from_a_lab(client, login):
    h = login(ANALYST)
    opts = _options(client, h)
    b = find(client, h, "FC-2611-12")
    res = client.post(
        f"/api/batches/{b['id']}/coas",
        headers=h,
        data={"source": "lab", "issuer_id": str(opts["factories"][0]["id"])},
    )
    assert res.status_code == 422


def test_dashboard_counts_follow_the_batches(client, login):
    counts = client.get("/api/dashboard", headers=login(ANALYST)).json()["batches_by_status"]
    assert counts["pending_review"] == 2
    assert counts["on_hold"] == 1
    assert counts["pending_approval"] == 1
    assert counts["awaiting_coa"] == 1


def test_check_records_which_parameter_each_row_matched(client, login):
    d = detail(client, login(ANALYST), "FC-2611-07")
    factory = next(c for c in d["coas"] if c["source"] == "factory")
    by_name = {r["name_as_written"]: r["matched_parameter_id"] for r in factory["results"]}
    params = {p["name"]: p["id"] for p in d["line_detail"]["spec"]["parameters"]}
    assert by_name["Total iron (as Fe)"] == params["Iron (as Fe)"]
    assert by_name["FeCl3 content"] == params["Ferric chloride (FeCl3)"]


def test_unchanged_recheck_does_not_add_history(client, login):
    h = login(ANALYST)
    d = detail(client, h, "FC-2611-07")
    before = len(d["history"])
    after = act(client, h, d["id"], "rerun_check").json()
    assert len(after["history"]) == before
    assert after["status"] == "on_hold"
