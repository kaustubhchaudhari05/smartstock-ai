import threading
import time
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import InventoryTransaction, Product, TransactionType
from app.services import inventory_service
from app.services.exceptions import BusinessRuleError


def move(client, product_id, ttype, qty, **extra):
    return client.post(
        "/api/inventory/transactions",
        json={"product_id": product_id, "transaction_type": ttype, "quantity": qty, **extra},
    )


# ---------- recording movements ----------


@pytest.mark.parametrize(
    "ttype, qty, expected_stock, expected_change",
    [
        ("STOCK_IN", 50, 62, 50),
        ("STOCK_OUT", 5, 7, -5),
        ("RETURN", 2, 14, 2),
        ("ADJUSTMENT", -3, 9, -3),
        ("ADJUSTMENT", 4, 16, 4),
    ],
)
def test_movement_updates_stock(client, db, product, ttype, qty, expected_stock, expected_change):
    res = move(client, product.id, ttype, qty, reference="REF-1", notes="test")
    assert res.status_code == 201, res.json()
    body = res.json()
    assert body["previous_stock"] == 12
    assert body["current_stock"] == expected_stock
    assert body["transaction"]["stock_change"] == expected_change
    assert body["transaction"]["product_sku"] == "WM-001"
    db.expire_all()
    assert db.get(Product, product.id).current_stock == expected_stock


def test_stock_out_cannot_go_negative(client, db, product):
    res = move(client, product.id, "STOCK_OUT", 13)
    assert res.status_code == 422
    assert "Insufficient stock for WM-001: 12 available" in res.json()["detail"]
    db.expire_all()
    assert db.get(Product, product.id).current_stock == 12
    assert db.scalar(select(InventoryTransaction)) is None  # nothing recorded


def test_negative_adjustment_cannot_go_negative(client, product):
    assert move(client, product.id, "ADJUSTMENT", -13).status_code == 422
    assert move(client, product.id, "ADJUSTMENT", -12).json()["current_stock"] == 0  # exactly zero is fine


def test_quantity_validation(client, product):
    for ttype, qty in [("STOCK_IN", 0), ("STOCK_IN", -5), ("STOCK_OUT", -1), ("RETURN", -2), ("ADJUSTMENT", 0)]:
        assert move(client, product.id, ttype, qty).status_code == 422, (ttype, qty)
    assert move(client, product.id, "THEFT", 1).status_code == 422
    assert move(client, product.id, "STOCK_IN", 1, unknown=1).status_code == 422


def test_movement_unknown_product(client):
    res = move(client, 999999, "STOCK_IN", 1)
    assert res.status_code == 404


def test_movement_on_inactive_product(client, product):
    client.delete(f"/api/products/{product.id}")
    res = move(client, product.id, "STOCK_IN", 10)
    assert res.status_code == 422
    assert "inactive" in res.json()["detail"]


# ---------- history ----------


def test_transaction_history_filters(client, product):
    move(client, product.id, "STOCK_IN", 50, reference="PO-1")
    move(client, product.id, "STOCK_OUT", 5)
    move(client, product.id, "ADJUSTMENT", -1)

    all_txns = client.get("/api/inventory/transactions").json()
    assert [t["transaction_type"] for t in all_txns] == ["ADJUSTMENT", "STOCK_OUT", "STOCK_IN"]  # newest first

    by_type = client.get("/api/inventory/transactions", params={"transaction_type": "STOCK_IN"}).json()
    assert [t["reference"] for t in by_type] == ["PO-1"]

    by_product = client.get("/api/inventory/transactions", params={"product_id": product.id, "limit": 2}).json()
    assert len(by_product) == 2

    future = client.get("/api/inventory/transactions", params={"date_from": "2999-01-01T00:00:00Z"}).json()
    assert future == []
    assert client.get("/api/inventory/transactions", params={"transaction_type": "BAD"}).status_code == 422


# ---------- overview & detail ----------


def test_overview(client, db, product, supplier):
    db.add_all(
        [
            Product(sku="PAP-101", name="Paper", category="Office Supplies", current_stock=220,
                    reorder_point=100, minimum_stock=50, reorder_quantity=300, unit_cost=Decimal("4.20")),
            Product(sku="OLD-1", name="Old", category="Office Supplies", current_stock=7,
                    reorder_point=0, minimum_stock=0, reorder_quantity=0, unit_cost=Decimal("1.00"), is_active=False),
        ]
    )
    db.commit()
    move(client, product.id, "STOCK_IN", 3)  # WM-001 -> 15 units

    res = client.get("/api/inventory")
    assert res.status_code == 200
    body = res.json()
    # 15 x 8.50 = 127.50 ; 220 x 4.20 = 924.00
    assert body["summary"] == {
        "total_products": 2,
        "total_units": 235,
        "total_stock_value": "1051.50",
        "healthy_count": 1,
        "low_stock_count": 1,
        "out_of_stock_count": 0,
        "reorder_needed_count": 1,
        "replenishment_cost": "850.00",  # WM-001: reorder 100 x 8.50
    }
    wm = next(i for i in body["items"] if i["sku"] == "WM-001")
    assert wm["stock_value"] == "127.50"
    assert wm["inventory_status"] == "LOW_STOCK"  # 15 <= reorder point 20
    assert wm["last_stock_update"] is not None
    paper = next(i for i in body["items"] if i["sku"] == "PAP-101")
    assert paper["last_stock_update"] is None  # no movements recorded
    assert paper["inventory_status"] == "HEALTHY"

    office = client.get("/api/inventory", params={"category": "office supplies", "include_inactive": True}).json()
    assert office["summary"]["total_products"] == 2
    assert office["summary"]["total_stock_value"] == "931.00"


