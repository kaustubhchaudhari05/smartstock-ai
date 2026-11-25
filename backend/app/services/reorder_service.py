"""Deterministic stock status classification and reorder checks.

Business rule (CLAUDE.md, Workflow 2):
    current_stock == 0             -> OUT_OF_STOCK
    current_stock <= reorder_point -> LOW_STOCK
    otherwise                      -> HEALTHY

OVERSTOCKED is intentionally out of scope.

Replenishment risk (decided here, explained by the LLM), first match wins:
    OUT_OF_STOCK                                   -> CRITICAL
    stock does not cover demand during lead time   -> CRITICAL
    current_stock <= minimum_stock                 -> HIGH
    LOW_STOCK                                      -> MEDIUM
    otherwise                                      -> LOW
"""

import enum
from decimal import ROUND_HALF_UP, Decimal

from app.models.ai_recommendation import RiskLevel


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


def lead_time_demand(average_daily_sales: Decimal, lead_time_days: int | None) -> Decimal | None:
    """Expected units sold while waiting for a delivery; None without a lead time or demand."""
    if lead_time_days is None or average_daily_sales <= 0:
        return None
    return (average_daily_sales * lead_time_days).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def covers_lead_time(current_stock: int, expected_demand: Decimal | None) -> bool | None:
    """True if current stock lasts until a new delivery arrives; None if demand is unknown."""
    if expected_demand is None:
        return None
    return Decimal(current_stock) >= expected_demand


def assess_risk(
    current_stock: int, reorder_point: int, minimum_stock: int, stock_covers_lead_time: bool | None
) -> RiskLevel:
    status = classify_stock(current_stock, reorder_point)
    if status == InventoryStatus.OUT_OF_STOCK or stock_covers_lead_time is False:
        return RiskLevel.CRITICAL
    if current_stock <= minimum_stock:
        return RiskLevel.HIGH
    if status == InventoryStatus.LOW_STOCK:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW
