import re
from decimal import Decimal

import pytest

from app.models import AIRecommendation, Product, Supplier
from app.services.purchase_order_service import line_totals


@pytest.fixture
def recommendation(db, product):
    def make(suggested_quantity=120, target=product):
        rec = AIRecommendation(
            product_id=target.id, recommendation="Order now.", suggested_quantity=suggested_quantity,
            risk_level="CRITICAL", urgency="IMMEDIATE" if suggested_quantity else "NONE",
            reasoning="Stock is low.", model_name="fake", prompt_version="test", context={})
        db.add(rec)
        db.commit()
        return rec

    return make


@pytest.fixture
def cable(db, supplier):
    p = Product(sku="CBL-010", name="USB Cable", category="Electronics", current_stock=40, reorder_point=30,
                minimum_stock=10, reorder_quantity=200, unit_cost=Decimal("0.10"), supplier=supplier)
    db.add(p)
    db.commit()
    return p


def create(client, **body):
    return client.post("/api/purchase-orders", json=body)


def test_draft_from_recommendation(client, db, product, recommendation):
    rec = recommendation()
    res = create(client, recommendation_id=rec.id)
    assert res.status_code == 201
    po = res.json()
    assert re.fullmatch(r"PO-\d{4}-\d{5}", po["po_number"]) and po["po_number"].endswith(f"{po['id']:05d}")
    assert (po["status"], po["total_amount"], po["item_count"], po["approved_at"]) == ("DRAFT", "1020.00", 1, None)
    assert po["supplier"]["name"] == "Acme Peripherals" and po["supplier"]["email"] == "orders@acme.example"
    (item,) = po["items"]
    assert (item["product_sku"], item["quantity"], item["unit_price"], item["total_price"], item["recommendation_id"]) == (
        "WM-001", 120, "8.50", "1020.00", rec.id)

    db.refresh(rec)
    db.refresh(product)
    assert rec.status == "ACCEPTED"
    assert product.current_stock == 12  # a draft never changes stock
    assert client.get(f"/api/purchase-orders/{po['id']}").json() == po


def test_recommendation_can_be_used_once(client, recommendation):
    rec = recommendation()
    assert create(client, recommendation_id=rec.id).status_code == 201
    res = create(client, recommendation_id=rec.id)
    assert res.status_code == 409
    assert res.json()["detail"] == f"Recommendation {rec.id} is already ACCEPTED"


def test_recommendation_overrides(client, recommendation):
    po = create(client, recommendation_id=recommendation().id, quantity=150, unit_price="8.00").json()
    assert (po["items"][0]["quantity"], po["items"][0]["unit_price"], po["total_amount"]) == (150, "8.00", "1200.00")


def test_recommendation_without_suggested_order(client, db, recommendation):
    rec = recommendation(suggested_quantity=0)
    res = create(client, recommendation_id=rec.id)
    assert res.status_code == 422 and "suggests no order" in res.json()["detail"]
    db.refresh(rec)
    assert rec.status == "PENDING_REVIEW"  # nothing changed
    assert create(client, recommendation_id=rec.id, quantity=10).status_code == 201


def test_recommendation_errors(client, db, product, recommendation):
    assert create(client, recommendation_id=999999).status_code == 404
    rec = recommendation()
    product.supplier_id = None
    db.commit()
    res = create(client, recommendation_id=rec.id)
    assert res.status_code == 422 and "has no supplier" in res.json()["detail"]


def test_manual_draft_totals_are_exact(client, product, cable, supplier):
    res = create(client, supplier_id=supplier.id, items=[
        {"product_id": product.id, "quantity": 7, "unit_price": "19.99"},
        {"product_id": cable.id, "quantity": 3},  # 3 x 0.10 must be 0.30 exactly
    ])
    assert res.status_code == 201
    po = res.json()
    assert [(i["product_sku"], i["unit_price"], i["total_price"], i["recommendation_id"]) for i in po["items"]] == [
        ("WM-001", "19.99", "139.93", None), ("CBL-010", "0.10", "0.30", None)]
    assert po["total_amount"] == "140.23"


def test_supplier_and_product_rules(client, db, product, cable, supplier, inactive_supplier):
    other = Supplier(name="Other Co", email="sales@other.example", lead_time_days=4)
    db.add(other)
    db.commit()
    line = [{"product_id": product.id, "quantity": 5}]

    def detail(**body):
        res = create(client, **body)
        assert res.status_code == 422, res.json()
        return res.json()["detail"]

    assert "not supplied by Other Co" in detail(supplier_id=other.id, items=line)
    assert detail(supplier_id=inactive_supplier.id, items=line) == "Supplier Old Supplier is inactive"
    assert detail(supplier_id=999999, items=line) == "Supplier 999999 not found"
    assert detail(supplier_id=supplier.id, items=[{"product_id": 999999, "quantity": 1}]) == "Product 999999 not found"
    assert "appears twice" in detail(supplier_id=supplier.id, items=line * 2)
    client.delete(f"/api/products/{cable.id}")
    assert detail(supplier_id=supplier.id, items=[{"product_id": cable.id, "quantity": 1}]) == "Product CBL-010 is inactive"
    supplier.is_active = False
    db.commit()
    assert detail(supplier_id=supplier.id, items=line) == "Supplier Acme Peripherals is inactive"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"supplier_id": 1},
        {"items": [{"product_id": 1, "quantity": 1}]},  # supplier required
        {"recommendation_id": 1, "items": [{"product_id": 1, "quantity": 1}]},
        {"supplier_id": 1, "items": [{"product_id": 1, "quantity": 1}], "quantity": 5},
        {"supplier_id": 1, "items": []},
        {"supplier_id": 1, "items": [{"product_id": 1, "quantity": 0}]},
        {"supplier_id": 1, "items": [{"product_id": 1, "quantity": 1_000_001}]},
        {"supplier_id": 1, "items": [{"product_id": 1, "quantity": 1, "unit_price": "1.005"}]},
        {"supplier_id": 1, "items": [{"product_id": 1, "quantity": 1, "unit_price": "-1"}]},
        {"supplier_id": 1, "items": [{"product_id": 1, "quantity": 1}], "status": "APPROVED"},
        {"recommendation_id": 0},
    ],
)
def test_request_validation(client, body):
    assert create(client, **body).status_code == 422


