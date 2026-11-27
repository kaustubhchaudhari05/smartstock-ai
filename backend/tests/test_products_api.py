from decimal import Decimal

from sqlalchemy import select

from app.models import InventoryTransaction, Product


def payload(**overrides):
    data = {
        "sku": "kb-002",
        "name": "Mechanical Keyboard",
        "category": "Electronics",
        "description": "Brown switches",
        "current_stock": 85,
        "reorder_point": 25,
        "minimum_stock": 10,
        "reorder_quantity": 60,
        "unit_cost": "32.00",
    }
    data.update(overrides)
    return data


# ---------- create ----------


def test_create_product(client, db, supplier):
    res = client.post("/api/products", json=payload(supplier_id=supplier.id))
    assert res.status_code == 201
    body = res.json()
    assert body["sku"] == "KB-002"  # normalised to upper case
    assert body["unit_cost"] == "32.00"
    assert body["supplier"] == {"id": supplier.id, "name": supplier.name}
    assert body["is_active"] is True

    txns = db.scalars(select(InventoryTransaction).where(InventoryTransaction.product_id == body["id"])).all()
    assert [(t.transaction_type, t.quantity, t.reference) for t in txns] == [
        ("STOCK_IN", 85, "OPENING-BALANCE")
    ]


def test_create_product_with_zero_stock_records_no_transaction(client, db):
    res = client.post("/api/products", json=payload(current_stock=0))
    assert res.status_code == 201
    assert res.json()["supplier"] is None
    assert db.scalar(select(InventoryTransaction)) is None


def test_create_duplicate_sku_is_conflict(client, product):
    res = client.post("/api/products", json=payload(sku="wm-001"))
    assert res.status_code == 409
    assert "WM-001" in res.json()["detail"]


def test_create_with_unknown_supplier(client):
    res = client.post("/api/products", json=payload(supplier_id=999999))
    assert res.status_code == 422
    assert res.json()["detail"] == "Supplier 999999 does not exist"


def test_create_with_inactive_supplier(client, inactive_supplier):
    res = client.post("/api/products", json=payload(supplier_id=inactive_supplier.id))
    assert res.status_code == 422
    assert "inactive" in res.json()["detail"]


def test_create_minimum_stock_above_reorder_point(client):
    res = client.post("/api/products", json=payload(minimum_stock=30, reorder_point=25))
    assert res.status_code == 422
    assert "cannot exceed reorder_point" in res.json()["detail"]


def test_create_validation_errors(client):
    bad = [
        payload(current_stock=-1),
        payload(unit_cost="-0.01"),
        payload(unit_cost="1.234"),  # more than 2 decimal places
        payload(sku="bad sku!"),
        payload(name=""),
        payload(unknown_field=1),
    ]
    for body in bad:
        assert client.post("/api/products", json=body).status_code == 422, body
    missing = payload()
    del missing["reorder_point"]
    assert client.post("/api/products", json=missing).status_code == 422


# ---------- read / list ----------


def test_get_product(client, product):
    res = client.get(f"/api/products/{product.id}")
    assert res.status_code == 200
    assert res.json()["sku"] == "WM-001"
    assert res.json()["current_stock"] == 12


def test_get_missing_product(client):
    res = client.get("/api/products/999999")
    assert res.status_code == 404
    assert res.json()["detail"] == "Product 999999 not found"


def test_list_filters(client, db, product, supplier):
    db.add_all(
        [
            Product(sku="PAP-101", name="A4 Copy Paper", category="Office Supplies", reorder_point=100,
                    minimum_stock=50, reorder_quantity=300, unit_cost=Decimal("4.20")),
            Product(sku="FAX-105", name="Fax Paper", category="Office Supplies", reorder_point=0,
                    minimum_stock=0, reorder_quantity=0, unit_cost=Decimal("2.50"), is_active=False),
        ]
    )
    db.flush()

    skus = lambda res: [p["sku"] for p in res.json()]
    assert skus(client.get("/api/products")) == ["PAP-101", "WM-001"]  # sorted, active only
    assert skus(client.get("/api/products", params={"include_inactive": True})) == ["FAX-105", "PAP-101", "WM-001"]
    assert skus(client.get("/api/products", params={"search": "mouse"})) == ["WM-001"]
    assert skus(client.get("/api/products", params={"search": "pap"})) == ["PAP-101"]  # SKU match
    assert skus(client.get("/api/products", params={"category": "office supplies"})) == ["PAP-101"]
    assert skus(client.get("/api/products", params={"supplier_id": supplier.id})) == ["WM-001"]
    assert skus(client.get("/api/products", params={"limit": 1, "skip": 1})) == ["WM-001"]
    # LIKE wildcards are matched literally
    assert skus(client.get("/api/products", params={"search": "%"})) == []


