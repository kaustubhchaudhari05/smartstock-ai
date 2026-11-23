from app.models import Supplier


def payload(**overrides):
    data = {
        "name": "PackRight Packaging",
        "email": "Orders@PackRight.example",
        "phone": "+1-555-0103",
        "address": "9 Industrial Park Rd",
        "lead_time_days": 10,
    }
    data.update(overrides)
    return data


# ---------- create ----------


def test_create_supplier(client):
    res = client.post("/api/suppliers", json=payload())
    assert res.status_code == 201
    body = res.json()
    assert body["id"] > 0
    assert body["email"] == "orders@packright.example"  # normalised to lower case
    assert body["is_active"] is True
    assert body["lead_time_days"] == 10


def test_create_minimal_supplier(client):
    res = client.post("/api/suppliers", json={"name": "Bare Co", "email": "a@b.example", "lead_time_days": 0})
    assert res.status_code == 201
    assert res.json()["phone"] is None
    assert res.json()["address"] is None


def test_create_duplicate_name_is_conflict(client, supplier):
    res = client.post("/api/suppliers", json=payload(name="  acme peripherals "))
    assert res.status_code == 409
    assert "Acme Peripherals" in res.json()["detail"]


def test_create_validation_errors(client):
    bad = [
        payload(email="not-an-email"),
        payload(email="a@b"),
        payload(lead_time_days=-1),
        payload(lead_time_days=366),
        payload(name=""),
        payload(is_active=False),  # not accepted on create
        payload(unknown=1),
    ]
    for body in bad:
        assert client.post("/api/suppliers", json=body).status_code == 422, body


# ---------- list ----------


def test_list_suppliers(client, db, supplier, inactive_supplier):
    db.add(Supplier(name="Zeta Metals", email="z@zeta.example", lead_time_days=21))
    db.flush()
    names = lambda res: [s["name"] for s in res.json()]

    assert names(client.get("/api/suppliers")) == ["Acme Peripherals", "Zeta Metals"]
    assert names(client.get("/api/suppliers", params={"include_inactive": True})) == [
        "Acme Peripherals", "Old Supplier", "Zeta Metals"
    ]
    assert names(client.get("/api/suppliers", params={"search": "zeta"})) == ["Zeta Metals"]
    assert names(client.get("/api/suppliers", params={"search": "_"})) == []  # literal match
    assert names(client.get("/api/suppliers", params={"limit": 1, "skip": 1})) == ["Zeta Metals"]


# ---------- update ----------


def test_update_supplier(client, supplier):
    res = client.put(f"/api/suppliers/{supplier.id}", json={"lead_time_days": 3, "phone": "+1-555-9999"})
    assert res.status_code == 200
    body = res.json()
    assert body["lead_time_days"] == 3
    assert body["phone"] == "+1-555-9999"
    assert body["name"] == "Acme Peripherals"  # untouched


def test_update_clear_optional_fields(client, supplier):
    res = client.put(f"/api/suppliers/{supplier.id}", json={"phone": None, "address": None})
    assert res.status_code == 200
    assert res.json()["phone"] is None


def test_update_rejects_null_for_required_field(client, supplier):
    assert client.put(f"/api/suppliers/{supplier.id}", json={"email": None}).status_code == 422


def test_update_name_conflict(client, supplier, inactive_supplier):
    res = client.put(f"/api/suppliers/{supplier.id}", json={"name": "OLD SUPPLIER"})
    assert res.status_code == 409
    # renaming to its own name (different case) is fine
    assert client.put(f"/api/suppliers/{supplier.id}", json={"name": "ACME Peripherals"}).status_code == 200


def test_deactivate_and_reactivate(client, supplier, product):
    res = client.put(f"/api/suppliers/{supplier.id}", json={"is_active": False})
    assert res.status_code == 200
    assert res.json()["is_active"] is False
    assert client.get("/api/suppliers").json() == []
    # existing products keep their supplier link ...
    assert client.get(f"/api/products/{product.id}").json()["supplier_id"] == supplier.id
    # ... but the inactive supplier cannot be assigned to new products
    new = {"sku": "X-1", "name": "X", "category": "C", "reorder_point": 1, "minimum_stock": 0,
           "reorder_quantity": 1, "unit_cost": "1.00", "supplier_id": supplier.id}
    assert client.post("/api/products", json=new).status_code == 422

    assert client.put(f"/api/suppliers/{supplier.id}", json={"is_active": True}).json()["is_active"] is True


def test_update_missing_supplier(client):
    res = client.put("/api/suppliers/999999", json={"name": "X"})
    assert res.status_code == 404
    assert res.json()["detail"] == "Supplier 999999 not found"
