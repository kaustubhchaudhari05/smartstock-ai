import threading
import time
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    AIRecommendation,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderStatusHistory,
    Supplier,
)
from app.repositories import purchase_order_repository
from app.schemas.purchase_order import PurchaseOrderApprove
from app.services import purchase_order_service
from app.services.exceptions import ConflictError


@pytest.fixture
def draft(client, db, product):
    rec = AIRecommendation(
        product_id=product.id, recommendation="Order now.", suggested_quantity=120, risk_level="CRITICAL",
        urgency="IMMEDIATE", reasoning="Stock is low.", model_name="fake", prompt_version="test", context={})
    db.add(rec)
    db.commit()
    res = client.post("/api/purchase-orders", json={"recommendation_id": rec.id})
    assert res.status_code == 201
    return res.json()


def approve(client, order_id, **body):
    return client.patch(f"/api/purchase-orders/{order_id}/approve", json={"approver": "Priya Shah", **body})


def reject(client, order_id, **body):
    return client.patch(f"/api/purchase-orders/{order_id}/reject",
                        json={"approver": "Priya Shah", "reason": "Quantity too high", **body})


def test_draft_starts_with_a_creation_entry(draft):
    (entry,) = draft["status_history"]
    assert (entry["from_status"], entry["to_status"], entry["changed_by"]) == (None, "DRAFT", None)
    assert entry["comment"].startswith("Draft created from AI recommendation #")


def test_approve(client, db, product, draft):
    res = approve(client, draft["id"], comment="  Urgent, go ahead.  ")
    assert res.status_code == 200
    po = res.json()
    assert po["status"] == "APPROVED"
    assert datetime.fromisoformat(po["approved_at"]) >= datetime.fromisoformat(po["created_at"])
    assert po["total_amount"] == "1020.00"  # unchanged by approval
    created, approved = po["status_history"]
    assert (approved["from_status"], approved["to_status"], approved["changed_by"], approved["comment"]) == (
        "DRAFT", "APPROVED", "Priya Shah", "Urgent, go ahead.")
    db.refresh(product)
    assert product.current_stock == 12  # approval does not receive stock
    assert [o["id"] for o in client.get("/api/purchase-orders", params={"status": "APPROVED"}).json()] == [draft["id"]]


def test_reject_records_reason(client, draft):
    po = reject(client, draft["id"]).json()
    assert (po["status"], po["approved_at"]) == ("REJECTED", None)
    last = po["status_history"][-1]
    assert (last["from_status"], last["to_status"], last["changed_by"], last["comment"]) == (
        "DRAFT", "REJECTED", "Priya Shah", "Quantity too high")


def test_blank_comment_is_stored_as_null(client, draft):
    assert approve(client, draft["id"], comment="   ").json()["status_history"][-1]["comment"] is None


@pytest.mark.parametrize(
    ("first", "second", "message"),
    [
        (approve, approve, "is already APPROVED"),
        (approve, reject, "is already APPROVED"),
        (reject, approve, "is already REJECTED"),
        (reject, reject, "is already REJECTED"),
    ],
)
def test_decisions_are_final(client, draft, first, second, message):
    assert first(client, draft["id"]).status_code == 200
    res = second(client, draft["id"])
    assert res.status_code == 409
    assert res.json()["detail"] == f"Purchase order {draft['po_number']} {message}"
    assert len(client.get(f"/api/purchase-orders/{draft['id']}").json()["status_history"]) == 2


@pytest.mark.parametrize("status", ["SENT", "RECEIVED", "CANCELLED"])
def test_other_statuses_cannot_be_decided(client, db, draft, status):
    order = db.get(PurchaseOrder, draft["id"])
    order.status = status
    if status != "CANCELLED":
        order.approved_at = order.created_at
    db.commit()
    assert approve(client, draft["id"]).status_code == 409
    assert reject(client, draft["id"]).status_code == 409


def test_pending_approval_can_be_decided(client, db, draft):
    db.get(PurchaseOrder, draft["id"]).status = "PENDING_APPROVAL"
    db.commit()
    po = approve(client, draft["id"]).json()
    assert po["status"] == "APPROVED"
    assert po["status_history"][-1]["from_status"] == "PENDING_APPROVAL"


