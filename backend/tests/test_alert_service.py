import threading
import time
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AIRecommendation, InventoryAlert, InventoryTransaction, Product
from app.services import alert_service


def make_product(db, sku="P-1", stock=50, reorder_point=20, minimum_stock=10, active=True):
    p = Product(sku=sku, name=f"Product {sku}", category="Test", current_stock=stock,
                reorder_point=reorder_point, minimum_stock=minimum_stock, reorder_quantity=100,
                unit_cost=Decimal("1.00"), is_active=active)
    db.add(p)
    db.commit()
    return p


def alerts(db, product_id, unresolved_only=False):
    stmt = select(InventoryAlert).where(InventoryAlert.product_id == product_id).order_by(InventoryAlert.id)
    rows = db.scalars(stmt).all()
    return [a for a in rows if a.status != "RESOLVED"] if unresolved_only else rows


def summary_of(db, product_id):
    return [(a.alert_type, a.severity, a.status) for a in alerts(db, product_id)]


# ---------- desired state (pure) ----------


def test_desired_alert_rules(db):
    p = make_product(db, stock=50)
    assert alert_service.desired_alert(p) is None                     # healthy
    p.current_stock = 20
    assert alert_service.desired_alert(p)[:2] == ("LOW_STOCK", "MEDIUM")   # = reorder point
    p.current_stock = 10
    assert alert_service.desired_alert(p)[:2] == ("LOW_STOCK", "HIGH")    # = minimum stock
    p.current_stock = 0
    assert alert_service.desired_alert(p)[:2] == ("OUT_OF_STOCK", "CRITICAL")
    p.is_active = False
    assert alert_service.desired_alert(p) is None                     # inactive: never alert


def test_alert_message_uses_real_figures(db):
    p = make_product(db, sku="WM-001", stock=12)
    p.name = "Wireless Mouse"
    _, _, message = alert_service.desired_alert(p)
    assert message == "Wireless Mouse (WM-001) is low on stock: 12 units, at or below reorder point 20."


# ---------- check_product lifecycle ----------


def test_healthy_product_gets_no_alert(db):
    p = make_product(db, stock=50)
    result = alert_service.check_product(db, p)
    assert result.status == "HEALTHY"
    assert alerts(db, p.id) == []


def test_low_stock_creates_one_alert_and_is_idempotent(db):
    p = make_product(db, stock=15)
    first = alert_service.check_product(db, p)
    assert len(first.created) == 1
    second = alert_service.check_product(db, p)
    assert (second.created, second.updated, second.resolved) == ([], [], [])
    assert summary_of(db, p.id) == [("LOW_STOCK", "MEDIUM", "OPEN")]


def test_severity_escalates_on_existing_alert(db):
    p = make_product(db, stock=15)
    alert_service.check_product(db, p)
    p.current_stock = 8  # below minimum stock 10
    result = alert_service.check_product(db, p)
    assert len(result.updated) == 1 and result.created == []
    assert summary_of(db, p.id) == [("LOW_STOCK", "HIGH", "OPEN")]


def test_low_to_out_of_stock_resolves_low_and_opens_out(db):
    p = make_product(db, stock=15)
    alert_service.check_product(db, p)
    p.current_stock = 0
    result = alert_service.check_product(db, p)
    assert len(result.created) == 1 and len(result.resolved) == 1
    assert summary_of(db, p.id) == [("LOW_STOCK", "MEDIUM", "RESOLVED"), ("OUT_OF_STOCK", "CRITICAL", "OPEN")]
    assert alerts(db, p.id)[0].resolved_at is not None


def test_recovery_resolves_alerts(db):
    p = make_product(db, stock=0)
    alert_service.check_product(db, p)
    p.current_stock = 100
    result = alert_service.check_product(db, p)
    assert result.status == "HEALTHY" and len(result.resolved) == 1
    assert alerts(db, p.id, unresolved_only=True) == []


def test_new_alert_after_resolution(db):
    p = make_product(db, stock=15)
    alert_service.check_product(db, p)
    p.current_stock = 100
    alert_service.check_product(db, p)
    p.current_stock = 5
    alert_service.check_product(db, p)
    assert summary_of(db, p.id) == [("LOW_STOCK", "MEDIUM", "RESOLVED"), ("LOW_STOCK", "HIGH", "OPEN")]


def test_acknowledged_alert_is_kept_not_duplicated(db):
    p = make_product(db, stock=15)
    alert_service.check_product(db, p)
    alerts(db, p.id)[0].status = "ACKNOWLEDGED"
    db.commit()
    result = alert_service.check_product(db, p)
    assert result.created == []
    assert summary_of(db, p.id) == [("LOW_STOCK", "MEDIUM", "ACKNOWLEDGED")]