def test_product_inventory_detail(client, product):
    move(client, product.id, "STOCK_IN", 10)
    move(client, product.id, "STOCK_OUT", 4)
    res = client.get(f"/api/inventory/{product.id}")
    assert res.status_code == 200
    body = res.json()
    assert body["current_stock"] == 18
    assert body["stock_value"] == "153.00"
    assert [t["stock_change"] for t in body["recent_transactions"]] == [-4, 10]


def test_inventory_analytics_by_category(client, db, product):
    """product fixture: WM-001, Electronics, 12 units (LOW), reorder 100 x 8.50."""
    def add(sku, category, stock, rp, rq, cost, active=True):
        db.add(Product(sku=sku, name=sku, category=category, current_stock=stock, reorder_point=rp,
                       minimum_stock=0, reorder_quantity=rq, unit_cost=Decimal(cost), is_active=active))

    add("USB-003", "Electronics", 0, 40, 200, "2.10")           # OUT: 200 x 2.10 = 420.00
    add("KB-002", "Electronics", 85, 25, 60, "32.00")           # HEALTHY
    add("PEN-102", "Office Supplies", 35, 40, 150, "3.10")      # LOW: 150 x 3.10 = 465.00
    add("FAX-105", "Office Supplies", 0, 5, 10, "2.50", False)  # inactive OUT: never in replenishment
    db.commit()

    body = client.get("/api/inventory").json()
    s = body["summary"]
    assert (s["total_products"], s["healthy_count"], s["low_stock_count"], s["out_of_stock_count"]) == (4, 1, 2, 1)
    assert s["reorder_needed_count"] == 3
    assert s["replenishment_cost"] == "1735.00"  # 850.00 + 420.00 + 465.00

    cats = {c["category"]: c for c in body["categories"]}
    assert list(cats) == ["Electronics", "Office Supplies"]  # sorted
    e = cats["Electronics"]
    assert (e["total_products"], e["total_units"], e["total_stock_value"]) == (3, 97, "2822.00")  # 102.00 + 0 + 2720.00
    assert (e["reorder_needed_count"], e["replenishment_cost"]) == (2, "1270.00")
    assert cats["Office Supplies"]["replenishment_cost"] == "465.00"

    # inactive products: counted by status when included, but never need reordering
    with_inactive = client.get("/api/inventory", params={"include_inactive": True}).json()["summary"]
    assert (with_inactive["total_products"], with_inactive["out_of_stock_count"]) == (5, 2)
    assert (with_inactive["reorder_needed_count"], with_inactive["replenishment_cost"]) == (3, "1735.00")

    # category filter narrows both summary and breakdown
    office = client.get("/api/inventory", params={"category": "office supplies"}).json()
    assert [c["category"] for c in office["categories"]] == ["Office Supplies"]
    assert office["summary"]["replenishment_cost"] == "465.00"


def test_analytics_on_empty_inventory(client):
    body = client.get("/api/inventory").json()
    assert body["categories"] == [] and body["items"] == []
    assert body["summary"]["total_stock_value"] == "0.00"
    assert body["summary"]["replenishment_cost"] == "0.00"


def test_status_follows_stock_movements(client, product):
    """Status is recalculated from current stock on every read (12, reorder point 20)."""
    status = lambda: client.get(f"/api/inventory/{product.id}").json()["inventory_status"]
    assert status() == "LOW_STOCK"
    move(client, product.id, "STOCK_IN", 9)  # 21
    assert status() == "HEALTHY"
    move(client, product.id, "STOCK_OUT", 1)  # 20: boundary
    assert status() == "LOW_STOCK"
    move(client, product.id, "STOCK_OUT", 20)  # 0
    assert status() == "OUT_OF_STOCK"
    summary = client.get("/api/inventory").json()["summary"]
    assert (summary["low_stock_count"], summary["out_of_stock_count"]) == (0, 1)


def test_product_inventory_detail_missing(client):
    assert client.get("/api/inventory/999999").status_code == 404


# ---------- concurrency (real committed transactions, cleaned up afterwards) ----------


def test_concurrent_stock_out_is_serialised(engine):
    """Two sessions each try to take 8 of 10 units. The row lock makes the second wait,
    then see the committed stock (2) and fail, instead of both succeeding."""
    with Session(engine) as setup:
        p = Product(sku="CONC-1", name="Concurrency", category="Test", current_stock=10,
                    reorder_point=0, minimum_stock=0, reorder_quantity=0, unit_cost=Decimal("1"))
        setup.add(p)
        setup.commit()
        pid = p.id

    second_result: dict = {}

    def second_session():
        with Session(engine) as s2:
            try:
                inventory_service.apply_movement(
                    s2, product_id=pid, transaction_type=TransactionType.STOCK_OUT, quantity=8
                )
                s2.commit()
                second_result["outcome"] = "succeeded"
            except BusinessRuleError as exc:
                s2.rollback()
                second_result["outcome"] = str(exc)

    try:
        with Session(engine) as s1:
            inventory_service.apply_movement(
                s1, product_id=pid, transaction_type=TransactionType.STOCK_OUT, quantity=8
            )
            worker = threading.Thread(target=second_session)
            worker.start()
            time.sleep(0.5)
            assert worker.is_alive(), "second session should be blocked by the row lock"
            s1.commit()
        worker.join(timeout=10)

        assert "Insufficient stock for CONC-1: 2 available" in second_result["outcome"]
        with Session(engine) as check:
            assert check.get(Product, pid).current_stock == 2
            count = len(check.scalars(select(InventoryTransaction).where(InventoryTransaction.product_id == pid)).all())
            assert count == 1
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(InventoryTransaction).where(InventoryTransaction.product_id == pid))
            cleanup.execute(delete(Product).where(Product.id == pid))
            cleanup.commit()
