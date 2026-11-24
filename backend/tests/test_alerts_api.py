from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models import InventoryAlert, Product
from app.services import alert_service


def out_of_stock_product(db, sku="USB-003"):
    p = Product(sku=sku, name="USB-C Cable", category="Electronics", current_stock=0, reorder_point=40,
                minimum_stock=20, reorder_quantity=200, unit_cost=Decimal("2.10"))
    db.add(p)
    db.commit()
    return p


def raise_alerts(db, *products):
    for p in products:
        alert_service.check_product(db, p)
    db.commit()


def alert_id(db, product):
    return db.query(InventoryAlert).filter_by(product_id=product.id).order_by(InventoryAlert.id.desc()).first().id


# ---------- list ----------


def test_list_alerts_and_filters(client, db, product):
    usb = out_of_stock_product(db)
    raise_alerts(db, product, usb)  # WM-001 LOW_STOCK/MEDIUM, USB-003 OUT_OF_STOCK/CRITICAL

    body = client.get("/api/alerts").json()
    assert [(a["product_sku"], a["alert_type"], a["severity"], a["status"]) for a in body] == [
        ("USB-003", "OUT_OF_STOCK", "CRITICAL", "OPEN"),  # newest first
        ("WM-001", "LOW_STOCK", "MEDIUM", "OPEN"),
    ]
    assert body[0]["product_name"] == "USB-C Cable"
    assert body[0]["resolved_at"] is None

    skus = lambda params: [a["product_sku"] for a in client.get("/api/alerts", params=params).json()]
    assert skus({"alert_type": "LOW_STOCK"}) == ["WM-001"]
    assert skus({"severity": "CRITICAL"}) == ["USB-003"]
    assert skus({"product_id": product.id}) == ["WM-001"]
    assert skus({"status": "RESOLVED"}) == []
    assert skus({"limit": 1}) == ["USB-003"]

    # resolve WM-001 by restocking; unresolved_only hides it, status=RESOLVED shows it
    client.post("/api/inventory/transactions",
                json={"product_id": product.id, "transaction_type": "STOCK_IN", "quantity": 100})
    assert skus({"unresolved_only": True}) == ["USB-003"]
    assert skus({"status": "RESOLVED"}) == ["WM-001"]


def test_list_rejects_unknown_filter_values(client):
    for params in ({"status": "CLOSED"}, {"alert_type": "OVERSTOCKED"}, {"severity": "URGENT"}):
        assert client.get("/api/alerts", params=params).status_code == 422, params


# ---------- detail ----------


def test_alert_detail_includes_live_stock(client, db, product):
    raise_alerts(db, product)
    aid = alert_id(db, product)
    body = client.get(f"/api/alerts/{aid}").json()
    assert body["message"] == "Wireless Mouse (WM-001) is low on stock: 12 units, at or below reorder point 20."
    assert body["product"] == {
        "current_stock": 12, "reorder_point": 20, "minimum_stock": 10,
        "reorder_quantity": 100, "inventory_status": "LOW_STOCK", "is_active": True,
    }


def test_alert_detail_missing(client):
    res = client.get("/api/alerts/999999")
    assert res.status_code == 404
    assert res.json()["detail"] == "Alert 999999 not found"


# ---------- acknowledge ----------


def test_acknowledge_and_unacknowledge(client, db, product):
    raise_alerts(db, product)
    aid = alert_id(db, product)

    res = client.patch(f"/api/alerts/{aid}", json={"status": "ACKNOWLEDGED"})
    assert res.status_code == 200
    assert res.json()["status"] == "ACKNOWLEDGED"
    # repeating is harmless
    assert client.patch(f"/api/alerts/{aid}", json={"status": "ACKNOWLEDGED"}).json()["status"] == "ACKNOWLEDGED"
    # monitoring keeps the acknowledged alert (no duplicate)
    raise_alerts(db, product)
    assert len(client.get("/api/alerts", params={"product_id": product.id}).json()) == 1

    res = client.patch(f"/api/alerts/{aid}", json={"status": "OPEN"})
    assert res.json()["status"] == "OPEN"


def test_manual_resolve_is_rejected(client, db, product):
    raise_alerts(db, product)
    aid = alert_id(db, product)
    res = client.patch(f"/api/alerts/{aid}", json={"status": "RESOLVED"})
    assert res.status_code == 422
    assert "resolve automatically" in res.json()["detail"]
    assert client.get(f"/api/alerts/{aid}").json()["status"] == "OPEN"


def test_resolved_alert_cannot_be_changed(client, db, product):
    raise_alerts(db, product)
    aid = alert_id(db, product)
    client.post("/api/inventory/transactions",
                json={"product_id": product.id, "transaction_type": "STOCK_IN", "quantity": 100})
    for status in ("ACKNOWLEDGED", "OPEN"):
        res = client.patch(f"/api/alerts/{aid}", json={"status": status})
        assert res.status_code == 409, status
        assert res.json()["detail"] == f"Alert {aid} is already resolved"
    # resolved_at is kept, and patching RESOLVED onto a resolved alert is a harmless no-op
    detail = client.patch(f"/api/alerts/{aid}", json={"status": "RESOLVED"}).json()
    assert detail["status"] == "RESOLVED"
    assert datetime.fromisoformat(detail["resolved_at"]) > datetime.now(timezone.utc) - timedelta(minutes=1)


def test_patch_validation(client, db, product):
    raise_alerts(db, product)
    aid = alert_id(db, product)
    assert client.patch(f"/api/alerts/{aid}", json={"status": "CLOSED"}).status_code == 422
    assert client.patch(f"/api/alerts/{aid}", json={"status": "ACKNOWLEDGED", "severity": "LOW"}).status_code == 422
    assert client.patch(f"/api/alerts/{aid}", json={}).status_code == 422
    assert client.patch("/api/alerts/999999", json={"status": "ACKNOWLEDGED"}).status_code == 404
