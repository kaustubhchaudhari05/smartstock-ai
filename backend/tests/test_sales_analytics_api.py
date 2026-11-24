from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models import Product, Sale


def add_sales(db, product, *, per_day, days, hours_ago_start=1):
    now = datetime.now(timezone.utc)
    for i in range(days):
        db.add(Sale(product_id=product.id, quantity_sold=per_day, unit_price=Decimal("1.00"),
                    sale_date=now - timedelta(hours=hours_ago_start + 24 * i)))
    db.commit()


def test_analytics_for_all_products(client, db, product):
    other = Product(sku="SRV-304", name="Servo", category="Components", current_stock=50, reorder_point=15,
                    minimum_stock=8, reorder_quantity=50, unit_cost=Decimal("3.20"))
    db.add(other)
    db.commit()
    add_sales(db, product, per_day=5, days=30)   # WM-001: 150 in 30d, steady

    res = client.get("/api/sales/analytics")
    assert res.status_code == 200
    body = res.json()
    assert body["definitions"] == {
        "short_window_days": 7, "long_window_days": 30, "trend_threshold": "0.15",
        "windows": "rolling, ending at as_of",
    }
    assert body["summary"] == {
        "products": 2, "units_sold_7d": 35, "units_sold_30d": 150,
        "increasing": 0, "stable": 1, "decreasing": 0, "insufficient_data": 1,
    }
    srv, wm = body["products"]  # sorted by SKU
    assert (wm["sku"], wm["average_daily_sales"], wm["days_remaining"], wm["trend"]) == ("WM-001", "5.00", "2.4", "STABLE")
    assert wm["daily_sales"] is None
    assert (srv["sku"], srv["days_remaining"], srv["trend"]) == ("SRV-304", None, "INSUFFICIENT_DATA")
    datetime.fromisoformat(body["as_of"])  # valid timestamp


def test_analytics_for_one_product_includes_daily_series(client, db, product):
    add_sales(db, product, per_day=2, days=10)
    body = client.get("/api/sales/analytics", params={"product_id": product.id}).json()
    assert body["summary"]["products"] == 1
    (m,) = body["products"]
    assert m["sku"] == "WM-001"
    assert len(m["daily_sales"]) == 30
    assert sum(d["units_sold"] for d in m["daily_sales"]) == 20
    assert m["daily_sales"][-1]["date"] == datetime.now(timezone.utc).date().isoformat()


def test_recorded_sale_counts_immediately(client, db, product):
    client.post("/api/sales", json={"product_id": product.id, "quantity_sold": 3, "unit_price": "15.99"})
    (m,) = client.get("/api/sales/analytics", params={"product_id": product.id}).json()["products"]
    assert (m["units_sold_7d"], m["units_sold_30d"], m["current_stock"]) == (3, 3, 9)
    assert m["trend"] == "INCREASING"  # all 30-day sales happened this week


def test_inactive_products(client, db, product):
    client.delete(f"/api/products/{product.id}")
    assert client.get("/api/sales/analytics").json()["products"] == []
    assert len(client.get("/api/sales/analytics", params={"include_inactive": True}).json()["products"]) == 1
    # explicitly requested by id: returned even when inactive
    assert client.get("/api/sales/analytics", params={"product_id": product.id}).status_code == 200


def test_unknown_product(client):
    res = client.get("/api/sales/analytics", params={"product_id": 999999})
    assert res.status_code == 404
    assert res.json()["detail"] == "Product 999999 not found"
