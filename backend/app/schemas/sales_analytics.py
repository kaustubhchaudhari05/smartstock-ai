import enum
from datetime import date, datetime
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


class AnalyticsDefinitions(BaseModel):
    """The rules used, returned so the UI (and the LLM later) can state them precisely."""

    short_window_days: int
    long_window_days: int
    trend_threshold: Decimal = Field(description="0.15 = 7-day vs 30-day daily average must differ by >15%")
    windows: str = "rolling, ending at as_of"


class SalesAnalyticsSummary(BaseModel):
    products: int
    units_sold_7d: int
    units_sold_30d: int
    increasing: int
    stable: int
    decreasing: int
    insufficient_data: int


class SalesAnalytics(BaseModel):
    as_of: datetime
    definitions: AnalyticsDefinitions
    summary: SalesAnalyticsSummary
    products: list[ProductSalesMetrics]
