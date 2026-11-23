from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import InventoryTransaction, Product, Sale


def sell(client, product_id, qty, price="15.99", **extra):
    return client.post(
        "/api/sales", json={"product_id": product_id, "quantity_sold": qty, "unit_price": price, **extra}
    )


# ---------- recording sales ----------


def test_record_sale_deducts_stock_atomically(client, db, product):
    res = sell(client, product.id, 3, reference="SO-1")
    assert res.status_code == 201, res.json()
    body = res.json()
    assert body["previous_stock"] == 12
    assert body["current_stock"] == 9
    sale = body["sale"]
    assert sale["product_sku"] == "WM-001"
    assert sale["unit_price"] == "15.99"
    assert sale["total_amount"] == "47.97"  # 3 x 15.99
    assert sale["reference"] == "SO-1"

    db.expire_all()
    assert db.get(Product, product.id).current_stock == 9
    txn = db.get(InventoryTransaction, body["inventory_transaction_id"])
    assert (txn.transaction_type, txn.quantity, txn.reference, txn.notes) == (
        "STOCK_OUT", 3, "SO-1", f"Sale #{sale['id']}"
    )


def test_sale_defaults_to_now(client, product):
    before = datetime.now(timezone.utc)
    sale_date = datetime.fromisoformat(sell(client, product.id, 1).json()["sale"]["sale_date"])
    assert before - timedelta(seconds=5) <= sale_date <= datetime.now(timezone.utc) + timedelta(seconds=5)


def test_back_dated_sale(client, product):
    when = (datetime.now(timezone.utc) - timedelta(days=3)).replace(microsecond=0)
    res = sell(client, product.id, 1, sale_date=when.isoformat())
    assert res.status_code == 201
    assert datetime.fromisoformat(res.json()["sale"]["sale_date"]) == when


def test_insufficient_stock_records_nothing(client, db, product):
    res = sell(client, product.id, 13)
    assert res.status_code == 422
    assert "Insufficient stock for WM-001: 12 available" in res.json()["detail"]
    db.expire_all()
    assert db.get(Product, product.id).current_stock == 12
    assert db.scalar(select(Sale)) is None
    assert db.scalar(select(InventoryTransaction)) is None


def test_sale_of_entire_stock(client, product):
    assert sell(client, product.id, 12).json()["current_stock"] == 0
    assert sell(client, product.id, 1).status_code == 422


def test_sale_on_inactive_product(client, product):
    client.delete(f"/api/products/{product.id}")
    assert sell(client, product.id, 1).status_code == 422


def test_sale_unknown_product(client):
    assert sell(client, 999999, 1).status_code == 404


def test_sale_validation(client, product):
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    bad = [
        {"quantity_sold": 0},
        {"quantity_sold": -1},
        {"unit_price": "-1.00"},
        {"unit_price": "1.999"},
        {"sale_date": future},
        {"sale_date": "2026-11-01T10:00:00"},  # no timezone
        {"unknown": 1},
    ]
    for override in bad:
        body = {"product_id": product.id, "quantity_sold": 1, "unit_price": "15.99", **override}
        assert client.post("/api/sales", json=body).status_code == 422, override


# ---------- listing ----------


def test_list_sales_filters(client, db, product):
    other = Product(sku="KB-002", name="Keyboard", category="Electronics", current_stock=50,
                    reorder_point=10, minimum_stock=5, reorder_quantity=20, unit_cost=Decimal("30"))
    db.add(other)
    db.commit()
    now = datetime.now(timezone.utc)
    sell(client, product.id, 1, sale_date=(now - timedelta(days=10)).isoformat())
    sell(client, product.id, 2, sale_date=(now - timedelta(days=2)).isoformat())
    sell(client, other.id, 3, price="59.99")

    qtys = lambda res: [s["quantity_sold"] for s in res.json()]
    assert qtys(client.get("/api/sales")) == [3, 2, 1]  # newest sale_date first
    assert qtys(client.get("/api/sales", params={"product_id": product.id})) == [2, 1]
    week_ago = (now - timedelta(days=7)).isoformat()
    assert qtys(client.get("/api/sales", params={"date_from": week_ago})) == [3, 2]
    assert qtys(client.get("/api/sales", params={"date_to": week_ago})) == [1]
    assert qtys(client.get("/api/sales", params={"limit": 1, "skip": 1})) == [2]
    assert client.get("/api/sales").json()[0]["total_amount"] == "179.97"
