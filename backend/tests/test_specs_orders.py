"""Specs, orders and customers."""

from datetime import date

ANALYST = "arjun@batchgate.dev"
MANAGER = "meera@batchgate.dev"
SALES = "sara@batchgate.dev"  # manages Ridgeway Industrial Supply only

ANHYDROUS = [
    {
        "name": "Assay (as FeCl3)",
        "rule_type": "min",
        "low": 98,
        "unit": "%",
        "aliases": ["Ferric chloride", "Assay"],
    },
    {"name": "Ferrous chloride", "rule_type": "max", "high": 0.1, "unit": "%"},
    {"name": "Insolubles", "rule_type": "max", "high": 0.1, "unit": "%", "tolerance_abs": 0.02},
    {
        "name": "Appearance",
        "rule_type": "text_match",
        "expected_text": "Dark brown to black powder",
        "critical": False,
    },
]


def ref(client, h):
    """Return customer and product ids by name."""
    body = client.get("/api/reference", headers=h).json()
    customers = {c["name"]: c["id"] for c in body["customers"]}
    products = {p["name"]: p["id"] for p in body["products"]}
    return customers, products


def make_anhydrous_spec(client, h, **overrides):
    """Create an anhydrous ferric chloride spec for Ridgeway."""
    customers, products = ref(client, h)
    payload = {
        "customer_id": customers["Ridgeway Industrial Supply"],
        "product_id": products["Ferric Chloride"],
        "grade": "Anhydrous 98%",
        "parameters": ANHYDROUS,
    } | overrides
    return client.post("/api/specs", headers=h, json=payload)


def test_list_specs_shows_current_versions_with_usage(client, login):
    specs = client.get("/api/specs", headers=login(ANALYST)).json()
    assert len(specs) == 4
    fecl3 = next(s for s in specs if s["grade"] == "40% solution")
    assert fecl3["version"] == 1
    assert fecl3["open_lines"] == 1
    assert fecl3["tests"] == 7


def test_sales_sees_only_their_customers_specs(client, login):
    specs = client.get("/api/specs", headers=login(SALES)).json()
    assert {s["customer"]["name"] for s in specs} == {"Ridgeway Industrial Supply"}
    lumora = next(
        s
        for s in client.get("/api/specs", headers=login(ANALYST)).json()
        if s["customer"]["name"] == "Lumora Personal Care"
    )
    assert client.get(f"/api/specs/{lumora['id']}", headers=login(SALES)).status_code == 404


def test_spec_detail_has_parameters_and_tolerances(client, login):
    h = login(ANALYST)
    spec_id = next(
        s["id"] for s in client.get("/api/specs", headers=h).json() if s["grade"] == "40% solution"
    )
    d = client.get(f"/api/specs/{spec_id}", headers=h).json()
    free_acid = next(p for p in d["parameters"] if p["name"] == "Free acid (as HCl)")
    assert free_acid["spec_text"] == "max 0.5 %"
    assert free_acid["tolerance_abs"] == 0.05
    assert d["used_by"][0]["po_number"] == "PO-1042"
    assert d["can_edit"] is False


def test_manager_creates_a_spec(client, login):
    res = make_anhydrous_spec(client, login(MANAGER))
    assert res.status_code == 201, res.text
    d = res.json()
    assert (d["grade"], d["version"], d["status"]) == ("Anhydrous 98%", 1, "active")
    assert [p["spec_text"] for p in d["parameters"]][:2] == ["min 98 %", "max 0.1 %"]
    assert d["can_edit"] is True


def test_analyst_and_sales_cannot_create_specs(client, login):
    assert make_anhydrous_spec(client, login(ANALYST)).status_code == 403
    assert make_anhydrous_spec(client, login(SALES)).status_code == 403


def test_duplicate_spec_points_to_new_version(client, login):
    h = login(MANAGER)
    make_anhydrous_spec(client, h)
    res = make_anhydrous_spec(client, h, grade="anhydrous 98%")
    assert res.status_code == 409
    assert "new version" in res.json()["detail"]


