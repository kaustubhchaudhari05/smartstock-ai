"""Deterministic stock status classification and reorder checks.

Business rule (CLAUDE.md, Workflow 2):
    current_stock == 0             -> OUT_OF_STOCK
    current_stock <= reorder_point -> LOW_STOCK
    otherwise                      -> HEALTHY

OVERSTOCKED is intentionally out of scope.
"""

import enum


class InventoryStatus(str, enum.Enum):
    HEALTHY = "HEALTHY"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"


def classify_stock(current_stock: int, reorder_point: int) -> InventoryStatus:
    if current_stock < 0 or reorder_point < 0:
        # The database forbids negative values; reaching this means corrupt input.
        raise ValueError("current_stock and reorder_point must be non-negative")
    if current_stock == 0:
        return InventoryStatus.OUT_OF_STOCK
    if current_stock <= reorder_point:
        return InventoryStatus.LOW_STOCK
    return InventoryStatus.HEALTHY


def needs_reorder(current_stock: int, reorder_point: int) -> bool:
    """True when stock has reached the reorder point (LOW_STOCK or OUT_OF_STOCK)."""
    return classify_stock(current_stock, reorder_point) != InventoryStatus.HEALTHY
