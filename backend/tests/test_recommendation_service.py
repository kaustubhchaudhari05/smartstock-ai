import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.ai import recommendation_service as svc
from app.ai.client import FakeLLMClient, LLMInvalidResponseError, LLMNotConfiguredError, LLMTimeoutError
from app.core.limits import MAX_STOCK
from app.models import AIRecommendation, InventoryAlert, Product, PurchaseOrder, Sale
from app.services import alert_service
from app.services.exceptions import BusinessRuleError, NotFoundError

AS_OF = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def answer(**overrides):
    base = {
        "urgency": "IMMEDIATE",
        "recommendation": "Order 120 units of Wireless Mouse today.",
        "suggested_quantity": 120,
        "reasoning": ["Stock of 12 is below the reorder point of 20.", "Stock runs out before delivery."],
    }
    return json.dumps({**base, **overrides})


def add_sales(db, product, per_day=5, days=30):
    for i in range(days):
        db.add(Sale(product_id=product.id, quantity_sold=per_day, unit_price=Decimal("15.99"),
                    sale_date=AS_OF - timedelta(hours=1 + 24 * i)))
    db.commit()


def generate(db, product, fake, **kwargs):
    return svc.generate_recommendation(db, product.id, llm=fake, as_of=AS_OF, **kwargs)


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


@pytest.fixture
def selling_product(db, product):
    """Wireless Mouse: 12 in stock, 5/day, 7-day lead time -> 35 units needed -> CRITICAL."""
    add_sales(db, product)
    alert_service.check_product(db, product)
    db.commit()
    return product


def test_generates_and_stores_validated_recommendation(db, selling_product):
    fake = FakeLLMClient([answer(reasoning=["  Stock is\n low. ", "Order now."])])
    rec = generate(db, selling_product, fake)

    assert rec.id is not None
    assert (rec.risk_level, rec.urgency, rec.suggested_quantity, rec.status) == (
        "CRITICAL", "IMMEDIATE", 120, "PENDING_REVIEW")
    assert rec.reasoning == "Stock is low.\nOrder now."
    assert (rec.model_name, rec.prompt_version, rec.prompt_tokens) == ("fake", svc.PROMPT_VERSION, 0)
    alert = db.scalars(select(InventoryAlert).where(InventoryAlert.product_id == selling_product.id)).one()
    assert rec.alert_id == alert.id

    ctx = rec.context  # exact data the LLM saw, stored for audit and the UI
    assert ctx["product"]["current_stock"] == 12
    assert ctx["sales"]["average_daily_sales_30d"] == "5.00"
    assert len(ctx["sales"]["daily_units_last_30d"]) == 30
    assert ctx["risk"] == {
        "risk_level": "CRITICAL", "at_or_below_reorder_point": True, "at_or_below_minimum_stock": False,
        "expected_demand_during_lead_time": "35.00", "stock_covers_lead_time": False}
    assert ctx["quantity_guidance"] == {"min_quantity": 0, "max_quantity": 450}  # 90 days x 5/day
    assert ctx["alert"] == {"alert_type": "LOW_STOCK", "severity": "MEDIUM"}

    # decision support only: stock and orders untouched
    db.refresh(selling_product)
    assert selling_product.current_stock == 12
    assert count(db, PurchaseOrder) == 0


def test_llm_receives_context_but_no_supplier_contact_details(db, selling_product):
    fake = FakeLLMClient([answer()])
    generate(db, selling_product, fake)
    (call,) = fake.calls
    assert '"sku": "WM-001"' in call["user"]
    assert "Acme Peripherals" in call["user"]
    assert "orders@acme.example" not in call["user"]
    assert call["schema_name"] == "inventory_recommendation"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"suggested_quantity": 451}, "outside the allowed range 0-450"),
        ({"urgency": "NONE", "suggested_quantity": 50}, "urgency NONE"),
        ({"urgency": "SOON", "suggested_quantity": 0}, "urgency NONE"),
        ({"urgency": "ROUTINE"}, "contradicts risk level CRITICAL"),
        ({"urgency": "NONE", "suggested_quantity": 0}, "contradicts risk level CRITICAL"),
        ({"suggested_quantity": -1}, "suggested_quantity"),
        ({"risk_level": "LOW"}, "risk_level"),  # the LLM may not set the risk level
    ],
)
def test_invalid_answers_are_rejected_and_nothing_is_saved(db, selling_product, override, message):
    with pytest.raises(LLMInvalidResponseError, match=message):
        generate(db, selling_product, FakeLLMClient([answer(**override)]))
    assert count(db, AIRecommendation) == 0