def test_spec_validation_messages(client, login):
    h = login(MANAGER)
    cases = [
        ([], "at least one test"),
        ([{"name": "Assay", "rule_type": "min", "unit": "%"}], "enter the minimum"),
        ([{"name": "SG", "rule_type": "range", "low": 1.5, "high": 1.4}], "lower limit is above"),
        ([{"name": "Look", "rule_type": "text_match"}], "describe what the result should say"),
        (
            [
                {"name": "Assay", "rule_type": "min", "low": 1},
                {"name": "assay", "rule_type": "complies"},
            ],
            "appears twice",
        ),
        (
            [{"name": "Assay", "rule_type": "min", "low": 1, "tolerance_abs": -1}],
            "can't be negative",
        ),
    ]
    for params, message in cases:
        res = make_anhydrous_spec(client, h, parameters=params)
        assert res.status_code == 422, params
        assert message in res.json()["detail"], res.json()


def test_editing_creates_a_new_version_and_keeps_existing_lines(client, login):
    h = login(MANAGER)
    specs = client.get("/api/specs", headers=h).json()
    v1 = next(s for s in specs if s["grade"] == "40% solution")
    detail = client.get(f"/api/specs/{v1['id']}", headers=h).json()

    params = [
        {
            k: p[k]
            for k in (
                "name",
                "rule_type",
                "low",
                "high",
                "unit",
                "expected_text",
                "aliases",
                "critical",
            )
        }
        for p in detail["parameters"]
    ]
    params[4]["high"] = 0.08  # tighter insolubles limit
    res = client.post(
        f"/api/specs/{v1['id']}/versions",
        headers=h,
        json={"notes": "Customer tightened insolubles.", "parameters": params},
    )
    assert res.status_code == 201, res.text
    v2 = res.json()
    assert v2["version"] == 2
    assert [v["status"] for v in v2["versions"]] == ["active", "superseded"]
    assert v2["used_by"][0]["spec_version"] == 1  # the order keeps the agreed version

    old = client.get(f"/api/specs/{v1['id']}", headers=h).json()
    assert old["status"] == "superseded"
    assert old["current_version_id"] == v2["id"]
    assert old["can_edit"] is False
    assert (
        client.post(
            f"/api/specs/{v1['id']}/versions", headers=h, json={"parameters": params}
        ).status_code
        == 409
    )

    current = client.get("/api/specs", headers=h).json()
    assert sum(s["grade"] == "40% solution" for s in current) == 1


def test_list_orders_with_progress(client, login):
    orders = client.get("/api/orders", headers=login(ANALYST)).json()
    po = next(o for o in orders if o["po_number"] == "PO-1042")
    assert po["lines"] == 3
    assert po["quantity"] == 40
    assert po["released_quantity"] == 0
    assert po["on_hold"] == 1
    assert po["batches_in_qc"] == 2


def test_sales_sees_only_their_orders(client, login):
    h = login(SALES)
    assert [o["po_number"] for o in client.get("/api/orders", headers=h).json()] == ["PO-1042"]
    lumora = next(
        o
        for o in client.get("/api/orders", headers=login(ANALYST)).json()
        if o["po_number"] == "PO-2001"
    )
    assert client.get(f"/api/orders/{lumora['id']}", headers=h).status_code == 404


def test_order_detail_lists_batches_per_line(client, login):
    h = login(ANALYST)
    po = next(
        o for o in client.get("/api/orders", headers=h).json() if o["po_number"] == "PO-1042"
    )
    d = client.get(f"/api/orders/{po['id']}", headers=h).json()
    line1 = d["lines"][0]
    assert (line1["product"], line1["grade"], line1["spec_current"]) == (
        "Ferric Chloride",
        "40% solution",
        True,
    )
    assert {b["batch_number"]: b["status"] for b in line1["batches"]} == {
        "FC-2611-07": "on_hold",
        "FC-2611-12": "awaiting_coa",
    }
    assert line1["batches"][0]["decision"] == "hold"
    assert d["lines"][2]["batches"] == []  # line 3 waits for MT-2611-04 to be assigned