# ---------- update ----------


def test_update_product(client, product):
    res = client.put(f"/api/products/{product.id}", json={"name": "Wireless Mouse Pro", "unit_cost": "9.25"})
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Wireless Mouse Pro"
    assert body["unit_cost"] == "9.25"
    assert body["reorder_point"] == 20  # untouched fields kept


def test_update_cannot_change_stock(client, product):
    res = client.put(f"/api/products/{product.id}", json={"current_stock": 500})
    assert res.status_code == 422


def test_update_clear_supplier_and_description(client, product):
    res = client.put(f"/api/products/{product.id}", json={"supplier_id": None, "description": None})
    assert res.status_code == 200
    assert res.json()["supplier"] is None


def test_update_rejects_null_for_required_field(client, product):
    assert client.put(f"/api/products/{product.id}", json={"name": None}).status_code == 422


def test_update_thresholds_checked_against_existing_values(client, product):
    # existing minimum_stock is 10
    res = client.put(f"/api/products/{product.id}", json={"reorder_point": 5})
    assert res.status_code == 422


def test_update_sku_conflict(client, db, product):
    db.add(Product(sku="KB-002", name="Keyboard", category="Electronics", reorder_point=1,
                   minimum_stock=0, reorder_quantity=1, unit_cost=Decimal("1")))
    db.flush()
    assert client.put(f"/api/products/{product.id}", json={"sku": "kb-002"}).status_code == 409
    # keeping its own SKU is fine
    assert client.put(f"/api/products/{product.id}", json={"sku": "wm-001"}).status_code == 200


def test_update_inactive_supplier_rejected(client, product, inactive_supplier):
    res = client.put(f"/api/products/{product.id}", json={"supplier_id": inactive_supplier.id})
    assert res.status_code == 422


def test_update_missing_product(client):
    assert client.put("/api/products/999999", json={"name": "X"}).status_code == 404


# ---------- deactivate ----------


def test_delete_deactivates(client, db, product):
    res = client.delete(f"/api/products/{product.id}")
    assert res.status_code == 200
    assert res.json()["is_active"] is False
    # still in the database, hidden from the default list, idempotent on repeat
    assert db.get(Product, product.id) is not None
    assert client.get("/api/products").json() == []
    assert client.delete(f"/api/products/{product.id}").status_code == 200


def test_reactivate_via_update(client, product):
    client.delete(f"/api/products/{product.id}")
    res = client.put(f"/api/products/{product.id}", json={"is_active": True})
    assert res.json()["is_active"] is True


def test_inventory_status_is_computed_on_read(client, product):
    # WM-001: 12 in stock, reorder point 20 -> LOW_STOCK
    assert client.get(f"/api/products/{product.id}").json()["inventory_status"] == "LOW_STOCK"
    client.put(f"/api/products/{product.id}", json={"reorder_point": 12})
    assert client.get(f"/api/products/{product.id}").json()["inventory_status"] == "LOW_STOCK"  # equal
    client.put(f"/api/products/{product.id}", json={"reorder_point": 11, "minimum_stock": 5})
    assert client.get(f"/api/products/{product.id}").json()["inventory_status"] == "HEALTHY"
    client.post("/api/inventory/transactions", json={
        "product_id": product.id, "transaction_type": "STOCK_OUT", "quantity": 12})
    listed = client.get("/api/products", params={"search": "WM-001"}).json()
    assert listed[0]["inventory_status"] == "OUT_OF_STOCK"
    # read-only: cannot be sent
    assert client.put(f"/api/products/{product.id}", json={"inventory_status": "HEALTHY"}).status_code == 422
