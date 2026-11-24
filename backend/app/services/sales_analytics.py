"""Deterministic sales analytics (CLAUDE.md Workflow 3). Never delegated to the LLM.

Definitions (as_of = now in UTC by default):
    7-day / 30-day     rolling windows: sales with as_of - N days < sale_date <= as_of.
                       Rolling (not calendar-day) windows avoid the bias a partly elapsed
                       "today" would add, while still counting today's sales immediately.
    daily sales        units per UTC calendar day for the 30 days ending on as_of's date,
                       zero-filled (for charts; today is a partial day)
    average daily      units_sold_30d / 30 (exact decimal, rounded to 0.01)
    days remaining     current_stock / average daily (exact, rounded to 0.1);
                       None if there were no sales in the 30-day window
    trend              7-day daily average vs 30-day daily average:
                       > +15% INCREASING, < -15% DECREASING, else STABLE;
                       INSUFFICIENT_DATA if there were no sales in the 30-day window
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Product, Sale
from app.schemas.sales_analytics import (
    AnalyticsDefinitions,
    DailySales,
    ProductSalesMetrics,
    SalesAnalytics,
    SalesAnalyticsSummary,
    SalesTrend,
)
from app.services.exceptions import NotFoundError

SHORT_WINDOW = 7
LONG_WINDOW = 30
TREND_THRESHOLD = Decimal("0.15")
CENT = Decimal("0.01")
TENTH = Decimal("0.1")


# ---------- pure calculations ----------


def daily_series(units_by_day: dict[date, int], last_day: date, days: int) -> list[DailySales]:
    """`days` consecutive calendar days ending at last_day (oldest first), zero-filled."""
    start = last_day - timedelta(days=days - 1)
    return [
        DailySales(date=d, units_sold=units_by_day.get(d, 0))
        for d in (start + timedelta(days=i) for i in range(days))
    ]


def average_daily(units: int, days: int) -> Decimal:
    return (Decimal(units) / Decimal(days)).quantize(CENT, rounding=ROUND_HALF_UP)


def days_remaining(current_stock: int, units_sold_30d: int) -> Decimal | None:
    """current_stock / (units_30d / 30), computed exactly before rounding. None for zero demand."""
    if units_sold_30d <= 0:
        return None
    exact = Decimal(current_stock) * LONG_WINDOW / Decimal(units_sold_30d)
    return exact.quantize(TENTH, rounding=ROUND_HALF_UP)


def sales_trend(units_7d: int, units_30d: int) -> SalesTrend:
    if units_30d <= 0:
        return SalesTrend.INSUFFICIENT_DATA
    # (units_7d / 7) / (units_30d / 30), exact
    ratio = (Decimal(units_7d) * LONG_WINDOW) / (Decimal(units_30d) * SHORT_WINDOW)
    if ratio > 1 + TREND_THRESHOLD:
        return SalesTrend.INCREASING
    if ratio < 1 - TREND_THRESHOLD:
        return SalesTrend.DECREASING
    return SalesTrend.STABLE


def build_metrics(
    product: Product,
    *,
    units_7d: int,
    units_30d: int,
    units_total: int,
    daily: list[DailySales] | None = None,
) -> ProductSalesMetrics:
    return ProductSalesMetrics(
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        current_stock=product.current_stock,
        units_sold_total=units_total,
        units_sold_7d=units_7d,
        units_sold_30d=units_30d,
        average_daily_sales_7d=average_daily(units_7d, SHORT_WINDOW),
        average_daily_sales=average_daily(units_30d, LONG_WINDOW),
        days_remaining=days_remaining(product.current_stock, units_30d),
        trend=sales_trend(units_7d, units_30d),
        daily_sales=daily,
    )


# ---------- database aggregation ----------


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _window_totals(
    db: Session, as_of: datetime, product_id: int | None
) -> dict[int, tuple[int, int, int]]:
    """{product_id: (units_7d, units_30d, units_total)} in one query, rolling windows ending at as_of."""
    qty = Sale.quantity_sold
    in_window = lambda days: Sale.sale_date > as_of - timedelta(days=days)
    stmt = (
        select(
            Sale.product_id,
            func.coalesce(func.sum(qty).filter(in_window(SHORT_WINDOW)), 0),
            func.coalesce(func.sum(qty).filter(in_window(LONG_WINDOW)), 0),
            func.sum(qty),
        )
        .where(Sale.sale_date <= as_of)
        .group_by(Sale.product_id)
    )
    if product_id is not None:
        stmt = stmt.where(Sale.product_id == product_id)
    return {pid: (int(u7), int(u30), int(total)) for pid, u7, u30, total in db.execute(stmt)}


def _daily_units(db: Session, as_of: datetime, product_id: int) -> dict[date, int]:
    """Units per UTC calendar day for the 30 days ending on as_of's date (up to as_of)."""
    last_day = as_of.astimezone(timezone.utc).date()
    start = datetime.combine(last_day - timedelta(days=LONG_WINDOW - 1), time.min, tzinfo=timezone.utc)
    day = func.date(func.timezone("UTC", Sale.sale_date))
    stmt = (
        select(day, func.sum(Sale.quantity_sold))
        .where(Sale.product_id == product_id, Sale.sale_date >= start, Sale.sale_date <= as_of)
        .group_by(day)
    )
    result: dict[date, int] = defaultdict(int)
    for d, units in db.execute(stmt):
        result[d] = int(units)
    return result