def _spec_id(client, h, customer_id, grade):
    """Return the id of a customer's current spec for a grade."""
    specs = client.get(f"/api/customers/{customer_id}/specs", headers=h).json()["specs"]
    return next(s["id"] for s in specs if s["grade"] == grade)


def test_sales_creates_an_order_for_their_customer(client, login):
    h = login(SALES)
    customers, _ = ref(client, h)
    assert list(customers) == ["Ridgeway Industrial Supply"]
    cid = customers["Ridgeway Industrial Supply"]
    res = client.post(
        "/api/orders",
        headers=h,
        json={
            "po_number": "po-1077",
            "customer_id": cid,
            "order_date": date(2026, 11, 3).isoformat(),
            "lines": [
                {"spec_id": _spec_id(client, h, cid, "78% active"), "quantity": 12},
                {"spec_id": _spec_id(client, h, cid, "40% solution"), "quantity": 8.5},
            ],
        },
    )
    assert res.status_code == 201, res.text
    d = res.json()
    assert d["po_number"] == "PO-1077"
    assert [(ln["line_no"], ln["grade"], ln["quantity"]) for ln in d["lines"]] == [
        (1, "78% active", 12),
        (2, "40% solution", 8.5),
    ]
    assert d["status"] == "open"


def test_order_rules(client, login):
    h = login(MANAGER)
    customers, _ = ref(client, h)
    ridgeway, lumora = customers["Ridgeway Industrial Supply"], customers["Lumora Personal Care"]
    ridgeway_spec = _spec_id(client, h, ridgeway, "40% solution")

    def post(**kw):
        """Post an order with the given overrides."""
        body = {"po_number": "PO-9", "customer_id": ridgeway, "order_date": "2026-11-03"}
        body |= kw
        return client.post("/api/orders", headers=h, json=body)

    assert (
        post(po_number="PO-1042", lines=[{"spec_id": ridgeway_spec, "quantity": 1}]).status_code
        == 409
    )
    wrong_customer = post(customer_id=lumora, lines=[{"spec_id": ridgeway_spec, "quantity": 1}])
    assert wrong_customer.status_code == 422
    assert "Lumora Personal Care's specs" in wrong_customer.json()["detail"]
    assert post(lines=[]).status_code == 422
    assert post(lines=[{"spec_id": ridgeway_spec, "quantity": 0}]).status_code == 422


def test_sales_cannot_order_for_other_customers(client, login):
    lumora = ref(client, login(MANAGER))[0]["Lumora Personal Care"]
    h = login(SALES)
    assert client.get(f"/api/customers/{lumora}/specs", headers=h).status_code == 404
    res = client.post(
        "/api/orders",
        headers=h,
        json={
            "po_number": "PO-5",
            "customer_id": lumora,
            "order_date": "2026-11-03",
            "lines": [{"spec_id": 1, "quantity": 1}],
        },
    )
    assert res.status_code == 422


def test_analyst_cannot_create_orders(client, login):
    h = login(ANALYST)
    res = client.post(
        "/api/orders",
        headers=h,
        json={
            "po_number": "PO-6",
            "customer_id": 1,
            "order_date": "2026-11-03",
            "lines": [{"spec_id": 1, "quantity": 1}],
        },
    )
    assert res.status_code == 403


def test_replaced_spec_cannot_be_used_on_a_new_order(client, login):
    h = login(MANAGER)
    created = make_anhydrous_spec(client, h).json()
    params = [
        {
            k: p[k]
            for k in (
                "name",
                "rule_type",
                "low",
                "high",
                "unit",
                "expected_text",
                "aliases",
                "critical",
            )
        }
        for p in created["parameters"]
    ]
    client.post(f"/api/specs/{created['id']}/versions", headers=h, json={"parameters": params})
    res = client.post(
        "/api/orders",
        headers=h,
        json={
            "po_number": "PO-7",
            "customer_id": created["customer"]["id"],
            "order_date": "2026-11-03",
            "lines": [{"spec_id": created["id"], "quantity": 2}],
        },
    )
    assert res.status_code == 422
    assert "current version" in res.json()["detail"]