def test_approval_rechecks_master_data(client, db, product, supplier, draft):
    supplier.is_active = False
    db.commit()
    res = approve(client, draft["id"])
    assert res.status_code == 422 and res.json()["detail"] == "Supplier Acme Peripherals is inactive"
    po = client.get(f"/api/purchase-orders/{draft['id']}").json()
    assert po["status"] == "DRAFT" and len(po["status_history"]) == 1  # nothing written
    assert reject(client, draft["id"]).status_code == 200  # rejecting is still possible


def test_approval_rechecks_products(client, db, product, draft):
    other = Supplier(name="Other Co", email="sales@other.example", lead_time_days=4)
    db.add(other)
    db.commit()
    client.put(f"/api/products/{product.id}", json={"supplier_id": other.id})
    res = approve(client, draft["id"])
    assert res.status_code == 422 and "not supplied by Acme Peripherals" in res.json()["detail"]
    client.put(f"/api/products/{product.id}", json={"supplier_id": draft["supplier_id"]})
    client.delete(f"/api/products/{product.id}")
    res = approve(client, draft["id"])
    assert res.status_code == 422 and res.json()["detail"] == "Product WM-001 is inactive"


@pytest.mark.parametrize(
    ("action", "body"),
    [
        ("approve", {}),
        ("approve", {"approver": "   "}),
        ("approve", {"approver": "x" * 101}),
        ("approve", {"approver": "Priya", "status": "APPROVED"}),
        ("reject", {"approver": "Priya"}),
        ("reject", {"approver": "Priya", "reason": "  no "}),
        ("reject", {"reason": "Too many units"}),
    ],
)
def test_request_validation(client, draft, action, body):
    assert client.patch(f"/api/purchase-orders/{draft['id']}/{action}", json=body).status_code == 422


def test_unknown_order(client):
    res = approve(client, 999999)
    assert res.status_code == 404 and res.json() == {"detail": "Purchase order 999999 not found"}


def test_manual_draft_history(client, product, supplier):
    po = client.post("/api/purchase-orders", json={
        "supplier_id": supplier.id, "items": [{"product_id": product.id, "quantity": 10}]}).json()
    assert po["status_history"][0]["comment"] == "Draft created manually"


def test_concurrent_decisions_are_serialised(engine):
    """While one approver holds the order (and approves it), a second decision waits on the
    row lock, then sees APPROVED and gets a conflict instead of overwriting the decision."""
    with Session(engine) as setup:
        sup = Supplier(name="Conc Approver Supplier", email="a@conc.example", lead_time_days=2)
        p = Product(sku="CONC-APPR", name="Concurrency", category="Test", current_stock=1, reorder_point=5,
                    minimum_stock=1, reorder_quantity=10, unit_cost=Decimal("2.00"), supplier=sup)
        setup.add(p)
        setup.commit()
        ids = (sup.id, p.id)
    from app.schemas.purchase_order import PurchaseOrderCreate, PurchaseOrderItemCreate

    with Session(engine) as s0:
        order_id = purchase_order_service.create_draft(s0, PurchaseOrderCreate(
            supplier_id=ids[0], items=[PurchaseOrderItemCreate(product_id=ids[1], quantity=5)])).id

    outcome: dict = {}

    def second_approver():
        with Session(engine) as s2:
            try:
                purchase_order_service.approve(s2, order_id, PurchaseOrderApprove(approver="Second"))
                outcome["result"] = "approved"
            except ConflictError as exc:
                outcome["result"] = str(exc)

    try:
        with Session(engine) as s1:
            order = purchase_order_repository.lock_order(s1, order_id)
            worker = threading.Thread(target=second_approver)
            worker.start()
            time.sleep(0.5)
            assert worker.is_alive(), "second decision should wait for the order lock"
            order.status, order.approved_at = "APPROVED", datetime.now().astimezone()
            s1.commit()
        worker.join(timeout=10)
        assert outcome["result"].endswith("is already APPROVED")
        with Session(engine) as check:
            changed_by = check.scalars(select(PurchaseOrderStatusHistory.changed_by).where(
                PurchaseOrderStatusHistory.purchase_order_id == order_id)).all()
            assert "Second" not in changed_by
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(PurchaseOrderStatusHistory).where(
                PurchaseOrderStatusHistory.purchase_order_id == order_id))
            cleanup.execute(delete(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == order_id))
            cleanup.execute(delete(PurchaseOrder).where(PurchaseOrder.id == order_id))
            cleanup.execute(delete(Product).where(Product.id == ids[1]))
            cleanup.execute(delete(Supplier).where(Supplier.id == ids[0]))
            cleanup.commit()