def test_upper_bound_is_inclusive(db, selling_product):
    assert generate(db, selling_product, FakeLLMClient([answer(suggested_quantity=450)])).suggested_quantity == 450


def test_llm_failure_saves_nothing_and_keeps_alerts(db, selling_product):
    with pytest.raises(LLMTimeoutError):
        generate(db, selling_product, FakeLLMClient([LLMTimeoutError("slow")]))
    assert count(db, AIRecommendation) == 0
    assert count(db, InventoryAlert) == 1  # monitoring results are independent of the LLM


def test_healthy_product_may_get_no_order(db, product):
    product.current_stock = 500
    db.commit()
    add_sales(db, product, per_day=2)
    rec = generate(db, product, FakeLLMClient([answer(urgency="NONE", suggested_quantity=0)]))
    assert (rec.risk_level, rec.urgency, rec.suggested_quantity, rec.alert_id) == ("LOW", "NONE", 0, None)


def test_product_without_supplier_or_sales(db, product):
    product.supplier_id = None
    db.commit()
    db.refresh(product)
    fake = FakeLLMClient([answer(urgency="SOON", suggested_quantity=100)])
    rec = generate(db, product, fake)
    ctx = rec.context
    assert ctx["supplier"] is None
    assert ctx["sales"]["days_remaining"] is None and ctx["sales"]["trend"] == "INSUFFICIENT_DATA"
    assert ctx["risk"]["expected_demand_during_lead_time"] is None
    assert ctx["risk"]["stock_covers_lead_time"] is None
    assert rec.risk_level == "MEDIUM"  # low stock, above minimum, lead time unknown
    assert ctx["quantity_guidance"]["max_quantity"] == 300  # 3 x reorder quantity


def test_explicit_alert_must_match_and_be_unresolved(db, selling_product, supplier):
    other = Product(sku="KB-002", name="Keyboard", category="Electronics", current_stock=0,
                    reorder_point=5, minimum_stock=2, reorder_quantity=20, unit_cost=Decimal("20.00"),
                    supplier=supplier)
    db.add(other)
    db.flush()
    alert_service.check_product(db, other)
    db.commit()
    other_alert = db.scalars(select(InventoryAlert).where(InventoryAlert.product_id == other.id)).one()
    fake = FakeLLMClient([answer()])

    with pytest.raises(BusinessRuleError, match="does not belong"):
        generate(db, selling_product, fake, alert_id=other_alert.id)
    with pytest.raises(NotFoundError, match="Alert 999999"):
        generate(db, selling_product, fake, alert_id=999999)

    own = db.scalars(select(InventoryAlert).where(InventoryAlert.product_id == selling_product.id)).one()
    own.status, own.resolved_at = "RESOLVED", AS_OF
    db.commit()
    with pytest.raises(BusinessRuleError, match="already resolved"):
        generate(db, selling_product, fake, alert_id=own.id)
    assert fake.calls == []  # rejected before calling the LLM


def test_unknown_or_inactive_product(db, product):
    fake = FakeLLMClient([answer()])
    with pytest.raises(NotFoundError, match="Product 999999"):
        svc.generate_recommendation(db, 999999, llm=fake)
    product.is_active = False
    db.commit()
    with pytest.raises(BusinessRuleError, match="inactive"):
        generate(db, product, fake)
    assert fake.calls == []


def test_without_injected_client_uses_configured_client(db, product):
    # conftest blocks real LLM clients; this checks that the configured client is used
    with pytest.raises(LLMNotConfiguredError, match="Tests must not call a real LLM"):
        svc.generate_recommendation(db, product.id)


@pytest.mark.parametrize(
    ("stock", "reorder_qty", "avg", "expected_max"),
    [
        (12, 100, Decimal("5.00"), 450),   # 90 days of demand beats 3 x 100
        (12, 200, Decimal("5.00"), 600),   # 3 standard orders beat 450
        (12, 0, Decimal("0"), 1),          # nothing configured: still allows ordering 1
        (12, 100, Decimal("0.01"), 300),
        (12, 900_000, Decimal("0"), 1_000_000),     # capped at the largest single movement
        (MAX_STOCK - 10, 100, Decimal("0"), 10),     # never beyond the stock column limit
        (MAX_STOCK, 100, Decimal("0"), 0),
    ],
)
def test_quantity_bounds(stock, reorder_qty, avg, expected_max):
    p = Product(current_stock=stock, reorder_quantity=reorder_qty)
    assert svc.quantity_bounds(p, avg).model_dump() == {"min_quantity": 0, "max_quantity": expected_max}