def test_total_too_large(client, product, supplier):
    res = create(client, supplier_id=supplier.id, items=[
        {"product_id": product.id, "quantity": 1_000_000, "unit_price": "9999999999.99"}])
    assert res.status_code == 422 and res.json()["detail"] == "Order total is too large"


def test_list_and_filters(client, product, cable, supplier, recommendation):
    first = create(client, recommendation_id=recommendation().id).json()
    second = create(client, supplier_id=supplier.id, items=[{"product_id": cable.id, "quantity": 50}]).json()
    items = client.get("/api/purchase-orders").json()
    assert [i["id"] for i in items] == [second["id"], first["id"]]
    assert "items" not in items[0] and items[0]["supplier_name"] == "Acme Peripherals"
    assert len(client.get("/api/purchase-orders", params={"status": "DRAFT"}).json()) == 2
    assert client.get("/api/purchase-orders", params={"status": "APPROVED"}).json() == []
    assert client.get("/api/purchase-orders", params={"supplier_id": 999999}).json() == []
    assert client.get("/api/purchase-orders", params={"status": "BOGUS"}).status_code == 422


def test_unknown_order(client):
    res = client.get("/api/purchase-orders/999999")
    assert res.status_code == 404 and res.json() == {"detail": "Purchase order 999999 not found"}


def test_line_totals():
    totals, total = line_totals([(3, Decimal("0.10")), (7, Decimal("19.99")), (1, Decimal("0"))])
    assert totals == [Decimal("0.30"), Decimal("139.93"), Decimal("0.00")]
    assert total == Decimal("140.23")
    assert line_totals([]) == ([], Decimal("0.00"))


def test_concurrent_drafts_from_one_recommendation(engine):
    """While one request holds the recommendation row (and accepts it), a second request
    waits on the row lock, then sees ACCEPTED and gets a conflict instead of a second order."""
    import threading
    import time

    from sqlalchemy import delete, select
    from sqlalchemy.orm import Session

    from app.models import PurchaseOrder, PurchaseOrderItem
    from app.repositories import purchase_order_repository
    from app.schemas.purchase_order import PurchaseOrderCreate
    from app.services import purchase_order_service
    from app.services.exceptions import ConflictError

    with Session(engine) as setup:
        sup = Supplier(name="Conc Supplier", email="c@conc.example", lead_time_days=2)
        p = Product(sku="CONC-PO", name="Concurrency", category="Test", current_stock=1, reorder_point=5,
                    minimum_stock=1, reorder_quantity=10, unit_cost=Decimal("2.00"), supplier=sup)
        setup.add(p)
        setup.flush()
        rec = AIRecommendation(product_id=p.id, recommendation="Order.", suggested_quantity=10,
                               risk_level="HIGH", urgency="SOON", reasoning="r", model_name="fake",
                               prompt_version="test", context={})
        setup.add(rec)
        setup.commit()
        ids = (sup.id, p.id, rec.id)

    outcome: dict = {}

    def second_request():
        with Session(engine) as s2:
            try:
                purchase_order_service.create_draft(s2, PurchaseOrderCreate(recommendation_id=ids[2]))
                outcome["result"] = "created"
            except ConflictError as exc:
                outcome["result"] = str(exc)

    try:
        with Session(engine) as s1:
            first = purchase_order_repository.lock_recommendation(s1, ids[2])
            worker = threading.Thread(target=second_request)
            worker.start()
            time.sleep(0.5)
            assert worker.is_alive(), "second request should wait for the recommendation lock"
            first.status = "ACCEPTED"  # what the first request does before committing
            s1.commit()
        worker.join(timeout=10)
        assert outcome["result"] == f"Recommendation {ids[2]} is already ACCEPTED"
        with Session(engine) as check:
            assert check.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.product_id == ids[1])).all() == []
    finally:
        with Session(engine) as cleanup:
            from app.models import PurchaseOrderStatusHistory

            order_ids = [o for (o,) in cleanup.execute(
                select(PurchaseOrderItem.purchase_order_id).where(PurchaseOrderItem.product_id == ids[1]))]
            cleanup.execute(delete(PurchaseOrderStatusHistory).where(
                PurchaseOrderStatusHistory.purchase_order_id.in_(order_ids)))
            cleanup.execute(delete(PurchaseOrder).where(PurchaseOrder.id.in_(order_ids)))
            cleanup.execute(delete(AIRecommendation).where(AIRecommendation.id == ids[2]))
            cleanup.execute(delete(Product).where(Product.id == ids[1]))
            cleanup.execute(delete(Supplier).where(Supplier.id == ids[0]))
            cleanup.commit()
