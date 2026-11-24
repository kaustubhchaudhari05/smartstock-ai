import enum
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class SalesTrend(str, enum.Enum):
    INCREASING = "INCREASING"
    STABLE = "STABLE"
    DECREASING = "DECREASING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class DailySales(BaseModel):
    date: date
    units_sold: int


class ProductSalesMetrics(BaseModel):
    product_id: int
    sku: str
    name: str
    current_stock: int
    units_sold_total: int = Field(description="All-time units sold")
    units_sold_7d: int = Field(description="Rolling last 7 x 24 hours")
    units_sold_30d: int = Field(description="Rolling last 30 x 24 hours")
    average_daily_sales_7d: Decimal
    average_daily_sales: Decimal = Field(description="Average daily demand: units_sold_30d / 30")
    days_remaining: Decimal | None = Field(
        description="current_stock / average_daily_sales; null when there were no sales in 30 days"
    )
    trend: SalesTrend
    daily_sales: list[DailySales] | None = Field(
        default=None,
        description="Units per UTC calendar day, last 30 days oldest first, today partial "
        "(single-product requests only)",
    )