def test_inactive_product_alerts_are_resolved(db):
    p = make_product(db, stock=0)
    alert_service.check_product(db, p)
    p.is_active = False
    alert_service.check_product(db, p)
    assert alerts(db, p.id, unresolved_only=True) == []


# ---------- full monitoring run ----------


def test_run_inventory_check(db):
    healthy = make_product(db, sku="H-1", stock=50)
    low = make_product(db, sku="L-1", stock=15)
    out = make_product(db, sku="O-1", stock=0)
    make_product(db, sku="X-1", stock=0, active=False)

    first = alert_service.run_inventory_check(db)
    assert (first.products_checked, first.alerts_created, first.alerts_updated, first.alerts_resolved) == (4, 2, 0, 0)
    second = alert_service.run_inventory_check(db)
    assert (second.alerts_created, second.alerts_updated, second.alerts_resolved) == (0, 0, 0)  # no duplicates
    assert alerts(db, healthy.id) == []
    assert summary_of(db, low.id) == [("LOW_STOCK", "MEDIUM", "OPEN")]
    assert summary_of(db, out.id) == [("OUT_OF_STOCK", "CRITICAL", "OPEN")]


# ---------- real-time: stock movements and sales trigger checks ----------


def test_stock_movement_creates_and_resolves_alert(client, db, product):
    # fixture product: stock 12, reorder point 20, minimum 10 -> already LOW but never checked
    client.post("/api/inventory/transactions",
                json={"product_id": product.id, "transaction_type": "STOCK_OUT", "quantity": 4})
    assert summary_of(db, product.id) == [("LOW_STOCK", "HIGH", "OPEN")]  # 8 <= minimum 10
    client.post("/api/inventory/transactions",
                json={"product_id": product.id, "transaction_type": "STOCK_IN", "quantity": 100})
    assert summary_of(db, product.id) == [("LOW_STOCK", "HIGH", "RESOLVED")]


def test_sale_that_empties_stock_raises_critical_alert(client, db, product):
    res = client.post("/api/sales", json={"product_id": product.id, "quantity_sold": 12, "unit_price": "15.99"})
    assert res.status_code == 201
    assert summary_of(db, product.id) == [("OUT_OF_STOCK", "CRITICAL", "OPEN")]


def test_rejected_sale_creates_no_alert(client, db, product):
    res = client.post("/api/sales", json={"product_id": product.id, "quantity_sold": 99, "unit_price": "1.00"})
    assert res.status_code == 422
    assert alerts(db, product.id) == []


# ---------- concurrency: duplicate prevention by the database ----------


def test_concurrent_checks_create_only_one_alert(engine):
    """Two sessions check the same low-stock product at once. Both see no existing alert;
    the partial unique index makes the second insert wait, then fail, and the service
    treats that as 'already exists' instead of erroring or duplicating."""
    with Session(engine) as setup:
        p = Product(sku="CONC-ALERT", name="Concurrent", category="Test", current_stock=5,
                    reorder_point=20, minimum_stock=1, reorder_quantity=10, unit_cost=Decimal("1"))
        setup.add(p)
        setup.commit()
        pid = p.id

    outcome: dict = {}

    def second_session():
        with Session(engine) as s2:
            try:
                result = alert_service.check_product(s2, s2.get(Product, pid))
                s2.commit()
                outcome["created"] = len(result.created)
            except Exception as exc:  # pragma: no cover - reported in assertion
                outcome["error"] = repr(exc)

    try:
        with Session(engine) as s1:
            assert len(alert_service.check_product(s1, s1.get(Product, pid)).created) == 1
            worker = threading.Thread(target=second_session)
            worker.start()
            time.sleep(0.5)
            assert worker.is_alive(), "second insert should wait on the unique index"
            s1.commit()
        worker.join(timeout=10)

        assert outcome == {"created": 0}
        with Session(engine) as check:
            rows = check.scalars(select(InventoryAlert).where(InventoryAlert.product_id == pid)).all()
            assert [(a.alert_type, a.status) for a in rows] == [("LOW_STOCK", "OPEN")]
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(AIRecommendation).where(AIRecommendation.product_id == pid))
            cleanup.execute(delete(InventoryAlert).where(InventoryAlert.product_id == pid))
            cleanup.execute(delete(InventoryTransaction).where(InventoryTransaction.product_id == pid))
            cleanup.execute(delete(Product).where(Product.id == pid))
            cleanup.commit()
