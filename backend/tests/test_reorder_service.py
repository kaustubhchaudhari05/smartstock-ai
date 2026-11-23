import pytest
from sqlalchemy.exc import IntegrityError

from app.models import InventoryAlert
from app.services.reorder_service import InventoryStatus, classify_stock, needs_reorder

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