def product_metrics(db: Session, product_id: int, as_of: datetime | None = None) -> ProductSalesMetrics:
    """Metrics for one product, including its 30-day daily series."""
    as_of = as_of or now_utc()
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError(f"Product {product_id} not found")
    u7, u30, total = _window_totals(db, as_of, product_id).get(product_id, (0, 0, 0))
    daily = daily_series(
        _daily_units(db, as_of, product_id), as_of.astimezone(timezone.utc).date(), LONG_WINDOW
    )
    return build_metrics(product, units_7d=u7, units_30d=u30, units_total=total, daily=daily)


def all_product_metrics(
    db: Session, as_of: datetime | None = None, include_inactive: bool = False
) -> list[ProductSalesMetrics]:
    """Metrics for every product (one aggregate query), sorted by SKU. No daily series."""
    as_of = as_of or now_utc()
    stmt = select(Product).order_by(Product.sku)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    totals = _window_totals(db, as_of, None)
    metrics = []
    for p in db.scalars(stmt).all():
        u7, u30, total = totals.get(p.id, (0, 0, 0))
        metrics.append(build_metrics(p, units_7d=u7, units_30d=u30, units_total=total))
    return metrics


# ---------- API response ----------


def get_analytics(
    db: Session,
    *,
    product_id: int | None = None,
    include_inactive: bool = False,
    as_of: datetime | None = None,
) -> SalesAnalytics:
    """All products (no daily series), or one product with its 30-day daily series."""
    as_of = as_of or now_utc()
    if product_id is not None:
        products = [product_metrics(db, product_id, as_of=as_of)]
    else:
        products = all_product_metrics(db, as_of=as_of, include_inactive=include_inactive)
    trend_count = lambda trend: sum(m.trend == trend for m in products)
    return SalesAnalytics(
        as_of=as_of,
        definitions=AnalyticsDefinitions(
            short_window_days=SHORT_WINDOW,
            long_window_days=LONG_WINDOW,
            trend_threshold=TREND_THRESHOLD,
        ),
        summary=SalesAnalyticsSummary(
            products=len(products),
            units_sold_7d=sum(m.units_sold_7d for m in products),
            units_sold_30d=sum(m.units_sold_30d for m in products),
            increasing=trend_count(SalesTrend.INCREASING),
            stable=trend_count(SalesTrend.STABLE),
            decreasing=trend_count(SalesTrend.DECREASING),
            insufficient_data=trend_count(SalesTrend.INSUFFICIENT_DATA),
        ),
        products=products,
    )