def test_new_spec_and_order_let_a_batch_be_checked_against_the_right_grade(client, login):
    """A new grade spec and an order for it let a batch be checked against it."""
    h = login(MANAGER)
    spec = make_anhydrous_spec(client, h).json()
    order = client.post(
        "/api/orders",
        headers=h,
        json={
            "po_number": "PO-1090",
            "customer_id": spec["customer"]["id"],
            "order_date": "2026-11-03",
            "lines": [{"spec_id": spec["id"], "quantity": 0.5}],
        },
    ).json()
    line_id = order["lines"][0]["id"]

    opts = client.get("/api/catalog/options", headers=login(ANALYST)).json()
    assert any(ln["id"] == line_id for ln in opts["open_lines"])


NEW_CUSTOMER = {"name": "  Harbourline   Water Utility ", "country": "Canada", "industry": "Water"}


def test_sales_adds_a_customer_and_is_assigned_to_it(client, login):
    h = login(SALES)
    res = client.post("/api/customers", headers=h, json=NEW_CUSTOMER)
    assert res.status_code == 201, res.text
    c = res.json()
    assert (c["name"], c["country"], c["industry"]) == (
        "Harbourline Water Utility",
        "Canada",
        "Water",
    )

    customers, _ = ref(client, h)
    assert "Harbourline Water Utility" in customers
    me = client.get("/api/auth/me", headers=h).json()
    assert "Harbourline Water Utility" in {x["name"] for x in me["customers"]}

    # No specs yet, so no order lines are possible.
    assert client.get(f"/api/customers/{c['id']}/specs", headers=h).json()["specs"] == []
    order = client.post(
        "/api/orders",
        headers=h,
        json={
            "po_number": "HW-1",
            "customer_id": c["id"],
            "order_date": "2026-11-03",
            "lines": [],
        },
    )
    assert order.status_code == 422

    audit = client.get("/api/audit?kind=order", headers=login(MANAGER)).json()["entries"]
    assert audit[0]["action"] == "customer_added"
    assert audit[0]["entity_label"] == "Harbourline Water Utility"


def test_new_customer_gets_a_spec_then_an_order(client, login):
    m = login(MANAGER)
    cid = client.post("/api/customers", headers=m, json=NEW_CUSTOMER).json()["id"]
    spec = make_anhydrous_spec(client, m, customer_id=cid)
    assert spec.status_code == 201, spec.text
    order = client.post(
        "/api/orders",
        headers=m,
        json={
            "po_number": "HW-2",
            "customer_id": cid,
            "order_date": "2026-11-03",
            "lines": [{"spec_id": spec.json()["id"], "quantity": 20}],
        },
    )
    assert order.status_code == 201, order.text


def test_duplicate_customer_names_are_refused(client, login):
    h = login(MANAGER)
    res = client.post(
        "/api/customers", headers=h, json={"name": "ridgeway industrial supply", "country": "US"}
    )
    assert res.status_code == 409
    assert "already a customer" in res.json()["detail"]

    # A customer managed by someone else: ask an admin.
    res = client.post(
        "/api/customers",
        headers=login(SALES),
        json={"name": "Lumora Personal Care", "country": "US"},
    )
    assert res.status_code == 409
    assert "Ask an admin" in res.json()["detail"]


def test_customer_needs_name_and_country_and_analysts_cannot_add(client, login):
    m = login(MANAGER)
    assert (
        client.post("/api/customers", headers=m, json={"name": " ", "country": "US"}).status_code
        == 422
    )
    assert client.post("/api/customers", headers=m, json={"name": "X"}).status_code == 422
    assert (
        client.post("/api/customers", headers=login(ANALYST), json=NEW_CUSTOMER).status_code == 403
    )
