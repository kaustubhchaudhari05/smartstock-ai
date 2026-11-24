"""Inventory edge cases: alerts stay in sync with every change that affects stock status,
thresholds at their limits, and quantities at the edge of what the database can store."""

from decimal import Decimal

from sqlalchemy import select

from app.models import InventoryAlert, Product

PG_INT_MAX = 2_147_483_647


def alerts(db, product_id, unresolved_only=True):
    db.expire_all()
    rows = db.scalars(
        select(InventoryAlert).where(InventoryAlert.product_id == product_id).order_by(InventoryAlert.id)
    ).all()
    return [(a.alert_type, a.severity) for a in rows if not unresolved_only or a.status != "RESOLVED"]


def new_product(client, **overrides):
    body = {"sku": "EDGE-1", "name": "Edge", "category": "Test", "current_stock": 50,
            "reorder_point": 20, "minimum_stock": 10, "reorder_quantity": 100, "unit_cost": "1.00", **overrides}
    res = client.post("/api/products", json=body)
    assert res.status_code == 201, res.json()
    return res.json()["id"]


def move(client, product_id, ttype, qty):
    return client.post("/api/inventory/transactions",
                       json={"product_id": product_id, "transaction_type": ttype, "quantity": qty})


# ---------- alerts follow product changes, not only stock movements ----------


def test_creating_product_below_reorder_point_raises_alert(client, db):
    low = new_product(client, sku="LOW-1", current_stock=15)
    out = new_product(client, sku="OUT-1", current_stock=0)
    ok = new_product(client, sku="OK-1", current_stock=50)
    assert alerts(db, low) == [("LOW_STOCK", "MEDIUM")]
    assert alerts(db, out) == [("OUT_OF_STOCK", "CRITICAL")]
    assert alerts(db, ok) == []


def test_raising_reorder_point_raises_alert_and_lowering_resolves_it(client, db):
    pid = new_product(client, current_stock=50)
    client.put(f"/api/products/{pid}", json={"reorder_point": 60})
    assert alerts(db, pid) == [("LOW_STOCK", "MEDIUM")]
    client.put(f"/api/products/{pid}", json={"reorder_point": 30})
    assert alerts(db, pid) == []


def test_raising_minimum_stock_escalates_severity(client, db):
    pid = new_product(client, current_stock=15)  # LOW / MEDIUM
    client.put(f"/api/products/{pid}", json={"minimum_stock": 15})
    assert alerts(db, pid) == [("LOW_STOCK", "HIGH")]


def test_deactivating_resolves_and_reactivating_reraises(client, db):
    pid = new_product(client, current_stock=0)
    assert alerts(db, pid) == [("OUT_OF_STOCK", "CRITICAL")]
    client.delete(f"/api/products/{pid}")
    assert alerts(db, pid) == []
    client.put(f"/api/products/{pid}", json={"is_active": True})
    assert alerts(db, pid) == [("OUT_OF_STOCK", "CRITICAL")]


def test_renaming_product_refreshes_alert_message(client, db):
    pid = new_product(client, current_stock=15)
    client.put(f"/api/products/{pid}", json={"name": "Renamed"})
    db.expire_all()
    message = db.scalar(select(InventoryAlert.message).where(InventoryAlert.product_id == pid))
    assert message.startswith("Renamed (EDGE-1)")


# ---------- threshold limits ----------


def test_reorder_point_zero(client, db):
    pid = new_product(client, current_stock=1, reorder_point=0, minimum_stock=0)
    assert alerts(db, pid) == []                      # 1 > 0: healthy
    move(client, pid, "STOCK_OUT", 1)
    assert alerts(db, pid) == [("OUT_OF_STOCK", "CRITICAL")]  # 0 is always out of stock


def test_adjustment_to_exactly_zero_is_out_of_stock(client, db):
    pid = new_product(client, current_stock=5)
    res = move(client, pid, "ADJUSTMENT", -5)
    assert res.json()["current_stock"] == 0
    assert alerts(db, pid) == [("OUT_OF_STOCK", "CRITICAL")]
    assert client.get(f"/api/inventory/{pid}").json()["inventory_status"] == "OUT_OF_STOCK"


def test_stock_exactly_at_minimum_is_high_severity(client, db):
    pid = new_product(client, current_stock=11)  # LOW / MEDIUM (11 > minimum 10)
    move(client, pid, "STOCK_OUT", 1)            # 10 == minimum
    assert alerts(db, pid) == [("LOW_STOCK", "HIGH")]


def test_product_without_supplier_still_alerts(client, db):
    pid = new_product(client, current_stock=0)  # no supplier_id
    assert alerts(db, pid) == [("OUT_OF_STOCK", "CRITICAL")]


# ---------- quantities at the limits ----------


def test_oversized_quantities_rejected_by_validation(client, db):
    pid = new_product(client)
    for ttype, qty in [("STOCK_IN", 1_000_001), ("ADJUSTMENT", -1_000_001), ("STOCK_OUT", 10**12)]:
        assert move(client, pid, ttype, qty).status_code == 422, (ttype, qty)
    sale = {"product_id": pid, "quantity_sold": 1_000_001, "unit_price": "1.00"}
    assert client.post("/api/sales", json=sale).status_code == 422
    too_much_stock = {"sku": "BIG", "name": "Big", "category": "T", "current_stock": PG_INT_MAX + 1,
                      "reorder_point": 0, "minimum_stock": 0, "reorder_quantity": 0, "unit_cost": "1.00"}
    assert client.post("/api/products", json=too_much_stock).status_code == 422


def test_stock_cannot_overflow_database_integer(client, db):
    p = Product(sku="NEAR-MAX", name="Near max", category="Test", current_stock=PG_INT_MAX - 5,
                reorder_point=0, minimum_stock=0, reorder_quantity=0, unit_cost=Decimal("0.01"))
    db.add(p)
    db.commit()
    res = move(client, p.id, "STOCK_IN", 10)
    assert res.status_code == 422  # a clear business error, not a 500
    assert "exceed" in res.json()["detail"]
    assert move(client, p.id, "STOCK_IN", 5).json()["current_stock"] == PG_INT_MAX  # exactly the max is fine
