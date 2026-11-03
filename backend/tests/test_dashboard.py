"""Dashboard API."""


def test_dashboard_requires_login(client):
    assert client.get("/api/dashboard").status_code == 401


def test_qc_sees_all_customers(client, login):
    body = client.get("/api/dashboard", headers=login("arjun@batchgate.dev")).json()
    assert body["scope"] == "All customers"
    assert {o["po_number"] for o in body["recent_orders"]} == {"PO-1042", "PO-2001"}
    assert body["active_specs"] == 4
    assert body["order_lines"] == 4


def test_sales_only_sees_assigned_customers(client, login):
    body = client.get("/api/dashboard", headers=login("sara@batchgate.dev")).json()
    assert body["scope"] == "Ridgeway Industrial Supply"
    assert [o["po_number"] for o in body["recent_orders"]] == ["PO-1042"]
    assert body["active_specs"] == 3


def test_same_product_on_two_lines_keeps_distinct_grades(client, login):
    body = client.get("/api/dashboard", headers=login("meera@batchgate.dev")).json()
    po = next(o for o in body["recent_orders"] if o["po_number"] == "PO-1042")
    triazine = [line for line in po["lines"] if line["product"] == "MEA Triazine"]
    assert {line["grade"] for line in triazine} == {"78% active", "40% active"}
