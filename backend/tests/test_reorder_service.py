import pytest
from sqlalchemy.exc import IntegrityError

from app.models import InventoryAlert
from decimal import Decimal

from app.models.ai_recommendation import RiskLevel
from app.services.reorder_service import (
    InventoryStatus,
    assess_risk,
    classify_stock,
    covers_lead_time,
    lead_time_demand,
    needs_reorder,
)

H, L, O = InventoryStatus.HEALTHY, InventoryStatus.LOW_STOCK, InventoryStatus.OUT_OF_STOCK


@pytest.mark.parametrize(
    "current_stock, reorder_point, expected",
    [
        (0, 20, O),     # nothing left
        (0, 0, O),      # out of stock wins even with reorder point 0
        (1, 20, L),
        (12, 20, L),    # Wireless Mouse demo case
        (20, 20, L),    # boundary: equal to reorder point is LOW_STOCK (<=)
        (21, 20, H),    # boundary: one above is HEALTHY
        (1, 0, H),      # reorder point 0: any stock is healthy
        (640, 30, H),
    ],
)
def test_classify_stock(current_stock, reorder_point, expected):
    assert classify_stock(current_stock, reorder_point) is expected


@pytest.mark.parametrize("current_stock, reorder_point", [(-1, 10), (5, -1)])
def test_classify_rejects_negative_input(current_stock, reorder_point):
    with pytest.raises(ValueError):
        classify_stock(current_stock, reorder_point)


def test_needs_reorder():
    assert needs_reorder(0, 20) is True
    assert needs_reorder(20, 20) is True
    assert needs_reorder(21, 20) is False


def test_statuses_are_exactly_the_supported_set():
    assert {s.value for s in InventoryStatus} == {"HEALTHY", "LOW_STOCK", "OUT_OF_STOCK"}


def test_overstocked_alert_type_rejected_by_database(db, product):
    db.add(InventoryAlert(product_id=product.id, alert_type="OVERSTOCKED", severity="LOW", message="x"))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.parametrize(
    "avg, lead, expected",
    [
        (Decimal("5.97"), 5, Decimal("29.85")),
        (Decimal("0.33"), 7, Decimal("2.31")),
        (Decimal("5.00"), 0, Decimal("0.00")),  # same-day delivery
        (Decimal("0"), 5, None),                # no demand
        (Decimal("5.00"), None, None),          # no supplier
    ],
)
def test_lead_time_demand(avg, lead, expected):
    assert lead_time_demand(avg, lead) == expected


def test_covers_lead_time():
    assert covers_lead_time(30, Decimal("29.85")) is True
    assert covers_lead_time(29, Decimal("29.85")) is False
    assert covers_lead_time(0, Decimal("0.00")) is True
    assert covers_lead_time(12, None) is None


@pytest.mark.parametrize(
    "stock, reorder, minimum, covers, expected",
    [
        (0, 20, 10, None, RiskLevel.CRITICAL),    # out of stock
        (0, 20, 10, True, RiskLevel.CRITICAL),
        (12, 20, 10, False, RiskLevel.CRITICAL),  # Wireless Mouse: runs out before delivery
        (50, 20, 10, False, RiskLevel.CRITICAL),  # healthy status but will not last the lead time
        (10, 20, 10, True, RiskLevel.HIGH),       # boundary: at minimum stock
        (10, 20, 10, None, RiskLevel.HIGH),
        (11, 20, 10, True, RiskLevel.MEDIUM),     # low stock, above minimum, covers lead time
        (20, 20, 10, None, RiskLevel.MEDIUM),     # boundary: at reorder point
        (21, 20, 10, True, RiskLevel.LOW),
        (21, 20, 10, None, RiskLevel.LOW),        # no sales data: status decides
    ],
)
def test_assess_risk(stock, reorder, minimum, covers, expected):
    assert assess_risk(stock, reorder, minimum, covers) is expected
