from decimal import Decimal

from app.models import Product, PurchaseOrder, Supplier

ORDER = ["DRAFT", "PENDING_APPROVAL", "APPROVED", "REJECTED", "SENT", "RECEIVED", "CANCELLED"]


def make_order(client, db, supplier, product, quantity, unit_price, status="DRAFT"):
    po = client.post("/api/purchase-orders", json={"supplier_id": supplier.id, "items": [
        {"product_id": product.id, "quantity": quantity, "unit_price": unit_price}]}).json()
    if status != "DRAFT":
        order = db.get(PurchaseOrder, po["id"])
        order.status = status
        if status in ("APPROVED", "SENT", "RECEIVED"):
            order.approved_at = order.created_at
        db.commit()
    return po


def summary(client, **params):
    res = client.get("/api/purchase-orders/summary", params=params)
    assert res.status_code == 200
    return res.json()


def test_empty_summary_is_zero_filled(client):
    body = summary(client)
    assert [s["status"] for s in body["by_status"]] == ORDER
    assert all(s == {"status": s["status"], "order_count": 0, "total_amount": "0.00"} for s in body["by_status"])
    assert (body["awaiting_decision_count"], body["awaiting_decision_amount"], body["approved_count"],
            body["approved_amount"], body["total_orders"]) == (0, "0.00", 0, "0.00", 0)


def test_counts_and_amounts_per_status(client, db, product, supplier):
    make_order(client, db, supplier, product, 3, "0.10")                       # 0.30 DRAFT
    make_order(client, db, supplier, product, 7, "19.99", "PENDING_APPROVAL")  # 139.93
    make_order(client, db, supplier, product, 100, "8.50", "APPROVED")         # 850.00
    make_order(client, db, supplier, product, 1, "5.00", "REJECTED")           # 5.00
    make_order(client, db, supplier, product, 2, "1.25", "DRAFT")              # 2.50

    body = summary(client)
    by = {s["status"]: (s["order_count"], s["total_amount"]) for s in body["by_status"]}
    assert by == {"DRAFT": (2, "2.80"), "PENDING_APPROVAL": (1, "139.93"), "APPROVED": (1, "850.00"),
                  "REJECTED": (1, "5.00"), "SENT": (0, "0.00"), "RECEIVED": (0, "0.00"),
                  "CANCELLED": (0, "0.00")}
    assert (body["awaiting_decision_count"], body["awaiting_decision_amount"]) == (3, "142.73")
    assert (body["approved_count"], body["approved_amount"], body["total_orders"]) == (1, "850.00", 5)


def test_supplier_filter(client, db, product, supplier):
    other = Supplier(name="Other Co", email="sales@other.example", lead_time_days=4)
    servo = Product(sku="SRV-304", name="Servo", category="Components", current_stock=50, reorder_point=15,
                    minimum_stock=8, reorder_quantity=50, unit_cost=Decimal("3.20"), supplier=other)
    db.add(servo)
    db.commit()
    make_order(client, db, supplier, product, 10, "8.50")
    make_order(client, db, other, servo, 10, "3.20")

    assert summary(client)["awaiting_decision_amount"] == "117.00"
    assert summary(client, supplier_id=other.id)["awaiting_decision_amount"] == "32.00"
    assert summary(client, supplier_id=999999)["total_orders"] == 0


def test_summary_route_is_not_taken_for_an_order_id(client):
    assert client.get("/api/purchase-orders/summary").status_code == 200
    assert client.get("/api/purchase-orders/999999").status_code == 404
